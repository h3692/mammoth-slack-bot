from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from slack_sdk.web.async_client import AsyncWebClient

from models import Campaign, Submission, SubmissionStatus, SubmissionType
from rate_limiter import RateLimiter
from store import InMemoryStore
from summarizer import URLSummarizer, extract_url

# Points awarded per action
POINTS_URL = 10
POINTS_IDEA = 5
POINTS_KUDOS = 15
POINTS_ANONYMOUS = 20
POINTS_VALIDATION_BONUS = 25
POINTS_REACTION = 2


def strip_pii(text: str) -> str:
    """Remove emails, phone numbers, and Slack user mentions from text."""
    # Email addresses
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[REDACTED]", text)
    # Phone numbers (various formats)
    text = re.sub(
        r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", "[REDACTED]", text
    )
    # Slack user mentions <@U12345>
    text = re.sub(r"<@U\w+>", "[REDACTED]", text)
    return text


def detect_submission_type(text: str) -> SubmissionType:
    """Detect submission type from message content."""
    if extract_url(text):
        return SubmissionType.URL
    kudos_keywords = ["kudos", "shoutout", "props", "great job", "well done", "thank you", "thanks to"]
    if any(kw in text.lower() for kw in kudos_keywords):
        return SubmissionType.KUDOS
    return SubmissionType.IDEA


class SlackEventHandler:
    def __init__(
        self,
        store: InMemoryStore,
        rate_limiter: RateLimiter,
        summarizer: URLSummarizer,
        slack_client: AsyncWebClient,
        bot_user_id: str,
    ):
        self.store = store
        self.rate_limiter = rate_limiter
        self.summarizer = summarizer
        self.slack_client = slack_client
        self.bot_user_id = bot_user_id

    async def handle_app_mention(self, event: dict, say) -> None:
        """Handle @Mammoth mentions in public channels."""
        user_id = event.get("user", "")
        text = event.get("text", "")
        channel = event.get("channel", "")
        ts = event.get("ts", "")

        # Strip bot mention from text
        text = re.sub(r"<@\w+>\s*", "", text).strip()
        if not text:
            await say(
                text="Tag me with a URL, idea, or kudos to submit it for ESG scouting!",
                thread_ts=ts,
            )
            return

        # Rate limit check
        allowed, denial_msg = await self.rate_limiter.can_submit(user_id)
        if not allowed:
            try:
                await self.slack_client.chat_postEphemeral(
                    channel=channel, user=user_id, text=denial_msg
                )
            except Exception:
                await say(text=denial_msg, thread_ts=ts)
            return

        # Detect type
        sub_type = detect_submission_type(text)
        url = extract_url(text) if sub_type == SubmissionType.URL else None

        # Fetch user display name
        try:
            user_info = await self.slack_client.users_info(user=user_id)
            display_name = (
                user_info["user"]["profile"].get("display_name")
                or user_info["user"]["profile"].get("real_name")
                or user_id
            )
        except Exception:
            display_name = user_id

        # Determine points
        points_map = {
            SubmissionType.URL: POINTS_URL,
            SubmissionType.IDEA: POINTS_IDEA,
            SubmissionType.KUDOS: POINTS_KUDOS,
        }
        base_points = points_map.get(sub_type, POINTS_IDEA)

        # Check weekly cap
        can_earn, actual_points = await self.rate_limiter.can_earn_submission_points(
            user_id, base_points
        )

        # Create and store submission
        submission = Submission(
            type=sub_type,
            text=text,
            url=url,
            submitter_slack_id=user_id,
            submitter_name=display_name,
            channel_id=channel,
            message_ts=ts,
            points_awarded=actual_points if can_earn else 0,
        )
        await self.store.add_submission(submission)

        if can_earn and actual_points > 0:
            await self.store.award_points(user_id, actual_points)

        # Reply with confirmation
        type_labels = {
            SubmissionType.URL: "article",
            SubmissionType.IDEA: "idea",
            SubmissionType.KUDOS: "kudos",
        }
        type_label = type_labels.get(sub_type, "submission")
        points_msg = f" (+{actual_points} pts)" if actual_points > 0 else ""

        await say(
            text=f"Logged your {type_label} submission!{points_msg} Peers can react to validate it.",
            thread_ts=ts,
        )

        # If URL, summarize in background and post
        if sub_type == SubmissionType.URL and url:
            summary = await self.summarizer.summarize(url)
            await self.store.update_submission(submission.id, summary=summary)

            summary_text = "\n".join(f"• {bullet}" for bullet in summary)
            await say(
                text=f":robot_face: *AI Summary:*\n{summary_text}",
                thread_ts=ts,
            )

    async def handle_direct_message(self, event: dict, say) -> None:
        """Handle anonymous DMs to the bot."""
        # Ignore bot's own messages
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return
        if event.get("user") == self.bot_user_id:
            return

        user_id = event.get("user", "")
        text = event.get("text", "")
        channel = event.get("channel", "")

        if not text.strip():
            return

        # Rate limit check
        allowed, denial_msg = await self.rate_limiter.can_submit(user_id)
        if not allowed:
            await say(text=denial_msg)
            return

        # Strip PII from the report text
        anonymized_text = strip_pii(text)

        # Check weekly point cap
        can_earn, actual_points = await self.rate_limiter.can_earn_submission_points(
            user_id, POINTS_ANONYMOUS
        )

        # Record rate-limit entry under real user BEFORE creating the anonymous submission
        # This ensures the real user's daily count is tracked properly
        from datetime import datetime, timezone
        self.store._user_submission_times[user_id].append(datetime.now(timezone.utc))

        # Store as anonymous — real user_id NOT stored in submission
        submission = Submission(
            type=SubmissionType.ANONYMOUS_REPORT,
            text=anonymized_text,
            submitter_slack_id="anonymous",
            submitter_name="Anonymous Employee",
            channel_id=channel,
            message_ts=event.get("ts", ""),
            is_anonymous=True,
            points_awarded=actual_points if can_earn else 0,
        )
        # add_submission without recording rate-limit again for "anonymous"
        async with self.store._lock:
            self.store._submissions[submission.id] = submission
            key = self.store._ts_key(submission.channel_id, submission.message_ts)
            self.store._ts_index[key] = submission.id

        # Award points to real user (tracked internally but never exposed)
        if can_earn and actual_points > 0:
            await self.store.award_points(user_id, actual_points)

        points_line = f"You earned {actual_points} points. " if actual_points > 0 else ""
        await say(
            text=(
                "Your anonymous report has been submitted securely. "
                f"{points_line}"
                "Your identity is *not* attached to this report."
            )
        )

    async def handle_reaction_added(self, event: dict) -> None:
        """Handle emoji reactions on submission messages."""
        emoji = event.get("reaction", "")
        reacting_user = event.get("user", "")
        item = event.get("item", {})
        channel = item.get("channel", "")
        message_ts = item.get("ts", "")
        item_user = event.get("item_user", "")

        # Don't count self-reactions
        if reacting_user == item_user:
            return

        # Look up the submission
        submission, newly_validated = await self.store.add_reaction(
            channel, message_ts, emoji, reacting_user
        )
        if not submission:
            return

        # Award reaction points to the reactor (2 pts, 5/day cap)
        can_earn = await self.rate_limiter.can_earn_reaction_points(reacting_user)
        if can_earn:
            can_weekly, _ = await self.rate_limiter.can_earn_submission_points(
                reacting_user, POINTS_REACTION
            )
            if can_weekly:
                await self.store.award_points(reacting_user, POINTS_REACTION)
                await self.store.record_reaction_earning(reacting_user)

        # If just crossed the validation threshold
        if newly_validated:
            # Award bonus points to original submitter
            original_user = submission.submitter_slack_id
            if original_user != "anonymous":
                can_earn_bonus, bonus = (
                    await self.rate_limiter.can_earn_submission_points(
                        original_user, POINTS_VALIDATION_BONUS
                    )
                )
                if can_earn_bonus and bonus > 0:
                    await self.store.award_points(original_user, bonus)
                    await self.store.update_submission(
                        submission.id,
                        points_awarded=submission.points_awarded + bonus,
                    )

            # Post validation message in thread
            try:
                await self.slack_client.chat_postMessage(
                    channel=channel,
                    thread_ts=message_ts,
                    text=(
                        f":star: This submission reached {submission.reaction_count} reactions "
                        f"and is now *High Value*! "
                        f"+{POINTS_VALIDATION_BONUS} bonus points to {submission.submitter_name}."
                    ),
                )
            except Exception as e:
                print(f"[SlackHandler] Failed to post validation message: {e}")

    async def send_weekly_digest(self, manager_user_id: str) -> None:
        """Send the top 3 submissions as a Block Kit digest to the manager."""
        all_subs = await self.store.list_submissions()
        # Sort by reaction count descending, take top 3
        top_subs = sorted(all_subs, key=lambda s: s.reaction_count, reverse=True)[:3]

        if not top_subs:
            await self.slack_client.chat_postMessage(
                channel=manager_user_id,
                text="No submissions this week yet. Encourage your team to scout!",
            )
            return

        stats = await self.store.get_stats()

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Weekly ESG Scouting Digest",
                    "emoji": True,
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f":bar_chart: {stats.total_submissions} total submissions | :star: {stats.validated_count} validated | :trophy: {stats.total_points_awarded} points awarded",
                    }
                ],
            },
            {"type": "divider"},
        ]

        medal_emojis = [":first_place_medal:", ":second_place_medal:", ":third_place_medal:"]
        type_emojis = {
            SubmissionType.URL: ":link:",
            SubmissionType.IDEA: ":bulb:",
            SubmissionType.KUDOS: ":raised_hands:",
            SubmissionType.ANONYMOUS_REPORT: ":shield:",
        }

        for i, sub in enumerate(top_subs):
            medal = medal_emojis[i] if i < len(medal_emojis) else ""
            type_emoji = type_emojis.get(sub.type, "")
            text_preview = sub.text[:150] + ("..." if len(sub.text) > 150 else "")
            url_line = f"\n<{sub.url}>" if sub.url else ""

            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"{medal} {type_emoji} *{sub.type.value}*\n"
                            f"{text_preview}{url_line}\n"
                            f"_{sub.submitter_name}_ · {sub.reaction_count} reactions"
                        ),
                    },
                }
            )

        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Open Dashboard",
                            "emoji": True,
                        },
                        "url": "http://localhost:8000",
                        "action_id": "open_dashboard",
                    }
                ],
            }
        )

        await self.slack_client.chat_postMessage(
            channel=manager_user_id,
            blocks=blocks,
            text="Weekly ESG Scouting Digest - Top 3 Submissions",
        )

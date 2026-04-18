from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from models import (
    Campaign,
    Submission,
    SubmissionStatus,
    SubmissionType,
    StatsResponse,
)

VALIDATION_THRESHOLD = 3


class InMemoryStore:
    def __init__(self):
        self._submissions: Dict[str, Submission] = {}
        self._campaigns: Dict[str, Campaign] = {}
        # Composite index: "{channel_id}:{message_ts}" -> submission_id
        self._ts_index: Dict[str, str] = {}
        # Rate limiting tracking
        self._user_submission_times: Dict[str, List[datetime]] = defaultdict(list)
        self._user_weekly_points: Dict[str, Dict[int, int]] = defaultdict(
            lambda: defaultdict(int)
        )  # user_id -> {iso_week -> points}
        self._user_daily_reactions: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )  # user_id -> {date_str -> count}
        self._lock = asyncio.Lock()

    def _ts_key(self, channel_id: str, message_ts: str) -> str:
        return f"{channel_id}:{message_ts}"

    async def add_submission(self, submission: Submission) -> Submission:
        async with self._lock:
            self._submissions[submission.id] = submission
            self._ts_index[
                self._ts_key(submission.channel_id, submission.message_ts)
            ] = submission.id
            self._user_submission_times[submission.submitter_slack_id].append(
                submission.created_at
            )
            return submission

    async def get_submission(self, submission_id: str) -> Optional[Submission]:
        return self._submissions.get(submission_id)

    async def get_submission_by_ts(
        self, channel_id: str, message_ts: str
    ) -> Optional[Submission]:
        key = self._ts_key(channel_id, message_ts)
        sub_id = self._ts_index.get(key)
        if sub_id:
            return self._submissions.get(sub_id)
        return None

    async def list_submissions(
        self,
        type_filter: Optional[SubmissionType] = None,
        status_filter: Optional[SubmissionStatus] = None,
        is_anonymous: Optional[bool] = None,
        is_high_value: Optional[bool] = None,
    ) -> List[Submission]:
        results = list(self._submissions.values())
        if type_filter is not None:
            results = [s for s in results if s.type == type_filter]
        if status_filter is not None:
            results = [s for s in results if s.status == status_filter]
        if is_anonymous is not None:
            results = [s for s in results if s.is_anonymous == is_anonymous]
        if is_high_value is not None:
            results = [s for s in results if s.is_high_value == is_high_value]
        results.sort(key=lambda s: s.created_at, reverse=True)
        return results

    async def update_submission(self, submission_id: str, **kwargs) -> Optional[Submission]:
        async with self._lock:
            sub = self._submissions.get(submission_id)
            if not sub:
                return None
            for key, value in kwargs.items():
                if hasattr(sub, key):
                    setattr(sub, key, value)
            return sub

    async def add_reaction(
        self, channel_id: str, message_ts: str, emoji: str, user_id: str
    ) -> Tuple[Optional[Submission], bool]:
        """Returns (updated_submission, newly_validated).
        newly_validated is True if this reaction pushed it past the threshold."""
        async with self._lock:
            key = self._ts_key(channel_id, message_ts)
            sub_id = self._ts_index.get(key)
            if not sub_id:
                return None, False

            sub = self._submissions.get(sub_id)
            if not sub:
                return None, False

            # One reaction per user (prevents gaming)
            if user_id in sub.reactions:
                return sub, False

            sub.reactions[user_id] = emoji
            old_count = sub.reaction_count
            sub.reaction_count = len(sub.reactions)

            newly_validated = (
                old_count < VALIDATION_THRESHOLD
                and sub.reaction_count >= VALIDATION_THRESHOLD
            )
            if newly_validated:
                sub.is_high_value = True
                sub.status = SubmissionStatus.VALIDATED

            return sub, newly_validated

    async def add_campaign(self, campaign: Campaign) -> Campaign:
        async with self._lock:
            self._campaigns[campaign.id] = campaign
            return campaign

    async def list_campaigns(self) -> List[Campaign]:
        results = list(self._campaigns.values())
        results.sort(key=lambda c: c.created_at, reverse=True)
        return results

    async def get_stats(self) -> StatsResponse:
        subs = list(self._submissions.values())
        total_points = sum(s.points_awarded for s in subs)

        # Submissions by type
        by_type: Dict[str, int] = defaultdict(int)
        for s in subs:
            by_type[s.type.value] += 1

        # Top contributors (non-anonymous)
        contributor_points: Dict[str, Dict] = {}
        for s in subs:
            if not s.is_anonymous and s.submitter_slack_id != "anonymous":
                if s.submitter_slack_id not in contributor_points:
                    contributor_points[s.submitter_slack_id] = {
                        "name": s.submitter_name,
                        "points": 0,
                        "submissions": 0,
                    }
                contributor_points[s.submitter_slack_id]["points"] += s.points_awarded
                contributor_points[s.submitter_slack_id]["submissions"] += 1

        top = sorted(
            contributor_points.values(), key=lambda x: x["points"], reverse=True
        )[:5]

        return StatsResponse(
            total_submissions=len(subs),
            validated_count=sum(1 for s in subs if s.is_high_value),
            anonymous_count=sum(1 for s in subs if s.is_anonymous),
            total_points_awarded=total_points,
            campaigns_created=len(self._campaigns),
            submissions_by_type=dict(by_type),
            top_contributors=top,
        )

    # --- Rate limit helpers ---

    async def check_submission_rate(self, user_id: str) -> bool:
        """Returns True if user is within the 3/24hr limit."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)
        times = self._user_submission_times.get(user_id, [])
        recent = [t for t in times if t > cutoff]
        self._user_submission_times[user_id] = recent  # clean up old entries
        return len(recent) < 3

    async def check_weekly_points(self, user_id: str, proposed: int) -> bool:
        """Returns True if awarding `proposed` points stays under 50/week cap."""
        now = datetime.now(timezone.utc)
        iso_week = now.isocalendar()[1]
        current = self._user_weekly_points[user_id][iso_week]
        return (current + proposed) <= 50

    async def award_points(self, user_id: str, points: int) -> int:
        """Award points and track weekly total. Returns new weekly total."""
        now = datetime.now(timezone.utc)
        iso_week = now.isocalendar()[1]
        self._user_weekly_points[user_id][iso_week] += points
        return self._user_weekly_points[user_id][iso_week]

    async def check_daily_reaction_earnings(self, user_id: str) -> bool:
        """Returns True if user is within the 5 reaction-earnings/day limit."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._user_daily_reactions[user_id][today] < 5

    async def record_reaction_earning(self, user_id: str) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._user_daily_reactions[user_id][today] += 1

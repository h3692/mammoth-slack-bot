from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from models import (
    Campaign,
    CampaignCreate,
    DigestRequest,
    StatusUpdate,
    SubmissionStatus,
    SubmissionType,
)
from rate_limiter import RateLimiter
from slack_handler import SlackEventHandler
from store import InMemoryStore
from summarizer import URLSummarizer

# Load environment variables
load_dotenv()

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN", "")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MANAGER_SLACK_USER_ID = os.environ.get("MANAGER_SLACK_USER_ID", "")

# --- Initialize core modules ---
store = InMemoryStore()
rate_limiter = RateLimiter(store)
summarizer = URLSummarizer(ANTHROPIC_API_KEY)

# --- Slack Bolt App (Socket Mode) ---
bolt_app = AsyncApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)

# We'll set the handler after we know the bot_user_id
handler: SlackEventHandler | None = None


async def init_handler():
    """Initialize the SlackEventHandler with the bot's user ID."""
    global handler
    try:
        auth = await bolt_app.client.auth_test()
        bot_user_id = auth["user_id"]
    except Exception:
        bot_user_id = "unknown"

    handler = SlackEventHandler(
        store=store,
        rate_limiter=rate_limiter,
        summarizer=summarizer,
        slack_client=bolt_app.client,
        bot_user_id=bot_user_id,
    )


# --- Register Slack Bolt event listeners ---
@bolt_app.event("app_mention")
async def on_app_mention(event, say):
    if handler:
        await handler.handle_app_mention(event, say)


@bolt_app.event("message")
async def on_message(event, say):
    if handler and event.get("channel_type") == "im":
        await handler.handle_direct_message(event, say)


@bolt_app.event("reaction_added")
async def on_reaction_added(event):
    if handler:
        await handler.handle_reaction_added(event)


# --- FastAPI App ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start Socket Mode handler as a background task on startup."""
    await init_handler()
    socket_handler = AsyncSocketModeHandler(bolt_app, SLACK_APP_TOKEN)
    task = asyncio.create_task(socket_handler.start_async())
    print("Socket Mode handler started — Mammoth bot is live!")
    yield
    task.cancel()


api = FastAPI(title="Mammoth ESG Scouting API", lifespan=lifespan)

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- API Routes ---
@api.get("/api/submissions")
async def list_submissions(
    type: SubmissionType | None = None,
    status: SubmissionStatus | None = None,
    is_anonymous: bool | None = None,
    is_high_value: bool | None = None,
):
    subs = await store.list_submissions(
        type_filter=type,
        status_filter=status,
        is_anonymous=is_anonymous,
        is_high_value=is_high_value,
    )
    return [s.model_dump(mode="json") for s in subs]


@api.patch("/api/submissions/{submission_id}/status")
async def update_status(submission_id: str, body: StatusUpdate):
    sub = await store.update_submission(submission_id, status=body.status)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    return sub.model_dump(mode="json")


@api.post("/api/submissions/{submission_id}/save-to-campaign")
async def save_to_campaign(submission_id: str, body: CampaignCreate | None = None):
    sub = await store.get_submission(submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    title = (body.title if body and body.title else sub.text[:80])
    description = (body.description if body and body.description else sub.text)

    campaign = Campaign(
        submission_id=submission_id,
        title=title,
        description=description,
        source_url=sub.url,
        source_type=sub.type,
    )
    await store.add_campaign(campaign)
    await store.update_submission(
        submission_id, status=SubmissionStatus.SAVED_TO_CAMPAIGN
    )
    return campaign.model_dump(mode="json")


@api.get("/api/campaigns")
async def list_campaigns():
    campaigns = await store.list_campaigns()
    return [c.model_dump(mode="json") for c in campaigns]


@api.get("/api/stats")
async def get_stats():
    stats = await store.get_stats()
    return stats.model_dump(mode="json")


@api.post("/api/digest")
async def trigger_digest(body: DigestRequest | None = None):
    target = (body.manager_user_id if body and body.manager_user_id else MANAGER_SLACK_USER_ID)
    if not target:
        return {"error": "No manager user ID configured"}
    if handler:
        await handler.send_weekly_digest(target)
    return {"status": "sent", "recipient": target}


# --- Serve frontend ---
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

@api.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# Mount static files for any additional assets
if os.path.isdir(FRONTEND_DIR):
    api.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

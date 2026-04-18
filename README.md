# Mammoth — Bottom-Up ESG Scouting Module

A demo MVP that flips Mammoth Climate's top-down ESG campaign model. Instead of managers creating campaigns from scratch, **employees proactively submit** ESG ideas, articles, and reports via Slack. Peers validate with emoji reactions, and managers triage the best content into campaigns from a branded web dashboard.

## Architecture

```
Employee (Slack)              Backend (FastAPI)            Dashboard (Browser)
     |                              |                            |
     |--@Mammoth + URL------------->|                            |
     |                              |--Claude API summary        |
     |<--thread reply (AI summary)--|                            |
     |                              |--store submission--------->|
     |                              |                            |
     |--emoji reaction------------->|                            |
     |                              |--count reactions           |
     |                              |--if 3+: validate---------->|
     |                              |                            |
     |--DM (anonymous)------------->|                            |
     |                              |--strip PII, store--------->|
     |<--confirmation---------------|                            |
     |                              |                            |
     |                              |<--GET /api/submissions-----|
     |                              |---JSON response----------->|
     |                              |                   (polls every 4s)
```

## Features

### Slack Bot (@Mammoth)
- **Public channel mentions**: Tag `@Mammoth` with a URL or idea — bot logs it and generates a 3-bullet AI summary
- **Emoji validation**: When a submission gets 3+ reactions from different users, it's marked "High Value" with bonus points
- **Anonymous DMs**: Message the bot directly for anonymous facility/issue reports — PII is stripped automatically
- **Rate limiting**: 3 submissions/day, 50 points/week, 5 reaction-earnings/day

### Manager Dashboard
- **Triage inbox**: All submissions with real-time polling (4-second refresh)
- **Filtering**: All, High Engagement, Anonymous Reports, URLs, Kudos
- **One-click actions**: Save to Campaign Builder, Approve, Dismiss
- **Weekly digest**: Block Kit message sent to manager's Slack DM with top 3 submissions
- **Live stats**: Total submissions, validated count, anonymous reports, points awarded

## Quick Start

### 1. Create the Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**
2. Name it **Mammoth**, select your workspace

3. **Basic Information** → scroll to **App-Level Tokens** → **Generate Token**
   - Token Name: `socket-mode`
   - Scope: `connections:write`
   - Click **Generate** → copy the `xapp-...` token

4. **Socket Mode** (left sidebar) → **Toggle ON**

5. **OAuth & Permissions** → **Bot Token Scopes** — add:
   - `app_mentions:read`
   - `chat:write`
   - `im:read`
   - `im:write`
   - `im:history`
   - `reactions:read`
   - `users:read`

6. **Event Subscriptions** → **Toggle ON** (no Request URL needed with Socket Mode)
   - Under **Subscribe to bot events**, add:
     - `app_mention`
     - `message.im`
     - `reaction_added`
   - Click **Save Changes**

7. **App Home** (left sidebar):
   - Toggle ON: **Allow users to send Slash commands and messages from the messages tab**

8. **Install App** (left sidebar) → **Install to Workspace** → **Allow**
   - Copy the **Bot User OAuth Token** (`xoxb-...`)

9. Back in **Basic Information** → copy the **Signing Secret**

### 2. Set Up Environment

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

Create `backend/.env` from the example:

```bash
cp .env.example .env
```

Fill in your tokens:

```env
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_SIGNING_SECRET=your-signing-secret
ANTHROPIC_API_KEY=sk-ant-your-key
MANAGER_SLACK_USER_ID=U0XXXXXXX
```

> **Finding your Manager Slack User ID**: In Slack, click on your profile → three dots menu → "Copy member ID"

### 3. Run the Server

```bash
cd backend
uvicorn main:api --reload --port 8000
```

You should see:
```
Socket Mode handler started — Mammoth bot is live!
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 4. Invite the Bot to a Channel

In Slack, go to any channel and type:
```
/invite @Mammoth
```

### 5. Open the Dashboard

Visit [http://localhost:8000](http://localhost:8000)

## Demo Walkthrough (Interview Script)

1. **Show the empty dashboard** — clean slate, explain the concept
2. **In Slack, tag the bot with an article**: `@Mammoth Check out this sustainability report https://example.com/esg-report`
3. **Watch the bot reply** — confirmation message + AI-generated 3-bullet summary in thread
4. **Switch to dashboard** — see the submission appear in real-time (within 4 seconds)
5. **Have 2-3 colleagues react** with emoji on the Slack message
6. **Watch "High Value"** badge appear on the dashboard when threshold is hit
7. **DM the bot anonymously**: "The lights on the 3rd floor are left on every weekend"
8. **Show the anonymous report** in the dashboard — no identity attached
9. **Click "Save to Campaign"** on the validated submission — it moves to Campaigns sidebar
10. **Click "Send Weekly Digest"** — show the Block Kit message arrive in your Slack DMs
11. **Demonstrate rate limiting**: Submit 3 ideas rapidly, show the "save it for tomorrow" message on the 4th

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, Slack Bolt |
| Slack | Socket Mode (WebSocket, no public URL needed) |
| AI | Claude API (Haiku) for URL summarization |
| Frontend | Single HTML file, Tailwind CSS CDN |
| Data | In-memory store (no database) |
| Real-time | Dashboard polls every 4 seconds |

## Points System

| Action | Points |
|--------|--------|
| Submit a URL | 10 |
| Submit an idea | 5 |
| Submit kudos | 15 |
| Submit anonymous report | 20 |
| Submission validated (3+ reactions) | +25 bonus |
| React to someone's submission | 2 |

### Anti-Spam Caps

| Limit | Threshold |
|-------|-----------|
| Submissions per day | 3 per 24hr rolling window |
| Points per week | 50 max |
| Reaction earnings per day | 5 max |
# mammoth-slack-bot

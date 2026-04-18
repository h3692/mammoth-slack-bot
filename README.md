# Mammoth — Bottom-Up ESG Scouting Module

***Mammoth Climate Proactive Slack Bot***

**What is this? - Project Description**
This project is a demo of a potential extention onto Mammoth Climate's existing suite of Slack/Team native employee ESG management tools to transform it into a more reactive entity as opposed to a static channel updater. This project has 2 components, the first is the Slack functionality add on which allows user to ping the Mammoth bot with things like employee kudos, cool ESG articles that are relevant as well as top community initatiatives the company can participate in. The user can log these by messaging the Mammoth bot in a channel server or they can anonymously notify the bot by sending a direct message as well. Initatives that gain traction will be rewarded points and employee-driven engagement tool usage will also be logged within Mammoth's ESG profiling capacities. This connects to the second part of the demo which is a dashboard that showcases all employee driven ESG initatives. If there are any cool articles, learnings or events, an ESG leader in the company can also flag them to use in future campaigns.

**Why was this built? - Core Consumer Pain Point**
Mammoth is already a strong player in the ESG management market, however they largely rely on static tools like pushing videos, lessons and events into the chat and allowing employees to engage with them. This ignores another side of ESG management entirely which comes in terms of onus on the part of the employee. Employees who play a more active role in supporting company ESG initatives will be ones who can contribute more actively beyond just engaging with the resources that the existing Mammoth bot is pushing. Hence, there is a unique opportunity here to integrate tools that promote employee engagement from a completely new dimension by allowing users to type to the bot and communicate with it directly.

**What is the solution? - @Mention Form Factor**
The Mammoth bot extention enables users to integrate their own findings in a seamless way with their existing workflow on Slack. It encourages them to be more proactive in their ESG initaitives instead of being responsive towards content that is pushed directly to them. However, it does not inhibit on the primary function of the employee (which is to do work) by limiting the capacity to which they can send messages and log points to the Mammoth bot in order to preserve the core intention of this feature as a fun engagement tool as opposed to an exploit that detracts employees from the tasks and deliverables that they need to complete

**How does it work? - Key Demo Functionalities**

see architecture

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

# 🧠 Google Keep Intelligence Agent — Phase 1

**Personal AI OS | Epic 1 | Keep + Priority Summariser**

An AI agent that transforms chaotic Google Keep notes into a prioritised, actionable intelligence brief delivered to your phone via Telegram.

## Architecture

```
Google Keep JSON (Takeout export)
        ↓
  GitHub Repository
        ↓
  GitHub Actions (manual trigger)
        ↓
  Python Agent (agent.py)
        ↓
  ┌─────────────────────┐
  │  LLM Classification  │  ← OpenAI (reasoning)
  │  (llm_extractor.py)  │
  └─────────┬───────────┘
            ↓
  ┌─────────────────────┐
  │  Priority Scoring    │  ← Python (control)
  │  (scoring.py)        │
  └─────────┬───────────┘
            ↓
  📱 Telegram Notification
```

**Key Principle:** LLM does reasoning. Python does control. Never let LLM control priority fully.

## Repo Structure

```
keep_agent/
├── agent.py              # Main orchestrator
├── llm_extractor.py      # OpenAI structured extraction
├── scoring.py            # Deterministic priority scoring
├── telegram_notify.py    # Telegram Bot API integration
├── requirements.txt      # Python dependencies
├── keep_data/            # Your Keep export goes here
│   └── keep_data.json    # (sample data included)
├── output/               # Generated analysis JSON
└── .github/
    └── workflows/
        └── run.yml       # GitHub Actions workflow
```

## Setup

### 1. Export Google Keep Data

1. Go to [Google Takeout](https://takeout.google.com/)
2. Select **only** Google Keep
3. Export as JSON
4. Place the `.json` file(s) in `keep_data/`

### 2. Create Telegram Bot

1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Send `/newbot` and follow prompts → save the **bot token**
3. Message your new bot (send anything)
4. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. Find your **chat_id** in the response

### 3. Set GitHub Secrets

In your GitHub repo → Settings → Secrets → Actions:

| Secret | Value |
|--------|-------|
| `OPENAI_API_KEY` | Your OpenAI API key |
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Your chat ID |

### 4. Run

**GitHub Actions (recommended):**
- Go to Actions tab → "Keep Intelligence Agent" → Run workflow

**Local:**
```bash
export OPENAI_API_KEY="sk-..."
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_CHAT_ID="your_chat_id"

cd keep_agent
pip install -r requirements.txt
python agent.py
```

## Output Example

```
🧠 KEEP INTELLIGENCE BRIEF
Wednesday, 25 February 2026

🎯 TOP PRIORITIES
  1. File self-assessment tax return  [finance]  ⚡72
  2. Book dentist appointment  [health]  ⚡55
  3. Cancel old gym membership & start new routine  [health]  ⚡48
  4. Update CV with API project  [career]  ⚡40
  5. Set up budget spreadsheet  [finance]  ⚡38

⚠️ NEGLECTED DOMAINS
  • 🚨 RELATIONSHIPS: Only 1 task(s) — below threshold
  • ⚠️ LEARNING: Only 1 task(s) — below threshold

📊 SCAN SUMMARY
  Notes scanned: 12
  Tasks extracted: 8
  Vague notes: 2
  Duplicate groups: 1
```

## Scoring Formula

```
Priority Score = Urgency + Impact + Staleness
```

| Factor | How it works | Max |
|--------|-------------|-----|
| **Urgency** | Keywords (ASAP, deadline, today) + detected deadlines | 80 |
| **Impact** | Domain weight (health=25, finance=22, career=20...) | 25 |
| **Staleness** | Days since note was last edited | 20 |

All weights are tunable in `scoring.py`.

## Validation Metrics

This agent is useful if:
- ✅ You act on at least 1 surfaced task daily
- ✅ It reduces note clutter over 2 weeks
- ✅ It surfaces neglected domains accurately

If not → iterate prompt + scoring weights.

## Roadmap

- **Phase 1** ← You are here: Manual export → classification → scoring → Telegram
- **Phase 2**: Scheduled daily cron, rolling state memory, trend detection
- **Phase 3**: Cross-app priority reconciliation (Notion, Todoist, Calendar)
- **Phase 4**: Website continuous audit agent
- **Phase 5**: Executive Life OS — weekly AI Chief of Staff briefing

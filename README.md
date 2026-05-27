# Lodsuite Control Plane

AI-powered UGC Ad Pipeline for generating German B2B industrial video ads in POV-selfie style.

## Overview

The Control Plane is the central orchestration component of the Lodsuite pipeline. It runs 24/7 on a VPS and handles:

- Telegram Bot for user interaction
- Job queue and state management
- Script generation (via Claude API)
- Coordination with GPU render workers

## Architecture

```
┌─────────────────────────────────────────────┐
│  CONTROL PLANE (VPS, 24/7)                  │
│  - FastAPI + Telegram Bot + SQLite          │
│  - Claude API für Skript-Generation         │
│  - Job-Queue + State Machine                │
└──────────────┬──────────────────────────────┘
               │ HTTPS (Bearer Token Auth)
               ▼
┌─────────────────────────────────────────────┐
│  RENDER PLANE (GPU, on-demand) - Phase 2    │
│  - ComfyUI + Wan 2.2 + Flux + F5-TTS        │
└─────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- FFmpeg (for mock rendering)

### Setup

1. Clone the repository and create environment:

```bash
cd lodsuite-control
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configure environment:

```bash
cp .env.example .env
# Edit .env with your credentials
```

3. Run with Docker Compose:

```bash
docker-compose up -d
```

Or run locally:

```bash
# Terminal 1: Start API
uvicorn app.main:app --reload

# Terminal 2: Start Bot
python -m app.bot.main
```

## Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token | Yes |
| `TELEGRAM_ADMIN_USER_IDS` | Comma-separated user IDs | No |
| `ANTHROPIC_API_KEY` | Claude API key | For production |
| `DATABASE_URL` | SQLite connection string | No (default provided) |
| `MOCK_RENDER` | Enable mock rendering | No (default: true) |
| `MOCK_SCRIPT` | Enable mock script generation | No (default: true) |

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and help |
| `/new` | Start new job (mode selection) |
| `/new structured` | Start structured mode directly |
| `/new file` | Upload YAML script |
| `/jobs` | List your jobs |
| `/status <id>` | Get job status |
| `/cancel <id>` | Cancel a job |

## API Endpoints

### Public Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/api/v1/jobs` | Create job |
| GET | `/api/v1/jobs` | List jobs |
| GET | `/api/v1/jobs/{id}` | Get job details |
| POST | `/api/v1/jobs/{id}/script/approve` | Approve script |
| POST | `/api/v1/jobs/{id}/final/approve` | Approve final video |
| GET | `/api/v1/jobs/{id}/final.mp4` | Download video |

### Render Worker Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/render-queue/next` | Get next render task |
| POST | `/api/v1/jobs/{id}/scene/{n}/status` | Update scene status |
| POST | `/api/v1/jobs/{id}/scene/{n}/variant` | Upload variant |
| POST | `/api/v1/jobs/{id}/final` | Upload final video |

## Job Flow

1. **Brief Mode**: User provides briefing → AI generates script → Review → Render
2. **Structured Mode**: User builds script scene-by-scene → Review → Render
3. **File Mode**: User uploads YAML script → Review → Render

## State Machine

```
BRIEFING_RECEIVED → SCRIPT_GENERATING → SCRIPT_PENDING_REVIEW
                                              ↓
COMPLETED ← FINAL_PENDING_REVIEW ← ASSEMBLY_RUNNING ← ... ← SCRIPT_APPROVED
```

## Development

### Run Tests

```bash
pytest
```

### Code Quality

```bash
ruff check .
mypy app
```

### Database Migrations

```bash
alembic upgrade head
alembic revision --autogenerate -m "description"
```

## Project Structure

```
lodsuite-control/
├── app/
│   ├── api/           # FastAPI endpoints
│   ├── bot/           # Telegram bot
│   │   └── handlers/  # Command handlers
│   ├── db/            # Database models
│   ├── services/      # Business logic
│   └── schemas/       # Pydantic schemas
├── library/           # Asset library
│   └── prompts/       # Location/camera/action JSONs
├── characters/        # Character style guides
├── jobs/              # Job output directory
├── tests/             # Test files
└── systemd/           # Service files
```

## License

MIT

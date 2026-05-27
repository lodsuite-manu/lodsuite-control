# Architecture Decisions

This document records key architectural decisions made during development.

## ADR-001: Two-Plane Architecture

**Status:** Accepted

**Context:**
We need to run a Telegram bot 24/7 while minimizing GPU costs.

**Decision:**
Separate the system into Control Plane (VPS) and Render Plane (GPU):
- Control Plane runs continuously on cheap VPS (~5 CHF/month)
- Render Plane (GPU) runs only when needed

**Consequences:**
- Bot is always available
- GPU costs are usage-based
- Requires HTTP API between planes
- State must be persisted on Control Plane

---

## ADR-002: SQLite for Primary Database

**Status:** Accepted

**Context:**
Need a database for job state that works in single-node VPS setup.

**Decision:**
Use SQLite with aiosqlite for async support.

**Consequences:**
- No separate database server needed
- Simple backup (copy file)
- Limited concurrent writes (acceptable for our scale)
- Easy migration to PostgreSQL later if needed

---

## ADR-003: Telegram ConversationHandler for State

**Status:** Accepted

**Context:**
Need to manage multi-step user interactions in Telegram.

**Decision:**
Use python-telegram-bot's ConversationHandler for conversation flow.

**Consequences:**
- Clean state machine for user interactions
- State is in-memory (resets on restart)
- Works well for Phase 1
- May need Redis-backed state for Phase 2 (high availability)

---

## ADR-004: UUID Job IDs with Short-Prefix Support

**Status:** Accepted

**Context:**
Need unique job identifiers that are also user-friendly.

**Decision:**
Use full UUIDs internally, accept short prefixes (6+ chars) in user-facing commands.

**Consequences:**
- Globally unique IDs
- Users can reference jobs with short prefixes (e.g., `abc123`)
- Collision-resistant for prefix matching

---

## ADR-005: YAML for Script Format

**Status:** Accepted

**Context:**
Power users want to upload pre-made scripts.

**Decision:**
Use YAML for the script file format (Mode C).

**Consequences:**
- More human-readable than JSON
- Supports comments
- Easy to edit manually
- Standard parsing with PyYAML

---

## ADR-006: Mock Mode for Phase 1

**Status:** Accepted

**Context:**
Need to test the full flow without GPU infrastructure.

**Decision:**
Implement MOCK_RENDER and MOCK_SCRIPT flags:
- Mock script returns hardcoded 3-scene script
- Mock render creates black videos with FFmpeg

**Consequences:**
- Full end-to-end testing without GPU
- Clear separation of mock vs real implementations
- Easy to switch via environment variables

---

## ADR-007: Asset Library as JSON Files

**Status:** Accepted

**Context:**
Need to define locations, cameras, and actions for scripts.

**Decision:**
Store assets in JSON files in `library/prompts/` directory.

**Consequences:**
- Easy to edit and version control
- Loaded at startup
- No database needed for assets
- Fast lookups via in-memory dictionary

---

## ADR-008: FastAPI for API Layer

**Status:** Accepted

**Context:**
Need a REST API for bot-API and worker-API communication.

**Decision:**
Use FastAPI with Pydantic for validation.

**Consequences:**
- Automatic OpenAPI documentation
- Type-safe request/response handling
- Async support matches our async database
- Good integration with SQLAlchemy 2.0

---

## ADR-009: Structlog for Logging

**Status:** Accepted

**Context:**
Need structured logging for debugging and monitoring.

**Decision:**
Use structlog with JSON output in production.

**Consequences:**
- Context-aware logging
- Easy to parse in log aggregators
- Pretty console output in development
- Consistent logging across components

---

## ADR-010: Docker Compose for Deployment

**Status:** Accepted

**Context:**
Need reproducible deployment for Control Plane.

**Decision:**
Use Docker Compose with services: redis, api, bot, worker.

**Consequences:**
- Single-command deployment
- Consistent environments
- Easy to add/remove components
- Volume management for persistence

---

## Future Considerations

### Phase 2 Decisions Needed

1. **Render Worker Authentication**: Bearer token vs mTLS
2. **Queue Backend**: Keep RQ or switch to Celery/Dramatiq
3. **Still Image Library**: Pre-generate or on-demand
4. **Re-render Logic**: Scene-level vs full job re-render
5. **Webhook vs Polling**: For GPU → Control Plane communication

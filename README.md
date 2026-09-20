# GmailQuest

Natural-language statistics over the org's Gmail account — "who emails us most?", "what do
people ask about most?" — with exact answers for structured questions and an MCP server so
any future dev can point their own agent at it.

Not a developer, or just want the short version? See `GUIDE.md` instead — this file assumes
you're comfortable with a terminal.

See `PLAN.md` for the full design rationale (why not just a generic Gmail MCP connector).

The short version: raw email content never gets summed up by an LLM. Gmail is synced into a
local SQLite database; questions like "top senders" are answered with plain SQL (exact, free,
instant); fuzzier questions like "most common topics" are answered from a precomputed,
locally-embedded cluster index (approximate, but computed once, not per query). The LLM is
only used for two small, bounded things: routing a free-text question to the right tool, and
writing a short label for each topic cluster.

## Setup

### 1. Install dependencies

This project uses [uv](https://docs.astral.sh/uv/) and is pinned to Python 3.12 (see
`.python-version`) for ML library compatibility.

```powershell
uv sync
```

### 2. Enable the Gmail API and get OAuth credentials

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and create a new
   project (or reuse one).
2. Enable the **Gmail API** for that project (APIs & Services → Library → search "Gmail API").
3. Configure the **OAuth consent screen** (APIs & Services → OAuth consent screen):
   - User type: External is fine.
   - Add the org Gmail account as a test user (testing mode doesn't require Google review
     for a single account).
4. Create credentials (APIs & Services → Credentials → Create Credentials → OAuth client ID):
   - Application type: **Desktop app**.
5. Download the resulting JSON and save it as `data/credentials.json`.

### 3. Configure environment

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set:
- `GMAILQUEST_ORG_EMAIL` — the org's Gmail address (used to tell inbound from outbound mail).
- `ANTHROPIC_API_KEY` — only needed for the `ask` tool and cluster labeling; sync and the
  exact structured stats tools work without it.

### 4. First sync

```powershell
uv run gmailquest sync --full --start 2026-01-01
```

`--start`/`--end` (ISO dates, end exclusive — same convention as every stats function) scope
the backfill to a window so you're not pulling the entire mailbox history on the first run.
Drop them to sync everything, or use `--query` instead/as well for anything Gmail search
syntax can express (e.g. `--query "after:2026/01/01 from:*@devpost.com"`). Providing a window
or query implies `--full` automatically. The first run opens a browser for the one-time OAuth
consent; after that, the refresh token in `data/token.json` is reused automatically. Re-run
`uv run gmailquest sync` (no options) any time afterward for a cheap incremental update —
already-stored messages are skipped, so a scoped backfill is also cheap to re-run/resume.

### 5. Build the topic index (optional, needed for "most asked questions")

```powershell
uv run gmailquest cluster
```

This downloads a small local embedding model on first run (no API key needed) and re-clusters
whenever you want fresh topics (e.g. after every sync). Note this is separate from the sync
window: `sync --query` controls what gets *downloaded*, `cluster` re-clusters whatever is
already in the local database. Scope it to a period with `--start`/`--end`:

```powershell
uv run gmailquest cluster --start 2026-07-01 --end 2026-10-01
```

This replaces the whole topic index with one scoped to that window — it doesn't merge with
a previous run. Narrowing the window means fewer clusters and fewer LLM labeling calls, so
it's the cheap/fast option when you only care about a recent period.

## Using it

**Without any agent**, straight from the CLI:

```powershell
uv run gmailquest ask "who emails us the most this month?"
```

**As an MCP server**, so any MCP-capable agent can query it — add to Claude Desktop/Code as a
custom connector, command: `uv run gmailquest-mcp` (or `uv run python -m GmailQuest.mcp_server`),
working directory: this project. It exposes:

| Tool | What it answers |
|---|---|
| `top_senders(start, end, limit)` | Who sends us the most email |
| `top_recipients(start, end, limit)` | Who we email the most |
| `email_volume(start, end, granularity)` | Inbound/outbound volume over time |
| `avg_response_time(start, end)` | How fast we reply, on average |
| `top_question_topics(start, end, limit)` | What people ask about most (approximate) |
| `ask(question)` | Free-text convenience wrapper around all of the above |

Every tool except `ask` is exact and LLM-free — a future dev's agent can call them directly
without spending any tokens on the mailbox data itself.

## For future devs

- All the real logic lives in `stats.py` / `semantic.py`, independent of MCP. `mcp_server.py`
  is a thin wrapper — add a new statistic by writing a plain function in `stats.py` (or
  `semantic.py`), then exposing it with a `@mcp.tool()` wrapper the same way the existing
  ones are.
- To add it to the NL router too, add its schema + a dispatch entry in `nlrouter.py`.
- `data/gmailquest.sqlite` is the only state; delete it and re-run `sync --full` to rebuild
  from scratch.
- The MCP server currently runs over stdio (local-only). If the org wants a shared,
  always-on instance later, swap the transport in `mcp_server.py` (`mcp.run(transport=...)`)
  — the tool functions themselves don't change.

## Tests

```powershell
uv run pytest
```

`test_stats.py` asserts exact expected counts against a small hand-built fixture database —
that's what actually proves the structured-stats answers are precise, not just plausible.

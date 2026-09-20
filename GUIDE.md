# GmailQuest, Explained Simply

This is a small tool that reads through the org's Gmail inbox and answers questions about
it in plain English — things like:

- "Who sends us the most email?"
- "What do people usually ask us about?"
- "How fast do we usually reply?"

You don't need to scroll through hundreds of emails to find out — you just ask, and it
looks it up.

## How it works, in one paragraph

The tool copies the emails (just the text, not attachments) into a private file on one
computer. From then on, it counts things directly from that file — so answers like "who
emails us most" are exact counts, not a guess from a chatbot. For fuzzier questions like
"what do people ask about most," it groups similar questions together automatically and
gives each group a short label.

## Who needs to set it up?

One person who's comfortable following step-by-step instructions on a computer (doesn't
need to know how to code) does a one-time setup, described below. After that, anyone on
the team can just ask questions through a connected chat tool.

## One-time setup

You'll need access to the org's Gmail account and about 15 minutes.

### Step 1 — Get permission for the tool to read the inbox

Google requires every app to be individually approved before it's allowed to read an
inbox, even a private one only your org uses. This is a security thing, not something we
can skip.

1. Go to console.cloud.google.com and sign in with the **org's Gmail account**.
2. Click "New Project," give it any name (e.g. "Mailbox Insights"), and create it.
3. In the search bar at the top, search "Gmail API" and click **Enable**.
4. Go to "OAuth consent screen" (left menu). Choose **External**, fill in an app name and
   your email, and save. When it asks for "test users," add the org's own Gmail address.
5. Go to "Credentials" (left menu) → **Create Credentials** → **OAuth client ID** → choose
   **Desktop app** → Create.
6. A box pops up with a **Download JSON** button. Click it.
7. Rename the downloaded file to `credentials.json` and put it inside this project's
   `data` folder (create the folder if it isn't there yet).

### Step 2 — Tell the tool which inbox is "ours"

1. Find the file called `.env.example` in this folder. Make a copy of it and rename the
   copy to `.env`.
2. Open `.env` in any text editor (Notepad is fine).
3. After `GMAILQUEST_ORG_EMAIL=`, type the org's Gmail address, e.g.:
   `GMAILQUEST_ORG_EMAIL=team.hackconcordia@ecaconcordia.ca`

### Step 3 — Get a Claude API key (only needed for plain-English questions)

Skip this if you're fine only using the pre-built lookups (who emails us most, reply
speed, etc). It's required for asking free-form questions and for grouping similar
questions together.

1. Go to console.anthropic.com and sign in (or create an account).
2. Make sure you're inside a specific **Workspace**, not "no workspace" — check the
   switcher near the top-left if unsure.
3. Go to **API Keys** → **Create Key**, then copy it (starts with `sk-ant-`).
4. In `.env`, paste it after `ANTHROPIC_API_KEY=`.

**Treat this key like a password.** Anyone with it can run up charges under the org's
name. Never post it publicly or send it over chat/email — paste it only into `.env`,
which already stays out of the shared repo automatically.

### Step 4 — Install what the tool needs

Open a terminal in this project folder and run:

```
uv sync
```

(Only needs to be done once, or after an update. `uv` is a Python installer — if the
command isn't found, whoever set up your computer needs to install it first.)

### Step 5 — Copy the emails in

```
uv run gmailquest sync --full --start 2026-01-01
```

This is the step that actually reads the inbox. Change the date to however far back you
want to look (or leave it off entirely to copy the whole inbox history — slower, but
sometimes worth it). The first time you run it, a browser window pops up asking you to
log in and approve access — do that once, and it remembers you after. Once this has run,
you can just run `uv run gmailquest sync` (no options) any time to grab whatever's new.

### Step 6 — Group similar questions together (optional)

```
uv run gmailquest cluster
```

Only needed if you want "what do people ask about most" to work. Skip it if you only care
about "who emails us most" type questions.

## Using it day to day

Once it's set up, anyone can ask questions through whatever AI chat tool has been
connected to it — ask whoever did the setup which one that is (Claude Desktop, Claude
Code, or something else). You just type your question in plain English, like you would to
a person, and it answers from the real numbers, not a guess.

If no chat tool is connected yet, whoever did the setup can also just type questions
straight into a terminal:

```
uv run gmailquest ask "who emails us the most this month?"
```

## Keeping the numbers fresh

New email keeps arriving, so the inbox copy needs to be refreshed regularly. Run this
whenever you want up-to-date answers:

```
uv run gmailquest sync
```

(No need for `--full` after the first time — it only grabs what's new, and it's quick.)

## What you don't need to worry about

- You don't need to know how to code.
- You don't need to understand what's inside the `GmailQuest` folder — that's for
  whoever maintains this.
- Nothing you ask gets sent anywhere except Claude (for plain-English questions) and
  Google (to read the inbox) — no email content is stored or shared anywhere beyond that.

## Something broke, or you want the technical details

This guide skips the "why" behind how it's built. If you're technical, or you're handing
this off to a developer, see `README.md` and `PLAN.md` in this same folder for the full
picture.

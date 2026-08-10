# CLAUDE.md

## What this project is

DocTracker (branded **DOCKET** in the web UI, formerly **LAKAD**) — a Flask document
receiving/releasing tracker built for the DepEd Leyte Division. It tracks documents through
offices via QR-code scanning, routing slips, transfers, and a client-facing submission/tracking
portal. There is a companion Expo/React Native mobile app in `mobile/`.

## Stack and environment

- **Backend:** Python + Flask, app-factory pattern (`create_app` in [app.py](app.py)).
  Blueprints in [routes/](routes/) (`admin`, `auth`, `backup`, `client`, `dashboard`, `download`,
  `import_excel`, `offices`, `progress`, `scanning`, `so`), business logic in [services/](services/),
  a separate mobile/JWT API in [blueprints/api.py](blueprints/api.py).
- **Data:** PostgreSQL via `DATABASE_URL`, with a **JSON-file fallback** when `DATABASE_URL` is
  empty (`documents.json`, `users.json`, `routing_slips.json`, …). The test suite runs entirely on
  the JSON backend — `tests/conftest.py` forces `DATABASE_URL=""`.
- **Config:** all in [config.py](config.py), read from env vars. `.env` is loaded via python-dotenv
  if present. `.env` and all the `*.json` data files are gitignored.
- **Python version:** `.python-version` pins `3.13.3`, but the checked-in `.venv` actually runs
  **Python 3.14.3** (that's what pytest reports). Don't assume 3.13.
- **Mobile:** Expo / React Native / expo-router / NativeWind / TanStack Query, in `mobile/`.

## Branch

**The production branch is `DOCTRACKER_PROD`.** It is `origin/HEAD`. **It is not `main`.**

`origin/main` still exists but is **363 commits behind** `DOCTRACKER_PROD` and 0 ahead — it is
abandoned, not a parallel line of development. Do not branch from it, merge to it, or treat it as
the trunk.

Convention visible in the history: work happens on a topic branch, is sometimes staged on `testdoc`,
then lands on `DOCTRACKER_PROD` via a merge commit (e.g. `eede694 Promote Excel/JSON honesty fix …
from testdoc to production`).

## Commands

Run everything from the repo root, using the checked-in venv (`.venv/Scripts/python.exe` on Windows).

**Tests — the only real check this repo has:**

```
.venv/Scripts/python.exe -m pytest
```

> **Run this and quote the real output. Do not report a remembered number, and do not claim the
> check is unavailable.**

**Baseline as of 2026-07-20 (Python 3.14.3, pytest 9.0.3). It differs between a dev machine and
the server — check which one you are on before comparing.**

On a dev machine (no mail credentials in `.env`):

```
14 failed, 328 passed, 1 skipped, 9 warnings in 51.99s
```

On the server (real `GMAIL_APP_PASSWORD` + `MAIL_SENDER` in `.env`): **16 failed** — the same 14,
plus 2 in `tests/test_email_service.py` that only fail when mail is actually enabled.

All failures are **pre-existing and are stale tests, not live product bugs** — see
[BACKLOG.md](BACKLOG.md) "Known bounds". They are 9 in `tests/test_client_routes.py`, 5 in
`tests/test_scanning_routes.py::TestOfficeAction`, and (server only) 2 in
`tests/test_email_service.py`. **A green run is not the bar; matching this baseline is.** If you see
a different count, something changed — investigate before proceeding.

**Typecheck / lint (backend):** there is **none**. No ruff, mypy, flake8, black, or pylint is
installed in `.venv` and no config for any exists. Don't invent a command; say there isn't one.

**Typecheck (mobile):** no npm script exists, but the binary does:

```
cd mobile && ./node_modules/.bin/tsc --noEmit
```

**Baseline: 8 errors** (see BACKLOG.md — one of them, `setAcceptTarget`, is a genuine live bug).
Note `tsc` exits **0** here despite printing errors, so check the output, not the exit code.

**Run locally:** `python app.py` (serves on :5000), or `START_SERVER.bat` on Windows.

**Production:** `gunicorn app:app --workers 4 --threads 2 --timeout 120` (see `Procfile`).

**Deploy:** deploys are triggered by a **GitHub webhook consumed by NEXUS Panel**, a separate Flask
deployment tool that is **not part of this repo** and has no config here — which is why grepping this
repo for the deploy path finds nothing. Production runs **gunicorn under systemd (unit
`app-doctracker`)**, fronted by a **Cloudflare tunnel**. It does **not** run `python app.py`.

**There is no GitHub Actions workflow in this repo, and there is no CI.** Nothing runs pytest, tsc,
or any lint on push or PR — every check in this file is one you must run locally and read yourself.

**Do not add a workflow that pushes to a branch in order to deploy.** That is not how this system
works, and a previous attempt at it (`.github/workflows/deploy.yml`, deleted 2026-07-14) was actively
dangerous — see the Closed section of [BACKLOG.md](BACKLOG.md).

## Invariants

Things that look wrong or removable but must not be touched without understanding why.

- **The literal string `"LAKAD"` in backup metadata is load-bearing.** Backups are written with
  `"app": "LAKAD - DepEd Leyte Division"` ([services/backup.py:441](services/backup.py:441),
  [:530](services/backup.py:530)), and restore's content-validation guard checks
  `meta["app"].startswith("LAKAD")` ([routes/backup.py:253](routes/backup.py:253)). The app has been
  rebranded to `APP_NAME = "DOCKET"` ([config.py:109](config.py:109)) — **do not "finish" the rebrand
  by changing these backup strings.** They identify a file format, not a brand. (The guard ORs the
  `LAKAD` prefix with `"version" in meta` / `"tables" in meta`, so a rename would degrade rather than
  hard-break recognition — but it would still make older backups less recognizable for no gain.)

- **`_restore_documents_tx` deliberately does NOT call `batch_save_docs`**
  ([services/backup.py:1256](services/backup.py:1256)). `batch_save_docs` opens its own connection,
  commits independently, and **fires client notifications** — using it would break restore atomicity
  and spam every client with status emails/pushes for restored documents. This is not duplication to
  be refactored away.

- **`services/client_view.py` lives outside `services/documents.py` on purpose**
  ([services/client_view.py:5](services/client_view.py:5)). It is the client-safe view-model layer and
  must never be reachable from staff rendering or the mobile API, so internal `officer`/`remarks`
  fields can't leak to clients. Don't merge it into `documents.py` for tidiness.
  Its action classification uses **lowercased substring matching, not equality** — the document
  `action` strings are f-strings, not an enum. Don't "fix" it into an equality check.

- **Client notifications run on a bare thread and that is a decision, not an oversight**
  ([services/client_notify.py:15-18](services/client_notify.py:15)). The comment explicitly says do
  NOT rely on it for guaranteed delivery and **do NOT add a queue now**. `MILESTONE_STATUSES`
  deliberately excludes internal `Transferred`/`Routed` movements — clients aren't told about
  internal shuffling.

- **Password reset stores only the SHA-256 hash of the token, never the raw token**
  ([services/password_reset.py:24](services/password_reset.py:24)). It deliberately does NOT copy the
  invite flow's plaintext-token pattern. Its rate limiting is DB-backed (not the in-memory
  `RATE_LIMITS`) specifically because multi-worker gunicorn gives each process its own in-memory
  view, which would let an attacker exceed the limit N-fold. Don't consolidate the two limiters.

- **`routes/auth.py:219`** — a mail/token failure inside the reset-request path must swallow the
  exception and **not** change the response, so the endpoint can't be used to enumerate which emails
  exist. The bare `except: pass` is intentional.

- **`build_transfer_slip` must not be called for INTERNAL transfers**
  ([services/misc.py:472](services/misc.py:472)) — internal transfers create no routing slip.

- **The 403 error handler redirects instead of returning 403** for non-`/api/` paths
  ([app.py:506-514](app.py:506)). This is why several route tests see a `302` where they assert
  `200`/`403`. It's deliberate (guests get sent to login rather than a dead end) — the tests are what's
  stale, not the handler.

- **Upload limits are two-tier by design** ([config.py](config.py) FIX 9): 25 MB app-wide, with a
  route-scoped 100 MB **only** for `/backup/restore` via a `before_request` hook
  ([app.py:263](app.py:263)). Full backups run 7-10 MB+. Don't collapse these into one limit.

## Conventions

- **Commit style is mixed** and no hook enforces one. Both Conventional Commits
  (`feat(admin):`, `fix(trash):`, `refactor(icons):`, `test:`) and plain sentences
  (`Add LOG cart count badge…`) appear in recent history. Match the surrounding style; don't
  reformat others' commits.
- Merges into production get a descriptive merge commit (`Merge <what> …`, `Promote <what> from
  testdoc to production`), not a bare `Merge branch`.
- Branch names are also mixed: `feature/self-service-password-reset`, `restore-upload-limit`,
  `backup-stage2-restore-fidelity`, plus environment-ish branches `testdoc` / `rome`.
- `config.py` and `app.py` carry numbered `FIX n:` comments referencing a security-hardening pass.
  When you touch that code, keep the numbering coherent rather than renumbering.

## Working discipline
- **Verify before you fix.** Confirm the defect still exists in the current code before writing a fix. Filed items go stale; a filed diagnosis is a hypothesis, not a finding.
- **Investigate before building.** For any non-trivial task, diagnose in the actual codebase first. State what you found before proposing a change.
- **Small verified steps.** One change per branch. Commit and verify before the next. Always leave the system working.
- **Say when you don't know.** Don't assert something you haven't checked. Don't claim a check ran if it didn't.

## Backlog & work-selection discipline
- Capture before drift: when a new idea, gap, or bug surfaces mid-work, log it to BACKLOG.md immediately — before deciding whether to act on it. An idea worth doing is worth writing down the moment it appears. (You may still choose to do it now, but capture first.)
- Choose next work by PRIORITY, not arrival order. Backlog is NOT strict FIFO — do the most important/severe item, not the oldest. A live bug or a gap affecting many users beats a nice-to-have logged earlier.
- Before starting a new arc: review the backlog and pick deliberately. Ask "is anything logged more important than what I'm about to start?"
- After finishing an arc: do a short "what did this touch?" check — log any gaps or affected surfaces the work exposed. Features are not done until the parts they affect (existing data, other surfaces, edit paths) are checked, not just the happy path on new data.

## BACKLOG.md discipline
Before every commit, ask: what did this work CLOSE?
- Fixed a filed item → tick it, move it to Closed, and add one line on what actually turned out to be wrong (often not what the entry said).
- Surfaced something new → add it.
- Changed the shape of an existing item → rewrite it. A stale entry is worse than none.

Both directions, every commit. The edit ships in the SAME commit as the fix, or in the merge commit — never as a separate "update backlog" commit, because that's the one you skip when you're tired.

Do not wait to be asked. If a merge lands and BACKLOG.md didn't change in either direction, either nothing was learned or the file is now lying.

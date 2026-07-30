# Backlog

## How this file works

Before every commit, ask: what did this work CLOSE?
- Fixed a filed item → tick it, move it to Closed, and add one line on what actually turned out to be wrong (often not what the entry said).
- Surfaced something new → add it.
- Changed the shape of an existing item → rewrite it. A stale entry is worse than none.

Both directions, every commit. The edit ships in the SAME commit as the fix, or in the merge commit — never as a separate "update backlog" commit, because that's the one you skip when you're tired.

Do not wait to be asked. If a merge lands and BACKLOG.md didn't change in either direction, either nothing was learned or the file is now lying.

> **Verify before you fix.** Backlog items go stale. Confirm the defect still exists before writing a fix.

---

## Live bugs

Things broken for users right now.

- [ ] **Mobile: accepting a document crashes its success handler (`setAcceptTarget` is not defined).**
  [mobile/app/(app)/receive-docs.tsx:170](mobile/app/(app)/receive-docs.tsx:170) calls
  `setAcceptTarget(null)` inside `acceptMutation.onSuccess`, but **no `acceptTarget` state is declared
  anywhere in the file** — `grep -n "acceptTarget" mobile/app/\(app\)/receive-docs.tsx` returns only
  that one line. `tsc --noEmit` reports it as `error TS2304: Cannot find name 'setAcceptTarget'`.
  At runtime this throws a `ReferenceError` as the *first* statement of `onSuccess`, so everything
  after it is skipped: `invalidate()` never runs (list doesn't refresh), the "Document received
  successfully" toast never shows, and the follow-up forward-to-intended-recipient prompt never fires.
  The `POST /documents/<id>/accept` itself already succeeded server-side, so the document *is*
  accepted — the UI just silently fails to reflect it. Not verified on a device; diagnosis is from
  source + typecheck.

- [ ] **Mobile: 8 TypeScript errors, and `tsc` exits 0 anyway.**
  `cd mobile && ./node_modules/.bin/tsc --noEmit` prints 8 errors but returns exit code **0**, so any
  CI or pre-commit hook keyed on the exit code would pass silently. Beyond the `setAcceptTarget` bug
  above, the other 7 are: two unresolved module imports (`lib/services/auth.ts:1` → `./config`,
  `lib/store.ts:2` → `../types`); two `boolean` assigned to `string` in
  [lib/prefetch.ts:75](mobile/lib/prefetch.ts:75) and [:86](mobile/lib/prefetch.ts:86); a
  `string | undefined` → `SetStateAction<string>` in
  [receive-docs.tsx:537](mobile/app/(app)/receive-docs.tsx:537); `EncodingType` missing from
  `expo-file-system` in [bulk-create-users.tsx:127](mobile/app/(app)/bulk-create-users.tsx:127)
  (likely an SDK-version drift, that export moved); and `version` missing on `EmbeddedManifest` in
  [hooks/useAppVersion.ts:48](mobile/hooks/useAppVersion.ts:48). The two unresolved imports are the
  suspicious ones — either dead files or a genuinely broken import path. Not yet triaged individually.

## Known bounds

Real but narrow limitations. Things that are wrong but contained, or design decisions that keep producing bugs.

- **Pre-existing test failures — all stale tests, not product bugs. The baseline differs between
  a dev machine and the server, so state which you ran.**
  - **Local (no mail credentials in `.env`):** `14 failed, 328 passed, 1 skipped`.
  - **Server (real `GMAIL_APP_PASSWORD` + `MAIL_SENDER` in `.env`):** 2 additional failures in
    `tests/test_email_service.py`, so `16 failed`.

  (Passed count rose from 313 to 328 on 2026-07-20 when the `APP_URL_CONFIG` branch added 15 tests.)
  Three independent root causes, all "the code moved on and the tests didn't":

  1. **9 failures in `tests/test_client_routes.py`** — `_login_as_client`
     ([tests/test_client_routes.py:56](tests/test_client_routes.py:56)) POSTs credentials to
     `/client/login`, but that route was centralized: it now *unconditionally* 302-redirects to
     `auth.login` without ever authenticating
     ([routes/client.py:161-171](routes/client.py:161)). The helper's `assert 302` still passes by
     coincidence, so the fixture reports success while establishing **no session** — every downstream
     client test (portal, submit, trash, delete) then fails. `TestClientLogin::test_get_renders_form`
     fails more directly: it asserts `200` for a form that no longer exists there.
     Fix direction: point the tests at `/login`. Don't "fix" the route back.

  2. **5 failures in `tests/test_scanning_routes.py::TestOfficeAction`** — the tests request
     `/office-action/main-office-rec` with **no `exp`/`sig` query params**. Office-action QR URLs are
     now HMAC-signed, so `verify_office_action` ([services/qr.py:58](services/qr.py:58)) returns
     `False` → `abort(403)` → and the 403 handler ([app.py:506-514](app.py:506)) *redirects* guests to
     login rather than returning 403. Net result: the tests assert `200` and get `302`. Both the
     signing and the redirect are intentional; the tests predate them and need to sign their URLs.

  3. **2 failures in `tests/test_email_service.py`, on the server only** — these tests predate the
     **Brevo → Gmail migration**. They drive `BREVO_API_KEY`
     ([tests/test_email_service.py:104](tests/test_email_service.py:104), [:115](tests/test_email_service.py:115)),
     but `MAIL_ENABLED` is now derived from `GMAIL_APP_PASSWORD and MAIL_SENDER`
     ([config.py:135-138](config.py:135)). On a dev machine those are unset, so `MAIL_ENABLED` is
     `False`: `test_send_invite_email_disabled_by_default` gets the `ok is False` it asserts, and
     `test_send_invite_email_mocked_brevo` hits its own `pytest.skip`
     ([:124](tests/test_email_service.py:124)) — that skip *is* the "1 skipped" in the baseline. On
     the server both credentials are set, `MAIL_ENABLED` is `True`, and both tests fail.
     Fix direction: drive `GMAIL_APP_PASSWORD`/`MAIL_SENDER`, not `BREVO_API_KEY`, and monkeypatch
     `MAIL_ENABLED` explicitly instead of depending on ambient `.env` state.

  **Until these are fixed, `pytest` is not a clean pass/fail signal** — you must compare against a
  baseline that itself depends on where you ran it, which is exactly the kind of thing that hides a
  real regression. Worth fixing for that reason alone.

- **Rebrand to `DOCKET` is half-applied, and the rest of it must NOT be finished blindly.**
  `APP_NAME = "DOCKET"` ([config.py:109](config.py:109)) covers web templates, but `LAKAD` remains in:
  backup metadata (**load-bearing — see CLAUDE.md invariants, do not change**), the console banner
  ([app.py:605](app.py:605)), password-reset email copy
  ([routes/auth.py:281-298](routes/auth.py:281)), and an API notification string
  ([blueprints/api.py:3003](blueprints/api.py:3003)). The email/banner ones are safe to update; the
  backup ones are not. Anyone doing a blanket find-and-replace will break backup recognition.

- **`get_base_url()` can still return `""`, which yields a relative URL in a QR.**
  [services/qr.py:34-44](services/qr.py:34). If `APP_URL` is empty AND `request_host_url` is empty
  AND `socket.gethostbyname` raises, the final `except` returns `""` — and every caller does
  `f"{base}/doc-scan/…"`, producing a relative path that encodes into an unscannable QR. This is the
  same failure `make_doc_status_qr_png` was just fixed for (see Closed), one level down. Narrow: it
  needs a DNS failure on a machine with no `APP_URL`, so production is not exposed. Not fixed with
  that change because `get_base_url` has seven callers and changing its contract deserves its own
  branch. Fix direction: return a sentinel or raise rather than `""`; a QR that can't be built should
  fail loudly, never silently emit a relative path.

- **Three `make_doc_status_qr_png` call sites don't pass `request.host_url`.**
  [routes/client.py:769](routes/client.py:769), [routes/scanning.py:158](routes/scanning.py:158),
  [routes/scanning.py:379](routes/scanning.py:379). The `host_url` parameter added on 2026-07-20
  defaults to `""`, so these three fall through `get_base_url` to `APP_URL` or the LAN-IP guess
  rather than the actual request host. With `APP_URL` set — i.e. production — this is invisible and
  correct. It only matters on a dev/LAN deployment with `APP_URL` empty, where the QR would get the
  `gethostbyname` guess instead of the host the client actually reached the app on. All three are in
  request context, so the fix is mechanical: pass `request.host_url`. Left out of the original change
  to keep the behaviour delta to one function.

- **`templates/doctracker-processflow.html` is dead and factually wrong — delete it.**
  Nothing renders it: the only matches for its name are its own `url_for('static', …)` links to
  [static/css/doctracker-processflow.css](static/css/doctracker-processflow.css) and
  [static/js/doctracker-processflow.js](static/js/doctracker-processflow.js). No route in `routes/`,
  `blueprints/` or `app.py` calls `render_template` on it. It also describes an architecture that no
  longer exists — 6 Railway references across the page (the `☁️ Cloud-Based (Railway)` chip at L26,
  a "Deploy to Railway / Railway auto-deploys" step and "APP_URL in Railway Variables panel" at L68,
  "admin credentials from Railway Variables" at L112, `PostgreSQL — Persistent Database (Railway)`
  at L137, a `Railway — Cloud Hosting & Auto-Deploy` tech entry at L138, and the footer stack at
  L154) — whereas production is gunicorn under systemd behind a Cloudflare tunnel, deployed by the
  NEXUS webhook. Correcting it means rewriting the deployment narrative, and the page is unreachable,
  so **deleting it (with its CSS and JS) is the better move.** Deliberately excluded from the
  `APP_URL_CONFIG` branch, which corrected only the equivalent live text in `send_invite.html`.

- **In-memory rate limiting is per-process and leaks under multi-worker gunicorn.**
  `RATE_LIMITS` ([config.py](config.py)) is in-memory, and production runs `--workers 4`, so the
  effective limit is up to 4× the configured one. Already known and worked around for password reset
  (which uses a DB-backed limiter — see `PASSWORD_RESET_RATE_LIMITS`), but **login, register,
  status_update, doc_create, and api limits are still in-memory** and therefore still 4×-able.

- **Role enforcement on web routes is incomplete — most staff routes are `login_required`-only.**
  `login_required` ([utils.py:26](utils.py:26)) checks only `session["logged_in"]`, not role, so until
  now any logged-in session — **including a `client`** — could reach staff routes by typing the URL.
  The UI hides the links (nav is gated by `current_role` in `templates/base.html`), so it was an
  exposure by direct request, not a visible one. A `staff_required` decorator now exists
  ([utils.py:49](utils.py:49)) — session-based (admits the env-var admin, which has no `users` row),
  redirect-on-fail like `admin_required`.

  **Partially closed (branch `feature/staff-required-decorator`, commit 1a of 3):** applied to the four
  confidentiality-sensitive routes that render internal `officer`/`remarks` fields the `client_view.py`
  sanitizer would otherwise strip — `view_doc` ([routes/dashboard.py:695](routes/dashboard.py:695)),
  `travel_log_json` ([routes/dashboard.py:2179](routes/dashboard.py:2179)), `web_doc_lookup`
  ([routes/scanning.py:293](routes/scanning.py:293)) — plus `so_download`
  ([routes/so.py:989](routes/so.py:989)), which also got the `_require_staff()` (`can_generate_so`)
  gate its SO siblings have.

  *Correction to the original framing of `so_download`:* it was **not** `login_required`-only — it
  already had an inline `role not in ("staff","admin")` 403. The real gap was the missing
  `can_generate_so` check, so the leak severity was overstated: it was reachable only by a staff user
  lacking SO access, never by a client.

  **Still open (deferred, NOT in commit 1a):**
  - *1b — remaining ~39 web staff routes*: add/edit/transfer/release/status/routing/scanning etc. still
    `login_required`-only. See the full inventory in the staff_required investigation.
  - *1c — `jwt_staff_required` for mobile (higher priority than 1b)*: `api_create_document`
    ([blueprints/api.py:447](blueprints/api.py:447)), `api_quick_note`
    ([blueprints/api.py:1622](blueprints/api.py:1622)), `api_release_document`
    ([blueprints/api.py:1511](blueprints/api.py:1511)), and `api_check_duplicate`
    ([blueprints/api.py:1646](blueprints/api.py:1646)) are `@jwt_required()`-only — reachable **and
    functional from a client token today**. Build it `g`-cached so the per-request
    `get_user_by_username` fetch doesn't fire twice (or per keystroke on `api_check_duplicate`).
  - *Cleanup*: the inline `role not in ("staff","admin")` 403 in `so_download` is now shadowed by
    `_require_staff()` and is dead — remove it in a follow-up (left in 1a to avoid refactoring).
  - *Decide deliberately (not a `staff_required` question)*: the dropdown-options editors, `db_status`,
    `app_qr`, and `client_reg_qr` may want `admin_required` rather than `staff_required` — needs an
    intent call, not a mechanical gate.

## Features / polish

Wanted, not broken.

- **No linter or typechecker on the Python side at all.** No ruff/mypy/flake8/black/pylint installed
  in `.venv`, no config file for any of them. For a ~27k-line Flask app with security-sensitive auth,
  CSRF, and backup/restore paths, that's a real gap — but adding one now would produce a large
  pre-existing error baseline, so it needs to be introduced deliberately (start with `ruff` defaults
  and a baseline, not a big-bang cleanup).

- **CSP still uses `unsafe-inline` for scripts.** [app.py:460](app.py:460) —
  `# TODO: replace 'unsafe-inline' with nonces once templates support it`. The blocker is the
  templates, not the header.

- **`.python-version` says 3.13.3; the actual `.venv` is Python 3.14.3.** Harmless today (tests pass
  on 3.14) but it's a trap for anyone rebuilding the venv from the pin. Pick one.

- [ ] **`origin/main` should be deleted or archived on the remote.** It is **363 commits behind
  `DOCTRACKER_PROD` and 0 ahead** — strictly an ancestor, holding nothing unique. With
  `.github/workflows/deploy.yml` gone it now has **no consumer at all**: nothing in this repo
  references it, and NEXUS Panel deploys from `DOCTRACKER_PROD`. But it still *looks* like the trunk
  to anyone who lands on the GitHub repo and doesn't read CLAUDE.md, which is exactly how someone ends
  up branching from a stale tree. **This is an operator action, not a code change** — deleting or
  archiving a remote branch can't be done from a PR; someone with repo admin has to do it (and should
  decide whether to archive-tag it first rather than hard-delete).

- [ ] **Password authentication is enabled for SSH on the production server.** Observed during the key
  rotation above: removing the old key caused a **fallthrough to password auth, which succeeded** — so
  the server accepts passwords for SSH login, a brute-forceable surface exposed to anyone who can reach
  the port. Consider setting `PasswordAuthentication no` in `sshd_config`. **Do this only AFTER
  confirming key-only access works for every account that needs it** — disabling password auth while an
  account still depends on it (no working key installed) locks that account out of the box, and if
  it's the only admin path, locks everyone out. Operator action on the server; not a code change.

## Closed

- [x] **~~`routes/so.py` hardcoded the app's own hostname while everything else read `APP_URL`.~~**
  Closed 2026-07-20 on branch `APP_URL_CONFIG`. `_VERIFY_BASE` at `routes/so.py:519` was a literal
  `https://doctracker.depedleytepersonnelunit.com`, the **sole** backend hostname literal — every
  other QR path and email link already resolved through `APP_URL`/`get_base_url`. Replaced with
  `_verify_base()`, which reads `APP_URL` at call time and refuses when it is unset or not absolute.

  **Two things turned out to be different from the initial diagnosis.**

  First, the filed plan was to raise at the point of use (the old `:929`). Tracing the handler showed
  that would be actively harmful: the route's `try` opens at `:876` and by `:929` it has already
  saved the `.docx`, created a documents row, fired an auto-transfer notification, and INSERTed into
  `so_records`. Raising there returns 500 having left **a QR-less file on disk, an orphaned document
  row, a notification already sent, and an `so_records` row no QR points at** — and a retry makes a
  second set. The check now runs in the validate block *before* any side effect.

  Second, the concern that a `RuntimeError` would be swallowed into a generic 500 was **unfounded**:
  the blanket handler returns `str(e)` as `message` and the frontend displays it
  ([templates/so_request.html:648](templates/so_request.html:648)). The message was always going to
  reach the operator. The ordering was the real defect; the error surfacing was fine.

  Also closed in the same commit: `make_doc_status_qr_png` emitted a **relative** `/doc-scan/<token>`
  whenever `APP_URL` was empty (`base = APP_URL or ""`) — a client-facing QR that was silently
  unscannable. Now routed through `get_base_url`. Two narrower follow-ups were surfaced rather than
  swept in; both are filed under Known bounds above.

- [x] **~~`origin/main` is dead but still wired to the deploy workflow.~~** Closed 2026-07-14 by
  deleting `.github/workflows/deploy.yml` (branch `remove-dead-deploy-workflow`).

  **The filed entry was wrong about the danger.** It framed this as a stale-tree risk — "pushing to
  `main` would deploy a 363-commit-stale tree." That was too generous. Reading the workflow properly,
  it would not have deployed `main` *or* any known ref:

  - It ran a bare **`git pull` with no `git checkout`**, so it would have deployed **whatever branch
    the server happened to have checked out** — an unknown ref, not `main`. The branch that triggered
    the workflow had no bearing on what got deployed.
  - It targeted **`/var/www/doctracker`**, which is **not where this app lives**. Production is under
    NEXUS-managed deployments, not that path.
  - It ran **`pkill -f "python app.py"`** and restarted with **`nohup python app.py &`** — so it would
    have killed the running process and tried to bring production back up as a **single-process Flask
    dev server**, not the multi-worker gunicorn that actually serves it (`Procfile`, systemd unit
    `app-doctracker`, behind a Cloudflare tunnel).

  So the real hazard wasn't "deploys something stale," it was "**kills production and restarts it
  wrong, from an unknown ref, in the wrong directory**." It never was the deploy path for current
  production — deploys go through a GitHub webhook consumed by **NEXUS Panel**, an external Flask tool
  with no presence in this repo (operator-confirmed; that's why grepping found no trace of it).

  `origin/main` itself is strictly an ancestor of `DOCTRACKER_PROD` (363 behind, 0 ahead) and holds
  nothing unique. Deploy path now documented accurately in [CLAUDE.md](CLAUDE.md) "Commands".

  **Follow-up:** the GitHub Actions secrets outlived the workflow — now closed, see the next item.

- [x] **~~GitHub Actions SSH secrets survive the workflow deletion and may need rotating.~~** Closed
  2026-07-15 (branch `close-ssh-secret-rotation`). Resolved by deleting the secrets and rotating the
  server login key.

  **What was actually found was worse and larger than this entry predicted.** The prediction was
  "three secrets, rotate the deploy key if it's still live." Reality:

  - The secret set was **FOUR, not three**: `SSH_HOST`, `SSH_PORT`, `SSH_PRIVATE_KEY`, `SSH_USERNAME`.
    `SSH_PORT` was **never referenced by the workflow** at all — so reading the workflow (which is all
    the previous entry did) would never have surfaced it. They had been present **~4 months**.
  - `SSH_PRIVATE_KEY` was **not a dedicated deploy key** as assumed. The sole inbound key installed on
    the production server (fingerprint `3BnEmhD5`, label `depedleyte-server`) turned out to be the
    **operator's personal, passphrase-protected login key** — the only inbound key on the box.
  - Whether that key's private half was ever copied into `SSH_PRIVATE_KEY` **could not be verified from
    outside GitHub** (secret values are write-only). Per the credential-rotation-on-exposure rule, it
    was therefore **rotated rather than assumed safe** — an unverifiable exposure of a personal login
    key to the whole server is treated as an exposure, not waved through.

  **Resolution:**
  - All **four** GitHub secrets deleted.
  - Server login key **rotated**: new key `depedleyte-server-2026-07` installed and verified; old key
    `3BnEmhD5` removed and confirmed dead (login with it now fails).
  - NEXUS's **outbound** `github_panel` key correctly **left untouched** — it is how NEXUS pulls from
    GitHub and is unrelated to the inbound login key that was exposed.

  Surfaced a new issue in the process — see "Password authentication is enabled on the production
  server" under Features / polish.

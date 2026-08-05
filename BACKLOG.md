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

- [ ] **Mobile: 7 TypeScript errors, and `tsc` exits 0 anyway.**
  `cd mobile && ./node_modules/.bin/tsc --noEmit` prints 7 errors but returns exit code **0**, so any
  CI or pre-commit hook keyed on the exit code would pass silently. The 7 are: two unresolved module
  imports (`lib/services/auth.ts:1` → `./config`,
  `lib/store.ts:2` → `../types`); two `boolean` assigned to `string` in
  [lib/prefetch.ts:75](mobile/lib/prefetch.ts:75) and [:86](mobile/lib/prefetch.ts:86); a
  `string | undefined` → `SetStateAction<string>` in
  [receive-docs.tsx:536](mobile/app/(app)/receive-docs.tsx:536); `EncodingType` missing from
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

- **Role enforcement on web+mobile routes — the core gap is now CLOSED (1a+1b+1c); only cleanups remain.**
  `login_required` ([utils.py:26](utils.py:26)) checks only `session["logged_in"]`, not role, so any
  logged-in session — **including a `client`** — used to reach staff routes by typing the URL. The UI
  hid the links (nav is gated by `current_role` in `templates/base.html`), so it was an exposure by
  direct request, not a visible one. Two session-based decorators now close it: `staff_required`
  ([utils.py:49](utils.py:49)) — redirect-on-fail like `admin_required` — and its JSON twin
  `staff_required_json` ([utils.py:70](utils.py:70)) — 401/403 JSON, never a redirect. Both admit the
  env-var admin (which has no `users` row).

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

  **Also closed (commit 1c): mobile JWT gate.** `jwt_staff_required` + `_is_env_admin` added to
  [blueprints/api.py:98](blueprints/api.py:98) — single-fetch, `g`-cached (`g.current_api_user`),
  admits the env-var admin (no `users` row) via the inline env check, includes `superadmin`. Applied to
  `api_create_document` ([blueprints/api.py:485](blueprints/api.py:485)), `api_quick_note`
  ([blueprints/api.py:1660](blueprints/api.py:1660)), and `api_check_duplicate`
  ([blueprints/api.py:1684](blueprints/api.py:1684)) — all three had no ownership branch and no
  legitimate client use, yet were reachable **and functional from a client token** before this. New
  `staff_tokens`/`client_tokens` fixtures + `TestJwtStaffGate` (6 tests, client→403 / staff→success)
  raise the baseline 328→334 passed; the 14 failures are unchanged.

  **`api_release_document` ([blueprints/api.py:1511](blueprints/api.py:1511)) deliberately NOT gated.**
  Its owner is `original_logged_by or logged_by` ([:1524](blueprints/api.py:1524)) and it admits
  `user_id == original_logger`. `api_client_submit` stamps `logged_by = client_id` (see the new item
  below), so a client is the legitimate release-owner of their own submission — gating it would 403 a
  real flow. Left on `@jwt_required()`. `api_update_status` also left as-is: it has a genuine
  client-owner branch ([:535](blueprints/api.py:535)).

  **Also closed (commit 1b): the remaining web staff surface.** `staff_required` (redirect, HTML) on
  15 routes and `staff_required_json` (JSON 403) on 18 AJAX routes, across
  `dashboard.py`/`offices.py`/`scanning.py`. `transfer_doc`
  ([routes/dashboard.py:1048](routes/dashboard.py:1048)) got an **inline** `is_ajax`-negotiating gate
  rather than a decorator: the route owns a `{"ok": False, ...}` failure contract that the decorator's
  `{"error": ...}` shape would not match. `so_types_list`/`so_fields` left as-is (already had correct
  inline JSON 403). Tightened `test_client_blocked_from_add_doc` — it accepted `200`, so it passed
  *with the leak open*; now `(302, 403)`. New `TestStaffSurfaceGate` (8 tests) raises the baseline
  334→342 passed; the 14 failures are unchanged.

  *Finding (defense-in-depth, not a bug):* on POST routes, `csrf_check` ([app.py:332](app.py:332))
  runs as a `before_request` **ahead of** the RBAC decorators, so a token-less client POST is 302'd by
  CSRF before it ever reaches the 403. Both paths are closed — no token → CSRF stops it, valid token →
  RBAC stops it. The POST test seeds a token via a GET first (login clears the session; the token is
  only re-seeded on the next request) to exercise the RBAC path specifically.

  **Still open (deferred):**
  - *Cleanup (own commits)*: handler-body single-fetch refactor — the gated mobile handlers still call
    `get_user_by_username` in-body though `jwt_staff_required` caches `g.current_api_user`; collapses
    `api_update_status`'s three fetches
    ([:532](blueprints/api.py:532)/[:533](blueprints/api.py:533)/[:538](blueprints/api.py:538)) and
    `api_edit_document`'s two ([:2193](blueprints/api.py:2193)/[:2194](blueprints/api.py:2194)) to one.
    Plus three now-dead guards left in place to avoid refactoring: the inline `role not in (...)` 403 in
    `so_download` (shadowed by `_require_staff()`), and the inline *redirects* in
    `staff_confirm_appointment`/`staff_reject_appointment` (shadowed by `staff_required_json` — and a
    redirect was the wrong failure mode for a JSON route anyway). And widen web `staff_required`
    ([utils.py:49](utils.py:49)) to include `'superadmin'`, matching mobile `jwt_staff_required`.
  - *NEW — same defect class as 1b, admin scope*: `admin_required` ([utils.py:36](utils.py:36))
    redirects-to-HTML on failure but gates two **JSON** routes — `delete_routing_slip`
    ([routes/offices.py:540](routes/offices.py:540)) and `bulk_create_offices`
    ([routes/offices.py:147](routes/offices.py:147)) — so an auth failure there 302s-to-HTML a `fetch`
    caller. Works today only because an admin is always the caller. Wants an `admin_required_json` twin.
  - *Test coverage*: no test asserts an **unauthenticated** (no-token) request to the JWT-gated mobile
    endpoints gets **401** — `TestJwtStaffGate` only exercises client-token→403 and staff→success. Add
    a no-token→401 case so the unauthenticated path is pinned alongside the authorization path.
  - *Confirm dead-or-alive (non-urgent)*: `get_transferred_documents`
    ([routes/dashboard.py:1926](routes/dashboard.py:1926)) and `get_dropdown_options_api`
    ([routes/dashboard.py:1943](routes/dashboard.py:1943)) were gated for safety in 1b, but no
    client-side caller turned up in templates or static JS — verify they're live before assuming so.
  - *Decide deliberately (not a `staff_required` question)*: the dropdown-options editors, `db_status`,
    `app_qr`, and `client_reg_qr` may want `admin_required` rather than `staff_required` — needs an
    intent call, not a mechanical gate.

- **Client-submit endpoints disagree on ownership shape — one stamps `logged_by` on a client submit.**
  `api_client_submit` ([blueprints/api.py:3158-3159](blueprints/api.py:3158)) stamps **both**
  `logged_by` **and** `submitted_by` with the client's id; `api_client_submit_mobile`
  ([blueprints/api.py:3389](blueprints/api.py:3389)) stamps **only** `submitted_by`. Same user action,
  two ownership shapes — this is the source of the `both_stamped=2` documents seen in prod. `logged_by`
  on a client submission is almost certainly wrong: `logged_by` means "staff logged this from inside the
  office," and it's what `api_release_document` keys ownership on ([:1524](blueprints/api.py:1524)) —
  which is exactly why that endpoint couldn't be staff-gated in 1c. Needs its own investigation: what
  breaks if `api_client_submit` stops writing `logged_by`, whether the 2 existing docs need a data fix,
  and how this interacts with the staff-submission ownership model. **HIGH** — directly feeds the
  submission-ownership work.

- **The username rename deliberately does NOT rewrite free-text fields.** `rename_user`
  ([services/auth.py:762](services/auth.py:762)) rewrites structured identity fields only.
  `referred_to`, `sender_name`, `recipient_name`, and `travel_log[].remarks` are intentionally
  excluded and documented in code — they are free text that may coincidentally contain a name, and
  rewriting them risks corrupting prose. This is a boundary, not a gap: a renamed user's name can
  still appear verbatim inside those fields by design.

- **The rename's `travel_log` full_name pass is a sequential scan.** In the `fn_safe` branch the
  SELECT uses `jsonb_array_elements` + `lower(officer)`, which is not sargable and whose `OR` defeats
  the GIN-eligible `@>` containment term, so it necessarily scans. Fine under ~100k documents, and it
  runs once per rename inside the 120s transaction (the Kim → Paul rename over ~13k docs was clean).
  Revisit with an expression index on `lower(officer)` (or a restructured query) only if `documents`
  grows large.

## Features / polish

Wanted, not broken.

- [ ] **Opaque per-client QR token** (receive-side: staff pull up a client's pending docs by scanning
  the client's QR).
  - [x] **Storage + generation.** `client_qr_tokens` table (`token` PK, `username`, `created_at`;
    mirrors `doc_qr_tokens`) in [services/database.py](services/database.py), with a `username` index.
    `get_or_create_client_token` / `resolve_client_token` in
    [services/qr.py](services/qr.py) — the token is a **non-consuming, non-expiring opaque `CLI-`
    identifier** resolved server-side, so a photographed QR reveals only a random string, never the
    username. Guarded one-time backfill for existing clients in `_run_migrations`, and a generation
    hook in `create_user` for `role=client` (the single choke point all client-creation paths funnel
    through). Backfill uses the **shared migration cursor** (`cur=cur`) so inserts land in the same
    transaction as the `CREATE TABLE` — a fresh pooled connection would not see the uncommitted table.
    Backfill **NOT yet run against a real DB** — verified only in JSON-mode pytest (baseline
    `14 failed / 370 passed / 1 skipped` held; `test_qr_service` all green).
  - [x] **Client + staff token-fetch/resolve endpoints** in [blueprints/api.py](blueprints/api.py).
    `GET /client/qr-token` (client-auth: `@jwt_required` + inline `role=client` check) returns the
    caller's own token via `get_or_create_client_token`, keyed on `get_jwt_identity()` **only** (never
    a query param), with a `"" -> HTTP 500` guard so an empty QR is never rendered. `POST
    /staff/resolve-client-qr` (`@jwt_staff_required`, staff/admin only) resolves a scanned token to
    that client's **pending** docs (`submitted_by == user` AND `transfer_status == 'pending'`),
    then **scoped to what the calling staff can receive** (`pending_at_staff == caller` OR
    unassigned-at-caller's-office), mirroring `/pending-documents` — admins/env-admin still see all;
    returns `{client_username, client_name, documents[]}` in the `/pending-documents` serialized
    shape, with `client_name` read from the users record (never client input). Baseline held
    `14 failed / 376 passed / 1 skipped`.
    - Scoping was a follow-up fix: the first cut returned every doc a client had pending *anywhere*.
      A **live smoke test** surfaced it — scanning a client's QR at the counter showed months-old
      in-flight docs already accepted and routed deep, pending at *other* staff, which the scanning
      staff can't act on. Now mirrors `/pending-documents`' recipient narrowing exactly (env-admin
      resolved via `_is_admin_user`, since `g.current_api_user` is `None` for it).
  - [x] **Client app renders its QR** — [mobile/app/(client)/my-qr.tsx](mobile/app/(client)/my-qr.tsx)
    renders the opaque `CLI-` token **client-side** via `react-native-qrcode-svg` (first use of the
    already-installed lib), fetched from `GET /client/qr-token` (TanStack Query, `staleTime: Infinity`
    since the token is stable). Shows the client's `full_name`/`@username` from the auth store so staff
    can eyeball identity while scanning. Registered as a hidden route (`href: null`, like `track/[id]`);
    reached by a prominent brand-blue button at the top of `my-docs`. An empty/missing token routes to
    an error state (retry + pull-to-refresh) — **never** renders a blank `<QRCode value=""/>`. `tsc
    --noEmit` unchanged: 7 pre-existing errors, 0 new.
    - **Build fallout — SDK-54 dep drift (fixed).** The first EAS Android build of this screen failed
      at Gradle dependency resolution with **"No variants exist"** across the native module graph. Root
      cause: `react-native-svg` was declared with a caret (`^15.12.1`) and had floated to **15.15.4**,
      while Expo SDK 54 requires the **exact** pin `15.12.1`. It sat latent for months because nothing
      imported the lib — `my-qr.tsx` is the **first consumer**, so this was the first build to autolink
      svg's native Android code. Fixed via `npx expo install --fix`: `react-native-svg → 15.12.1`
      (exact), `babel-preset-expo → ~54.0.10` (was a wrong-**major** `55.0.19`), plus minor SDK-54 patch
      bumps to `expo`/`expo-dev-client`/`expo-linking`/`expo-notifications`/`expo-router`.
      `expo install --check` now clean; `tsc` unchanged. **Build not yet re-run** at commit time. The
      pre-existing `npm audit` advisories (28) are unrelated and left untouched.
  - [x] Staff scan → resolve client QR → batch-receive. `scanner.tsx` recognizes `CLI-` tokens with
    the same throw-and-catch dispatch as `SLIP_` (before the doc-id GET, so no wasted network calls),
    POSTs `/staff/resolve-client-qr`, and opens a batch-receive modal — "Receiving for {client_name}"
    over the client's receivable docs (already staff-scoped server-side). A prominent **Accept All**
    loops `POST /documents/{id}/accept` and **skips** the per-doc forward-to-intended dialog (mirrors
    `receive-docs.tsx` `handleAcceptAll`) so a batch never fires N forward prompts; **per-doc Accept**
    honors forward-to-intended for the selective case. An empty result (the client's docs are pending
    with other staff) renders a friendly "nothing here for you" state, not an error. Camera gate blocks
    scanning while the modal is open or resolving. `tsc --noEmit` unchanged (7 pre-existing, 0 new).
    **Not yet device-tested.** This completes the client-QR receive-side arc.

- [ ] **Display-name-only rename still orphans history** (follow-up to the shipped username-rename,
  now under Closed). The rename only fires when the username actually changes — `rename_user` rejects
  `old == new` username. Editing ONLY a user's `full_name` (username unchanged) takes the plain
  `update_user` path in `edit_user_route`, so historical `full_name` occurrences and the ambiguous
  `*_name` companions are NOT rewritten and orphan exactly as usernames did before the feature. Needs
  a same-username display-name-rewrite path: either a `rename_display_name(username, old_fn, new_fn)`
  service or relaxing `rename_user` to accept an unchanged username with a changed full_name, then
  wiring the full_name-changed branch in `edit_user_route`. Real follow-up feature, deferred out of
  Step 3 (its contract was deliberately not expanded).

- [ ] **`documents_updated == N` in `test_rename_user.py` is a magic number.** The happy-path
  assertion cross-checks the rewrite count against a hand-computed constant explained only by a
  comment, not derived from the seeded fixture — if the fixture changes, the number drifts silently
  and the check stops meaning anything. Consider deriving the expected count from the seeded documents.
  Test hygiene, not a product bug.

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

## Operational / cleanup

Non-code operator actions and housekeeping surfaced during recent work.

- [ ] **Rotate the prod `doctracker_app` DB password — it appeared in terminal scrollback during the
  rename work.** Rotate-on-exposure: the production `doctracker_app` Postgres password was visible in
  the terminal during the rename/verification session, so treat it as exposed and rotate it. Also
  rotate the `testdoc2_app` DB password and the `testdoc` `ADMIN_PASSWORD` (lower stakes, same
  session). Operator action on the server / secrets store; not a code change.

- [ ] **Branch cleanup.** `feature/username-rename-service` and `feature/staff-required-decorator`
  are both merged into `DOCTRACKER_PROD` and can be deleted. `testdoc` currently holds mangled
  rename-test data (it was reset to the feature tip for staging) and should be reset to track
  `DOCTRACKER_PROD` again once this merge is pushed.

- [ ] **`testdoc` deploy: empty Manage Users list + 500 on direct `/edit-user/<username>`.** On the
  `testdoc` deployment the Manage Users list renders empty and hitting `/edit-user/<username>`
  directly returns a 500 — the **prod** frontend is fine. It made staging the rename harder than it
  needed to be. Not blocking (prod unaffected) but worth diagnosing eventually; likely a testdoc
  data/env difference rather than a code bug.

- [ ] **Pre-rename backup retained — clean up in a few days.**
  `~/rename_backups/doctrack_pre_rename_20260731_214203.dump` was taken before the prod rename and is
  kept as a rollback safety net. Delete it once the rename has been confirmed stable for a few days
  (early August 2026).

## Closed

- [x] **~~Mobile: accepting a document crashes its success handler (`setAcceptTarget` is not defined).~~**
  [mobile/app/(app)/receive-docs.tsx:170](mobile/app/(app)/receive-docs.tsx:170) called
  `setAcceptTarget(null)` as the *first* statement of `acceptMutation.onSuccess`, throwing a
  `ReferenceError` that skipped everything after it — `invalidate()` (list refresh), the "Document
  received successfully" toast, and the forward-to-intended-recipient prompt — even though the
  `POST /documents/<id>/accept` had already succeeded server-side.
  **Closing reality:** it was **dead code left over from a removed accept-target flow**, not a missing
  wire-up. There was no `acceptTarget` state and no accept modal to restore — the whole file declares
  no such pair (only `rejectTarget`/`forwardTarget`/`staffPickerDoc`), and the single-doc accept fires
  directly from the green Accept button (`acceptMutation.mutate(doc)`) with no intermediate target or
  confirmation UI. The fix was a **one-line deletion** of `setAcceptTarget(null);`. Verified by `tsc`:
  `error TS2304: Cannot find name 'setAcceptTarget'` is gone and the mobile error count dropped
  **8 → 7** (the surviving `receive-docs.tsx` line-537 `SetStateAction` error shifted to 536 and stays
  open under the "7 TypeScript errors" item). Not yet verified on a device — device/testdoc
  verification still pending.

- [x] **~~Username rename with full-history rewrite.~~** Shipped and **deployed to prod** (merge
  `d86b0d0`, onto rollback target `7e05976`; no schema changes). Usernames are stored as bare strings
  across `documents` JSONB (`logged_by`, `original_logged_by`, …) and ~15 other tables/columns with
  **no FK**, so the old edit-user flow renamed only the `users` row and **orphaned every referencing
  document** — while the UI already promised "Changing the username will also update the login name."
  `rename_user` ([services/auth.py:762](services/auth.py:762)) now rewrites every reference in ONE
  `get_conn()` transaction (mirrors `restore_backup`; no `batch_save_docs`/`audit_log` inside), wired
  into `edit_user_route`.

  **All four build steps landed:**
  - `f580645` — validator (`_validate_username`, `[a-z0-9._-]`, 3–32) + `rename_user` service:
    set-based rewrite of `_RENAME_DOC_KEYS` and the §2c tables, plus the ambiguous
    `received_by`/`accepted_by`/`travel_log[].officer` fields matched on exact username always and on
    old full_name **only when unique among users** (shared name → `full_name_ambiguous`, full_name
    pass skipped so a different person's history is never touched). (Steps 1+2)
  - `92a6584` — structured companion fields (`accepted_by_username`, `*_name`,
    `transfer_batches.transferred_to_name`) + **case-insensitive** full_name matching everywhere
    (prod had casing drift, canonical `KIM WENDELL DAVOCOL` vs stored `Kim Wendell Davocol`, that
    exact match missed); the written-back value is the new canonical full_name. Free-text fields left
    out on purpose (now filed under Known bounds). (Step 2.5)
  - `18562b1` — route wiring + guards: a genuine username change diverts to `rename_user` **FIRST**,
    then `update_user` with `new_username=None`; server-side self-rename guard; post-commit
    `audit_log("username_renamed", …)`; prominent re-login warning; `full_name_ambiguous` warning.
    Route tests in [tests/test_admin_rename_route.py](tests/test_admin_rename_route.py). (Step 3)
  - `d86b0d0` — merged to `DOCTRACKER_PROD`.

  **Verified on `testdoc` against a full production data copy**, then the **real
  `Kim Wendell Davocol` → `Paul Opiniano` rename was executed on prod and verified clean**: zero
  remaining old-username traces across `documents`, `travel_log`, and `activity_log`; the `users` row
  and `full_name` are correct; **~13,192 documents** carried forward.

  **Closing reality (learned during testdoc verification — the entry that would otherwise lie):** the
  rename MUST go through `edit_user_route`, which runs `rename_user` **THEN** `update_user`. Calling
  `rename_user` directly leaves `users.full_name` UNSET — `rename_user` never writes that column (its
  uniqueness gate READS the old value while it is still the old name); `update_user` is what sets the
  new full_name afterward. The ordering in the route is load-bearing, not incidental.

  Deferred follow-ups from this work are filed above: the display-name-only rename gap and the
  `documents_updated` test magic number (Features / polish); the free-text boundary and the
  `travel_log` seq-scan (Known bounds); branch cleanup, the retained pre-rename backup, and the
  `testdoc` frontend bug (Operational / cleanup).

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

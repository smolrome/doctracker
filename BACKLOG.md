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
    - **Build fallout #2 — dev build emitted a .tar.gz of debug+release APKs, not one installable
      .apk (fixed).** After the dep alignment, the `development` EAS build produced a `.tar.gz`
      containing `debug/` + `release/` APK folders instead of a single installable `.apk`. Cause: a
      stale, gitignored `mobile/android/` prebuild (a May-16 local `expo prebuild`) was being reused by
      EAS (build log: "reusing /android"), so Gradle assembled **both** build variants and EAS tarballed
      them. DTRacker builds a clean single APK because it has **no** local native folder — it's fully
      managed. Fixed by deleting the stale `mobile/android/` and adding `mobile/.easignore` (`/android`,
      `/ios`) so EAS runs `expo prebuild` fresh from `app.json` on **every** build. The `android/` folder
      was confirmed 100% regenerable (App Links intent filter is in `app.json` `intentFilters`; Firebase
      config sourced from root `google-services.json`; `MainActivity`/`MainApplication` are unmodified
      boilerplate; no hand-edits after prebuild). Confirmed: project upload **681MB → 96MB**, build
      emitted a single `app-debug.apk`, installs cleanly. Firebase `google-services.json` lives at the
      **mobile root** (not in `android/`), so it survives the deletion.
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
  - [x] **`office_slug` added to `/staff/resolve-client-qr` per-doc response** (prerequisite for the
    mobile intake "Receive & Route" handler-picker). The resolve response returned the office display
    name (`target_office_name` / `pending_at_office`) but not the slug the picker needs to call
    `GET /offices/{slug}/staff`. Added `office_slug` per doc, sourced directly from the doc's stored
    `target_office_slug` (written at submit time by both `/client/submit` paths) — **not** a new
    slugify and **not** a name→slug lookup, so it matches stored slugs exactly. Note: the existing
    scanner forward flow does not itself resolve a slug (it transfers to a known `intended_for_username`);
    the reusable slug→staff pattern is submit.tsx reading `office_slug` directly. Response shape
    otherwise unchanged. Baseline held: 14 failed / 377 passed / 1 skipped.
  - [x] **Mobile intake "Receive & Route" — routing is now mandatory at intake.** The client-QR batch
    modal no longer offers accept-without-routing: the intake/primary recipient is pure intake
    (receives, routes, releases) and always hands each doc onward to a handling staff member. Per-doc
    **Receive & Route** opens a staff picker built from the doc's `office_slug` →
    `GET /offices/{slug}/staff` and fires `POST /documents/{id}/transfer` (the existing atomic
    receive+forward). **Route all to one handler** routes a whole same-office batch in one pass,
    **guarded against mixed-office batches** (offered only when every doc shares one office slug).
    Routed docs leave the list; an empty list means everything was received and routed. **Self-routing
    is blocked at BOTH layers:** the UI filters the caller out of the handler options (filtered at
    render, not in the shared `['office-staff', slug]` queryFn, so submit.tsx's cache stays unfiltered),
    and the mobile `/transfer` endpoint now rejects `to_staff == self` before any state change —
    mirroring the web guard (`routes/dashboard.py:1101`) and closing a mobile/web inconsistency where a
    self-route was a silent no-op that vanished the doc from the list as if handled. Completes the
    tracked custody chain: client submit → intake receives+routes → handler, every hop logged in
    `travel_log`. `tsc --noEmit` unchanged (7 pre-existing, 0 new). Baseline held: 14 failed / 377
    passed / 1 skipped. **Not yet device-tested.**

- [ ] **Release-to-client** (digitize the logbook "pull-out": a collector — often NOT the submitter, a
  favor-doer — collects a finished document; staff logs who took it).
  - [x] Server: `document_releases` table + `POST /documents/{id}/release-to-client`. Group-gated
    (staff must be in the office's primary group — release is NEVER client-triggered, closing the
    false-custody hole). Soft warning (409 `requires_confirm`) if the doc looks mid-process; staff can
    override; staff judgment + the release log are the accountability control (no ready-for-pickup state
    yet — deferred). Logs collector name/username/origin/office/position/contact (name required;
    office/position/origin TYPED for now, auto-fill from expanded profile is a later arc), `released_by`
    staff, timestamp; appends timeline "Released to {name} of {origin} by {staff}". Baseline held:
    14 failed / 377 passed / 1 skipped. **Not yet device-tested.**
  - [x] Server: `POST /staff/resolve-collector-identity` (`@jwt_staff_required`) — resolves a
    collector's `CLI-` QR token to identity ONLY (`username`, `full_name`, `email`/`phone` if present
    on the client record), NOT pending docs (distinct from `/staff/resolve-client-qr`, the receive
    flow, which is unchanged). Prerequisite for the mobile release form's collector auto-fill. Contact
    fields may be blank (thin client profile) — the form pre-fills what exists, staff types the rest.
    Baseline held: 14 failed / 377 passed / 1 skipped.
  - [x] Mobile: scan doc QR → capture collector (scan collector QR or type) → release. The scanned-doc
    overlay became the action hub for ANY resolved doc (not just pending-incoming), since a finished
    doc being released is not pending — Release was otherwise unreachable; deliberate behavior change,
    replaces the old auto-navigate-to-detail for non-receivable docs. "Release to Collector" opens a
    collector-capture form with QR auto-fill via `/staff/resolve-collector-identity`; submit handles
    201 / 409-override / 403 / error. tsc 7 pre-existing, 0 new. **Not yet device-tested.**
  - [x] Bug closed along the way — **scanner writes left the mobile detail screen stale.** Six
    document-mutating scanner handlers invalidated `['documents']`/`['pending-*']`/`['stats']` but never
    the detail key `['document', <id>]`, and the detail query inherits a 5-min global staleTime +
    offlineFirst persisted cache — so opening a just-released/accepted/routed doc showed pre-write data.
    Fix: each handler now also invalidates the `['document']` prefix (matches every detail entry).
    `handleForwardTransfer` additionally gained list invalidation it never had. What turned out true:
    the release build didn't introduce the staleness — it exposed a pre-existing gap shared by
    accept/route/reject/slip-route/forward.
  - [x] Bug closed along the way — **Receive & Route never recorded intake's receipt (custody hole).**
    `POST /documents/<id>/transfer` wrote only the OUTGOING leg, so a client-submitted doc routed via
    mobile Receive & Route jumped from client→intake-pending straight to intake→handler-pending with no
    intake receipt ever written (no `status='Received'`, no `date_received`/`accepted_by`, no timeline
    entry), leaving it perpetually `transfer_status='pending'` and throwing a bogus 409 "still pending"
    on later release. Fix: `api_transfer_document` now settles the caller's receipt BEFORE the outgoing
    leg, gated on `transfer_status=='pending' AND pending_at_staff==caller`, mirroring
    `api_accept_document` (receipt timeline entry, `date_received`, `accepted_by`,
    `logged_by`/`logged_by_office` ownership so intake retains dashboard visibility through routing) in
    one atomic `save_doc`. What turned out true: the gate is provably safe because Accept flips
    `transfer_status` to `'accepted'`, so an already-accepted doc routed onward never re-settles — no
    phantom second receipt. Baseline held: 14 failed / 377 passed / 1 skipped.
  - [ ] (future) Expand client registration/profile to store office/position/origin so collector QR
    auto-fills them
  - [ ] (future) "Ready for pickup" state so release is gated on finished-ness, not just staff judgment
  - **Open follow-ups (as of prod deploy 9d81de0):**
    - [ ] VERIFY (partial): receipt-settle on prod. Case 1 VERIFIED — doc test3/REF-2026-D306 shows a
      "Document Accepted" travel_log entry, `logged_by=paulpiniano`, and web-dashboard visibility while
      pending onward. Case 2 (already-accepted doc routed onward → NO second receipt) STILL unverified.
      Restore point: `doctrack-prereceipt-20260805_205325.sql.gz`.
    - [x] Naming/consistency: inside-office moves now read "Transfer" throughout the mobile scanner
      intake flow. What turned out true: `transfer_type` was already hardcoded `'inside_office'` (=
      server "Transferred"), so this was a pure string rename — no payload/semantics change. Routing-slip
      feature (distinct QR type) keeps its own "routing" wording.
    - [x] Intended-For auto-route: per-doc button is now "Receive & Transfer → {name}" and routes
      directly. What turned out true: `intended_for_username` already rode on each doc from
      resolve-client-qr, so this was pure mobile-side — pre-validation against the office staff list
      (prefetched on sheet render), self-transfer guard (falls back to picker), stale-handler fallback
      (⚠️ note), and a "Choose someone else" override. Server self-transfer guard unchanged.
    - [x] DONE: pending_at_staff_name staleness on the API transfer/accept path. Pre-existing (April–May
      2026, not from af44af5); surfaced by the release 409 naming the wrong person (showed Paul when doc
      was pending with Loralyn). Fixed forward: api_transfer_document now writes
      `pending_at_staff_name=recipient_full_name` (matching web path); api_accept_document now clears
      `pending_at_staff`/`pending_at_staff_name`/`pending_at_office` (doc is Received, no pending target).
      Verified: no display site reads pending_at_* on a Received doc (all gate on status=='Pending').
    - [x] DONE: web pending-leg-ending paths now clear pending_at_staff_name, matching the API fix
      (6a8c8fc). accept_document (dashboard.py:~1826) cleared staff/office but left the name; the same
      pass also fixed reject_document (:~1922, same omission) and release_doc (:~1305, which didn't
      touch pending_at_* at all — a doc CAN reach release with live pending fields since logged_by
      only moves to the recipient on accept). Ordering verified on all three: nothing reads these to
      build a persisted value after the clear point.
    - [x] DONE-BY-INVESTIGATION: backfill existing docs whose stored pending_at_staff_name drifted from
      pending_at_staff. Diagnostic run on prod (8,008 pending docs) found ZERO drifted-and-resolvable
      still-pending docs and ZERO unresolvable usernames. The forward fix (6a8c8fc) prevents new drift;
      no existing still-pending doc carries a stale pending_at_staff_name. No backfill needed — not
      written, not run. Multi-transfer-while-pending drift (which bit test3) has no live instances in
      current data.
    - [x] DONE-BY-INVESTIGATION: accepted-doc cleanup (accepted before the clear-fix, still carrying
      non-empty pending_at_* fields). Diagnostic found exactly 1 accepted doc with stale non-empty
      pending fields. Count=1, nothing reads pending_at_* on a Received doc, so left as-is; the
      accept-clear fix (6a8c8fc) prevents new ones. Not worth a cleanup pass.
    - [ ] Mobile release flow: happy path + 409-override device-tested; NOT re-tested since cache-fix
      and receipt-settle landed. Full re-test outstanding.
    - [ ] ExpoSQLite native-module crash seen in dev logs (dev-client/build mismatch) — blocks
      dev-client launch; unrelated to scanner changes. Triage separately.
    - [x] DONE: client contact-leak fix (server half / Commit A). collector_contact was baked into the
      release travel_log remark text (api.py:1794) and the mobile client rendered it via the RAW staff
      endpoint GET /documents/<id> (which returns the full serialized doc to any owning client). Fixed:
      (1) dropped the contact fragment from the release remark; (2) added GET /client/documents/<id> — a
      client-safe endpoint composing build_client_track_view + explicit-whitelist document/release blocks
      (NEVER collector_contact, never raw remarks/officer, never serialize(doc)); (3) added ownership gate
      to /qr/generate/<id> (was @jwt_required with NO ownership check — any user could QR any doc).
      Regression tests added (TestClientDocEndpoint, TestQrOwnershipGate) — the contact-absence test
      asserts the value appears NOWHERE in the payload and was proven to fail on a deliberate re-leak.
      pytest 14/383/1.
    - [x] DONE: Commit B (mobile) — mobile client track screen now consumes GET /client/documents/<id>
      (was the raw staff GET /documents/<id>). History renders the sanitized {office,label,date} items
      (no raw remarks — entry.remarks is gone from the code); metadata reads the whitelisted `document`
      block (remarks/notes/description rows dropped); a release card shows collector identity
      (name/origin/office/position/date/releasing-staff) with NO contact field. Closes the DISPLAY leak
      on EXISTING docs (e.g. test3) whose stored remarks still contain contact — no data scrub needed.
      tsc: 7 pre-existing errors, 0 new (none in the touched file). Awaiting device test before deploy.
    - [x] DONE: client history enrichment — server (Step 1). The post-leak sanitizer had over-reduced
      history to generic bucket labels, hiding legitimate journey info. `_build_history` now emits, per
      movement, the unchanged collapsed {office, label, date} PLUS a nested detail:{label, office,
      officer_name, date_time} for tap-to-expand. Office stays visible in the collapsed label; the staff
      name lands ONLY in detail.officer_name (resolved username→full-name via the user-map). Raw remarks
      and the raw action string are STILL never surfaced anywhere including inside detail — only the
      bucketed label is used. Additive/backward-compatible: web + mobile ignore the new detail key until
      the expand-UI is built. Tests: rewrote the history privacy test for the new rule + added a
      raw-action-not-surfaced test; TestClientDocEndpoint passes unchanged. pytest 14/384/1.
    - [x] DONE: client history enrichment — server, richer labels + actor role + transient recipient.
      Builds on Step 1. `_classify` now emits SPECIFIC labels ("Transferred — Inside Office" /
      "Forwarded — Another Office" split from one generic bucket; "Released to collector" vs "Released
      from the office"; plus received/rejected/hold/logged/edited) — all from safe action substrings,
      never echoing raw text. detail gains `actor_role` (fixed vocabulary — "Received by"/"Sent by"/
      "Released by"/etc., never free text) and a transient `recipient_name` on the LATEST transfer entry
      only, sourced from doc.pending_at_staff_name (a resolved staff name — never referred_to/free-text,
      never contact). Collector-release detection uses the "Released to…by" shape and is robust to
      collector origin being optional (origin-less collector releases were previously mislabeled as plain
      office releases; the earlier " of … by " pattern missed them). Confirmed "Released by Originating
      Staff" (has " by " but no "released to ") is NOT mislabeled. Display-layer only, no write-path
      change; client_view stays pure (no DB import). Remaining: mobile render of the enriched shape (Step
      2 below). NOTE: collector ORIGIN is optional on all release surfaces (server, mobile, web) — a
      candidate future improvement is making it required, which would also improve release-record
      completeness. pytest 14/388/1.
    - [x] DONE: client history enrichment — Step 2 (mobile render). The mobile client track screen
      ([mobile/app/(client)/track/[id].tsx](mobile/app/(client)/track/[id].tsx)) now renders the enriched
      shape: specific labels in the timeline; tap-to-expand shows "{actor_role} {officer_name}" (Received
      by / Sent by / Released by…), a transient "Sent to {recipient_name}" on the latest transfer, and the
      date/time. Full collector detail (name/origin/office/position, released-by, date) is folded INTO the
      "Released to collector" entry's expand — the standalone release card was removed for one unified
      timeline. Collector data comes from the endpoint's already-safe `release` block (no contact field
      exists); the release entry is matched by the server-produced label, never by re-parsing raw strings
      on the client. No contact anywhere. Closes the client history enrichment thread AND the broader
      contact-leak privacy arc. tsc: 0 new errors (7 pre-existing, none in track/[id].tsx).
    - [ ] (optional) client history enrichment — Step 3 (web expand UI). client_track.html could grow a
      matching tap/click-to-expand for `detail`; currently the web template just ignores the new key.
      Nice-to-have, not required for the mobile enrichment to land.
    - [ ] TODO: staff scanner offers "Release to Collector" on an ALREADY-RELEASED doc. Scanning a doc
      with status=Released still shows the release action in the scanned-doc overlay (mobile scanner).
      Should suppress/disable release when the doc is already Released (status=='Released' or
      transfer_status=='released') to prevent a duplicate document_releases row + duplicate timeline
      entry. Investigate: where the overlay decides which actions to show (scanner.tsx scanned-doc
      overlay), and whether the SERVER should also reject a re-release (defense in depth — the UI guard
      is convenience, the server should refuse releasing an already-released doc). Likely both: hide the
      button AND have api_release_to_client reject if already released.

- [ ] **Maintenance mode (admin toggle).** A switch the admin flips to show an "under maintenance"
  screen to everyone accessing DocTracker, with an ON indicator in the admin UI. Scope decided: blocks
  **EVERYTHING** (staff web, client portal, mobile API) — admins **ALWAYS** exempt. Design constraints
  already worked out (must honor when built):
  1. **NEVER lock the admin out** — the maintenance guard must exempt admin sessions AND the login
     route, or flipping it on bricks access to turn it off. This is the #1 rule.
  2. **State must be DB-backed or file-backed, NOT an in-memory flag** — multi-worker gunicorn would
     leave the flag inconsistent across workers (same reason as rate-limiting/job-state).
  3. **Enforce via a `before_request` hook** (same layer as the CSRF guard), short-circuiting to the
     maintenance response UNLESS admin or an exempt route.
  4. **Mobile API must return a JSON 503** (not an HTML maintenance page) so the app can handle it
     gracefully — an HTML body would break the app ugly. **Hard requirement:** the mobile API must
     never receive an HTML maintenance page. The mobile app may need matching "under maintenance"
     handling for that 503 (mobile-side follow-up).
  5. **Server-side enforcement, not a client-hidden banner** — the block is real; the banner is just
     the visible signal.
  Attach point TBD: `before_request` in [app.py](app.py) near the CSRF guard; admin toggle in the admin
  blueprint; state in a small settings table or a file like the webhook secrets.

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

- [x] **~~`rename_user` missed 3 username-bearing columns — one caused silent document misrouting.~~**
  A column-by-column audit (prompted by live device testing of the client-QR receive feature) found
  `rename_user` ([services/auth.py](services/auth.py)) rewrote ~15 surfaces but **missed three**:
  `saved_offices.primary_recipient`, `client_qr_tokens.username`, and `password_reset_tokens.username`.
  **The real bug was `saved_offices.primary_recipient`** — an office's default receiving-staff username.
  When a primary recipient was renamed, the office kept pointing at the **dead** old username, so mobile
  submissions matched nobody at Tier 1/2 and **silently fell through to the Tier-3 "first staff"
  fallback → documents routed to the WRONG person, with no error**. Only masked in the field because
  the affected office had been manually re-saved with the new name.
  **Two audit-claimed misses were false** and were NOT touched: `push_tokens.username` was already
  covered ([auth.py](services/auth.py), DELETE-then-UPDATE PK-safe), and `staff_pairings` has **no
  username columns** (keys on `user_a`/`user_b`) — an `UPDATE staff_pairings SET staff_username=…`
  would have raised "column does not exist" and aborted the whole rename transaction.
  **Fix:** rewrite all three in the DB path; the JSON path had the **same asymmetry** (`created_by`
  covered, `primary_recipient` missed) and is now symmetric. Added a regression test
  ([tests/test_rename_user.py](tests/test_rename_user.py)) asserting `saved_offices` rewrites **both**
  `created_by` and `primary_recipient` together. The two token columns are covered by the DB path but
  are **not reachable by the JSON test harness** (their JSON stores are dict-keyed-by-token with
  `username` as a sub-value) — documented in-code and in the test as an honest limitation, not
  fabricated coverage. Baseline held: 14 failed / 377 passed / 1 skipped.

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

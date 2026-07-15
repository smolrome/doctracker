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

- **14 pre-existing test failures — all stale tests, not product bugs.** Baseline is
  `14 failed, 313 passed, 1 skipped`. Two independent root causes, both "the code moved on and the
  tests didn't":

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

  **Until these are fixed, `pytest` is not a clean pass/fail signal** — you must compare against the
  14/313/1 baseline, which is exactly the kind of thing that hides a real regression. Worth fixing for
  that reason alone.

- **Rebrand to `DOCKET` is half-applied, and the rest of it must NOT be finished blindly.**
  `APP_NAME = "DOCKET"` ([config.py:109](config.py:109)) covers web templates, but `LAKAD` remains in:
  backup metadata (**load-bearing — see CLAUDE.md invariants, do not change**), the console banner
  ([app.py:605](app.py:605)), password-reset email copy
  ([routes/auth.py:281-298](routes/auth.py:281)), and an API notification string
  ([blueprints/api.py:3003](blueprints/api.py:3003)). The email/banner ones are safe to update; the
  backup ones are not. Anyone doing a blanket find-and-replace will break backup recognition.

- **In-memory rate limiting is per-process and leaks under multi-worker gunicorn.**
  `RATE_LIMITS` ([config.py](config.py)) is in-memory, and production runs `--workers 4`, so the
  effective limit is up to 4× the configured one. Already known and worked around for password reset
  (which uses a DB-backed limiter — see `PASSWORD_RESET_RATE_LIMITS`), but **login, register,
  status_update, doc_create, and api limits are still in-memory** and therefore still 4×-able.

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

"""
routes/auth.py — Login, logout, register, and session management routes.
"""
import re
import time

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from services.auth import (
    check_rate_limit, create_user, reset_rate_limit,
    update_last_login, verify_user,
)
from services.email import validate_invite_token, consume_invite_token
from services.misc import audit_log, save_office
from utils import get_client_ip, is_logged_in

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if is_logged_in():
        return redirect(url_for("dashboard.index"))
    error = None
    lockout_remaining = 0
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        ip = get_client_ip()
        allowed, wait = check_rate_limit("login", f"{ip}:{username.lower()}")
        if not allowed:
            mins = max(1, wait // 60)
            error = f"Too many failed attempts. Try again in {mins} minute{'s' if mins != 1 else ''}."
            lockout_remaining = wait
            audit_log("login_blocked", f"username={username}",
                      username=username, ip=ip)
        else:
            full_name, role, office = verify_user(username, password)
            if full_name:
                reset_rate_limit("login", f"{ip}:{username.lower()}")
                session.clear()
                session.update({
                    "logged_in":   True,
                    "username":    username.lower().strip(),
                    "full_name":   full_name,
                    "role":        role,
                    "office":      office,
                    "last_active": time.time(),
                })
                session.permanent = True
                update_last_login(username.lower().strip())
                audit_log("login_ok", f"role={role}",
                          username=username, ip=ip)
                if role == "client":
                    return redirect(url_for("client.portal"))
                next_raw = request.args.get("next", "")
                # Open redirect protection: only allow relative paths
                from urllib.parse import urlparse
                parsed = urlparse(next_raw)
                if next_raw and not parsed.scheme and not parsed.netloc and next_raw.startswith("/"):
                    next_url = next_raw
                else:
                    next_url = url_for("dashboard.index")
                flash(f"Welcome, {full_name}!", "success")
                return redirect(next_url)
            else:
                error = "Invalid username or password."
                audit_log("login_fail", f"username={username}",
                          username=username, ip=ip)
    return render_template("login.html", error=error,
                           lockout_remaining=lockout_remaining)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if is_logged_in():
        return redirect(url_for("dashboard.index"))

    token = request.args.get("token") or request.form.get("token", "")

    print(f"[REGISTER] ===== method={request.method} =====")
    print(f"[REGISTER] token present: {bool(token)} | token prefix: {token[:12] if token else 'NONE'}")

    token_email, token_name = (None, None)
    if token:
        try:
            token_email, token_name = validate_invite_token(token)
            print(f"[REGISTER] validate_invite_token → email={token_email!r} name={token_name!r}")
        except Exception as e:
            print(f"[REGISTER] validate_invite_token EXCEPTION: {type(e).__name__}: {e}")

    token_valid = bool(token_email)
    print(f"[REGISTER] token_valid={token_valid}")
    error = None

    if request.method == "POST":
        print(f"[REGISTER] POST fields: username={request.form.get('username','')!r} office={request.form.get('office','')!r} full_name={request.form.get('full_name','')!r}")

        if not token_valid:
            error = "Invalid or expired invite link. Please ask the admin for a new one."
            print(f"[REGISTER] BLOCKED — token_valid=False")
        else:
            username  = request.form.get("username", "").strip()
            full_name = request.form.get("full_name", "").strip()
            password  = request.form.get("password", "").strip()
            confirm   = request.form.get("confirm_password", "").strip()
            office    = request.form.get("office", "").strip()

            print(f"[REGISTER] Validating: username={username!r} office={office!r} pw_len={len(password)}")

            if not username or not password:
                error = "Username and password are required."
                print(f"[REGISTER] FAIL — missing username/password")
            elif not office:
                error = "Please enter your office or unit name."
                print(f"[REGISTER] FAIL — missing office")
            elif len(password) < 8:
                error = "Password must be at least 8 characters."
                print(f"[REGISTER] FAIL — password too short")
            elif not re.search(r'[0-9]', password):
                error = "Password must contain at least one number."
                print(f"[REGISTER] FAIL — password missing number")
            elif not re.search(r'[A-Z]', password):
                error = "Password must contain at least one uppercase letter."
                print(f"[REGISTER] FAIL — password missing uppercase")
            elif not re.search(r'[^A-Za-z0-9]', password):
                error = "Password must contain at least one special character (e.g. @, #, !, %)."
                print(f"[REGISTER] FAIL — password missing special char")
            elif password != confirm:
                error = "Passwords do not match."
                print(f"[REGISTER] FAIL — passwords do not match")
            else:
                print(f"[REGISTER] Calling create_user({username!r}, role=staff, office={office!r})")
                ok, err = create_user(username, password, full_name or token_name,
                                      office=office)
                print(f"[REGISTER] create_user result → ok={ok}, err={err!r}")
                if ok:
                    print(f"[REGISTER] SUCCESS — consuming token and saving office")
                    consume_invite_token(token)
                    save_office(office, username)
                    audit_log("staff_registered", f"username={username} office={office}",
                              username=username, ip=get_client_ip())
                    flash(
                        f"Account created! Your office '{office}' QR code has been generated automatically.",
                        "success"
                    )
                    print(f"[REGISTER] Done — redirecting to login")
                    return redirect(url_for("auth.login"))
                else:
                    error = err
                    print(f"[REGISTER] create_user FAILED: {err!r}")

    print(f"[REGISTER] Rendering form — error={error!r} token_valid={token_valid}")
    return render_template("register.html", error=error, token=token,
                           token_valid=token_valid,
                           token_email=token_email,
                           token_name=token_name)


@auth_bp.route("/logout")
def logout():
    audit_log("logout", "", username=session.get("username", "anonymous"),
              ip=get_client_ip())
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("dashboard.index"))
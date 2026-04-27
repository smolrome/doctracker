"""
routes/auth.py — Login, logout, register, and session management routes.
"""
import re
import time

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from services.auth import (
    check_rate_limit, create_user, get_user, reset_rate_limit,
    update_last_login, update_user, update_user_password, verify_password, verify_user,
)
from services.email import validate_invite_token, consume_invite_token
from services.misc import audit_log, load_saved_offices, save_office
from services.cart_store import save_cart, load_cart, clear_cart
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
                clean_username = username.lower().strip()
                saved_cart = load_cart(clean_username)
                session.clear()
                session.update({
                    "logged_in":   True,
                    "username":    clean_username,
                    "full_name":   full_name,
                    "role":        role,
                    "office":      office,
                    "last_active": time.time(),
                })
                if saved_cart:
                    session["staff_cart"] = saved_cart
                session.permanent = True
                update_last_login(clean_username)
                audit_log("login_ok", f"role={role}",
                          username=username, ip=ip)
                if role == "client":
                    return redirect(url_for("client.portal"))
                next_raw = request.args.get("next", "")
                from urllib.parse import urlparse
                parsed = urlparse(next_raw)
                if next_raw and not parsed.scheme and not parsed.netloc and next_raw.startswith("/"):
                    next_url = next_raw
                else:
                    next_url = url_for("dashboard.index")
                flash(f"Welcome, {full_name}!", "success")
                if saved_cart:
                    flash(f"📋 Your previous cart with {len(saved_cart)} unsaved document{'s' if len(saved_cart) != 1 else ''} has been restored.", "info")
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

    token_email, token_name = (None, None)
    if token:
        try:
            token_email, token_name = validate_invite_token(token)
        except Exception:
            pass

    token_valid = bool(token_email)
    error = None

    # Load existing offices for dropdown
    existing_offices = []
    if token_valid:
        try:
            existing_offices = load_saved_offices()
            # If no saved offices, auto-build from users' office field
            if not existing_offices:
                from services.auth import get_all_users
                all_users = get_all_users()
                seen = set()
                for u in all_users:
                    o = (u.get('office') or '').strip()
                    if o and o not in seen:
                        seen.add(o)
                        existing_offices.append({'office_name': o, 'office_slug': o})
        except Exception:
            pass

    if request.method == "POST":
        if not token_valid:
            error = "Invalid or expired invite link. Please ask the admin for a new one."
        else:
            username  = request.form.get("username", "").strip()
            full_name = request.form.get("full_name", "").strip()
            password  = request.form.get("password", "").strip()
            confirm   = request.form.get("confirm_password", "").strip()
            office    = request.form.get("office", "").strip()

            if not username or not password:
                error = "Username and password are required."
            elif not office:
                error = "Please enter your office or unit name."
            elif len(password) < 8:
                error = "Password must be at least 8 characters."
            elif not re.search(r'[0-9]', password):
                error = "Password must contain at least one number."
            elif password != confirm:
                error = "Passwords do not match."
            else:
                ok, err = create_user(username, password, full_name or token_name,
                                      office=office)
                if ok:
                    consume_invite_token(token)

                    # Check if office already exists - only create QR if new
                    office_exists = False
                    matched_office_name = None
                    try:
                        saved_offices = load_saved_offices()
                        office_slug = re.sub(r'\s+', '-', office.strip().lower())
                        for saved in saved_offices:
                            if saved.get('office_slug') == office_slug:
                                office_exists = True
                                matched_office_name = saved.get('office_name', office)
                                break
                    except Exception:
                        pass

                    if not office_exists:
                        save_office(office, username)
                        flash(
                            f"Account created! Your office '{office}' QR code has been generated automatically.",
                            "success"
                        )
                    else:
                        flash(
                            f"Account created! You've been assigned to the existing office '{matched_office_name or office}'.",
                            "success"
                        )
                    return redirect(url_for("auth.login"))
                else:
                    error = err

    return render_template("register.html", error=error, token=token,
                           token_valid=token_valid,
                           token_email=token_email,
                           token_name=token_name,
                           existing_offices=existing_offices)


@auth_bp.route("/logout")
def logout():
    username = session.get("username", "")
    audit_log("logout", "", username=username or "anonymous", ip=get_client_ip())
    staff_cart = session.get("staff_cart", [])
    if staff_cart and username:
        save_cart(username, staff_cart)
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("dashboard.index"))


@auth_bp.route("/profile", methods=["GET", "POST"])
def profile():
    if not is_logged_in():
        return redirect(url_for("auth.login"))

    username = session.get("username")
    user = get_user(username)
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("dashboard.index"))

    errors = {}
    success_msg = None

    if request.method == "POST":
        section = request.form.get("_section", "info")

        if section == "info":
            full_name = request.form.get("full_name", "").strip()
            office    = request.form.get("office", "").strip()
            if not full_name:
                errors["full_name"] = "Display name is required."
            if not office:
                errors["office"] = "Office is required."
            if not errors:
                ok, err = update_user(username, full_name=full_name, office=office)
                if ok:
                    session["full_name"] = full_name
                    session["office"]    = office
                    session.modified     = True
                    audit_log("profile_updated", f"full_name={full_name}",
                              username=username, ip=get_client_ip())
                    flash("Profile updated successfully.", "success")
                else:
                    errors["general"] = err or "Could not update profile."

        elif section == "password":
            current_pw  = request.form.get("current_password", "")
            new_pw      = request.form.get("new_password", "").strip()
            confirm_pw  = request.form.get("confirm_password", "").strip()
            # re-fetch with hash for verification
            from services.auth import _load_users_json, USE_DB
            stored_hash = ""
            if USE_DB:
                from services.database import get_conn
                try:
                    with get_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute("SELECT password_hash FROM users WHERE username=%s", (username,))
                            row = cur.fetchone()
                            if row:
                                stored_hash = row["password_hash"]
                except Exception:
                    pass
            else:
                for u in _load_users_json():
                    if u["username"] == username:
                        stored_hash = u.get("password_hash", "")
                        break
            if not verify_password(current_pw, stored_hash):
                errors["current_password"] = "Current password is incorrect."
            elif len(new_pw) < 8:
                errors["new_password"] = "New password must be at least 8 characters."
            elif not any(c.isdigit() for c in new_pw):
                errors["new_password"] = "New password must contain at least one number."
            elif new_pw != confirm_pw:
                errors["confirm_password"] = "Passwords do not match."
            if not errors:
                ok, err = update_user_password(username, new_pw)
                if ok:
                    audit_log("password_changed", "", username=username, ip=get_client_ip())
                    flash("Password changed successfully.", "success")
                else:
                    errors["new_password"] = err or "Could not change password."

        user = get_user(username)
        if not errors:
            return redirect(url_for("auth.profile"))

    return render_template("profile.html", user=user, errors=errors)
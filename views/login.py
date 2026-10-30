"""Log-in page: email or mobile number plus password. "Forgot password?" resets it with a 6-digit code emailed to the person."""
import streamlit as st

import auth
import ui

ui.inject_css()
ui.hero("Welcome back", "One login for everyone: renters, owners and administrators.")

user = auth.current_user()
if user:
    st.success(f"You are signed in as {user['full_name']}.")
    ui.link("views/browse.py", "Find a flat", "🔎")
    if auth.is_admin(user):
        ui.link("views/admin.py", "Admin", "🛡️")
    st.stop()

def _clear_reset():
    for k in ("reset_email", "reset_msg", "reset_demo_code", "reset_mode"):
        st.session_state.pop(k, None)


_, mid, _ = st.columns([1, 2, 1])
with mid:
    if st.session_state.get("reset_done"):
        st.success(st.session_state.pop("reset_done"))

    if st.session_state.get("reset_mode") and not st.session_state.get("reset_email"):
        # ---- forgot password, step 1: ask for the email
        st.subheader("Forgot your password?")
        st.caption("Enter the email you signed up with. We will email you a 6-digit code.")
        with st.form("reset_request_form"):
            r_email = st.text_input("Email")
            send = st.form_submit_button("Send code", type="primary")
        if send:
            ok, msg, demo = auth.request_password_reset(r_email)
            if not ok:
                st.error(msg)
            else:
                st.session_state["reset_email"] = auth.normalize_email(r_email)
                st.session_state["reset_msg"] = msg
                st.session_state["reset_demo_code"] = demo
                st.rerun()
        if st.button("Back to log in"):
            _clear_reset()
            st.rerun()

    elif st.session_state.get("reset_email"):
        # ---- forgot password, step 2: code + new password
        r_email = st.session_state["reset_email"]
        st.subheader("Set a new password")
        st.info(st.session_state.get("reset_msg", auth.RESET_SENT))
        if st.session_state.get("reset_demo_code"):
            st.warning(f"Demo code: **{st.session_state['reset_demo_code']}**")
        with st.form("reset_confirm_form"):
            code = st.text_input("6-digit code", max_chars=6, placeholder="123456")
            p1 = st.text_input("New password", type="password", help="At least 8 characters, with letters and numbers.")
            p2 = st.text_input("Repeat new password", type="password")
            save = st.form_submit_button("Change password", type="primary")
        if save:
            ok, msg = auth.reset_password(r_email, code, p1, p2)
            if ok:
                _clear_reset()
                st.session_state["reset_done"] = msg
                st.rerun()
            else:
                st.error(msg)
        b1, b2 = st.columns(2)
        if b1.button("Resend code"):
            ok, msg, demo = auth.request_password_reset(r_email)
            if ok:
                st.session_state["reset_msg"] = msg
                st.session_state["reset_demo_code"] = demo
                st.rerun()
            else:
                st.error(msg)
        if b2.button("Use a different email"):
            st.session_state.pop("reset_email", None)
            st.session_state.pop("reset_demo_code", None)
            st.rerun()

    else:
        with st.form("login_form"):
            who = st.text_input("Email or mobile number")
            password = st.text_input("Password", type="password")
            go = st.form_submit_button("Log in", type="primary")
        if go:
            found, msg = auth.authenticate(who, password)
            if found is None:
                st.error(msg)
            else:
                auth.login(found)
                # The menu was built for a visitor and has no Browse page yet. Rerun first, so app.py builds the
                # full menu for this person, then app.py opens the right page (see "after_login" there).
                st.session_state["after_login"] = "admin" if found["role"] == auth.ADMIN else "browse"
                st.rerun()
        if st.button("Forgot password?"):
            st.session_state["reset_mode"] = True
            st.rerun()
        st.write("New here?")
        ui.link("views/signup.py", "Create an account", "➕")

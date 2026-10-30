"""Sign-up page: create an account as a renter or an owner."""
import streamlit as st

import auth
import ui

ui.inject_css()
ui.hero("Create your account", "Renters search and find a flat that fits their preferences. Owners list flats for rent.")

user = auth.current_user()
if user:
    if st.session_state.get("signup_welcome") == user["user_id"]:   # just signed up in this session
        st.success(f"Welcome, {user['full_name']}. Your email is verified and your account is ready.")
    else:
        st.success(f"You are already signed in as {user['full_name']}.")
    ui.link("views/browse.py", "Find a flat", "🔎")
    if user["role"] == "owner":
        ui.link("views/list_flat.py", "List your flat", "➕")
    st.stop()

form_col = st.container()

def _already_exists(email):
    """This email already has an account: drop the code form and show a clean "please log in" screen."""
    st.session_state.pop("signup_pending", None)
    st.session_state.pop("signup_demo_code", None)
    st.session_state.pop("signup_verified", None)
    st.session_state["signup_existing"] = email
    st.rerun()


def _finish(p):
    """Create the account after the email code is right."""
    role = p["role"]
    try:
        uid = auth.create_user(p["full_name"], p["email"], p["phone"], p["password"], role, email_verified=True)
    except ValueError as e:
        if auth._find(p["email"]):
            _already_exists(p["email"])
        st.error(str(e))
        return
    auth.save_interests(uid, **p.get("interests", {}))
    st.session_state.pop("signup_pending", None)
    st.session_state.pop("signup_demo_code", None)
    st.session_state.pop("signup_verified", None)
    auth.login({"full_name": p["full_name"], "email": p["email"], "phone": p["phone"],
                "user_id": uid, "role": role, "created_at": ""})
    st.session_state["signup_welcome"] = uid
    # The Sign up page is not in a logged-in person's menu, so app.py sends them to Home once, and Home
    # shows the "account created" message.
    st.session_state["account_created"] = p["full_name"]
    st.session_state["goto_home_once"] = True
    st.rerun()


with form_col:
    pending = st.session_state.get("signup_pending")
    if pending is None:
        # ---- step 1: details
        existing = st.session_state.pop("signup_existing", None)
        if existing:
            st.success(f"An account with {existing} already exists. Please log in with your password, "
                       "or sign up below with a different email and mobile number.")
            ui.link("views/login.py", "Log in", "🔑")
        with st.form("signup_form"):
            name = st.text_input("Full name", placeholder="Rahim Uddin")
            role_label = st.radio("I am a", list(auth.ROLES.values()), horizontal=True)
            c1, c2 = st.columns(2)
            email = c1.text_input("Email", placeholder="name@example.com", help="We send a 6-digit code here.")
            phone = c2.text_input("Mobile number", placeholder="01712345678")
            p1, p2 = st.columns(2)
            password = p1.text_input("Password", type="password", help="At least 8 characters, with letters and numbers.")
            password2 = p2.text_input("Repeat password", type="password")
            st.markdown("**Your interests** (optional, helps us show you what matters)")
            purposes = st.multiselect("What brings you here?", auth.PURPOSES)
            agree = st.checkbox("I agree that my name and contact details are stored to run my account. "
                                "Contact details are shown to others only if I choose that on my listing.")
            submitted = st.form_submit_button("Send verification code", type="primary")

        if submitted:
            errors, clean = auth.validate_signup(name, email, phone, password, password2, agree)
            if errors:
                for e in errors:
                    st.error(e)
            else:
                ok, msg, demo = auth.start_email_otp(clean["email"], reuse=True)
                if not ok:
                    st.error(msg)
                else:
                    role = next(k for k, v in auth.ROLES.items() if v == role_label)
                    st.session_state["signup_pending"] = {
                        **clean, "password": password, "role": role,
                        "interests": {"purposes": purposes}}
                    st.session_state["signup_demo_code"] = demo
                    st.session_state["signup_msg"] = msg
                    st.rerun()
    else:
        # ---- step 2: enter the code
        st.info(st.session_state.get("signup_msg", f"We sent a 6-digit code to {pending['email']}."))
        if st.session_state.get("signup_demo_code"):
            st.warning(f"Demo code: **{st.session_state['signup_demo_code']}**")
        with st.form("otp_form"):
            code = st.text_input("6-digit code", max_chars=6, placeholder="123456")
            verify = st.form_submit_button("Verify and create account", type="primary")
        if verify:
            # The code is used up the moment it is right. If the page is run twice (double click, slow
            # reply), the second run must not ask for the same code again, so remember that it was right.
            if st.session_state.get("signup_verified") == pending["email"]:
                ok, msg = True, ""
            else:
                ok, msg = auth.check_email_otp(pending["email"], code)
                if ok:
                    st.session_state["signup_verified"] = pending["email"]
            if ok:
                _finish(pending)
            elif auth._find(pending["email"]):
                _already_exists(pending["email"])
            else:
                st.error(msg)
        b1, b2 = st.columns(2)
        if b1.button("Resend code"):
            ok, msg, demo = auth.start_email_otp(pending["email"])
            if ok:
                st.session_state["signup_demo_code"] = demo
                st.session_state["signup_msg"] = msg
                st.rerun()
            else:
                st.error(msg)
        if b2.button("Change email / details"):
            st.session_state.pop("signup_pending", None)
            st.session_state.pop("signup_demo_code", None)
            st.rerun()

st.write("Already have an account?")
ui.link("views/login.py", "Log in", "🔑")

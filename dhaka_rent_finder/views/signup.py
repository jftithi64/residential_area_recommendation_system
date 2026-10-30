"""Sign-up page: create an account as a renter or an owner."""
import streamlit as st

import auth
import ui

ui.inject_css()
ui.hero("Create your account", "Save the flats you like, list your own, and manage your listings in one place.")

user = auth.current_user()
if user:
    st.success(f"You are already signed in as {user['full_name']}.")
    ui.link("views/find.py", "Find a flat", "🔎")
    st.stop()

form_col, info_col = st.columns([3, 2], gap="large")

with form_col:
    with st.form("signup_form"):
        name = st.text_input("Full name", placeholder="Rahim Uddin")
        role_label = st.radio("I am a", list(auth.ROLES.values()), horizontal=True)
        c1, c2 = st.columns(2)
        email = c1.text_input("Email", placeholder="name@example.com")
        phone = c2.text_input("Mobile number", placeholder="01712345678")
        p1, p2 = st.columns(2)
        password = p1.text_input("Password", type="password", help="At least 8 characters, with letters and numbers.")
        password2 = p2.text_input("Repeat password", type="password")
        agree = st.checkbox("I agree that my name and contact details are stored to run my account. "
                            "Contact details are shown to others only if I choose that on my listing.")
        submitted = st.form_submit_button("Create account", type="primary")

    if submitted:
        errors, clean = auth.validate_signup(name, email, phone, password, password2, agree)
        if errors:
            for e in errors:
                st.error(e)
        else:
            role = next(k for k, v in auth.ROLES.items() if v == role_label)
            try:
                uid = auth.create_user(clean["full_name"], clean["email"], clean["phone"], password, role)
            except ValueError as e:
                st.error(str(e))
            else:
                auth.login({**clean, "user_id": uid, "role": role, "created_at": ""})
                st.success(f"Welcome, {clean['full_name']}. Your account is ready.")
                ui.link("views/find.py", "Find a flat", "🔎")
                if role == "owner":
                    ui.link("views/list_flat.py", "List your flat", "➕")

with info_col:
    with st.container(border=True):
        st.subheader("What you can do")
        st.markdown(
            "- **Renters:** rank flats by fair rent and real road distance to your school or office.\n"
            "- **Owners:** list a flat and keep it fresh so renters trust it.\n"
            "- **Everyone:** manage your listings from one account.")
    st.write("Already have an account?")
    ui.link("views/login.py", "Log in", "🔑")

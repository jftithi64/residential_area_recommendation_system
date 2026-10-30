"""Menu rights: the admin chooses which pages a renter and an owner can see."""
import streamlit as st

import auth
import permissions
import ui

ui.inject_css()
ui.hero("Menu rights", "Choose which pages each type of account can see. Changes apply the next time they open the site.")

admin_user = auth.require_admin()

matrix = permissions.load_matrix()
labels = permissions.ROLE_NAMES

st.caption("Tick a box to give that kind of person the page. Administrators always see every page. "
           "Home, About and My account are always on. Admin, Insights and Menu rights are for administrators only. Visitors (not logged in) see only Home, Log in and Sign up; "
           "this cannot be changed. For renters and owners a switched-off page is hidden.")

head = st.columns([3] + [1.4] * len(permissions.ROLES))
head[0].markdown("**Page**")
for col, role in zip(head[1:], permissions.ROLES):
    col.markdown(f"**{labels[role]}**")

new = {role: {} for role in permissions.ROLES}
# Same order as the side menu: working pages, then the admin pages, then About and My account.
_first = [k for k in permissions.PAGES if k not in ("about", "account")]
for key in _first + list(permissions.ADMIN_PAGES) + ["about", "account"]:
    row = st.columns([3] + [1.4] * len(permissions.ROLES))
    if key in permissions.ADMIN_PAGES:      # admin-only pages: shown, but nobody else can get them
        _file, title, icon = permissions.ADMIN_PAGES[key]
        row[0].markdown(f"{icon} {title}  \n*administrator only*")
        for col, role in zip(row[1:], permissions.ROLES):
            col.checkbox(f"{title} for {labels[role]}", value=False, disabled=True, key=f"perm_{role}_{key}",
                         label_visibility="collapsed")
        continue
    _file, title, icon, locked = permissions.PAGES[key]
    row[0].markdown(f"{icon} {title}" + ("  \n*always on*" if locked else ""))
    for col, role in zip(row[1:], permissions.ROLES):
        new[role][key] = col.checkbox(f"{title} for {labels[role]}", value=matrix[role][key],
                                      disabled=permissions.is_fixed(role, key), key=f"perm_{role}_{key}", label_visibility="collapsed")

st.write("")
b1, b2, _ = st.columns([1, 1, 3])
if b1.button("Save rights", type="primary"):
    permissions.save_matrix(new, admin_user["email"])
    st.success("Saved.")
if b2.button("Reset to default"):
    permissions.reset_defaults()
    for role in permissions.ROLES:
        for key in permissions.PAGES:
            st.session_state.pop(f"perm_{role}_{key}", None)
    st.success("All pages are allowed again for renters and owners.")
    st.rerun()

changed = [(labels[r], permissions.PAGES[k][1]) for r in permissions.ROLES for k in permissions.PAGES
           if not new[r][k]]
if changed:
    st.markdown("**Currently hidden (after you press Save):**")
    for who, page in changed:
        st.caption(f"{who}: {page}")

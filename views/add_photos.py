"""Add photos to a flat you listed. You need the listing number and the private edit code you received."""
import streamlit as st

import db
import listing_logic
import photos
import permissions
import ui

ui.inject_css()
permissions.guard("add_photos")
ui.hero("Add photos", "Flats with photos get chosen first. Add up to five pictures of your flat.")

MAX_TRIES = 5
state = st.session_state
state.setdefault("photo_tries", 0)

if "photo_listing" not in state:
    with st.form("photo_login"):
        lid = st.number_input("Listing number", min_value=1, step=1, value=1_000_000)
        code = st.text_input("Edit code", type="password", help="The private code shown once when you listed the flat.")
        ok = st.form_submit_button("Continue", type="primary")
    if ok:
        row = db.get_listing(int(lid))
        if state["photo_tries"] >= MAX_TRIES:
            st.error("Too many wrong tries in this visit. Close the page and open it again later.")
        elif row and row.get("is_extra") and listing_logic.check_code(code, row.get("edit_code_hash")):
            state["photo_listing"] = int(lid)
            st.rerun()
        else:
            state["photo_tries"] += 1
            st.error("The listing number or the edit code is wrong.")
    st.caption("Lost your edit code? It cannot be shown again. Ask the admin to help you.")
    st.stop()

lid = state["photo_listing"]
row = db.get_listing(lid)
st.markdown(f"**Listing {lid}:** {row['location']}, {ui.money(row['price'])} a month")
if state.get("photo_msg"):
    st.success(state.pop("photo_msg"))
mine = photos.photos_for(lid)
st.write(f"{len(mine)} of {photos.MAX_PHOTOS} photos saved.")

if mine:
    cols = st.columns(min(len(mine), 3))
    for n, (pid, path) in enumerate(mine):
        with cols[n % len(cols)]:
            st.image(str(path))
            if st.button("Delete", key=f"del{pid}"):
                photos.delete_photo(pid, lid)
                st.rerun()

left = photos.MAX_PHOTOS - len(mine)
if left > 0:
    key = f"upload{state.get('upload_n', 0)}"
    files = st.file_uploader(f"Choose up to {left} pictures (JPG, PNG or WebP)", type=["jpg", "jpeg", "png", "webp"],
                             accept_multiple_files=True, key=key)
    if files and st.button("Save photos", type="primary"):
        saved, problems = 0, []
        for f in files:
            try:
                photos.add_photo(lid, f.getvalue())
                saved += 1
            except ValueError as e:
                problems.append(f"{f.name}: {e}")
        for p in problems:
            st.error(p)
        if saved:
            state["upload_n"] = state.get("upload_n", 0) + 1
            state["photo_msg"] = f"Saved {saved} photo{'s' if saved != 1 else ''}."
            st.rerun()
    st.caption("Photos are shrunk and stripped of hidden camera data such as GPS. Do not upload pictures of people.")

if st.button("Done"):
    state.pop("photo_listing", None)
    st.rerun()

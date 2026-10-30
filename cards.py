"""Flat cards (photo, rent, badges, contact buttons) and the destination list shared by the pages."""
import html

import pandas as pd
import streamlit as st

import db
import ui
from flatcard_logic import deal_badge, freshness, phone_links


@st.cache_data(ttl=600)
def landmark_table():
    """Schools, colleges, universities, offices and areas that can be a destination. Column 'label' is shown."""
    lm = db.load_landmarks().dropna(subset=["lat", "lon"]).copy()
    lm["label"] = lm["name"] + " (" + lm["kind"] + ")"
    return lm.reset_index(drop=True)


def _pill(text, kind):
    return f'<span class="pill pill-{kind}">{html.escape(text)}</span>'


def flat_card(r, dest_name=None, contact=None, photo=None, logged_in=False):
    """Draw one flat. r is a row of the ranked table. contact is only given when the owner made it public."""
    esc = html.escape
    sub = "" if r["Sub"] in ("Unknown", "", None) else f"{r['Sub']}, "
    pills = []
    badge = deal_badge(r.get("deal_%"))
    if badge:
        pills.append(_pill(*badge))
    pills.append(_pill(*freshness(r.get("is_extra"), r.get("updated_at"), r.get("listed_at"))))
    km = r.get("km")
    if dest_name and km is not None and not pd.isna(km):
        how = "by road" if r.get("dist_source") in ("osrm", "google") else "estimated"
        pills.append(_pill(f"{km:.1f} km to {dest_name}, {how}", "info"))
    with st.container(border=True):
        left, right = st.columns([1, 2.2], gap="medium")
        with left:
            if photo:
                st.image(str(photo))
            else:
                st.markdown(ui.photo_placeholder(r.get("listing_id") or 0), unsafe_allow_html=True)
        with right:
            body = (f'<div class="flat-title">{int(r["Bed"])} bed, {int(r["Bath"])} bath, {r["Sqft"]:,.0f} sqft</div>'
                    f'<div class="flat-sub">{esc(sub + str(r["Place"]))}</div>'
                    f'<div class="flat-price">{ui.money(r["Price"])}<small> a month</small></div>')
            tm = r.get("total_monthly")
            if dest_name and tm is not None and not pd.isna(tm) and tm > r["Price"]:
                body += f'<div class="flat-sub">About {ui.money(tm)} a month with travel</div>'
            body += "<div style='margin-top:.35rem'>" + "".join(pills) + "</div>"
            if r.get("details"):
                body += f'<div class="flat-sub">{esc(str(r["details"]))}</div>'
            if r.get("address_label"):
                body += f'<div class="flat-sub">{esc(str(r["address_label"]))}</div>'
            st.markdown(body, unsafe_allow_html=True)
            _contact_row(r, contact, logged_in)


def _contact_row(r, contact, logged_in):
    if not r.get("is_extra") or pd.isna(r.get("is_extra")):
        st.caption("No contact for this flat: it comes from a public dataset of asking rents.")
    elif not contact:
        st.caption("The owner has not shared contact details.")
    elif not logged_in:
        st.caption("Log in to see the owner's contact.")
        ui.link("views/login.py", "Log in", "🔑")
    else:
        links = phone_links(contact)
        if links:
            st.markdown(f'<div class="btn-row"><a class="btn btn-call" href="{links["tel"]}">Call {links["shown"]}</a>'
                        f'<a class="btn btn-wa" href="{links["wa"]}" target="_blank" rel="noopener">WhatsApp</a></div>',
                        unsafe_allow_html=True)
        else:
            st.markdown(f"**Contact:** {html.escape(str(contact))}")

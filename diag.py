"""Diagnostic page. Run:  python -m streamlit run diag.py   then send a screenshot of the whole page."""
import streamlit as st

st.set_page_config(page_title="Diagnostic", layout="wide")
st.write("Streamlit version:", st.__version__)
st.write("Theme base:", st.get_option("theme.base"), "| text colour:", st.get_option("theme.textColor"))

st.subheader("A. Plain widgets (none of my CSS)")
st.selectbox("A: Bedrooms", [1, 2, 3, 4, 5], index=1, key="a1")
st.number_input("A: Rent", 3000, 500000, 20000, key="a2")

st.subheader("B. Same widgets after ui.inject_css()")
import ui
ui.inject_css()
st.selectbox("B: Bedrooms", [1, 2, 3, 4, 5], index=1, key="b1")
st.number_input("B: Rent", 3000, 500000, 20000, key="b2")

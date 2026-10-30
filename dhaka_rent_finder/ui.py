"""Look and feel shared by every page: theme, hero banner, tiles, pills, number formatting, safe widgets.

Same palette as dhaka_rent_finder.html: cool paper-green background, deep teal accent, white surfaces.
Old helper names (inject_css, hero, pills, money, show_df, link) are unchanged, so existing pages keep working.
"""
import math

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=Hanken+Grotesk:wght@400;500;600;700&family=Noto+Sans+Bengali:wght@400;600&display=swap');

:root {
  --bg: #EEF1EF; --surface: #FFFFFF; --surface2: #E4EAE7; --ink: #17211F; --muted: #55655F;
  --line: #CBD5D1; --accent: #0B6B5F; --accent-dark: #0A4F47; --stripe: #F2B01E; --brick: #A63A2B;
  --display: "Bricolage Grotesque", "Hanken Grotesk", system-ui, sans-serif;
  --body: "Hanken Grotesk", "Noto Sans Bengali", system-ui, -apple-system, "Segoe UI", sans-serif;
}

.stApp { background: var(--bg); font-family: var(--body); color: var(--ink); }
.block-container { padding-top: 1.6rem; max-width: 1180px; }
h1, h2, h3 { font-family: var(--display); letter-spacing: -0.01em; color: var(--ink); }
h2, h3 { font-weight: 700; }

/* sidebar */
section[data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--line); }
.brand { font-family: var(--display); font-weight: 700; font-size: 1.25rem; color: var(--accent-dark);
         padding: .2rem 0 .6rem 0; }
.brand small { display: block; font-family: var(--body); font-weight: 500; font-size: .8rem; color: var(--muted); }
.who { background: var(--bg); border: 1px solid var(--line); border-radius: 10px; padding: .55rem .75rem;
       font-size: .9rem; margin-bottom: .5rem; }
.who b { display: block; }

/* hero: the one loud element. The striped edge borrows the painted bands of Dhaka rickshaws. */
.hero { position: relative; padding: 1.7rem 1.9rem 1.9rem; border-radius: 16px; margin-bottom: 1.2rem;
        background: linear-gradient(135deg, var(--accent) 0%, var(--accent-dark) 100%); overflow: hidden; }
.hero::after { content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 9px;
               background: repeating-linear-gradient(90deg, var(--stripe) 0 28px, var(--brick) 28px 40px,
                                                     #fff 40px 48px); }
.hero h1 { color: #fff; margin: 0 0 .35rem 0; font-size: 2.1rem; line-height: 1.15; }
.hero p { color: #d6efe9; margin: 0; font-size: 1.05rem; max-width: 60ch; }

/* tiles and cards */
.tile { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: .9rem 1.1rem; }
.tile .num { font-family: var(--display); font-weight: 700; font-size: 1.8rem; color: var(--accent-dark);
             line-height: 1.1; }
.tile .lbl { color: var(--muted); font-size: .9rem; }
div[data-testid="stMetric"] { background: var(--surface); border: 1px solid var(--line); border-radius: 12px;
                              padding: .8rem 1rem; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 12px; }
div[data-testid="stForm"] { background: var(--surface); border: 1px solid var(--line); border-radius: 14px;
                            padding: 1.3rem 1.4rem; }
div[data-testid="stForm"] button { width: 100%; }

/* inputs and buttons */
div[data-baseweb="input"], div[data-baseweb="select"] > div, textarea { border-radius: 10px !important; }
button[kind="primary"], button[data-testid="stBaseButton-primary"],
button[data-testid="stBaseButton-primaryFormSubmit"] {
  background: var(--accent); border: 1px solid var(--accent); border-radius: 10px; font-weight: 600; }
button[kind="primary"]:hover, button[data-testid="stBaseButton-primary"]:hover,
button[data-testid="stBaseButton-primaryFormSubmit"]:hover { background: var(--accent-dark); border-color: var(--accent-dark); }
button[kind="secondary"], button[data-testid="stBaseButton-secondary"] { border-radius: 10px; }
button:focus-visible, input:focus-visible, a:focus-visible { outline: 3px solid var(--stripe) !important;
                                                              outline-offset: 2px; }
button[data-baseweb="tab"] { font-weight: 600; }

/* pills */
.pill { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .78rem;
        font-weight: 600; margin: 0 6px 4px 0; }
.pill-good { background: #DDF0E2; color: #1B6E36; }
.pill-warn { background: #F7E8CC; color: #8A5200; }
.pill-info { background: #E1ECF7; color: #1D4F8A; }
.pill-muted { background: #E4EAE7; color: #44504B; }

/* phones */
@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; }
  .hero { padding: 1.2rem 1.1rem 1.4rem; }
  .hero h1 { font-size: 1.6rem; }
}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title, subtitle=""):
    """Banner at the top of a page. Title and subtitle must be our own text, not user input."""
    st.markdown(f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)


def brand():
    """Name block at the top of the sidebar."""
    st.sidebar.markdown('<div class="brand">Dhaka House Rent Finder<small>Fair rents, real distances</small></div>',
                        unsafe_allow_html=True)


def tile(number, label):
    """A small statistic box. Values must be our own text or numbers."""
    st.markdown(f'<div class="tile"><div class="num">{number}</div><div class="lbl">{label}</div></div>',
                unsafe_allow_html=True)


def pills(items):
    """items: [(text, kind)] with kind good / warn / info / muted. Text must be our own, not user input."""
    st.markdown(" ".join(f'<span class="pill pill-{k}">{t}</span>' for t, k in items), unsafe_allow_html=True)


def money(x):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return "-"
        return f"৳{float(x):,.0f}"
    except (TypeError, ValueError):
        return "-"


def show_df(df, **kw):
    """st.dataframe that works on old and new Streamlit versions."""
    try:
        st.dataframe(df, width="stretch", **kw)
    except TypeError:
        st.dataframe(df, use_container_width=True, **kw)


def link(path, label, icon=None):
    """A link to another page of the site; silently skipped if the Streamlit version cannot do it."""
    try:
        st.page_link(path, label=label, icon=icon)
    except Exception:
        pass

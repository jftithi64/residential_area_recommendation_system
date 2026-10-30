"""Look and feel shared by every page: theme, hero banner, tiles, pills, number formatting, safe widgets.

Same palette as dhaka_rent_finder.html: cool paper-green background, deep teal accent, white surfaces.
Old helper names (inject_css, hero, pills, money, show_df, link) are unchanged, so existing pages keep working.
"""
import base64
import functools
import math

import streamlit as st

from common import ROOT

ASSETS = ROOT / "assets"

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
.hero-art { position: absolute; right: 0; bottom: 9px; height: calc(100% - 9px); width: 40%; pointer-events: none;
            object-fit: cover; object-position: right bottom; }
.hero h1, .hero p { position: relative; z-index: 1; max-width: 58%; }
.hero h1 { color: #fff; margin: 0 0 .35rem 0; font-size: 2.1rem; line-height: 1.15; }
.hero p { color: #d6efe9; margin: 0; font-size: 1.05rem; max-width: min(60ch, 58%); }

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
/* Only the submit button fills the width. A bare "button" rule here also stretched the dropdown arrow and the
   + / - buttons of number boxes, which squeezed the chosen value out of sight. */
div[data-testid="stForm"] [data-testid="stFormSubmitButton"] button { width: 100%; }

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

/* flat cards */
.flat-title { font-family: var(--display); font-weight: 700; font-size: 1.15rem; }
.flat-sub { color: var(--muted); font-size: .92rem; margin: .1rem 0; }
.flat-price { font-family: var(--display); font-weight: 700; font-size: 1.6rem; color: var(--accent-dark);
              margin: .25rem 0; }
.flat-price small { font-size: .9rem; color: var(--muted); font-weight: 500; }
.photo-ph { position: relative; border-radius: 10px; overflow: hidden; min-height: 150px; }
.photo-ph img { display: block; width: 100%; height: 100%; min-height: 150px; object-fit: cover; }
.photo-ph span { position: absolute; left: 8px; bottom: 14px; background: rgba(255,255,255,.88); color: var(--muted);
                 font-size: .75rem; font-weight: 600; padding: 1px 8px; border-radius: 999px; }
.brand img { width: 100%; max-width: 210px; display: block; margin-bottom: .2rem; }
.feat img { width: 100%; max-width: 150px; border-radius: 12px; margin-bottom: .4rem; display: block; }
.nophoto { display: flex; align-items: center; justify-content: center; min-height: 150px; border-radius: 10px;
           background: var(--surface2); color: var(--muted); font-size: .9rem; }
.btn-row { display: flex; gap: .5rem; margin-top: .5rem; flex-wrap: wrap; align-items: center; }
.btn { display: inline-block; padding: .45rem .95rem; border-radius: 10px; font-weight: 600;
       text-decoration: none !important; font-size: .92rem; }
.btn-call { background: var(--accent); color: #fff !important; }
.btn-wa { background: #E7F6EC; color: #1B6E36 !important; border: 1px solid #BFE3CB; }
.verdict { border-radius: 12px; padding: 1rem 1.2rem; background: var(--surface); border: 1px solid var(--line); }
.verdict .big { font-family: var(--display); font-weight: 700; font-size: 2rem; color: var(--accent-dark); }

/* visitor home page */
.sign-line { color: var(--muted); margin: .9rem 0 .1rem; }
.stats-band { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 1rem 1.2rem;
              margin: .4rem 0 1.2rem; }
.stat-big { font-family: var(--display); font-weight: 700; font-size: 2.2rem; color: var(--accent-dark); line-height: 1.05; }
.stat-lbl { color: var(--muted); font-size: .92rem; }
.stars { color: #E0A100; letter-spacing: 2px; font-size: 1.05rem; }
.stars .off { color: #D4DAD7; }
.review { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: .9rem 1.1rem;
          height: 100%; }
.review p { margin: .35rem 0 .5rem; color: var(--ink); }
.review .by { color: var(--muted); font-size: .85rem; }
.review-wrap { margin-bottom: .6rem; }
.lock-box { background: var(--surface); border: 2px dashed var(--accent); border-radius: 14px; padding: 1.1rem 1.3rem;
            margin-bottom: 1.2rem; }
.lock-box h3 { margin: 0 0 .25rem 0; }
.step-no { display: inline-flex; width: 2rem; height: 2rem; border-radius: 50%; background: var(--accent); color: #fff;
           font-weight: 700; align-items: center; justify-content: center; margin-bottom: .3rem; }

/* phones */
@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; }
  .hero { padding: 1.2rem 1.1rem 1.4rem; }
  .hero-art { opacity: .3; width: 100%; }
  .hero h1, .hero p { max-width: none; }
  .hero h1 { font-size: 1.6rem; }
}
</style>
"""


@functools.lru_cache(maxsize=None)
def asset_uri(name):
    """Data URI of a file in assets/ so it can sit inside our own HTML. Empty string if the file is missing."""
    f = ASSETS / name
    if not f.exists():
        return ""
    mime = "image/svg+xml" if f.suffix == ".svg" else "image/png"
    return f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode()


def photo_placeholder(seed=0):
    """HTML for a flat that has no photo yet: a drawn building, in one of three colours picked from the id."""
    uri = asset_uri(f"flat_placeholder_{int(seed) % 3}.svg")
    if not uri:
        return '<div class="nophoto">No photo yet</div>'
    return f'<div class="photo-ph"><img src="{uri}" alt="No photo yet"><span>No photo yet</span></div>'


def feature(image, text_md):
    """Small illustration with a text block under it (home page). text_md is our own markdown, not user input."""
    uri = asset_uri(image)
    st.markdown(f'<div class="feat"><img src="{uri}" alt=""></div>' if uri else "", unsafe_allow_html=True)
    st.markdown(text_md)


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title, subtitle=""):
    """Banner at the top of a page. Title and subtitle must be our own text, not user input."""
    art = asset_uri("hero_skyline.svg")
    img = f'<img class="hero-art" src="{art}" alt="">' if art else ""
    st.markdown(f'<div class="hero">{img}<h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)


def brand():
    """Name block at the top of the sidebar."""
    logo = asset_uri("logo.svg")
    top = f'<img src="{logo}" alt="Dhaka House Rent Finder">' if logo else "Dhaka House Rent Finder"
    st.sidebar.markdown(f'<div class="brand">{top}<small>Fair rents, real distances</small></div>',
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
        import auth
        import permissions
        key = permissions.FILE_TO_KEY.get(path)
        user = auth.current_user()
        role = permissions.role_from_db(user) if user else permissions.VISITOR
        if key and key not in permissions.allowed_pages(role):
            return   # this kind of person has no right to that page, so do not offer the link
        st.page_link(path, label=label, icon=icon)
    except Exception:
        pass


def goto(path, fallback="views/start.py"):
    """Switch to a page, or to `fallback` (Home) when this account type has no right to it."""
    import auth
    import permissions
    key = permissions.FILE_TO_KEY.get(path)
    user = auth.current_user()
    role = permissions.role_from_db(user) if user else permissions.VISITOR
    if key and key not in permissions.allowed_pages(role):
        path = fallback
    st.switch_page(path)


def stars(n, size=5):
    """Star row as HTML, e.g. stars(4) -> four gold stars and one grey. n must be a number, not user text."""
    n = max(0, min(size, int(round(float(n)))))
    return f'<span class="stars">{"★" * n}<span class="off">{"★" * (size - n)}</span></span>'


def esc(text):
    """Escape user text before it goes inside our own HTML (names and review comments come from users)."""
    import html
    return html.escape(str(text or ""), quote=True)


def review_card(r):
    """One review as an HTML card (stars, comment, name, role). Text comes from users, so it is escaped."""
    import auth
    who = auth.ROLE_LABELS.get(r.get("role"), "")
    when = str(r.get("created_at") or "")[:10]
    meta = " · ".join(x for x in (esc(who), esc(when)) if x)
    return (f'<div class="review review-wrap">{stars(r["rating"])}<p>{esc(r["comment"])}</p>'
            f'<div class="by"><b>{esc(r["name"])}</b>{" · " + meta if meta else ""}</div></div>')


def review_form(user, key="review_form"):
    """Write / edit my review: stars, a few words, Save. One review per account; saving again replaces it."""
    import db
    mine = db.get_review(user["user_id"])
    with st.form(key):
        stars_i = st.select_slider("Your rating", options=[1, 2, 3, 4, 5], value=(mine or {}).get("rating", 5),
                                   format_func=lambda n: "★" * n)
        text_i = st.text_area("Your review", value=(mine or {}).get("comment", ""), max_chars=400,
                              placeholder="For example: I found a flat near my office in two days.")
        saved = st.form_submit_button("Save review" if not mine else "Update review", type="primary")
    if saved:
        err = db.save_review(user["user_id"], user["full_name"].split()[0] if user["full_name"] else "User",
                             user["role"], stars_i, text_i)
        if err:
            st.error(err)
        else:
            st.success("Thank you! Your review is on the home page.")
    elif mine and st.button("Delete my review", key=key + "_del"):
        db.delete_review(user["user_id"])
        st.rerun()

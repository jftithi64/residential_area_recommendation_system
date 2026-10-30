"""A tiny stand-in for streamlit so the page scripts can be run (and checked for errors) without a browser.

Every widget returns its default value, unless a test gives an answer for its label in `ANSWERS`
or presses a button by putting its label in `PRESS`.
"""
import datetime


_RESOURCES = {}


class StopPage(Exception):
    pass


class RerunPage(Exception):
    pass


class _State(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v


class Api:
    ANSWERS, PRESS, CALLS = {}, set(), []

    def __init__(self, shared=None):
        self.session_state = shared if shared is not None else _State()

    # context manager so `with st.container():` works
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def _note(self, name, *a):
        Api.CALLS.append((name, a[:1]))

    def __getattr__(self, name):          # any other st.something(...) is recorded and ignored
        if name.startswith("__"):
            raise AttributeError(name)

        def f(*a, **k):
            self._note(name, *a)
            return self
        return f

    # ---- widgets
    def _ans(self, label, default):
        return Api.ANSWERS[label] if label in Api.ANSWERS else default

    def text_input(self, label, value="", **k):
        return self._ans(label, value or "")

    text_area = text_input

    def number_input(self, label, min_value=None, max_value=None, value=None, step=None, **k):
        return self._ans(label, value)

    def selectbox(self, label, options=(), index=0, **k):
        options = list(options)
        default = None if index is None or not options else options[index]
        return self._ans(label, default)

    def radio(self, label, options=(), index=0, **k):
        return self._ans(label, list(options)[index])

    def multiselect(self, label, options=(), default=None, **k):
        return self._ans(label, list(default or []))

    def checkbox(self, label, value=False, **k):
        return self._ans(label, value)

    def slider(self, label, min_value=0, max_value=100, value=None, **k):
        return self._ans(label, min_value if value is None else value)

    def date_input(self, label, value=None, **k):
        return self._ans(label, value or datetime.date.today())

    def file_uploader(self, label, **k):
        return self._ans(label, None)

    def button(self, label, *a, **k):
        return label in Api.PRESS

    form_submit_button = button

    def download_button(self, label, *a, **k):
        return False

    # ---- layout
    def columns(self, spec, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [Api(self.session_state) for _ in range(n)]

    def tabs(self, labels):
        return [Api(self.session_state) for _ in labels]

    def container(self, *a, **k):
        return self

    expander = form = spinner = empty = sidebar = container

    # ---- control flow and caching
    def stop(self):
        raise StopPage()

    def rerun(self):
        raise RerunPage()

    def cache_data(self, *a, **k):
        if len(a) == 1 and callable(a[0]) and not k:
            return a[0]
        return lambda f: f

    def cache_resource(self, *a, **k):
        """Like the real one: the function runs once and every caller gets the same object."""
        def wrap(f):
            key = (f.__code__.co_filename, f.__code__.co_firstlineno)   # the page script is re-run, so key by source

            def inner(*x, **y):
                if key not in _RESOURCES:
                    _RESOURCES[key] = f(*x, **y)
                return _RESOURCES[key]
            return inner
        return wrap(a[0]) if len(a) == 1 and callable(a[0]) and not k else wrap


st = Api()


def reset(answers=None, press=(), keep_resources=False):
    st.session_state.clear()
    if not keep_resources:
        _RESOURCES.clear()
    Api.ANSWERS = dict(answers or {})
    Api.PRESS = set(press)
    Api.CALLS = []

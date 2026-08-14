"""Scoped terminal-style theme for Streamlit."""

from __future__ import annotations


TERMINAL_CSS = """
<style>
section[data-testid="stSidebar"], .stApp {
  background: #0b1114;
  color: #d8e4e5;
}
.stApp h1, .stApp h2, .stApp h3 { letter-spacing: -0.02em; }
.stApp code, .stApp pre { color: #75e0bd; }
button[kind="primary"] { background: #1fb98b; color: #07110e; }
button:focus, input:focus, textarea:focus { outline: 2px solid #75e0bd; outline-offset: 2px; }
</style>
"""


def apply_terminal_theme(st) -> None:
    st.markdown(TERMINAL_CSS, unsafe_allow_html=True)


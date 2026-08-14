"""Small, dependency-free presentation helpers for Streamlit pages."""

from __future__ import annotations


STATUS_LABELS = {
    "pending": "排队中",
    "running": "运行中",
    "completed": "已完成",
    "degraded": "部分完成",
    "failed": "失败",
    "interrupted": "已中断",
    "skipped": "已跳过",
}


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def page_heading(st, title: str, description: str) -> None:
    st.title(title)
    st.caption(description)


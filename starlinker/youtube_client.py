from __future__ import annotations
from googleapiclient.discovery import build
import streamlit as st

@st.cache_resource(show_spinner=False)
def get_youtube_client(api_key: str):
    """Ленивая и кешируемая инициализация клиента YouTube Data API v3."""
    return build("youtube", "v3", developerKey=api_key)

from __future__ import annotations
import os
import streamlit as st
from dotenv import load_dotenv

# Загружаем локальные .env при разработке
load_dotenv()

def get_api_key() -> str | None:
    """
    Порядок:
      1) st.secrets["YOUTUBE_API_KEY"]
      2) env/.env
    """
    return st.secrets.get("YOUTUBE_API_KEY") or os.getenv("YOUTUBE_API_KEY")

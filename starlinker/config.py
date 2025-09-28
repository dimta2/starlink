import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

def get_api_key() -> str | None:
    # 1) Streamlit secrets → 2) env/.env
    return st.secrets.get("YOUTUBE_API_KEY") or os.getenv("YOUTUBE_API_KEY")

import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

def get_api_key() -> str | None:
    return st.secrets.get("YOUTUBE_API_KEY") or os.getenv("YOUTUBE_API_KEY")

from googleapiclient.discovery import build
import streamlit as st

@st.cache_resource(show_spinner=False)
def get_youtube_client(api_key: str):
    # Кешируем ресурс Google API клиента
    return build("youtube", "v3", developerKey=api_key)

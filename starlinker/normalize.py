from __future__ import annotations
from typing import Dict, Optional, Tuple, List
import re
import streamlit as st
from googleapiclient.errors import HttpError

_UC_RE = re.compile(r"(UC[0-9A-Za-z_-]{20,})", re.I)

def extract_uc_id(s: str) -> Optional[str]:
    if not isinstance(s, str): return None
    s = s.strip()
    m = _UC_RE.search(s)
    if m: return m.group(1)
    m2 = re.search(r"channel/(UC[0-9A-Za-z_-]{20,})", s, re.I)
    return m2.group(1) if m2 else None

def extract_handle(s: str, treat_bare_names: bool = False) -> Optional[str]:
    if not isinstance(s, str): return None
    s0 = s.strip()
    m = re.search(r"@([A-Za-z0-9._-]{3,})", s0)
    if m: return m.group(1).lower()
    m = re.search(r"youtube\.com/\@([A-Za-z0-9._-]{3,})", s0, re.I)
    if m: return m.group(1).lower()
    m = re.search(r"youtube\.com/(?:c|user)/([A-Za-z0-9._-]{3,})", s0, re.I)
    if m: return m.group(1).lower()
    if treat_bare_names:
        token = re.sub(r"\s+", "", s0).split("/")[0].strip(".")
        if re.fullmatch(r"[A-Za-z0-9._-]{3,}", token):
            return token.lower()
    return None

@st.cache_data(show_spinner=False, ttl=7200)
def resolve_handle_to_channel_id(youtube, handle: str) -> Optional[str]:
    """Через search→channels проверяем customUrl и берём подходящий channel_id."""
    try:
        sres = youtube.search().list(
            q=handle, part="snippet", type="channel", maxResults=10
        ).execute()
        ch_ids = [it["snippet"]["channelId"] for it in sres.get("items", []) if it.get("snippet")]
        if not ch_ids:
            return None
        cres = youtube.channels().list(part="snippet", id=",".join(ch_ids[:50])).execute()
        # точное совпадение customUrl
        for it in cres.get("items", []):
            custom = (it.get("snippet", {}).get("customUrl") or "").lstrip("@").lower()
            if custom == handle.lower():
                return it["id"]
        return ch_ids[0]
    except HttpError:
        return None

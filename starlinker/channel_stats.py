from typing import Dict, Iterable, List, Tuple, Optional
from datetime import datetime, timedelta, timezone

import streamlit as st
from googleapiclient.errors import HttpError
from googleapiclient.discovery import Resource  # для hash_funcs

def _chunked(seq: List[str], n: int) -> Iterable[List[str]]:
    for i in range(0, len(seq), n):
        yield seq[i:i+n]

@st.cache_data(show_spinner=False, ttl=3600, hash_funcs={Resource: lambda _: b"yt"})
def fetch_channels_stats(youtube, channel_ids: List[str]) -> Dict[str, dict]:
    """channel_id -> {'subs','country','uploads_playlist_id','title'}"""
    out: Dict[str, dict] = {}
    for batch in _chunked(channel_ids, 50):
        try:
            res = youtube.channels().list(
                part="statistics,snippet,contentDetails",
                id=",".join(batch)
            ).execute()
        except HttpError:
            continue
        for item in res.get("items", []):
            ch_id = item["id"]
            stats = item.get("statistics", {}) or {}
            snip = item.get("snippet", {}) or {}
            cdet = item.get("contentDetails", {}) or {}
            out[ch_id] = {
                "subs": int(stats.get("subscriberCount", 0) or 0),
                "country": snip.get("country", "N/A"),
                "uploads_playlist_id": cdet.get("relatedPlaylists", {}).get("uploads", ""),
                "title": snip.get("title") or None,
            }
    return out

def _iso_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def iter_recent_upload_video_ids(youtube, uploads_playlist_id: str, since_dt: datetime, max_fetch: int):
    fetched = 0
    page_token: Optional[str] = None
    while True:
        try:
            pl = youtube.playlistItems().list(
                part="contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=50, pageToken=page_token
            ).execute()
        except HttpError:
            return
        for it in pl.get("items", []):
            fetched += 1
            pub = _iso_to_dt(it["contentDetails"]["videoPublishedAt"])
            if pub >= since_dt:
                yield it["contentDetails"]["videoId"]
            else:
                return
            if fetched >= max_fetch:
                return
        page_token = pl.get("nextPageToken")
        if not page_token:
            return

@st.cache_data(show_spinner=False, ttl=900, hash_funcs={Resource: lambda _: b"yt"})
def get_avg_views_for_period(youtube, uploads_playlist_id: str, days: int, max_fetch: int) -> Tuple[Optional[int], int]:
    since_dt = datetime.now(timezone.utc) - timedelta(days=days)
    vids = list(iter_recent_upload_video_ids(youtube, uploads_playlist_id, since_dt, max_fetch=max_fetch))
    if not vids:
        return None, 0

    total_views = 0
    counted = 0
    for batch in _chunked(vids, 50):
        try:
            vres = youtube.videos().list(part="statistics", id=",".join(batch)).execute()
        except HttpError:
            continue
        for it in vres.get("items", []):
            vc = int(it.get("statistics", {}).get("viewCount", 0) or 0)
            total_views += vc
            counted += 1
    return (total_views // counted, counted) if counted else (None, 0)

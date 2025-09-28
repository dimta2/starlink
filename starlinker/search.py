from typing import Dict, Optional
from googleapiclient.errors import HttpError
from .quota import add

def search_channels_by_keyword(
    youtube,
    keyword: str,
    max_pages: int,
    max_channels: int,
    by_channel: bool = False
) -> Dict[str, str]:
    out: Dict[str, str] = {}
    page_token: Optional[str] = None
    pages = 0
    while True:
        try:
            # каждую страницу считаем как +100 юнитов
            add(100, note=f"search.list:{'channel' if by_channel else 'video'} kw={keyword} page={pages+1}")
            resp = youtube.search().list(
                q=keyword, part="snippet",
                type="channel" if by_channel else "video",
                maxResults=50, pageToken=page_token
            ).execute()
        except HttpError:
            break

        items = resp.get("items", [])
        for it in items:
            if by_channel:
                ch_id = it["id"]["channelId"]
                ch_title = it["snippet"].get("title") or ch_id
            else:
                sn = it.get("snippet") or {}
                ch_id = sn.get("channelId")
                ch_title = sn.get("channelTitle") or ch_id
            if ch_id and ch_id not in out:
                out[ch_id] = ch_title
                if len(out) >= max_channels:
                    return out

        page_token = resp.get("nextPageToken")
        pages += 1
        if not page_token or pages >= max_pages:
            break
    return out

from typing import Dict, Optional
from googleapiclient.errors import HttpError

def search_channels_by_keyword(youtube, keyword: str, max_pages: int, max_channels: int) -> Dict[str, str]:
    """
    Возвращает {channel_id: channel_title} для заданного ключевого слова,
    с пагинацией до max_pages и ограничением уникальных каналов max_channels.
    """
    out: Dict[str, str] = {}
    page_token: Optional[str] = None
    pages = 0
    while True:
        try:
            resp = youtube.search().list(
                q=keyword, part="snippet", type="video",
                maxResults=50, pageToken=page_token
            ).execute()
        except HttpError:
            break

        for it in resp.get("items", []):
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

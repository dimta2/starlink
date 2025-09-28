from __future__ import annotations
from typing import Dict, Optional
from googleapiclient.errors import HttpError

def search_channels_by_keyword(
    youtube,
    keyword: str,
    max_pages: int,
    max_channels: int,
    by_channel: bool = False,
) -> Dict[str, str]:
    """
    Возвращает {channel_id: channel_title}.

    by_channel=False: ищем видео и собираем авторов (шире охват).
    by_channel=True: ищем каналы напрямую (точнее для брендинга, чуть уже охват).
    """
    out: Dict[str, str] = {}
    page_token: Optional[str] = None
    pages = 0

    while True:
        try:
            if by_channel:
                resp = youtube.search().list(
                    q=keyword, part="snippet", type="channel",
                    maxResults=50, pageToken=page_token
                ).execute()
                for it in resp.get("items", []):
                    cid = it["id"]["channelId"]
                    title = it["snippet"].get("title") or cid
                    if cid not in out:
                        out[cid] = title
                        if len(out) >= max_channels:
                            return out
            else:
                resp = youtube.search().list(
                    q=keyword, part="snippet", type="video",
                    maxResults=50, pageToken=page_token
                ).execute()
                for it in resp.get("items", []):
                    sn = it.get("snippet") or {}
                    cid = sn.get("channelId")
                    title = sn.get("channelTitle") or cid
                    if cid and cid not in out:
                        out[cid] = title
                        if len(out) >= max_channels:
                            return out
        except HttpError:
            # Тихо пропускаем ошибку (квота/транзиент) и выходим из цикла
            break

        page_token = resp.get("nextPageToken")
        pages += 1
        if not page_token or pages >= max_pages:
            break

    return out

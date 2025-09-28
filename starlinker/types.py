from typing import TypedDict, Optional

class ChannelBrief(TypedDict):
    id: str
    title: str

class ChannelStats(TypedDict, total=False):
    subs: int
    total_views: int
    country: str
    uploads_playlist_id: str

class ResultRow(TypedDict, total=False):
    Канал: str
    Подписчики: int
    Просмотры_total: int
    Средние_за_дни: int
    Видео_за_дни: int
    Страна: str
    Ссылка: str
    channel_id: str

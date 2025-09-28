# StarLinker v. 1.3
# a tool for searching YouTube influencers
# (c) StarPets 2025

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Optional, Iterable

import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

# =================== НАСТРОЙКА СТРАНИЦЫ ===================
st.set_page_config(page_title="StarLinker", page_icon="🔎", layout="wide")

# =================== ИНИЦИАЛИЗАЦИЯ ===================
load_dotenv()
# сначала пробуем Streamlit secrets, потом .env
api_key = os.getenv("YOUTUBE_API_KEY")
try:
    import streamlit as st
    if not api_key:
        api_key = st.secrets.get("YOUTUBE_API_KEY")
except Exception:
    pass

API_KEY = os.getenv("YOUTUBE_API_KEY")

st.title("🔎 StarLinker — Поиск блогеров на YouTube (v1.3)")

# =================== ХЕЛПЕРЫ ===================
def chunked(iterable: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]

def iso_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def build_client(api_key: str):
    return build("youtube", "v3", developerKey=api_key)

def extract_channel_id(url_or_id: str) -> str:
    """
    Пытается вытащить channel_id (обычно начинается с 'UC').
    Поддерживает:
      - https://www.youtube.com/channel/UCxxxx
      - просто 'UCxxxx' (чистый id в ячейке)
    Возвращает '' если не удалось.
    """
    if not isinstance(url_or_id, str):
        return ""
    s = url_or_id.strip()
    # чистый UC-id
    if re.fullmatch(r"UC[0-9A-Za-z_-]{20,}", s):
        return s
    # ссылка с /channel/UC...
    m = re.search(r"(?:/channel/)(UC[0-9A-Za-z_-]{20,})", s)
    if m:
        return m.group(1)
    return ""

# =================== САЙДБАР: ПАРАМЕТРЫ ===================
with st.sidebar:
    st.header("⚙️ Параметры поиска")
    max_pages_per_keyword = st.number_input(
        "Макс. страниц на ключ (по 50 видео)",
        min_value=1, max_value=10, value=3, step=1,
        help="Пагинация поиска YouTube. 1 страница = до 50 видео."
    )
    max_channels_per_keyword = st.number_input(
        "Ограничение каналов на ключ",
        min_value=10, max_value=5000, value=500, step=10,
        help="Чтобы не сжигать квоту, можно ограничить число уникальных каналов на ключ."
    )
    max_recent_uploads_fetch = st.number_input(
        "Макс. загруженных видео на канал (для среднего за период)",
        min_value=20, max_value=500, value=150, step=10,
        help="Сколько последних видео смотреть из плейлиста загрузок канала."
    )

    st.markdown("---")
    st.header("📊 Фильтры")
    min_subs = st.number_input("Мин. подписчиков", value=1_000, step=500)
    max_subs = st.number_input("Макс. подписчиков", value=500_000, step=1_000)
    min_views_total = st.number_input("Мин. просмотров канала (total)", value=10_000, step=1_000)

    period_days = st.number_input("Период (дней) для среднего по видео", value=30, min_value=1, max_value=90)
    min_avg_views_period = st.number_input("Мин. средние просмотры за период", value=2_000, step=100)

    st.markdown("---")
    st.header("🗂️ Исключить уже имеющихся блогеров")
    uploaded_file = st.file_uploader(
        "Загрузите Excel/CSV из вашей базы (со столбцом 'Ссылка' или 'channel_id')",
        type=["xlsx", "csv"],
        help="Эти каналы будут исключены из результатов текущего поиска."
    )

# =================== ЗАГРУЗКА БАЗЫ ДЛЯ ИСКЛЮЧЕНИЯ ===================
existing_ids: set[str] = set()
if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith(".csv"):
            df_existing = pd.read_csv(uploaded_file)
        else:
            df_existing = pd.read_excel(uploaded_file)

        # Находим подходящие колонки
        cols_lower = {c.lower(): c for c in df_existing.columns}
        channel_id_col = None
        link_col = None

        # приоритет: явный channel_id
        for k, orig in cols_lower.items():
            if "channel_id" == k or k.endswith("channel_id") or k == "id":
                channel_id_col = orig
                break
        if not channel_id_col:
            # ищем ссылку
            for k, orig in cols_lower.items():
                if "ссыл" in k or "link" in k or "url" in k:
                    link_col = orig
                    break

        if channel_id_col:
            for v in df_existing[channel_id_col].dropna():
                ch = extract_channel_id(str(v))
                if ch:
                    existing_ids.add(ch)
        elif link_col:
            for v in df_existing[link_col].dropna():
                ch = extract_channel_id(str(v))
                if ch:
                    existing_ids.add(ch)
        else:
            st.warning("⚠️ Не нашли столбцы 'channel_id' или 'Ссылка/Link' — исключение дубликатов не применится.")

        st.info(f"📂 Загружено {len(existing_ids)} каналов для исключения")
    except Exception as e:
        st.error(f"Ошибка загрузки базы: {e}")

# =================== ВВОД КЛЮЧЕВЫХ СЛОВ ===================
keywords_input = st.text_area("Ключевые слова (по одному в строке)")
keywords = [kw.strip() for kw in keywords_input.splitlines() if kw.strip()]

st.caption("ℹ️ Рекомендации: увеличь число страниц и лимит каналов на ключ, если находок мало. "
           "Слишком строгие фильтры тоже могут обнулять результат.")

# =================== API-ОБОЛОЧКИ ===================
def search_channels_by_keyword(youtube, keyword: str, max_pages: int, max_channels: int) -> Dict[str, str]:
    """Возвращает {channel_id: channel_title} для заданного ключа, проходя до max_pages страниц."""
    channel_map: Dict[str, str] = {}
    page_token: Optional[str] = None
    pages = 0

    while True:
        try:
            resp = youtube.search().list(
                q=keyword,
                part="snippet",
                type="video",
                maxResults=50,
                pageToken=page_token
            ).execute()
        except HttpError as e:
            st.warning(f"⚠️ Ошибка поиска по ключу «{keyword}»: {e}")
            break

        for it in resp.get("items", []):
            ch_id = it["snippet"]["channelId"]
            ch_title = it["snippet"]["channelTitle"]
            if ch_id not in channel_map:
                channel_map[ch_id] = ch_title
                if len(channel_map) >= max_channels:
                    return channel_map

        page_token = resp.get("nextPageToken")
        pages += 1
        if not page_token or pages >= max_pages:
            break

    return channel_map

def fetch_channels_stats(youtube, channel_ids: List[str]) -> Dict[str, Tuple[int, int, str, str]]:
    """
    Возвращает словарь:
      channel_id -> (subs, total_views, country, uploads_playlist_id)
    """
    out: Dict[str, Tuple[int, int, str, str]] = {}
    for batch in chunked(channel_ids, 50):
        try:
            res = youtube.channels().list(
                part="statistics,snippet,contentDetails",
                id=",".join(batch)
            ).execute()
        except HttpError as e:
            st.warning(f"⚠️ Ошибка получения статистики каналов: {e}")
            continue

        for item in res.get("items", []):
            ch_id = item["id"]
            stats = item.get("statistics", {})
            snip = item.get("snippet", {})
            cdet = item.get("contentDetails", {})
            subs = int(stats.get("subscriberCount", 0) or 0)
            total_views = int(stats.get("viewCount", 0) or 0)
            country = snip.get("country", "N/A")
            uploads_pid = cdet.get("relatedPlaylists", {}).get("uploads", "")
            if uploads_pid:
                out[ch_id] = (subs, total_views, country, uploads_pid)
    return out

def iter_recent_upload_video_ids(
    youtube, uploads_playlist_id: str, since_dt: datetime, max_fetch: int
) -> Iterable[str]:
    fetched = 0
    page_token: Optional[str] = None
    while True:
        try:
            pl = youtube.playlistItems().list(
                part="contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=50,
                pageToken=page_token
            ).execute()
        except HttpError as e:
            st.warning(f"⚠️ Ошибка чтения плейлиста загрузок: {e}")
            return

        for it in pl.get("items", []):
            fetched += 1
            pub = iso_to_dt(it["contentDetails"]["videoPublishedAt"])
            if pub >= since_dt:
                yield it["contentDetails"]["videoId"]
            else:
                # Порядок: новые → старые. Старше периода — дальше можно не идти.
                return
            if fetched >= max_fetch:
                return

        page_token = pl.get("nextPageToken")
        if not page_token:
            return

def get_avg_views_for_period(
    youtube, uploads_playlist_id: str, days: int, max_fetch: int
) -> Tuple[Optional[int], int]:
    """
    Возвращает (avg_views_or_None, count_videos_in_period).
    None — если за период нет видео.
    """
    since_dt = datetime.now(timezone.utc) - timedelta(days=days)
    vids = list(iter_recent_upload_video_ids(youtube, uploads_playlist_id, since_dt, max_fetch=max_fetch))
    if not vids:
        return None, 0

    total_views = 0
    counted = 0
    for batch in chunked(vids, 50):
        try:
            vres = youtube.videos().list(part="statistics", id=",".join(batch)).execute()
        except HttpError as e:
            st.warning(f"⚠️ Ошибка статистики видео: {e}")
            continue
        for it in vres.get("items", []):
            vc = int(it.get("statistics", {}).get("viewCount", 0) or 0)
            total_views += vc
            counted += 1

    if counted == 0:
        return None, 0
    return total_views // counted, counted

# =================== ОСНОВНОЙ БЛОК ===================
if st.button("🔍 Найти блогеров"):
    if not API_KEY:
        st.error("❌ API ключ не найден! Проверь файл .env (YOUTUBE_API_KEY=...)")
    elif not keywords:
        st.error("❌ Введи хотя бы одно ключевое слово!")
    else:
        youtube = build_client(API_KEY)

        all_channels: Dict[str, str] = {}
        progress = st.progress(0)
        status = st.empty()

        # 1) Поиск каналов по ключам (с пагинацией)
        for idx, kw in enumerate(keywords, start=1):
            status.write(f"🔎 Поиск по ключу «{kw}» ({idx}/{len(keywords)}) …")
            found = search_channels_by_keyword(
                youtube, kw,
                max_pages=int(max_pages_per_keyword),
                max_channels=int(max_channels_per_keyword),
            )
            # объединяем глобально
            for ch_id, title in found.items():
                all_channels.setdefault(ch_id, title)

            progress.progress(int(idx / max(1, len(keywords)) * 33))  # до ~33%

        if not all_channels:
            st.warning("😕 Ничего не найдено по ключевым словам. Попробуй другие ключи или увеличь пагинацию.")
            st.stop()

        # 2) Тянем статистику каналов батчами
        status.write(f"📦 Получаю статистику каналов (всего {len(all_channels)}) …")
        stats_map = fetch_channels_stats(youtube, list(all_channels.keys()))
        progress.progress(60)

        # 3) Базовые фильтры по каналу
        base_pass_ids = []
        for ch_id, tpl in stats_map.items():
            subs, total_views, _country, _uploads = tpl
            if min_subs <= subs <= max_subs and total_views >= min_views_total:
                base_pass_ids.append(ch_id)

        if not base_pass_ids:
            st.warning("😕 Ни один канал не прошёл фильтры по подписчикам/total просмотрам.")
            st.stop()

        # 4) Средние просмотры за период + фильтр дубликатов из загруженной базы
        results: List[Dict] = []
        skipped_existing = 0

        for i, ch_id in enumerate(base_pass_ids, start=1):
            title = all_channels.get(ch_id, ch_id)

            # исключаем, если уже есть в твоей базе
            if ch_id in existing_ids:
                skipped_existing += 1
                # обновим прогресс от 60% к 100% с учётом пропуска
                progress.progress(60 + int(40 * i / max(1, len(base_pass_ids))))
                continue

            subs, total_views, country, uploads_pid = stats_map[ch_id]
            status.write(f"⏱️ {i}/{len(base_pass_ids)} • Считаю средние за {int(period_days)} дн. для: {title}")
            avg_views, n_vids = get_avg_views_for_period(
                youtube, uploads_pid, int(period_days), max_fetch=int(max_recent_uploads_fetch)
            )

            if avg_views is None or avg_views < int(min_avg_views_period):
                progress.progress(60 + int(40 * i / max(1, len(base_pass_ids))))
                continue

            results.append({
                "Канал": title,
                "Подписчики": subs,
                "Просмотры (total)": total_views,
                f"Средние за {int(period_days)} дн.": avg_views,
                f"Видео за {int(period_days)} дн.": n_vids,
                "Страна": country,
                "Ссылка": f"https://www.youtube.com/channel/{ch_id}",
                "channel_id": ch_id,  # удобно сохранять для будущих исключений
            })

            progress.progress(60 + int(40 * i / max(1, len(base_pass_ids))))

        status.empty()
        progress.empty()

        # 5) Вывод и выгрузка
        if results:
            df = pd.DataFrame(results)
            df.drop_duplicates(subset=["channel_id"], inplace=True)
            sort_col = f"Средние за {int(period_days)} дн."
            df.sort_values(by=[sort_col, "Подписчики"], ascending=[False, False], inplace=True)

            msg = f"✅ Найдено {len(df)} новых каналов"
            if uploaded_file is not None:
                msg += f" (исключено как дубликаты: {skipped_existing})"
            st.success(msg)

            st.dataframe(df.drop(columns=["channel_id"]), use_container_width=True)

            excel_file = "bloggers.xlsx"
            df.to_excel(excel_file, index=False)
            with open(excel_file, "rb") as f:
                st.download_button(
                    label="📥 Скачать Excel",
                    data=f,
                    file_name="bloggers.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            if uploaded_file is not None and skipped_existing > 0:
                st.warning("Все кандидаты оказались в загруженной базе. Попробуй другие ключи или ослабь фильтры.")
            else:
                st.warning("😕 По заданным условиям ничего не найдено. Ослабь фильтры или увеличь период/страницы поиска.")

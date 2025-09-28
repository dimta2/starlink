# StarLinker v. 1.4
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

# =============== PAGE CONFIG ===============
st.set_page_config(page_title="StarLinker", page_icon="🔎", layout="wide")
st.title("🔎 StarLinker — Поиск блогеров на YouTube (v1.4)")

# =============== API KEY ===============
load_dotenv()
API_KEY = st.secrets.get("YOUTUBE_API_KEY") or os.getenv("YOUTUBE_API_KEY")

def build_client():
    if not API_KEY:
        return None
    return build("youtube", "v3", developerKey=API_KEY)

# =============== HELPERS ===============
UC_RE = re.compile(r"(UC[0-9A-Za-z_-]{20,})", re.I)

def chunked(seq: List[str], n: int) -> Iterable[List[str]]:
    for i in range(0, len(seq), n):
        yield seq[i:i+n]

def iso_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def extract_uc_id(s: str) -> Optional[str]:
    """Достаёт UC-id из строки (из любой формы URL/текста)."""
    if not isinstance(s, str):
        return None
    s = s.strip()
    m = UC_RE.search(s)
    if m:
        return m.group(1)
    # youtube.com/channel/UC...
    m2 = re.search(r"channel/(UC[0-9A-Za-z_-]{20,})", s, re.I)
    if m2:
        return m2.group(1)
    return None

def extract_handle(s: str, treat_bare_names: bool = False) -> Optional[str]:
    """Возвращает handle без @ (строчные), если его можно извлечь из строки."""
    if not isinstance(s, str):
        return None
    s0 = s.strip()

    # 1) @handle где угодно
    m = re.search(r"@([A-Za-z0-9._-]{3,})", s0)
    if m:
        return m.group(1).lower()

    # 2) youtube.com/@handle
    m = re.search(r"youtube\.com/\@([A-Za-z0-9._-]{3,})", s0, re.I)
    if m:
        return m.group(1).lower()

    # 3) youtube.com/c/<name> или /user/<name> → считаем как handle-кандидат
    m = re.search(r"youtube\.com/(?:c|user)/([A-Za-z0-9._-]{3,})", s0, re.I)
    if m:
        return m.group(1).lower()

    # 4) просто слово (по желанию)
    if treat_bare_names:
        token = re.sub(r"\s+", "", s0)
        token = token.split("/")[0].strip(".")
        if re.fullmatch(r"[A-Za-z0-9._-]{3,}", token):
            return token.lower()

    return None

_RESOLVE_CACHE: Dict[str, Optional[str]] = {}

def resolve_handle_to_channel_id(youtube, handle: str) -> Optional[str]:
    """Пытаемся найти channel_id по handle/кастомному URL. Возвращает UC-id или None."""
    if handle in _RESOLVE_CACHE:
        return _RESOLVE_CACHE[handle]

    if not youtube:
        _RESOLVE_CACHE[handle] = None
        return None

    try:
        # Ищем каналы по названию/handle
        sres = youtube.search().list(
            q=handle,
            part="snippet",
            type="channel",
            maxResults=10
        ).execute()
        ch_ids = [it["snippet"]["channelId"] for it in sres.get("items", []) if it.get("snippet")]
        if not ch_ids:
            _RESOLVE_CACHE[handle] = None
            return None

        # Тянем snippet каналов, чтобы сверить customUrl
        cres = youtube.channels().list(
            part="snippet",
            id=",".join(ch_ids[:50])
        ).execute()

        # Сначала ищем точное совпадение customUrl с handle
        for it in cres.get("items", []):
            sn = it.get("snippet", {})
            custom = (sn.get("customUrl") or "").lstrip("@").lower()
            if custom and custom == handle.lower():
                _RESOLVE_CACHE[handle] = it["id"]
                return it["id"]

        # Если точного нет — возьмём первый из поиска как наилучшее предположение
        _RESOLVE_CACHE[handle] = ch_ids[0]
        return ch_ids[0]

    except HttpError:
        _RESOLVE_CACHE[handle] = None
        return None

def normalize_existing_ids_from_df(
    youtube,
    df: pd.DataFrame,
    treat_bare_names: bool,
    do_normalize: bool,
    max_to_normalize: int
) -> Tuple[set, dict]:
    """
    Возвращает (existing_ids_set, stats_dict)
    Сначала берём все UC-id из явного столбца channel_id и ссылок /channel/UC…,
    затем по желанию нормализуем handle/custom URL → UC-id.
    """
    cols_lower = {c.lower(): c for c in df.columns}
    existing_ids: set = set()
    stats = {"taken_channel_id": 0, "extracted_from_url": 0, "normalized": 0, "unresolved": 0}

    # 1) явный столбец channel_id
    cid_col = None
    for k, orig in cols_lower.items():
        if k == "channel_id" or k.endswith("channel_id") or k == "id":
            cid_col = orig
            break
    if cid_col:
        for v in df[cid_col].dropna():
            uc = extract_uc_id(str(v))
            if uc:
                existing_ids.add(uc)
                stats["taken_channel_id"] += 1

    # 2) ссылки (Ссылка/Link/URL/…)
    link_col = None
    if not cid_col:
        for k, orig in cols_lower.items():
            if any(key in k for key in ["ссыл", "link", "url"]):
                link_col = orig
                break
    if link_col:
        for v in df[link_col].dropna():
            s = str(v)
            uc = extract_uc_id(s)
            if uc:
                existing_ids.add(uc)
                stats["extracted_from_url"] += 1

    # 3) нормализация handle/custom URL → UC-id
    if do_normalize:
        # Соберём все кандидаты-строки
        candidates: List[str] = []
        # Берём либо link-колонку, либо всю строку если нет
        source_cols = [cid_col] if cid_col else ([link_col] if link_col else list(df.columns))
        seen_raw = set()
        for c in source_cols:
            if not c:
                continue
            for v in df[c].dropna():
                s = str(v)
                if s in seen_raw:
                    continue
                seen_raw.add(s)
                # пропускаем, если уже UC найден
                if extract_uc_id(s):
                    continue
                # выделяем handle
                h = extract_handle(s, treat_bare_names=treat_bare_names)
                if h:
                    candidates.append(h)

        # ограничение по квоте
        to_norm = list(dict.fromkeys(candidates))[: max_to_normalize]  # uniq + cut
        resolved = 0
        prog = st.progress(0)
        status = st.empty()
        for i, h in enumerate(to_norm, start=1):
            status.write(f"🔁 Нормализация handle → channel_id: @{h} ({i}/{len(to_norm)})")
            uc = resolve_handle_to_channel_id(youtube, h)
            if uc:
                if uc not in existing_ids:
                    existing_ids.add(uc)
                resolved += 1
            prog.progress(int(i / max(1, len(to_norm)) * 100))
        prog.empty()
        status.empty()

        stats["normalized"] = resolved
        stats["unresolved"] = max(0, len(to_norm) - resolved)

    return existing_ids, stats

# =============== SIDEBAR ===============
with st.sidebar:
    st.header("⚙️ Параметры поиска")
    max_pages_per_keyword = st.number_input("Макс. страниц на ключ (по 50 видео)",
        min_value=1, max_value=10, value=3, step=1)
    max_channels_per_keyword = st.number_input("Ограничение каналов на ключ",
        min_value=10, max_value=5000, value=500, step=10)
    max_recent_uploads_fetch = st.number_input("Макс. загруженных видео на канал (для среднего за период)",
        min_value=20, max_value=500, value=150, step=10)

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
        "Загрузите Excel/CSV (со столбцом 'channel_id' или ссылками)", type=["xlsx", "csv"])

    normalize_handles = st.checkbox("Нормализовать @handle / /c/ /user/ в channel_id (рекомендуется)", True)
    treat_bare_names = st.checkbox("Считать голые имена как handle (может давать ложные совпадения)", False)
    max_to_normalize = st.number_input("Лимит на нормализацию (шт.)", min_value=50, max_value=5000, value=800, step=50)

# =============== INPUT ===============
keywords_input = st.text_area("Ключевые слова (по одному в строке)")
keywords = [kw.strip() for kw in keywords_input.splitlines() if kw.strip()]

st.caption("ℹ️ Теперь дубликаты исключаются по настоящему channel_id. "
           "Если в базе были @handle или custom URL, включи нормализацию в сайдбаре.")

# =============== SEARCH/ANALYTICS ===============
def search_channels_by_keyword(youtube, keyword: str, max_pages: int, max_channels: int) -> Dict[str, str]:
    channel_map: Dict[str, str] = {}
    page_token: Optional[str] = None
    pages = 0
    while True:
        try:
            resp = youtube.search().list(
                q=keyword, part="snippet", type="video", maxResults=50, pageToken=page_token
            ).execute()
        except HttpError as e:
            st.warning(f"⚠️ Ошибка поиска по ключу «{keyword}»: {e}")
            break
        for it in resp.get("items", []):
            sn = it.get("snippet") or {}
            ch_id = sn.get("channelId")
            ch_title = sn.get("channelTitle")
            if ch_id and ch_id not in channel_map:
                channel_map[ch_id] = ch_title or ch_id
                if len(channel_map) >= max_channels:
                    return channel_map
        page_token = resp.get("nextPageToken")
        pages += 1
        if not page_token or pages >= max_pages:
            break
    return channel_map

def fetch_channels_stats(youtube, channel_ids: List[str]) -> Dict[str, Tuple[int, int, str, str]]:
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

def iter_recent_upload_video_ids(youtube, uploads_playlist_id: str, since_dt: datetime, max_fetch: int) -> Iterable[str]:
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
                return
            if fetched >= max_fetch:
                return
        page_token = pl.get("nextPageToken")
        if not page_token:
            return

def get_avg_views_for_period(youtube, uploads_playlist_id: str, days: int, max_fetch: int) -> Tuple[Optional[int], int]:
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

# =============== MAIN BUTTON ===============
if st.button("🔍 Найти блогеров"):
    if not API_KEY:
        st.error("❌ API ключ не найден! Вставь YOUTUBE_API_KEY в Settings → Secrets (Streamlit Cloud).")
        st.stop()
    if not keywords:
        st.error("❌ Введи хотя бы одно ключевое слово!")
        st.stop()

    youtube = build_client()

    # === 0) Загрузка и нормализация базы для исключения ===
    existing_ids: set = set()
    stats_norm = {"taken_channel_id": 0, "extracted_from_url": 0, "normalized": 0, "unresolved": 0}
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith(".csv"):
                df_existing = pd.read_csv(uploaded_file)
            else:
                df_existing = pd.read_excel(uploaded_file)

            existing_ids, stats_norm = normalize_existing_ids_from_df(
                youtube,
                df_existing,
                treat_bare_names=treat_bare_names,
                do_normalize=normalize_handles,
                max_to_normalize=int(max_to_normalize),
            )
            st.info(
                f"📂 База для исключения: {len(existing_ids)} channel_id\n"
                f"• явные channel_id: {stats_norm['taken_channel_id']}\n"
                f"• из ссылок /channel/UC…: {stats_norm['extracted_from_url']}\n"
                f"• нормализовано из handle/custom: {stats_norm['normalized']}\n"
                f"• не распознано: {stats_norm['unresolved']}"
            )
        except Exception as e:
            st.warning(f"⚠️ Не удалось прочитать базу: {e}")

    # === 1) Поиск каналов по ключам (с пагинацией) ===
    all_channels: Dict[str, str] = {}
    progress = st.progress(0)
    status = st.empty()

    for idx, kw in enumerate(keywords, start=1):
        status.write(f"🔎 Поиск по ключу «{kw}» ({idx}/{len(keywords)}) …")
        found = search_channels_by_keyword(
            youtube, kw,
            max_pages=int(max_pages_per_keyword),
            max_channels=int(max_channels_per_keyword),
        )
        for ch_id, title in found.items():
            all_channels.setdefault(ch_id, title)
        progress.progress(int(idx / max(1, len(keywords)) * 20))  # до 20%

    if not all_channels:
        st.warning("😕 Ничего не найдено по ключам. Попробуй другие ключи или увеличь пагинацию.")
        st.stop()

    # Предварительно исключим уже имеющиеся каналы (экономим квоту)
    before = len(all_channels)
    all_channels = {cid: t for cid, t in all_channels.items() if cid not in existing_ids}
    pre_excluded = before - len(all_channels)

    if pre_excluded:
        st.caption(f"🧹 Предварительно исключено по базе: {pre_excluded} канал(ов).")

    # === 2) Тянем статистику каналов батчами ===
    status.write(f"📦 Получаю статистику каналов (всего кандидатов: {len(all_channels)}) …")
    stats_map = fetch_channels_stats(youtube, list(all_channels.keys()))
    progress.progress(60)

    # === 3) Базовые фильтры ===
    base_pass_ids = []
    for ch_id, tpl in stats_map.items():
        subs, total_views, _country, _uploads = tpl
        if min_subs <= subs <= max_subs and total_views >= min_views_total:
            base_pass_ids.append(ch_id)

    if not base_pass_ids:
        st.warning("😕 Ни один канал не прошёл фильтры по подписчикам/total просмотрам.")
        st.stop()

    # Исключаем по базе повторно на всякий случай
    base_pass_ids = [cid for cid in base_pass_ids if cid not in existing_ids]

    # === 4) Средние просмотры за период ===
    results: List[Dict] = []
    for i, ch_id in enumerate(base_pass_ids, start=1):
        title = all_channels.get(ch_id, ch_id)
        subs, total_views, country, uploads_pid = stats_map[ch_id]
        status.write(f"⏱️ {i}/{len(base_pass_ids)} • Считаю средние за {int(period_days)} дн.: {title}")
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
            "channel_id": ch_id,
        })
        progress.progress(60 + int(40 * i / max(1, len(base_pass_ids))))

    status.empty()
    progress.empty()

    # === 5) Вывод ===
    if results:
        df = pd.DataFrame(results)
        df.drop_duplicates(subset=["channel_id"], inplace=True)
        sort_col = f"Средние за {int(period_days)} дн."
        df.sort_values(by=[sort_col, "Подписчики"], ascending=[False, False], inplace=True)

        st.success(
            f"✅ Найдено {len(df)} новых каналов "
            f"(после исключения {len(existing_ids)} из базы и предфильтра {pre_excluded})."
        )
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
        st.warning("😕 По заданным условиям ничего не найдено (после исключения дубликатов/фильтров). "
                   "Ослабь фильтры, увеличь период или выключи нормализацию для теста.")

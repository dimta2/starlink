import os
os.environ["STREAMLIT_SERVER_FILEWATCHER_TYPE"] = "none"

import streamlit as st
import pandas as pd

from starlinker.config import get_api_key
from starlinker.youtube_client import get_youtube_client
from starlinker.search import search_channels_by_keyword
from starlinker.channel_stats import fetch_channels_stats, get_avg_views_for_period
from starlinker.dedupe import load_existing_ids
from starlinker.quota import init_budget, set_budget, used, budget

st.set_page_config(page_title="StarLinker", page_icon="🔎", layout="wide")
st.title("🔎 StarLinker — Поиск блогеров на YouTube")

API_KEY = get_api_key()
if not API_KEY:
    st.error("❌ Не найден YOUTUBE_API_KEY. В Cloud добавь в Settings → Secrets.")
    st.stop()

init_budget()

with st.sidebar:
    st.header("⚙️ Поиск")
    max_pages_per_keyword = st.number_input("Страниц на ключ (x50 видео)", 1, 5, 2)  # безопаснее по умолчанию
    max_channels_per_keyword = st.number_input("Лимит каналов на ключ", 10, 1000, 200)
    max_recent_uploads_fetch = st.number_input("Видео на канал для среднего", 20, 200, 80, 10)
    direct_channel_search = st.checkbox("Искать по каналам напрямую (type=channel)", False)

    st.markdown("---")
    st.header("📊 Фильтры")
    min_subs = st.number_input("Мин. подписчиков", value=1_000, step=500)
    max_subs = st.number_input("Макс. подписчиков", value=500_000, step=1_000)
    min_views_total = st.number_input("Мин. просмотров (total)", value=10_000, step=1_000)
    period_days = st.number_input("Период для среднего (дней)", 1, 90, 30)
    min_avg_views_period = st.number_input("Мин. средние просмотры за период", value=2_000, step=100)

    st.markdown("---")
    st.header("🗂️ База для исключения")
    uploaded_file = st.file_uploader("Загрузи Excel/CSV (channel_id/Ссылка/Link/URL/handle)", type=["xlsx", "csv"])
    normalize_handles = st.checkbox("Нормализовать @handle → channel_id (дорого!)", False)  # по умолчанию ВЫКЛ
    treat_bare_names = st.checkbox("Считать голые имена как handle", False)
    max_to_normalize = st.number_input("Лимит нормализации", 0, 500, 50, 10)

    st.markdown("---")
    st.header("⛽ Квота YouTube (юниты)")
    b = st.number_input("Бюджет на запуск", 500, 10000, 3000, 100)
    set_budget(b)
    st.caption("search.list = 100 u; channels/videos/playlistItems = 1 u. "
               "При превышении — процесс остановится с сообщением.")

    st.markdown("---")
    debug_mode = st.checkbox("Режим отладки", True)

keywords_input = st.text_area("Ключевые слова (по одному в строке)")
keywords = [k.strip() for k in keywords_input.splitlines() if k.strip()]

if st.button("🔍 Найти блогеров"):
    try:
        if not keywords:
            st.error("❌ Введи хотя бы одно ключевое слово!")
            st.stop()

        yt = get_youtube_client(API_KEY)

        # 0) existing_ids / existing_handles
        existing_ids = set()
        existing_handles = set()
        stats_norm = {}
        if uploaded_file is not None:
            try:
                df_old = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
                from starlinker.dedupe import load_existing_ids as _load
                existing_ids, existing_handles, stats_norm = _load(
                    yt, df_old,
                    treat_bare_names=treat_bare_names,
                    do_normalize=normalize_handles,
                    max_to_normalize=int(max_to_normalize)
                )
                if debug_mode:
                    st.info(
                        f"📂 База: {len(existing_ids)} по channel_id, {len(existing_handles)} по handle. "
                        f"Нормализовано: {stats_norm.get('normalized',0)}."
                    )
            except Exception as e:
                st.warning(f"⚠️ Не удалось прочитать базу: {e}")

        # 1) поиск
        all_channels = {}
        prog = st.progress(0); stat = st.empty()
        for i, kw in enumerate(keywords, start=1):
            stat.write(f"🔎 Поиск «{kw}» ({i}/{len(keywords)}) …")
            found = search_channels_by_keyword(
                yt, kw,
                max_pages=max_pages_per_keyword,
                max_channels=max_channels_per_keyword,
                by_channel=direct_channel_search
            )
            if debug_mode:
                st.caption(f"• найдено по «{kw}»: {len(found)} каналов (квота использована: {used()}/{budget()})")
            for cid, title in found.items():
                all_channels.setdefault(cid, title)
            prog.progress(int(i / len(keywords) * 20))

        if not all_channels:
            st.warning("Ничего не найдено на этапе поиска.")
            st.stop()

        # 1.1) исключить по id до статистики
        before = len(all_channels)
        all_channels = {cid: t for cid, t in all_channels.items() if cid not in existing_ids}
        if debug_mode:
            st.caption(f"🧹 Исключено по channel_id: {before - len(all_channels)}")

        # 2) статистика каналов
        stat.write(f"📦 Статистика каналов ({len(all_channels)}) …")
        stats_map = fetch_channels_stats(yt, list(all_channels.keys()))
        prog.progress(55)
        if debug_mode:
            st.caption(f"• статистика получена: {len(stats_map)} (квота: {used()}/{budget()})")

        # 2.1) исключение по handle (customUrl)
        def _norm(x: str | None) -> str:
            return (x or "").lstrip("@").lower()
        if existing_handles:
            drop_ids = [cid for cid, s in stats_map.items() if _norm(s.get("custom_url")) in existing_handles]
            for cid in drop_ids:
                stats_map.pop(cid, None); all_channels.pop(cid, None)
            if debug_mode and drop_ids:
                st.caption(f"🧹 Исключено по handle: {len(drop_ids)}")

        # 3) фильтры
        base_pass = [
            cid for cid, s in stats_map.items()
            if s.get("uploads_playlist_id")
            and (min_subs <= s.get("subs", 0) <= max_subs)
            and (s.get("total_views", 0) >= min_views_total)
        ]
        if debug_mode:
            st.caption(f"• прошло фильтр подписчики/total: {len(base_pass)}")

        if not base_pass:
            st.warning("Никто не прошёл фильтры по подписчикам/просмотрам.")
            st.stop()

        # 4) средние за период
        rows = []
        for i, cid in enumerate(base_pass, start=1):
            title = all_channels.get(cid, cid)
            s = stats_map[cid]
            stat.write(f"⏱️ {i}/{len(base_pass)} • Средние за {period_days} дн.: {title}")
            avg, count = get_avg_views_for_period(yt, s["uploads_playlist_id"], period_days, max_recent_uploads_fetch)
            if avg is None or avg < min_avg_views_period:
                prog.progress(60 + int(40 * i / len(base_pass)))
                continue
            rows.append({
                "Канал": title,
                "Подписчики": s["subs"],
                "Просмотры_total": s["total_views"],
                "Средние_за_дни": avg,
                "Видео_за_дни": count,
                "Страна": s["country"],
                "Ссылка": f"https://www.youtube.com/channel/{cid}",
                "channel_id": cid
            })
            if debug_mode and i % 5 == 0:
                st.caption(f"• квота: {used()}/{budget()}")
            prog.progress(60 + int(40 * i / len(base_pass)))

        stat.empty(); prog.empty()

        if rows:
            df = pd.DataFrame(rows).drop_duplicates(subset=["channel_id"])
            df = df.sort_values(by=["Средние_за_дни", "Подписчики"], ascending=[False, False])
            st.success(f"✅ Найдено {len(df)} новых каналов • Квота израсходована: {used()}/{budget()} юнитов")
            st.dataframe(df.drop(columns=["channel_id"]), use_container_width=True)
            xlsx = "bloggers.xlsx"
            df.to_excel(xlsx, index=False)
            with open(xlsx, "rb") as f:
                st.download_button("📥 Скачать Excel", f, file_name="bloggers.xlsx")
        else:
            st.warning("После финальных фильтров ничего не осталось.")
    except RuntimeError as e:
        st.error(f"⛽ Достигнут лимит квоты: {e}")

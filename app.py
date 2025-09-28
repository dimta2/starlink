# Starlinker Rolling build B280925A

import streamlit as st
import pandas as pd
from starlinker.config import get_api_key
from starlinker.youtube_client import get_youtube_client
from starlinker.search import search_channels_by_keyword
from starlinker.channel_stats import fetch_channels_stats, get_avg_views_for_period
from starlinker.dedupe import load_existing_ids

st.set_page_config(page_title="StarLinker", page_icon="🔎", layout="wide")
st.title("🔎 StarLinker — Поиск блогеров на YouTube Rolling")

API_KEY = get_api_key()
if not API_KEY:
    st.error("❌ Не найден YOUTUBE_API_KEY. В Cloud добавь в Settings → Secrets.")
    st.stop()

with st.sidebar:
    st.header("⚙️ Поиск")
    max_pages_per_keyword = st.number_input("Страниц на ключ (x50 видео)", 1, 10, 3)
    max_channels_per_keyword = st.number_input("Лимит каналов на ключ", 10, 5000, 500)
    max_recent_uploads_fetch = st.number_input("Видео на канал для среднего", 20, 500, 150, 10)

    st.markdown("---")
    st.header("📊 Фильтры")
    min_subs = st.number_input("Мин. подписчиков", value=1_000, step=500)
    max_subs = st.number_input("Макс. подписчиков", value=500_000, step=1_000)
    min_views_total = st.number_input("Мин. просмотров (total)", value=10_000, step=1_000)
    period_days = st.number_input("Период для среднего (дней)", 1, 90, 30)
    min_avg_views_period = st.number_input("Мин. средние просмотры за период", value=2_000, step=100)

    st.markdown("---")
    st.header("🗂️ База для исключения")
    uploaded_file = st.file_uploader("Загрузи Excel/CSV (channel_id/Ссылка/Link/URL)", type=["xlsx", "csv"])
    normalize_handles = st.checkbox("Нормализовать @handle / /c/ /user/ → channel_id", True)
    treat_bare_names = st.checkbox("Считать голые имена как handle", False)
    max_to_normalize = st.number_input("Лимит нормализации", 50, 5000, 800, 50)

keywords_input = st.text_area("Ключевые слова (по одному в строке)")
keywords = [k.strip() for k in keywords_input.splitlines() if k.strip()]

if st.button("🔍 Найти блогеров"):
    if not keywords:
        st.error("❌ Введи хотя бы одно ключевое слово!")
        st.stop()

    yt = get_youtube_client(API_KEY)

    # 0) existing_ids
    existing_ids = set(); stats_norm = {}
    if uploaded_file is not None:
        try:
            df_old = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
            existing_ids, stats_norm = load_existing_ids(
                yt, df_old, treat_bare_names=treat_bare_names,
                do_normalize=normalize_handles, max_to_normalize=int(max_to_normalize)
            )
            st.info(
                f"📂 Исключаем {len(existing_ids)} каналов из базы "
                f"(channel_id: {stats_norm.get('taken_channel_id',0)}, "
                f"из URL: {stats_norm.get('extracted_from_url',0)}, "
                f"нормализовано: {stats_norm.get('normalized',0)}, "
                f"не распознано: {stats_norm.get('unresolved',0)})"
            )
        except Exception as e:
            st.warning(f"⚠️ Не удалось прочитать базу: {e}")

    # 1) по ключам
    all_channels = {}
    prog = st.progress(0); stat = st.empty()
    for i, kw in enumerate(keywords, start=1):
        stat.write(f"🔎 Поиск «{kw}» ({i}/{len(keywords)}) …")
        found = search_channels_by_keyword(yt, kw, max_pages_per_keyword, max_channels_per_keyword)
        for cid, title in found.items():
            all_channels.setdefault(cid, title)
        prog.progress(int(i / len(keywords) * 25))

    if not all_channels:
        st.warning("Ничего не найдено. Попробуй другие ключи/больше страниц.")
        st.stop()

    # экономия квоты — выкинуть уже известные до stats
    before = len(all_channels)
    all_channels = {cid: t for cid, t in all_channels.items() if cid not in existing_ids}
    st.caption(f"🧹 Предварительно исключено {before - len(all_channels)} каналов из базы")

    # 2) батч-статистика
    stat.write(f"📦 Статистика каналов ({len(all_channels)}) …")
    stats_map = fetch_channels_stats(yt, list(all_channels.keys()))
    prog.progress(65)

    # 3) фильтр подписчики/total
    base_pass = [cid for cid, s in stats_map.items()
                 if s["uploads_playlist_id"]
                 and (min_subs <= s["subs"] <= max_subs)
                 and (s["total_views"] >= min_views_total)]
    if not base_pass:
        st.warning("Никто не прошёл фильтры по подписчикам/просмотрам.")
        st.stop()

    # safety: убрать снова известных (если загрузка случилась позже)
    base_pass = [cid for cid in base_pass if cid not in existing_ids]

    # 4) средние за период
    rows = []
    for i, cid in enumerate(base_pass, start=1):
        title = all_channels.get(cid, cid)
        s = stats_map[cid]
        stat.write(f"⏱️ {i}/{len(base_pass)} • Средние за {period_days} дн.: {title}")
        avg, count = get_avg_views_for_period(yt, s["uploads_playlist_id"], period_days, max_recent_uploads_fetch)
        if avg is None or avg < min_avg_views_period:
            prog.progress(65 + int(35 * i / len(base_pass)))
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
        prog.progress(65 + int(35 * i / len(base_pass)))

    stat.empty(); prog.empty()

    if rows:
        df = pd.DataFrame(rows).drop_duplicates(subset=["channel_id"])
        df = df.sort_values(by=["Средние_за_дни", "Подписчики"], ascending=[False, False])
        st.success(f"✅ Найдено {len(df)} новых каналов")
        st.dataframe(df.drop(columns=["channel_id"]), use_container_width=True)

        xlsx = "bloggers.xlsx"
        df.to_excel(xlsx, index=False)
        with open(xlsx, "rb") as f:
            st.download_button("📥 Скачать Excel", f, file_name="bloggers.xlsx")
    else:
        st.warning("По заданным условиям ничего не найдено. Ослабь фильтры или увеличь период.")

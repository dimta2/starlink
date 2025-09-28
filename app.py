import os
os.environ["STREAMLIT_SERVER_FILEWATCHER_TYPE"] = "none"  # отключаем file-watcher на хостингах

import streamlit as st
import pandas as pd

from starlinker.config import get_api_key
from starlinker.youtube_client import get_youtube_client
from starlinker.search import search_channels_by_keyword
from starlinker.channel_stats import fetch_channels_stats, get_avg_views_for_period
from starlinker.dedupe import build_title_blocklist

st.set_page_config(page_title="StarLinker", page_icon="🔎", layout="wide")
st.title("🔎 StarLinker — Поиск блогеров на YouTube")

API_KEY = get_api_key()
if not API_KEY:
    st.error("❌ Не найден YOUTUBE_API_KEY. В Streamlit → Settings → Secrets добавь ключ.")
    st.stop()

with st.sidebar:
    st.subheader("🎛️ Настройки")
    intensity = st.selectbox(
        "Интенсивность поиска",
        ["Низкая (дёшево)", "Средняя (сбаланс.)", "Высокая (глубоко)"],
        index=1
    )
    # пресеты глубины/стоимости
    PRESETS = {
        "Низкая (дёшево)":  {"pages": 1, "max_ch_per_kw": 80,  "videos_for_avg": 40,  "by_channel": True},
        "Средняя (сбаланс.)": {"pages": 2, "max_ch_per_kw": 200, "videos_for_avg": 80,  "by_channel": False},
        "Высокая (глубоко)": {"pages": 3, "max_ch_per_kw": 350, "videos_for_avg": 120, "by_channel": False},
    }
    P = PRESETS[intensity]

    st.markdown("---")
    st.subheader("📊 Фильтры качества")
    min_subs = st.number_input("Мин. подписчиков", value=1_000, step=500)
    min_avg_period = st.number_input("Мин. средние просмотры за период", value=2_000, step=100)
    period_days = st.number_input("Период (дней)", 1, 90, 30)

    st.markdown("---")
    st.subheader("🗂️ База для исключения (один столбец — названия каналов)")
    uploaded_file = st.file_uploader("Загрузи Excel/CSV", type=["xlsx", "csv"])

    st.caption("Под капотом мы используем кеш и бэтчи API, чтобы экономить квоту.")

keywords_input = st.text_area("Ключевые слова (по одному в строке)")
keywords = [k.strip() for k in keywords_input.splitlines() if k.strip()]

if st.button("🔍 Найти блогеров"):
    if not keywords:
        st.error("❌ Введи хотя бы одно ключевое слово!")
        st.stop()

    yt = get_youtube_client(API_KEY)

    # 0) Читаем базу — только названия (lower/trim/схлопнутые пробелы)
    title_blocklist = set()
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith(".csv"):
                df_in = pd.read_csv(uploaded_file)
            else:
                # если в книге несколько листов — объединим
                raw = pd.read_excel(uploaded_file, sheet_name=None)
                if isinstance(raw, dict):
                    df_in = pd.concat(raw.values(), ignore_index=True, sort=False)
                else:
                    df_in = raw
            title_blocklist = build_title_blocklist(df_in)
            st.info(f"📂 Дедуп по названиям: загружено {len(title_blocklist)} каналов из базы")
        except Exception as e:
            st.warning(f"⚠️ Не удалось прочитать файл: {e}")

    # 1) Поиск каналов по ключам (в один словарь)
    all_channels: dict[str, str] = {}
    prog = st.progress(0)
    note = st.empty()
    for i, kw in enumerate(keywords, start=1):
        note.write(f"🔎 Поиск «{kw}» ({i}/{len(keywords)}) …")
        found = search_channels_by_keyword(
            yt, kw,
            max_pages=P["pages"],
            max_channels=P["max_ch_per_kw"],
            by_channel=P["by_channel"]
        )
        for cid, title in found.items():
            all_channels.setdefault(cid, title)
        prog.progress(int(i / max(1, len(keywords)) * 25))

    if not all_channels:
        st.warning("Ничего не найдено на этапе поиска (попробуй другие ключевые слова).")
        st.stop()

    # 2) Статистика каналов (батч)
    note.write(f"📦 Получаю статистику по {len(all_channels)} каналам…")
    stats = fetch_channels_stats(yt, list(all_channels.keys()))
    prog.progress(60)

    # 3) Дедуп по названию (только если база загружена)
    def norm_title(x: str | None) -> str:
        return " ".join((x or "").strip().lower().split())

    if title_blocklist:
        before = len(stats)
        drop_ids = [cid for cid, s in stats.items() if norm_title(s.get("title") or all_channels.get(cid)) in title_blocklist]
        for cid in drop_ids:
            stats.pop(cid, None); all_channels.pop(cid, None)
        st.caption(f"🧹 Исключено по названию из базы: {before - len(stats)}")
    prog.progress(65)

    # 4) Фильтр по подписчикам (total views убрали из простого режима)
    base_pass = [cid for cid, s in stats.items() if s.get("uploads_playlist_id") and s.get("subs", 0) >= min_subs]
    if not base_pass:
        st.warning("Никто не прошёл фильтр по подписчикам.")
        st.stop()

    # 5) Средние просмотры за период
    rows = []
    for i, cid in enumerate(base_pass, start=1):
        t = stats[cid].get("title") or all_channels.get(cid, cid)
        note.write(f"⏱️ {i}/{len(base_pass)} • Средние за {period_days} дн.: {t}")
        avg, count = get_avg_views_for_period(yt, stats[cid]["uploads_playlist_id"], period_days, P["videos_for_avg"])
        if avg is None or avg < min_avg_period:
            prog.progress(65 + int(35 * i / len(base_pass)))
            continue
        rows.append({
            "Канал": t,
            "Подписчики": stats[cid]["subs"],
            "Средние_за_дни": avg,
            "Видео_за_дни": count,
            "Страна": stats[cid]["country"],
            "Ссылка": f"https://www.youtube.com/channel/{cid}",
            "channel_id": cid
        })
        prog.progress(65 + int(35 * i / len(base_pass)))

    note.empty(); prog.empty()

    if rows:
        df = pd.DataFrame(rows).drop_duplicates(subset=["channel_id"])
        df = df.sort_values(by=["Средние_за_дни", "Подписчики"], ascending=[False, False])
        st.success(f"✅ Найдено {len(df)} каналов")
        st.dataframe(df.drop(columns=["channel_id"]), use_container_width=True)
        xlsx = "bloggers.xlsx"
        df.to_excel(xlsx, index=False)
        with open(xlsx, "rb") as f:
            st.download_button("📥 Скачать Excel", f, file_name="bloggers.xlsx")
    else:
        st.warning("По заданным условиям ничего не найдено. Ослабь фильтр «Мин. средние просмотры» или увеличь период.")

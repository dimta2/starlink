# StarLinker v. 1.0
# a tool for searching YouTube influencers
# (c)Starpets 2025

import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from dotenv import load_dotenv
import os

# Загружаем API ключ из .env
load_dotenv()
api_key = os.getenv("YOUTUBE_API_KEY")

st.title("🔎 StarLinker — Поиск блогеров на YouTube")

# Ввод ключевых слов
keywords = st.text_area("Ключевые слова (по одному в строке)").splitlines()

# Фильтры
min_subs = st.number_input("Мин. подписчиков", value=1000, step=500)
max_subs = st.number_input("Макс. подписчиков", value=500000, step=1000)
min_views = st.number_input("Мин. просмотров канала", value=10000, step=1000)

if st.button("🔍 Найти блогеров"):
    if not api_key:
        st.error("❌ API ключ не найден! Проверь файл .env")
    elif not keywords:
        st.error("❌ Введи хотя бы одно ключевое слово!")
    else:
        youtube = build("youtube", "v3", developerKey=api_key)

        results = []

        for kw in keywords:
            # Поиск видео по ключевому слову
            search_req = youtube.search().list(
                q=kw,
                part="snippet",
                type="video",
                maxResults=20
            )
            search_res = search_req.execute()

            for item in search_res["items"]:
                channel_id = item["snippet"]["channelId"]
                channel_title = item["snippet"]["channelTitle"]

                # Получаем статистику канала
                channel_req = youtube.channels().list(
                    part="statistics,snippet",
                    id=channel_id
                )
                channel_res = channel_req.execute()

                if channel_res["items"]:
                    stats = channel_res["items"][0]["statistics"]
                    snippet = channel_res["items"][0]["snippet"]

                    subs = int(stats.get("subscriberCount", 0))
                    views = int(stats.get("viewCount", 0))
                    country = snippet.get("country", "N/A")

                    if min_subs <= subs <= max_subs and views >= min_views:
                        results.append({
                            "Канал": channel_title,
                            "Подписчики": subs,
                            "Просмотры": views,
                            "Страна": country,
                            "Ссылка": f"https://www.youtube.com/channel/{channel_id}"
                        })

        if results:
            df = pd.DataFrame(results)
            df.drop_duplicates(subset=["Ссылка"], inplace=True)
            st.success(f"✅ Найдено {len(df)} блогеров")
            st.dataframe(df)

            # Скачать Excel
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
            st.warning("😕 Блогеры по заданным условиям не найдены")
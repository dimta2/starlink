# 🔎 StarLinker — Поиск YouTube-инфлюенсеров

[![Streamlit](https://img.shields.io/badge/Streamlit-🎈-FF4B4B)](https://streamlit.io/)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

Инструмент для поиска релевантных YouTube-каналов по ключевым словам с умными фильтрами: подписчики, **средние просмотры за период**, страна, выгрузка в Excel, исключение уже известных каналов (с нормализацией `@handle` → `channel_id`).

> Версия модульной структуры проекта: **v1.5 Rolling**

---

## ✨ Особенности

- **Пагинация поиска**: до N страниц × 50 видео на ключ
- **Фильтры качества**:
  - подписчики (мин/макс),
  - суммарные просмотры канала (total),
  - **средние просмотры видео за последние _X_ дней**
- **Исключение дубликатов**  
  Загрузи CSV/XLSX своей базы — приложение:
  - прочитает `channel_id` и/или ссылки вида `/channel/UC…`,
  - по желанию **нормализует `@handle` / `/c/` / `/user/` → `channel_id`** через YouTube API,
  - исключит найденные каналы до тяжёлых запросов.
- **Экспорт в Excel** (`.xlsx`)
- **Кэширование** (Streamlit cache) для экономии квоты YouTube API
- Адаптивный UI, прогресс-бар, подсказки, статистика нормализации

---

## 🧱 Технологии

- Python 3.10+
- [Streamlit](https://streamlit.io/)
- `google-api-python-client` (YouTube Data API v3)
- `pandas`, `openpyxl`
- `python-dotenv` (локально)

---

## 🚀 Быстрый старт (локально)

1) Клонируй репозиторий и установи зависимости:
```bash
python -m venv venv
# Win: venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

2) Добавь ключ в `.env` **или** в Streamlit secrets:
```env
YOUTUBE_API_KEY=ВАШ_КЛЮЧ
```

3) Запусти:
```bash
streamlit run app.py
```

Откроется браузер по адресу `http://localhost:8501`.

---

## ☁️ Деплой (Streamlit Cloud)

1. Залей проект в GitHub.
2. На [share.streamlit.io](https://share.streamlit.io) выбери репозиторий и файл `app.py`.
3. В **Settings → Secrets** добавь:
   ```
   YOUTUBE_API_KEY="ВАШ_КЛЮЧ"
   ```
4. Готово — получишь URL вида `https://<имя>.streamlit.app`.

---

## 📄 Формат загружаемой базы

Поддерживаются `.csv` и `.xlsx` с **любой** из колонок:

- `channel_id` — **лучший вариант**
- `Ссылка` / `Link` / `URL` — ссылки вида `https://www.youtube.com/channel/UC…`
- `@handle` / `/c/<name>` / `/user/<name>` — будут нормализованы в `channel_id`, если включена опция.

---

## 🧪 Идеи для развития

- Медиана просмотров за период
- Среднее по последним N видео
- Экспорт нормализованной базы (`channel_id`) из загруженного файла
- Автоперезапуск по расписанию + уведомления

---

## 📜 Лицензия

MIT — см. LICENSE.

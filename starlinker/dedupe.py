from typing import Tuple, Set, Dict, List
import pandas as pd
import streamlit as st
from .normalize import extract_uc_id, extract_handle, resolve_handle_to_channel_id

# колонки, из которых извлекаем handle/ссылки/названия
_HANDLE_LIKE_COLS = {"handle", "username", "user", "ник", "никнейм", "аккаунт", "account"}
_URL_LIKE_COLS = {"link", "url", "ссылка"}
_TITLE_LIKE_COLS = {"name", "title", "channel", "канал", "название", "имя", "channel_name", "channel title"}

def _norm_title(x: str | None) -> str:
    return " ".join((x or "").strip().lower().split())

def load_existing_ids(
    youtube,
    df: pd.DataFrame,
    treat_bare_names: bool,
    do_normalize: bool,
    max_to_normalize: int
) -> Tuple[Set[str], Set[str], Set[str], Dict[str, int]]:
    """
    Возвращает (existing_ids, existing_handles, existing_titles, stats)
    """
    stats = {"taken_channel_id": 0, "extracted_from_url": 0, "normalized": 0, "unresolved": 0, "handles": 0, "titles": 0}
    existing_ids: Set[str] = set()
    existing_handles: Set[str] = set()
    existing_titles: Set[str] = set()

    # 1) channel_id из явных колонок и из любых ссылок (ищем UC… в тексте)
    cols_lower = {c.lower(): c for c in df.columns}
    cid_col = next((orig for k, orig in cols_lower.items() if k in {"channel_id", "id"} or k.endswith("channel_id")), None)

    if cid_col:
        for v in df[cid_col].dropna():
            uc = extract_uc_id(str(v))
            if uc:
                existing_ids.add(uc); stats["taken_channel_id"] += 1

    for c in df.columns:
        for v in df[c].dropna():
            uc = extract_uc_id(str(v))
            if uc:
                existing_ids.add(uc); stats["extracted_from_url"] += 1

    # 2) handles — только из «похожих» колонок (и/или treat_bare_names)
    for c in df.columns:
        cl = c.lower()
        consider_bare = treat_bare_names or (cl in _HANDLE_LIKE_COLS)
        for v in df[c].dropna():
            h = extract_handle(str(v), treat_bare_names=consider_bare)
            if h:
                existing_handles.add(h)
    stats["handles"] = len(existing_handles)

    # 3) titles — из «похожих» колонок, включая лист raw_input
    for c in df.columns:
        cl = c.lower()
        if (cl in _TITLE_LIKE_COLS) or any(tok in cl for tok in ["title", "channel", "канал", "назв"]):
            for v in df[c].dropna():
                nt = _norm_title(str(v))
                if nt:  
                    existing_titles.add(nt)
    stats["titles"] = len(existing_titles)

    # 4) (опц.) нормализация части handle → channel_id (дорого)
    if do_normalize and existing_handles:
        uniq = list(dict.fromkeys(existing_handles))[: max_to_normalize]
        resolved = 0
        prog = st.progress(0); status = st.empty()
        for i, h in enumerate(uniq, start=1):
            status.write(f"🔁 Нормализация @{h} ({i}/{len(uniq)})")
            uc = resolve_handle_to_channel_id(youtube, h)
            if uc:
                existing_ids.add(uc); resolved += 1
            prog.progress(int(i / max(1, len(uniq)) * 100))
        prog.empty(); status.empty()
        stats["normalized"] = resolved
        stats["unresolved"] = max(0, len(uniq) - resolved)

    return existing_ids, existing_handles, existing_titles, stats

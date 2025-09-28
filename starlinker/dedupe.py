from typing import Tuple, Set, Dict, List
import pandas as pd
import streamlit as st
from .normalize import extract_uc_id, extract_handle, resolve_handle_to_channel_id

def load_existing_ids(
    youtube,
    df: pd.DataFrame,
    treat_bare_names: bool,
    do_normalize: bool,
    max_to_normalize: int
) -> Tuple[Set[str], Set[str], Dict[str, int]]:
    """
    Возвращает (existing_ids, existing_handles, stats):
      - existing_ids: множество channel_id (UC…)
      - existing_handles: множество handle (без @, lower)
      - stats: счетчики
    """
    stats = {"taken_channel_id": 0, "extracted_from_url": 0, "normalized": 0, "unresolved": 0, "handles": 0}
    existing_ids: Set[str] = set()
    existing_handles: Set[str] = set()

    cols_lower = {c.lower(): c for c in df.columns}
    cid_col = next((orig for k, orig in cols_lower.items() if k in {"channel_id", "id"} or k.endswith("channel_id")), None)
    link_col = next((orig for k, orig in cols_lower.items() if any(t in k for t in ["ссыл", "link", "url"])), None)

    # 1) явные channel_id
    if cid_col:
        for v in df[cid_col].dropna():
            uc = extract_uc_id(str(v))
            if uc:
                existing_ids.add(uc); stats["taken_channel_id"] += 1

    # 2) из ссылок: channel/UC…
    if link_col:
        for v in df[link_col].dropna():
            s = str(v)
            uc = extract_uc_id(s)
            if uc:
                existing_ids.add(uc); stats["extracted_from_url"] += 1

    # 3) собрать handle из всех колонок (включая «голые», если включено)
    #    делаем это независимо от do_normalize — для матчинга по customUrl
    for c in df.columns:
        for v in df[c].dropna():
            h = extract_handle(str(v), treat_bare_names=treat_bare_names)
            if h:
                existing_handles.add(h)
    stats["handles"] = len(existing_handles)

    # 4) (опционально) нормализовать часть handle → channel_id (экономит будущие запросы)
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

    return existing_ids, existing_handles, stats

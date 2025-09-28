from __future__ import annotations
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
) -> Tuple[Set[str], Dict[str, int]]:
    """
    Возвращает (existing_ids, stats) после:
    - прямых channel_id,
    - UC из URL,
    - (опц.) нормализации handle/custom → channel_id.
    """
    stats = {"taken_channel_id": 0, "extracted_from_url": 0, "normalized": 0, "unresolved": 0}
    existing_ids: Set[str] = set()

    cols_lower = {c.lower(): c for c in df.columns}
    cid_col = next((orig for k, orig in cols_lower.items() if k in {"channel_id", "id"} or k.endswith("channel_id")), None)
    link_col = next((orig for k, orig in cols_lower.items() if any(t in k for t in ["ссыл", "link", "url"])), None)

    if cid_col:
        for v in df[cid_col].dropna():
            uc = extract_uc_id(str(v))
            if uc:
                existing_ids.add(uc); stats["taken_channel_id"] += 1

    if link_col:
        for v in df[link_col].dropna():
            uc = extract_uc_id(str(v))
            if uc:
                existing_ids.add(uc); stats["extracted_from_url"] += 1

    # нормализация
    if do_normalize:
        candidates: List[str] = []
        source_cols = [cid_col] if cid_col else ([link_col] if link_col else list(df.columns))
        seen = set()
        for c in source_cols:
            if not c: continue
            for v in df[c].dropna():
                s = str(v)
                if s in seen: continue
                seen.add(s)
                if extract_uc_id(s):  # уже есть
                    continue
                h = extract_handle(s, treat_bare_names=treat_bare_names)
                if h: candidates.append(h)

        uniq = list(dict.fromkeys(candidates))[: max_to_normalize]
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

    return existing_ids, stats

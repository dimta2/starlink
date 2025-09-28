from __future__ import annotations
import pandas as pd

def _norm_title(x: str | None) -> str:
    """lowercase + trim + схлопывание пробелов."""
    return " ".join((x or "").strip().lower().split())

def build_title_blocklist(df: pd.DataFrame) -> set[str]:
    """
    Принимает любой CSV/XLSX. Берёт первый непустой столбец
    и делает множество нормализованных названий каналов.
    Работает и когда читаем объединённую книгу (concat листов).
    """
    if df is None or df.empty:
        return set()

    # берём первый столбец, в котором есть данные
    first_col = next((c for c in df.columns if df[c].notna().any()), None)
    if first_col is None:
        return set()

    values = (str(v) for v in df[first_col].dropna().tolist())
    return { t for v in values if (t := _norm_title(v)) }

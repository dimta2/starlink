import pandas as pd

def _norm_title(x: str | None) -> str:
    return " ".join((x or "").strip().lower().split())

def build_title_blocklist(df: pd.DataFrame) -> set[str]:
    """
    Принимает любой CSV/XLSX. Берёт первый непустой столбец и делает множество
    нормализованных названий каналов.
    """
    if df is None or df.empty:
        return set()
    # берём первый колонку с >0 ненулевых значений
    col = None
    for c in df.columns:
        if df[c].notna().sum() > 0:
            col = c
            break
    if col is None:
        return set()
    return { _norm_title(str(v)) for v in df[col].dropna() if _norm_title(str(v)) }

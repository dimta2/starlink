import streamlit as st

def init_budget(default_budget: int = 3000) -> None:
    st.session_state.setdefault("_quota_budget", default_budget)
    st.session_state.setdefault("_quota_used", 0)

def set_budget(budget: int) -> None:
    st.session_state["_quota_budget"] = max(0, int(budget))

def add(units: int, note: str = "") -> None:
    """Увеличить счётчик юнитов; если превысили бюджет — кидаем исключение."""
    used = st.session_state.get("_quota_used", 0)
    budget = st.session_state.get("_quota_budget", 0)
    new_used = used + int(units)
    if budget and new_used > budget:
        raise RuntimeError(f"Quota budget exceeded ({new_used}/{budget} units). Last op: {note}")
    st.session_state["_quota_used"] = new_used

def used() -> int:
    return st.session_state.get("_quota_used", 0)

def budget() -> int:
    return st.session_state.get("_quota_budget", 0)

from __future__ import annotations

import re

from doctransai.models.render_plan import RenderPlan, TextFill


def select_review_text_fills(plan: RenderPlan) -> list[TextFill]:
    return [fill for fill in plan.text_fills if is_risky_auto_fill(fill)]


def is_risky_auto_fill(fill: TextFill) -> bool:
    if "@" in fill.slot_id:
        return False
    if fill.target.repeat_region_id is not None:
        return False
    transform = fill.transform or ""
    if transform.startswith("agent_"):
        return False
    if fill.confidence < 0.9 or "typed_row_match" in transform or transform.startswith("unique_"):
        return True
    if "->" in transform:
        left, right = transform.split("->", 1)
        return _normalize_label(left) != _normalize_label(right)
    return False


def _normalize_label(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value).casefold()

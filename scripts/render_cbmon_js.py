# -*- coding: utf-8 -*-
"""把cbmon_candidates_new.json轉成public/index.html script區塊要貼的JS陣列文字，印出供人工比對後貼回。"""
import json
from pathlib import Path

BASE = Path(__file__).parent.parent
with open(BASE / "cbmon_candidates_new.json", encoding="utf-8") as f:
    data = json.load(f)


def fmt_date(s):
    return s.replace("/", "-") if s else ""


def render(rows):
    lines = []
    for r in rows:
        lines.append(
            f'    ["{r["code"]}","{r["name"]}",{r["gap"]},{r["conv"]},"{fmt_date(r["maturity"])}","{r["state"]}"],'
        )
    return "\n".join(lines)


print("=== candidates ===")
print(render(data["candidates"]))
print("\n=== harvested ===")
print(render(data["harvested"]))
print("\n=== outliers ===")
print(render(data["outliers"]))

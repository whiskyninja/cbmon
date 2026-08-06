# 來源註記：這是 Codex 弄的。
# -*- coding: utf-8 -*-
"""把cbmon_candidates_new.json轉成public/index.html script區塊要貼的JS陣列文字，印出供人工比對後貼回。"""
import json
import re
import shutil
from datetime import datetime
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
            f'    ["{r["code"]}","{r["name"]}",{r["gap"]},{r["conv"]},"{fmt_date(r["maturity"])}","{r["state"]}",{r.get("streak", 0)},"{r.get("streak_quality", "incomplete")}","{fmt_date(r.get("last_failed_date") or "")}",{str(bool(r.get("redemption_window_active"))).lower()},"{fmt_date(r.get("qualified_on") or "")}"],'
        )
    return "\n".join(lines)


index_path = BASE / "public" / "index.html"
html = index_path.read_text(encoding="utf-8")

for key in ("candidates", "harvested", "outliers"):
    pattern = rf"(  const {key} = \[\n).*?(\n  \];)"
    replacement = rf"\g<1>{render(data[key])}\g<2>"
    html, count = re.subn(pattern, replacement, html, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"找不到或重複找到 const {key} 區塊")

master_csv = BASE / "xq_cb_master.csv"
snapshot_date = data.get("streak_summary", {}).get("as_of") or datetime.fromtimestamp(
    master_csv.stat().st_mtime
).strftime("%Y-%m-%d")
html = re.sub(
    r"可轉債資料 20\d{2}-\d{2}-\d{2}",
    f"可轉債資料 {snapshot_date}",
    html,
)
html = re.sub(
    r"20\d{2}-\d{2}-\d{2} 單日快照",
    f"{snapshot_date} 單日快照",
    html,
    count=1,
)

backup = index_path.with_name(f"index_{datetime.now():%Y%m%d%H%M%S}.bak.html")
shutil.copy2(index_path, backup)
index_path.write_text(html, encoding="utf-8")
print(f"已更新：{index_path}")
print(f"備份：{backup}")
print(f"資料日期：{snapshot_date}")

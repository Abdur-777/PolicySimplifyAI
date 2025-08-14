# utils.py — extract structured tasks
from __future__ import annotations
import re
from typing import List, Dict, Any

_MONTHS = {"january":"01","february":"02","march":"03","april":"04","may":"05","june":"06",
           "july":"07","august":"08","september":"09","october":"10","november":"11","december":"12"}

_dd_mon = re.compile(r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b", re.I)
_annual = re.compile(r"\b(each year|annually|annual)\b", re.I)
_owner_capture = re.compile(r"(Owner)\s*[:\-–—]?\s*([^—–\-|]+)", re.I)
_due_capture   = re.compile(r"(Due)\s*[:\-–—]?\s*([^—–\-|]+)", re.I)

def _normalize_due(text: str) -> str:
    s = (text or "").strip()
    if not s: return ""
    m = _dd_mon.search(s)
    if m:
        day = int(m.group(1)); mon = _MONTHS[m.group(2).lower()]
        mmdd = f"{int(mon):02d}-{int(day):02d}"
        return f"{mmdd} (annual)" if _annual.search(s) else mmdd
    return s

def _clean_action(line: str) -> str:
    s = line.strip().lstrip("-*• ").strip()
    parts = re.split(r"\s[—–-]\s", s)
    return (parts[0] if parts else s).strip()

def extract_structured_tasks(checklist_text: str) -> List[Dict[str, Any]]:
    tasks = []
    if not checklist_text: return tasks
    for raw in checklist_text.splitlines():
        s = raw.strip()
        if not s: continue
        if not (s.startswith(("-", "*", "•")) or s[:1].isdigit()): continue
        owner = ""; due = ""
        o = _owner_capture.search(s);  d = _due_capture.search(s)
        if o: owner = o.group(2).strip(" .;")
        if d: due = _normalize_due(d.group(2))
        action = _clean_action(s)
        tasks.append({"action": action, "owner": owner, "due": due})
    return tasks

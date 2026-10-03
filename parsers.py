"""Pure parsing helpers for Game Hours. No Qt, and nothing here ever writes a file.

Parser rule #1: never crash, never drop a line. Every item keeps its raw line;
anything that cannot be parsed is kept raw with empty fields.
"""
from __future__ import annotations

import codecs
import datetime as dt
import json
import re
from dataclasses import dataclass, field
from typing import Iterable

EARLIER = "Earlier"
IN_PROGRESS = "In progress"


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------
def decode_bytes(data: bytes) -> str:
    """utf-8-sig, then utf-16 if it has a BOM, then cp1257."""
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1257", errors="replace")


def read_text(path) -> str:
    with open(path, "rb") as f:  # read-only
        return decode_bytes(f.read())


def split_lines(text: str) -> list[str]:
    return re.split(r"\r\n|\r|\n", text)


def normalize(name: str) -> str:
    """Lowercase, strip non-alphanumerics (Unicode-aware, so CJK is kept)."""
    return re.sub(r"[\W_]+", "", name.lower())


def fmt_num(x: float, digits: int = 2) -> str:
    return f"{x:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{x:.0f}"


def fmt_minutes(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    if h and m:
        return f"{h}h {m}m"
    return f"{h}h" if h else f"{m}m"


# --------------------------------------------------------------------------
# hour log.txt
# --------------------------------------------------------------------------
@dataclass
class HourEntry:
    raw: str
    name: str = ""
    hours: float | None = None
    note: str = ""


_NUM = re.compile(r"\d+(?:\.\d+)?[hH]?")
_MAIN_END = re.compile(r"\(|\t| {3,}| ---")
_TOKEN = re.compile(r"\S+")


def _is_num(tok: str) -> bool:
    return _NUM.fullmatch(tok) is not None


def parse_hour_line(raw: str) -> HourEntry:
    entry = HourEntry(raw=raw)
    s = raw.strip().strip("*").strip()
    m = _MAIN_END.search(s)
    main = s[: m.start()] if m else s

    toks = [(t.group(), t.start(), t.end()) for t in _TOKEN.finditer(main)]
    seen_num = False
    for i, (t, _, _) in enumerate(toks):
        if _is_num(t):
            seen_num = True
        elif seen_num and any(c.isalpha() for c in t):
            toks = toks[:i]
            break
    if not toks:
        entry.note = s
        return entry

    nums = [i for i, (t, _, _) in enumerate(toks) if _is_num(t)]
    if nums and nums[-1] > 0:
        i = nums[-1]
        entry.hours = float(toks[i][0].rstrip("hH"))
        entry.name = main[toks[0][1]: toks[i - 1][2]].strip("* ")
        entry.note = s[toks[i][2]:].strip()
        return entry
    if nums:  # only a leading number, no name: unparseable, keep raw
        return entry

    # No hours token ("hades steamhrs+10"): name stops at the first "+" token.
    j = next((i for i in range(1, len(toks)) if "+" in toks[i][0]), len(toks))
    entry.name = main[toks[0][1]: toks[j - 1][2]].strip("* ")
    entry.note = s[toks[j - 1][2]:].strip()
    return entry


def parse_hours(text: str) -> list[HourEntry]:
    out = []
    for raw in split_lines(text):
        if not raw.strip():
            continue
        try:
            out.append(parse_hour_line(raw))
        except Exception:
            out.append(HourEntry(raw=raw))
    return out


# --------------------------------------------------------------------------
# fxgameanalasys.txt
# --------------------------------------------------------------------------
@dataclass
class ProgressItem:
    raw: str
    section: str
    name: str = ""
    percent: int | None = None
    hours: float | None = None
    note: str = ""


@dataclass
class Section:
    label: str
    items: list[ProgressItem] = field(default_factory=list)


@dataclass
class StoryItem:
    raw: str
    year: int | str = EARLIER
    name: str = ""
    hours: float | None = None
    estimate: bool = False
    replays: int = 0
    log_hours: float | None = None  # fallback from hour log.txt, see apply_hour_log()

    @property
    def total_hours(self) -> float | None:
        """Own hours always win; otherwise the hour-log fallback."""
        return self.hours if self.hours is not None else self.log_hours

    @property
    def from_log(self) -> bool:
        return self.hours is None and self.log_hours is not None


@dataclass
class CarItem:
    raw: str
    name: str = ""
    year: int | str = EARLIER  # EARLIER when the line has no 2-digit year
    played: int | None = None  # "x2" suffix


@dataclass
class FxData:
    sections: list[Section] = field(default_factory=lambda: [Section(IN_PROGRESS)])
    story: list[StoryItem] = field(default_factory=list)
    cars: list[CarItem] = field(default_factory=list)


_DOTS = re.compile(r"\.+")
_PCT = re.compile(r"(\d+)\s*%")
_HOURS = re.compile(r"\b(\d+(?:\.\d+)?)\s*h\b", re.I)
_REPLAY = re.compile(r"(.*?\S)\s*\+\s*(\d+)")
_TRAIL_NUM = re.compile(r"(.*\S)\s+(\d+(?:\.\d+)?)(\?)?")
_CAR_YEAR = re.compile(r"(.*\S)\s+(\d{2})")
_CAR_PLAYED = re.compile(r"(.+?)(?:\s+|(?<=\d))[xX](\d+)")
_YEAR_LINE = re.compile(r"\d{4}")


def parse_progress(raw: str, section: str) -> ProgressItem:
    item = ProgressItem(raw=raw, section=section)
    line = raw.strip()
    spans = []
    pm = _PCT.search(line)
    if pm:
        item.percent = int(pm.group(1))
        spans.append(pm.span())
    hm = _HOURS.search(line)
    if hm:
        item.hours = float(hm.group(1))
        spans.append(hm.span())
    end = min((a for a, _ in spans), default=len(line))
    item.name = re.sub(r"[\s\-]+$", "", line[:end]).strip()
    rest = line[end:]
    for a, b in sorted(spans, reverse=True):
        rest = rest[: a - end] + " " + rest[b - end:]
    item.note = " ".join(rest.split())
    return item


def parse_story(raw: str, year: int | str) -> StoryItem:
    s = raw.strip()
    item = StoryItem(raw=raw, year=year, name=s)
    m = _REPLAY.fullmatch(s)
    if m:  # "gta 5+1": the number belongs to the name, so no hours here
        item.name, item.replays = m.group(1).strip(), int(m.group(2))
        return item
    m = _TRAIL_NUM.fullmatch(s)
    if m:
        n = float(m.group(2))
        always = isinstance(year, int) and year >= 2026
        if always or 10 <= n < 1000:
            item.name, item.hours, item.estimate = m.group(1).strip(), n, bool(m.group(3))
    return item


def parse_car(raw: str) -> CarItem:
    s = raw.strip()
    item = CarItem(raw=raw, name=s)
    m = _CAR_YEAR.fullmatch(s)
    if m:
        item.name, item.year = m.group(1).strip(), 2000 + int(m.group(2))
    m = _CAR_PLAYED.fullmatch(item.name)
    if m:
        item.name, item.played = m.group(1).strip(), int(m.group(2))
    return item


def parse_fx(text: str) -> FxData:
    fx = FxData()
    section = fx.sections[0]
    finished = False
    mode = "story"
    year: int | str = EARLIER
    for raw in split_lines(text):
        line = raw.strip()
        if not line or _DOTS.fullmatch(line):
            continue
        try:
            if "---" in line:
                label = re.sub(r"-{3,}", "", line).strip(" \t-")
                finished = "finished" in label.lower()
                if finished:
                    mode, year = "story", EARLIER
                else:
                    section = Section(label or "-")
                    fx.sections.append(section)
            elif not finished:
                section.items.append(parse_progress(raw, section.label))
            elif line.lower().startswith("/story"):
                mode, year = "story", EARLIER
            elif line.lower().startswith("/cars"):
                mode = "cars"
            elif mode == "cars":
                fx.cars.append(parse_car(raw))
            elif _YEAR_LINE.fullmatch(line):
                year = int(line)
            else:
                fx.story.append(parse_story(raw, year))
        except Exception:
            if finished and mode == "cars":
                fx.cars.append(CarItem(raw=raw, name=line))
            elif finished:
                fx.story.append(StoryItem(raw=raw, year=year, name=line))
            else:
                section.items.append(ProgressItem(raw=raw, section=section.label, name=line))
    return fx


_REPLAY_WORD = re.compile(r"\s*\breplay\b.*$", re.I)


def strip_replay(name: str) -> str:
    """Drop the word "replay" and everything after it."""
    return _REPLAY_WORD.sub("", name)


def parse_aliases(text: str) -> tuple[dict[str, str], str | None]:
    """aliases.json -> ({finished name: hour log name}, error message or None)."""
    try:
        data = json.loads(text)
    except ValueError as e:
        return {}, f"aliases.json is not valid JSON: {e}"
    if not isinstance(data, dict):
        return {}, 'aliases.json must be an object like {"finished name": "hour log name"}'
    return {k: v for k, v in data.items() if isinstance(v, str)}, None


def apply_hour_log(fx: FxData, hours: Iterable[HourEntry], aliases: dict[str, str] | None = None) -> None:
    """Fill StoryItem.log_hours for finished entries that have no hours of their own.

    Finished name -> strip "replay..." -> normalize -> alias (normalized) -> exact match
    against hour log names. The first hour log line wins when a game appears twice.
    """
    amap = {normalize(k): normalize(v) for k, v in (aliases or {}).items() if normalize(k)}
    index: dict[str, HourEntry] = {}
    for e in hours:
        key = normalize(e.name)
        if key:
            index.setdefault(key, e)
    for s in fx.story:
        s.log_hours = None
        if s.hours is not None:
            continue
        key = normalize(strip_replay(s.name))
        entry = index.get(amap.get(key, key)) if key else None
        if entry is not None:
            s.log_hours = entry.hours


def year_keys(fx: FxData, extra_years: Iterable[int] = ()) -> list[int | str]:
    """["Earlier" (if used), then years ascending]."""
    years = {i.year for i in fx.story if isinstance(i.year, int)}
    years |= {i.year for i in fx.cars if isinstance(i.year, int)}
    years |= set(extra_years)
    keys: list[int | str] = sorted(years)
    if any(i.year == EARLIER for i in fx.story) or any(i.year == EARLIER for i in fx.cars):
        keys.insert(0, EARLIER)
    return keys


# --------------------------------------------------------------------------
# auto_game_sessions.txt
# --------------------------------------------------------------------------
@dataclass
class Session:
    raw: str
    date: dt.date
    start: str
    end: str
    game: str
    minutes: int


_TIME = re.compile(r"\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*")
_DURATION = re.compile(r"\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*", re.I)


def parse_duration(text: str) -> int | None:
    m = _DURATION.fullmatch(text)
    if not m or (m.group(1) is None and m.group(2) is None):
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


def parse_session_line(raw: str) -> Session | None:
    parts = raw.split("|")
    if len(parts) < 4:
        return None
    date = dt.date.fromisoformat(parts[0].strip())
    t = _TIME.fullmatch(parts[1])
    minutes = parse_duration(parts[-1])
    game = "|".join(parts[2:-1]).strip()
    if not t or minutes is None or not game:
        return None
    h1, m1, h2, m2 = (int(x) for x in t.groups())
    return Session(raw, date, f"{h1:02d}:{m1:02d}", f"{h2:02d}:{m2:02d}", game, minutes)


def parse_sessions(text: str) -> list[Session]:
    out = []
    for raw in split_lines(text):
        if not raw.strip():
            continue
        try:
            s = parse_session_line(raw)
        except Exception:
            s = None
        if s:  # malformed lines are skipped (by spec, for this file only)
            out.append(s)
    return out


# --------------------------------------------------------------------------
# Aggregates
# --------------------------------------------------------------------------
def auto_minutes_by_name(sessions: Iterable[Session]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for s in sessions:
        key = normalize(s.game)
        if key:
            totals[key] = totals.get(key, 0) + s.minutes
    return totals


def period_minutes(sessions: Iterable[Session], today: dt.date) -> tuple[int, int, int]:
    """(this ISO week, this month, this year) in minutes."""
    monday = today - dt.timedelta(days=today.weekday())
    sunday = monday + dt.timedelta(days=6)
    week = month = year = 0
    for s in sessions:
        if monday <= s.date <= sunday:
            week += s.minutes
        if (s.date.year, s.date.month) == (today.year, today.month):
            month += s.minutes
        if s.date.year == today.year:
            year += s.minutes
    return week, month, year


def top_auto_games(sessions: Iterable[Session], year: int, limit: int = 10) -> list[tuple[str, int]]:
    names: dict[str, str] = {}
    totals: dict[str, int] = {}
    for s in sessions:
        key = normalize(s.game)
        if s.date.year == year and key:
            names.setdefault(key, s.game)
            totals[key] = totals.get(key, 0) + s.minutes
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])[:limit]
    return [(names[k], m) for k, m in ranked]


def recap_text(year: int | str, fx: FxData, sessions: list[Session]) -> str:
    story = [s for s in fx.story if s.year == year]
    cars = [c for c in fx.cars if c.year == year]
    known = [s for s in story if s.total_hours is not None]
    total = sum(s.total_hours for s in known)
    approx = "~" if any(s.estimate for s in known) else ""
    missing = len(story) - len(known)

    lines = [f"Recap {year}", "", f"Story games finished: {len(story)}"]
    for s in story:
        bits = []
        if s.total_hours is not None:
            bits.append(("~" if s.estimate else "") + fmt_num(s.total_hours, 1) + "h"
                        + (" (hour log)" if s.from_log else ""))
        if s.replays:
            bits.append(f"+{s.replays} replay" + ("s" if s.replays > 1 else ""))
        lines.append(f"  - {s.name}" + (f" ({', '.join(bits)})" if bits else ""))
    lines += ["", f"Car games: {len(cars)}"]
    for c in cars:
        lines.append(f"  - {c.name}" + (f" (x{c.played})" if c.played else ""))
    lines += ["", f"Known hours: {approx}{fmt_num(total, 1)}h"
              f" ({missing} game{'s' if missing != 1 else ''} without hours)"]

    lines += ["", "Top auto-tracked games:"]
    top = top_auto_games(sessions, year) if isinstance(year, int) else []
    if top:
        lines += [f"  {i}. {name} - {fmt_minutes(m)}" for i, (name, m) in enumerate(top, 1)]
    else:
        lines.append("  (no tracked sessions)")
    return "\n".join(lines)

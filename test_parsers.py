import datetime as dt
import random

import pytest

import parsers as P

# ---------------------------------------------------------------- hour log
HOUR_CASES = [
    ("CSGO/2 4000h (total steam +800)", "CSGO/2", 4000, None),
    ("Fortnite 3539h               147 days", "Fortnite", 3539, "147 days"),
    ("Genshin 354 real (226 estimate)", "Genshin", 354, None),
    ("GTA 5 480 \t\t\t\t\t\t(259+EGS hours)", "GTA 5", 480, None),
    ("*far cry 6 62 (steam+20p1)", "far cry 6", 62, None),
    ("f1 25 47", "f1 25", 47, None),
    ("forza horizon 6 40", "forza horizon 6", 40, None),
    ("f1 manager 2024 17.5", "f1 manager 2024", 17.5, None),
    ("ETS2 20 counting from 204 steam", "ETS2", 20, None),
    ("horizon zero dawn 17.5h   \t\t\t\t9+8.5", "horizon zero dawn", 17.5, None),
    ("bl2 35 ---", "bl2", 35, None),
    ("bl3* 48", "bl3", 48, None),
    ("stalker 2 47 (steam-10)", "stalker 2", 47, None),
    ("hades steamhrs+10", "hades", None, None),
    ("wuwa egs +10", "wuwa egs", None, None),
]


@pytest.mark.parametrize("line,name,hours,note", HOUR_CASES)
def test_hour_log(line, name, hours, note):
    e = P.parse_hour_line(line)
    assert e.raw == line
    assert e.name == name
    assert e.hours == hours
    if note is not None:
        assert e.note == note


def test_hour_log_chinese_and_blank_lines():
    out = P.parse_hours("原神 354 real\n\n   \n鸣潮 120h\n")
    assert [(e.name, e.hours) for e in out] == [("原神", 354), ("鸣潮", 120)]


def test_hour_log_unparseable_keeps_raw():
    e = P.parse_hour_line("2077")
    assert e.raw == "2077" and e.name == "" and e.hours is None


# ----------------------------------------------------------- fxgameanalasys
FX = """gta IV 30%
syndicate - 5%
.....
WORK ON ------
bf4 campaign 0% previously 25%
valhalla 10h save gone
sleepign dogs
-------- MISC --------
something 50% 3h nice
-------- FINISHED --------
/story
borderlands 2
spiderman 2
2025
genshin 180
zzz 30
dark souls 3
metro 2033
ac origins 20?
gta 5+1
borderlands 2, presequel, 3+1
2026
miside 4
007 13
stalker 2 20
/cars 2020-2026
carbon 22
forza horizon 6 26
mw05x2 22
"""


@pytest.fixture(scope="module")
def fx():
    return P.parse_fx(FX)


def sec(fx, label):
    return next(s for s in fx.sections if s.label == label)


def test_sections_in_order(fx):
    assert [s.label for s in fx.sections] == ["In progress", "WORK ON", "MISC"]


def test_progress_items(fx):
    a, b = sec(fx, "In progress").items
    assert (a.name, a.percent, a.hours) == ("gta IV", 30, None)
    assert (b.name, b.percent) == ("syndicate", 5)
    items = sec(fx, "WORK ON").items
    assert (items[0].name, items[0].percent, items[0].note) == ("bf4 campaign", 0, "previously 25%")
    assert (items[1].name, items[1].hours, items[1].percent, items[1].note) == ("valhalla", 10, None, "save gone")
    assert (items[2].name, items[2].percent, items[2].hours) == ("sleepign dogs", None, None)
    m = sec(fx, "MISC").items[0]
    assert (m.name, m.percent, m.hours, m.note) == ("something", 50, 3, "nice")


def story(fx, year):
    return {s.name: s for s in fx.story if s.year == year}


def test_story_earlier(fx):
    e = story(fx, P.EARLIER)
    assert e["borderlands 2"].hours is None
    assert e["spiderman 2"].hours is None


def test_story_2025_rules(fx):
    y = story(fx, 2025)
    assert y["genshin"].hours == 180
    assert y["zzz"].hours == 30
    assert y["dark souls 3"].hours is None
    assert y["metro 2033"].hours is None
    assert (y["ac origins"].hours, y["ac origins"].estimate) == (20, True)
    assert (y["gta 5"].replays, y["gta 5"].hours) == (1, None)
    assert y["borderlands 2, presequel, 3"].replays == 1


def test_story_2026_always_hours(fx):
    y = story(fx, 2026)
    assert y["miside"].hours == 4
    assert y["007"].hours == 13
    assert y["stalker 2"].hours == 20


def test_cars(fx):
    cars = {c.name: c for c in fx.cars}
    assert cars["carbon"].year == 2022
    assert cars["forza horizon 6"].year == 2026
    assert (cars["mw05"].played, cars["mw05"].year) == (2, 2022)


def test_year_keys(fx):
    assert P.year_keys(fx) == [P.EARLIER, 2022, 2025, 2026]


def test_fx_line_accounting():
    text = "a 1%\n...\n--- X ---\nb\n--- FINISHED ---\n/story\n2026\nc 3\n/cars\nd 22\n"
    fx = P.parse_fx(text)
    n = sum(len(s.items) for s in fx.sections) + len(fx.story) + len(fx.cars)
    assert n == 4


# ----------------------------------------------------------------- sessions
def test_sessions():
    text = (
        "2026-10-03 | 23:26-23:37 | osu! | 10m\n"
        "2026-10-02 | 20:00-22:14 | Hades | 2h 14m\n"
        "2026-10-01 | 10:00-13:00 | 原神 | 3h 0m\n"
        "garbage\n"
        "2026-99-99 | 10:00-11:00 | bad date | 1h\n"
        "2026-10-03 | 10:00-11:00 | bad duration | soon\n"
    )
    s = P.parse_sessions(text)
    assert [(x.game, x.minutes) for x in s] == [("osu!", 10), ("Hades", 134), ("原神", 180)]
    assert s[0].date == dt.date(2026, 10, 3) and (s[0].start, s[0].end) == ("23:26", "23:37")


def test_name_matching_exact_normalized():
    assert P.normalize("osu!") == P.normalize("OSU") == "osu"
    assert P.normalize("GTA 5") == P.normalize("gta5")
    assert P.normalize("f1 25") != P.normalize("f1 2025")
    totals = P.auto_minutes_by_name(P.parse_sessions("2026-01-01 | 10:00-11:00 | GTA5 | 1h\n"))
    assert totals == {"gta5": 60}


def test_period_minutes():
    s = P.parse_sessions(
        "2026-10-03 | 10:00-11:00 | a | 1h\n"   # this week (Sat), month, year
        "2026-10-01 | 10:00-12:00 | a | 2h\n"   # month, year (week starts Mon 09-28 -> also week)
        "2026-09-01 | 10:00-13:00 | a | 3h\n"   # year only
        "2025-10-03 | 10:00-14:00 | a | 4h\n"   # none
    )
    assert P.period_minutes(s, dt.date(2026, 10, 3)) == (180, 180, 360)


def test_recap_text(fx):
    t = P.recap_text(2026, fx, P.parse_sessions("2026-01-01 | 10:00-12:00 | osu! | 2h\n"))
    assert "Story games finished: 3" in t
    assert "Car games: 1" in t
    assert "Known hours: 37h (0 games without hours)" in t
    assert "osu! - 2h" in t


# ----------------------------------------------------------------- encoding
TEXT = "原神 354\nčiulpk ąžuolas 12\n"


def test_encoding_utf8_bom(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(TEXT.encode("utf-8-sig"))
    assert P.read_text(p) == TEXT


def test_encoding_utf8_no_bom(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(TEXT.encode("utf-8"))
    assert P.read_text(p) == TEXT


def test_encoding_utf16_bom(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(TEXT.encode("utf-16"))  # writes BOM
    assert P.read_text(p) == TEXT
    p.write_bytes(b"\xfe\xff" + TEXT.encode("utf-16-be"))
    assert P.read_text(p) == TEXT


def test_encoding_cp1257_fallback(tmp_path):
    p = tmp_path / "a.txt"
    lt = "čiulpk ąžuolas 12\n"
    p.write_bytes(lt.encode("cp1257"))
    assert P.read_text(p) == lt


def test_chinese_survives_end_to_end(tmp_path):
    p = tmp_path / "hour log.txt"
    p.write_bytes("原神 354 real\n".encode("utf-16"))
    e = P.parse_hours(P.read_text(p))[0]
    assert (e.name, e.hours) == ("原神", 354)


# ------------------------------------------------------------ never crash
GARBAGE = [
    "", " ", "\t\t", "*", "***", "(", "()", "---", " ---", "....", "%", "50%", "h", "10h", "+", "+1", "x2",
    "|||", "||||", "2026-10-03 | | | ", "/story", "/cars", "?", "999999999999999999999999 h",
    "\x00\x01\x02", "名前 \u200b 3", "a" * 5000, "1 " * 3000, "-" * 100, "(" * 50 + "1",
    "0.0.0", "1..5h", "1e5", "\ud83c\udfae 10",
]


def _random_lines(n=300, seed=1):
    rnd = random.Random(seed)
    alphabet = "ab 1 2 5 9 0 .%+-*?()|/x h\t:\u539f\u795e,"
    return ["".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 40))) for _ in range(n)]


def test_never_crash_and_never_drop():
    lines = GARBAGE + _random_lines()
    text = "\n".join(lines)
    nonblank = [ln for ln in lines if ln.strip()]

    hours = P.parse_hours(text)
    assert [e.raw for e in hours] == [ln for ln in P.split_lines(text) if ln.strip()]
    assert len(hours) == len([ln for ln in P.split_lines(text) if ln.strip()])

    P.parse_sessions(text)

    for body in (text, "--- FINISHED ---\n/story\n" + text, "--- FINISHED ---\n/cars\n" + text):
        fx = P.parse_fx(body)
        raws = [i.raw for s in fx.sections for i in s.items] + [i.raw for i in fx.story] + [i.raw for i in fx.cars]
        assert all(isinstance(r, str) for r in raws)
        P.recap_text(2026, fx, [])
    assert nonblank  # sanity


def test_never_crash_on_garbage_bytes(tmp_path):
    rnd = random.Random(7)
    p = tmp_path / "bin.txt"
    p.write_bytes(bytes(rnd.randrange(256) for _ in range(5000)))
    text = P.read_text(p)
    P.parse_hours(text)
    P.parse_fx(text)
    P.parse_sessions(text)


# --------------------------------------------------- hour log fallback
def _fallback(fx_text, log_text, aliases=None):
    fx = P.parse_fx(fx_text)
    P.apply_hour_log(fx, P.parse_hours(log_text), aliases)
    return {s.name: s for s in fx.story}


FINISHED_2025 = "--- FINISHED ---\n/story\n2025\n"


def test_fallback_uses_hour_log_and_marks_it():
    s = _fallback(FINISHED_2025 + "hades\nsome unknown game\n", "hades 42 (steam)\n")
    assert (s["hades"].hours, s["hades"].log_hours, s["hades"].total_hours, s["hades"].from_log) == (None, 42, 42, True)
    assert s["some unknown game"].total_hours is None and not s["some unknown game"].from_log


def test_own_hours_win_over_hour_log():
    s = _fallback("--- FINISHED ---\n/story\n2026\nhades 10\n", "hades 42\n")
    assert (s["hades"].total_hours, s["hades"].from_log) == (10, False)


def test_exact_normalized_match_only():
    s = _fallback(FINISHED_2025 + "GTA 5\nf1 2024\n", "gta5 480\nf1 2025 30\n")
    assert s["GTA 5"].total_hours == 480
    assert s["f1 2024"].total_hours is None


def test_aliases():
    log = "yakuza lad 60\nsp2 20\nHonkaiSR 300\nFC5 25\nzenless zone zero 90\n"
    text = FINISHED_2025 + "Yakuza Like A Dragon\nspiderman 2\nhsr\nfar cry 5\nzzz\nunaliased\n"
    aliases = {"yakuza like a dragon": "yakuza lad", "spiderman 2": "sp2", "hsr": "HonkaiSR",
               "far cry 5": "FC5", "zzz": "zenless zone zero"}
    s = _fallback(text, log, aliases)
    assert [s[n].total_hours for n in ("Yakuza Like A Dragon", "spiderman 2", "hsr", "far cry 5", "zzz")] == [60, 20, 300, 25, 90]
    assert s["unaliased"].total_hours is None
    assert _fallback(FINISHED_2025 + "spiderman 2\n", log)["spiderman 2"].total_hours is None  # no alias, no match


def test_replay_word_stripped_before_matching():
    assert P.strip_replay("hades replay 2nd run") == "hades"
    assert P.strip_replay("Hades REPLAY") == "Hades"
    assert P.strip_replay("replayability") == "replayability"
    s = _fallback(FINISHED_2025 + "hades replay\nspiderman 2 replay 2\n", "hades 42\nsp2 20\n", {"spiderman 2": "sp2"})
    assert s["hades replay"].total_hours == 42
    assert s["spiderman 2 replay 2"].total_hours == 20


def test_duplicate_hour_log_uses_first_occurrence():
    s = _fallback(FINISHED_2025 + "hades\n", "hades 42\nhades 99\n")
    assert s["hades"].total_hours == 42


def test_hour_log_entry_without_hours_gives_no_fallback():
    s = _fallback(FINISHED_2025 + "hades\n", "hades steamhrs+10\n")
    assert s["hades"].total_hours is None


def test_recap_includes_fallback_hours():
    fx = P.parse_fx("--- FINISHED ---\n/story\n2026\nhades\nmiside 4\nnohours\n")
    P.apply_hour_log(fx, P.parse_hours("hades 42\n"))
    t = P.recap_text(2026, fx, [])
    assert "hades (42h (hour log))" in t
    assert "Known hours: 46h (1 game without hours)" in t


def test_parse_aliases():
    assert P.parse_aliases('{"a": "b", "c": 3}') == ({"a": "b"}, None)
    assert P.parse_aliases("{bad")[1]
    assert P.parse_aliases("[1]")[1]


def test_seed_aliases_file():
    import pathlib
    aliases, err = P.parse_aliases(P.read_text(pathlib.Path(__file__).parent / "aliases.json"))
    assert err is None
    assert aliases["hsr"] == "HonkaiSR" and aliases["ac origins"] == "aco" and len(aliases) == 13

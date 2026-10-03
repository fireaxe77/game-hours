"""Game Hours - read-only viewer for the game log files on the Desktop."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCharts import (QAbstractBarSeries, QBarCategoryAxis, QBarSeries, QBarSet, QChart,
                              QChartView, QValueAxis)
from PySide6.QtCore import QEvent, QMargins, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPen
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
                               QProgressBar, QPushButton, QScrollArea, QSplitter,
                               QStyledItemDelegate, QTableWidget, QTableWidgetItem,
                               QTabWidget, QTextEdit, QVBoxLayout, QWidget,
                               QAbstractItemView)

import parsers as P

FILES = {
    "fx": ("fxgameanalasys.txt", "Game progress log"),
    "hours": ("hour log.txt", "Hour log"),
    "sessions": ("auto_game_sessions.txt", "Auto session log"),
}

HERE = Path(__file__).resolve().parent

BG, PANEL, ALT, HOVER = "#1E1F22", "#2B2D31", "#303338", "#383B41"
TEXT, MUTED, BORDER = "#DBDEE1", "#949BA4", "#3A3C42"
ACCENT, ACCENT_LIGHT, ACCENT_SEL = "#7C5CFF", "#B7A5FF", "#4A3E99"
ROW_HEIGHT = 28

STYLE = """
* { font-family: "Segoe UI"; font-size: 10pt; }
QWidget { background: %BG%; color: %TEXT%; }
QLabel { background: transparent; }
QLabel#Title { font-size: 14pt; font-weight: 600; }
QScrollArea { border: none; }

QTabWidget::pane { border: none; }
QTabBar { background: transparent; }
QTabBar::tab { background: transparent; color: %MUTED%; padding: 10px 16px; margin-right: 4px;
               border: none; border-bottom: 2px solid transparent; }
QTabBar::tab:hover { color: %TEXT%; }
QTabBar::tab:selected { color: %TEXT%; border-bottom: 2px solid %ACCENT%; }

QPushButton { background: %PANEL%; color: %TEXT%; border: none; border-radius: 8px; padding: 8px 16px; }
QPushButton:hover { background: %HOVER%; }
QPushButton:pressed { background: %BORDER%; }
QPushButton#Accent { background: %ACCENT%; color: #FFFFFF; font-weight: 600; }
QPushButton#Accent:hover { background: #8F74FF; }
QPushButton#Accent:pressed { background: #6A4BE6; }

QLineEdit, QComboBox { background: %PANEL%; border: 1px solid %BORDER%; border-radius: 8px;
                       padding: 7px 12px; selection-background-color: %ACCENT%; }
QLineEdit:focus, QComboBox:focus, QComboBox:on { border: 1px solid %ACCENT%; }
QComboBox::drop-down { border: none; background: transparent; width: 28px; }
QComboBox QAbstractItemView { background: %PANEL%; border: 1px solid %BORDER%; outline: 0;
                              selection-background-color: %ACCENT%; }


QFrame#Card { background: %PANEL%; border-radius: 10px; }
QLabel#CardValue { font-size: 24pt; font-weight: 600; color: %TEXT%; }
QLabel#CardLabel { color: %MUTED%; }
QFrame#Notice { background: %PANEL%; border-radius: 10px; border-left: 3px solid %ACCENT%; }
QTextEdit { background: %PANEL%; border: none; border-radius: 10px; padding: 12px; }

QTableWidget { background: %PANEL%; alternate-background-color: %ALT%; border: none; border-radius: 10px;
               gridline-color: transparent; outline: 0;
               selection-background-color: %ACCENT_SEL%; selection-color: %TEXT%; }
QTableWidget::item { padding: 0 8px; border: none; }
QTableWidget::item:selected { background: %ACCENT_SEL%; color: %TEXT%; }
QHeaderView { background: %PANEL%; border: none; }
QHeaderView::section { background: %PANEL%; color: %MUTED%; font-weight: 700; border: none;
                       padding: 6px 8px; }
QTableCornerButton::section { background: %PANEL%; border: none; }

QProgressBar { background: %BG%; border: none; border-radius: 8px; text-align: center;
               color: #FFFFFF; margin: 5px 8px; min-height: 18px; max-height: 18px; }
QProgressBar::chunk { background: %ACCENT%; border-radius: 8px; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle { background: %BORDER%; border-radius: 5px; min-height: 24px; min-width: 24px; }
QScrollBar::handle:hover { background: %MUTED%; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QSplitter::handle { background: transparent; }
QSplitter::handle:horizontal { width: 12px; }
QSplitter::handle:vertical { height: 12px; }
QToolTip { background: %PANEL%; color: %TEXT%; border: 1px solid %BORDER%; padding: 4px; }
"""
for _name, _value in (("BG", BG), ("PANEL", PANEL), ("ALT", ALT), ("HOVER", HOVER), ("TEXT", TEXT),
                      ("MUTED", MUTED), ("BORDER", BORDER), ("ACCENT_SEL", ACCENT_SEL),
                      ("ACCENT", ACCENT)):
    STYLE = STYLE.replace(f"%{_name}%", _value)


def load_icon() -> QIcon:
    icon = QIcon(str(HERE / "icon.ico"))
    return icon if not icon.isNull() else QIcon(str(HERE / "icon.png"))


# ---------------------------------------------------------------- paths / settings
def desktop_dir() -> Path:
    """The real Desktop (OneDrive-safe) via SHGetKnownFolderPath."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

            folder_id = GUID(0xB4BFCC3A, 0xDB2C, 0x424C,
                             (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41))
            fn = ctypes.windll.shell32.SHGetKnownFolderPath
            fn.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
                           ctypes.POINTER(ctypes.c_void_p)]
            ptr = ctypes.c_void_p()
            if fn(ctypes.byref(folder_id), 0, None, ctypes.byref(ptr)) == 0:
                path = ctypes.wstring_at(ptr.value)
                ctypes.windll.ole32.CoTaskMemFree(ptr)
                if path:
                    return Path(path)
        except Exception:
            pass
    return Path.home() / "Desktop"


def settings_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "GameHours" / "settings.json"


def load_settings() -> dict:
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("paths"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"paths": {}}


def save_settings(settings: dict) -> None:
    try:
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def file_path(settings: dict, key: str) -> Path:
    chosen = settings["paths"].get(key)
    return Path(chosen) if chosen else desktop_dir() / FILES[key][0]


# ---------------------------------------------------------------- data
@dataclass
class AppData:
    hours: list = field(default_factory=list)
    fx: P.FxData = field(default_factory=P.FxData)
    sessions: list = field(default_factory=list)
    problems: dict = field(default_factory=dict)  # key -> message
    alias_error: str | None = None


def load_all(settings: dict) -> AppData:
    data = AppData()
    parsers = {"hours": ("hours", P.parse_hours), "fx": ("fx", P.parse_fx),
               "sessions": ("sessions", P.parse_sessions)}
    for key, (_, label) in FILES.items():
        path = file_path(settings, key)
        try:
            text = P.read_text(path)
        except FileNotFoundError:
            data.problems[key] = f"{label} not found: {path}"
            continue
        except OSError as e:
            data.problems[key] = f"Cannot read {label} ({path}): {e}"
            continue
        attr, parse = parsers[key]
        setattr(data, attr, parse(text))

    aliases = {}
    try:
        aliases, data.alias_error = P.parse_aliases(P.read_text(HERE / "aliases.json"))
    except FileNotFoundError:
        pass
    except OSError as e:
        data.alias_error = f"Cannot read aliases.json: {e}"
    P.apply_hour_log(data.fx, data.hours, aliases)
    return data


# ---------------------------------------------------------------- widget helpers
class HoverDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.row() == self.parent().hover_row and not option.state & option.state.State_Selected:
            painter.fillRect(option.rect, QColor(HOVER))
        super().paint(painter, option, index)


class HoverTable(QTableWidget):
    """Table that highlights the whole row under the mouse."""

    def __init__(self, *args):
        super().__init__(*args)
        self.hover_row = -1
        self.setMouseTracking(True)
        self.setItemDelegate(HoverDelegate(self))

    def _set_hover(self, row):
        if row != self.hover_row:
            self.hover_row = row
            self.viewport().update()

    def mouseMoveEvent(self, e):
        self._set_hover(self.rowAt(int(e.position().y())))
        super().mouseMoveEvent(e)

    def viewportEvent(self, e):
        if e.type() == QEvent.Leave:
            self._set_hover(-1)
        return super().viewportEvent(e)


def make_table(headers, stretch_col=0) -> QTableWidget:
    t = HoverTable(0, len(headers))
    t.setShowGrid(False)
    t.setFrameShape(QFrame.NoFrame)
    t.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
    t.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setSectionResizeMode(stretch_col, QHeaderView.Stretch)
    return t


def fill_table(t: QTableWidget, rows, raws=None) -> None:
    """rows: list of value lists (str / int / float / None). raws -> tooltip on column 0."""
    t.setSortingEnabled(False)
    t.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            item = QTableWidgetItem()
            if v is not None:
                item.setData(Qt.DisplayRole, v)
            if c == 0 and raws:
                item.setToolTip(raws[r])
            t.setItem(r, c, item)


def build_chart(title, categories, sets, angle=0) -> QChart:
    """Grouped vertical bar chart. sets: [(label, values)]; angle rotates category labels."""
    chart = QChart()
    chart.setTheme(QChart.ChartThemeDark)
    chart.setTitle(title)
    series = QBarSeries()
    top = 0.0
    for label, values in sets:
        values = [float(v) for v in values]
        bar = QBarSet(label)
        bar.append(values)
        series.append(bar)
        top = max([top] + values)
    series.setLabelsVisible(True)
    series.setLabelsPosition(QAbstractBarSeries.LabelsOutsideEnd)
    series.setBarWidth(0.6)
    chart.addSeries(series)

    cat_axis = QBarCategoryAxis()
    cat_axis.append([str(c) for c in categories])
    cat_axis.setLabelsAngle(angle)
    val_axis = QValueAxis()
    val_axis.setRange(0, top * 1.1 if top else 1)
    val_axis.setLabelFormat("%d")
    val_axis.applyNiceNumbers()
    chart.addAxis(cat_axis, Qt.AlignBottom)
    chart.addAxis(val_axis, Qt.AlignLeft)
    series.attachAxis(cat_axis)
    series.attachAxis(val_axis)
    chart.legend().setVisible(len(sets) > 1)

    # styling (after adding series/axes so the theme does not override it)
    small = QFont("Segoe UI", 9)
    chart.setBackgroundBrush(QColor(PANEL))
    chart.setBackgroundPen(QPen(Qt.NoPen))
    chart.setBackgroundRoundness(10)
    chart.setMargins(QMargins(12, 12, 12, 12))
    chart.setTitleBrush(QColor(TEXT))
    chart.setTitleFont(QFont("Segoe UI", 14, QFont.DemiBold))
    chart.legend().setLabelColor(QColor(MUTED))
    chart.legend().setFont(small)
    for axis in (cat_axis, val_axis):
        axis.setLabelsColor(QColor(MUTED))
        axis.setLabelsFont(small)
        axis.setLinePen(QPen(QColor(BORDER)))
        axis.setGridLineColor(QColor(BORDER))
    cat_axis.setGridLineVisible(False)
    for bar, color in zip(series.barSets(), (ACCENT, ACCENT_LIGHT)):
        bar.setColor(QColor(color))
        bar.setBorderColor(QColor(color))
        bar.setLabelColor(QColor(TEXT))
        bar.setLabelFont(small)
    return chart


def make_chart_view() -> QChartView:
    view = QChartView()
    view.setRenderHint(QPainter.Antialiasing)
    view.setFrameShape(QFrame.NoFrame)
    view.setBackgroundBrush(QColor(BG))
    view.setMinimumHeight(260)
    return view


def fill_year_combo(combo: QComboBox, keys) -> None:
    """Keep the previous selection if still present, otherwise select the latest."""
    prev = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    for k in keys:
        combo.addItem(str(k), k)
    idx = combo.findData(prev) if prev is not None else -1
    combo.setCurrentIndex(idx if idx >= 0 else len(keys) - 1)
    combo.blockSignals(False)


def clear_layout(layout) -> None:
    while (item := layout.takeAt(0)) is not None:
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()


def make_card(caption: str):
    """Rounded panel with a big number and a small muted label. Returns (card, value_label)."""
    card = QFrame()
    card.setObjectName("Card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(16, 16, 16, 16)
    lay.setSpacing(4)
    value = QLabel("0")
    value.setObjectName("CardValue")
    value.setAlignment(Qt.AlignCenter)
    label = QLabel(caption)
    label.setObjectName("CardLabel")
    label.setAlignment(Qt.AlignCenter)
    lay.addWidget(value)
    lay.addWidget(label)
    return card, value


def group_box(title: str, widget: QWidget) -> QWidget:
    """A 14pt semibold heading above a (self-paneled) widget."""
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    heading = QLabel(title)
    heading.setObjectName("Title")
    lay.addWidget(heading)
    lay.addWidget(widget, 1)
    return box


# ---------------------------------------------------------------- tabs
class Notice(QFrame):
    def __init__(self, message):
        super().__init__()
        self.setObjectName("Notice")
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 12, 12)
        label = QLabel(message)
        label.setWordWrap(True)
        row.addWidget(label, 1)


class MissingBar(QFrame):
    def __init__(self, key, message, on_choose):
        super().__init__()
        self.setObjectName("Notice")
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 12, 12)
        label = QLabel(message)
        label.setWordWrap(True)
        row.addWidget(label, 1)
        btn = QPushButton("Choose file")
        btn.clicked.connect(lambda: on_choose(key))
        row.addWidget(btn)


class Tab(QWidget):
    """Missing-file bars on top, tab content (self.body) below."""
    keys: tuple = ()
    uses_aliases = False

    def __init__(self, win):
        super().__init__()
        self.win = win
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 12, 0, 0)
        outer.setSpacing(12)
        self.bars = QVBoxLayout()
        self.bars.setSpacing(8)
        outer.addLayout(self.bars)
        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        outer.addLayout(self.body, 1)

    def refresh(self, data: AppData) -> None:
        clear_layout(self.bars)
        for key in self.keys:
            if key in data.problems:
                self.bars.addWidget(MissingBar(key, data.problems[key], self.win.choose_file))
        if self.uses_aliases and data.alias_error:
            self.bars.addWidget(Notice(data.alias_error))
        self.populate(data)

    def populate(self, data: AppData) -> None:
        raise NotImplementedError


class HoursTab(Tab):
    keys = ("hours", "sessions")

    def __init__(self, win):
        super().__init__(win)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search game or note...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.apply_filter)
        self.body.addWidget(self.search)
        split = QSplitter(Qt.Vertical)
        self.table = make_table(["Game", "Manual hours (hour log)", "Auto tracked hours", "Note"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.view = make_chart_view()
        split.addWidget(self.table)
        split.addWidget(self.view)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        self.body.addWidget(split, 1)

    def populate(self, data):
        auto = P.auto_minutes_by_name(data.sessions)
        rows, raws = [], []
        for e in data.hours:
            minutes = auto.get(P.normalize(e.name)) if e.name else None
            rows.append([e.name or e.raw, e.hours,
                         round(minutes / 60, 2) if minutes is not None else None, e.note])
            raws.append(e.raw)
        fill_table(self.table, rows, raws)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(1, Qt.DescendingOrder)
        self.apply_filter()

        top = sorted((e for e in data.hours if e.hours is not None and e.name),
                     key=lambda e: -e.hours)[:15]
        self.view.setChart(build_chart("Top 15 by manual hours", [e.name for e in top],
                                       [("Manual hours", [e.hours for e in top])], angle=-45))

    def apply_filter(self):
        q = self.search.text().strip().lower()
        for r in range(self.table.rowCount()):
            text = " ".join(self.table.item(r, c).text() for c in (0, 3)).lower()
            self.table.setRowHidden(r, bool(q) and q not in text)


def finished_hours_text(s: P.StoryItem) -> str:
    if s.total_hours is None:
        return ""
    return ("~" if s.estimate else "") + P.fmt_num(s.total_hours, 1) + (" (hour log)" if s.from_log else "")


class FinishedTab(Tab):
    keys = ("fx", "hours")
    uses_aliases = True

    def __init__(self, win):
        super().__init__(win)
        self.fx = P.FxData()
        row = QHBoxLayout()
        row.addWidget(QLabel("Year:"))
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self.render)
        row.addWidget(self.combo)
        row.addStretch(1)
        self.body.addLayout(row)

        split = QSplitter(Qt.Horizontal)
        self.story = make_table(["Story game", "Hours", "Replays"])
        self.cars = make_table(["Car game", "Played"])
        for title, table in (("Story", self.story), ("Cars", self.cars)):
            split.addWidget(group_box(title, table))
        outer = QSplitter(Qt.Vertical)
        outer.addWidget(split)
        self.view = make_chart_view()
        outer.addWidget(self.view)
        outer.setStretchFactor(0, 3)
        outer.setStretchFactor(1, 2)
        self.body.addWidget(outer, 1)

    def populate(self, data):
        self.fx = data.fx
        keys = P.year_keys(data.fx)
        fill_year_combo(self.combo, keys)
        self.render()
        counts = [([sum(1 for s in data.fx.story if s.year == k) for k in keys]),
                  ([sum(1 for c in data.fx.cars if c.year == k) for k in keys])]
        self.view.setChart(build_chart("Finished per year", keys,
                                       [("Story", counts[0]), ("Cars", counts[1])]))

    def render(self):
        key = self.combo.currentData()
        story = [s for s in self.fx.story if s.year == key]
        cars = [c for c in self.fx.cars if c.year == key]
        fill_table(self.story, [
            [s.name, finished_hours_text(s),
             str(s.replays) if s.replays else ""] for s in story], [s.raw for s in story])
        fill_table(self.cars, [[c.name, f"x{c.played}" if c.played else ""] for c in cars],
                   [c.raw for c in cars])


class InProgressTab(Tab):
    keys = ("fx",)

    def __init__(self, win):
        super().__init__(win)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.holder = QWidget()
        self.groups = QVBoxLayout(self.holder)
        self.groups.setContentsMargins(0, 0, 0, 0)
        self.groups.setSpacing(12)
        scroll.setWidget(self.holder)
        self.body.addWidget(scroll)

    def populate(self, data):
        clear_layout(self.groups)
        for section in data.fx.sections:
            if not section.items:
                continue
            table = make_table(["Game", "Progress", "Hours", "Note"])
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
            table.setColumnWidth(1, 180)
            table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
            table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            fill_table(table, [[i.name or i.raw, None,
                                P.fmt_num(i.hours, 1) + "h" if i.hours is not None else "", i.note]
                               for i in section.items], [i.raw for i in section.items])
            for r, item in enumerate(section.items):
                if item.percent is not None:
                    bar = QProgressBar()
                    bar.setRange(0, 100)
                    bar.setValue(min(item.percent, 100))
                    bar.setFormat(f"{item.percent}%")
                    bar.setAlignment(Qt.AlignCenter)
                    table.setCellWidget(r, 1, bar)
            table.setFixedHeight(table.horizontalHeader().height() + ROW_HEIGHT * len(section.items) + 4)
            self.groups.addWidget(group_box(section.label, table))
        self.groups.addStretch(1)


class AutoLogTab(Tab):
    keys = ("sessions",)

    def __init__(self, win):
        super().__init__(win)
        cards = QHBoxLayout()
        self.values = {}
        cards.setSpacing(12)
        for name in ("This week", "This month", "This year"):
            card, value = make_card(name)
            value.setText("0m")
            cards.addWidget(card)
            self.values[name] = value
        self.body.addLayout(cards)
        self.table = make_table(["Date", "Start", "End", "Game", "Duration"], stretch_col=3)
        self.body.addWidget(self.table, 1)

    def populate(self, data):
        week, month, year = P.period_minutes(data.sessions, dt.date.today())
        for name, minutes in zip(self.values, (week, month, year)):
            self.values[name].setText(P.fmt_minutes(minutes))
        newest = sorted(data.sessions, key=lambda s: (s.date, s.start), reverse=True)
        fill_table(self.table, [[s.date.isoformat(), s.start, s.end, s.game, P.fmt_minutes(s.minutes)]
                                for s in newest], [s.raw for s in newest])


class RecapTab(Tab):
    keys = ("fx", "sessions", "hours")
    uses_aliases = True

    def __init__(self, win):
        super().__init__(win)
        self.data = AppData()
        row = QHBoxLayout()
        row.addWidget(QLabel("Year:"))
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self.render)
        row.addWidget(self.combo)
        row.addStretch(1)
        self.copy_btn = QPushButton("Copy as text")
        self.copy_btn.clicked.connect(self.copy)
        row.addWidget(self.copy_btn)
        self.body.addLayout(row)
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.cards = {}
        for name in ("Story games", "Car games", "Known hours"):
            card, value = make_card(name)
            cards.addWidget(card)
            self.cards[name] = value
        self.body.addLayout(cards)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.body.addWidget(self.text, 1)

    def populate(self, data):
        self.data = data
        fill_year_combo(self.combo, P.year_keys(data.fx, {s.date.year for s in data.sessions}))
        self.render()

    def render(self):
        key = self.combo.currentData()
        self.text.setPlainText("" if key is None else P.recap_text(key, self.data.fx, self.data.sessions))
        story = [x for x in self.data.fx.story if x.year == key]
        known = [x for x in story if x.total_hours is not None]
        approx = "~" if any(x.estimate for x in known) else ""
        self.cards["Story games"].setText(str(len(story)))
        self.cards["Car games"].setText(str(sum(1 for c in self.data.fx.cars if c.year == key)))
        self.cards["Known hours"].setText(f"{approx}{P.fmt_num(sum(x.total_hours for x in known), 1)}h")

    def copy(self):
        QApplication.clipboard().setText(self.text.toPlainText())
        self.copy_btn.setText("Copied!")
        QTimer.singleShot(1200, lambda: self.copy_btn.setText("Copy as text"))


# ---------------------------------------------------------------- window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Game Hours")
        self.setWindowIcon(load_icon())
        self.resize(1100, 760)
        self.settings = load_settings()

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        header = QHBoxLayout()
        header.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(load_icon().pixmap(32, 32))
        header.addWidget(logo)
        title = QLabel("Game Hours")
        title.setObjectName("Title")
        header.addWidget(title)
        header.addStretch(1)
        refresh = QPushButton("Refresh")
        refresh.setObjectName("Accent")
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        root.addLayout(header)

        self.tabs = QTabWidget()
        self.tab_list = []
        for cls, name in ((HoursTab, "Hours"), (FinishedTab, "Finished"), (InProgressTab, "In progress"),
                          (AutoLogTab, "Auto log"), (RecapTab, "Recap")):
            tab = cls(self)
            self.tab_list.append(tab)
            self.tabs.addTab(tab, name)
        root.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        self.refresh()

    def refresh(self):
        data = load_all(self.settings)
        for tab in self.tab_list:
            tab.refresh(data)

    def choose_file(self, key):
        _, label = FILES[key]
        current = file_path(self.settings, key)
        start = current.parent if current.parent.is_dir() else desktop_dir()
        path, _ = QFileDialog.getOpenFileName(self, f"Choose {label}", str(start),
                                              "Text files (*.txt);;All files (*)")
        if path:
            self.settings["paths"][key] = path
            save_settings(self.settings)
            self.refresh()


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    pal = QPalette()
    for role, color in (
        (QPalette.Window, BG), (QPalette.WindowText, TEXT),
        (QPalette.Base, PANEL), (QPalette.AlternateBase, ALT),
        (QPalette.Text, TEXT), (QPalette.Button, PANEL),
        (QPalette.ButtonText, TEXT), (QPalette.ToolTipBase, PANEL),
        (QPalette.ToolTipText, TEXT), (QPalette.Highlight, ACCENT),
        (QPalette.HighlightedText, "#FFFFFF"), (QPalette.PlaceholderText, MUTED),
    ):
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)


def main() -> int:
    if os.name == "nt":  # own taskbar identity, so the taskbar shows our icon, not Python's
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GameHours.App")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setWindowIcon(load_icon())
    apply_dark_theme(app)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

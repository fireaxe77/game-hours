"""Game Hours - read-only viewer for the game log files on the Desktop."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCharts import (QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView,
                              QValueAxis)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
                               QProgressBar, QPushButton, QScrollArea, QSplitter,
                               QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit,
                               QVBoxLayout, QWidget, QAbstractItemView)

import parsers as P

FILES = {
    "fx": ("fxgameanalasys.txt", "Game progress log"),
    "hours": ("hour log.txt", "Hour log"),
    "sessions": ("auto_game_sessions.txt", "Auto session log"),
}


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
    return data


# ---------------------------------------------------------------- widget helpers
def make_table(headers, stretch_col=0) -> QTableWidget:
    t = QTableWidget(0, len(headers))
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
    return chart


def make_chart_view() -> QChartView:
    view = QChartView()
    view.setRenderHint(QPainter.Antialiasing)
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


# ---------------------------------------------------------------- tabs
class MissingBar(QFrame):
    def __init__(self, key, message, on_choose):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        row = QHBoxLayout(self)
        label = QLabel(message)
        label.setWordWrap(True)
        row.addWidget(label, 1)
        btn = QPushButton("Choose file")
        btn.clicked.connect(lambda: on_choose(key))
        row.addWidget(btn)


class Tab(QWidget):
    """Missing-file bars on top, tab content (self.body) below."""
    keys: tuple = ()

    def __init__(self, win):
        super().__init__()
        self.win = win
        outer = QVBoxLayout(self)
        self.bars = QVBoxLayout()
        outer.addLayout(self.bars)
        self.body = QVBoxLayout()
        outer.addLayout(self.body, 1)

    def refresh(self, data: AppData) -> None:
        clear_layout(self.bars)
        for key in self.keys:
            if key in data.problems:
                self.bars.addWidget(MissingBar(key, data.problems[key], self.win.choose_file))
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


class FinishedTab(Tab):
    keys = ("fx",)

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
            box = QGroupBox(title)
            QVBoxLayout(box).addWidget(table)
            split.addWidget(box)
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
            [s.name, ("~" if s.estimate else "") + P.fmt_num(s.hours, 1) if s.hours is not None else "",
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
        scroll.setWidget(self.holder)
        self.body.addWidget(scroll)

    def populate(self, data):
        clear_layout(self.groups)
        for section in data.fx.sections:
            if not section.items:
                continue
            box = QGroupBox(section.label)
            lay = QVBoxLayout(box)
            table = make_table(["Game", "Progress", "Hours", "Note"])
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
            table.setColumnWidth(1, 180)
            table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
            table.verticalHeader().setDefaultSectionSize(28)
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
            table.setFixedHeight(table.horizontalHeader().height() + 28 * len(section.items) + 4)
            lay.addWidget(table)
            self.groups.addWidget(box)
        self.groups.addStretch(1)


class AutoLogTab(Tab):
    keys = ("sessions",)

    def __init__(self, win):
        super().__init__(win)
        cards = QHBoxLayout()
        self.values = {}
        for name in ("This week", "This month", "This year"):
            card = QFrame()
            card.setFrameShape(QFrame.StyledPanel)
            lay = QVBoxLayout(card)
            value = QLabel("0m")
            value.setAlignment(Qt.AlignCenter)
            value.setStyleSheet("font-size: 26px; font-weight: bold;")
            caption = QLabel(name)
            caption.setAlignment(Qt.AlignCenter)
            lay.addWidget(value)
            lay.addWidget(caption)
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
    keys = ("fx", "sessions")

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

    def copy(self):
        QApplication.clipboard().setText(self.text.toPlainText())
        self.copy_btn.setText("Copied!")
        QTimer.singleShot(1200, lambda: self.copy_btn.setText("Copy as text"))


# ---------------------------------------------------------------- window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Game Hours")
        self.resize(1100, 760)
        self.settings = load_settings()

        central = QWidget()
        root = QVBoxLayout(central)
        header = QHBoxLayout()
        title = QLabel("Game Hours")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch(1)
        refresh = QPushButton("Refresh")
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
    pal = QPalette()
    for role, color in (
        (QPalette.Window, "#2b2b2b"), (QPalette.WindowText, "#e6e6e6"),
        (QPalette.Base, "#1e1e1e"), (QPalette.AlternateBase, "#262626"),
        (QPalette.Text, "#e6e6e6"), (QPalette.Button, "#3a3a3a"),
        (QPalette.ButtonText, "#e6e6e6"), (QPalette.ToolTipBase, "#3a3a3a"),
        (QPalette.ToolTipText, "#e6e6e6"), (QPalette.Highlight, "#2f6fb5"),
        (QPalette.HighlightedText, "#ffffff"), (QPalette.PlaceholderText, "#888888"),
    ):
        pal.setColor(role, QColor(color))
    app.setPalette(pal)


def main() -> int:
    app = QApplication(sys.argv)
    apply_dark_theme(app)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

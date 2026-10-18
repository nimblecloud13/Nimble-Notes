# Copyright (c) 2026 NimbleCloud13
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Nimble Notes - one note per app, in a small desktop window you can leave open all day.
NimbleCloud13 - nimblecloud13@gmail.com - https://github.com/nimblecloud13

A native Qt window, not a browser page: no Flask, no port, nothing leaves this computer.
The apps sit in a column on the left. Each one has an editable TL;DR pane and, under it,
a separate scrolling notes pane. Everything saves itself to plain files in data/ (see store.py).
Lives in the tray. Run with pythonw (launch_nimble_notes.bat) so no console shows.
"""

import base64
import copy
import ctypes
import html
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import winreg

from PySide6.QtCore import (QByteArray, QEasingCurve, QEvent, QMimeData, QObject, QPoint, QPointF, QPropertyAnimation,
                            QRect, QRectF, QSize, Qt, QTimer, QUrl, Signal)
from PySide6.QtGui import (QColor, QCursor, QDesktopServices, QDrag, QFont, QFontDatabase, QIcon, QImage, QKeySequence, QPainter, QPalette,
                           QPen, QPolygonF,
                           QPixmap, QShortcut, QSyntaxHighlighter, QTextBlockFormat, QTextCharFormat, QTextCursor,
                           QTextDocument)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QFileDialog, QFrame, QGraphicsDropShadowEffect,
                               QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
                               QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSplitter,
                               QSplitterHandle, QStackedLayout, QStyle, QStyledItemDelegate, QSystemTrayIcon, QTextEdit,
                               QVBoxLayout, QWidget, QWidgetAction)

import media
import nimble_themes
import store
import theme as T

APP_NAME = "Nimble Notes"
VERSION = "2.7.1"
APP_DIR = store.APP_DIR
TEST = bool(os.environ.get("NIMBLE_NOTES_TEST"))  # test runs never touch the registry or start anything
LOG_PATH = os.path.join(os.path.dirname(store.DATA_DIR), "logs", "nimble_notes.log")
LOGO_PATH = os.path.join(APP_DIR, "static", "nimblecloud.png")

LINKS = [
    ("GitHub", "https://github.com/nimblecloud13"),
    ("Support", "https://buymeacoffee.com/nimblecloud13"),
]
# the small card behind the NimbleCloud13 button at the bottom left
CARD_LINKS = [
    ("GitHub", "https://github.com/nimblecloud13"),
    ("Buy me a coffee", "https://buymeacoffee.com/nimblecloud13"),
]

ROLE_KIND = Qt.UserRole
ROLE_ID = Qt.UserRole + 1
ROLE_DEPTH = Qt.UserRole + 2   # how deep a category (or a note's category) sits: drawn as an indent
CATEGORY_MIME = "application/x-nimble-category"

# how a section can be ordered: key, menu label, label once reversed, what it does
SORTS = [
    ("manual", "My order", "", "The order you dragged the rows into."),
    ("name", "A to Z", "Z to A", "By name."),
    ("created", "Created, newest first", "Created, oldest first", "By the date the app's folder was created."),
    ("recent", "Recently edited first", "Least recently edited first", "By the last time the note was changed."),
]
SORT_KEYS = [s[0] for s in SORTS]
SORT_TAG = {"manual": ("", ""), "name": ("a-z", "z-a"), "created": ("newest", "oldest"),
            "recent": ("edited", "least edited")}

# the Sort menu of a category: label, sort, reversed, what it does
NOTE_SORTS = [
    ("My order", "manual", False, "The order you dragged the notes into."),
    ("A to Z", "name", False, "By name."),
    ("Z to A", "name", True, "By name, backwards."),
    ("Oldest first", "created", True, "By when the note was made (an app's folder date for older entries)."),
    ("Newest first", "created", False, "By when the note was made, newest at the top."),
    ("Recently edited first", "recent", False, "By the last time the note was changed."),
]
CATEGORY_SORTS = [("A to Z", "name", False), ("Z to A", "name", True), ("Oldest first", "created", False),
                  ("Newest first", "created", True)]

# a done line: optional indent, optional list bullet, then "[x] "
DONE_RE = re.compile(r"^(\s*(?:[-*+]\s+)?)\[x\]\s?", re.I)
LEAD_RE = re.compile(r"^\s*(?:[-*+]\s+)?")


TOKEN_RE = re.compile(r"\w+|[^\w\s]")  # TokenLite's rule: every word and every punctuation mark is one token


# the images folder gets a pop-up each time it passes another this-many bytes: 5 GB, 10 GB, 15 GB ...
ALERT_STEP = int(os.environ.get("NIMBLE_NOTES_ALERT_BYTES") or 0) if TEST else 0
ALERT_STEP = ALERT_STEP or 5 * 1024 ** 3


def count_tokens(text):
    return len(TOKEN_RE.findall(text))


def open_lines(text):
    """How many lines of a note's open text are still to do: not blank, not ticked off with [x]."""
    return sum(1 for ln in text.split("\n") if ln.strip() and not DONE_RE.match(ln))


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg.rstrip() + "\n")
    except OSError:
        pass


def excepthook(etype, value, tb):
    log("".join(traceback.format_exception(etype, value, tb)))


def mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


# ---------------------------------------------------------------------------- Windows bits

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "NimbleNotes"
_test_autostart = [""]


def autostart_command():
    exe = sys.executable
    if os.path.basename(exe).lower() == "python.exe":
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        exe = w if os.path.exists(w) else exe
    return f'"{exe}" "{os.path.join(APP_DIR, "app.py")}" --hidden'


def autostart_get():
    if TEST:
        return _test_autostart[0]
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return str(winreg.QueryValueEx(k, RUN_NAME)[0])
    except OSError:
        return ""


def autostart_set(on):
    if TEST:
        _test_autostart[0] = autostart_command() if on else ""
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(k, RUN_NAME)
                except FileNotFoundError:
                    pass
    except OSError as ex:
        log(f"autostart: {ex}")


def claim_instance(quit_only=False):
    """One copy only. A second launch tells the first to show its window (or, with --quit, to save
    and close), then leaves. Returns None when this copy should not start."""
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    for fn in (k.CreateMutexW, k.CreateEventW, k.OpenEventW):
        fn.restype = ctypes.c_void_p
    suffix = "Test" if TEST else ""
    mutex = k.CreateMutexW(None, False, "NimbleNotesInstance" + suffix)
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        ev = k.OpenEventW(0x0002, False, ("NimbleNotesQuit" if quit_only else "NimbleNotesShow") + suffix)
        if ev:
            k.SetEvent(ctypes.c_void_p(ev))
        return None
    if quit_only:
        return None
    return (mutex, k.CreateEventW(None, False, False, "NimbleNotesShow" + suffix),
            k.CreateEventW(None, False, False, "NimbleNotesQuit" + suffix))


class InstanceSignals(QObject):
    wake = Signal()
    leave = Signal()


def watch_events(show_ev, quit_ev, sig):
    """Sleep on the show and quit events in a background thread (no CPU while waiting)."""
    k = ctypes.WinDLL("kernel32")
    k.WaitForMultipleObjects.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p), ctypes.c_int,
                                         ctypes.c_uint32]
    k.WaitForMultipleObjects.restype = ctypes.c_uint32
    handles = (ctypes.c_void_p * 2)(show_ev, quit_ev)

    def loop():
        while True:
            hit = k.WaitForMultipleObjects(2, handles, False, 0xFFFFFFFF)
            if hit == 0:
                sig.wake.emit()
            else:
                if hit == 1:
                    sig.leave.emit()
                return

    threading.Thread(target=loop, daemon=True).start()


def trim_memory():
    """Hand the RAM we are not using back to Windows. Called when the window goes to the tray."""
    try:
        k = ctypes.WinDLL("kernel32")
        k.GetCurrentProcess.restype = ctypes.c_void_p
        k.SetProcessWorkingSetSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t]
        k.SetProcessWorkingSetSize(k.GetCurrentProcess(), ctypes.c_size_t(-1).value, ctypes.c_size_t(-1).value)
    except Exception:
        pass


def colorref(hex_color):
    return int(hex_color[5:7] + hex_color[3:5] + hex_color[1:3], 16)


def dark_titlebar(win):
    """Tint the native title bar to match the sidebar (Windows 11): dark or light with the theme."""
    try:
        hwnd = ctypes.c_void_p(int(win.winId()))
        dark = 0 if T.MODE == "light" else 1
        for attr, val in ((20, dark), (35, colorref(T.BG_PANEL)), (36, colorref(T.TEXT_DIM)), (34, colorref(T.BORDER))):
            v = ctypes.c_int(val)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), 4)
    except Exception:
        pass


# ---------------------------------------------------------------------------- drawing helpers

FONTS_DIR = os.path.join(APP_DIR, "fonts")  # a copy of the shared Nimble Fonts repository (fonts.json + files)
FONT_CHOICES = []   # [{id, name, family, style, source}] once load_fonts() has run
SOURCE_TITLES = {"system": "Windows fonts", "google": "Google Fonts", "fontshare": "Fontshare"}


def load_fonts():
    """Register the bundled fonts with Qt and list every font that can be picked: the Windows ones that are
    installed and the bundled ones whose files loaded. Runs once."""
    if FONT_CHOICES:
        return FONT_CHOICES
    rows = []
    for name in ("fonts.json", "local.json"):  # local.json: fonts kept on this computer only, never published
        try:
            rows += store.read_json(os.path.join(FONTS_DIR, name), {}).get("fonts") or []
        except Exception:
            pass
    if not any(r.get("id") == "segoe-ui" for r in rows):
        rows.insert(0, {"id": "segoe-ui", "name": "Segoe UI", "source": "system", "style": "sans", "files": []})
    have = set(QFontDatabase.families())
    for r in rows:
        family = r.get("name")
        if r.get("source") == "system":
            if family not in have:
                continue
        else:
            got = []
            for rel in r.get("files") or []:
                fid = QFontDatabase.addApplicationFont(os.path.join(FONTS_DIR, *rel.split("/")[1:]))
                if fid >= 0:
                    got += QFontDatabase.applicationFontFamilies(fid)
            if not got:
                continue
            family = family if family in got else got[0]  # the family name Qt knows it by
        FONT_CHOICES.append({"id": r["id"], "name": r["name"], "family": family, "style": r.get("style", "sans"),
                             "source": r.get("source", "system")})
    return FONT_CHOICES


def font_family(font_id):
    """The family for a saved font id, or Segoe UI when the id is unknown or its files are gone."""
    for c in load_fonts():
        if c["id"] == font_id:
            return c["family"]
    return "Segoe UI"


def notes_font(px):
    f = QFont(T.NOTES_FONT)
    f.setPixelSize(px)
    return f


def gear_icon(color, size=16):
    """A small gear drawn from the theme color (no picture file, no symbol from a font)."""
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(dpr, dpr)
    p.translate(size / 2, size / 2)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    for i in range(8):
        p.save()
        p.rotate(i * 45)
        p.drawRoundedRect(QRectF(-1.6, -size * .47, 3.2, 4), 1, 1)
        p.restore()
    p.drawEllipse(QPointF(0, 0), size * .32, size * .32)
    p.setCompositionMode(QPainter.CompositionMode_Clear)
    p.drawEllipse(QPointF(0, 0), size * .13, size * .13)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return QIcon(pm)


def ui_font(px, weight=QFont.Normal, mono=False):
    f = QFont(T.MONO_FONT if mono else T.UI_FONT)
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


def lbl_font():
    f = QFont(T.UI_FONT)
    f.setPointSizeF(6.4)  # 8.5px
    f.setBold(True)
    f.setLetterSpacing(QFont.AbsoluteSpacing, 2)
    f.setCapitalization(QFont.AllUppercase)
    return f


def acc(alpha):
    """The theme's accent at some strength (0 to 255)."""
    return QColor(*T.ACCENT_RGB, int(alpha))


def on_acc(alpha=255):
    """The color for text and marks drawn on the accent."""
    c = QColor(T.ON_ACCENT)
    c.setAlpha(int(alpha))
    return c


def theme_swatch(theme_id, size=14):
    """A small square in a theme's background with a dot of its accent: shown beside each theme's name."""
    t = nimble_themes.tokens(theme_id)
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(t["BORDER_HI"]), 1))
    p.setBrush(QColor(t["BG"]))
    p.drawRoundedRect(QRectF(.5, .5, size - 1, size - 1), 3.5, 3.5)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(t["ACCENT"]))
    p.drawEllipse(QRectF(size * .3, size * .3, size * .4, size * .4))
    p.end()
    return QIcon(pm)


def pin_icon(size=14):
    """A push pin: the Pin button's mark."""
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(T.TEXT_DIM), 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    s = size
    p.drawRoundedRect(QRectF(s * .32, s * .1, s * .36, s * .34), 1.5, 1.5)   # the head
    p.drawLine(QPointF(s * .2, s * .48), QPointF(s * .8, s * .48))           # the collar
    p.drawLine(QPointF(s * .5, s * .48), QPointF(s * .5, s * .92))           # the needle
    p.end()
    return QIcon(pm)


def pin_rect(box):
    """Where the small pin sits at the right end of a row of the list."""
    return QRectF(box.right() - 22, box.center().y() - 7, 14, 14)


def pin_fits(box):
    """The pin is left out of a row too narrow for it (the tags go before it does)."""
    return box.width() >= 130


def draw_pin(p, rect, on, ink=None):
    c = QColor(ink) if ink is not None else QColor(T.ACCENT_TEXT if on else T.TEXT_MUTED)
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(c, 1.4, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(c if on else Qt.NoBrush)
    x, y, w = rect.x(), rect.y(), rect.width()
    p.drawEllipse(QRectF(x + w * .3, y + w * .04, w * .4, w * .4))
    p.drawLine(QPointF(x + w * .16, y + w * .5), QPointF(x + w * .84, y + w * .5))
    p.drawLine(QPointF(x + w * .5, y + w * .5), QPointF(x + w * .5, y + w * .98))
    p.restore()


def place_icon(size=14):
    """A little screen with its left half filled: the Place button's mark."""
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(T.TEXT_DIM), 1.2))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(1, 2, size - 2, size - 4), 2, 2)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(T.ACCENT))
    p.drawRoundedRect(QRectF(2.6, 3.6, (size - 5.2) / 2, size - 7.2), 1, 1)
    p.end()
    return QIcon(pm)


def app_icon():
    """The app's own mark, in the accent of the theme picked (the taskbar and tray icons follow it)."""
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128):
        pm = QPixmap(s, s)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.ACCENT))
        p.drawRoundedRect(QRectF(s * .06, s * .06, s * .88, s * .88), s * .2, s * .2)
        p.setPen(QPen(QColor("#13161e"), max(1.6, s * .09), Qt.SolidLine, Qt.RoundCap))
        for y, x2 in ((.34, .72), (.5, .72), (.66, .54)):
            p.drawLine(QPointF(s * .28, s * y), QPointF(s * x2, s * y))
        p.end()
        icon.addPixmap(pm)
    return icon


def make_menu(parent=None):
    m = QMenu(parent)
    m.setWindowFlags(m.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    m.setAttribute(Qt.WA_TranslucentBackground)
    m.setToolTipsVisible(True)
    return m


def show_menu(menu, at):
    """Pop a menu up at a screen position. Every menu goes through here."""
    menu.exec(at)


def button(text, tier, tip=""):
    b = QPushButton(text)
    b.setProperty("tier", tier)
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.NoFocus)
    if tip:
        b.setToolTip(tip)
    return b


def section_label(text, tip=""):
    lab = QLabel(text)
    lab.setFont(lbl_font())
    lab.setObjectName("seclabel")  # its color comes from the theme's stylesheet
    if tip:
        lab.setToolTip(tip)
    return lab


def kbd(text):
    lab = QLabel(text)
    lab.setObjectName("kbd")
    return lab


def set_lit(btn, on):
    """Light a chip button (amber) or put it back to plain."""
    if bool(btn.property("lit")) != bool(on):
        btn.setProperty("lit", bool(on))
        btn.style().unpolish(btn)
        btn.style().polish(btn)


# ---------------------------------------------------------------------------- notes editor

class DoneHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        self.fmt = QTextCharFormat()
        self.fmt.setForeground(QColor(T.TEXT_MUTED))  # greyed, clearly not live text, still easy to read

    def highlightBlock(self, text):
        if DONE_RE.match(text):
            self.setFormat(0, len(text), self.fmt)


def zoom_step(ev):
    """+1, -1 or 0 (reset) when the key press is Ctrl with plus, minus or zero. None for anything else."""
    if ev.modifiers() & ~(Qt.ShiftModifier | Qt.KeypadModifier) != Qt.ControlModifier:
        return None
    return {Qt.Key_Plus: 1, Qt.Key_Equal: 1, Qt.Key_Minus: -1, Qt.Key_Underscore: -1, Qt.Key_0: 0}.get(ev.key())


class AutoPlain(QPlainTextEdit):
    """A plain text box that is one line tall while it is empty and grows to fit its text. It stops
    growing at `cap` pixels and scrolls from there, so a long text cannot push the notes off the window."""

    def __init__(self):
        super().__init__()
        self.cap = 150
        self.manual = None  # a height set by dragging its grip, or None to grow with the text
        self.room = 10 ** 6  # the most a dragged height may take in the window as it is now
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.document().setDocumentMargin(2)
        self.textChanged.connect(self.fit)

    def lines(self):
        """How many lines the text takes on screen, wrapped lines included. At least one."""
        lay, n, block = self.document().documentLayout(), 0, self.document().firstBlock()
        while block.isValid():
            lay.blockBoundingRect(block)  # lays the block out at the width the box has now
            n += max(1, block.layout().lineCount())
            block = block.next()
        return max(1, n)

    def most(self):
        """How many lines fit before the cap; `pad` is everything in the box's height that is not a line."""
        self.ensurePolished()
        m = self.contentsMargins()
        pad = m.top() + m.bottom() + math.ceil(3 * self.document().documentMargin()) + 1
        return max(3, (self.cap - pad) // self.fontMetrics().lineSpacing()), pad

    def set_cap(self, px):
        if px != self.cap:
            self.cap = px
            self.fit()

    def fit(self):
        most, pad = self.most()
        n = self.lines()
        if self.manual is not None:  # dragged to a height: it keeps it and scrolls when the text is longer
            line = self.fontMetrics().lineSpacing()
            tall = max(line + pad, min(int(self.manual), self.room))
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if n * line + pad > tall else Qt.ScrollBarAlwaysOff)
            if tall != self.height() or tall != self.minimumHeight():
                self.setFixedHeight(tall)
            return
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if n > most else Qt.ScrollBarAlwaysOff)
        tall = min(n, most) * self.fontMetrics().lineSpacing() + pad
        if tall != self.height() or tall != self.minimumHeight():
            self.setFixedHeight(tall)
        if n <= most:
            self.verticalScrollBar().setValue(0)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.fit()


class HeightGrip(QWidget):
    """A thin bar under a box: drag it up or down to make the box shorter or taller (the notes below take
    or give the room). A double-click puts the box back to growing with its text."""
    dragged = Signal(int)   # the height wanted
    reset = Signal()

    def __init__(self, box):
        super().__init__()
        self.box = box
        self.setFixedHeight(9)
        self.setCursor(Qt.SizeVerCursor)
        self.setMouseTracking(True)
        self.setToolTip("Drag to make the Ideas box taller or shorter; the notes take the rest. "
                        "Double-click to let it grow with its text again.")
        self._from, self._h = None, 0

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._from, self._h = ev.globalPosition().y(), self.box.height()

    def mouseMoveEvent(self, ev):
        if self._from is not None and ev.buttons() & Qt.LeftButton:
            self.dragged.emit(int(self._h + ev.globalPosition().y() - self._from))

    def mouseReleaseEvent(self, ev):
        self._from = None

    def mouseDoubleClickEvent(self, ev):
        self.reset.emit()

    def enterEvent(self, ev):
        self.update()

    def leaveEvent(self, ev):
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.ACCENT if self.underMouse() else T.BORDER_HI))
        w = 34
        p.drawRoundedRect(QRectF((self.width() - w) / 2, 3, w, 3), 1.5, 1.5)
        p.end()


class AutoText(QTextEdit):
    """A text box with no scrollbar of its own that is always exactly as tall as its text. Two of these
    sit in the notes scroll area with the Revisions complete button between them, so the button moves down
    as you type, like part of the text."""
    zoom = Signal(int)

    def __init__(self, extra_lines=0):
        super().__init__()
        self.extra_lines = extra_lines
        self.setFrameShape(QFrame.NoFrame)
        self.setAcceptRichText(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(6)
        self.textChanged.connect(self.fit)

    def fit(self):
        tall = math.ceil(self.document().size().height()) + self.extra_lines * self.fontMetrics().lineSpacing()
        if tall != self.height():
            self.setFixedHeight(tall)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.fit()

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.ControlModifier:
            self.zoom.emit(1 if ev.angleDelta().y() > 0 else -1)
            ev.accept()
        else:
            ev.ignore()  # the notes pane scrolls, not this box

    def keyPressEvent(self, ev):
        step = zoom_step(ev)
        if step is not None:
            self.zoom.emit(step)
            return
        super().keyPressEvent(ev)


class WorkEdit(AutoText):
    """Where you type. One blank line is kept under the text; the picture strip and the Revisions
    complete button come after it. Pictures dropped or pasted here go to the strip, not into the text."""
    strike = Signal()
    images = Signal(object)  # pictures dropped or pasted: file paths and/or QImages

    def __init__(self):
        super().__init__(extra_lines=1)

    def canInsertFromMimeData(self, source):
        return bool(media.image_payload(source)) or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        got = media.image_payload(source)
        if got:
            self.images.emit(got)
            return
        super().insertFromMimeData(source)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_D and ev.modifiers() == Qt.ControlModifier:
            self.toggle_done()
            return
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and ev.modifiers() & Qt.ControlModifier:
            self.strike.emit()
            return
        super().keyPressEvent(ev)

    def toggle_done(self):
        """Mark the current line (or every selected line) done, or not done again. One undo step."""
        doc = self.document()
        cur = self.textCursor()
        first = doc.findBlock(cur.selectionStart()).blockNumber()
        end_block = doc.findBlock(cur.selectionEnd())
        last = end_block.blockNumber()
        if cur.hasSelection() and last > first and cur.selectionEnd() == end_block.position():
            last -= 1
        blocks = [doc.findBlockByNumber(n) for n in range(first, last + 1)]
        blocks = [b for b in blocks if b.text().strip()]
        if not blocks:
            return
        make_done = not all(DONE_RE.match(b.text()) for b in blocks)
        edit = QTextCursor(doc)
        edit.beginEditBlock()
        for b in blocks:
            text = b.text()
            m = DONE_RE.match(text)
            if make_done and not m:
                edit.setPosition(b.position() + LEAD_RE.match(text).end())
                edit.insertText("[x] ")
            elif not make_done and m:
                edit.setPosition(b.position() + len(m.group(1)))
                edit.setPosition(b.position() + m.end(), QTextCursor.KeepAnchor)
                edit.removeSelectedText()
        edit.endEditBlock()


class RevTag(QAbstractButton):
    """A revision's stamp, drawn as a small pill. The whole pill is a button, and the amber word at its
    end says what a click does."""

    def __init__(self, label, action, px):
        super().__init__()
        self.label, self.action = label, action
        f = QFont(T.MONO_FONT)
        f.setPixelSize(max(9, px - 3))
        f.setBold(True)
        self.setFont(f)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.setFixedSize(self.sizeHint())

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self.label + "    " + self.action) + 18, fm.height() + 8)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        hot = self.underMouse()
        p.setPen(QPen(QColor(T.ACCENT if hot else T.BORDER_HI), 1))
        p.setBrush(QColor(T.BG_HI if hot else T.BG_CARD))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 5, 5)
        p.setFont(self.font())
        box = QRectF(self.rect()).adjusted(9, 0, 0, 0)
        p.setPen(QColor(T.TEXT_DIM))
        p.drawText(box, Qt.AlignLeft | Qt.AlignVCenter, self.label)
        box.setLeft(box.left() + p.fontMetrics().horizontalAdvance(self.label + "    "))
        p.setPen(QColor(T.ACCENT_TEXT))
        p.drawText(box, Qt.AlignLeft | Qt.AlignVCenter, self.action)


class RevisionsView(QWidget):
    """Every revision of the note, newest first, each under its tag.

    A finished revision is greyed and read only, and its tag says Undo. Undo makes that one revision
    editable again right where it is: it gets live text in a box of its own, and its tag says
    Revisions complete. The text being typed at the top of the note is never touched by either."""
    reopen = Signal(int)
    complete = Signal(int)
    remove = Signal(int)
    edited = Signal(int, str)
    caret = Signal(object)  # the text box of a reopened revision whose caret moved
    zoom = Signal(int)
    picture = Signal(int, int)               # revision number, which of its pictures was clicked
    picture_menu = Signal(int, int, QPoint)  # the same, right-clicked, and where on screen
    picture_remove = Signal(int, int)        # the same, its x clicked
    focused = Signal(int)                    # the revision whose text was clicked into

    def __init__(self):
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(0)
        self.tags, self.bodies = {}, {}  # revision number -> its tag button / its text box, in screen order

    def show_revisions(self, revs, px, folder=""):
        """Rebuild the cards. If a reopened revision was being typed in, the caret goes back where it was.
        `folder` is the entry's images folder, where the revisions' pictures and videos are."""
        self.folder = folder
        typing = next(((n, b.textCursor().position()) for n, b in self.bodies.items() if b.hasFocus()), None)
        while self.lay.count():
            w = self.lay.takeAt(0).widget()
            if w:
                w.hide()
                w.deleteLater()
        self.tags, self.bodies = {}, {}
        self.setVisible(bool(revs))
        for i, r in enumerate(revs):
            self.lay.addWidget(self.card(r, px, i == 0))
        if typing and typing[0] in self.bodies and not self.bodies[typing[0]].isReadOnly():
            self.focus(typing[0], typing[1])

    def card(self, r, px, first):
        n, is_open = r["n"], bool(r.get("open"))
        card = QWidget()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 3 if first else 14, 0, 0)
        lay.setSpacing(4)
        if is_open:
            tag = RevTag(f"{stamp_words(r['stamp'])}  \u00b7  editing", "Completed", px)
            tag.setToolTip(f"Revision {n} is open for editing in the box below. Click here when it is done: it "
                           f"is greyed out again under the same number.")
            tag.clicked.connect(lambda: self.complete.emit(n))
        else:
            tag = RevTag(stamp_words(r["stamp"]), "Undo", px)
            tag.setToolTip(f"Undo Revisions complete for Revision {n}: it becomes editable again right here, so "
                           f"you can add to it. Your other notes are not touched.")
            tag.clicked.connect(lambda: self.reopen.emit(n))
        tag.setContextMenuPolicy(Qt.CustomContextMenu)
        tag.customContextMenuRequested.connect(lambda pos, t=tag: self.menu(n, is_open, None, t.mapToGlobal(pos)))
        row = QHBoxLayout()
        row.setContentsMargins(6, 0, 0, 0)
        row.addWidget(tag)
        row.addStretch(1)
        lay.addLayout(row)
        body = AutoText()
        body.setFont(ui_font(px))
        body.document().setDefaultFont(ui_font(px))
        body.setPlainText(r["text"])
        body.zoom.connect(self.zoom)
        if is_open:
            body.setObjectName("revopen")
            DoneHighlighter(body.document())
            body.textChanged.connect(lambda b=body: self.edited.emit(n, b.toPlainText()))
            body.cursorPositionChanged.connect(lambda b=body: self.caret.emit(b))
            box = QFrame()
            box.setObjectName("revbox")
            inner = QVBoxLayout(box)
            inner.setContentsMargins(1, 2, 4, 2)
            inner.addWidget(body)
            lay.addWidget(box)
        else:
            body.setObjectName("revdone")
            body.setReadOnly(True)
            body.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            body.setContextMenuPolicy(Qt.CustomContextMenu)
            body.customContextMenuRequested.connect(lambda pos, b=body: self.menu(n, False, b, b.mapToGlobal(pos)))
            lay.addWidget(body)
        if r.get("images"):
            strip = media.FilmStrip(live=False)
            strip.show_images([os.path.join(self.folder, name) for name in r["images"]])
            strip.opened.connect(lambda i: self.picture.emit(n, i))
            strip.menu.connect(lambda i, at: self.picture_menu.emit(n, i, at))
            strip.remove.connect(lambda i: self.picture_remove.emit(n, i))
            lay.addWidget(strip)
        body.installEventFilter(self)
        self.tags[n], self.bodies[n] = tag, body
        return card

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.FocusIn:
            n = next((k for k, b in self.bodies.items() if b is obj), 0)
            if n:
                self.focused.emit(n)
        return False

    def menu(self, n, is_open, body, at):
        m = make_menu(self)
        if body is not None and body.textCursor().hasSelection():
            m.addAction("Copy", body.copy)
        if is_open:
            m.addAction(f"Mark Revision {n} complete", lambda: self.complete.emit(n)).setToolTip(
                "Greys it out again under the same number. Same as clicking its tag.")
        else:
            m.addAction(f"Undo Revision {n} (edit it again)", lambda: self.reopen.emit(n)).setToolTip(
                "Makes this revision editable again right where it is. Same as clicking its tag.")
        m.addAction(f"Delete Revision {n}", lambda: self.remove.emit(n)).setToolTip(
            "Removes this revision from the note. A toast offers Undo.")
        show_menu(m, at)

    def focus(self, n, pos=None):
        """Put the caret in a reopened revision: at a given place, else at its end."""
        body = self.bodies.get(n)
        if body is None:
            return
        body.setFocus()
        c = body.textCursor()
        if pos is None:
            c.movePosition(QTextCursor.End)
        else:
            c.setPosition(max(0, min(pos, body.document().characterCount() - 1)))
        body.setTextCursor(c)


class EscLineEdit(QLineEdit):
    escaped = Signal()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.escaped.emit()
            return
        super().keyPressEvent(ev)


class Grip(QSplitterHandle):
    """Splitter handle. Between the TL;DR and notes panes it shows a short bar that lights up on hover."""

    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self.setAttribute(Qt.WA_Hover, True)
        if orientation == Qt.Vertical:
            self.setToolTip("Drag to make the TL;DR pane taller or shorter.")
        else:
            self.setToolTip("Drag to make the list wider or narrower.")

    def paintEvent(self, ev):
        if self.orientation() != Qt.Vertical:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.ACCENT if self.underMouse() else T.BORDER_HI))
        p.drawRoundedRect(QRectF((self.width() - 46) / 2, (self.height() - 3) / 2, 46, 3), 1.5, 1.5)


class Splitter(QSplitter):
    def createHandle(self):
        return Grip(self.orientation(), self)


class TitleLabel(QLabel):
    """The entry name. Long names are cut with an ellipsis instead of pushing the buttons off the window."""
    double_clicked = Signal()

    def mouseDoubleClickEvent(self, ev):
        self.double_clicked.emit()

    def minimumSizeHint(self):
        return QSize(90, super().minimumSizeHint().height())

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setFont(self.font())
        p.setPen(QColor(T.TEXT))
        p.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter,
                   self.fontMetrics().elidedText(self.text(), Qt.ElideRight, self.width()))


# ---------------------------------------------------------------------------- the left column

class AppDelegate(QStyledItemDelegate):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.f_name = ui_font(13)
        self.f_name_sel = ui_font(13, QFont.DemiBold)
        self.f_tag = ui_font(10)
        self.f_tag.setStyleStrategy(QFont.NoSubpixelAntialias)
        self.f_lbl = lbl_font()
        self.f_count = ui_font(10, mono=True)

    def sizeHint(self, option, index):
        return QSize(0, 30 if index.data(ROLE_KIND) == "section" else 34)

    def paint(self, p, option, index):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(option.rect)
        if index.data(ROLE_KIND) == "section":
            key = index.data(ROLE_ID)
            sec = self.win.store.section(key) or {}
            depth = int(index.data(ROLE_DEPTH) or 0)
            hov = bool(option.state & QStyle.State_MouseOver)  # a heading is a button: a click folds it
            box = r.adjusted(8 + 14 * depth, 2, -8, -2)
            folded = key in self.win.folded()
            picked = key == self.win.focus_sec
            if picked:  # the category picked last: lit like a selected note; + New adds into it
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(T.SELECT))
                p.drawRoundedRect(box, 7, 7)
                hov = True  # its text and marks in full brightness
            cx, cy = box.left() + 7, box.center().y() + 2  # the fold mark: right when folded, down when open
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.TEXT if hov else T.TEXT_MUTED))
            if folded:
                tri = [QPointF(cx - 2.5, cy - 4), QPointF(cx - 2.5, cy + 4), QPointF(cx + 3, cy)]
            else:
                tri = [QPointF(cx - 4, cy - 2.5), QPointF(cx + 4, cy - 2.5), QPointF(cx, cy + 3)]
            p.drawPolygon(QPolygonF(tri))
            right = box.right() - 4
            if pin_fits(box):
                if sec.get("pinned") or hov:
                    draw_pin(p, pin_rect(box), bool(sec.get("pinned")))
                right = box.right() - 28
            count = str(self.win.section_counts.get(key, 0))
            if key in self.win.group_counts:  # the list shows only one group: shown / all
                count = f"{self.win.group_counts[key]}/{count}"
            p.setFont(self.f_count)
            p.setPen(QColor(T.TEXT if hov else T.TEXT_MUTED))
            if box.width() >= 110:
                cw = p.fontMetrics().horizontalAdvance(count)
                p.drawText(QRectF(right - cw, box.top() + 3, cw, box.height()), Qt.AlignRight | Qt.AlignVCenter, count)
                right -= cw + 10
                tag = self.win.sort_tag(key)
                if tag and box.width() >= 190:
                    p.setFont(self.f_tag)
                    tw = p.fontMetrics().horizontalAdvance(tag)
                    p.setPen(QColor(T.ACCENT_TEXT))
                    p.drawText(QRectF(right - tw, box.top() + 3, tw, box.height()), Qt.AlignRight | Qt.AlignVCenter, tag)
                    right -= tw + 10
            p.setFont(self.f_lbl)
            p.setPen(QColor(T.TEXT if hov else T.TEXT_MUTED))
            room = QRectF(box.left() + 17, box.top() + 3, max(10, right - box.left() - 17), box.height())
            p.drawText(room, Qt.AlignLeft | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(self.win.store.section_title(key), Qt.ElideRight, int(room.width())))
            p.restore()
            return
        e = self.win.store.get(index.data(ROLE_ID))
        if not e:
            p.restore()
            return
        sel = bool(option.state & QStyle.State_Selected)
        hov = bool(option.state & QStyle.State_MouseOver)
        box = r.adjusted(8 + 14 * int(index.data(ROLE_DEPTH) or 0), 2, -8, -2)
        p.setPen(Qt.NoPen)
        pending = bool(self.win.open_n.get(e["id"]))  # its note still has open lines
        gold = sel and pending  # a selected note with pending revisions is gold; any other selected note is blue
        if sel:  # selected: a lighter, bluer navy, or the gold when the note is also pending
            fill = QColor(T.ACCENT if pending else T.SELECT)
            for grow, alpha in ((2, 18), (1, 34)):  # a soft glow of the same color, kept inside the row
                glow = QColor(fill)
                glow.setAlpha(alpha)
                p.setBrush(glow)
                p.drawRoundedRect(box.adjusted(-grow, -grow, grow, grow), 7 + grow, 7 + grow)
            p.setBrush(fill)
            p.drawRoundedRect(box, 7, 7)
        elif hov:
            p.setBrush(QColor(T.BG_HI))
            p.drawRoundedRect(box, 7, 7)
        todo = pending and not sel
        if todo:  # this note still has open lines: amber wash and an amber bar down the left edge
            p.setBrush(acc(62 if hov else 46))
            p.drawRoundedRect(box, 7, 7)
            p.setBrush(QColor(T.ACCENT))
            p.drawRoundedRect(QRectF(box.left(), box.top() + 5, 3, box.height() - 10), 1.5, 1.5)
        tag_w = 0
        pin_room = pin_fits(box)
        if pin_room:  # the pin keeps its place at the right end; it shows when pinned or under the mouse
            if e.get("pinned") or hov:
                draw_pin(p, pin_rect(box), bool(e.get("pinned")), on_acc() if gold else None)
            box = box.adjusted(0, 0, -24, 0)
        label = self.win.row_tag(e) if box.width() >= 150 else ""  # tags are the first thing a narrow row drops
        groups = self.win.group_tags.get(e["id"]) if box.width() >= 120 else None
        if groups:
            tag_w = self.paint_tags(p, box, e, label, groups, sel, gold)
        elif label:  # the tag only gets the room the full name leaves; it goes before the name is cut
            p.setFont(self.f_name_sel if sel else self.f_name)
            name_w = p.fontMetrics().horizontalAdvance(e["name"])
            room = min(box.width() - 13 - name_w - (4 if pin_room else 10) - 8 - 10, box.width() * .38)
            p.setFont(self.f_tag)
            fm = p.fontMetrics()
            if room >= min(28, fm.horizontalAdvance(label)):
                tag = fm.elidedText(label, Qt.ElideRight, int(room))
                tag_w = fm.horizontalAdvance(tag) + 8
                p.setPen(on_acc(170) if gold else QColor(T.TEXT_DIM if sel else T.TEXT_MUTED))
                p.drawText(box.adjusted(0, 0, -10, 0), Qt.AlignRight | Qt.AlignVCenter, tag)
        p.setFont(self.f_name_sel if sel else self.f_name)
        if gold:
            p.setPen(on_acc())
        elif sel:
            p.setPen(QColor(T.TEXT))
        elif todo:
            p.setPen(QColor(T.TEXT))
        else:
            p.setPen(QColor(T.TEXT if hov else T.TEXT_DIM))
        name_rect = box.adjusted(13, 0, -(tag_w + (4 if pin_room else 10)), 0)
        p.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(e["name"], Qt.ElideRight, int(name_rect.width())))
        p.restore()

    def paint_tags(self, p, box, e, label, groups, sel, gold=False):
        """The right end of a row whose note is in a group: the group's name in a small outlined tag,
        and the date tag too (when sorted by a date) if there is room for both beside the name. The name comes
        first: when it leaves no room for the group's name, a small square mark stands in for the tag.
        Returns the width taken."""
        p.setFont(self.f_name_sel if sel else self.f_name)
        avail = box.width() - 23
        room = avail - (p.fontMetrics().horizontalAdvance(e["name"]) + 4) - 8  # the full name comes first
        text = groups[0] + (f" +{len(groups) - 1}" if len(groups) > 1 else "")
        p.setFont(self.f_tag)
        fm = p.fontMetrics()
        want = {"pill": fm.horizontalAdvance(text) + 12,
                "tag": min(fm.horizontalAdvance(label), box.width() * .38) if label else 0}
        least, got = {"pill": 34, "tag": 28}, {"pill": 0, "tag": 0}
        sorted_by = self.win.sort_of(e["section"])[0] in ("created", "recent")
        for what in (("tag", "pill") if sorted_by else ("pill", "tag")):  # who gets the room first
            if want[what] and room >= least[what]:
                got[what] = min(want[what], room)
                room -= got[what] + 6
        right = box.right() - 10
        if got["tag"]:
            p.setPen(on_acc(170) if gold else QColor(T.TEXT_DIM if sel else T.TEXT_MUTED))
            p.drawText(QRectF(right - got["tag"], box.top(), got["tag"], box.height()), Qt.AlignRight | Qt.AlignVCenter,
                       fm.elidedText(label, Qt.ElideRight, int(got["tag"])))
            right -= got["tag"] + 6
        edge = on_acc(150) if gold else acc(175)
        p.setBrush(Qt.NoBrush)
        if got["pill"]:
            rect = QRectF(right - got["pill"], box.center().y() - 8, got["pill"], 16)
            p.setPen(QPen(edge, 1))
            p.drawRoundedRect(rect.adjusted(.5, .5, -.5, -.5), 5, 5)
            p.setPen(on_acc() if gold else QColor(T.ACCENT_TEXT))
            p.drawText(rect, Qt.AlignCenter, fm.elidedText(text, Qt.ElideRight, int(got["pill"] - 10)))
            right -= got["pill"] + 6
        elif box.width() >= 150 and room >= 13:  # the small mark too only where the name leaves room for it
            p.setPen(QPen(edge, 1.4))
            p.drawRoundedRect(QRectF(right - 7, box.center().y() - 3.5, 7, 7), 2, 2)
            right -= 13
        return box.right() - 10 - right


class _MSLLHOOK(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long), ("mouseData", ctypes.c_uint), ("flags", ctypes.c_uint),
                ("time", ctypes.c_uint), ("extra", ctypes.c_size_t)]


class DragWheel:
    """While a drag is held, Windows' drag loop keeps the mouse wheel away from the window. For the length of
    the drag only, a low-level mouse hook catches the wheel and scrolls the list when the pointer is over it."""

    def __init__(self, view):
        self.view, self.hook, self.proc = view, None, None

    def __enter__(self):
        if TEST or sys.platform != "win32":
            return self
        try:
            u, k = ctypes.windll.user32, ctypes.windll.kernel32
            proc_t = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)
            u.SetWindowsHookExW.restype = ctypes.c_void_p
            u.SetWindowsHookExW.argtypes = (ctypes.c_int, proc_t, ctypes.c_void_p, ctypes.c_uint)
            u.CallNextHookEx.restype = ctypes.c_ssize_t
            u.CallNextHookEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)
            u.UnhookWindowsHookEx.argtypes = (ctypes.c_void_p,)
            k.GetModuleHandleW.restype = ctypes.c_void_p
            self.u = u
            self.proc = proc_t(self.on_event)
            self.hook = u.SetWindowsHookExW(14, self.proc, k.GetModuleHandleW(None), 0)  # WH_MOUSE_LL
        except Exception as ex:
            log(f"drag wheel: {ex}")
            self.hook = None
        return self

    def __exit__(self, *_a):
        if self.hook:
            self.u.UnhookWindowsHookEx(self.hook)
        self.hook = None
        return False

    def on_event(self, code, wparam, lparam):
        try:
            if code == 0 and wparam == 0x020A:  # WM_MOUSEWHEEL
                delta = ctypes.c_short((_MSLLHOOK.from_address(lparam).mouseData >> 16) & 0xFFFF).value
                if self.scroll(QCursor.pos(), delta):
                    return 1  # used here: nothing else scrolls under the drag
        except Exception:
            pass
        return self.u.CallNextHookEx(None, code, wparam, lparam)

    def scroll(self, at, delta):
        """Scroll the list for a wheel turn of `delta` (120 a notch) with the pointer at `at` (screen point).
        Returns True when the pointer is over the list."""
        vp = self.view.viewport()
        if not vp.rect().contains(vp.mapFromGlobal(at)):
            return False
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.value() - round(delta / 120 * 60))
        return True


class AppList(QListWidget):
    """The list of notes under their categories. Notes drag the usual way. A category heading drags too
    (taking everything inside it along); a click on a heading folds it; a click on a row's pin pins it."""
    moved = Signal()
    delete_pressed = Signal()
    header_clicked = Signal(str, bool)   # category key, whether the click was on the fold mark
    header_folded = Signal(str)          # a double-click on a heading
    row_released = Signal(str)           # a note row clicked and let go without dragging it
    pin_clicked = Signal(str, str)        # kind ("app" or "section"), id
    section_dropped = Signal(str, int)    # category key, the row it was dropped before

    def __init__(self):
        super().__init__()
        self.setObjectName("applist")
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(14)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self._head, self._press = -1, QPoint()
        self._row = None  # the note row under a press, until it is released or dragged
        self.setAutoScrollMargin(36)  # holding a dragged note near the top or bottom edge scrolls too

    def item_box(self, it):
        return QRectF(self.visualItemRect(it)).adjusted(8 + 14 * int(it.data(ROLE_DEPTH) or 0), 2, -8, -2)

    def pin_hit(self, pos):
        """The item whose pin is under `pos`, or None."""
        it = self.itemAt(pos)
        if it is None:
            return None
        box = self.item_box(it)
        return it if pin_fits(box) and pin_rect(box).adjusted(-4, -4, 4, 4).contains(QPointF(pos)) else None

    def drop_row(self, pos):
        it = self.itemAt(pos)
        if it is None:
            return self.count()
        return self.row(it) + (1 if pos.y() > self.visualItemRect(it).center().y() else 0)

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasFormat(CATEGORY_MIME):
            ev.setDropAction(Qt.MoveAction)
            ev.accept()
            return
        super().dragEnterEvent(ev)

    def dragMoveEvent(self, ev):
        if ev.mimeData().hasFormat(CATEGORY_MIME):
            ev.setDropAction(Qt.MoveAction)
            ev.accept()
            return
        super().dragMoveEvent(ev)

    def dropEvent(self, ev):
        if ev.mimeData().hasFormat(CATEGORY_MIME):
            key = bytes(ev.mimeData().data(CATEGORY_MIME)).decode("utf-8")
            row = self.drop_row(ev.position().toPoint())
            ev.setDropAction(Qt.MoveAction)
            ev.accept()
            QTimer.singleShot(0, lambda: self.section_dropped.emit(key, row))
            return
        super().dropEvent(ev)
        QTimer.singleShot(0, self.moved.emit)

    def head_row(self, ev):
        it = self.itemAt(ev.position().toPoint())
        return self.row(it) if it is not None and it.data(ROLE_KIND) == "section" else -1

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            hit = self.pin_hit(ev.position().toPoint())
            if hit is not None:
                self._head = -1
                self.pin_clicked.emit(hit.data(ROLE_KIND), hit.data(ROLE_ID))
                ev.accept()
                return
        self._head = self.head_row(ev) if ev.button() == Qt.LeftButton else -1
        self._press = ev.position().toPoint()
        it = self.itemAt(self._press)
        self._row = it.data(ROLE_ID) if (ev.button() == Qt.LeftButton and it is not None
                                         and it.data(ROLE_KIND) == "app") else None
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if (self._head >= 0 and ev.buttons() & Qt.LeftButton
                and (ev.position().toPoint() - self._press).manhattanLength() >= QApplication.startDragDistance()):
            key = self.item(self._head).data(ROLE_ID)
            self._head = -1
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(CATEGORY_MIME, key.encode("utf-8"))
            drag.setMimeData(mime)
            with DragWheel(self):
                drag.exec(Qt.MoveAction)
            return
        super().mouseMoveEvent(ev)

    def startDrag(self, actions):
        self._row = None  # a drag, not a click: the note is not opened
        with DragWheel(self):  # the mouse wheel scrolls the list while the note is held
            super().startDrag(actions)

    def mouseReleaseEvent(self, ev):
        row, self._head = self._head, -1
        eid, self._row = self._row, None
        super().mouseReleaseEvent(ev)
        if row >= 0 and ev.button() == Qt.LeftButton and self.head_row(ev) == row:
            it = self.item(row)
            on_mark = ev.position().x() < self.item_box(it).left() + 18
            self.header_clicked.emit(it.data(ROLE_ID), on_mark)
        elif eid and ev.button() == Qt.LeftButton:
            it = self.itemAt(ev.position().toPoint())
            if it is not None and it.data(ROLE_ID) == eid:
                self.row_released.emit(eid)

    def mouseDoubleClickEvent(self, ev):
        it = self.itemAt(ev.position().toPoint())
        if (ev.button() == Qt.LeftButton and it is not None and it.data(ROLE_KIND) == "section"
                and ev.position().x() >= self.item_box(it).left() + 18):
            self.header_folded.emit(it.data(ROLE_ID))
            ev.accept()
            return
        super().mouseDoubleClickEvent(ev)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Delete:
            self.delete_pressed.emit()
            return
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and self.currentItem() is not None \
                and self.currentItem().data(ROLE_KIND) == "app":
            self.row_released.emit(self.currentItem().data(ROLE_ID))
            return
        super().keyPressEvent(ev)


# ---------------------------------------------------------------------------- toast + about

class Toast(QFrame):
    """A short message that rises into place and goes away by itself. The big one sits at the bottom of
    the main pane. The small one (a bubble) is put beside whatever it is about, at `anchor`."""

    def __init__(self, parent, small=False):
        super().__init__(parent)
        self.setObjectName("bubble" if small else "toast")
        self.setFixedHeight(26 if small else 36)
        self.anchor = None  # where a bubble goes, in the parent's coordinates
        self.callback = None
        self.label = QLabel()
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.btn = button("", "toast")
        self.btn.clicked.connect(self.act)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(*((11, 0, 11, 0) if small else (16, 0, 14, 0)))
        lay.setSpacing(10)
        lay.addWidget(self.label)
        lay.addWidget(self.btn)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)
        self.anim = QPropertyAnimation(self, b"pos", self)
        self.anim.setDuration(180)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        parent.installEventFilter(self)
        self.hide()

    def spot(self):
        par = self.parentWidget()
        if self.anchor is not None:
            return QPoint(max(4, min(self.anchor.x(), par.width() - self.width() - 4)), max(0, self.anchor.y()))
        return QPoint((par.width() - self.width()) // 2, par.height() - self.height() - 18)

    def say(self, text, action="", callback=None, ms=1800):
        self.label.setText(text)
        self.callback = callback
        self.btn.setText(action)
        self.btn.setVisible(bool(action))
        self.adjustSize()
        end = self.spot()
        self.show()
        self.raise_()
        self.anim.stop()
        self.anim.setStartValue(end + QPoint(0, 10))
        self.anim.setEndValue(end)
        self.anim.start()
        self.timer.start(ms)

    def act(self):
        cb, self.callback = self.callback, None
        self.hide()
        if cb:
            cb()

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Resize and self.isVisible():
            self.move(self.spot())
        return False


class FontList(QListWidget):
    """Every font, A to Z, each name written in its own font."""
    picked = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("fontlist")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(14)
        for c in sorted(load_fonts(), key=lambda c: c["name"].lower()):
            it = QListWidgetItem(c["name"])
            f = QFont(c["family"])
            f.setPixelSize(15)
            it.setFont(f)
            it.setData(Qt.UserRole, c["id"])
            it.setToolTip(f"{c['name']}. Click to use it for the whole app.")
            self.addItem(it)
        self.itemClicked.connect(lambda it: it.data(Qt.UserRole) and self.picked.emit(it.data(Qt.UserRole)))

    def mark(self, font_id):
        for i in range(self.count()):
            it = self.item(i)
            if it.data(Qt.UserRole) == font_id:
                self.setCurrentItem(it)
                self.scrollToItem(it)
                return


class SettingsCard(QWidget):
    """The card behind Change Font at the bottom left: one list of fonts for the whole app. A click on a
    name uses it at once and keeps it."""

    def __init__(self, parent, win):
        super().__init__(parent)
        self.win = win
        self.setObjectName("backdrop")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.card = QFrame(self)
        self.card.setObjectName("aboutcard")
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(10)
        title = QLabel("Font")
        title.setObjectName("famtitle")
        lay.addWidget(title)
        self.fonts = FontList()
        self.fonts.picked.connect(self.win.set_app_font)
        lay.addWidget(self.fonts, 1)
        close = button("Close", "secondary", "Close this card. Esc works too.")
        close.clicked.connect(self.hide)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        parent.installEventFilter(self)
        self.hide()

    def open(self):
        self.fonts.mark(self.win.font_id())
        self.fit()
        self.show()
        self.raise_()
        self.setFocus()

    def fit(self):
        r = self.parentWidget().rect()
        self.setGeometry(r)
        w, h = min(360, r.width() - 24), min(560, r.height() - 24)
        self.card.setGeometry((r.width() - w) // 2, (r.height() - h) // 2, w, h)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Resize and self.isVisible():
            self.fit()
        return False

    def mousePressEvent(self, ev):
        if not self.card.geometry().contains(ev.position().toPoint()):
            self.hide()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.hide()


class FolderCard(QWidget):
    """The card behind the folder in the status bar: the folder linked to this note, a button to change
    it and a button to open it in Explorer."""

    def __init__(self, parent, win):
        super().__init__(parent)
        self.win = win
        self.setObjectName("backdrop")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.card = QFrame(self)
        self.card.setObjectName("aboutcard")
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(10)
        title = QLabel("Linked folder")
        title.setObjectName("famtitle")
        lay.addWidget(title)
        self.path = QLabel()
        self.path.setObjectName("folderpath")
        self.path.setWordWrap(True)
        self.path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.path)
        self.change_btn = button("Change folder...", "secondary", "Pick another folder for this note with the "
                                                                   "Explorer folder picker. A toast offers Undo.")
        self.change_btn.clicked.connect(self.change)
        self.open_btn = button("Open in Explorer", "primary", "Opens this folder in Explorer.")
        self.open_btn.clicked.connect(self.explore)
        close = button("Close", "secondary", "Close this card. Esc works too.")
        close.clicked.connect(self.hide)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.open_btn)
        row.addWidget(self.change_btn)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        parent.installEventFilter(self)
        self.hide()

    def refresh(self):
        e = self.win.store.get(self.win.cur)
        folder = self.win.store.folder(e) if e else ""
        there = bool(folder and os.path.isdir(folder))
        self.path.setText(folder if folder else "This note has no folder linked yet.")
        self.change_btn.setText("Change folder..." if folder else "Link folder...")
        self.change_btn.setEnabled(bool(e))
        self.open_btn.setEnabled(there)
        self.open_btn.setToolTip("Opens this folder in Explorer." if there else "There is no folder to open yet.")

    def change(self):
        self.hide()
        self.win.pick_folder()

    def explore(self):
        self.hide()
        self.win.open_folder()

    def open(self):
        self.refresh()
        self.fit()
        self.show()
        self.raise_()
        self.setFocus()

    def fit(self):
        r = self.parentWidget().rect()
        self.setGeometry(r)
        w = min(460, r.width() - 24)
        self.card.setFixedWidth(w)
        self.card.adjustSize()
        h = self.card.sizeHint().height()
        self.card.setGeometry((r.width() - w) // 2, max(12, (r.height() - h) // 2), w, h)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Resize and self.isVisible():
            self.fit()
        return False

    def mousePressEvent(self, ev):
        if not self.card.geometry().contains(ev.position().toPoint()):
            self.hide()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.hide()


class LinksCard(QWidget):
    """The small card behind the NimbleCloud13 button at the bottom left: GitHub and Buy me a coffee."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("backdrop")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.card = QFrame()
        self.card.setObjectName("aboutcard")
        self.card.setFixedWidth(340)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(24, 22, 24, 18)
        lay.setSpacing(8)
        title = QLabel("NimbleCloud13")
        title.setObjectName("famtitle")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)
        lay.addSpacing(4)
        self.buttons = []
        for name, url in CARD_LINKS:
            b = button(f"{name}    {url.split('//')[1]}", "linkcard", f"Opens {url} in your browser.")
            b.clicked.connect(lambda _=False, u=url: self.go(u))
            lay.addWidget(b)
            self.buttons.append(b)
        fine = QLabel("Support means a lot to my family.")
        fine.setObjectName("aboutfine")
        fine.setAlignment(Qt.AlignCenter)
        lay.addSpacing(4)
        lay.addWidget(fine)
        close = button("Close", "secondary", "Close this card. Esc works too.")
        close.clicked.connect(self.hide)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        row.addStretch(1)
        lay.addLayout(row)
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        mid = QHBoxLayout()
        mid.addStretch(1)
        mid.addWidget(self.card)
        mid.addStretch(1)
        outer.addLayout(mid)
        outer.addStretch(1)
        self.opened = []  # test hook: links that would have opened
        parent.installEventFilter(self)
        self.hide()

    def go(self, url):
        if TEST:
            self.opened.append(url)
        else:
            QDesktopServices.openUrl(QUrl(url))

    def open(self):
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.setFocus()

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Resize and self.isVisible():
            self.setGeometry(self.parentWidget().rect())
        return False

    def mousePressEvent(self, ev):
        if not self.card.geometry().contains(ev.position().toPoint()):
            self.hide()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.hide()


class PickChip(QAbstractButton):
    """One note in the groups panel: a real toggle button, lit with a ticked box while the note is in
    the group being edited. The small number at its right is how many open lines the note has."""

    def __init__(self, name, open_n):
        super().__init__()
        self.name, self.open_n = name, open_n
        self.setCheckable(True)
        self.setFixedHeight(24)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on, hot = self.isChecked(), self.underMouse()
        p.setPen(QPen(QColor(T.ACCENT if on else (T.BORDER_HI if hot else T.BORDER)), 1))
        p.setBrush(acc(44) if on else QColor(T.BG_HI if hot else T.BG))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 6, 6)
        box = QRectF(7, (self.height() - 12) / 2, 12, 12)
        p.setPen(QPen(QColor(T.ACCENT if on else T.BORDER_HI), 1))
        p.setBrush(QColor(T.ACCENT if on else T.BG_INPUT))
        p.drawRoundedRect(box, 3, 3)
        if on:  # a black tick on the amber box
            p.setPen(QPen(on_acc(), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPolyline([QPointF(box.left() + 2.8, box.center().y() + .3), QPointF(box.left() + 5.1, box.bottom() - 3),
                            QPointF(box.right() - 2.5, box.top() + 3.2)])
        right = self.width() - 8
        if self.open_n:
            p.setFont(ui_font(10, QFont.Bold, mono=True))
            p.setPen(QColor(T.ACCENT_TEXT))
            tag = str(self.open_n)
            w = p.fontMetrics().horizontalAdvance(tag)
            p.drawText(QRectF(right - w, 0, w, self.height()), Qt.AlignVCenter | Qt.AlignLeft, tag)
            right -= w + 6
        p.setFont(ui_font(12, QFont.DemiBold if on else QFont.Normal))
        p.setPen(QColor(T.TEXT if (on or hot) else T.TEXT_DIM))
        room = QRectF(26, 0, max(10, right - 26), self.height())
        p.drawText(room, Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(self.name, Qt.ElideRight, int(room.width())))


class WrapRow(QWidget):
    """A row of buttons that wraps onto more lines when it is too narrow for one."""

    def __init__(self, gap=6):
        super().__init__()
        self.gap, self.items = gap, []
        self.right_from = None  # items from this index on sit at the right end of the last line
        self.setMinimumWidth(60)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_items(self, widgets):
        for w in self.items:
            w.hide()
            w.deleteLater()
        self.items = list(widgets)
        for w in self.items:
            hidden = w.isHidden() and w.testAttribute(Qt.WA_WState_ExplicitShowHide)
            w.setParent(self)
            w.setVisible(not hidden)  # an item hidden on purpose stays hidden
            w.installEventFilter(self)
        self.place()

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.Show, QEvent.Hide):  # an item came or went: lay the row out again
            QTimer.singleShot(0, self.place)
        return False

    def place(self):
        width = max(60, self.width())
        cut = len(self.items) if self.right_from is None else self.right_from
        lines, line, x = [], [], 0
        for w in self.items[:cut]:
            if not w.isVisibleTo(self):
                continue
            w.ensurePolished()
            size = w.sizeHint()
            wide = min(size.width(), width)
            if line and x + wide > width:
                lines.append(line)
                line, x = [], 0
            line.append((w, x, wide, size.height()))
            x += wide + self.gap
        right = []
        for w in self.items[cut:]:
            if w.isVisibleTo(self):
                w.ensurePolished()
                size = w.sizeHint()
                right.append((w, min(size.width(), width), size.height()))
        if right:
            need = sum(wide for _w, wide, _h in right) + self.gap * (len(right) - 1)
            if line and x + need > width:  # no room beside the left ones: a line of their own, still to the right
                lines.append(line)
                line, x = [], 0
            if need <= width:
                rx = width - need
                for w, wide, h in right:
                    line.append((w, rx, wide, h))
                    rx += wide + self.gap
            else:  # wider than the row: they wrap like the rest
                for w, wide, h in right:
                    if line and x + wide > width:
                        lines.append(line)
                        line, x = [], 0
                    line.append((w, x, wide, h))
                    x += wide + self.gap
        if line:
            lines.append(line)
        y = 0
        for line in lines:  # the items of a line share its middle
            tall = max(h for _w, _x, _wide, h in line)
            for w, x, wide, h in line:
                w.setGeometry(x, y + (tall - h) // 2, wide, h)
            y += tall + self.gap
        tall = max(1, y - self.gap)
        if tall != self.height() or tall != self.minimumHeight():
            self.setFixedHeight(tall)

    def resizeEvent(self, ev):
        self.place()


# where the window can be put: (kind, side) -> (left, top, width, height) as parts of the screen
PLACES = {
    ("half", "left"): (0, 0, .5, 1), ("half", "right"): (.5, 0, .5, 1),
    ("half", "top"): (0, 0, 1, .5), ("half", "bottom"): (0, .5, 1, .5),
    ("third", "left"): (0, 0, 1 / 3, 1), ("third", "right"): (2 / 3, 0, 1 / 3, 1),
    ("third", "top"): (0, 0, 1, 1 / 3), ("third", "bottom"): (0, 2 / 3, 1, 1 / 3),
    ("quarter", "left"): (0, 0, .25, 1), ("quarter", "right"): (.75, 0, .25, 1),
    ("quarter", "top"): (0, 0, 1, .25), ("quarter", "bottom"): (0, .75, 1, .25),
    ("fifth", "left"): (0, 0, .2, 1), ("fifth", "right"): (.8, 0, .2, 1),
    ("fifth", "top"): (0, 0, 1, .2), ("fifth", "bottom"): (0, .8, 1, .2),
    ("sixth", "left"): (0, 0, 1 / 6, 1), ("sixth", "right"): (5 / 6, 0, 1 / 6, 1),
    ("sixth", "top"): (0, 0, 1, 1 / 6), ("sixth", "bottom"): (0, 5 / 6, 1, 1 / 6),
    ("seventh", "left"): (0, 0, 1 / 7, 1), ("seventh", "right"): (6 / 7, 0, 1 / 7, 1),
    ("seventh", "top"): (0, 0, 1, 1 / 7), ("seventh", "bottom"): (0, 6 / 7, 1, 1 / 7),
    ("eighth", "left"): (0, 0, 1 / 8, 1), ("eighth", "right"): (7 / 8, 0, 1 / 8, 1),
    ("eighth", "top"): (0, 0, 1, 1 / 8), ("eighth", "bottom"): (0, 7 / 8, 1, 1 / 8),
    ("corner", "top-left"): (0, 0, .5, .5), ("corner", "top-right"): (.5, 0, .5, .5),
    ("corner", "bottom-left"): (0, .5, .5, .5), ("corner", "bottom-right"): (.5, .5, .5, .5),
}
PLACE_ROWS = [("half", "Half", ("left", "right", "top", "bottom")),
              ("third", "Third", ("left", "right", "top", "bottom")),
              ("quarter", "Quarter", ("left", "right", "top", "bottom")),
              ("fifth", "Fifth", ("left", "right", "top", "bottom")),
              ("sixth", "Sixth", ("left", "right", "top", "bottom")),
              ("seventh", "Seventh", ("left", "right", "top", "bottom")),
              ("eighth", "Eighth", ("left", "right", "top", "bottom")),
              ("corner", "Corner", ("top-left", "top-right", "bottom-left", "bottom-right"))]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def corner_hit(x, y, spots, size=3):
    """True when (x, y) is within `size` pixels of one of the corners in `spots` (inside the screen)."""
    return any(sx <= x < sx + size and sy <= y < sy + size for sx, sy in spots)


def stamp_words(stamp):
    """A revision's stamp as its tag shows it: '10-15-26 16:42' becomes '10-15-26 - 16:42'."""
    day, _, clock = str(stamp or "").partition(" ")
    return f"{day} - {clock}" if clock else day


def place_words(kind, side):
    """'the left third of the screen' and so on."""
    if kind == "full":
        return "the whole screen"
    if kind == "corner":
        return f"the {side.replace('-', ' ')} quarter of the screen"
    return f"the {side} {kind} of the screen"


def place_rect(work, frac):
    """The part of a work area (left, top, right, bottom) that a placement takes: x, y, width, height.
    Edges are rounded once, so two placements side by side meet without a gap."""
    left, top, right, bottom = work
    wide, tall = right - left, bottom - top
    fx, fy, fw, fh = frac
    x1, y1 = left + round(fx * wide), top + round(fy * tall)
    x2, y2 = left + round((fx + fw) * wide), top + round((fy + fh) * tall)
    return x1, y1, x2 - x1, y2 - y1


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", _RECT), ("rcWork", _RECT), ("dwFlags", ctypes.c_ulong)]


class _WINDOWPOS(ctypes.Structure):
    _fields_ = [("hwnd", ctypes.c_void_p), ("after", ctypes.c_void_p), ("x", ctypes.c_int), ("y", ctypes.c_int),
                ("cx", ctypes.c_int), ("cy", ctypes.c_int), ("flags", ctypes.c_uint)]


class _MSG(ctypes.Structure):
    _fields_ = [("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint), ("wParam", ctypes.c_size_t),
                ("lParam", ctypes.c_ssize_t), ("time", ctypes.c_ulong), ("x", ctypes.c_long), ("y", ctypes.c_long)]


class _APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("hWnd", ctypes.c_void_p), ("uCallbackMessage", ctypes.c_uint),
                ("uEdge", ctypes.c_uint), ("rc", _RECT), ("lParam", ctypes.c_ssize_t)]


class Win32Place:
    """The Windows side of placing the window: monitors and their work areas (the screen less the
    taskbar), the invisible resize border Windows 10/11 keeps around a window, and the move itself. All
    in real screen pixels, so it is right at any display scaling."""

    def __init__(self):
        self.u = ctypes.WinDLL("user32")
        self.dwm = ctypes.WinDLL("dwmapi")
        u = self.u
        u.MonitorFromWindow.restype = ctypes.c_void_p
        u.MonitorFromWindow.argtypes = (ctypes.c_void_p, ctypes.c_uint)
        u.GetMonitorInfoW.argtypes = (ctypes.c_void_p, ctypes.POINTER(_MONITORINFO))
        u.GetWindowRect.argtypes = (ctypes.c_void_p, ctypes.POINTER(_RECT))
        u.SetWindowPos.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_uint)
        self.enum_proc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_RECT),
                                            ctypes.c_void_p)
        u.EnumDisplayMonitors.argtypes = (ctypes.c_void_p, ctypes.c_void_p, self.enum_proc, ctypes.c_void_p)
        self.dwm.DwmGetWindowAttribute.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint)
        self.shell = ctypes.WinDLL("shell32")
        self.shell.SHAppBarMessage.restype = ctypes.c_size_t
        self.shell.SHAppBarMessage.argtypes = (ctypes.c_ulong, ctypes.POINTER(_APPBARDATA))
        self.bars = set()  # windows registered as app bars

    def info(self, mon):
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(mi)
        self.u.GetMonitorInfoW(mon, ctypes.byref(mi))
        return mi

    def monitors(self):
        """Every monitor, left to right: (handle, its whole area, its work area)."""
        found = []
        cb = self.enum_proc(lambda h, _dc, _r, _d: found.append(h) or 1)
        self.u.EnumDisplayMonitors(None, None, cb, None)
        out = []
        for h in found:
            mi = self.info(h)
            m, w = mi.rcMonitor, mi.rcWork
            out.append((h, (m.left, m.top, m.right, m.bottom), (w.left, w.top, w.right, w.bottom)))
        return sorted(out, key=lambda o: (o[1][0], o[1][1]))

    def work_area(self, hwnd, step=0):
        """The work area of the monitor the window is on, or of the one `step` monitors further along."""
        mons = self.monitors()
        here = self.u.MonitorFromWindow(hwnd, 2)  # the nearest monitor
        i = next((k for k, m in enumerate(mons) if m[0] == here), 0)
        return mons[(i + step) % len(mons)][2]

    def rect(self, hwnd):
        r = _RECT()
        self.u.GetWindowRect(hwnd, ctypes.byref(r))
        return r.left, r.top, r.right, r.bottom

    def border(self, hwnd):
        """The invisible resize border on each side (left, top, right, bottom)."""
        left, top, right, bottom = self.rect(hwnd)
        ext = _RECT()
        if self.dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(ext), ctypes.sizeof(ext)) != 0:  # extended frame bounds
            return 0, 0, 0, 0
        return ext.left - left, ext.top - top, right - ext.right, bottom - ext.bottom

    def appbar_on(self, hwnd, side, rect):
        """Reserve a strip of the screen for the window (a Windows app bar): other windows keep out of it
        and maximize beside it. `rect` is (left, top, right, bottom) of the strip wanted; Windows may trim
        it (the taskbar, another app bar). Returns the strip it gave."""
        edge = {"left": 0, "top": 1, "right": 2, "bottom": 3}[side]
        abd = _APPBARDATA()
        abd.cbSize = ctypes.sizeof(abd)
        abd.hWnd = hwnd
        abd.uCallbackMessage = 0x8000 + 0x51
        if hwnd not in self.bars:
            self.shell.SHAppBarMessage(0, ctypes.byref(abd))  # ABM_NEW
            self.bars.add(hwnd)
        left, top, right, bottom = rect
        abd.uEdge = edge
        abd.rc = _RECT(left, top, right, bottom)
        self.shell.SHAppBarMessage(2, ctypes.byref(abd))  # ABM_QUERYPOS
        r = abd.rc
        if side == "left":
            r.right = r.left + (right - left)
        elif side == "right":
            r.left = r.right - (right - left)
        elif side == "top":
            r.bottom = r.top + (bottom - top)
        else:
            r.top = r.bottom - (bottom - top)
        self.shell.SHAppBarMessage(3, ctypes.byref(abd))  # ABM_SETPOS
        return abd.rc.left, abd.rc.top, abd.rc.right, abd.rc.bottom

    def appbar_off(self, hwnd):
        if hwnd in self.bars:
            abd = _APPBARDATA()
            abd.cbSize = ctypes.sizeof(abd)
            abd.hWnd = hwnd
            self.shell.SHAppBarMessage(1, ctypes.byref(abd))  # ABM_REMOVE
            self.bars.discard(hwnd)

    def move(self, hwnd, x, y, w, h, side):
        """Put the visible window exactly on (x, y, w, h). If Windows will not let it be that small, it
        keeps to the edge it was put against."""
        bl, bt, br, bb = self.border(hwnd)
        flags = 0x0004 | 0x0010 | 0x0200  # no z-order change, no activation, no owner z-order
        self.u.SetWindowPos(hwnd, None, x - bl, y - bt, w + bl + br, h + bt + bb, flags)
        left, top, right, bottom = self.rect(hwnd)
        aw, ah = right - left - bl - br, bottom - top - bt - bb
        nx = x + w - aw if aw > w and "right" in side else x
        ny = y + h - ah if ah > h and "bottom" in side else y
        if (nx, ny) != (x, y):
            self.u.SetWindowPos(hwnd, None, nx - bl, ny - bt, 0, 0, flags | 0x0001)  # keep the size
        return aw, ah


class PlaceTile(QAbstractButton):
    """One choice in the Place menu: a little screen with the part the window will take filled in."""

    def __init__(self, kind, side, on):
        super().__init__()
        self.kind, self.side, self.on = kind, side, on
        self.setFixedSize(46, 32)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.setToolTip(f"Put the window on {place_words(kind, side)}. It stays there, even after a restart, "
                        f"until you drag it somewhere else.")

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        hot = self.underMouse()
        screen = QRectF(4.5, 4.5, self.width() - 9, self.height() - 9)
        p.setPen(QPen(QColor(T.ACCENT if self.on else (T.TEXT_DIM if hot else T.BORDER_HI)), 1.2))
        p.setBrush(QColor(T.BG_HI if hot else T.BG_INPUT))
        p.drawRoundedRect(screen, 3, 3)
        inner = screen.adjusted(2.2, 2.2, -2.2, -2.2)
        fx, fy, fw, fh = PLACES[(self.kind, self.side)]
        part = QRectF(inner.x() + fx * inner.width(), inner.y() + fy * inner.height(),
                      fw * inner.width(), fh * inner.height()).adjusted(.4, .4, -.4, -.4)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.ACCENT) if (self.on or hot) else acc(150))
        p.drawRoundedRect(part, 1.5, 1.5)


class PlaceGrid(QWidget):
    """The grid in the Place menu: a row each for half, third, quarter, fifth, sixth, seventh, eighth and corner."""
    picked = Signal(str, str)

    def __init__(self, current):
        super().__init__()
        self.tiles = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(10, 6, 10, 4)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(2)
        for r, (kind, label, sides) in enumerate(PLACE_ROWS):
            lab = QLabel(label)
            lab.setObjectName("placehead")
            grid.addWidget(lab, r, 0)
            for c, side in enumerate(sides):
                tile = PlaceTile(kind, side, current == (kind, side))
                tile.clicked.connect(lambda _=False, k=kind, s=side: self.picked.emit(k, s))
                grid.addWidget(tile, r, c + 1)
                self.tiles[(kind, side)] = tile


def short_name(name, most=22):
    return name if len(name) <= most else name[:most - 1].rstrip() + "\u2026"


class Groups(QWidget):
    """The groups panel. A group is a short list of notes to work on together. The buttons along the
    top are the groups. Under them is every note at once, in columns, each one a toggle that is lit
    while the note is in the group picked above. A note can be in several groups. Changes are saved as
    they are made, and Undo steps back through the ones made while the panel is open."""
    COL, GAP = 206, 12

    def __init__(self, parent, win):
        super().__init__(parent)
        self.win = win
        self.gid = ""            # the group being edited
        self.fresh = set()       # groups made here that were never named or filled: dropped again on Done
        self.made = set()        # groups made here that still have the name they were given
        self.undo_stack = []
        self.touched = False     # anything changed since the panel opened
        self.chips = {}          # entry id -> its toggle
        self.heads = []          # (section key, title, heading button)
        self.tab_btns = {}       # group id -> its button along the top
        self.columns = 0
        self.setObjectName("backdrop")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.card = QFrame()
        self.card.setObjectName("famcard")
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(22, 18, 22, 14)
        lay.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        title = QLabel("Groups")
        title.setObjectName("famtitle")
        self.undo_btn = button("Undo", "secondary", "Take back the last change made in this panel.")
        self.undo_btn.clicked.connect(self.undo)
        self.done_btn = button("Done", "strike", "Close this panel. If you changed a group, the list then shows "
                                                 "that group. Esc works too. Changes are already saved.")
        self.done_btn.clicked.connect(self.done)
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(self.undo_btn)
        top.addWidget(self.done_btn)
        lay.addLayout(top)
        blurb = QLabel("A group is a short list of notes to work on together. Pick a group below, or make a new "
                       "one, then click the notes that belong in it. A note can be in several groups. Back in "
                       "the list, click a group to see only its notes, and All notes to see everything.")
        blurb.setObjectName("aboutblurb")
        blurb.setWordWrap(True)
        lay.addWidget(blurb)
        self.tabs = WrapRow()
        lay.addWidget(self.tabs)

        self.edit_row = QWidget()
        row = QHBoxLayout(self.edit_row)
        row.setContentsMargins(0, 2, 0, 0)
        row.setSpacing(8)
        row.addWidget(section_label("Name", "The name of the group picked above. Change it and press Enter."), 0,
                      Qt.AlignVCenter)
        self.name_edit = EscLineEdit()
        self.name_edit.setFixedWidth(230)
        self.name_edit.setMaxLength(40)
        self.name_edit.setPlaceholderText("Group name")
        self.name_edit.setToolTip("The name of this group. Change it and press Enter.")
        self.name_edit.editingFinished.connect(self.rename)
        self.name_edit.escaped.connect(self.done)
        self.del_btn = button("Delete group", "secondary", "Deletes this group. The notes themselves are not "
                                                           "touched. Undo, above, brings it back.")
        self.del_btn.clicked.connect(self.delete)
        self.msg = QLabel()
        self.msg.setObjectName("hint")
        self.count = QLabel()
        self.count.setObjectName("hint")
        self.open_btn = button("Add notes with open lines", "chip")
        self.open_btn.clicked.connect(self.add_open)
        self.clear_btn = button("Clear", "chip", "Takes every note out of this group. The notes themselves are "
                                                 "not touched. Undo, above, puts them back.")
        self.clear_btn.clicked.connect(self.clear)
        row.addWidget(self.name_edit)
        row.addWidget(self.del_btn)
        row.addWidget(self.msg)
        row.addStretch(1)
        row.addWidget(self.count)
        row.addWidget(self.open_btn)
        row.addWidget(self.clear_btn)
        lay.addWidget(self.edit_row)

        self.area = QScrollArea()
        self.area.setObjectName("pickscroll")
        self.area.setFrameShape(QFrame.NoFrame)
        self.area.setWidgetResizable(True)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.area.viewport().setObjectName("pickview")
        lay.addWidget(self.area, 1)
        self.empty = QLabel("There are no groups. Click + New group, above, to make one.")
        self.empty.setObjectName("emptysub")
        self.empty.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.empty, 1)
        self.msg_timer = QTimer(self)
        self.msg_timer.setSingleShot(True)
        self.msg_timer.timeout.connect(lambda: self.msg.setText(""))

        outer = QVBoxLayout(self)
        outer.addStretch(1)
        mid = QHBoxLayout()
        mid.addStretch(1)
        mid.addWidget(self.card)
        mid.addStretch(1)
        outer.addLayout(mid)
        outer.addStretch(1)
        parent.installEventFilter(self)
        self.hide()

    # ---- opening and closing
    def open(self, gid="", new=False, with_ids=()):
        """Open on one group. `new` makes a group first (holding `with_ids`) and puts the cursor in its name."""
        win = self.win
        self.undo_stack, self.touched, self.fresh = [], False, set()
        self.made = set()  # groups made here that still have the name they were given
        self.msg.setText("")
        if new or not win.groups():
            g = win.make_group(with_ids)
            self.made.add(g["id"])
            if with_ids:
                self.touched = True
            else:
                self.fresh.add(g["id"])
            win.groups_changed()
            gid, new = g["id"], True
        self.gid = gid if win.group_by_id(gid) else win.groups()[0]["id"]
        self.settle()
        self.show()
        self.raise_()
        if new:
            self.name_edit.setFocus()
            self.name_edit.selectAll()
        else:
            self.setFocus()

    def settle(self):
        """Size the card to the window and lay the notes out in as many columns as fit."""
        par = self.parentWidget()
        self.setGeometry(par.rect())
        self.card.setFixedSize(max(480, min(par.width() - 56, 1220)), max(340, min(par.height() - 56, 780)))
        self.rebuild()

    def done(self):
        if not self.isVisible():
            return
        self.rename()  # a name typed but not entered yet still counts
        self.hide()
        win = self.win
        dropped = [g for g in win.groups() if g["id"] in self.fresh and not g["ids"]]
        for g in dropped:  # made here, never named, never filled: it was not wanted
            win.groups().remove(g)
        win.groups_panel_closed(self.gid, self.touched)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Resize and self.isVisible():
            self.settle()
        return False

    def mousePressEvent(self, ev):
        if not self.card.geometry().contains(ev.position().toPoint()):
            self.done()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.done()

    # ---- the columns of notes
    def plan(self, sections, per):
        """Split the headings and notes into columns of at most `per` rows. A section that runs on into
        the next column gets its heading again there, and a heading is never left alone at the foot."""
        cols = []
        for key, title, entries in sections:
            if not cols or len(cols[-1]) + 2 > per:
                cols.append([])
            cols[-1].append(("head", key, title))
            for e in entries:
                if len(cols[-1]) >= per:
                    cols.append([("head", key, title)])
                cols[-1].append(("note", e, None))
        return cols

    def rebuild(self):
        win = self.win
        sections = [(s["key"], s["title"], win.ordered(s["key"])) for s in win.store.sections]
        sections = [s for s in sections if s[2]]
        room = self.card.width() - 44 - 12  # the card's margins and the scrollbar
        fit = max(1, (room + self.GAP) // (self.COL + self.GAP))
        per = max(3, math.ceil(sum(len(es) + 1 for _k, _t, es in sections) / fit))
        cols = self.plan(sections, per)
        while len(cols) > fit:
            per += 1
            cols = self.plan(sections, per)
        self.columns = len(cols)
        inner = QWidget()
        inner.setObjectName("pickinner")
        row = QHBoxLayout(inner)
        row.setContentsMargins(0, 0, 0, 4)
        row.setSpacing(self.GAP)
        self.chips, self.heads = {}, []
        for items in cols:
            holder = QWidget()
            holder.setFixedWidth(self.COL)
            col = QVBoxLayout(holder)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(3)
            for kind, a, b in items:
                if kind == "head":
                    head = QPushButton()
                    head.setObjectName("pickhead")
                    head.setFont(lbl_font())
                    head.setCursor(Qt.PointingHandCursor)
                    head.setFocusPolicy(Qt.NoFocus)
                    head.setToolTip(f"Click to put every note under {b} in this group. If they are all in "
                                    f"it already, it takes them all out.")
                    head.clicked.connect(lambda _=False, k=a: self.toggle_section(k))
                    col.addWidget(head)
                    self.heads.append((a, b, head))
                else:
                    chip = PickChip(a["name"], win.open_n.get(a["id"], 0))
                    chip.toggled.connect(lambda on, i=a["id"]: self.pick(i, on))
                    col.addWidget(chip)
                    self.chips[a["id"]] = chip
            col.addStretch(1)
            row.addWidget(holder, 0, Qt.AlignTop)
        row.addStretch(1)
        self.area.setWidget(inner)  # the old columns are deleted with the widget they were in
        self.sync()

    def group(self):
        return self.win.group_by_id(self.gid)

    def sync(self):
        """Make the group buttons, the name, every toggle, heading and count show what is true now."""
        win = self.win
        if not self.group() and win.groups():
            self.gid = win.groups()[0]["id"]
        g = self.group()
        tabs, self.tab_btns = [], {}
        for o in win.groups():
            n = len(win.members(o))
            b = button(f"{short_name(o['name'])}  {n}", "chip",
                       f"{o['name']}: {n} note{'' if n == 1 else 's'}. Click to work on this group here.")
            b.setProperty("lit", o is g)
            b.clicked.connect(lambda _=False, i=o["id"]: self.select(i))
            tabs.append(b)
            self.tab_btns[o["id"]] = b
        self.new_btn = button("+ New group", "chip", "Make another group, then type its name and click the notes "
                                                     "that belong in it.")
        self.new_btn.clicked.connect(self.add_group)
        tabs.append(self.new_btn)
        self.tabs.set_items(tabs)
        self.edit_row.setVisible(bool(g))
        self.area.setVisible(bool(g))
        self.empty.setVisible(not g)
        self.undo_btn.setEnabled(bool(self.undo_stack))
        if not g:
            return
        if self.name_edit.text() != g["name"]:
            self.name_edit.blockSignals(True)
            self.name_edit.setText(g["name"])
            self.name_edit.blockSignals(False)
        picked = set(win.members(g))
        for eid, chip in self.chips.items():
            e = win.store.get(eid)
            if chip.isChecked() != (eid in picked):
                chip.blockSignals(True)
                chip.setChecked(eid in picked)
                chip.blockSignals(False)
            todo = win.open_n.get(eid, 0)
            chip.setToolTip((e["name"] if e else "") + (f"\nIn {g['name']}. Click to take it out."
                                                        if eid in picked else f"\nClick to put it in {g['name']}.")
                            + (f"\n{todo} open line{'' if todo == 1 else 's'} in its note." if todo else ""))
        for key, title, head in self.heads:
            ids = [e["id"] for e in win.store.entries if e["section"] == key]
            head.setText(f"{title}   {sum(1 for i in ids if i in picked)}/{len(ids)}")
        total = len(win.store.entries)
        self.count.setText(f"{len(picked)} of {total} notes in this group")
        self.clear_btn.setEnabled(bool(picked))
        waiting = [e["id"] for e in win.store.entries if win.open_n.get(e["id"], 0) and e["id"] not in picked]
        self.open_btn.setEnabled(bool(waiting))
        self.open_btn.setToolTip(f"Adds the {len(waiting)} note{'' if len(waiting) == 1 else 's'} that still "
                                 f"{'has' if len(waiting) == 1 else 'have'} open lines (the highlighted rows in the list)."
                                 if waiting else "Every note with open lines is already in this group.")

    # ---- changes
    def snap(self):
        """Remember how things are, for Undo, just before a change."""
        self.undo_stack.append((copy.deepcopy(self.win.groups()), self.win.view_ids(),
                                self.gid, set(self.fresh)))
        del self.undo_stack[:-60]
        self.touched = True

    def changed(self):
        self.win.groups_changed()
        self.sync()

    def undo(self):
        if not self.undo_stack:
            return
        groups, view, self.gid, self.fresh = self.undo_stack.pop()
        self.name_edit.blockSignals(True)
        self.name_edit.clear()  # so that a half-typed name is not entered again on top of the undo
        self.name_edit.blockSignals(False)
        self.win.groups()[:] = groups
        self.win.store.state["group_view"] = view
        self.changed()

    def say(self, text):
        self.msg.setText(text)
        self.msg_timer.start(4500)

    def select(self, gid):
        self.rename()
        self.gid = gid
        self.sync()

    def add_group(self):
        self.rename()
        self.snap()
        g = self.win.make_group()
        self.fresh.add(g["id"])
        self.made.add(g["id"])
        self.gid = g["id"]
        self.changed()
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def rename(self):
        g = self.group()
        if not g:
            return
        name = " ".join(self.name_edit.text().split())
        if not name or name == g["name"]:
            self.name_edit.setText(g["name"])
            return
        same = next((o for o in self.win.groups() if o is not g and o["name"].lower() == name.lower()), None)
        if same is not None:  # that group exists: pick it (a new, unnamed group's notes go into it)
            self.snap()
            if g["id"] in self.fresh or g["id"] in self.made:
                same["ids"] = list(dict.fromkeys(same["ids"] + g["ids"]))
                self.win.groups().remove(g)
                self.fresh.discard(g["id"])
            self.gid = same["id"]
            self.name_edit.blockSignals(True)
            self.name_edit.setText(same["name"])
            self.name_edit.blockSignals(False)
            self.changed()
            return
        self.snap()
        g["name"] = name
        self.fresh.discard(g["id"])
        self.made.discard(g["id"])
        self.changed()

    def delete(self):
        g = self.group()
        if not g:
            return
        self.name_edit.setText(g["name"])  # whatever was being typed goes with the group
        self.snap()
        groups = self.win.groups()
        at = groups.index(g)
        groups.remove(g)
        self.gid = groups[min(at, len(groups) - 1)]["id"] if groups else ""
        self.changed()

    def set_ids(self, ids):
        g = self.group()
        if not g or list(ids) == g["ids"]:
            return
        self.rename()  # a name typed but not entered yet is kept, not wiped by the redraw
        self.snap()
        g["ids"] = list(dict.fromkeys(ids))
        if g["ids"]:
            self.fresh.discard(g["id"])
        self.changed()

    def pick(self, eid, on):
        g = self.group()
        if g:
            rest = [i for i in g["ids"] if i != eid]
            self.set_ids(rest + [eid] if on else rest)

    def toggle_section(self, key):
        g = self.group()
        if not g:
            return
        ids = [e["id"] for e in self.win.store.entries if e["section"] == key]
        if all(i in g["ids"] for i in ids):
            self.set_ids([i for i in g["ids"] if i not in ids])
        else:
            self.set_ids(g["ids"] + [i for i in ids if i not in g["ids"]])

    def add_open(self):
        g = self.group()
        if g:
            self.set_ids(g["ids"] + [e["id"] for e in self.win.store.entries
                                     if self.win.open_n.get(e["id"], 0) and e["id"] not in g["ids"]])

    def clear(self):
        self.set_ids([])


# ---------------------------------------------------------------------------- main window

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.store = store.Store()
        self.docs = {}            # id -> QTextDocument of the open text, made the first time an entry is opened
        self.revs = {}            # id -> its finished revisions, newest first: {n, stamp, text}
        self.imgs = {}            # id -> file names of the pictures on the note being typed
        self.ideas_cache = {}     # id -> text of its Ideas pane
        self.ideas_dirty = set()  # ids whose ideas are not on disk yet
        self.tok_rev = 0          # the revision the token count is about; 0 means the notes being typed
        self.mtimes = {}          # id -> notes file time when we last read or wrote it
        self.dirty = set()        # ids whose notes are not on disk yet
        self.meta_dirty = False   # name / TL;DR not on disk yet
        self.note_cache = {}      # notes text for search, for entries never opened
        self.open_n = {}          # id -> open (not finished) lines in its note; rows with any are highlighted
        self.section_counts = {}
        self.shown = {}           # section key -> entry ids in the order they are on screen
        self.dates = {}           # entry id -> (created, last code change), looked up for the date sorts
        self.dates_at = 0.0
        self.sec_target = None    # section being renamed in the name box; None means a new one
        self.cur = None
        self.hist, self.hist_i, self._push = [], -1, True
        self._loading = False
        self.started = []         # test hook: what Open folder / Launch would have started
        self.really_quit = False
        self.tray = None
        self.notes = self.notes_content = None
        self.state_dirty = False  # zoom, theme or place not on disk yet
        self.pin_rect = None      # the strip of screen reserved while pinned (real pixels), or None
        self.hold, self.moving_self = None, False   # the window rect held while a strip is reserved
        self.hold_timer = QTimer(self)
        self.hold_timer.setSingleShot(True)
        self.hold_timer.timeout.connect(lambda: setattr(self, "hold", None))
        self.focus_sec = None     # the category clicked last: a new note goes into it
        self.corner_was = (False, False)  # the hot corner: (pointer in it, button down) at the last look
        self.fresh_id = None      # the last new note made: dropped again if it is left blank
        self.move_undo, self.move_redo = [], []   # Ctrl+Z / Ctrl+Y for notes moved in the list
        self.single = False       # one pane at a time (a very narrow window): the list or the note
        self.split_was = None     # the list's width before one-pane mode
        self.group_counts = {}    # section key -> rows shown, while the list shows only one group
        self.group_tags = {}      # entry id -> names of the groups it is in, for the tag on its row
        self.group_chips = {}     # group id -> its button above the list
        self.clip_queue = []      # what Revisions complete still has to put on the clipboard, in order
        self.clip_log = []        # test hook: everything put on the clipboard, in order
        self.clip_i = self.clip_total = 0
        self.clip_eid = self.clip_beside = None
        self.clip_run = 0         # goes up each time a copy starts or is dropped
        try:
            self.notes_px = max(9, min(34, int(self.store.state.get("notes_px", 14))))
        except (TypeError, ValueError):
            self.notes_px = 14

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(300, 220)  # a quarter of a small screen; the layout tightens itself, down to one pane
        self.resize(1120, 720)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(700)
        self.save_timer.timeout.connect(self.flush)
        self.clip_timer = QTimer(self)  # the pause between two things put on the clipboard
        self.clip_timer.setSingleShot(True)
        self.clip_timer.timeout.connect(self.clip_step)
        try:
            self.clip_gap = max(100, min(3000, int(self.store.state.get("clip_gap_ms", 500))))
        except (TypeError, ValueError):
            self.clip_gap = 500
        self.load_groups()
        self.compact = None        # (narrow, short) once the layout has been fitted to the window
        self.placing = False       # the app itself is moving the window right now
        self.place_seen = None     # where the window was put, to notice when it is dragged away
        self.win32 = None if TEST else Win32Place()
        self.place_timer = QTimer(self)
        self.place_timer.setSingleShot(True)
        self.place_timer.timeout.connect(self.check_place)
        self.theme_timer = QTimer(self)  # the short pause before a theme being pointed at is shown
        self.theme_timer.setSingleShot(True)
        self.theme_timer.timeout.connect(self.show_preview)
        self.preview_id, self.theme_chosen = None, False

        self.build()
        self.apply_notes_font()
        self.restore_window()
        self.apps_mtime = mtime(store.APPS_PATH)
        self.fill_list(self.store.state.get("current"))
        saved = self.store.state.get("theme")
        if nimble_themes.valid(saved) and saved != T.ID:  # started without the theme on (main() puts it on first)
            self.apply_theme(saved, save=False)
        self.refresh_theme_btn()
        self.refresh_place_btn()
        app = QApplication.instance()
        app.screenAdded.connect(self.watch_screen)
        app.screenRemoved.connect(lambda _s: QTimer.singleShot(400, self.reapply_place))
        for s in app.screens():
            self.watch_screen(s, quiet=True)
        QTimer.singleShot(0, self.after_resize)
        QTimer.singleShot(2500, self.check_images_size)

    # ---- layout
    def build(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.hsplit = Splitter(Qt.Horizontal)
        self.hsplit.setChildrenCollapsible(False)
        self.hsplit.setHandleWidth(5)
        self.hsplit.addWidget(self.build_sidebar())
        self.hsplit.addWidget(self.build_main())
        self.hsplit.setStretchFactor(0, 0)
        self.hsplit.setStretchFactor(1, 1)
        self.hsplit.setSizes([272, 848])
        self.hsplit.splitterMoved.connect(lambda *_: QTimer.singleShot(0, self.after_resize))
        outer.addWidget(self.hsplit, 1)
        outer.addWidget(self.build_status())
        self.toast = Toast(self.main)
        self.bubble = Toast(self.notes_content, small=True)  # "Copied to clipboard", beside the button pressed
        self.links = LinksCard(root)
        self.settings = SettingsCard(root, self)
        self.folder_card = FolderCard(root, self)
        self.groups_panel = Groups(root, self)
        self.viewer = media.ImageViewer(root)
        self.viewer.copy.connect(self.copy_picture)
        self.viewer.menu.connect(self.viewer_menu)
        self.notice = media.Notice(root)
        self.notice.copy_path.connect(self.copy_text)
        self.grip = media.CornerGrip(root)
        self.root = root
        root.installEventFilter(self)

        QShortcut(QKeySequence("Ctrl+F"), self, self.focus_search)
        QShortcut(QKeySequence("Ctrl+N"), self, self.new_entry)
        QShortcut(QKeySequence("Ctrl+S"), self, self.save_now)
        QShortcut(QKeySequence("F2"), self, self.start_rename)
        QShortcut(QKeySequence("Ctrl+G"), self, self.toggle_group_view)
        QShortcut(QKeySequence("Ctrl+Z"), self, lambda: self.step_move(self.move_undo, self.move_redo, "Undid"))
        QShortcut(QKeySequence("Ctrl+Y"), self, lambda: self.step_move(self.move_redo, self.move_undo, "Redid"))
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, lambda: self.step_move(self.move_redo, self.move_undo, "Redid"))

    def build_sidebar(self):
        side = QFrame()
        side.setObjectName("sidebar")
        side.setMinimumWidth(150)   # the list can be made narrow; what does not fit steps aside (fit_sidebar)
        side.setMaximumWidth(460)
        self.side = side
        side.installEventFilter(self)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        prow = QHBoxLayout()  # Swap fills the row; Hide notes pane keeps to the right of it, out of the way
        prow.setContentsMargins(12, 12, 12, 8)
        prow.setSpacing(8)
        self.pane_btn = button("Hide notes pane", "chip", "Show the list or the note, not both, whenever the "
                                                          "window is not full screen. Swap switches between them.")
        self.pane_btn.clicked.connect(lambda: self.set_one_pane(not self.store.state.get("one_pane")))
        set_lit(self.pane_btn, bool(self.store.state.get("one_pane")))
        self.note_btn = button("Back", "chip", "Back to the note you are on. The mouse's back and forward "
                                               "buttons switch between the list and the note too.")
        self.note_btn.clicked.connect(lambda: self.show_pane("note"))
        self.note_btn.hide()  # only while one pane shows at a time
        self.prow_gap = QWidget()  # pushes Pin and Hide notes pane to the right while Back shows
        self.prow_gap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.prow_gap.hide()
        self.side_pin = button("Pin", "chip")
        self.side_pin.setIcon(pin_icon())
        self.side_pin.clicked.connect(self.toggle_pin)
        self.side_pin.hide()  # in the list while one pane shows at a time, when the window can be pinned
        prow.addWidget(self.note_btn, 0, Qt.AlignVCenter)
        prow.addWidget(self.prow_gap, 1)
        prow.addWidget(self.side_pin, 0, Qt.AlignVCenter)
        prow.addWidget(self.pane_btn, 0, Qt.AlignLeft | Qt.AlignVCenter)
        lay.addLayout(prow)

        srow = QHBoxLayout()
        srow.setContentsMargins(12, 0, 12, 6)
        self.search = EscLineEdit()
        self.search.escaped.connect(self.clear_search)
        self.search.setPlaceholderText("Search   Ctrl+F")
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip("Filters the list as you type. Matches the name, TL;DR, ideas and the "
                               "note text. Several words must all match. Esc clears it.")
        self.search.textChanged.connect(self.apply_filter)
        srow.addWidget(self.search)
        lay.addLayout(srow)

        ghead = QHBoxLayout()  # groups: a label with its two actions, then one button per group
        ghead.setContentsMargins(14, 4, 12, 4)
        ghead.setSpacing(6)
        self.groups_lbl = section_label("Groups", "A group is a short list of notes to work on together. Click a "
                                                  "group below to see only its notes, and All notes to see "
                                                  "everything again. Ctrl+G flips between the two.")
        ghead.addWidget(self.groups_lbl, 0, Qt.AlignVCenter)
        ghead.addStretch(1)
        self.newgrp_btn = button("+ New", "chip", "Make a new group: type its name, then click the notes that "
                                                  "belong in it.")
        self.newgrp_btn.clicked.connect(lambda: self.open_groups(new=True))
        self.editgrp_btn = button("Edit", "chip", "Edit the groups: change which notes are in a group, rename "
                                                  "it, delete it, or make another.")
        self.editgrp_btn.clicked.connect(lambda: self.open_groups())
        ghead.addWidget(self.newgrp_btn)
        ghead.addWidget(self.editgrp_btn)
        lay.addLayout(ghead)
        gbox = QHBoxLayout()
        gbox.setContentsMargins(12, 0, 12, 8)
        self.group_bar = WrapRow()
        gbox.addWidget(self.group_bar)
        lay.addLayout(gbox)
        tools = QHBoxLayout()
        tools.setContentsMargins(12, 0, 12, 6)  # just above the first category
        tools.setSpacing(6)
        self.sec_btn = button("+ Category", "chip", "Add a category to the list, then drag notes into it. Click a "
                                                    "category to fold it; right-click it to sort, rename, pin, add "
                                                    "a subcategory or remove it. Drag a category to move it.")
        self.sec_btn.clicked.connect(lambda: self.ask_section_name(None))
        self.sec_edit = EscLineEdit()
        self.sec_edit.setPlaceholderText("Category name, then Enter")
        self.sec_edit.setToolTip("Type the category's name and press Enter. Esc cancels.")
        self.sec_edit.hide()
        self.sec_edit.returnPressed.connect(self.commit_section)
        self.sec_edit.editingFinished.connect(self.close_section_box)
        self.sec_edit.escaped.connect(self.close_section_box)
        tools.addWidget(self.sec_btn)
        tools.addWidget(self.sec_edit, 1)
        tools.addStretch(1)
        lay.addLayout(tools)


        self.list = AppList()
        self.list.setItemDelegate(AppDelegate(self))
        self.list.currentItemChanged.connect(self.on_current)
        self.list.customContextMenuRequested.connect(self.list_menu)
        self.list.moved.connect(self.on_moved)
        self.list.delete_pressed.connect(self.remove_current)
        self.list.header_clicked.connect(self.header_click)
        self.list.header_folded.connect(self.toggle_fold)
        self.list.row_released.connect(self.row_opened)
        self.list.pin_clicked.connect(self.toggle_row_pin)
        self.list.section_dropped.connect(self.drop_section)
        lay.addWidget(self.list, 1)

        foot = QHBoxLayout()
        foot.setContentsMargins(12, 8, 8, 4)
        foot.setSpacing(7)
        new = button("+ New", "secondary", "Add an entry under the one you are on, then type its name.")
        new.clicked.connect(lambda: self.new_entry())
        foot.addWidget(new)
        self.foot_kbd = kbd("Ctrl+N")
        foot.addWidget(self.foot_kbd, 0, Qt.AlignVCenter)
        foot.addStretch(1)
        where = self.where_btn = button("Notes folder", "ghost", f"Opens the folder where every note is saved: "
                                                f"{store.contract_dir(store.NOTES_DIR)}\nOne plain text file per "
                                                f"entry, named after the entry.")
        where.clicked.connect(lambda: self.start_path(store.NOTES_DIR))
        foot.addWidget(where)
        lay.addLayout(foot)
        frow = QHBoxLayout()
        frow.setContentsMargins(12, 2, 12, 0)
        self.font_btn = button("Change Font", "chip", "Pick the font for the whole app from one list, each name "
                                                      "shown in its own font.")
        self.font_btn.clicked.connect(lambda: self.settings.open())
        frow.addWidget(self.font_btn)
        frow.setSpacing(6)
        self.size_down = button("-", "chip", "Smaller text in the notes and the Ideas box (Ctrl -).")
        self.size_down.setObjectName("sizebtn")
        self.size_down.clicked.connect(lambda: self.zoom_notes(-1))
        self.size_up = button("+", "chip", "Bigger text in the notes and the Ideas box (Ctrl +).")
        self.size_up.setObjectName("sizebtn")
        self.size_up.clicked.connect(lambda: self.zoom_notes(1))
        frow.addWidget(self.size_down)
        frow.addWidget(self.size_up)
        frow.addStretch(1)
        lay.addLayout(frow)
        self.ver_lbl = QWidget()  # the version, and NimbleCloud13 as a button to the links card
        vrow = QHBoxLayout(self.ver_lbl)
        vrow.setContentsMargins(16, 2, 12, 8)
        vrow.setSpacing(4)
        ver = self.ver_text = QLabel(f"v{VERSION}  ·")
        ver.setObjectName("version")
        self.nc_btn = button("NimbleCloud13", "ghost", "GitHub and Buy me a coffee links.")
        self.nc_btn.setObjectName("ncbtn")
        self.nc_btn.clicked.connect(lambda: self.links.open())
        vrow.addWidget(ver)
        vrow.addWidget(self.nc_btn)
        vrow.addStretch(1)
        lay.addWidget(self.ver_lbl)
        return side

    def build_main(self):
        self.main = QWidget()
        self.main.setObjectName("main")
        self.stack = QStackedLayout(self.main)

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(22, 14, 22, 10)
        lay.setSpacing(8)
        self.page_lay = lay

        top = QHBoxLayout()
        top.setSpacing(8)
        self.list_btn = button("All Notes", "primary", "Show the list of notes. Clicking a note brings you "
                                                       "back here, and Swap there comes back without picking one.")
        self.list_btn.setObjectName("swapbtn")
        self.list_btn.clicked.connect(lambda: self.show_pane("list"))
        self.list_btn.hide()  # only in a window too narrow for the list and the note side by side
        top.addWidget(self.list_btn, 0, Qt.AlignVCenter)
        self.title = TitleLabel()
        self.title.setObjectName("title")
        self.title.setToolTip("Double-click to rename (or press F2).")
        self.title.double_clicked.connect(self.start_rename)
        self.title_edit = EscLineEdit()
        self.title_edit.setObjectName("titleedit")
        self.title_edit.hide()
        self.title_edit.editingFinished.connect(self.commit_rename)
        self.title_edit.escaped.connect(self.cancel_rename)
        self.folder_btn = button("Open folder", "secondary", "Opens this app's folder in Explorer.")
        self.folder_btn.clicked.connect(self.open_folder)
        self.link_btn = button("Link folder", "secondary")
        self.link_btn.clicked.connect(self.pick_folder)
        self.launch_btn = button("Launch", "secondary")
        self.launch_btn.clicked.connect(self.launch)
        self.launch_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self.launch_btn.customContextMenuRequested.connect(self.launch_menu)
        top.addWidget(self.title)
        top.addWidget(self.title_edit, 1)
        top.addStretch(1)
        self.pin_btn = button("Pin", "chip")
        self.pin_btn.setIcon(pin_icon())
        self.pin_btn.clicked.connect(self.toggle_pin)
        self.pin_btn.hide()  # shown only while the window is docked against a side
        self.fork_btn = button("Fork", "chip", "Make a copy of this note right below it, named with _v2 (or the "
                                               "next free number): its notes, ideas, TL;DR and pictures.")
        self.fork_btn.clicked.connect(lambda: self.fork_entry(self.cur))
        for b in (self.folder_btn, self.link_btn, self.launch_btn):
            b.setProperty("tier", "chip")  # the same size as the chips they now sit beside
        lay.addLayout(top)

        self.group_btn = button("", "chip")
        self.group_btn.clicked.connect(lambda: self.group_menu())
        self.chips_row = WrapRow(gap=8)  # wraps onto a second line when the window is narrow
        self.chips_row.set_items([self.group_btn, self.fork_btn, self.pin_btn, self.folder_btn, self.link_btn,
                                  self.launch_btn])
        self.chips_row.right_from = 2  # Pin, Open folder, Change linked folder and Launch keep to the right
        lay.addWidget(self.chips_row)

        tbox = QWidget()
        tl = QVBoxLayout(tbox)
        tl.setContentsMargins(0, 6, 0, 0)
        tl.setSpacing(6)
        trow = QHBoxLayout()
        trow.setSpacing(10)
        trow.addWidget(section_label("TL;DR", "What this app is for, in a line or two. Edit it freely. The "
                                              "box is one line tall while it is empty and grows to fit what "
                                              "is in it."), 0, Qt.AlignVCenter)
        trow.addStretch(1)
        tl.addLayout(trow)
        self.tldr = AutoPlain()
        self.tldr.setObjectName("tldr")
        self.tldr.setPlaceholderText("What is this one for?")
        self.tldr.setTabChangesFocus(True)
        self.tldr.textChanged.connect(self.on_tldr_changed)
        tl.addWidget(self.tldr)

        ibox = QWidget()
        il = QVBoxLayout(ibox)
        il.setContentsMargins(0, 2, 0, 0)
        il.setSpacing(6)
        il.addWidget(section_label("Ideas", "Half-thoughts about this app that are not revision notes yet. "
                                            "Plain text, saved by itself to ideas.txt in this entry's folder. "
                                            "The box is one line tall while it is empty and grows to fit what "
                                            "is in it."))
        self.ideas = AutoPlain()
        self.ideas.setObjectName("ideas")
        self.ideas.setPlaceholderText("Half-thoughts go here.")
        self.ideas.textChanged.connect(self.on_ideas_changed)
        il.addWidget(self.ideas)
        self.ideas_grip = HeightGrip(self.ideas)
        self.ideas_grip.dragged.connect(self.drag_ideas)
        self.ideas_grip.reset.connect(lambda: self.drag_ideas(None))
        il.setSpacing(2)
        il.addWidget(self.ideas_grip)
        h = self.store.state.get("ideas_h")
        self.ideas.manual = int(h) if isinstance(h, (int, float)) and h > 0 else None

        nbox = QWidget()
        nl = QVBoxLayout(nbox)
        nl.setContentsMargins(0, 2, 0, 0)
        nl.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(section_label("Notes", "Your notes for this app. Saved by itself as you type, to a plain "
                                              "text file named after this entry in the notes folder (button at "
                                              "the bottom left)."), 0, Qt.AlignVCenter)
        head.addSpacing(4)
        self.copy_btn = button("Copy note", "chip", "Copies this whole note to the clipboard: its name, the open "
                                                    "text, then every revision under its number and date stamp, "
                                                    "with a blank line between them.")
        self.copy_btn.clicked.connect(self.copy_note)
        head.addWidget(self.copy_btn)
        head.addSpacing(4)
        self.tokens = QLabel()
        self.tokens.setObjectName("tokens")
        self.tokens.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.tokens.setToolTip("How big the update you are writing is, in tokens: every word and every "
                               "punctuation mark counts as one (the count TokenLite gives). Click into a "
                               "revision and this shows that revision's count instead.")
        head.addWidget(self.tokens)
        head.addStretch(1)
        self.counts = QLabel()
        self.counts.setObjectName("hint")
        self.counts.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.counts.setToolTip("Lines still open, lines ticked off with Ctrl+D, and how many finished "
                               "revisions this note has.")
        head.addWidget(self.counts)
        head.addSpacing(8)
        kd = kbd("Ctrl+D")
        head.addWidget(kd, 0, Qt.AlignVCenter)
        hint = QLabel("line done")
        hint.setObjectName("hint")
        hint.setToolTip("Ticks off just the line you are on, or every selected line, without filing it: the "
                        "line is greyed and starts with [x]. Press it again to bring the line back.")
        head.addWidget(hint)
        head.addSpacing(8)
        kz = kbd("Ctrl +/-")
        head.addWidget(kz, 0, Qt.AlignVCenter)
        zhint = QLabel("text size")
        zhint.setObjectName("hint")
        zhint.setToolTip("Ctrl with plus or minus makes the notes text bigger or smaller (9 to 34). Ctrl+0 puts "
                         "it back to 14. Ctrl with the mouse wheel does the same.")
        head.addWidget(zhint)
        self.wide_only = [self.counts, kd, hint, kz, zhint]  # left out of a narrow window
        nl.addLayout(head)

        # one scrolling box: the text you type, the picture strip, the Revisions complete button, then
        # the finished revisions (greyed) with the newest right under the button
        self.notes_box = QFrame()
        self.notes_box.setObjectName("notesbox")
        self.notes_box.setMinimumHeight(90)
        box_lay = QVBoxLayout(self.notes_box)
        box_lay.setContentsMargins(1, 1, 1, 1)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("notescroll")
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.viewport().setObjectName("notesview")
        content = QWidget()
        content.setObjectName("notescontent")
        content.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)  # always the box's width: lines wrap, never scroll sideways
        cl = QVBoxLayout(content)
        cl.setContentsMargins(6, 4, 8, 10)
        cl.setSpacing(0)
        notes = WorkEdit()
        notes.setObjectName("work")
        notes.setPlaceholderText("Type your notes here.")
        notes.textChanged.connect(self.on_notes_changed)
        notes.cursorPositionChanged.connect(self.caret_moved)
        notes.strike.connect(self.strike)
        notes.zoom.connect(self.zoom_notes)
        notes.images.connect(self.add_images)
        cl.addWidget(notes)
        self.strip = media.FilmStrip(live=True)  # the border between the notes being typed and the button
        self.strip.add.connect(self.pick_images)
        self.strip.dropped.connect(self.add_images)
        self.strip.opened.connect(lambda i: self.view_pictures(0, i))
        self.strip.menu.connect(lambda i, at: self.picture_menu(0, i, at))
        self.strip.remove.connect(lambda i: self.ask_remove_picture(0, i))
        cl.addWidget(self.strip)
        srow = QHBoxLayout()
        srow.setContentsMargins(6, 8, 0, 6)
        srow.setSpacing(8)
        self.strike_btn = button("Completed", "strike")
        self.strike_btn.clicked.connect(self.strike)
        self.strike_glow = QGraphicsDropShadowEffect(self.strike_btn)
        self.strike_glow.setBlurRadius(16)
        self.strike_glow.setOffset(0, 2)
        self.strike_glow.setColor(acc(70))
        self.strike_btn.setGraphicsEffect(self.strike_glow)
        srow.addWidget(self.strike_btn)
        self.strike_kbd = kbd("Ctrl+Enter")
        srow.addWidget(self.strike_kbd, 0, Qt.AlignVCenter)
        srow.addStretch(1)
        cl.addLayout(srow)
        self.history = RevisionsView()
        self.history.zoom.connect(self.zoom_notes)
        self.history.reopen.connect(lambda n: self.reopen_revision(self.cur, n))
        self.history.complete.connect(lambda n: self.close_revision(self.cur, n))
        self.history.remove.connect(lambda n: self.delete_revision(self.cur, n))
        self.history.edited.connect(self.revision_edited)
        self.history.caret.connect(self.follow_rev_caret)
        self.history.picture.connect(self.view_pictures)
        self.history.picture_menu.connect(self.picture_menu)
        self.history.picture_remove.connect(self.ask_remove_picture)
        self.history.focused.connect(self.watch_tokens)
        cl.addWidget(self.history)
        cl.addStretch(1)
        self.scroll.setWidget(content)
        box_lay.addWidget(self.scroll)
        nl.addWidget(self.notes_box, 1)
        self.notes, self.notes_content = notes, content
        notes.installEventFilter(self)
        content.installEventFilter(self)

        self.tall_only = [tbox, self.ideas_grip]  # left out of a very short window, with the brand row
        lay.addWidget(tbox)        # as tall as its text
        lay.addWidget(ibox)        # as tall as its text
        lay.addWidget(nbox, 1)     # the notes get everything that is left
        self.panes = (tbox, ibox, nbox)
        self.stack.addWidget(page)

        empty = QWidget()
        el = QVBoxLayout(empty)
        el.setSpacing(10)
        el.addStretch(1)
        t = QLabel("No notes yet")
        t.setObjectName("emptytitle")
        t.setAlignment(Qt.AlignCenter)
        s = QLabel("Add an entry for each app you want to keep notes on.")
        s.setObjectName("emptysub")
        s.setAlignment(Qt.AlignCenter)
        s.setWordWrap(True)  # never makes the window wider than a quarter of a small screen
        cta = button("+ New note", "primary", "Add your first entry, then type its name.")
        cta.setFixedHeight(60)
        cta.clicked.connect(self.new_entry)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(cta)
        row.addStretch(1)
        el.addWidget(t)
        el.addWidget(s)
        el.addSpacing(8)
        el.addLayout(row)
        el.addStretch(1)
        self.stack.addWidget(empty)
        return self.main

    def build_status(self):
        bar = QFrame()
        bar.setObjectName("statusbar")
        bar.setFixedHeight(28)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(16)
        self.saved = QLabel("Ready")
        self.saved.setObjectName("saved")
        self.saved.setToolTip("When the last change was written to disk. Saving is automatic.")
        self.saved.hide()  # shown only when a save fails
        self.path_lbl = QPushButton()
        self.path_lbl.setObjectName("statuspath")
        self.path_lbl.setCursor(Qt.PointingHandCursor)
        self.path_lbl.setFocusPolicy(Qt.NoFocus)
        self.path_lbl.setToolTip("The folder linked to this note. Click to change it or open it in Explorer.")
        self.path_lbl.clicked.connect(lambda: self.folder_card.open())
        self.path_lbl.setMinimumWidth(0)
        sp = self.path_lbl.sizePolicy()
        sp.setHorizontalPolicy(sp.Policy.Ignored)
        self.path_lbl.setSizePolicy(sp)
        self.saved.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.place_btn = button("Place", "chip")
        self.place_btn.clicked.connect(self.place_menu)
        self.theme_btn = button("", "chip")
        self.theme_btn.clicked.connect(self.theme_menu)
        lay.addWidget(self.saved)
        lay.addWidget(self.path_lbl, 1, Qt.AlignVCenter)
        pair = QHBoxLayout()
        pair.setSpacing(6)
        pair.addWidget(self.place_btn, 0, Qt.AlignVCenter)
        pair.addWidget(self.theme_btn, 0, Qt.AlignVCenter)
        lay.addLayout(pair)
        return bar

    # ---- the list
    def count_open(self, eid):
        """Open lines in a note: in the text being typed, and in any revision reopened with Undo."""
        if eid in self.docs:
            work, revs = self.docs[eid].toPlainText(), self.revs.get(eid, [])
        else:
            work, revs = store.parse_notes(self.note_text(eid))
        return open_lines(work) + sum(open_lines(r["text"]) for r in revs if r.get("open"))

    def refresh_open(self, eid=None):
        """Recount the open lines of one note, or of every note. Rows that have any are highlighted."""
        changed = False
        for e in ([self.store.get(eid)] if eid else self.store.entries):
            if not e:
                continue
            n = self.count_open(e["id"])
            if self.open_n.get(e["id"], 0) != n:
                self.open_n[e["id"]] = n
                changed = True
                it = self.item_for(e["id"])
                if it:
                    it.setToolTip(self.row_tip(e))
        if changed:
            self.list.viewport().update()

    def fill_list(self, select_id=None):
        self.refresh_open()
        scroll = self.list.verticalScrollBar().value()
        self.list.blockSignals(True)
        self.list.clear()
        self.section_counts, self.shown = {}, {}
        for sec, depth in self.store.flat_sections():
            key = sec["key"]
            head = QListWidgetItem()
            head.setData(ROLE_KIND, "section")
            head.setData(ROLE_ID, key)
            head.setData(ROLE_DEPTH, depth)
            head.setFlags(Qt.ItemIsEnabled)
            head.setToolTip(f"{sec['title']}: click it to pick it (+ New then adds the note here). Click the "
                            f"arrow, or double-click, to fold or unfold it. Drag it to move it. Right-click to "
                            f"sort, rename, pin, add a subcategory or remove it.")
            self.list.addItem(head)
            rows = self.ordered(key)
            self.shown[key] = [e["id"] for e in rows]
            for e in rows:
                self.section_counts[key] = self.section_counts.get(key, 0) + 1
                it = QListWidgetItem()
                it.setData(ROLE_KIND, "app")
                it.setData(ROLE_ID, e["id"])
                it.setData(ROLE_DEPTH, depth)
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
                it.setToolTip(self.row_tip(e))
                self.list.addItem(it)
        self.list.blockSignals(False)
        self.refresh_group_bar()
        self.apply_filter()
        self.list.verticalScrollBar().setValue(scroll)
        if not self.store.entries:
            self.show_entry(None)
            return
        target = select_id if self.store.get(select_id) else self.store.entries[0]["id"]
        it = self.item_for(target)
        self.list.blockSignals(True)
        self.list.setCurrentItem(it)
        self.list.blockSignals(False)
        self.show_entry(target)

    # ---- sorting a section
    def sort_of(self, key):
        choice = (self.store.state.get("sort") or {}).get(key) or {}
        by = choice.get("by") if choice.get("by") in SORT_KEYS else "manual"
        return by, bool(choice.get("rev"))

    def sort_tag(self, key):
        by, rev = self.sort_of(key)
        return SORT_TAG[by][1 if rev else 0]

    def entry_dates(self, e):
        """(made, last edited): when the note was made (an app's folder date for entries from before 2.0),
        and when its notes file last changed."""
        if e["id"] not in self.dates:
            made, changed = self.store.dates(e)
            try:
                edited = os.path.getmtime(self.store.notes_path(e["id"]))
            except OSError:
                edited = 0
            self.dates[e["id"]] = (e.get("created") or made, edited or changed)
        return self.dates[e["id"]]

    def ordered(self, key):
        """A category's notes: the pinned ones first, as they are, then the rest in the order its sort asks for."""
        rows = [e for e in self.store.entries if e["section"] == key]
        pinned = [e for e in rows if e.get("pinned")]
        return pinned + self.sort_rows([e for e in rows if not e.get("pinned")], key)

    def sort_rows(self, rows, key):
        by, rev = self.sort_of(key)
        if by == "manual":
            return rows
        rows.sort(key=lambda e: e["name"].lower())
        if by == "name":
            return rows[::-1] if rev else rows
        if time.time() - self.dates_at > 120:  # look at the folders again, at most every two minutes
            self.dates, self.dates_at = {}, time.time()
        which = 0 if by == "created" else 1
        known = sorted((e for e in rows if self.entry_dates(e)[which]), key=lambda e: self.entry_dates(e)[which],
                       reverse=not rev)
        return known + [e for e in rows if not self.entry_dates(e)[which]]

    def row_tag(self, e):
        """The small text at the right of a row: the date, when the category is sorted by a date."""
        by, _ = self.sort_of(e["section"])
        if by in ("created", "recent"):
            when = self.entry_dates(e)[0 if by == "created" else 1]
            return time.strftime("%m-%d-%y", time.localtime(when)) if when else ""
        return ""

    def set_sort(self, key, by, rev=None):
        cur_by, was = self.sort_of(key)
        if rev is None:  # no direction given: the same choice again flips it
            rev = (not was) if (by == cur_by and by != "manual") else False
        self.store.state.setdefault("sort", {})[key] = {"by": by, "rev": rev}
        self.state_dirty = True
        self.save_timer.start()
        if by in ("created", "recent"):
            self.dates_at = 0.0
        self.fill_list(self.cur)

    def section_item(self, key):
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(ROLE_KIND) == "section" and it.data(ROLE_ID) == key:
                return it
        return None

    def section_menu(self, key, at=None):
        """Right-click on a category: sort its notes, sort the categories beside it, fold, pin, rename, add a
        subcategory, move it into another one, move it up or down, remove it."""
        sec = self.store.section(key)
        if not sec:
            return
        title = sec["title"]
        m = make_menu(self)
        head = m.addAction(f"Sort the notes in {title} by")
        head.setEnabled(False)
        by, rev = self.sort_of(key)
        for label, skey, srev, tip in NOTE_SORTS:
            a = m.addAction(label, lambda b=skey, r=srev: self.set_sort(key, b, r))
            a.setCheckable(True)
            a.setChecked(by == skey and (skey == "manual" or rev == srev))
            a.setToolTip(tip + " Pinned notes stay at the top.")
        sub = make_menu(m)
        sub.setTitle("Sort the categories beside it by")
        for label, cby, crev in CATEGORY_SORTS:
            sub.addAction(label, lambda b=cby, r=crev: self.sort_categories(sec["parent"], b, r)).setToolTip(
                "Sorts this category and the others at the same level. Pinned ones stay first.")
        m.addMenu(sub)
        m.addSeparator()
        folded = key in self.folded()
        m.addAction("Unfold" if folded else "Fold", lambda: self.toggle_fold(key)).setToolTip(
            "Hides or shows everything inside it, subcategories too. A click on the heading does the same.")
        m.addAction("Unpin" if sec["pinned"] else "Pin to the top", lambda: self.toggle_row_pin("section", key)).setToolTip(
            "A pinned category stays first among the categories beside it when they are sorted.")
        m.addAction("Rename category...", lambda: self.ask_section_name(key)).setToolTip(
            "Type a new name in the box under the search field.")
        m.addAction("New subcategory...", lambda: self.ask_section_name(None, parent=key)).setToolTip(
            "Adds a category inside this one.")
        into = make_menu(m)
        into.setTitle("Move into")
        top = into.addAction("Top level", lambda: self.place_category(key, "", None))
        top.setEnabled(bool(sec["parent"]))
        inside = self.store.descendants(key) | {key}
        for o, depth in self.store.flat_sections():
            if o["key"] in inside:
                continue
            a = into.addAction("    " * depth + o["title"], lambda k=o["key"]: self.place_category(key, k, None))
            a.setEnabled(o["key"] != sec["parent"])
        m.addMenu(into)
        sib = self.store.children(sec["parent"])
        up = m.addAction("Move up", lambda: self.move_section(key, -1))
        up.setEnabled(sib.index(sec) > 0)
        down = m.addAction("Move down", lambda: self.move_section(key, 1))
        down.setEnabled(sib.index(sec) < len(sib) - 1)
        gone = m.addAction("Remove category", lambda: self.remove_section(key))
        gone.setEnabled(len(self.store.sections) > 1)
        gone.setToolTip("Takes the category away. Its notes move to the category above it (or Other) and its "
                        "subcategories move up a level. A toast offers Undo.")
        if at is None:
            it = self.section_item(key)
            at = self.list.viewport().mapToGlobal(self.list.visualItemRect(it).bottomLeft() + QPoint(14, 0))
        show_menu(m, at)

    # ---- categories
    def folded(self):
        return set(self.store.state.get("collapsed") or [])

    def header_click(self, key, on_mark):
        """A click on a category: on its arrow it folds; anywhere else it is picked, so + New adds there."""
        if on_mark:
            self.toggle_fold(key)
            return
        self.focus_sec = key
        self.list.clearSelection()
        self.list.viewport().update()

    def row_opened(self, eid):
        """A note row was clicked and let go (not dragged), or Enter was pressed on it: open it, and in
        one-pane view go to the note."""
        self.focus_sec = None
        if self.cur != eid:
            self.select(eid)
        else:
            self.list.viewport().update()
        if self.single:
            self.show_pane("note")
            self.notes.setFocus()

    def toggle_fold(self, key):
        """Fold a category (everything inside it, subcategories too, is hidden), or unfold it."""
        f = self.folded()
        f ^= {key}
        self.store.state["collapsed"] = sorted(f)
        self.state_dirty = True
        self.save_timer.start()
        self.apply_filter()

    def reveal(self, eid):
        """Unfold whatever hides a note."""
        e = self.store.get(eid)
        if not e:
            return
        chain, k = set(), e["section"]
        while k:
            chain.add(k)
            sec = self.store.section(k)
            k = sec["parent"] if sec else ""
        f = self.folded()
        if f & chain:
            self.store.state["collapsed"] = sorted(f - chain)
            self.state_dirty = True
            self.save_timer.start()
            self.apply_filter()

    def toggle_row_pin(self, kind, rid):
        """The small pin on a row: a pinned note stays at the top of its category, a pinned category first
        among the categories beside it, whatever the sort."""
        self.flush()
        if kind == "section":
            sec = self.store.section(rid)
            if not sec:
                return
            self.store.set_section_pinned(rid, not sec["pinned"])
            if sec["pinned"]:  # first among its brothers and sisters straight away
                self.store.place_section(rid, sec["parent"], None)
        else:
            e = self.store.get(rid)
            if not e:
                return
            e["pinned"] = not e.get("pinned")
            self.store.save_entries()
        self.apps_mtime = mtime(store.APPS_PATH)
        self.fill_list(self.cur)

    def sort_categories(self, parent, by, rev):
        self.flush()
        self.store.sort_sections(parent, by, rev)
        self.apps_mtime = mtime(store.APPS_PATH)
        self.fill_list(self.cur)

    def place_category(self, key, parent, after):
        self.flush()
        if self.store.place_section(key, parent, after):
            self.apps_mtime = mtime(store.APPS_PATH)
            self.fill_list(self.cur)
            it = self.section_item(key)
            if it:
                self.list.scrollToItem(it)

    def drop_section(self, key, row):
        """A category heading was dragged to `row`. Dropped right under another heading it goes inside that
        category, first; dropped anywhere else it goes after the category above, at that one's level.
        Everything inside it moves with it."""
        sec = self.store.section(key)
        if not sec:
            return
        inside = self.store.descendants(key) | {key}
        items = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(ROLE_KIND) == "section":
                items.append(("section", it.data(ROLE_ID), it.data(ROLE_ID)))
            else:
                e = self.store.get(it.data(ROLE_ID))
                items.append(("app", it.data(ROLE_ID), e["section"] if e else ""))
        above = [x for x in items[:max(0, min(row, len(items)))] if x[2] not in inside]
        if not above:
            self.place_category(key, "", None)
            return
        kind, rid, home = above[-1]
        if kind == "section":  # right under a heading: inside it, first
            self.place_category(key, rid, None)
        else:                  # among a category's notes: after that category, beside it
            target = self.store.section(home)
            if target:
                self.place_category(key, target["parent"], home)

    def ask_section_name(self, key=None, parent=""):
        """Show the name box under the search field: for a new category (inside `parent`), or to rename one."""
        self.sec_target, self.sec_parent = key, parent
        self.sec_btn.hide()
        self.sec_edit.setText(self.store.section_title(key) if key else "")
        self.sec_edit.show()
        self.sec_edit.setFocus()
        self.sec_edit.selectAll()

    def close_section_box(self):
        if self.sec_edit.isHidden():
            return
        self.sec_edit.blockSignals(True)
        self.sec_edit.hide()
        self.sec_edit.blockSignals(False)
        self.sec_btn.show()
        self.fit_sidebar()

    def commit_section(self):
        name, key, parent = self.sec_edit.text().strip(), self.sec_target, getattr(self, "sec_parent", "")
        self.close_section_box()
        if not name:
            return
        self.flush()
        if key:
            if name == self.store.section_title(key):
                return
            self.store.rename_section(key, name)
        else:
            key = self.store.add_section(name, parent)
            if parent:
                f = self.folded() - {parent}
                self.store.state["collapsed"] = sorted(f)
        self.apps_mtime = mtime(store.APPS_PATH)
        self.fill_list(self.cur)
        it = self.section_item(key)
        if it:
            self.list.scrollToItem(it)
        if self.sec_target is None:
            self.toast.say(f"Category {name} added. Drag notes into it, or right-click a note and use Move to.",
                           ms=4500)

    def move_section(self, key, step):
        self.flush()
        self.store.move_section(key, step)
        self.apps_mtime = mtime(store.APPS_PATH)
        self.fill_list(self.cur)
        it = self.section_item(key)
        if it:
            self.list.scrollToItem(it)

    def remove_section(self, key):
        self.flush()
        title = self.store.section_title(key)
        undo = self.store.remove_section(key)
        if not undo:
            return
        self.apps_mtime = mtime(store.APPS_PATH)
        self.fill_list(self.cur)
        n = len(undo["ids"])
        moved = f" Its {n} note{'' if n == 1 else 's'} moved to {self.store.section_title(undo['home'])}." if n else ""
        self.toast.say(f"Removed the category {title}.{moved}", "Undo", lambda: self.put_section(undo), ms=8000)

    def put_section(self, undo):
        self.flush()
        self.store.put_section(undo)
        self.apps_mtime = mtime(store.APPS_PATH)
        self.fill_list(self.cur)

    def row_tip(self, e):
        tip = e["name"]
        mine = self.group_tags.get(e["id"])
        if mine:
            tip += f"\nGroup{'' if len(mine) == 1 else 's'}: {', '.join(mine)}"
        todo = self.open_n.get(e["id"], 0)
        if todo:
            tip += f"\nHighlighted because its note has {todo} open line{'' if todo == 1 else 's'} not yet marked complete."
        return tip + "\nDrag to reorder. Right-click for rename, folder, move and remove."

    def copy_note(self):
        """Put the whole note on the clipboard: name, open text, then each revision under its stamp."""
        e = self.store.get(self.cur)
        doc = self.docs.get(self.cur)
        if not e or doc is None:
            return
        work, revs = doc.toPlainText(), self.revs.get(self.cur, [])
        if not work.strip() and not revs and not self.imgs.get(self.cur):
            self.toast.say("This note is empty, so there is nothing to copy yet.", ms=2500)
            return
        self.to_clipboard(store.readable_notes(e["name"], work, revs, self.imgs.get(self.cur, []),
                                               self.entry_folder(self.cur)))
        self.toast.say(f"Copied the whole note ({len(revs)} revision{'' if len(revs) == 1 else 's'} included)")

    def stop_clip_queue(self):
        """Drop whatever a Revisions complete still had to copy, and its bubble that was counting pictures."""
        if self.clip_queue:
            self.bubble.hide()
        self.clip_run += 1
        self.clip_queue = []
        self.clip_timer.stop()

    def to_clipboard(self, text):
        """One plain copy. It replaces whatever a Revisions complete still had queued."""
        self.stop_clip_queue()
        self.put_text(text)

    def put_text(self, text):
        if TEST:
            self.clip = text  # test runs never touch the real clipboard
            self.clip_log.append(("text", text))
        else:
            QApplication.clipboard().setText(text)

    def put_pixels(self, path):
        """Put one picture on the clipboard as a picture and nothing else: the form that Windows
        clipboard history (Win+V) keeps. False when the file cannot be read as a picture."""
        if not os.path.isfile(path):
            return False
        if TEST:
            self.clip_image = path
            self.clip_log.append(("image", path))
            return True
        mime = self.pixels_mime(path)
        if mime is None:
            return False
        QApplication.clipboard().setMimeData(mime)
        return True

    @staticmethod
    def pixels_mime(path):
        """A picture's pixels and nothing else (no file, no text), or None when it cannot be read."""
        img = QImage(path)
        if img.isNull():
            return None
        mime = QMimeData()
        mime.setImageData(img)
        return mime

    def copy_revision(self, eid, text, beside, pictures=()):
        """Revisions complete also copies what was just completed. Its pictures go on the clipboard
        first, one at a time with a short pause between them, so that Windows clipboard history (Win+V)
        keeps every one. The text goes last, so Ctrl+V pastes the text: the entry's name, a blank line,
        the text, then the full path of each picture and video. A video cannot go in clipboard history,
        so it is only listed by its path. A small bubble next to the button that was pressed says how
        far along it is; `beside` returns that button once the pane has settled."""
        e = self.store.get(eid)
        words = store.readable_notes(e["name"] if e else "", text, [], pictures, self.entry_folder(eid))
        stills = [self.store.image_path(eid, n) for n in pictures if not media.is_video(n)]
        self.stop_clip_queue()
        self.clip_queue = [("image", p) for p in stills if os.path.isfile(p)] + [("text", words)]
        self.clip_total, self.clip_i = len(self.clip_queue) - 1, 0
        self.clip_eid, self.clip_beside = eid, beside
        self.clip_step()

    def clip_step(self):
        """Put the next queued thing on the clipboard. The rest follow, one pause apart."""
        say = ""
        while self.clip_queue and not say:
            kind, value = self.clip_queue.pop(0)
            if kind == "text":
                self.put_text(value)
                n = self.clip_i
                say = (f"Copied {n} picture{'' if n == 1 else 's'} for Win+V, then the notes for Ctrl+V"
                       if n else "Copied to clipboard")
            elif self.put_pixels(value):
                self.clip_i += 1
                say = f"Copying picture {self.clip_i} of {self.clip_total}"
        more = bool(self.clip_queue)
        if more:
            self.clip_timer.start(self.clip_gap)
        if say and self.clip_eid == self.cur and self.clip_beside:
            beside, ms = self.clip_beside, (self.clip_gap + 1500 if more else (3500 if self.clip_i else 1800))
            run = self.clip_run  # a newer copy in the meantime means this bubble is out of date
            QTimer.singleShot(0, lambda: self.bubble_beside(beside(), say, ms) if run == self.clip_run else None)

    def bubble_beside(self, widget, text="Copied to clipboard", ms=1800):
        if widget is None or not widget.isVisible():
            return
        self.bubble.anchor = widget.mapTo(self.notes_content,
                                          QPoint(widget.width() + 10, (widget.height() - self.bubble.height()) // 2))
        self.bubble.say(text, ms=ms)

    def item_for(self, eid):
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(ROLE_KIND) == "app" and it.data(ROLE_ID) == eid:
                return it
        return None

    def select(self, eid, push=True):
        it = self.item_for(eid)
        if not it:
            return
        if it.isHidden():
            self.search.clear()
            self.reveal(eid)
        self._push = push
        self.list.setCurrentItem(it)
        self._push = True
        self.list.scrollToItem(it)

    def on_current(self, cur, _prev):
        if cur and cur.data(ROLE_KIND) == "app":
            self.focus_sec = None
            self.show_entry(cur.data(ROLE_ID), self._push)  # one-pane view: the note shows on release

    def note_text(self, eid):
        if eid in self.docs:
            return store.join_notes(self.docs[eid].toPlainText(), self.revs.get(eid, []), self.imgs.get(eid, []))
        if eid not in self.note_cache:
            self.note_cache[eid] = self.store.read_notes(eid)
        return self.note_cache[eid]

    def apply_filter(self):
        """Hide what the search box, the group being shown or a folded category leaves out. Searching looks
        through every note and ignores folding while it does. The note that is open keeps its row (unless a
        category above it is folded)."""
        words = self.search.text().lower().split()
        only = self.shown_ids() if (not words and self.group_active()) else None
        narrowed = bool(words) or only is not None
        self.list.setDragEnabled(not narrowed)
        folded = set() if words else self.folded()
        self.group_counts = {}
        heads, stack, content = [], [], {}
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(ROLE_KIND) == "section":
                key, d = it.data(ROLE_ID), int(it.data(ROLE_DEPTH) or 0)
                while stack and stack[-1][0] >= d:
                    stack.pop()
                heads.append((it, key, any(k in folded for _d, k in stack)))
                stack.append((d, key))
                content[key] = False
                if only is not None:
                    self.group_counts[key] = 0
                continue
            e = self.store.get(it.data(ROLE_ID))
            hit = True
            if words and e:
                hay = " ".join((e["name"], e["tldr"],
                                self.ideas_text(e["id"]), self.note_text(e["id"]))).lower()
                hit = all(w in hay for w in words)
            elif only is not None:
                hit = it.data(ROLE_ID) in only or it.data(ROLE_ID) == self.cur
                if hit and stack:
                    self.group_counts[stack[-1][1]] += 1
            it.setHidden(not hit or any(k in folded for _d, k in stack))
            if hit:
                for _d, k in stack:
                    content[k] = True
        for it, key, under_fold in heads:
            it.setHidden(under_fold or (narrowed and not content.get(key)))
        self.list.viewport().update()

    def on_moved(self):
        """A row was dragged: its section is whichever heading now sits above it. The section it landed
        in keeps what is on screen as its own order (a sorted section goes back to My order); sections
        that were not touched keep their order, sorted or not."""
        keys = self.store.section_keys()
        now, section = {k: [] for k in keys}, keys[0]
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(ROLE_KIND) == "section":
                section = it.data(ROLE_ID)
            else:
                now.setdefault(section, []).append(it.data(ROLE_ID))
        mine = {k: [e["id"] for e in self.store.entries if e["section"] == k] for k in keys}
        self.remember_move()
        pairs = []
        for k in keys:
            was = self.shown.get(k, [])
            if now[k] == was:
                order = mine[k]                                   # untouched: keep its own order
            elif set(now[k]) < set(was):
                order = [i for i in mine[k] if i in now[k]]       # a row only left it
            else:
                order = now[k]                                    # a row landed or moved here
                if self.sort_of(k)[0] != "manual":
                    self.store.state.setdefault("sort", {})[k] = {"by": "manual", "rev": False}
                    self.state_dirty = True
            pairs += [(i, k) for i in order]
        self.store.reorder(pairs)
        self.apps_mtime = mtime(store.APPS_PATH)
        self.fill_list(self.cur)

    def move_snap(self):
        """Where every note is (its category and order) and how each category is sorted."""
        return [(e["id"], e["section"]) for e in self.store.entries], copy.deepcopy(self.store.state.get("sort") or {})

    def remember_move(self):
        """Just before a note is moved: keep how things were, for Ctrl+Z. A new move ends any redo."""
        self.move_undo.append((self.move_snap(), self.cur))
        del self.move_undo[:-60]
        self.move_redo.clear()

    def step_move(self, take, give, said):
        """Ctrl+Z (or Ctrl+Y) on a move: put the notes back where they were (or where they went).
        Typing fields keep Ctrl+Z for their own text, so this only answers in the list and the rest of the window."""
        if not take:
            self.toast.say("Nothing to undo" if said == "Undid" else "Nothing to redo", ms=1800)
            return
        self.flush()
        (pairs, sort), eid = take.pop()
        give.append((self.move_snap(), self.cur))
        keys = set(self.store.section_keys())
        now = {e["id"]: e["section"] for e in self.store.entries}
        self.store.reorder([(i, k if k in keys else now[i]) for i, k in pairs if i in now])
        self.store.state["sort"] = sort
        self.state_dirty = True
        self.apps_mtime = mtime(store.APPS_PATH)
        target = eid if self.store.get(eid) else self.cur
        self.fill_list(target)
        if self.item_for(target):
            self.reveal(target)
            self.list.scrollToItem(self.item_for(target))
        self.toast.say(f"{said} the move", ms=2000)

    def list_menu(self, pos):
        it = self.list.itemAt(pos)
        m = make_menu(self)
        if it and it.data(ROLE_KIND) == "app":
            eid = it.data(ROLE_ID)
            e = self.store.get(eid)
            self.select(eid)
            m.addAction("Rename\tF2", self.start_rename).setToolTip("Change the name shown in the list.")
            m.addAction("Fork", lambda: self.fork_entry(eid)).setToolTip(
                "Makes a copy right below it, named with _v2 (or the next free number).")
            m.addAction("Unpin" if e.get("pinned") else "Pin to the top", lambda: self.toggle_row_pin("app", eid)).setToolTip(
                "A pinned note stays at the top of its category whatever the sort.")
            folder = self.store.folder(e)
            if folder and os.path.isdir(folder):
                m.addAction("Open folder", self.open_folder).setToolTip("Opens this app's folder in Explorer.")
            if self.store.launcher(e):
                m.addAction("Launch", self.launch).setToolTip("Runs its launcher.")
            m.addAction("Change linked folder...", self.pick_folder).setToolTip(
                "Pick the folder this entry points at. Opens a normal Explorer folder picker.")
            m.addAction("Change launcher...", self.pick_launcher).setToolTip(
                "Point the Launch button at the .bat, .exe or other file that launches the app. Opens a "
                "normal Explorer file picker.")
            sub = make_menu(m)
            sub.setTitle("Move to")
            for sec, depth in self.store.flat_sections():
                a = sub.addAction("    " * depth + sec["title"], lambda k=sec["key"]: self.move_to(eid, k))
                a.setEnabled(sec["key"] != e["section"])
            m.addMenu(sub)
            sub = make_menu(m)
            sub.setTitle("Groups")
            self.fill_group_menu(sub, eid)
            m.addMenu(sub)
            m.addSeparator()
            m.addAction("Remove\tDel", lambda: self.remove_entry(eid)).setToolTip(
                "Takes it off the list. The notes are kept in data/removed and it can be restored.")
        elif it and it.data(ROLE_KIND) == "section":
            self.section_menu(it.data(ROLE_ID), self.list.viewport().mapToGlobal(pos))
            return
        else:
            m.addAction("New\tCtrl+N", self.new_entry)
            m.addAction("New category...", lambda: self.ask_section_name(None))
        gone = self.store.removed()
        if gone:
            m.addSeparator()
            sub = make_menu(m)
            sub.setTitle(f"Restore removed ({len(gone)})")
            for rec in reversed(gone[-20:]):
                rid = rec["entry"].get("id")
                sub.addAction(f"{rec['entry'].get('name', rid)}    {rec.get('removed', '')}",
                              lambda r=rid: self.restore_entry(r))
            m.addMenu(sub)
        show_menu(m, self.list.viewport().mapToGlobal(pos))

    # ---- groups
    def load_groups(self):
        """Groups are kept in state.json as [{id, name, ids}], with group_view naming the one the list
        shows ('' for every note). The single working group of 1.9 becomes a group with that name."""
        st = self.store.state
        groups = []
        for g in st.get("groups") if isinstance(st.get("groups"), list) else []:
            if isinstance(g, dict) and g.get("id") and str(g.get("name") or "").strip():
                groups.append({"id": str(g["id"]), "name": str(g["name"]).strip(),
                               "ids": list(dict.fromkeys(str(i) for i in g.get("ids") or []))})
        if "group" in st or "group_on" in st:
            old = [str(i) for i in st.pop("group", None) or []]
            on = bool(st.pop("group_on", False))
            if old and not groups:
                groups.append({"id": "g1", "name": "Working group", "ids": list(dict.fromkeys(old))})
                st["group_view"] = "g1" if on else ""
            self.state_dirty = True
            self.save_timer.start()
        st["groups"] = groups
        st["group_view"] = self.view_ids()

    def groups(self):
        return self.store.state["groups"]

    def group_by_id(self, gid):
        return next((g for g in self.groups() if g["id"] == gid), None)

    def members(self, g):
        """The notes in a group, leaving out any that are no longer in the list."""
        return [i for i in g["ids"] if self.store.get(i)] if g else []

    def view_ids(self):
        """The ids of the groups the list is set to show (any number of them; none means every note)."""
        v = self.store.state.get("group_view")
        ids = [v] if isinstance(v, str) else (v if isinstance(v, list) else [])
        return [i for i in dict.fromkeys(str(x) for x in ids if x) if self.group_by_id(i)]

    def view_groups(self):
        return [self.group_by_id(i) for i in self.view_ids()]

    def view_group(self):
        """The first group the list is set to show, or None for every note."""
        gs = self.view_groups()
        return gs[0] if gs else None

    def shown_ids(self):
        """Every note in the groups being shown."""
        return {i for g in self.view_groups() for i in self.members(g)}

    def group_active(self):
        """True while the list shows only some groups."""
        return bool(self.shown_ids())

    def groups_of(self, eid):
        return [g for g in self.groups() if eid in g["ids"]]

    def make_group(self, ids=()):
        """A new group with a name nobody has yet. The caller says when to redraw."""
        names = {g["name"].lower() for g in self.groups()}
        name, n = "New group", 2
        while name.lower() in names:
            name, n = f"New group {n}", n + 1
        k = 1
        while self.group_by_id(f"g{k}"):
            k += 1
        g = {"id": f"g{k}", "name": name, "ids": [i for i in dict.fromkeys(ids) if self.store.get(i)]}
        self.groups().append(g)
        return g

    def groups_changed(self):
        """Something about the groups changed: save it and redraw everything that shows them."""
        st = self.store.state
        st["group_view"] = [i for i in self.view_ids() if self.members(self.group_by_id(i))]  # gone or empty: dropped
        self.state_dirty = True
        self.save_timer.start()
        self.refresh_groups()

    def refresh_groups(self):
        self.refresh_group_bar()
        self.apply_filter()
        self.refresh_group_chip()
        for i in range(self.list.count()):
            it = self.list.item(i)
            e = self.store.get(it.data(ROLE_ID)) if it.data(ROLE_KIND) == "app" else None
            if e:
                it.setToolTip(self.row_tip(e))
        self.list.viewport().update()

    def refresh_group_bar(self):
        """The buttons above the list: All notes, then one per group. Every group being shown is lit, and
        All notes while it shows everything."""
        view = self.view_groups() if self.group_active() else []
        every = button("All notes", "chip", "Show every note in the list.")
        every.setProperty("lit", not view)  # lit gold like a group's chip when it is what the list shows
        every.clicked.connect(lambda: self.show_group(""))
        chips, self.group_chips, self.all_chip = [every], {}, every
        for g in self.groups():
            n = len(self.members(g))
            if not n:
                tip = f"{g['name']} has no notes yet. Click to pick them."
            elif g in view:
                tip = (f"The list shows the {n} note{'' if n == 1 else 's'} in {g['name']}"
                       f"{' with the other lit groups' if len(view) > 1 else ''}. Click to stop showing it.")
            else:
                tip = (f"Show the {n} note{'' if n == 1 else 's'} in {g['name']}; click more groups to show "
                       f"them too.")
            b = button(f"{short_name(g['name'])}  {n}", "chip", tip + "\nRight-click to edit or delete this group.")
            b.setProperty("lit", g in view)
            b.clicked.connect(lambda _=False, i=g["id"]: self.show_group(i))
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda pos, i=g["id"], b=b: self.group_chip_menu(i, b.mapToGlobal(pos)))
            chips.append(b)
            self.group_chips[g["id"]] = b
        self.group_bar.set_items(chips)
        self.group_tags = {}
        for g in self.groups():
            for i in g["ids"]:
                self.group_tags.setdefault(i, []).append(g["name"])

    def refresh_group_chip(self):
        """The chip in the note's header: which groups this note is in."""
        mine = self.group_tags.get(self.cur) or []
        if not mine:
            self.group_btn.setText("No group")
            tip = "This note is in no group."
        else:
            self.group_btn.setText(f"Group: {mine[0]}" if len(mine) == 1 else f"Groups: {mine[0]} +{len(mine) - 1}")
            tip = f"This note is in: {', '.join(mine)}."
        self.group_btn.setToolTip(tip + " Click to put it in a group, take it out of one, or make a new group. "
                                        "A group is a short list of notes to work on together; the buttons "
                                        "above the list show one group at a time.")
        self.chips_row.place()

    def show_group(self, gid, only=False):
        """A group's button: show its notes too, or stop showing it if it is lit. '' shows every note again.
        `only` shows that one group alone. A group with no notes yet opens for picking."""
        g = self.group_by_id(gid)
        if g and not self.members(g):
            self.open_groups(g["id"])
            return
        st = self.store.state
        view = self.view_ids()
        if not g:
            view = []
        elif only:
            view = [g["id"]]
        elif g["id"] in view:
            view.remove(g["id"])
        else:
            view.append(g["id"])
        st["group_view"] = view
        if view:
            st["group_last"] = list(view)
        self.state_dirty = True
        self.save_timer.start()
        self.refresh_groups()
        it = self.item_for(self.cur)
        if it:
            self.list.scrollToItem(it)

    def toggle_group_view(self):
        """Ctrl+G: from a group back to every note, or from every note to the group shown last."""
        if self.group_active():
            self.show_group("")
            return
        last = self.store.state.get("group_last") or []
        last = [last] if isinstance(last, str) else last
        last = [i for i in last if self.members(self.group_by_id(i))]
        if not last:
            g = next((o for o in self.groups() if self.members(o)), None)
            last = [g["id"]] if g else []
        if last:
            self.store.state["group_view"] = last
            self.state_dirty = True
            self.save_timer.start()
            self.refresh_groups()
        else:
            self.open_groups(new=not self.groups())

    def open_groups(self, gid="", new=False, with_ids=()):
        """Open the groups panel: on a given group, else the one being shown, else the last, else the first."""
        self.refresh_open()
        if not new and not self.group_by_id(gid):
            last = self.store.state.get("group_last") or []
            last = last[0] if isinstance(last, list) and last else (last if isinstance(last, str) else "")
            g = self.view_group() or self.group_by_id(last)
            gid = g["id"] if g else ""
        self.groups_panel.open(gid, new, with_ids)

    def groups_panel_closed(self, gid, touched):
        """The panel was closed. If a group was changed in it, the list now shows that group."""
        g = self.group_by_id(gid)
        if touched and self.members(g) and gid not in self.view_ids():
            self.show_group(g["id"])  # shown along with any groups already lit
        else:
            self.groups_changed()

    def toggle_membership(self, gid, eid, quiet=False):
        g, e = self.group_by_id(gid), self.store.get(eid)
        if not g or not e:
            return
        if eid in g["ids"]:
            g["ids"].remove(eid)
            said = f"Took {e['name']} out of {g['name']}"
        else:
            g["ids"].append(eid)
            said = f"Added {e['name']} to {g['name']}"
        self.groups_changed()
        if not quiet:
            self.toast.say(said, "Undo", lambda: self.toggle_membership(gid, eid, quiet=True), ms=5000)

    def fill_group_menu(self, m, eid):
        """Every group with a tick while this note is in it, then the two ways into the panel."""
        for g in self.groups():
            a = m.addAction(g["name"], lambda i=g["id"]: self.toggle_membership(i, eid))
            a.setCheckable(True)
            a.setChecked(eid in g["ids"])
            a.setToolTip("This note is in this group. Click to take it out." if eid in g["ids"]
                         else "Click to put this note in this group.")
        if self.groups():
            m.addSeparator()
        m.addAction("New group with this note...", lambda: self.open_groups(new=True, with_ids=[eid])).setToolTip(
            "Makes a group that starts with this note in it, then lets you name it and add more.")
        mine = self.groups_of(eid)
        m.addAction("Edit groups...", lambda: self.open_groups(mine[0]["id"] if mine else "")).setToolTip(
            "Opens the groups panel: change which notes are in a group, rename it, delete it, or make another.")

    def group_menu(self):
        if not self.cur:
            return
        m = make_menu(self)
        self.fill_group_menu(m, self.cur)
        show_menu(m, self.group_btn.mapToGlobal(QPoint(0, self.group_btn.height() + 4)))

    def group_chip_menu(self, gid, at):
        g = self.group_by_id(gid)
        if not g:
            return
        m = make_menu(self)
        m.addAction("Edit this group...", lambda: self.open_groups(gid)).setToolTip(
            "Change which notes are in it, or rename it.")
        m.addAction("Delete group", lambda: self.delete_group(gid)).setToolTip(
            "Deletes the group. The notes themselves are not touched, and a toast offers Undo.")
        show_menu(m, at)

    def delete_group(self, gid):
        g = self.group_by_id(gid)
        if not g:
            return
        at, view = self.groups().index(g), self.view_ids()
        self.groups().remove(g)
        self.groups_changed()
        self.toast.say(f"Deleted the group {g['name']}", "Undo", lambda: self.put_group(g, at, view), ms=7000)

    def put_group(self, g, at, view):
        if self.group_by_id(g["id"]):
            return
        self.groups().insert(min(at, len(self.groups())), g)
        self.store.state["group_view"] = view
        self.groups_changed()

    # ---- showing an entry
    def doc_for(self, eid):
        doc = self.docs.get(eid)
        if doc is None:
            work, images, revs = store.parse_note(self.store.read_notes(eid))
            self.imgs[eid] = images
            doc = QTextDocument(self)
            doc.setDocumentMargin(6)
            doc.setDefaultFont(ui_font(self.notes_px))
            doc.setPlainText(work)
            doc.clearUndoRedoStacks()
            DoneHighlighter(doc)
            self.docs[eid] = doc
            self.revs[eid] = revs
            self.mtimes[eid] = mtime(self.store.notes_path(eid))
            self.note_cache.pop(eid, None)
        return doc

    def sync_doc(self, eid):
        """Pick up a notes file that was changed on disk by something else (never over unsaved typing)."""
        doc = self.docs.get(eid)
        path = self.store.notes_path(eid)
        if doc is None or eid in self.dirty or mtime(path) == self.mtimes.get(eid):
            return
        pos = self.notes.textCursor().position() if eid == self.cur else 0
        work, images, revs = store.parse_note(self.store.read_notes(eid))
        self.imgs[eid] = images
        self.set_work_text(eid, work)
        self.revs[eid] = revs
        self.mtimes[eid] = mtime(path)
        self.refresh_open(eid)
        if eid == self.cur:
            self.place_cursor(pos)
            self.refresh_history()
            self.refresh_strip()
            self.refresh_counts()
            self.refresh_tokens()

    def set_work_text(self, eid, text):
        """Replace an entry's open text from code (a reload or a strike), without it counting as typing."""
        self._loading = True
        self.docs[eid].setPlainText(text)
        self.docs[eid].clearUndoRedoStacks()
        self._loading = False
        if eid == self.cur:
            self.update_strike_btn()

    def place_cursor(self, pos):
        c = self.notes.textCursor()
        c.setPosition(max(0, min(int(pos), self.notes.document().characterCount() - 1)))
        self.notes.setTextCursor(c)
        self.caret_moved()

    def caret_moved(self):
        if not self._loading:
            QTimer.singleShot(0, self.keep_caret_in_view)  # after the box has grown to fit the new text

    def keep_caret_in_view(self):
        """The notes pane scrolls as one piece, so follow the caret by hand."""
        r = self.notes.cursorRect()
        p = self.notes.mapTo(self.notes_content, r.center())
        self.scroll.ensureVisible(p.x(), p.y(), 0, r.height() * 2)

    def set_notes_focus(self, on):
        if self.notes_box.property("focused") != on:
            self.notes_box.setProperty("focused", on)
            self.notes_box.style().unpolish(self.notes_box)
            self.notes_box.style().polish(self.notes_box)

    def remember_cursor(self):
        if self.cur and self.cur in self.docs:
            self.store.state.setdefault("cursor", {})[self.cur] = self.notes.textCursor().position()

    def show_entry(self, eid, push=True):
        if self.fresh_id and eid != self.fresh_id:
            QTimer.singleShot(0, self.drop_fresh)
        if self.title_edit.isVisible():
            self.commit_rename()
        self.remember_cursor()
        e = self.store.get(eid)
        self.cur = e["id"] if e else None
        self.stack.setCurrentIndex(0 if e else 1)
        if not e:
            self.path_lbl.setText("")
            return
        if push and (not self.hist or self.hist[self.hist_i] != eid):
            del self.hist[self.hist_i + 1:]
            self.hist.append(eid)
            self.hist_i = len(self.hist) - 1
        self._loading = True
        doc = self.doc_for(eid)
        doc.setDefaultFont(self.notes.font())
        self.notes.setDocument(doc)
        self.notes.setTabStopDistance(4 * self.notes.fontMetrics().horizontalAdvance(" "))
        self.notes.fit()
        self.tldr.setPlainText(e["tldr"])
        self.ideas.setPlainText(self.ideas_text(eid))
        self._loading = False
        self.sync_doc(eid)
        self.refresh_history()
        self.refresh_strip()
        self.tok_rev = 0
        self.refresh_tokens()
        self.scroll.verticalScrollBar().setValue(0)
        self.place_cursor(self.store.state.get("cursor", {}).get(eid, 0))
        self.refresh_header()
        self.refresh_counts()
        self.update_strike_btn()
        if self.group_active() and not self.search.text().strip():
            self.apply_filter()  # the note that is open keeps its row even when it is outside the group

    def refresh_header(self):
        e = self.store.get(self.cur)
        if not e:
            return
        self.title.setText(e["name"])
        self.refresh_group_chip()
        self.chips_row.place()
        folder = self.store.folder(e)
        found = bool(folder) and os.path.isdir(folder)
        self.folder_btn.setVisible(found)
        narrow = bool(self.compact and self.compact[0])
        self.link_btn.setVisible(not (narrow and found))  # in a narrow window it is in the row's right-click menu
        if not folder:
            self.link_btn.setText("Link folder")
            self.link_btn.setToolTip("No folder is linked yet. Pick this app's folder with a normal Explorer "
                                     "folder picker.")
        elif found:
            self.link_btn.setText("Change linked folder")
            self.link_btn.setToolTip(f"Linked to {store.contract_dir(folder)}\nClick to point this entry at a different "
                                     f"folder, for "
                                     f"when the wrong one was linked. A toast offers Undo.")
        else:
            self.link_btn.setText("Change linked folder")
            self.link_btn.setToolTip(f"The linked folder was not found: {store.contract_dir(folder)}\n"
                                     f"Click to pick where it lives now.")
        self.path_lbl.setText(store.contract_dir(folder) if folder else "No folder linked")
        bat = self.store.launcher(e)
        if bat:
            how = "linked by you" if self.store.linked_launcher(e) else "found automatically"
            self.launch_btn.setText("Launch")
            self.launch_btn.setToolTip(f"Runs {self.short_path(bat, folder)} ({how}), the same as double-clicking "
                                       f"it.\nRight-click to link a different launcher.")
        else:
            self.launch_btn.setText("Link launcher")
            self.launch_btn.setToolTip("No launcher was found for this entry. Click and point it at the .bat, "
                                       ".exe, .cmd, shortcut or other file that launches the app. After that "
                                       "this button launches it.")
        self.launch_btn.show()  # the row wraps, so these fit in any width
        it = self.item_for(e["id"])
        if it:
            it.setToolTip(self.row_tip(e))
        self.list.viewport().update()

    def refresh_counts(self):
        if not self.cur or self.cur not in self.docs:
            self.counts.setText("")
            return
        lines = [ln for ln in self.docs[self.cur].toPlainText().split("\n") if ln.strip()]
        done = sum(1 for ln in lines if DONE_RE.match(ln))
        revs = len(self.revs.get(self.cur, []))
        bits = [f"{len(lines) - done} open, {done} done"] if lines else []
        if revs:
            bits.append(f"{revs} revision" + ("s" if revs != 1 else ""))
        editing = sum(1 for r in self.revs.get(self.cur, []) if r.get("open"))
        if editing:
            bits.append(f"{editing} reopened")
        self.counts.setText("  \u00b7  ".join(bits))

    def refresh_history(self):
        self.history.show_revisions(self.revs.get(self.cur, []), self.notes_px, self.entry_folder(self.cur))

    def update_strike_btn(self):
        doc = self.docs.get(self.cur)
        on = doc is not None and (not doc.isEmpty() or bool(self.imgs.get(self.cur)))
        nxt = max((r["n"] for r in self.revs.get(self.cur, [])), default=0) + 1
        self.strike_btn.setEnabled(on)
        self.strike_glow.setEnabled(on)
        self.strike_btn.setToolTip(f"Marks everything typed above as done: it is greyed out and filed as "
                                   f"Revision {nxt}, with the date and time, right under this button. The space "
                                   f"above is cleared for new notes, and the completed text is copied to the clipboard. "
                                   f"Pictures on it are copied first, one at a time, so Win+V has each of them and "
                                   f"Ctrl+V pastes the text. Click Undo on a revision's tag to edit that revision again.")

    # ---- strike through, revisions, text size
    def strike(self):
        eid, doc = self.cur, self.docs.get(self.cur)
        if doc is None:
            return
        text = "\n".join(ln.rstrip() for ln in doc.toPlainText().split("\n")).strip("\n")
        pics = list(self.imgs.get(eid, []))
        if not text.strip() and not pics:
            return
        revs = self.revs.setdefault(eid, [])
        n = max((r["n"] for r in revs), default=0) + 1
        rev = {"n": n, "stamp": time.strftime("%m-%d-%y %H:%M"), "text": text}
        if pics:
            rev["images"] = pics  # the pictures go with the batch they were added to
        revs.insert(0, rev)
        self.imgs[eid] = []
        self.set_work_text(eid, "")
        self.revisions_changed(eid)
        self.copy_revision(eid, text, lambda: self.strike_kbd, pics)
        self.notes.setFocus()
        self.scroll.verticalScrollBar().setValue(0)
        self.toast.say(f"Filed as Revision {n}", "Undo", lambda: self.undo_filing(eid, n), ms=7000)

    def revisions_changed(self, eid):
        self.dirty.add(eid)
        self.flush()
        if eid == self.cur:
            self.refresh_history()
            self.refresh_strip()
            self.refresh_counts()
            self.update_strike_btn()
            self.refresh_tokens()

    def unstrike(self, eid, n):
        """Take a revision out of the finished list and put its text back at the top of the open notes."""
        revs = self.revs.get(eid, [])
        rev = next((r for r in revs if r["n"] == n), None)
        if rev is None or eid not in self.docs:
            return
        revs.remove(rev)
        self.imgs[eid] = list(rev.get("images") or []) + self.imgs.get(eid, [])  # its pictures come back too
        now = self.docs[eid].toPlainText()
        self.set_work_text(eid, rev["text"] + ("\n" + now if now.strip() else ""))
        self.revisions_changed(eid)
        if eid == self.cur:
            self.place_cursor(len(rev["text"]))
            self.notes.setFocus()
        self.toast.say(f"Revision {n} is back in your open notes")

    def find_rev(self, eid, n):
        return next((r for r in self.revs.get(eid, []) if r["n"] == n), None)

    def undo_filing(self, eid, n):
        """Undo on the toast right after Revisions complete. If nothing new has been typed, the text
        simply goes back where it was. If there is new text, the revision is reopened in place instead,
        so the new notes are left alone."""
        doc = self.docs.get(eid)
        if doc is not None and not doc.toPlainText().strip():
            self.unstrike(eid, n)
        else:
            self.reopen_revision(eid, n)

    def reopen_revision(self, eid, n):
        """Undo on a revision's tag: that revision becomes editable again where it is. The text being
        typed at the top of the note is not touched."""
        rev = self.find_rev(eid, n)
        if rev is None or rev.get("open"):
            return
        rev["open"] = True
        rev["was"] = rev["text"]  # kept in memory only, to tell later whether it was changed
        self.revisions_changed(eid)
        if eid == self.cur:
            self.history.focus(n)
            QTimer.singleShot(0, lambda: self.show_revision(n))

    def follow_rev_caret(self, body):
        """Keep the caret of a reopened revision in view while typing in it."""
        def look():
            if body in self.history.bodies.values():
                r = body.cursorRect()
                spot = body.mapTo(self.notes_content, r.center())
                self.scroll.ensureVisible(spot.x(), spot.y(), 0, r.height() * 2)
        QTimer.singleShot(0, look)

    def show_revision(self, n):
        body = self.history.bodies.get(n)
        if body is not None:
            self.scroll.ensureWidgetVisible(body, 0, 60)

    def revision_edited(self, n, text):
        """Typing in a reopened revision."""
        rev = self.find_rev(self.cur, n)
        if rev is None or not rev.get("open") or rev["text"] == text:
            return
        rev["text"] = text
        self.dirty.add(self.cur)
        self.save_timer.start()
        self.refresh_tokens()

    def close_revision(self, eid, n):
        """Revisions complete on a reopened revision: it is greyed out again under its own number. Its
        stamp moves to now if the text was changed. A revision emptied out is removed (with Undo)."""
        rev = self.find_rev(eid, n)
        if rev is None or not rev.get("open"):
            return
        text = "\n".join(ln.rstrip() for ln in rev["text"].split("\n")).strip("\n")
        if not text.strip():
            self.delete_revision(eid, n)
            return
        if text != rev.pop("was", None):
            rev["stamp"] = time.strftime("%m-%d-%y %H:%M")
        rev.pop("open", None)
        rev["text"] = text
        self.revisions_changed(eid)
        self.copy_revision(eid, text, lambda: self.history.tags.get(n), rev.get("images") or [])
        if eid == self.cur:
            self.notes.setFocus()
        self.toast.say(f"Revision {n} is complete again")

    def delete_revision(self, eid, n):
        revs = self.revs.get(eid, [])
        rev = next((r for r in revs if r["n"] == n), None)
        if rev is None:
            return
        at = revs.index(rev)
        revs.pop(at)
        self.revisions_changed(eid)
        self.toast.say(f"Deleted Revision {n}", "Undo", lambda: self.put_revision(eid, at, rev), ms=7000)

    def put_revision(self, eid, at, rev):
        revs = self.revs.setdefault(eid, [])
        revs.insert(min(at, len(revs)), rev)
        self.revisions_changed(eid)

    def zoom_notes(self, step):
        px = 14 if step == 0 else max(9, min(34, self.notes_px + step))
        if px == self.notes_px:
            return
        self.notes_px = px
        self.store.state["notes_px"] = px
        self.state_dirty = True
        self.save_timer.start()
        self.apply_notes_font()

    def apply_notes_font(self):
        f = notes_font(self.notes_px)
        self.notes.setFont(f)
        self.notes.document().setDefaultFont(f)
        self.notes.setTabStopDistance(4 * self.notes.fontMetrics().horizontalAdvance(" "))
        self.notes.fit()
        self.ideas.setFont(notes_font(self.notes_px + 2))  # a little larger than the notes, so it stands out
        self.ideas.fit()
        self.refresh_history()
        self.caret_moved()

    # ---- pictures
    def entry_folder(self, eid):
        """Where the entry's pictures and videos are: images/<entry name>/."""
        e = self.store.get(eid)
        return self.store.media_dir(e) if e else ""

    def picture_names(self, eid, rev_n):
        """The picture names of the notes being typed (rev_n 0) or of one revision."""
        if not rev_n:
            return self.imgs.get(eid, [])
        return (self.find_rev(eid, rev_n) or {}).get("images") or []

    def refresh_strip(self):
        names = self.imgs.get(self.cur, []) if self.cur else []
        self.strip.show_images([self.store.image_path(self.cur, n) for n in names])

    def pick_images(self):
        if not self.cur:
            return
        start = store.expand_dir(self.store.state.get("last_picture_dir", ""))
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add pictures or videos to this note", start or "",
            "Pictures and videos (*.png *.jpg *.jpeg *.jfif *.webp *.bmp *.gif *.tif *.tiff "
            "*.mp4 *.mov *.webm *.mkv *.avi *.m4v *.wmv);;All files (*.*)")
        if files:
            self.store.state["last_picture_dir"] = store.contract_dir(os.path.dirname(os.path.normpath(files[0])))
            self.state_dirty = True
            self.add_images(files)

    def add_images(self, items):
        """Pictures and videos picked, dropped or pasted onto the notes being typed. Each is copied into
        images/<entry name>/ (a pasted picture is saved there as a PNG) and shown in the strip above the
        button."""
        eid = self.cur
        if not eid or eid not in self.docs:
            return
        added = []
        for it in items:
            try:
                if isinstance(it, str):
                    if it.lower().endswith(store.MEDIA_EXT) and os.path.isfile(it):
                        added.append(self.store.add_image_file(eid, it))
                else:
                    name = self.store.free_image_name(eid, "pasted_" + time.strftime("%m%d%y_%H%M%S") + ".png")
                    path = self.store.image_path(eid, name)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    if it.save(path, "PNG"):
                        added.append(name)
            except OSError as ex:
                log(f"picture not added: {ex}")
        live = self.imgs.setdefault(eid, [])
        new = [n for n in dict.fromkeys(added) if n not in live]
        if not new:
            self.toast.say("That one is already on this note." if added else "Nothing could be added.", ms=2500)
            return
        live.extend(new)
        self.revisions_changed(eid)
        self.toast.say(f"Added {len(new)} file{'' if len(new) == 1 else 's'} to this note")
        self.check_images_size()

    def view_pictures(self, rev_n, i):
        """A click on a thumbnail: a picture opens enlarged, a video opens in the default video player."""
        names = self.picture_names(self.cur, rev_n)
        if not 0 <= i < len(names):
            return
        path = self.store.image_path(self.cur, names[i])
        if media.is_video(path):
            if os.path.isfile(path):
                self.start_path(path)
            else:
                self.toast.say("That video is missing from the images folder.", ms=3000)
            return
        stills = [self.store.image_path(self.cur, n) for n in names if not media.is_video(n)]
        self.viewer.open(stills, stills.index(path))

    def show_in_folder(self, path):
        if TEST:
            self.started.append(path)
        else:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])

    def copy_text(self, text):
        self.to_clipboard(text)

    def copy_picture(self, path):
        """Put a picture on the clipboard as a picture, and as a file too so it can also be pasted into
        a folder. A video is copied as a file."""
        if not path or not os.path.isfile(path):
            self.toast.say("That file is missing from the images folder.", ms=3000)
            return False
        self.stop_clip_queue()
        if TEST:
            self.clip_image = path  # test runs never touch the real clipboard
            self.clip_log.append(("picture", path))
            return True
        QApplication.clipboard().setMimeData(self.picture_mime(path))
        return True

    @staticmethod
    def picture_mime(path):
        """What goes on the clipboard for one file: the file itself, and for a picture its pixels too."""
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path)])
        if not media.is_video(path):
            img = QImage(path)
            if not img.isNull():
                mime.setImageData(img)
        return mime

    def picture_menu(self, rev_n, i, at):
        eid = self.cur
        names = self.picture_names(eid, rev_n)
        if not 0 <= i < len(names):
            return
        path = self.store.image_path(eid, names[i])
        video = media.is_video(path)
        m = make_menu(self)
        m.addAction("Play video" if video else "Enlarge", lambda: self.view_pictures(rev_n, i)).setToolTip(
            "Same as clicking it.")
        m.addAction("Copy video file" if video else "Copy image", lambda: self.copy_from_strip(path)).setToolTip(
            "Puts it on the clipboard, ready to paste.")
        m.addAction("Show in its folder", lambda: self.show_in_folder(path)).setToolTip(
            "Opens the images folder for this note in Explorer with this file selected.")
        m.addAction("Remove from note...", lambda: self.ask_remove_picture(rev_n, i)).setToolTip(
            "Takes it off this note. The file itself stays in the images folder.")
        show_menu(m, at)

    def copy_from_strip(self, path):
        if self.copy_picture(path):
            self.toast.say("Video file copied" if media.is_video(path) else "Image copied")

    def viewer_menu(self, at):
        path = self.viewer.current()
        m = make_menu(self)
        m.addAction("Copy image", self.viewer.copy_now).setToolTip("Puts this picture on the clipboard, ready to paste.")
        m.addAction("Show in its folder", lambda: self.show_in_folder(path)).setToolTip(
            "Opens the images folder for this note in Explorer with this file selected.")
        show_menu(m, at)

    def ask_remove_picture(self, rev_n, i):
        """The x on a thumbnail (or Remove in its menu): confirm first, and say where the file still lives."""
        eid = self.cur
        names = self.picture_names(eid, rev_n)
        if not 0 <= i < len(names):
            return
        name = names[i]
        kind = "video" if media.is_video(name) else "picture"
        self.notice.ask(
            f"Take this {kind} off the note?",
            "It only comes off the note. The file is not deleted: it still lives in the images folder, here:",
            self.store.image_path(eid, name),
            [("Remove from note", "strike", lambda: self.remove_picture(eid, rev_n, name),
              "Takes it off the note. The file stays where it is, and a toast offers Undo."),
             ("Cancel", "secondary", None, "Leave it on the note.")])

    def remove_picture(self, eid, rev_n, name):
        """Take a picture or video off the notes being typed (rev_n 0) or off a revision. Only its line in
        the notes file goes; the file stays in images/<entry name>/."""
        rev = self.find_rev(eid, rev_n) if rev_n else None
        names = self.imgs.setdefault(eid, []) if not rev_n else (rev or {}).get("images")
        if not names or name not in names:
            return
        i = names.index(name)
        names.pop(i)
        if rev is not None and not names:
            rev.pop("images", None)
        self.revisions_changed(eid)
        self.toast.say(f"Took {name} off the note", "Undo", lambda: self.put_picture(eid, rev_n, i, name), ms=7000)

    def put_picture(self, eid, rev_n, i, name):
        rev = self.find_rev(eid, rev_n) if rev_n else None
        if rev_n and rev is None:
            return
        names = self.imgs.setdefault(eid, []) if not rev_n else rev.setdefault("images", [])
        if name not in names:
            names.insert(min(i, len(names)), name)
        self.revisions_changed(eid)

    def check_images_size(self):
        """Pop up each time the images folder passes another 5 GB (5, 10, 15 and so on). Files are never
        deleted from it by the app, so this is the reminder to clear it out by hand."""
        total = self.store.images_bytes()
        level = int(total // ALERT_STEP)
        seen = int(self.store.state.get("images_alert", 0) or 0)
        if level == seen:
            return
        self.store.state["images_alert"] = level  # going down is remembered too, so it warns again later
        self.state_dirty = True
        self.save_timer.start()
        if level > seen:
            self.notice.ask(
                f"The images folder has passed {level * ALERT_STEP / 1024 ** 3:g} GB",
                f"It now holds {total / 1024 ** 3:.1f} GB of pictures and videos. Files stay in it even after "
                f"they are taken off a note, so it only grows until you clear it out yourself. This message "
                f"comes back at every further 5 GB.",
                store.IMAGES_DIR,
                [("Open images folder", "strike", lambda: self.start_path(store.IMAGES_DIR),
                  "Opens the images folder in Explorer."),
                 ("Close", "secondary", None, "Close this message.")])

    # ---- ideas
    def ideas_text(self, eid):
        if eid not in self.ideas_cache:
            self.ideas_cache[eid] = self.store.read_ideas(eid)
        return self.ideas_cache[eid]

    def on_ideas_changed(self):
        if self._loading or not self.cur:
            return
        self.ideas_cache[self.cur] = self.ideas.toPlainText()
        self.ideas_dirty.add(self.cur)
        self.save_timer.start()

    # ---- the token count
    def watch_tokens(self, rev_n):
        """Point the gold token count at the notes being typed (0) or at the revision clicked into."""
        if rev_n != self.tok_rev:
            self.tok_rev = rev_n
            self.refresh_tokens()

    def refresh_tokens(self):
        rev = self.find_rev(self.cur, self.tok_rev) if self.tok_rev else None
        if rev is not None:
            n = count_tokens(rev["text"])
            self.tokens.setText(f"Revision {rev['n']}:  {n:,} token{'' if n == 1 else 's'}")
        elif self.cur in self.docs:
            n = count_tokens(self.docs[self.cur].toPlainText())
            self.tokens.setText(f"{n:,} token{'' if n == 1 else 's'}")
        else:
            self.tokens.setText("")

    # ---- sizes that follow the window
    def after_resize(self):
        self.apply_compact()
        self.fit_boxes()
        QTimer.singleShot(0, self.place_grip)

    def drag_ideas(self, px):
        """The Ideas box's grip: a height (the notes keep at least about 110 px), or None to grow with its text."""
        if px is not None:
            room = self.ideas.height() + max(0, self.notes_box.height() - 110)
            line = self.ideas.fontMetrics().lineSpacing()
            px = max(line + 8, min(int(px), room))
        self.ideas.manual = px
        self.ideas.fit()
        self.store.state["ideas_h"] = px
        self.state_dirty = True
        self.save_timer.start()

    def fit_boxes(self):
        """The TL;DR and Ideas boxes grow with their text, but only until the notes would be squeezed:
        past that each box scrolls instead. The taller the window, the more they may grow."""
        tall = self.main.height()
        keep = max(100, min(220, int(tall * 0.3)))  # what the notes always keep
        cap = max(69, (tall - 210 - keep) // 2)
        self.ideas.room = max(0, tall - 330)  # a dragged Ideas box still leaves the notes their room
        for box in (self.tldr, self.ideas):
            box.set_cap(cap)

    def apply_compact(self):
        """Fit the layout to the window. A narrow window (a quarter or a third of a wide screen) leaves
        out the keyboard hints, the line counts and the Change linked folder button (still in the row's
        right-click menu), and lets the chips under the title wrap. A very short window (a quarter of the
        screen's height) leaves out the TL;DR, the chips under the title and the brand row."""
        whole = self.isMaximized() or self.isFullScreen()
        single = self.root.width() < 380 or (bool(self.store.state.get("one_pane")) and not whole)
        if single != self.single:
            self.single = single
            side = self.hsplit.widget(0)
            if single:  # too narrow for both: one pane at a time, the note first
                self.split_was = self.hsplit.sizes()
                self.show_pane("note")
            else:
                side.setMaximumWidth(460)
                side.show()
                self.main.show()
                if self.split_was:
                    self.hsplit.setSizes(self.split_was)
            self.list_btn.setVisible(single)
            self.note_btn.setVisible(single and not self.main.isVisible())
            self.refresh_side_row()
        narrow, short = self.root.width() < 820, self.root.height() < 520
        tiny, slim = single or self.main.width() < 440, self.root.width() < 560
        if (narrow, short, tiny, slim) == self.compact:
            return
        self.compact = (narrow, short, tiny, slim)
        for w in self.wide_only:
            w.setVisible(not narrow)
        for w in self.tall_only + [self.ver_lbl]:
            w.setVisible(not short)
        self.tokens.setVisible(not tiny)
        self.strike_kbd.setVisible(not tiny)
        self.page_lay.setContentsMargins(*((10, 10, 10, 8) if tiny else (22, 14, 22, 10)))
        self.refresh_theme_btn()
        self.refresh_header()

    def show_pane(self, which):
        """One-pane mode (a very narrow window): show the list or the note."""
        side = self.hsplit.widget(0)
        if which == "list":
            side.setMaximumWidth(16777215)
            side.show()
            self.main.hide()
            if self.cur:
                self.list.scrollToItem(self.item_for(self.cur))
        else:
            side.hide()
            self.main.show()
        self.note_btn.setVisible(self.single and which == "list")
        self.refresh_side_row()

    def refresh_side_row(self):
        """The row at the top of the list: Back, then Pin and Hide notes pane at the right while one pane
        shows at a time; Hide notes pane alone at the left otherwise."""
        one = self.single
        self.prow_gap.setVisible(one)
        self.side_pin.setVisible(one and self.can_pin())

    def set_one_pane(self, on):
        """Hide notes pane: one pane at a time (the list or the note) whenever the window is not full
        screen. A very narrow window always works this way."""
        self.store.state["one_pane"] = bool(on)
        self.state_dirty = True
        self.save_timer.start()
        set_lit(self.pane_btn, bool(on))
        self.apply_compact()
        if self.single and on:
            self.show_pane("list")  # turned on from the list: stay on the list, with Swap right under

    def fit_sidebar(self):
        """A narrow list keeps what matters: the extras step aside as it gets narrower."""
        w = self.side.width()
        self.foot_kbd.setVisible(w >= 240)
        self.where_btn.setVisible(w >= 215)
        self.ver_text.setVisible(w >= 200)
        self.groups_lbl.setVisible(w >= 205)

    # ---- placing the window
    def place_of(self):
        p = self.store.state.get("place") or {}
        return (p.get("kind"), p.get("side")) if p.get("kind") else None

    def frame_now(self):
        if TEST:
            g = self.geometry()
            return g.x(), g.y(), g.width(), g.height()
        return self.win32.rect(int(self.winId()))

    def place_menu(self):
        """The Place button: a grid of little screens (half, third, quarter, corner, against each side),
        then full screen, the other screen, and letting the window move freely again."""
        m = make_menu(self)
        here = self.place_of()
        grid = PlaceGrid(here)
        grid.picked.connect(lambda k, s: (m.close(), self.place_window(k, s)))
        wa = QWidgetAction(m)
        wa.setDefaultWidget(grid)
        m.addAction(wa)
        m.addSeparator()
        full = m.addAction("Full screen", lambda: self.place_window("full", ""))
        full.setCheckable(True)
        full.setChecked(bool(here and here[0] == "full"))
        full.setToolTip("Fills the screen, the same as the maximize button, and comes back that way after a restart.")
        if len(QApplication.screens()) > 1:
            m.addAction("Move to the next screen", self.place_next_screen).setToolTip(
                "Puts the window on the next monitor, in the same place on it.")
        free = m.addAction("Let it move freely", self.release_place)
        free.setEnabled(bool(here))
        free.setToolTip("Stops holding the window in place. Dragging the window does the same.")
        m.ensurePolished()
        show_menu(m, self.place_btn.mapToGlobal(QPoint(0, -m.sizeHint().height() - 4)))

    def place_window(self, kind, side):
        """Put the window on part of the screen and keep it there (it comes back there after a restart
        and when the screen changes) until it is dragged somewhere else. A strip a fifth of the screen wide
        or narrower turns on Hide notes pane: the list and the note take turns."""
        if kind in ("fifth", "sixth", "seventh", "eighth") and side in ("left", "right") \
                and not self.store.state.get("one_pane"):
            self.set_one_pane(True)
        was = self.pinned_now()
        self.unpin(keep=True)
        self.store.state["place"] = {"kind": kind, "side": side}
        self.state_dirty = True
        self.save_timer.start()
        if was and self.can_pin():  # a pinned window put on another strip stays pinned there
            self.repin()
        else:
            if not self.can_pin():
                self.store.state["pinned"] = False
            self.apply_place()
        self.refresh_place_btn()

    def apply_place(self, step=0):
        here = self.place_of()
        if not here or not self.isVisible():
            return
        self.placing = True
        QTimer.singleShot(700, lambda: setattr(self, "placing", False))
        if here[0] == "full":
            if not self.isMaximized():
                self.showMaximized()
            return
        frac = PLACES.get(here)
        if not frac:
            return
        if self.isMaximized() or self.isMinimized():
            self.showNormal()
        if TEST:  # off screen: the same arithmetic on Qt's own idea of the screen
            screens = QApplication.screens()
            on = QApplication.screenAt(self.geometry().center()) or self.screen()
            i = screens.index(on) if on in screens else 0
            g = screens[(i + step) % len(screens)].availableGeometry()
            x, y, w, h = place_rect((g.left(), g.top(), g.left() + g.width(), g.top() + g.height()), frac)
            self.setGeometry(QRect(x, y, w, h))
            if self.width() > w and "right" in here[1]:
                self.move(x + w - self.width(), self.y())
            if self.height() > h and "bottom" in here[1]:
                self.move(self.x(), y + h - self.height())
        else:
            hwnd = int(self.winId())
            x, y, w, h = place_rect(self.win32.work_area(hwnd, step), frac)
            self.win32.move(hwnd, x, y, w, h, here[1])
        self.place_seen = self.frame_now()

    def reapply_place(self):
        if self.place_of() and self.isVisible() and not self.isMinimized():
            if self.pinned_now():
                self.repin()
            else:
                self.apply_place()

    def place_next_screen(self):
        if self.place_of() and self.place_of()[0] != "full":
            self.apply_place(step=1)
        else:
            self.showNormal()
            self.place_window("half", "left")
            self.apply_place(step=1)
        QTimer.singleShot(400, self.reapply_place)  # once more, in case that monitor has another scaling

    def release_place(self, quiet=False):
        if not self.store.state.get("place"):
            return
        self.unpin()
        self.store.state["place"] = None
        self.place_seen = None
        self.state_dirty = True
        self.save_timer.start()
        self.refresh_place_btn()
        if not quiet:
            self.toast.say("The window moves freely again")

    def check_place(self):
        """The window moved or changed size. If that was not the app placing it, it is free again."""
        here = self.place_of()
        if not here or self.placing or not self.isVisible() or self.isMinimized():
            return
        if here[0] == "full":
            if not self.isMaximized():
                self.release_place(quiet=True)
            return
        if self.isMaximized():
            return
        if self.place_seen is not None and self.frame_now() != self.place_seen:
            self.release_place(quiet=True)

    # ---- Pin: keep other windows out of the strip the window is docked to
    def can_pin(self):
        """Only a window docked against a side (a half, third, quarter, fifth or sixth) can be pinned."""
        here = self.place_of()
        return bool(here and here[0] in ("half", "third", "quarter", "fifth", "sixth", "seventh", "eighth"))

    def pinned_now(self):
        return bool(self.store.state.get("pinned")) and self.can_pin()

    def toggle_pin(self):
        if self.pinned_now():
            self.unpin()
            self.store.state["pinned"] = False
            self.toast.say("Unpinned: other windows can use that space again")
        elif self.can_pin():
            self.store.state["pinned"] = True
            self.repin()
            self.toast.say("Pinned: other windows now keep out of this strip")
        self.state_dirty = True
        self.save_timer.start()
        self.refresh_place_btn()

    def repin(self):
        """Reserve the strip and put the window on it."""
        here = self.place_of()
        if not self.can_pin() or not self.isVisible():
            return
        self.placing = True
        QTimer.singleShot(900, lambda: setattr(self, "placing", False))
        if self.isMaximized() or self.isMinimized():
            self.showNormal()
        if TEST:
            self.apply_place()
            self.pin_rect = self.frame_now()
            return
        hwnd = int(self.winId())
        if self.pin_rect is None:  # the strip is measured on the screen as it is without this app bar
            x, y, w, h = place_rect(self.win32.work_area(hwnd), PLACES[here])
            self.own_move(hwnd, x, y, w, h, here[1])  # on the strip first, and held there while it is reserved
            self.hold_place(hwnd)
            self.pin_rect = self.win32.appbar_on(hwnd, here[1], (x, y, x + w, y + h))
        left, top, right, bottom = self.pin_rect
        aw, ah = self.own_move(hwnd, left, top, right - left, bottom - top, here[1])
        side = here[1]
        if (side in ("left", "right") and aw > right - left) or (side in ("top", "bottom") and ah > bottom - top):
            # the window cannot be as small as the strip: reserve the room it really takes, so nothing overlaps
            if side == "left":
                right = left + aw
            elif side == "right":
                left = right - aw
            elif side == "top":
                bottom = top + ah
            else:
                top = bottom - ah
            self.pin_rect = self.win32.appbar_on(hwnd, side, (left, top, right, bottom))
            left, top, right, bottom = self.pin_rect
            self.own_move(hwnd, left, top, right - left, bottom - top, side)
        self.hold_place(hwnd)
        self.place_seen = self.frame_now()

    def own_move(self, hwnd, x, y, w, h, side):
        """A move the app makes itself, which the hold below lets through."""
        self.moving_self = True
        try:
            return self.win32.move(hwnd, x, y, w, h, side)
        finally:
            self.moving_self = False

    def hold_place(self, hwnd, ms=1500):
        """Keep the window exactly where it is for a moment. Reserving the strip makes Windows clear the
        space of every window in it, this one included; held, it stays on its strip instead of being pushed
        out and moved back."""
        left, top, right, bottom = self.win32.rect(hwnd)
        self.hold = (left, top, right - left, bottom - top)
        self.hold_timer.start(ms)

    def nativeEvent(self, kind, message):
        if self.hold is None:  # nearly always: nothing to do
            return False, 0
        if not self.moving_self and bytes(kind) == b"windows_generic_MSG":
            msg = _MSG.from_address(int(message))
            if msg.message == 0x0046 and msg.lParam:  # WM_WINDOWPOSCHANGING from anyone but the app itself
                wp = _WINDOWPOS.from_address(msg.lParam)
                if not wp.flags & 0x2:  # SWP_NOMOVE not set: it would move
                    wp.x, wp.y = self.hold[0], self.hold[1]
                if not wp.flags & 0x1:  # SWP_NOSIZE not set: it would resize
                    wp.cx, wp.cy = self.hold[2], self.hold[3]
        return False, 0

    def unpin(self, keep=False):
        """Give the strip back. `keep` leaves the choice saved, so it is pinned again when it comes back."""
        if self.pin_rect is not None and not TEST:
            self.win32.appbar_off(int(self.winId()))
        self.pin_rect = None
        if not keep:
            self.store.state["pinned"] = False

    def refresh_place_btn(self):
        here = self.place_of()
        pinned = self.pinned_now()
        self.pin_btn.setVisible(self.can_pin())
        set_lit(self.pin_btn, pinned)
        set_lit(self.side_pin, pinned)
        self.refresh_side_row()
        if pinned:
            tip = ("Pinned: other windows keep out of this strip of the screen and maximize beside it, like the "
                   "taskbar. Click to unpin.")
        else:
            tip = ("Pin the window to this strip: other windows then keep out of it and maximize beside it, like "
                   "the taskbar. Works when it is docked against a side of the screen, not a corner.")
        self.pin_btn.setToolTip(tip)
        self.side_pin.setToolTip(tip)
        self.place_btn.setIcon(place_icon())
        self.place_btn.setProperty("sel", bool(here))
        self.place_btn.style().unpolish(self.place_btn)
        self.place_btn.style().polish(self.place_btn)
        if here:
            self.place_btn.setToolTip(f"The window is held on {place_words(*here)}. Click to put it somewhere "
                                      f"else; drag the window to let it go.")
        else:
            self.place_btn.setToolTip("Put the window on half, a third or a quarter of the screen, against "
                                      "any side, or in a corner, like Windows+arrow keys. It stays there, "
                                      "even after a restart, until you drag it away.")

    def watch_screen(self, s, quiet=False):
        s.availableGeometryChanged.connect(lambda _r: QTimer.singleShot(400, self.reapply_place))
        if not quiet:
            QTimer.singleShot(400, self.reapply_place)

    def moveEvent(self, ev):
        super().moveEvent(ev)
        self.place_timer.start(700)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.place_timer.start(700)

    def changeEvent(self, ev):
        super().changeEvent(ev)
        if ev.type() == QEvent.WindowStateChange and getattr(self, "root", None) is not None:
            QTimer.singleShot(0, self.apply_compact)

    def showEvent(self, ev):
        super().showEvent(ev)
        if self.place_of():
            QTimer.singleShot(0, self.reapply_place)

    def hideEvent(self, ev):
        super().hideEvent(ev)
        if self.pin_rect is not None and not self.isMinimized():  # hidden in the tray: give the strip back for now
            self.unpin(keep=True)

    # ---- themes
    def theme_menu(self):
        """The Theme button: the 14 themes. Pointing at one shows it; a click keeps it; closing the menu
        without a click puts the old one back."""
        m = make_menu(self)
        saved = T.ID
        self.theme_chosen = False
        for t in T.THEMES:
            a = m.addAction(theme_swatch(t["id"]), t["name"], lambda i=t["id"]: self.pick_theme(i))
            a.setCheckable(True)
            a.setChecked(t["id"] == saved)
            a.setData(t["id"])
            a.setToolTip(f"{t['name']}, a {t['mode']} theme. Point at it to see it, click to keep it.")
        m.hovered.connect(lambda a: self.preview_theme(a.data()))
        m.aboutToHide.connect(lambda: QTimer.singleShot(0, lambda: self.end_preview(saved)))
        m.ensurePolished()
        show_menu(m, self.theme_btn.mapToGlobal(QPoint(0, -m.sizeHint().height() - 4)))

    def preview_theme(self, theme_id):
        if theme_id and nimble_themes.valid(theme_id):
            self.preview_id = theme_id
            self.theme_timer.start(140)

    def show_preview(self):
        if self.preview_id and self.preview_id != T.ID:
            self.apply_theme(self.preview_id, save=False)

    def end_preview(self, saved):
        self.theme_timer.stop()
        self.preview_id = None
        if not self.theme_chosen and T.ID != saved:
            self.apply_theme(saved, save=False)

    def pick_theme(self, theme_id):
        self.theme_chosen = True
        self.set_theme(theme_id)

    def font_id(self):
        """The font picked for the app (older saves kept the app and the notes apart: the app's one wins)."""
        st = self.store.state
        return st.get("font") or st.get("ui_font") or "segoe-ui"

    def set_app_font(self, font_id):
        """One font for the whole app: the list, the buttons, the notes and the Ideas box."""
        self.store.state["font"] = font_id
        self.store.state.pop("ui_font", None)
        self.store.state.pop("notes_font", None)
        self.set_font("notes_font", font_id, quiet=True)
        self.set_font("ui_font", font_id, quiet=True)
        self.store.state.pop("ui_font", None)
        self.store.state.pop("notes_font", None)
        label = next((c["name"] for c in load_fonts() if c["id"] == font_id), font_id)
        self.toast.say(f"Font: {label}", ms=1800)

    def set_font(self, key, font_id, quiet=False):
        """Use a font for the app ("ui_font") or for the notes ("notes_font") at once, and keep it."""
        family = font_family(font_id)
        self.store.state[key] = font_id
        self.state_dirty = True
        self.save_timer.start()
        if key == "notes_font":
            T.NOTES_FONT = family
            self.apply_notes_font()
        else:
            old, T.UI_FONT = T.UI_FONT, family
            app = QApplication.instance()
            app.setFont(ui_font(13))
            skip = {self.notes, self.ideas}
            for w in app.allWidgets():  # every widget in the old app font takes the new one, its size kept
                if w in skip or isinstance(w, FontList):
                    continue
                f = w.font()
                if f.family() == old:
                    f.setFamily(family)
                    w.setFont(f)
            d = self.list.itemDelegate()
            for name in ("f_name", "f_name_sel", "f_tag"):
                if hasattr(d, name):
                    getattr(d, name).setFamily(family)
            self.list.doItemsLayout()
        for w in QApplication.instance().allWidgets():
            w.update()
        if not quiet:
            label = next((c["name"] for c in load_fonts() if c["id"] == font_id), family)
            self.toast.say(f"{'Notes' if key == 'notes_font' else 'App'} font: {label}", ms=1800)

    def set_theme(self, theme_id):
        """Keep a theme: it is on at once and comes back after a restart."""
        self.theme_timer.stop()
        self.preview_id = None
        self.apply_theme(theme_id, save=True)

    def apply_theme(self, theme_id, save=True):
        """Recolor the whole app: tokens, palette, stylesheet, title bar, glows, icons, painted widgets."""
        tid = T.apply(theme_id)
        app = QApplication.instance()
        apply_palette(app)
        app.setStyleSheet(T.QSS)
        dark_titlebar(self)
        self.paint_glows()
        self.refresh_header()
        self.refresh_theme_btn()
        self.refresh_place_btn()
        for a_id, a in (getattr(self.tray, "theme_actions", None) or {}).items():
            a.setChecked(a_id == tid)
        for w in app.allWidgets():
            w.update()
        if save:  # a theme kept (not one being pointed at): the taskbar and tray icons take its color
            icon = app_icon()
            app.setWindowIcon(icon)
            self.setWindowIcon(icon)
            if self.tray is not None:
                self.tray.setIcon(icon)
            self.store.state["theme"] = tid
            self.state_dirty = True
            self.save_timer.start()
        return tid

    def paint_glows(self):
        self.strike_glow.setColor(acc(70))

    def refresh_theme_btn(self):
        self.theme_btn.setIcon(theme_swatch(T.ID))
        self.theme_btn.setText("" if (self.compact and self.compact[3]) else T.NAME)
        self.theme_btn.setToolTip(f"Theme: {T.NAME}. Click to pick one of the {len(T.THEMES)} Nimble themes: "
                                  f"pointing at a name shows it, a click keeps it. Only the colors change.")

    # ---- the corner grip
    def place_grip(self):
        """Stretch the invisible resize grip from the bottom right corner of the notes box to the bottom
        right corner of the window, so the whole of that corner drags the window larger or smaller."""
        root = self.root
        if self.stack.currentIndex() == 0 and self.notes_box.isVisible():
            corner = self.notes_box.mapTo(root, QPoint(self.notes_box.width(), self.notes_box.height()))
        else:
            corner = QPoint(root.width() - 26, root.height() - 38)
        x = max(0, min(corner.x(), root.width() - 26))
        y = max(0, min(corner.y(), root.height() - 26))
        self.grip.setGeometry(x, y, root.width() - x, root.height() - y)
        self.grip.raise_()

    # ---- saving
    def on_notes_changed(self):
        if self._loading or not self.cur or self.cur not in self.docs:  # a note just dropped has no text any more
            return
        self.dirty.add(self.cur)
        self.save_timer.start()
        self.update_strike_btn()
        self.refresh_tokens()
        if self.docs[self.cur].isEmpty() != (self.open_n.get(self.cur, 0) == 0):
            self.refresh_open(self.cur)  # the row lights up as soon as there is something open, not a second later

    def on_tldr_changed(self):
        e = self.store.get(self.cur)
        if self._loading or not e:
            return
        e["tldr"] = self.tldr.toPlainText()
        self.touch_meta()

    def touch_meta(self):
        self.meta_dirty = True
        self.save_timer.start()

    def flush(self):
        """Write everything that changed. Called by the typing timer and before anything that reads the disk."""
        self.save_timer.stop()
        wrote = False
        try:
            for eid in list(self.dirty):
                if eid in self.docs:
                    self.store.write_notes(eid, store.join_notes(self.docs[eid].toPlainText(),
                                                                 self.revs.get(eid, []), self.imgs.get(eid, [])))
                    self.mtimes[eid] = mtime(self.store.notes_path(eid))
                    wrote = True
                    self.refresh_open(eid)
                self.dirty.discard(eid)
            for eid in list(self.ideas_dirty):
                self.store.write_ideas(eid, self.ideas_cache.get(eid, ""))
                self.ideas_dirty.discard(eid)
                wrote = True
            if self.meta_dirty:
                self.store.save_entries()
                self.apps_mtime = mtime(store.APPS_PATH)
                self.meta_dirty = False
                wrote = True
            if self.state_dirty:
                self.store.save_state()
                self.state_dirty = False
        except OSError as ex:
            log(f"save failed: {ex}")
            self.saved.setText(f"Could not save: {ex}")
            self.saved.show()
            return
        if wrote:
            self.saved.hide()
            self.refresh_counts()

    def save_now(self):
        self.flush()
        self.toast.say("Saved. It also saves by itself as you type.")

    def check_disk(self):
        """On coming back to the window: pick up edits made to the files by something else."""
        if not self.meta_dirty and mtime(store.APPS_PATH) != self.apps_mtime:
            self.store.load_entries()
            self.apps_mtime = mtime(store.APPS_PATH)
            self.fill_list(self.cur)
        elif self.cur:
            self.sync_doc(self.cur)
        self.note_cache = {}  # notes of entries that are not open here may have been edited outside too
        self.ideas_cache = {k: v for k, v in self.ideas_cache.items() if k in self.ideas_dirty or k == self.cur}
        self.refresh_open()

    # ---- the TL;DR
    def show_tldr(self, text):
        self._loading = True
        self.tldr.setPlainText(text)
        self._loading = False

    def set_tldr(self, eid, text):
        e = self.store.get(eid)
        if not e:
            return
        e["tldr"] = text
        self.touch_meta()
        if self.cur == eid:
            self.show_tldr(text)

    # ---- header actions
    def start_rename(self):
        e = self.store.get(self.cur)
        if not e or self.title_edit.isVisible():
            return
        self.title.hide()
        self.title_edit.setText(e["name"])
        self.title_edit.show()
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def commit_rename(self):
        if not self.title_edit.isVisible():
            return
        e = self.store.get(self.cur)
        name = self.title_edit.text().strip()
        self.title_edit.hide()
        self.title.show()
        if e and name and name != e["name"]:
            self.flush()
            self.store.rename(e, name)  # the notes file is renamed with it
            self.apps_mtime = mtime(store.APPS_PATH)
            if e["id"] in self.docs:
                self.mtimes[e["id"]] = mtime(self.store.notes_path(e["id"]))
            self.refresh_header()
            self.refresh_history()  # the entry's folder was renamed with it, so its pictures have new paths
            self.refresh_strip()
            if self.sort_of(e["section"])[0] == "name":
                QTimer.singleShot(0, lambda: self.fill_list(self.cur))
        self.notes.setFocus()
        QTimer.singleShot(0, self.notes.setFocus)  # and again once the list has been redrawn

    def cancel_rename(self):
        self.title_edit.blockSignals(True)
        self.title_edit.hide()
        self.title_edit.blockSignals(False)
        self.title.show()
        self.notes.setFocus()

    def set_field(self, field, value):
        e = self.store.get(self.cur)
        if not e or e[field] == value:
            return
        e[field] = value
        self.touch_meta()
        self.refresh_header()
        if self.sort_of(e["section"])[0] == field:  # the list is ordered by what just changed
            self.fill_list(self.cur)

    def move_to(self, eid, section):
        e = self.store.get(eid)
        if not e:
            return
        self.flush()
        self.remember_move()
        e["section"] = section
        self.store.save_entries()
        self.apps_mtime = mtime(store.APPS_PATH)
        self.fill_list(eid)
        self.list.scrollToItem(self.item_for(eid))

    def start_path(self, path):
        """Open a folder or run a launcher the way Explorer would."""
        if TEST:
            self.started.append(path)
            return True
        try:
            os.startfile(path, cwd=path if os.path.isdir(path) else os.path.dirname(path))
            return True
        except OSError as ex:
            log(f"could not start {os.path.basename(path)}: {ex}")
            self.toast.say(f"Could not open it: {ex.strerror or ex}", ms=4000)
            return False

    def open_folder(self):
        e = self.store.get(self.cur)
        if not e:
            return
        folder = self.store.folder(e)
        if folder and os.path.isdir(folder):
            self.start_path(folder)
        else:
            self.pick_folder()

    @staticmethod
    def short_path(path, folder):
        """The path as seen from the entry's folder when it is inside it, else the whole path."""
        if folder and os.path.normcase(path).startswith(os.path.normcase(folder) + os.sep):
            return os.path.relpath(path, folder)
        return store.contract_dir(path)

    def pick_folder(self):
        e = self.store.get(self.cur)
        if not e:
            return
        here = self.store.folder(e)
        start = here if here and os.path.isdir(here) else store.expand_dir(self.store.state.get("last_dir", ""))
        picked = QFileDialog.getExistingDirectory(self, f"Folder for {e['name']}", start or "")
        if not picked or (here and os.path.normcase(os.path.normpath(picked)) == os.path.normcase(here)):
            return
        before = (e["path"], e["launch"])
        self.flush()
        self.store.set_folder(e, picked)
        self.apps_mtime = mtime(store.APPS_PATH)
        self.store.state["last_dir"] = store.contract_dir(os.path.dirname(os.path.normpath(picked)))
        self.state_dirty = True
        self.save_timer.start()
        self.refresh_header()
        self.toast.say(f"Linked to {os.path.basename(os.path.normpath(picked))}", "Undo",
                       lambda: self.restore_links(e["id"], before), ms=7000)

    def restore_links(self, eid, links):
        """Undo for a folder or launch file change."""
        e = self.store.get(eid)
        if not e:
            return
        e["path"], e["launch"] = links
        self.store.save_entries()
        self.apps_mtime = mtime(store.APPS_PATH)
        if self.cur == eid:
            self.refresh_header()

    def launch(self):
        """Run the entry's launch file, or ask for one when none is known."""
        e = self.store.get(self.cur)
        if not e:
            return
        bat = self.store.launcher(e)
        if not bat:
            self.pick_launcher()
        elif self.start_path(bat):
            self.toast.say(f"Started {os.path.basename(bat)}")

    def pick_launcher(self):
        e = self.store.get(self.cur)
        if not e:
            return
        folder = self.store.folder(e)
        now = self.store.launcher(e)
        if now:
            start = os.path.dirname(now)
        elif folder and os.path.isdir(folder):
            start = folder
        else:
            start = store.expand_dir(self.store.state.get("last_dir", ""))
        picked, _ = QFileDialog.getOpenFileName(
            self, f"Launcher for {e['name']}", start or "",
            "Launchers (*.bat *.cmd *.exe *.lnk *.ps1 *.py *.pyw);;All files (*.*)")
        if not picked:
            return
        picked = os.path.normpath(picked)
        before = (e["path"], e["launch"])
        self.flush()
        if not e["path"]:
            self.store.set_folder(e, os.path.dirname(picked))  # nothing was linked yet: use the bat's own folder
        self.store.set_launcher(e, picked)
        self.apps_mtime = mtime(store.APPS_PATH)
        self.refresh_header()
        self.toast.say(f"Launch will run {os.path.basename(picked)}", "Undo",
                       lambda: self.restore_links(e["id"], before), ms=7000)

    def auto_launcher(self):
        e = self.store.get(self.cur)
        if not e or not e["launch"]:
            return
        before = (e["path"], e["launch"])
        self.flush()
        self.store.set_launcher(e, "")
        self.apps_mtime = mtime(store.APPS_PATH)
        self.refresh_header()
        found = self.store.launcher(e)
        self.toast.say(f"Found {os.path.basename(found)}" if found else "No launcher found in the folder",
                       "Undo", lambda: self.restore_links(e["id"], before), ms=7000)

    def launch_menu(self, pos):
        e = self.store.get(self.cur)
        if not e:
            return
        m = make_menu(self)
        bat = self.store.launcher(e)
        info = m.addAction(f"Runs: {self.short_path(bat, self.store.folder(e))}" if bat else "No launcher found")
        info.setEnabled(False)
        m.addAction("Change launcher..." if bat else "Link launcher...", self.pick_launcher).setToolTip(
            "Point this button at the .bat, .exe or other file that launches the app. Opens a normal "
            "Explorer file picker.")
        if e["launch"]:
            m.addAction("Find it automatically again", self.auto_launcher).setToolTip(
                "Forgets the file you linked and goes back to looking in the folder.")
        show_menu(m, self.launch_btn.mapToGlobal(QPoint(0, self.launch_btn.height() + 4)))

    # ---- add / remove
    def new_entry(self, section=None, first=False):
        self.flush()
        self.drop_fresh(force=True)  # an earlier new note that was never written in goes first
        if section is None and self.focus_sec and self.store.section(self.focus_sec):
            section, first = self.focus_sec, True  # a category was picked last: the note goes at its top
            if section in self.folded():
                self.toggle_fold(section)
        self.focus_sec = None
        cur = self.store.get(self.cur)
        sec = section or (cur["section"] if cur else self.store.section_keys()[0])
        after = self.cur if (cur and cur["section"] == sec and not first) else None
        e = self.store.add("New note", sec, after, first=first or not after)
        self.fresh_id = e["id"]
        if self.group_active():  # made while the list shows one group: it joins it, or it would vanish at once
            self.view_group()["ids"].append(e["id"])
            self.state_dirty = True
        self.apps_mtime = mtime(store.APPS_PATH)
        self.search.clear()
        self.fill_list(e["id"])
        self.reveal(e["id"])
        self.list.scrollToItem(self.item_for(e["id"]))
        if self.single:
            self.show_pane("note")
        self.start_rename()

    def drop_fresh(self, force=False):
        """Forget the last new note made, if it was never named or written in."""
        eid = self.fresh_id
        if not eid or (eid == self.cur and not force):
            return
        self.fresh_id = None
        e = self.store.get(eid)
        if not e:
            return
        if self.cur == eid and self.title_edit.isVisible():
            self.cancel_rename()
        blank = (e["name"] == "New note" and not e["tldr"].strip() and not self.ideas_text(eid).strip()
                 and not self.note_text(eid).strip() and not self.imgs.get(eid))
        if not blank:
            return
        doc = self.docs.pop(eid, None)
        if doc is not None:
            if self.notes.document() is doc:
                self.notes.setDocument(QTextDocument(self.notes))
            doc.deleteLater()
        for cache in (self.revs, self.imgs, self.note_cache, self.ideas_cache, self.open_n):
            cache.pop(eid, None)
        self.dirty.discard(eid)
        self.store.drop(eid)
        self.apps_mtime = mtime(store.APPS_PATH)
        self.fill_list(self.cur if self.cur != eid else None)

    def fork_entry(self, eid):
        """Copy a note right below it, named with _v2, _v3 and so on: its notes, ideas, TL;DR,
        folder, launcher, groups and pictures."""
        src = self.store.get(eid)
        if not src:
            return
        self.flush()
        m = re.match(r"^(.*)_v(\d+)$", src["name"])
        base, n = (m.group(1), int(m.group(2)) + 1) if m else (src["name"], 2)
        taken = {e["name"].lower() for e in self.store.entries}
        while f"{base}_v{n}".lower() in taken:
            n += 1
        e = self.store.add(f"{base}_v{n}", src["section"], eid)
        for k in ("path", "launch", "tldr"):
            e[k] = src[k]
        self.store.save_entries()
        text = self.store.read_notes(eid)
        if text:
            self.store.write_notes(e["id"], text)
        ideas = self.ideas_text(eid)
        if ideas.strip():
            self.store.write_ideas(e["id"], ideas)
        old_media, new_media = self.store.media_dir(src), self.store.media_dir(e)
        if os.path.isdir(old_media) and not os.path.exists(new_media):
            try:
                shutil.copytree(old_media, new_media)
            except OSError as ex:
                log(f"fork: pictures not copied: {ex}")
        for g in self.groups():
            if eid in g["ids"]:
                g["ids"].insert(g["ids"].index(eid) + 1, e["id"])
        self.state_dirty = True
        self.apps_mtime = mtime(store.APPS_PATH)
        self.fill_list(e["id"])
        self.refresh_groups()
        self.list.scrollToItem(self.item_for(e["id"]))
        self.toast.say(f"Forked {src['name']} as {e['name']}")

    def remove_current(self):
        if self.cur:
            self.remove_entry(self.cur)

    def remove_entry(self, eid):
        e = self.store.get(eid)
        if not e:
            return
        self.flush()
        ids = [o["id"] for o in self.store.entries]
        i = ids.index(eid)
        neighbor = ids[i + 1] if i + 1 < len(ids) else (ids[i - 1] if i else None)
        name = e["name"]
        self.store.remove(eid)
        self.apps_mtime = mtime(store.APPS_PATH)
        self.fill_list(neighbor if self.cur == eid else self.cur)
        doc = self.docs.pop(eid, None)
        if doc is not None:
            if self.notes.document() is doc:
                self.notes.setDocument(QTextDocument(self.notes))
            doc.deleteLater()
        self.note_cache.pop(eid, None)
        self.revs.pop(eid, None)
        self.open_n.pop(eid, None)
        self.imgs.pop(eid, None)
        self.ideas_cache.pop(eid, None)
        self.ideas_dirty.discard(eid)
        self.toast.say(f"Removed {name}", "Undo", lambda: self.restore_entry(eid), ms=7000)

    def restore_entry(self, eid):
        self.flush()
        e = self.store.restore(eid)
        if e:
            self.apps_mtime = mtime(store.APPS_PATH)
            self.fill_list(eid)
            self.list.scrollToItem(self.item_for(eid))
            self.toast.say(f"Restored {e['name']}")

    # ---- search, history, window
    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def clear_search(self):
        self.search.clear()
        self.notes.setFocus()

    def nav(self, step):
        """Mouse back / forward buttons walk through the entries you visited."""
        j = self.hist_i + step
        while 0 <= j < len(self.hist) and not self.store.get(self.hist[j]):
            j += step
        if 0 <= j < len(self.hist):
            self.hist_i = j
            self.select(self.hist[j], push=False)

    def eventFilter(self, obj, ev):
        kind = ev.type()
        if kind == QEvent.MouseButtonPress and ev.button() in (Qt.BackButton, Qt.ForwardButton):
            if self.single:  # one pane at a time: back shows the list, forward the note; pressed again, they swap
                on_list = not self.main.isVisible()
                want = "list" if ev.button() == Qt.BackButton else "note"
                if (want == "list") == on_list:
                    want = "note" if on_list else "list"
                self.show_pane(want)
                if want == "note" and self.notes is not None:
                    self.notes.setFocus()
            else:
                self.nav(-1 if ev.button() == Qt.BackButton else 1)
            return True
        if obj is self.notes and kind in (QEvent.FocusIn, QEvent.FocusOut):
            self.set_notes_focus(kind == QEvent.FocusIn)
            if kind == QEvent.FocusIn:
                self.watch_tokens(0)
        elif kind == QEvent.Resize and obj is getattr(self, "root", None):
            QTimer.singleShot(0, self.after_resize)
        elif kind == QEvent.Resize and obj is getattr(self, "side", None):
            QTimer.singleShot(0, self.fit_sidebar)
        elif obj is self.notes_content and kind == QEvent.MouseButtonPress and self.notes is not None:
            self.notes.setFocus()  # a click in the empty part of the notes pane puts you back in the text
        return False

    def keyPressEvent(self, ev):
        step = zoom_step(ev)
        if step is not None:
            self.zoom_notes(step)
            return
        super().keyPressEvent(ev)

    def event(self, ev):
        if ev.type() == QEvent.WindowActivate:
            self.check_disk()
        elif ev.type() == QEvent.WindowDeactivate:
            self.flush()
        return super().event(ev)

    def restore_window(self):
        st = self.store.state
        try:
            if st.get("geometry"):
                self.restoreGeometry(QByteArray(base64.b64decode(st["geometry"])))
            if st.get("hsplit"):
                self.hsplit.setSizes([int(v) for v in st["hsplit"]])
        except (ValueError, TypeError):
            pass

    def save_all(self):
        self.flush()
        self.remember_cursor()
        st = self.store.state
        st["geometry"] = base64.b64encode(bytes(self.saveGeometry())).decode("ascii")
        st["hsplit"] = self.hsplit.sizes()
        st.pop("vsplit", None)  # pane heights from before the boxes sized themselves
        st["current"] = self.cur
        live = {e["id"] for e in self.store.entries}
        st["cursor"] = {k: v for k, v in st.get("cursor", {}).items() if k in live}
        try:
            self.store.save_state()
        except OSError as ex:
            log(f"state save failed: {ex}")

    def show_window(self):
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        QTimer.singleShot(0, self.place_grip)

    def summon(self):
        """Bring the window to the front over everything, whatever had the focus: Windows only lets the app
        that had the last input take the foreground, so the app borrows that thread's input for a moment."""
        self.show_window()
        if TEST:
            return
        try:
            u, k = ctypes.windll.user32, ctypes.windll.kernel32
            u.GetForegroundWindow.restype = ctypes.c_void_p
            u.GetWindowThreadProcessId.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
            u.SetForegroundWindow.argtypes = u.BringWindowToTop.argtypes = (ctypes.c_void_p,)
            hwnd = int(self.winId())
            fg = u.GetForegroundWindow()
            theirs = u.GetWindowThreadProcessId(fg, None) if fg else 0
            mine = k.GetCurrentThreadId()
            if theirs and theirs != mine:
                u.AttachThreadInput(mine, theirs, True)
            u.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # topmost for a moment
            u.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # and back to normal
            u.BringWindowToTop(hwnd)
            u.SetForegroundWindow(hwnd)
            if theirs and theirs != mine:
                u.AttachThreadInput(mine, theirs, False)
        except Exception as ex:
            log(f"summon: {ex}")

    def watch_corner(self):
        """Every tenth of a second: is the pointer in the top left corner of the screen with the left button
        pressed? Then the window comes up. Costs next to nothing (two small Windows calls)."""
        try:
            pt = _POINT()
            u = ctypes.windll.user32
            u.GetCursorPos(ctypes.byref(pt))
            inside = corner_hit(pt.x, pt.y, self.corner_spots())
            down = bool(u.GetAsyncKeyState(0x01) & 0x8000) if inside else False
        except Exception:
            return
        was_in, was_down = self.corner_was
        self.corner_was = (inside, down)
        if inside and down and not was_down and was_in:  # pressed while already in the corner
            self.summon()

    def corner_spots(self):
        """The top left corner of every screen with no screen to its left or above it (real pixels)."""
        if getattr(self, "_spots", None) is None or time.monotonic() - self._spots[0] > 5:
            mons = [m[1] for m in self.win32.monitors()]
            spots = []
            for left, top, _r, _b in mons:
                beside = any(l2 <= left - 1 < r2 and t2 <= top < b2 for l2, t2, r2, b2 in mons)
                above = any(l2 <= left < r2 and t2 <= top - 1 < b2 for l2, t2, r2, b2 in mons)
                if not beside and not above:
                    spots.append((left, top))
            self._spots = (time.monotonic(), spots)
        return self._spots[1]

    def closeEvent(self, ev):
        """The X hides the window. The app keeps running in the tray until Quit."""
        self.drop_fresh(force=True)  # a new note left blank is not kept
        self.save_all()
        if self.really_quit or self.tray is None:
            ev.accept()
        else:
            ev.ignore()
            self.hide()
            QTimer.singleShot(400, trim_memory)

    def quit(self):
        self.really_quit = True
        self.unpin(keep=True)  # give the strip back to the other windows; it is pinned again next start
        self.save_all()
        if self.tray:
            self.tray.hide()
        QApplication.instance().quit()


# ---------------------------------------------------------------------------- start

def build_tray(app, win, icon):
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip(APP_NAME)
    m, auto, themes = tray_menu(win)
    tray.setContextMenu(m)
    tray.activated.connect(lambda why: win.show_window() if why == QSystemTrayIcon.Trigger else None)
    tray.menu, tray.auto_action, tray.theme_actions = m, auto, themes
    tray.show()
    return tray


def tray_menu(win):
    m = make_menu()
    info = m.addAction("Desktop window  ·  no browser, no port")
    info.setEnabled(False)
    m.addSeparator()
    m.addAction("Open " + APP_NAME, win.show_window).setToolTip("Bring the window up.")
    auto = m.addAction("Start with Windows")
    auto.setCheckable(True)
    auto.setChecked(bool(autostart_get()))
    auto.setToolTip("Starts Nimble Notes hidden in the tray when you sign in to Windows.")
    auto.toggled.connect(autostart_set)
    tm = make_menu(m)
    tm.setTitle("Theme")
    themes = {}
    for t in T.THEMES:
        a = tm.addAction(theme_swatch(t["id"]), t["name"], lambda i=t["id"]: win.set_theme(i))
        a.setCheckable(True)
        a.setChecked(t["id"] == T.ID)
        themes[t["id"]] = a
    m.addMenu(tm)
    m.addAction("About", lambda: (win.show_window(), win.about.open()))
    m.addSeparator()
    m.addAction("Quit", win.quit).setToolTip("Save everything and close Nimble Notes.")
    return m, auto, themes


def apply_palette(app):
    pal = QPalette()
    for role, color in ((QPalette.Window, T.BG), (QPalette.Base, T.BG_INPUT), (QPalette.AlternateBase, T.BG_CARD),
                        (QPalette.Text, T.TEXT), (QPalette.WindowText, T.TEXT), (QPalette.ButtonText, T.TEXT_DIM),
                        (QPalette.Button, T.BG_CARD), (QPalette.PlaceholderText, T.PLACEHOLDER),
                        (QPalette.ToolTipBase, T.BG_HI), (QPalette.ToolTipText, T.TEXT),
                        (QPalette.Highlight, T.ACCENT), (QPalette.HighlightedText, T.ON_ACCENT),
                        (QPalette.Link, T.ACCENT_TEXT)):
        pal.setColor(role, QColor(color))
    app.setPalette(pal)


def main():
    sys.excepthook = excepthook
    handles = claim_instance("--quit" in sys.argv)
    if handles is None:
        return 0
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("NimbleCloud13.NimbleNotes")
    except Exception:
        pass
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    saved = store.read_json(store.STATE_PATH, {})
    T.apply(saved.get("theme") if isinstance(saved, dict) else None)  # the saved theme is on before anything shows
    apply_palette(app)
    load_fonts()
    if isinstance(saved, dict):  # the saved font is on before anything is built
        fid = saved.get("font") or saved.get("ui_font") or "segoe-ui"
        T.UI_FONT = T.NOTES_FONT = font_family(fid)
    app.setFont(ui_font(13))
    app.setStyleSheet(T.QSS)
    icon = app_icon()
    app.setWindowIcon(icon)

    win = MainWindow()
    dark_titlebar(win)
    app.installEventFilter(win)
    app.aboutToQuit.connect(win.save_all)
    app.commitDataRequest.connect(lambda *_: win.save_all())

    first_run = not win.store.state.get("autostart_set")
    if first_run:
        autostart_set(True)
        win.store.state["autostart_set"] = True
        win.store.save_state()
    elif autostart_get() and autostart_get() != autostart_command():
        autostart_set(True)  # the app folder moved: point the startup entry at the new place
    win.tray = build_tray(app, win, icon)
    win.corner_timer = QTimer(win)  # the top left corner of the screen brings the window up when clicked
    win.corner_timer.timeout.connect(win.watch_corner)
    win.corner_timer.start(100)

    win.signals = InstanceSignals()
    win.signals.wake.connect(win.show_window, Qt.QueuedConnection)
    win.signals.leave.connect(win.quit, Qt.QueuedConnection)
    watch_events(handles[1], handles[2], win.signals)

    if "--hidden" in sys.argv:
        QTimer.singleShot(1500, trim_memory)
    else:
        win.show_window()
        if first_run:
            QTimer.singleShot(600, lambda: win.toast.say(
                "Nimble Notes starts with Windows. Turn that off from its tray icon.", ms=6000))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

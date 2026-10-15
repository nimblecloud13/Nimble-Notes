"""Nimble Notes theme: the NimbleCloud design tokens and the Qt stylesheet built from them.

The colors come from nimble_themes.py (the 15 approved themes, Nimble first and the default). apply(id)
rebinds every name below and rebuilds QSS, so anything that reads T.ACCENT and friends at paint time
follows the theme. Layout, sizes and fonts never change with a theme."""

import nimble_themes

UI_FONT = "Segoe UI"
MONO_FONT = "Consolas"
THEMES = nimble_themes.THEMES
DEFAULT = nimble_themes.DEFAULT

# filled in by apply(): the layered backgrounds, borders, the one accent, text and the category colors
ID = NAME = MODE = ""
BG = BG_PANEL = BG_CARD = BG_INPUT = BG_HI = BORDER = BORDER_HI = ""
ACCENT = ACCENT_HI = ACCENT_TEXT = ACCENT_SOFT = ON_ACCENT = PRESSED = ""
SELECT = ""     # the selected row in the list: a lighter, bluer shade of the navy background
GOLD_SOFT = ""  # the Ideas text: the theme's softer accent (a lighter gold in Nimble)
TEXT = TEXT_DIM = TEXT_MUTED = PLACEHOLDER = ""
GREEN = RED = BLUE = PURPLE = ""
ACCENT_RGB = BACKDROP_RGB = (0, 0, 0)
BACKDROP = SHADOW = QSS = ""


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


rgb_of = _rgb  # '#rrggbb' -> (r, g, b), for painting code that needs its own alpha


def _hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(v))):02x}" for v in rgb)


def mix(a, b, t):
    """The color t of the way from a to b."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(x + (y - x) * t for x, y in zip(ra, rb)))


def rgba(rgb, alpha):
    return f"rgba({rgb[0]},{rgb[1]},{rgb[2]},{alpha})"


def apply(theme_id=None):
    """Switch every token to one theme (an unknown id falls back to Nimble). Returns the id used."""
    t = nimble_themes.tokens(theme_id)
    g = globals()
    for k in ("ID", "NAME", "MODE", "BG", "BG_PANEL", "BG_CARD", "BG_INPUT", "BG_HI", "BORDER", "BORDER_HI",
              "ACCENT", "ACCENT_HI", "ACCENT_TEXT", "ACCENT_SOFT", "ON_ACCENT", "TEXT", "TEXT_DIM", "TEXT_MUTED",
              "GREEN", "RED", "BLUE", "PURPLE", "ACCENT_RGB", "BACKDROP", "SHADOW"):
        g[k] = t[k]
    g["GOLD_SOFT"] = t["ACCENT_SOFT"]
    nimble = t["ID"] == "nimble"
    g["PRESSED"] = "#d98a06" if nimble else mix(t["ACCENT"], "#000000", .14)  # the primary button held down
    g["SELECT"] = mix(t["BG_HI"], t["BLUE"], .28)
    g["PLACEHOLDER"] = "#5d6787" if nimble else mix(t["TEXT_MUTED"], t["BG_INPUT"], .38)
    g["BACKDROP_RGB"] = tuple(int(float(v)) for v in t["BACKDROP"][5:-1].split(",")[:3])
    g["QSS"] = build_qss()
    return t["ID"]


def build_qss():
    A = ACCENT_RGB
    sel = rgba(A, .38)
    return f"""
QWidget#root, QWidget#main {{ background: {BG}; }}
QFrame#sidebar {{ background: {BG_PANEL}; border: none; border-right: 1px solid {BORDER}; }}
QFrame#statusbar {{ background: {BG_PANEL}; border: none; border-top: 1px solid {BORDER}; }}
QLabel {{ color: {TEXT}; background: transparent; }}
QLabel#seclabel {{ color: {TEXT_MUTED}; }}

QPushButton#brand {{ font-size: 15px; font-weight: 700; color: {TEXT}; background: transparent;
  border: none; text-align: left; padding: 0; }}
QPushButton#brand:hover {{ color: {ACCENT_TEXT}; }}
QLabel#dot {{ background: {ACCENT}; border-radius: 3px; }}
QLabel#title {{ font-size: 20px; font-weight: 700; color: {TEXT}; }}
QLabel#similar, QLabel#statustext, QLabel#brandline {{ font-size: 11px; color: {TEXT_MUTED}; }}
QLabel#statuspath {{ font-family: '{MONO_FONT}'; font-size: 11px; color: {TEXT_MUTED}; }}
QLabel#saved {{ font-size: 11px; color: {TEXT_DIM}; }}
QLabel#hint {{ font-size: 11px; color: {TEXT_MUTED}; }}
QLabel#version {{ font-size: 10px; color: {TEXT_MUTED}; }}
QLabel#kbd {{ font-family: '{MONO_FONT}'; font-size: 10px; color: {TEXT_DIM}; background: {BG};
  border: 1px solid {BORDER_HI}; border-bottom: 2px solid {BORDER_HI}; border-radius: 4px; padding: 0px 5px; }}

QLineEdit {{ background: {BG_INPUT}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 7px;
  min-height: 30px; padding: 0 10px; font-size: 12px;
  selection-background-color: {sel}; selection-color: {TEXT}; }}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QLineEdit#titleedit {{ font-size: 20px; font-weight: 700; min-height: 34px; padding: 0 8px; }}

QPlainTextEdit {{ color: {TEXT}; border: 1px solid {BORDER}; border-radius: 7px;
  selection-background-color: {sel}; selection-color: {TEXT}; }}
QPlainTextEdit:focus {{ border-color: {ACCENT}; }}
QPlainTextEdit#tldr, QPlainTextEdit#ideas {{ background: {BG_CARD}; padding: 6px 8px 3px 8px; font-size: 13px; }}
QFrame#notesbox {{ background: {BG_INPUT}; border: 1px solid {BORDER}; border-radius: 7px; }}
QFrame#notesbox[focused="true"] {{ border-color: {ACCENT}; }}
QScrollArea#notescroll {{ background: transparent; border: none; }}
QWidget#notesview, QWidget#notescontent {{ background: transparent; }}
QTextEdit#work, QTextEdit#revopen, QTextEdit#revdone {{ background: transparent; border: none; color: {TEXT};
  selection-background-color: {sel}; selection-color: {TEXT}; }}
QTextEdit#revdone {{ color: {TEXT_MUTED}; }}
QFrame#revbox {{ background: {BG}; border: 1px solid {rgba(A, .55)}; border-radius: 7px; }}
QPushButton[tier="strike"] {{ min-height: 28px; background: {ACCENT}; color: {ON_ACCENT}; border: none;
  border-radius: 7px; padding: 0 14px; font-size: 12px; font-weight: 600; }}
QPushButton[tier="strike"]:hover {{ background: {ACCENT_HI}; }}
QPushButton[tier="strike"]:pressed {{ background: {PRESSED}; }}
QPushButton[tier="strike"]:disabled {{ background: {rgba(A, .16)}; color: {rgba(A, .55)}; }}

QPushButton[tier="secondary"] {{ min-height: 28px; background: transparent; border: 1px solid {BORDER_HI};
  color: {TEXT_DIM}; border-radius: 7px; padding: 0 14px; font-size: 12px; font-weight: 500; }}
QPushButton[tier="secondary"]:hover {{ background: {BG_HI}; color: {TEXT}; }}
QPushButton[tier="secondary"]:pressed {{ background: {BG_CARD}; }}
QPushButton[tier="primary"] {{ background: {ACCENT}; color: {ON_ACCENT}; border: none; border-radius: 7px;
  padding: 0 22px; font-size: 14px; font-weight: 600; }}
QPushButton[tier="primary"]:hover {{ background: {ACCENT_HI}; }}
QPushButton[tier="ghost"] {{ min-height: 26px; background: transparent; border: none; color: {TEXT_MUTED};
  padding: 0 8px; font-size: 12px; font-weight: 600; }}
QPushButton[tier="ghost"]:hover {{ color: {TEXT}; }}
QPushButton[tier="chip"] {{ min-height: 22px; background: {BG_CARD}; border: 1px solid {BORDER};
  color: {TEXT_DIM}; border-radius: 7px; padding: 0 9px; font-size: 11px; font-weight: 600; }}
QPushButton[tier="chip"]:hover {{ background: {BG_HI}; border-color: {BORDER_HI}; color: {TEXT}; }}
QPushButton[tier="chip"][sel="true"] {{ background: {BG_HI}; border-color: {BORDER_HI}; color: {TEXT}; }}
QPushButton[tier="chip"][lit="true"] {{ background: {ACCENT}; border-color: {ACCENT}; color: {ON_ACCENT}; }}
QPushButton[tier="chip"][lit="true"]:hover {{ background: {ACCENT_HI}; border-color: {ACCENT_HI}; color: {ON_ACCENT}; }}
QPushButton[tier="toast"] {{ background: transparent; border: none; color: {ACCENT_TEXT}; font-size: 12px;
  font-weight: 700; padding: 0 4px; }}
QPushButton[tier="toast"]:hover {{ color: {TEXT}; }}
QPushButton[tier="linkcard"] {{ background: {BG}; border: 1px solid {BORDER_HI}; border-radius: 7px;
  color: {TEXT_DIM}; font-size: 12px; font-weight: 600; padding: 9px 12px; text-align: left; }}
QPushButton[tier="linkcard"]:hover {{ background: {BG_HI}; border-color: {ACCENT}; color: {TEXT}; }}

QListWidget#applist {{ background: transparent; border: none; outline: 0; }}

QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px 0; }}
QScrollBar::handle:vertical {{ background: {BORDER_HI}; border-radius: 4px; min-height: 28px; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER_HI}; border-radius: 4px; min-width: 28px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QToolTip {{ background: {BG_HI}; color: {TEXT}; border: 1px solid {BORDER_HI}; padding: 5px 8px;
  font-size: 12px; }}

QMenu {{ background: {BG_CARD}; border: 1px solid {BORDER_HI}; border-radius: 7px; padding: 5px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 5px; color: {TEXT_DIM}; font-size: 12px; }}
QMenu::item:selected {{ background: {BG_HI}; color: {TEXT}; }}
QMenu::item:disabled {{ color: {rgba(_rgb(TEXT_MUTED), .45)}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 6px; }}
QMenu::icon {{ padding-left: 8px; }}
QMenu::indicator {{ width: 12px; height: 12px; margin-left: 8px; border-radius: 3px;
  border: 1px solid {BORDER_HI}; background: {BG_INPUT}; }}
QMenu::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QMenu QLineEdit {{ margin: 2px 2px 4px 2px; min-width: 190px; }}

QFrame#toast {{ background: {BG_HI}; border: 1px solid {BORDER_HI}; border-radius: 18px; }}
QFrame#toast QLabel {{ font-size: 12px; color: {TEXT}; }}
QFrame#bubble {{ background: {BG_HI}; border: 1px solid {BORDER_HI}; border-radius: 13px; }}
QFrame#bubble QLabel {{ font-size: 11px; color: {TEXT}; }}
QPlainTextEdit#ideas {{ color: {ACCENT_SOFT}; }}
QFrame#noticecard {{ background: {BG_CARD}; border: 1px solid {BORDER_HI}; border-radius: 14px; }}
QTextEdit#pathtext {{ background: transparent; border: none; color: {TEXT};
  selection-background-color: {sel}; selection-color: {TEXT}; }}
QLabel#tokens {{ font-family: '{MONO_FONT}'; font-size: 12px; font-weight: 700; color: {ACCENT_TEXT}; }}
QFrame#filmstrip {{ background: {BG_PANEL}; border: none; border-top: 1px solid {BORDER};
  border-bottom: 1px solid {BORDER}; }}
QFrame#revstrip {{ background: transparent; border: none; }}
QScrollArea#stripscroll {{ background: transparent; border: none; }}
QWidget#stripview, QWidget#stripinner {{ background: transparent; }}
QLabel#viewcaption {{ font-size: 12px; color: {TEXT_DIM}; }}

QWidget#backdrop {{ background: {BACKDROP}; }}
QFrame#aboutcard, QFrame#famcard {{ background: {BG_CARD}; border: 1px solid {BORDER_HI}; border-radius: 14px; }}
QLabel#famtitle {{ font-size: 19px; font-weight: 700; }}
QListWidget#famlist, QListWidget#famentries {{ background: {BG_INPUT}; border: 1px solid {BORDER};
  border-radius: 7px; padding: 4px; outline: 0; font-size: 12px; color: {TEXT_DIM}; }}
QListWidget#famlist::item, QListWidget#famentries::item {{ padding: 5px 8px; border-radius: 5px; color: {TEXT_DIM}; }}
QListWidget#famlist::item:hover, QListWidget#famentries::item:hover {{ background: {BG_HI}; color: {TEXT}; }}
QListWidget#famlist::item:selected {{ background: {ACCENT}; color: {ON_ACCENT}; }}
QListWidget#famentries::item:selected {{ background: {BG_HI}; color: {TEXT}; }}
QListWidget#famentries::indicator {{ width: 13px; height: 13px; border: 1px solid {BORDER_HI}; border-radius: 4px;
  background: {BG}; }}
QListWidget#famentries::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QPushButton#pickhead {{ background: transparent; border: none; color: {TEXT_MUTED}; text-align: left;
  padding: 8px 2px 2px 2px; }}
QPushButton#pickhead:hover {{ color: {TEXT}; }}
QScrollArea#pickscroll {{ background: transparent; border: none; }}
QWidget#pickview, QWidget#pickinner {{ background: transparent; }}
QLabel#placehead {{ font-size: 11px; color: {TEXT_MUTED}; }}
QLabel#abouttitle {{ font-size: 22px; font-weight: 700; }}
QLabel#aboutblurb {{ font-size: 12px; color: {TEXT_DIM}; }}
QLabel#aboutfine {{ font-size: 11px; color: {TEXT_MUTED}; }}
QLabel#emptytitle {{ font-size: 20px; font-weight: 700; }}
QLabel#emptysub {{ font-size: 13px; color: {TEXT_MUTED}; }}
"""


apply(DEFAULT)

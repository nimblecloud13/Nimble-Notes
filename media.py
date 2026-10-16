"""Nimble Notes pictures and videos: the film strip of thumbnails in a note, the enlarged viewer, the
helper that pulls pictures out of a drop or a paste, the small in-app pop-up with a copyable path, and
the invisible corner grip for resizing the window.
Pictures and videos are always copied into images/<entry name>/ (see store.py); the originals are never
touched, and taking one off a note never deletes its file."""

import math
import os

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QImage, QImageReader, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
                           QTextBlockFormat, QTextCursor, QTextOption)
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizeGrip,
                               QSizePolicy,
                               QTextEdit, QVBoxLayout, QWidget)

import theme as T
from store import MEDIA_EXT, VIDEO_EXT

THUMB = 80
_thumbs = {}  # path -> (file time, square QPixmap)


def is_video(path):
    return path.lower().endswith(VIDEO_EXT)


def image_payload(mime):
    """The pictures and videos in a drop or a paste: local files, else picture data. [] when there are
    none, and also when it is really text: a spreadsheet or document selection offers itself as a
    picture too."""
    files = [u.toLocalFile() for u in mime.urls()] if mime.hasUrls() else []
    files = [p for p in files if p and p.lower().endswith(MEDIA_EXT) and os.path.isfile(p)]
    if files:
        return files
    if mime.hasImage() and not (mime.hasText() and len(mime.text().split()) > 1):
        img = mime.imageData()
        if isinstance(img, QPixmap):
            img = img.toImage()
        if isinstance(img, QImage) and not img.isNull():
            return [img]
    return []


def thumb_pixmap(path, side=THUMB * 2):
    """A square, centre-cropped thumbnail, read at reduced size so a huge picture costs little memory.
    None for a video (it gets a drawn tile instead) and for a file that is missing or unreadable."""
    if is_video(path):
        return None
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return None
    hit = _thumbs.get(path)
    if hit and hit[0] == stamp:
        return hit[1]
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and min(size.width(), size.height()) > side:
        k = side / min(size.width(), size.height())
        reader.setScaledSize(QSize(max(side, round(size.width() * k)), max(side, round(size.height() * k))))
    img = reader.read()
    if img.isNull():
        return None
    m = min(img.width(), img.height())
    img = img.copy((img.width() - m) // 2, (img.height() - m) // 2, m, m)
    if m > side:
        img = img.scaled(side, side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    if len(_thumbs) > 300:
        _thumbs.clear()
    pm = QPixmap.fromImage(img)
    _thumbs[path] = (stamp, pm)
    return pm


def _small_font(px, bold=False, mono=False):
    f = QFont(T.MONO_FONT if mono else T.UI_FONT)
    f.setPixelSize(px)
    f.setBold(bold)
    return f


class Thumb(QAbstractButton):
    """One 80 px thumbnail in a film strip. A picture shows itself; a video shows a tile with a play
    mark and its name. While the mouse is over it a small x appears in its top right corner."""
    removed = Signal()  # the x was clicked

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.video = is_video(path)
        self.there = os.path.isfile(path)
        self.pm = thumb_pixmap(path)
        self.over_x = False
        self.setFixedSize(THUMB + 4, THUMB + 4)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.setMouseTracking(True)
        name = os.path.basename(path)
        if not self.there:
            tip = name + "\nThis file is missing from the images folder. The x takes it off the note."
        elif self.video:
            tip = name + "\nClick to play it in your video player. Right-click to copy it or show it in its folder."
        else:
            tip = name + "\nClick to enlarge. Right-click to copy it or show it in its folder."
        self.setToolTip(tip + "\nThe x in the corner takes it off this note; the file itself is kept.")

    def x_rect(self):
        return QRectF(THUMB + 2 - 21, 5, 18, 18)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        box = QRectF(2, 2, THUMB, THUMB)
        shape = QPainterPath()
        shape.addRoundedRect(box, 7, 7)
        p.fillPath(shape, QColor(T.BG_CARD if self.video else T.BG_INPUT))
        if self.pm:
            p.setClipPath(shape)
            p.drawPixmap(box, self.pm, QRectF(self.pm.rect()))
            p.setClipping(False)
        elif self.video and self.there:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.TEXT_DIM))
            cx, cy = box.center().x() + 2, box.center().y() - 8
            p.drawPolygon(QPolygonF([QPointF(cx - 9, cy - 11), QPointF(cx - 9, cy + 11), QPointF(cx + 10, cy)]))
            p.setPen(QColor(T.TEXT_MUTED))
            p.setFont(_small_font(9, bold=True, mono=True))
            p.drawText(QRectF(box.left(), box.bottom() - 30, THUMB, 12), Qt.AlignCenter,
                       os.path.splitext(self.path)[1][1:].upper())
            p.setFont(_small_font(9))
            name = p.fontMetrics().elidedText(os.path.basename(self.path), Qt.ElideMiddle, THUMB - 8)
            p.drawText(QRectF(box.left(), box.bottom() - 17, THUMB, 13), Qt.AlignCenter, name)
        else:
            p.setFont(_small_font(10))
            p.setPen(QColor(T.TEXT_MUTED))
            p.drawText(box, Qt.AlignCenter, "missing")
        if self.underMouse():
            p.setPen(QPen(QColor(T.BORDER_HI), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(1, 1, THUMB + 2, THUMB + 2), 8, 8)
            x = self.x_rect()  # the small x: dark until the mouse is on it, then red
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.RED) if self.over_x else QColor(*T.rgb_of(T.BG_INPUT), 215))
            p.drawEllipse(x)
            p.setPen(QPen(QColor(T.ON_ACCENT if self.over_x else T.TEXT), 1.7, Qt.SolidLine, Qt.RoundCap))
            c = x.center()
            p.drawLine(QPointF(c.x() - 3.6, c.y() - 3.6), QPointF(c.x() + 3.6, c.y() + 3.6))
            p.drawLine(QPointF(c.x() - 3.6, c.y() + 3.6), QPointF(c.x() + 3.6, c.y() - 3.6))

    def mouseMoveEvent(self, ev):
        over = self.x_rect().contains(ev.position())
        if over != self.over_x:
            self.over_x = over
            self.update()
        super().mouseMoveEvent(ev)

    def leaveEvent(self, ev):
        self.over_x = False
        super().leaveEvent(ev)

    def mousePressEvent(self, ev):
        self.x_down = ev.button() == Qt.LeftButton and self.x_rect().contains(ev.position())
        if not self.x_down:
            super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        if getattr(self, "x_down", False):
            self.x_down = False
            if self.x_rect().contains(ev.position()):
                self.removed.emit()
            return
        super().mouseReleaseEvent(ev)


class AddButton(QAbstractButton):
    """The add-picture button at the left of the live film strip: a small picture icon with a plus."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(34, 30)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.setToolTip("Add pictures or videos to this note. Pick files here, drag them onto the note, or paste "
                        "with Ctrl+V. Each one is copied into the images folder, in a subfolder named after this "
                        "note; the original is not touched.")

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        hot = self.underMouse()
        p.setPen(QPen(QColor(T.BORDER_HI), 1))
        p.setBrush(QColor(T.BG_HI) if hot else Qt.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 7, 7)
        pen = QPen(QColor(T.TEXT if hot else T.TEXT_DIM), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(7, 8, 15, 13), 2.5, 2.5)                      # the frame
        p.drawPolyline([QPointF(8.5, 19), QPointF(12.5, 14.5), QPointF(15.5, 17.5), QPointF(17.5, 15.5),
                        QPointF(21, 19)])                                      # the hills
        p.drawEllipse(QPointF(11.5, 11.5), 1.2, 1.2)                           # the sun
        p.setPen(QPen(QColor(T.ACCENT_TEXT), 1.7, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(26, 6), QPointF(26, 12))                            # the plus
        p.drawLine(QPointF(23, 9), QPointF(29, 9))


class FilmStrip(QFrame):
    """A row of 80 px thumbnails. The live strip sits between the text being typed and the Revisions
    complete button: it is always there (it is the border between the two), carries the add-picture
    button, and takes drops. A finished revision gets a plain strip, shown only when it has pictures."""
    add = Signal()
    opened = Signal(int)          # which one was clicked
    menu = Signal(int, QPoint)    # which one was right-clicked, and where on screen
    remove = Signal(int)          # which one had its x clicked
    dropped = Signal(object)      # dropped on the strip: file paths and/or QImages

    def __init__(self, live):
        super().__init__()
        self.live = live
        self.paths = []
        self.thumbs = []
        self.setObjectName("filmstrip" if live else "revstrip")
        self.setAcceptDrops(live)
        row = QHBoxLayout(self)
        row.setContentsMargins(8 if live else 6, 6 if live else 2, 8, 6 if live else 2)
        row.setSpacing(8)
        self.add_btn = None
        self.hint = QLabel("Drop, paste or add pictures and videos")
        self.hint.setObjectName("hint")
        self.hint.setMinimumWidth(0)
        self.hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)  # cut short in a narrow window
        if live:
            self.add_btn = AddButton()
            self.add_btn.clicked.connect(lambda: self.add.emit())
            row.addWidget(self.add_btn, 0, Qt.AlignVCenter)
            row.addWidget(self.hint, 1, Qt.AlignVCenter)  # takes the room the empty strip has, and gives it up
        self.area = QScrollArea()
        self.area.setObjectName("stripscroll")
        self.area.setFrameShape(QFrame.NoFrame)
        self.area.setWidgetResizable(True)
        self.area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.area.setFixedHeight(THUMB + 4 + 10)  # room for the thin scrollbar when the row overflows
        self.area.viewport().setObjectName("stripview")
        inner = QWidget()
        inner.setObjectName("stripinner")
        self.row = QHBoxLayout(inner)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(7)
        self.row.addStretch(1)
        self.area.setWidget(inner)
        row.addWidget(self.area, 1)
        if live:
            row.addStretch(0)
        self.show_images([])

    def show_images(self, paths):
        for t in self.thumbs:
            t.hide()
            t.deleteLater()
        self.paths, self.thumbs = list(paths), []
        for i, path in enumerate(self.paths):
            t = Thumb(path)
            t.clicked.connect(lambda _=False, i=i: self.opened.emit(i))
            t.removed.connect(lambda i=i: self.remove.emit(i))
            t.setContextMenuPolicy(Qt.CustomContextMenu)
            t.customContextMenuRequested.connect(lambda pos, i=i, t=t: self.menu.emit(i, t.mapToGlobal(pos)))
            self.row.insertWidget(self.row.count() - 1, t)
            self.thumbs.append(t)
        has = bool(self.paths)
        self.area.setVisible(has)
        self.hint.setVisible(self.live and not has)
        want = self.live or has
        if self.parentWidget() is not None or not want:
            self.setVisible(want)
        else:  # never show it before it has a parent (that flashes it as a window of its own): just undo any
            self.setAttribute(Qt.WA_WState_ExplicitShowHide, False)  # hide, so it shows with its parent
        self.setFixedHeight((THUMB + 4 + 10 + (12 if self.live else 4)) if has else 42)

    def dragEnterEvent(self, ev):
        if image_payload(ev.mimeData()):
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev):
        if image_payload(ev.mimeData()):
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        got = image_payload(ev.mimeData())
        if got:
            ev.acceptProposedAction()
            self.dropped.emit(got)


def _plain_button(parent, text, tier, tip, slot):
    b = QPushButton(text, parent)
    b.setProperty("tier", tier)
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.NoFocus)
    b.setToolTip(tip)
    if slot:
        b.clicked.connect(slot)
    return b


class ImageViewer(QWidget):
    """An enlarged picture over the whole window. The arrows and the arrow keys step through the note's
    pictures, the mouse wheel zooms, dragging moves a zoomed picture, Esc or a click beside it closes.
    Copy image, at the bottom, and the right-click menu put the picture on the clipboard."""
    copy = Signal(str)       # copy this picture (its path)
    menu = Signal(QPoint)    # right-clicked: where on screen

    def __init__(self, parent):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.paths, self.index, self.pm = [], 0, None
        self.zoom, self.shift, self.grab_at = 1.0, QPointF(0, 0), None
        self.dragged = False
        self.prev = _plain_button(self, "<", "secondary", "Previous picture (Left arrow).", lambda: self.step(-1))
        self.next = _plain_button(self, ">", "secondary", "Next picture (Right arrow).", lambda: self.step(1))
        self.shut = _plain_button(self, "Close", "secondary", "Close the picture. Esc works too.", self.hide)
        self.copy_btn = _plain_button(self, "Copy image", "secondary",
                                      "Puts this picture on the clipboard, ready to paste. Ctrl+C does the same.",
                                      self.copy_now)
        self.caption = QLabel(self)
        self.caption.setObjectName("viewcaption")
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.flash = QTimer(self)
        self.flash.setSingleShot(True)
        self.flash.timeout.connect(lambda: self.copy_btn.setText("Copy image"))
        parent.installEventFilter(self)
        self.hide()

    def current(self):
        return self.paths[self.index] if self.paths else ""

    def copy_now(self):
        if self.current():
            self.copy.emit(self.current())
            self.copy_btn.setText("Copied")
            self.place()
            self.flash.start(1300)

    def open(self, paths, index):
        self.paths = list(paths)
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.setFocus()
        self.load(index)

    def load(self, index):
        self.index = max(0, min(index, len(self.paths) - 1))
        self.zoom, self.shift = 1.0, QPointF(0, 0)
        path = self.current()
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid() and max(size.width(), size.height()) > 4000:  # keep a giant picture from eating memory
            k = 4000 / max(size.width(), size.height())
            reader.setScaledSize(QSize(round(size.width() * k), round(size.height() * k)))
        img = reader.read()
        self.pm = None if img.isNull() else QPixmap.fromImage(img)
        several = len(self.paths) > 1
        self.prev.setVisible(several)
        self.next.setVisible(several)
        self.copy_btn.setEnabled(self.pm is not None)
        self.copy_btn.setText("Copy image")
        name = os.path.basename(path)
        self.caption.setText(f"{self.index + 1} / {len(self.paths)}   ·   {name}"
                             + ("" if self.pm else "   ·   this picture could not be opened"))
        self.place()
        self.update()

    def step(self, by):
        if len(self.paths) > 1:
            self.load((self.index + by) % len(self.paths))

    def place(self):
        w, h = self.width(), self.height()
        self.prev.setGeometry(16, h // 2 - 20, 40, 40)
        self.next.setGeometry(w - 56, h // 2 - 20, 40, 40)
        self.shut.adjustSize()
        self.shut.move(w - self.shut.width() - 16, 14)
        self.copy_btn.adjustSize()
        self.copy_btn.move((w - self.copy_btn.width()) // 2, h - self.copy_btn.height() - 14)  # bottom, centred
        self.caption.setGeometry(70, self.copy_btn.y() - 30, max(10, w - 140), 24)

    def picture_rect(self):
        if not self.pm:
            return QRectF()
        room_w, room_h = max(50, self.width() - 150), max(50, self.height() - 150)
        fit = min(room_w / self.pm.width(), room_h / self.pm.height(), 1.0) * self.zoom
        w, h = self.pm.width() * fit, self.pm.height() * fit
        return QRectF((self.width() - w) / 2 + self.shift.x(), (self.height() - h) / 2 - 22 + self.shift.y(), w, h)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(*T.BACKDROP_RGB, 215) if T.MODE == "dark" else QColor(*T.rgb_of(T.BG_PANEL), 235))
        if self.pm:
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawPixmap(self.picture_rect(), self.pm, QRectF(self.pm.rect()))

    def eventFilter(self, obj, ev):
        if ev.type() == ev.Type.Resize and self.isVisible():
            self.setGeometry(self.parentWidget().rect())
        return False

    def resizeEvent(self, ev):
        self.place()

    def wheelEvent(self, ev):
        self.zoom = max(0.2, min(8.0, self.zoom * (1.15 if ev.angleDelta().y() > 0 else 1 / 1.15)))
        if self.zoom <= 1.0:
            self.shift = QPointF(0, 0)
        self.update()
        ev.accept()

    def contextMenuEvent(self, ev):
        if self.pm:
            self.menu.emit(ev.globalPos())

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.grab_at, self.dragged = ev.position(), False

    def mouseMoveEvent(self, ev):
        if self.grab_at is not None and self.zoom > 1.0:
            self.shift += ev.position() - self.grab_at
            self.grab_at, self.dragged = ev.position(), True
            self.update()

    def mouseReleaseEvent(self, ev):
        beside = not self.picture_rect().contains(ev.position())
        if ev.button() == Qt.LeftButton and self.grab_at is not None and not self.dragged and beside:
            self.hide()
        self.grab_at = None

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.hide()
        elif ev.key() == Qt.Key_Left:
            self.step(-1)
        elif ev.key() == Qt.Key_Right:
            self.step(1)
        elif ev.key() == Qt.Key_C and ev.modifiers() == Qt.ControlModifier:
            self.copy_now()


class CopyIcon(QAbstractButton):
    """The little two-overlapping-squares copy mark. It turns green for a moment after a click."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.setToolTip("Copy this path to the clipboard.")
        self.done = QTimer(self)
        self.done.setSingleShot(True)
        self.done.timeout.connect(self.update)
        self.clicked.connect(lambda: (self.done.start(1300), self.update()))

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = T.GREEN if self.done.isActive() else (T.ACCENT_TEXT if self.underMouse() else T.TEXT_DIM)
        p.setPen(QPen(QColor(color), 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(QColor(T.BG_CARD))
        p.drawRoundedRect(QRectF(6.5, 2.5, 9, 9), 2, 2)    # the square behind
        p.drawRoundedRect(QRectF(2.5, 6.5, 9, 9), 2, 2)    # the square in front


class PathLine(QWidget):
    """A full path that wraps wherever it must, can be selected, and carries the copy mark at its end,
    raised off the top right corner of the last character."""
    copy = Signal(str)
    TOP = 8  # room above the text for the raised copy mark

    def __init__(self):
        super().__init__()
        self.path = ""
        self.box = QTextEdit(self)
        self.box.setObjectName("pathtext")
        self.box.setReadOnly(True)
        self.box.setFrameShape(QFrame.NoFrame)
        self.box.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.box.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.box.setWordWrapMode(QTextOption.WrapAnywhere)
        self.box.setFont(_small_font(12, mono=True))
        self.box.document().setDocumentMargin(2)
        self.icon = CopyIcon(self)
        self.icon.clicked.connect(lambda: self.copy.emit(self.path))

    def set_path(self, path):
        self.path = path
        self.box.setPlainText(path)
        airy = QTextBlockFormat()  # open lines, so the raised copy mark never sits on the line above
        airy.setLineHeight(160, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        cur = QTextCursor(self.box.document())
        cur.select(QTextCursor.Document)
        cur.mergeBlockFormat(airy)
        self.settle()

    def settle(self):
        """Size the text to its lines and put the copy mark just past its last character, raised so that
        it sits off the top right corner of it."""
        width = max(60, self.width() - 24)
        self.box.document().setTextWidth(width)
        tall = math.ceil(self.box.document().size().height())
        self.box.setGeometry(0, self.TOP, width, tall)
        end = QTextCursor(self.box.document())
        end.movePosition(QTextCursor.End)
        spot = self.box.cursorRect(end)
        self.icon.move(min(self.width() - 18, spot.right() + 3), max(0, self.TOP + spot.top() - 8))
        self.setFixedHeight(tall + self.TOP + 2)

    def resizeEvent(self, ev):
        self.settle()


class Notice(QWidget):
    """An in-app pop-up over the whole window: a title, a line or two of text, optionally a full path
    with the copy mark at its end, and up to two buttons. Esc or a click beside it picks the last button."""
    copy_path = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("backdrop")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.card = QFrame()
        self.card.setObjectName("noticecard")
        self.card.setFixedWidth(540)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(10)
        self.title = QLabel()
        self.title.setObjectName("famtitle")
        self.title.setWordWrap(True)
        self.text = QLabel()
        self.text.setObjectName("aboutblurb")
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.path = PathLine()
        self.path.copy.connect(self.copy_path)
        lay.addWidget(self.title)
        lay.addWidget(self.text)
        lay.addWidget(self.path)
        lay.addSpacing(4)
        self.row = QHBoxLayout()
        self.row.setSpacing(8)
        self.row.addStretch(1)
        lay.addLayout(self.row)
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        mid = QHBoxLayout()
        mid.addStretch(1)
        mid.addWidget(self.card)
        mid.addStretch(1)
        outer.addLayout(mid)
        outer.addStretch(1)
        self.buttons = []
        self.quiet = None
        parent.installEventFilter(self)
        self.hide()

    def ask(self, title, text, path="", buttons=()):
        """buttons: (label, tier, what to run or None, tooltip). The last one is what Esc picks."""
        for b in self.buttons:
            b.hide()
            b.deleteLater()
        self.buttons = []
        self.title.setText(title)
        self.text.setText(text)
        self.path.setVisible(bool(path))
        for label, tier, run, tip in buttons:
            b = _plain_button(None, label, tier, tip, None)
            b.clicked.connect(lambda _=False, run=run: self.pick(run))
            self.row.addWidget(b)
            self.buttons.append(b)
        self.quiet = buttons[-1][2] if buttons else None
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.setFocus()
        if path:
            self.path.set_path(path)
            QTimer.singleShot(0, self.path.settle)

    def pick(self, run):
        self.hide()
        if run:
            run()

    def eventFilter(self, obj, ev):
        if ev.type() == ev.Type.Resize and self.isVisible():
            self.setGeometry(self.parentWidget().rect())
        return False

    def mousePressEvent(self, ev):
        if not self.card.geometry().contains(ev.position().toPoint()):
            self.pick(self.quiet)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.pick(self.quiet)


class CornerGrip(QSizeGrip):
    """A generous, invisible grab area in the bottom right corner of the window: everything between the
    corner of the notes box and the corner of the window resizes the window when dragged."""

    def paintEvent(self, ev):
        pass

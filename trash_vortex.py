"""A small, animated Trash target. Its idle light bends; its core hides."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient, QRegion
from PySide6.QtWidgets import QAbstractButton

from interactions import mime_paths


class TrashVortex(QAbstractButton):
    files_dropped = Signal(list)
    drag_hovered = Signal(bool)

    def __init__(self, config, path_filter, parent):
        super().__init__(parent)
        self.config = config
        self.path_filter = path_filter
        self.setObjectName("trashVortex")
        self.setFixedSize(176, 148)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Trash")
        self.setAccessibleDescription("Open the system Trash, or drop files here to move them to Trash.")
        self.hovered = self.keyboard_focus = self.dragging = False
        self.drop_paths = []
        self.reveal = 0.
        self._started = self._last_tick = time.monotonic()
        self._success_at = -100.
        self._halo = None
        self._halo_key = None
        self._stopped = False
        self._wide_mask = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        parent.installEventFilter(self)
        if self.window() is not parent:
            self.window().installEventFilter(self)
        self.reposition()
        self.update_mask()

    def update_mask(self):
        wide = self.hovered or self.dragging or self.keyboard_focus or self.reveal > .002
        if wide != self._wide_mask:
            self._wide_mask = wide
            # Do not intercept node clicks in the invisible caption area.
            self.setMask(QRegion(self.rect()) if wide else QRegion(QRect(30, 14, 116, 100), QRegion.RegionType.Ellipse))

    def reposition(self):
        parent = self.parentWidget()
        self.move(max(0, parent.width()-self.width()-8), max(0, parent.height()-self.height()-6))
        self.raise_()

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.reposition()
        if obj is self.window() and event.type() == QEvent.Type.WindowStateChange:
            self.sync_timer()
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        super().showEvent(event)
        self.reposition()
        self.sync_timer()

    def hideEvent(self, event):
        self.timer.stop()
        self.hovered = self.keyboard_focus = False
        self.set_dragging(False)
        super().hideEvent(event)

    def sync_timer(self):
        self.update_mask()
        if self._stopped or not self.isVisible() or self.window().isMinimized():
            self.timer.stop()
            return
        active = self.hovered or self.dragging or self.keyboard_focus or self.reveal > .002
        self.timer.setInterval(16 if active else 50)
        if not self.timer.isActive():
            self._last_tick = time.monotonic()
            self.timer.start()

    def stop(self):
        self._stopped = True
        self.timer.stop()

    def tick(self):
        now = time.monotonic()
        elapsed = min(.1, now-self._last_tick)
        self._last_tick = now
        active = self.hovered or self.dragging or self.keyboard_focus or now-self._success_at < 1.35
        target = 1. if active else 0.
        self.reveal += (target-self.reveal)*(1-math.exp(-elapsed*12))
        if abs(target-self.reveal) < .002:
            self.reveal = target
        self.sync_timer()
        # Never invalidate the graph's projection or scene caches.
        self.update()

    def enterEvent(self, event):
        self.hovered = True
        self.sync_timer()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False
        self.sync_timer()
        super().leaveEvent(event)

    def focusInEvent(self, event):
        self.keyboard_focus = event.reason() in (Qt.FocusReason.TabFocusReason,
            Qt.FocusReason.BacktabFocusReason, Qt.FocusReason.ShortcutFocusReason)
        self.sync_timer()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.keyboard_focus = False
        self.sync_timer()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click(); event.accept()
        else:
            super().keyPressEvent(event)

    def set_dragging(self, value, paths=None):
        changed = value != self.dragging
        self.dragging = value
        self.drop_paths = list(paths or []) if value else []
        if changed:
            self.drag_hovered.emit(value)
        self.sync_timer()

    def _receive(self, event, validate=False):
        # Acknowledge receipt as Copy so another app never deletes originals
        # after a canceled confirmation or an asynchronous gio failure. Orbit
        # itself performs the requested move to Trash after confirmation.
        if not event.possibleActions() & Qt.DropAction.CopyAction:
            event.ignore(); self.set_dragging(False); return False
        paths = self.path_filter(mime_paths(event.mimeData())) if validate else self.drop_paths
        if not paths:
            event.ignore(); self.set_dragging(False); return False
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self.set_dragging(True, paths)
        return True

    def dragEnterEvent(self, event):
        self._receive(event, validate=True)

    def dragMoveEvent(self, event):
        self._receive(event)

    def dragLeaveEvent(self, event):
        self.set_dragging(False)
        event.accept()

    def dropEvent(self, event):
        if self._receive(event, validate=True):
            paths = list(self.drop_paths)
            self.set_dragging(False)
            self.files_dropped.emit(paths)

    def celebrate(self):
        self._success_at = time.monotonic()
        self.sync_timer()

    def color(self, key, alpha=255):
        color = QColor(self.config["colors"][key])
        color.setAlpha(round(max(0, min(255, alpha))))
        return color

    def halo(self):
        key = (self.config["colors"]["primary"], self.config["colors"]["accent"], self.devicePixelRatioF())
        if key != self._halo_key:
            ratio = self.devicePixelRatioF()
            self._halo = QPixmap(round(144*ratio), round(144*ratio))
            self._halo.setDevicePixelRatio(ratio)
            self._halo.fill(Qt.GlobalColor.transparent)
            painter = QPainter(self._halo)
            gradient = QRadialGradient(QPointF(72, 72), 71)
            gradient.setColorAt(0, self.color("primary", 0))
            gradient.setColorAt(.3, self.color("primary", 0))
            gradient.setColorAt(.43, self.color("primary", 65))
            gradient.setColorAt(.64, self.color("accent", 20))
            gradient.setColorAt(1, self.color("accent", 0))
            painter.fillRect(QRectF(0, 0, 144, 144), gradient)
            painter.end()
            self._halo_key = key
        return self._halo

    @staticmethod
    def arc(radius, squash, start, span, phase, wobble=.035):
        path = QPainterPath()
        for index in range(61):
            angle = start+span*index/60
            r = radius*(1+wobble*math.sin(3*angle+phase))
            point = QPointF(math.cos(angle)*r, math.sin(angle)*r*squash)
            if index: path.lineTo(point)
            else: path.moveTo(point)
        return path

    def paintEvent(self, event):
        now = time.monotonic()
        phase = (now-self._started)*.58
        reveal = self.reveal
        success = now-self._success_at
        center = QPointF(self.width()/2, 62)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # A hint of light is always present, with no idle disk, icon or label.
        painter.save(); painter.translate(center); painter.rotate(-18)
        for index in range(3):
            radius = 24+index*6+reveal*17
            arc = self.arc(radius, .42+index*.07, phase*(1 if index != 1 else -.7)+index*2.1,
                           math.pi*(1.18+index*.15), phase+index)
            painter.setPen(QPen(self.color("primary" if index != 1 else "accent", 48+reveal*64), .9))
            painter.drawPath(arc)
        # Tiny highlights follow warped paths rather than blinking on/off.
        for index in range(8):
            angle = phase*(.65+index*.025)+index*2.399
            radius = 31+(index%3)*7+reveal*16
            point = QPointF(math.cos(angle)*radius, math.sin(angle)*radius*.57)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.color("primary" if index%3 else "accent", 50+reveal*110))
            painter.drawEllipse(point, .7+reveal*.45, .7+reveal*.45)
        painter.restore()

        if reveal <= .001:
            return
        painter.setOpacity(reveal)
        painter.drawPixmap(round(center.x()-72), round(center.y()-72), self.halo())
        # A soft local vignette keeps the core and caption legible over nodes.
        shadow = QRadialGradient(center, 64)
        shadow.setColorAt(0, self.color("background", 245))
        shadow.setColorAt(.58, self.color("background", 215))
        shadow.setColorAt(1, self.color("background", 0))
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(shadow)
        painter.drawEllipse(center, 64, 64)

        painter.save(); painter.translate(center); painter.rotate(-18)
        radius = 44+6*reveal
        # Back half of the accretion disk, partly occulted by the dark core.
        disk = self.arc(radius, .31, math.pi, math.pi, phase)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for width, alpha in ((9, 12), (4, 48), (1.25, 210)):
            painter.setPen(QPen(self.color("primary", alpha), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawPath(disk)
        core_radius = 19+4*reveal
        if 0 <= success < .85:
            core_radius *= 1+.08*math.sin(success/.85*math.pi)
        core = self.color("background").darker(280)
        painter.setPen(QPen(self.color("primary", 120), 1.1)); painter.setBrush(core)
        painter.drawEllipse(QPointF(0, 0), core_radius, core_radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        lens = self.arc(core_radius+3, 1., math.pi*.92, math.pi*1.22, phase, .014)
        painter.setPen(QPen(self.color("primary", 44), 5)); painter.drawPath(lens)
        painter.setPen(QPen(self.color("primary", 230), .85)); painter.drawPath(lens)
        # Front light bends up and over the event horizon.
        front = QPainterPath(QPointF(-radius, 0))
        front.cubicTo(-radius*.7, radius*.38, -core_radius*.95, radius*.28, -core_radius*.73, core_radius*.38)
        front.cubicTo(-core_radius*.45, -core_radius*.4, core_radius*.45, -core_radius*.4, core_radius*.73, core_radius*.38)
        front.cubicTo(core_radius*.95, radius*.28, radius*.7, radius*.38, radius, 0)
        for width, alpha in ((8, 14), (3.5, 65), (1.2, 240)):
            painter.setPen(QPen(self.color("primary", alpha), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawPath(front)
        painter.setPen(QPen(self.color("accent", 130), .9))
        painter.drawPath(self.arc(radius+5, .33, 0, math.pi, -phase))
        if self.dragging or 0 <= success < 1.:
            for index in range(10):
                progress = (phase*.7+index/10)%1 if self.dragging else min(1., success+index*.025)
                distance = 61*(1-progress)
                angle = phase*2+index*2.399+progress*2
                point = QPointF(math.cos(angle)*distance, math.sin(angle)*distance*.67)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(self.color("primary", 210*(1-progress)))
                painter.drawEllipse(point, 1.6, 1.6)
        painter.restore()

        # Caption appears with the core; there is no permanent toolbar button.
        font = QFont(self.config["font"], 10)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font); painter.setPen(self.color("text"))
        label = "Moved to Trash" if 0 <= success < 1.35 else "Trash"
        painter.drawText(QRectF(5, 104, self.width()-10, 20), Qt.AlignmentFlag.AlignCenter, label)
        painter.setFont(QFont(self.config["font"], 8)); painter.setPen(self.color("muted"))
        count = len(self.drop_paths)
        hint = f"Release {count} item{'s' if count != 1 else ''}" if self.dragging else "Drop files · click to open"
        painter.drawText(QRectF(2, 126, self.width()-4, 17), Qt.AlignmentFlag.AlignCenter, hint)
        if self.keyboard_focus:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(self.color("primary", 130), 1, Qt.PenStyle.DotLine))
            painter.drawRoundedRect(QRectF(6, 4, self.width()-12, self.height()-6), 22, 22)

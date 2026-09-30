"""Configurable pointer navigation and consistent file activation."""
import math
import os
import time

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QWidget

GESTURES = (
    ('Middle-button drag', 'middle'),
    ('Alt / Option + left-drag (trackpad)', 'alt_left'),
    ('Left-drag on empty canvas (trackpad)', 'left_canvas'),
    ('Right-button drag', 'right'),
)


def rotation_matches(graph, event, target):
    mode = graph.config.get('rotation_gesture', 'middle')
    button, modifiers = event.button(), event.modifiers()
    if mode == 'alt_left':
        return button == Qt.MouseButton.LeftButton and bool(modifiers & Qt.KeyboardModifier.AltModifier)
    if mode == 'left_canvas':
        return button == Qt.MouseButton.LeftButton and not target and not (
            modifiers & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
    if mode == 'right':
        return button == Qt.MouseButton.RightButton
    return button == Qt.MouseButton.MiddleButton


def begin_pointer(graph, event):
    position = event.position()
    target = graph.hit(position)
    rotation = rotation_matches(graph, event, target)
    # A remapped middle button pans instead. Right-drag continues to pan in
    # the trackpad modes, with the existing right-drag file action chooser.
    pan = event.button() == Qt.MouseButton.MiddleButton and not rotation
    if rotation or pan:
        graph.setFocus()
        graph.press = graph.last = QPointF(position)
        graph.moved = graph.dragging = graph.right_drag = False
        graph.press_path = ''
        graph._orbit_motion = ('rotate' if rotation else 'pan', event.button())
        graph._orbit_click = None
        graph.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()
        return True
    graph._orbit_motion = None
    # Some trackpad drivers deliver two clicks rather than a double-click.
    # Match the OS double-click interval and drag distance, not a fixed delay.
    selection_modifiers = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.MetaModifier | Qt.KeyboardModifier.AltModifier
    if event.button() == Qt.MouseButton.LeftButton and target and not event.modifiers() & selection_modifiers:
        now = time.monotonic()
        previous = getattr(graph, '_orbit_click', None)
        graph._orbit_click = (target, QPointF(position), now)
        if previous and previous[0] == target and now - previous[2] <= QApplication.doubleClickInterval() / 1000 and (
            position - previous[1]).manhattanLength() <= QApplication.startDragDistance():
            activate_node(graph, target, event)
            return True
    else:
        graph._orbit_click = None
    return False


def rotate(graph, delta):
    graph.yaw += delta.x() * .008 * (-1 if graph.config.get('invert_horizontal', False) else 1)
    graph.pitch = max(-1.48, min(1.48, graph.pitch + delta.y() * .008 * (1 if graph.config.get('invert_vertical', False) else -1)))
    graph.update()


def move_pointer(graph, event):
    motion = getattr(graph, '_orbit_motion', None)
    if motion and event.buttons() & motion[1]:
        delta = event.position() - graph.last
        if (event.position() - graph.press).manhattanLength() > QApplication.startDragDistance():
            graph.moved = True
        if motion[0] == 'rotate':
            rotate(graph, delta)
        else:
            graph.offset += delta
            graph.update()
        graph.last = event.position()
        event.accept()
        return True
    if event.buttons() and (event.position() - graph.press).manhattanLength() > QApplication.startDragDistance():
        graph._orbit_click = None
    return False


def end_pointer(graph, event):
    motion = getattr(graph, '_orbit_motion', None)
    if motion and event.button() == motion[1]:
        graph._orbit_motion = None
        graph.setCursor(Qt.CursorShape.ArrowCursor)
        if not graph.moved:
            if event.button() == Qt.MouseButton.RightButton:
                graph.context_requested.emit(graph.hit(event.position()), event.globalPosition().toPoint())
            elif event.button() == Qt.MouseButton.LeftButton and graph.config.get('rotation_gesture') == 'left_canvas':
                graph.set_selection(set())
        event.accept()
        return True
    return False


def activate_node(graph, path, event):
    now = time.monotonic()
    previous = getattr(graph, '_orbit_activated', None)
    graph._orbit_click = graph._orbit_motion = None
    graph.press_path = ''
    graph.dragging = False
    graph.ctrl = graph.shift = False
    graph.moved = True
    event.accept()
    # A native double-click may follow the second press already handled above.
    if previous and previous[0] == path and now - previous[1] < QApplication.doubleClickInterval() / 1000:
        return
    graph._orbit_activated = (path, now, QPointF(event.position()))
    graph.entered.emit(path)


def double_click(graph, event):
    if event.button() != Qt.MouseButton.LeftButton:
        return
    previous = getattr(graph, '_orbit_activated', None)
    if previous and time.monotonic() - previous[1] < QApplication.doubleClickInterval() / 1000 and (
        event.position() - previous[2]).manhattanLength() <= QApplication.startDragDistance():
        # Navigation may already have replaced the cloud after the second
        # press. Do not activate a different node now under the same pointer.
        event.accept()
        return
    target = graph.hit(event.position())
    if target and not rotation_matches(graph, event, target):
        activate_node(graph, target, event)


def trackpad_scroll(graph, event):
    if not graph.config.get('trackpad_scroll_rotate', False):
        return False
    pixel = event.pixelDelta()
    delta = QPointF(pixel) if not pixel.isNull() else QPointF(event.angleDelta()) * .25
    if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
        # Both pixel- and angle-based devices work for modified zoom.
        graph.zoom = max(.15, min(3.2, graph.zoom * math.exp(max(-2., min(2., delta.y() * .004)))))
        graph.update()
    else:
        rotate(graph, delta)
    event.accept()
    return True


def add_settings(dialog, form):
    from design import ComboBox
    combo = ComboBox()
    combo.setObjectName('rotationGesture')
    for label, value in GESTURES:
        combo.addItem(label, value)
    combo.setCurrentIndex(max(0, combo.findData(dialog.config.get('rotation_gesture', 'middle'))))
    combo.currentIndexChanged.connect(lambda _: dialog.set_value('rotation_gesture', combo.currentData()))
    form.addRow('Rotate the node cloud', combo)
    scroll = QCheckBox()
    scroll.setObjectName('trackpadScrollRotate')
    scroll.setChecked(dialog.config.get('trackpad_scroll_rotate', False))
    scroll.toggled.connect(lambda value: dialog.set_value('trackpad_scroll_rotate', value))
    form.addRow('Two-finger scroll rotates', scroll)
    note = QLabel('For trackpads, use Option/Alt + left-drag or drag empty canvas. Shift + drag still selects a rectangle. With scroll rotation enabled, hold Command/Ctrl while scrolling to zoom. Right-button rotation replaces right-drag file transfers; a right-click still opens the menu.')
    note.setWordWrap(True)
    note.setObjectName('muted')
    form.addRow(note)


def open_selection_key(window, obj, event):
    if event.type() not in (QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride):
        return False
    if event.key() not in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        return False
    if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier | Qt.KeyboardModifier.ShiftModifier):
        return False
    if QApplication.activeModalWidget():
        return False
    focus = QApplication.focusWidget()
    graph = window.graph
    selected_list = getattr(window, 'selected_list', None)
    if not isinstance(obj, QWidget) or QWidget.window(obj) is not window:
        return False
    if focus is not graph and not (selected_list and (focus is selected_list or selected_list.isAncestorOf(focus))):
        return False
    paths = sorted(graph.selected_paths)
    if not paths:
        return False
    event.accept()
    if event.type() == QEvent.Type.KeyPress and not event.isAutoRepeat():
        # Open every selected file; navigate once when folders are selected.
        files = [path for path in paths if path not in window.devices and not os.path.isdir(path)]
        folders = [path for path in paths if path not in files]
        for path in files + folders[:1]:
            window.open_node(path)
    return True


def update_hint(window):
    for label in window.findChildren(QLabel):
        if label.text().startswith('Middle drag to orbit') or label.property('orbitControlsHint'):
            label.setProperty('orbitControlsHint', True)
            mode = window.config.get('rotation_gesture', 'middle')
            caption = dict((value, text) for text, value in GESTURES).get(mode, GESTURES[0][0])
            label.setText(caption + ' to rotate\n' + ('Middle drag to pan' if mode == 'right' else 'Right drag on empty canvas to pan'))

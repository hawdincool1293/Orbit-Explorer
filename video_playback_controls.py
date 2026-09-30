"""Keep normal video playback compact; reveal editing controls on demand."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget


def sync(editor):
    progress = getattr(editor, 'playback_progress', None)
    if progress is None:
        return
    progress.setRange(0, round(editor.timeline.duration * 1000))
    progress.setEnabled(bool(editor.timeline.clips))
    if not progress.isSliderDown():
        progress.setValue(round(editor.timeline.playhead * 1000))
    if editor.panel.status.text().startswith('Non-destructive timeline') and not editor.edit_button.isChecked():
        editor.panel.status.setText('Video · drag the progress bar to seek')


def install(editor):
    if hasattr(editor, 'edit_tools'):
        return
    # Retain the original widgets, signal connections, timeline and player.
    # Only move editing UI into one collapsible container.
    def owner(layout, widget):
        if layout.indexOf(widget) >= 0:
            return layout
        for index in range(layout.count()):
            child = layout.itemAt(index).layout()
            found = owner(child, widget) if child else None
            if found is not None:
                return found
        return None

    controls = next((editor.box.itemAt(i).layout() for i in range(editor.box.count())
                     if editor.box.itemAt(i).layout() and owner(editor.box.itemAt(i).layout(), editor.volume) is not None), None)
    if controls is None:
        raise ValueError('The video playback control layout was not found.')
    # 0.6.2 uses a grid with volume/mute in a nested sound row. Move the
    # existing items into a playback row; retain every widget and connection.
    if not isinstance(controls, QHBoxLayout):
        index = next(i for i in range(editor.box.count()) if editor.box.itemAt(i).layout() is controls)
        editor.box.takeAt(index)
        original_controls = controls
        original_controls.setParent(None)
        controls = QHBoxLayout()
        while original_controls.count():
            item = original_controls.takeAt(0)
            if item.widget():
                controls.addWidget(item.widget())
            elif item.layout():
                item.layout().setParent(None)
                controls.addLayout(item.layout())
            else:
                controls.addItem(item)
        editor.box.insertLayout(index, controls)
    editor.edit_tools = QWidget(editor)
    editor.edit_tools.setObjectName('videoEditTools')
    tools = QVBoxLayout(editor.edit_tools)
    tools.setContentsMargins(0, 0, 0, 0)
    tools.setSpacing(5)
    actions = QHBoxLayout()
    tools.addLayout(actions)
    action_names = {'Add clip…', 'Split', 'Remove', 'Stitch', 'Undo', 'Export…'}
    for index in reversed(range(controls.count())):
        button = controls.itemAt(index).widget()
        if isinstance(button, QPushButton) and button.text() in action_names:
            controls.removeWidget(button)
            actions.insertWidget(0, button)
    actions.addStretch()
    # Locate the timeline widget and layouts containing trim/project controls.
    editing_layouts = []
    for index in range(editor.box.count()):
        item = editor.box.itemAt(index)
        widget, layout = item.widget(), item.layout()
        if isinstance(widget, QScrollArea) and widget.widget() is editor.timeline:
            editing_layouts.append((index, widget, None))
        elif layout and layout is not controls:
            direct = [layout.itemAt(i).widget() for i in range(layout.count())]
            if any(owner(layout, field) is not None for field in editor.fields) or any(
                isinstance(w, QPushButton) and w.text() in ('Save timeline…', 'Open timeline…') for w in direct):
                editing_layouts.append((index, None, layout))
    # Time display belongs to playback, even while the trim fields are hidden.
    for _, _, layout in editing_layouts:
        clock_owner = owner(layout, editor.clock) if layout else None
        if clock_owner is not None:
            clock_owner.removeWidget(editor.clock)
    for index, _, layout in reversed(editing_layouts):
        editor.box.takeAt(index)
        if layout:
            layout.setParent(None)
    for _, widget, layout in editing_layouts:
        if widget:
            tools.addWidget(widget)
        else:
            tools.addLayout(layout)
    editor.playback_progress = QSlider(Qt.Orientation.Horizontal)
    editor.playback_progress.setObjectName('videoPlaybackProgress')
    editor.playback_progress.setToolTip('Video progress · drag to seek')
    editor.playback_progress.sliderMoved.connect(lambda value: editor.seek(value / 1000))
    controls.insertWidget(1, editor.playback_progress, 1)
    controls.insertWidget(2, editor.clock)
    editor.edit_button = QPushButton('Edit video')
    editor.edit_button.setObjectName('videoEditToggle')
    editor.edit_button.setCheckable(True)
    editor.edit_button.setToolTip('Show trimming tools and the clip timeline')
    controls.addWidget(editor.edit_button)
    editor.box.addWidget(editor.edit_tools)
    editor.edit_tools.hide()

    def toggle(enabled):
        from panel_motion import reveal,dismiss
        if enabled:
            editor.edit_tools.show();reveal(editor.edit_tools,editor.config,'files')
        else:dismiss(editor.edit_tools,editor.config,'files',editor.edit_tools.hide)
        editor.edit_button.setText('Done editing' if enabled else 'Edit video')
        editor.edit_button.setToolTip('Hide editing tools; keep your edits' if enabled else 'Show trimming tools and the clip timeline')
        # Preserve errors and export/save messages instead of replacing them.
        if editor.panel.status.text().startswith(('Non-destructive timeline', 'Video ·')):
            editor.panel.status.setText('Non-destructive timeline · export creates a new file' if enabled else 'Video · drag the progress bar to seek')

    editor.edit_button.toggled.connect(toggle)
    editor.timeline.changed.connect(lambda: sync(editor))
    editor.timer.timeout.connect(lambda: sync(editor))
    sync(editor)

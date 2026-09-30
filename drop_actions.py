"""Explicit destination actions after a native file drag finishes."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from design import ui_icon, SurfaceDialog, DialogHandle


class DropActionDialog(SurfaceDialog):
    def __init__(self, paths, destination, config, parent=None):
        super().__init__(config,parent)
        self.action=None
        self.setWindowTitle('Dropped files')
        self.setModal(True); self.setMinimumWidth(430)
        layout=QVBoxLayout(self); layout.setContentsMargins(28,24,28,24); layout.setSpacing(12)
        title=QLabel(f"{len(paths)} item{'s' if len(paths)!=1 else ''} ready to place")
        title.setObjectName('dialogTitle'); layout.addWidget(title)
        subtitle=QLabel('Choose an action for '+(Path(destination).name or destination))
        subtitle.setTextFormat(Qt.TextFormat.PlainText); subtitle.setWordWrap(True); layout.addWidget(subtitle)
        location=QLabel(destination); location.setTextFormat(Qt.TextFormat.PlainText)
        location.setObjectName('muted'); location.setWordWrap(True); layout.addWidget(location)
        layout.addSpacing(8)
        self.buttons={}
        for action,title,detail in (('move','Move here','Relocate the originals'),
                                   ('copy','Copy here','Keep the originals in place'),
                                   ('link','Link here','Create symbolic links to the originals')):
            button=QPushButton(f'{title}\n{detail}'); button.setObjectName('dropAction')
            button.setAccessibleName(title); button.setAutoDefault(False)
            button.setIcon(ui_icon(action,config['colors']['primary'],22))
            button.clicked.connect(lambda checked=False,a=action:self.choose(a))
            layout.addWidget(button); self.buttons[action]=button
        row=QHBoxLayout(); row.addStretch()
        cancel=QPushButton('Cancel'); cancel.setObjectName('softButton'); cancel.setDefault(True)
        cancel.clicked.connect(self.reject); row.addWidget(cancel); layout.addLayout(row)
        self.buttons['cancel']=cancel; cancel.setFocus()

    def choose(self, action):
        if action not in ('move','copy','link'): self.reject(); return
        self.action=action; self.accept()

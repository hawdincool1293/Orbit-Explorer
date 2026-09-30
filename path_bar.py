"""Live path completion backed by Qt's asynchronous filesystem model."""
import os
from PySide6.QtCore import QAbstractListModel, QDir, QEvent, QModelIndex, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QCompleter, QFileSystemModel, QLineEdit, QListView, QStyle, QStyledItemDelegate
from design import PopupList,prepare_popup,ui_icon


class Suggestions(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent); self.items=[]
    def rowCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.items)
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.items): return None
        path, directory, icon=self.items[index.row()]
        if role==Qt.ItemDataRole.DisplayRole: return os.path.basename(path.rstrip(os.sep)) or path
        if role==Qt.ItemDataRole.UserRole: return path+(os.sep if directory and not path.endswith(os.sep) else '')
        if role==Qt.ItemDataRole.ToolTipRole: return path
        if role==Qt.ItemDataRole.DecorationRole: return icon
        if role==Qt.ItemDataRole.UserRole+1: return directory
    def replace(self, items):
        self.beginResetModel(); self.items=items; self.endResetModel()


class SuggestionDelegate(QStyledItemDelegate):
    def __init__(self, config, parent): super().__init__(parent); self.config=config
    def sizeHint(self, option, index): return QSize(360, 57)
    def paint(self, painter, option, index):
        painter.save(); painter.setRenderHint(painter.RenderHint.Antialiasing)
        r=QRectF(option.rect).adjusted(6, 3, -6, -3); colors=self.config['colors']
        if option.state & (QStyle.StateFlag.State_Selected|QStyle.StateFlag.State_MouseOver):
            color=QColor(colors['primary']); color.setAlpha(28)
            painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(color); painter.drawRoundedRect(r, 13, 13)
        icon=index.data(Qt.ItemDataRole.DecorationRole)
        if not icon or icon.isNull():icon=ui_icon('folder' if index.data(Qt.ItemDataRole.UserRole+1) else 'file',colors['primary'],22)
        if icon: icon.paint(painter, int(r.x()+12), int(r.y()+14), 22, 22)
        painter.setFont(QFont(self.config['font'], 10)); painter.setPen(QColor(colors['muted']))
        name=index.data() or ''; width=int(r.width()-62)
        painter.drawText(int(r.x()+48), int(r.y()+21), painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, width))
        painter.setFont(QFont(self.config['font'], 8)); painter.setPen(QColor(colors['muted']))
        path=index.data(Qt.ItemDataRole.ToolTipRole) or ''
        painter.drawText(int(r.x()+48), int(r.y()+40), painter.fontMetrics().elidedText(path, Qt.TextElideMode.ElideMiddle, width))
        painter.restore()


class PathBar(QLineEdit):
    def __init__(self, config, directory, parent=None):
        super().__init__(parent)
        self.config=config; self.directory=directory; self.parent_path=''; self._requested_text=''; self._closed=False
        self.candidate='';self.ghost_text=''
        self.setObjectName('addressInput'); self.setPlaceholderText('Go to a folder or file…')
        self.setAccessibleName('Location'); self.setClearButtonEnabled(True)
        self.fs=QFileSystemModel(self)
        self.fs.setOption(QFileSystemModel.Option.DontUseCustomDirectoryIcons, True)
        self.fs.setFilter(QDir.Filter.AllEntries|QDir.Filter.NoDotAndDotDot|QDir.Filter.Hidden|QDir.Filter.System)
        self.fs.sort(0, Qt.SortOrder.AscendingOrder)
        self.suggestions=Suggestions(self)
        self.completion=QCompleter(self.suggestions, self)
        self.completion.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self.completion.setCompletionRole(Qt.ItemDataRole.UserRole)
        self.completion.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completion.setMaxVisibleItems(7)
        popup=PopupList(); popup.setObjectName('pathSuggestions')
        popup.setUniformItemSizes(True); popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        popup.setSpacing(0); popup.setMouseTracking(True)
        # Do not call QLineEdit.setCompleter: its highlighted signal overwrites
        # the user's text while merely browsing the popup.
        self.completion.setPopup(popup); self.completion.setWidget(self)
        # setPopup installs Qt's compact completion delegate. Replace it only
        # afterwards so icons, full paths, and roomy rows survive.
        popup.setItemDelegate(SuggestionDelegate(config, popup))
        self.apply_theme()
        popup.installEventFilter(self); self.installEventFilter(self)
        self.debounce=QTimer(self); self.debounce.setSingleShot(True); self.debounce.setInterval(55)
        self.debounce.timeout.connect(self.refresh)
        self.textEdited.connect(self.edited)
        self.completion.activated[str].connect(self.stage_suggestion)
        popup.selectionModel().currentChanged.connect(lambda index,previous:self.stage_suggestion(index.data(Qt.ItemDataRole.UserRole) or ''))
        self.cursorPositionChanged.connect(lambda *_:self.update_ghost())
        self.fs.directoryLoaded.connect(self.loaded)
        self.fs.rowsInserted.connect(lambda *_: self.schedule_refresh())

    def apply_theme(self):
        # Completion popups are top-level windows and do not reliably inherit
        # the main window's stylesheet on all Qt platform plugins.
        prepare_popup(self.completion.popup(),self.config['colors']);self.update()

    def edited(self, text):
        self._requested_text=text
        self.candidate='';self.ghost_text='';self.update()
        self.suggestions.replace([]); self.completion.popup().hide()
        self.debounce.start()

    def schedule_refresh(self):
        if not self._closed and self.hasFocus() and self.text()==self._requested_text:
            self.debounce.start()

    def loaded(self, path):
        if os.path.normpath(path)==self.parent_path: self.schedule_refresh()

    def set_location(self, path):
        self.debounce.stop(); self._requested_text=''; self.parent_path=''
        self.candidate='';self.ghost_text=''
        self.completion.popup().hide(); self.suggestions.replace([]); self.setText(path)

    def refresh(self):
        text=self.text()
        if self._closed or not self.hasFocus() or text!=self._requested_text or self.cursorPosition()!=len(text): return
        if not text or text.startswith('drive:'): self.completion.popup().hide(); return
        expanded=os.path.expanduser(text)
        if not os.path.isabs(expanded): expanded=os.path.join(self.directory(), expanded)
        parent, fragment=os.path.split(expanded)
        # A slash is an explicit complete directory, not permission to insert
        # its first child. Wait until the user types the next component.
        if not fragment:self.dismiss();return
        parent=os.path.normpath(parent or os.sep)
        if parent!=self.parent_path:
            self.parent_path=parent
            self.fs.setRootPath(parent)
        root=self.fs.index(parent)
        if not root.isValid() or not self.fs.isDir(root):
            self.suggestions.replace([]); self.completion.popup().hide(); return
        self.fs.fetchMore(root)
        if not self.fs.rowCount(root): return
        first=self.fs.index(0, 0, root)
        # Native Qt matching, bounded to immediate children; no recursive walk
        # or second search index. Exact/prefix matches precede substrings.
        indices=self.fs.match(first, Qt.ItemDataRole.DisplayRole, fragment, 96,
                              Qt.MatchFlag.MatchStartsWith|Qt.MatchFlag.MatchWrap)
        if len(indices)<12 and fragment:
            indices+=self.fs.match(first, Qt.ItemDataRole.DisplayRole, fragment, 48,
                                   Qt.MatchFlag.MatchContains|Qt.MatchFlag.MatchWrap)
        favorites={os.path.normpath(f['path']) for f in self.config['favorites']}
        recents={os.path.normpath(path):i for i,path in enumerate(self.config['recent_folders'])}
        # Include known recent/pinned siblings even beyond the native match cap.
        for path in favorites|recents.keys():
            if os.path.dirname(path)==parent and fragment.casefold() in os.path.basename(path).casefold():
                index=self.fs.index(path)
                if index.isValid(): indices.append(index)
        found={}; query=fragment.casefold()
        for index in indices:
            path=self.fs.filePath(index); name=self.fs.fileName(index); folded=name.casefold()
            if query not in folded or path in found: continue
            if name.startswith('.') and not (fragment.startswith('.') or self.config['show_hidden']): continue
            directory=self.fs.isDir(index)
            rank=(0 if folded==query else 1 if folded.startswith(query) else 2,
                  not directory, path not in favorites, recents.get(path, 999999), folded, name)
            found[path]=(rank, directory, self.fs.fileIcon(index))
        items=[(path,data[1],data[2]) for path,data in sorted(found.items(), key=lambda pair:pair[1][0])[:12]]
        self.suggestions.replace(items)
        if not items: self.completion.popup().hide(); return
        self.completion.setCompletionPrefix('')
        popup=self.completion.popup(); popup.setMinimumWidth(self.width())
        self.completion.complete(self.rect())
        popup.setCurrentIndex(self.completion.completionModel().index(0,0))

    def accept_completion(self, value):
        self.debounce.stop(); self._requested_text=''
        self.candidate='';self.ghost_text=''
        self.setText(value); self.setModified(True); self.setCursorPosition(len(value)); self.completion.popup().hide()

    def stage_suggestion(self,value):
        self.candidate=value;self.update_ghost()

    def update_ghost(self):
        self.ghost_text=''
        if self.candidate and self.text()==self._requested_text and self.cursorPosition()==len(self.text()) and not self.hasSelectedText():
            prefix=self.text()[:self.text().rfind(os.sep)+1]
            suggested=prefix+os.path.basename(self.candidate.rstrip(os.sep))+(os.sep if self.candidate.endswith(os.sep) else '')
            if suggested.casefold().startswith(self.text().casefold()):self.ghost_text=suggested[len(self.text()):]
        self.update()

    def dismiss(self):
        self.debounce.stop();self._requested_text='';self.candidate='';self.ghost_text=''
        self.completion.popup().hide();self.update()

    def paintEvent(self,event):
        super().paintEvent(event)
        if not self.ghost_text or not self.hasFocus():return
        painter=QPainter(self);painter.setFont(self.font())
        color=QColor(self.config['colors']['muted']);color.setAlpha(165);painter.setPen(color)
        cursor=self.cursorRect();x=cursor.right()+1
        painter.setClipRect(self.rect().adjusted(x,2,-32,-2))
        painter.drawText(x,round((self.height()-painter.fontMetrics().height())/2)+painter.fontMetrics().ascent(),self.ghost_text)

    def focusOutEvent(self,event):
        if event.reason()!=Qt.FocusReason.PopupFocusReason:self.dismiss()
        super().focusOutEvent(event)

    def eventFilter(self, obj, event):
        if obj in (self, self.completion.popup()) and event.type()==QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.candidate and self.text()==self._requested_text and self.cursorPosition()==len(self.text()):
                self.accept_completion(self.candidate);event.accept();return True
            if event.key() in (Qt.Key.Key_Tab,Qt.Key.Key_Backtab) and self.completion.popup().isVisible():
                self.dismiss();self.focusNextPrevChild(event.key()==Qt.Key.Key_Tab);event.accept();return True
            if event.key()==Qt.Key.Key_Escape:
                self.dismiss();event.accept();return True
        return super().eventFilter(obj,event)

    def stop(self):
        self._closed=True;self.dismiss()

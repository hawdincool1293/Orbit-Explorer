"""Native, independently resizable file panels and their source-node tethers."""
import os,mimetypes
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import Qt,Signal,QObject,QUrl,QTimer,QPoint,QRectF,QSize
from PySide6.QtGui import QPainter,QColor,QPen,QImageReader,QPixmap,QMovie,QTextDocument,QKeySequence,QShortcut
from PySide6.QtWidgets import (QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QPlainTextEdit,
    QFileDialog,QMessageBox,QLineEdit,QTreeWidget,QTreeWidgetItem,QSlider,QSpinBox)
from PySide6.QtGui import QDesktopServices
from panes import LiveSplitter
from design import ui_icon,Panel
from file_tools import read_text,save_text,archive_contents,extract_archive

def viewer_kind(path):
    suffix=Path(path).suffix.lower();mime=mimetypes.guess_type(path)[0] or ''
    if suffix=='.pdf':return 'pdf'
    if suffix=='.gif':return 'gif'
    if mime.startswith('image/'):return 'image'
    if mime.startswith('video/'):return 'video'
    if suffix in ('.zip','.tar','.tgz','.tbz2','.txz') or str(path).lower().endswith(('.tar.gz','.tar.bz2','.tar.xz')):return 'archive'
    if mime.startswith('text/') or suffix in ('.json','.jsonl','.yaml','.yml','.toml','.ini','.conf','.cfg','.md','.log','.py','.js','.ts','.tsx','.jsx','.rs','.sh','.xml','.svg','.csv') or Path(path).name.lower() in ('readme','license','makefile','dockerfile'):return 'text'
    return ''

def icon_button(name,tip,config,callback):
    button=QPushButton();button.setProperty('role','icon');button.setFixedSize(32,32)
    button.setIcon(ui_icon(name,config['colors']['text'],19));button.setIconSize(QSize(19,19))
    button.setToolTip(tip);button.setAccessibleName(tip);button.clicked.connect(callback);return button

class JobBus(QObject):result=Signal(object,object,str)

class ImageCanvas(QWidget):
    def __init__(self,parent=None):super().__init__(parent);self.pixmap=QPixmap();self.setMinimumSize(100,80)
    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('#08090e'))
        if self.pixmap.isNull():return
        size=self.pixmap.size().scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio)
        target=QRectF((self.width()-size.width())/2,(self.height()-size.height())/2,size.width(),size.height())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform);painter.drawPixmap(target,self.pixmap,QRectF(self.pixmap.rect()))

class FilePanel(Panel):
    def __init__(self,path,kind,hub):
        super().__init__();self.path=path;self.kind=kind;self.hub=hub;self.config=hub.config;self.closed=False;self.busy=0
        self.player=None;self.movie=None;self.original=None;self.text=None;self.editor=None;self.close_after_save=None;self.setObjectName('panel');self.setMinimumSize(260,180)
        self.layout=QVBoxLayout(self);self.layout.setContentsMargins(12,8,12,10);self.layout.setSpacing(6)
        header=QHBoxLayout();self.title=QLabel(Path(path).name);self.title.setTextFormat(Qt.TextFormat.PlainText);self.title.setToolTip(path)
        self.title.setMinimumWidth(40);header.addWidget(self.title,1)
        header.addWidget(icon_button('fit','Locate source node',self.config,lambda:hub.locate.emit(self.path)))
        header.addWidget(icon_button('move','Open externally',self.config,lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(self.path))))
        header.addWidget(icon_button('close','Close file',self.config,lambda:hub.close_panel(self)))
        self.layout.addLayout(header)
        self.status=QLabel('Loading…');self.status.setObjectName('muted');self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText)
        if kind=='text':self.build_text()
        elif kind=='video':self.build_video()
        elif kind in ('image','gif'):self.build_image()
        elif kind=='archive':self.build_archive()
        elif kind=='pdf':self.build_pdf()
        self.layout.addWidget(self.status)

    def build_text(self):
        bar=QHBoxLayout();self.save_button=QPushButton('Save');self.save_button.clicked.connect(self.save);bar.addWidget(self.save_button)
        as_button=QPushButton('Save as…');as_button.clicked.connect(self.save_as);bar.addWidget(as_button)
        find=QLineEdit();find.setPlaceholderText('Find text · Enter');bar.addWidget(find,1)
        find.returnPressed.connect(lambda:self.find_text(find.text()));self.layout.addLayout(bar)
        self.text=QPlainTextEdit();self.text.setReadOnly(True);self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.layout.addWidget(self.text,1)
        self.text.document().modificationChanged.connect(lambda modified:self.title.setText(Path(self.path).name+(' •' if modified else '')))
        self.save_shortcut=QShortcut(QKeySequence.StandardKey.Save,self);self.save_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);self.save_shortcut.activated.connect(self.save)
        def ready(data):
            self.original=data;self.text.setPlainText(data['text']);self.text.setReadOnly(False);self.text.document().setModified(False)
            self.status.setText(f'{data["encoding"].upper()} · {"CRLF" if data["newline"]==chr(13)+chr(10) else "LF"}')
        self.hub.run(self,lambda:read_text(self.path),ready)
    def find_text(self,value):
        if not value:return
        if not self.text.find(value):
            cursor=self.text.textCursor();cursor.movePosition(cursor.MoveOperation.Start);self.text.setTextCursor(cursor);self.text.find(value)
    def save(self,checked=False):
        if not self.original or self.busy:return False
        snapshot=self.text.toPlainText();self.text.setReadOnly(True)
        def ready(data):
            self.original=data;self.text.document().setModified(False);self.text.setReadOnly(False);self.status.setText('Saved');self.hub.changed.emit()
            retry=self.close_after_save;self.close_after_save=None
            if retry:QTimer.singleShot(0,retry)
        self.hub.run(self,lambda:save_text(self.path,snapshot,self.original),ready);return True
    def save_as(self):
        if not self.original or self.busy:return
        path,_=QFileDialog.getSaveFileName(self,'Save a copy',self.path)
        if not path:return
        # This copy action never silently replaces an existing file.
        if os.path.lexists(path):self.status.setText('Choose a new filename; existing files are not replaced by Save as.');return
        data=self.text.toPlainText().replace('\n',self.original['newline']).encode(self.original['encoding'])
        def work():
            with open(path,'xb') as stream:stream.write(data)
            return path
        self.hub.run(self,work,lambda p:(self.status.setText('Copy saved to '+p),self.hub.changed.emit()))
    def build_image(self):
        if self.kind=='image':
            from image_editor import ImageEditor
            self.editor=ImageEditor(self);self.canvas=self.editor.canvas;self.layout.addWidget(self.editor,1);return
        self.canvas=ImageCanvas();self.layout.addWidget(self.canvas,1)
        if self.kind=='gif':
            self.movie=QMovie(self.path);self.movie.setCacheMode(QMovie.CacheMode.CacheNone)
            self.movie.frameChanged.connect(lambda _:self.image_frame(self.movie.currentPixmap()))
            self.movie.error.connect(lambda _:self.status.setText(self.movie.lastErrorString()))
            controls=QHBoxLayout();pause=QPushButton('Pause / play');pause.clicked.connect(lambda:self.movie.setPaused(self.movie.state()==QMovie.MovieState.Running));controls.addWidget(pause)
            speed=QSpinBox();speed.setRange(25,400);speed.setValue(100);speed.setSuffix('%');speed.valueChanged.connect(self.movie.setSpeed);controls.addWidget(speed);controls.addStretch();self.layout.addLayout(controls)
            self.movie.start();self.status.setText('Animated GIF')
        else:
            def read():
                reader=QImageReader(self.path);reader.setAutoTransform(True);size=reader.size()
                if size.isValid() and max(size.width(),size.height())>4096:
                    reader.setScaledSize(size.scaled(QSize(4096,4096),Qt.AspectRatioMode.KeepAspectRatio))
                image=reader.read()
                if image.isNull():raise ValueError(reader.errorString())
                return image
            self.hub.run(self,read,lambda image:(self.image_frame(QPixmap.fromImage(image)),self.status.setText(f'{image.width()} × {image.height()} preview')))
    def image_frame(self,pixmap):self.canvas.pixmap=pixmap;self.canvas.update()
    def build_video(self):
        from video_editor import VideoEditor
        self.editor=VideoEditor(self);self.player=self.editor.player;self.layout.addWidget(self.editor,1)
    def build_pdf(self):
        try:self.build_qt_pdf()
        except ImportError as exc:
            from pdf_fallback import PdfFallback
            self.pdf_fallback=PdfFallback(self,str(exc));self.layout.addWidget(self.pdf_fallback,1)
    def build_qt_pdf(self):
        from PySide6.QtPdf import QPdfDocument
        from PySide6.QtPdfWidgets import QPdfView
        self.pdf=QPdfDocument(self);self.pdf_view=QPdfView(self);self.pdf_view.setDocument(self.pdf)
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage);self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.layout.addWidget(self.pdf_view,1)
        error=self.pdf.load(self.path)
        self.status.setText(f'{self.pdf.pageCount()} pages' if error==QPdfDocument.Error.None_ else f'PDF could not be opened: {error.name}')
    def build_archive(self):
        self.entries=QTreeWidget();self.entries.setHeaderLabels(['Name','Size']);self.entries.setRootIsDecorated(False);self.entries.setUniformRowHeights(True);self.layout.addWidget(self.entries,1)
        extract=QPushButton('Extract to…');extract.clicked.connect(self.extract);self.layout.addWidget(extract)
        def ready(rows):
            self.entries.setUpdatesEnabled(False)
            for name,size,directory in rows[:1000]:QTreeWidgetItem(self.entries,[name,'Folder' if directory else f'{size:,} B'])
            self.entries.setUpdatesEnabled(True);self.entries.resizeColumnToContents(0)
            self.status.setText(f'{len(rows):,} entries · {sum(r[1] for r in rows):,} bytes'+(' · first 1,000 displayed' if len(rows)>1000 else ''))
        self.hub.run(self,lambda:archive_contents(self.path),ready)
    def extract(self):
        if self.busy:return
        parent=QFileDialog.getExistingDirectory(self,'Extract into a new folder',str(Path(self.path).parent))
        if parent:self.extract_to(parent)
    def extract_to(self,parent):
        self.status.setText('Extracting…')
        self.hub.run(self,lambda:extract_archive(self.path,parent,lambda:self.closed),lambda output:(self.status.setText('Extracted to '+output),self.hub.changed.emit()))
    def can_close(self,retry=None):
        if self.busy:self.status.setText('Please wait for the current read, save or extraction to finish.');return False
        if self.editor and not self.editor.can_close():return False
        if self.text and self.text.document().isModified():
            choice=QMessageBox.question(self,'Unsaved edits',f'Save changes to {Path(self.path).name}?',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
            if choice==QMessageBox.StandardButton.Save:self.close_after_save=retry;self.save();return False
            if choice==QMessageBox.StandardButton.Cancel:return False
        return True
    def stop(self):
        self.closed=True
        if self.editor:self.editor.stop()
        if self.player:self.player.stop()
        if self.movie:self.movie.stop()

class FileHub(QFrame):
    locate=Signal(str);changed=Signal();panels_changed=Signal()
    def __init__(self,config,parent=None):
        super().__init__(parent);self.config=config;self.panels={};self.closing=False;self.splitters=[]
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='orbit-file');self.bus=JobBus(self);self.bus.result.connect(self.completed)
        self.box=QVBoxLayout(self);self.box.setContentsMargins(0,0,0,0);self.splitter=LiveSplitter();self.box.addWidget(self.splitter);self.hide()
    def run(self,panel,work,done):
        panel.busy+=1
        def job():
            try:value=work();error=''
            except Exception as exc:value=None;error=str(exc)
            if not self.closing:self.bus.result.emit((panel,done),value,error)
        self.pool.submit(job)
    def completed(self,context,value,error):
        panel,done=context;panel.busy-=1
        if panel.closed:return
        if error:
            panel.close_after_save=None;panel.status.setText(error)
            if panel.text and panel.original:panel.text.setReadOnly(False)
        else:done(value)
    def open_file(self,path):
        path=os.path.abspath(path);kind=viewer_kind(path)
        if not kind:return False
        from panel_motion import finish,reveal
        if path in self.panels:
            panel=self.panels[path]
            if getattr(panel,'closing',False):
                panel.closing=False;reveal(panel.closing_target,self.config,'files')
            panel.setFocus();self.show();return True
        controller=getattr(self,'_entrance_controller',None)
        if controller and controller.exiting:finish(self)
        first=not self.panels;panel=FilePanel(path,kind,self)
        if not self.panels:self.splitter.addWidget(panel)
        else:
            old=max(self.panels.values(),key=lambda p:p.width()*p.height());parent=old.parentWidget()
            orientation=Qt.Orientation.Horizontal if old.width()>max(520,old.height()*1.3) else Qt.Orientation.Vertical
            # Keep Python ownership of replacement splitters, as ViewWorkspace does.
            # PySide's replaceWidget binding otherwise destroys the local wrapper
            # and all its file panels when this method returns.
            split=LiveSplitter(orientation);self.splitters.append(split)
            sizes=parent.sizes();parent.replaceWidget(parent.indexOf(old),split);parent.setSizes(sizes)
            split.addWidget(old);split.addWidget(panel);split.setSizes([400,400])
        self.panels[path]=panel;self.show();self.panels_changed.emit()
        from panel_motion import later
        later(self if first else panel,self.config,'files');return True
    def close_panel(self,panel):
        if panel.path not in self.panels or getattr(panel,'closing',False):return
        if not panel.can_close(lambda:self.close_panel(panel)):return
        from panel_motion import dismiss
        panel.closing=True;panel.closing_target=self if len(self.panels)==1 else panel
        dismiss(panel.closing_target,self.config,'files',lambda:self.remove_panel(panel))
    def remove_panel(self,panel):
        if panel.path not in self.panels:return
        panel.stop();self.panels.pop(panel.path,None);parent=panel.parentWidget()
        if parent.count()==2:
            sibling=parent.widget(1-parent.indexOf(panel));grand=parent.parentWidget();sibling.setParent(None)
            sizes=grand.sizes();grand.replaceWidget(grand.indexOf(parent),sibling);grand.setSizes(sizes)
            self.splitters.remove(parent);parent.setParent(None);parent.deleteLater()
        else:panel.setParent(None);panel.deleteLater()
        if not self.panels:self.hide()
        self.panels_changed.emit()
    def can_close(self):return all(p.can_close(lambda:self.window().close()) for p in self.panels.values())
    def snapshot(self):
        def record(widget):
            if isinstance(widget,FilePanel):return {'path':widget.path}
            return {'orientation':'h' if widget.orientation()==Qt.Orientation.Horizontal else 'v','sizes':widget.stored_sizes(),
                    'children':[record(widget.widget(i)) for i in range(widget.count())]}
        return record(self.splitter) if self.panels else {}
    def restore(self,data):
        if not isinstance(data,dict) or not data:return
        new_splits=[];sizes=[];count=0
        def build(item,depth=0):
            nonlocal count
            if not isinstance(item,dict) or depth>8 or count>=12:return None
            if 'path' in item:
                path=item['path']
                if not isinstance(path,str) or not os.path.isfile(path) or not viewer_kind(path):return None
                count+=1
                try:panel=FilePanel(path,viewer_kind(path),self)
                except Exception:return None
                self.panels[path]=panel;return panel
            children=[build(c,depth+1) for c in item.get('children',[])[:2]];children=[c for c in children if c]
            if not children:return None
            split=LiveSplitter(Qt.Orientation.Horizontal if item.get('orientation')=='h' else Qt.Orientation.Vertical);new_splits.append(split)
            for child in children:split.addWidget(child)
            sizes.append((split,item.get('sizes',[])));return split
        root=build(data)
        if root is None:return
        if isinstance(root,FilePanel):
            wrapper=LiveSplitter();wrapper.addWidget(root);root=wrapper;new_splits.append(root)
        old=self.splitter;self.box.replaceWidget(old,root);old.setParent(None);old.deleteLater();self.splitter=root;self.splitters=[s for s in new_splits if s is not root]
        self.show()
        for splitter,values in sizes:QTimer.singleShot(0,lambda s=splitter,v=values:s.restore_sizes(v))
        self.panels_changed.emit()
    def shutdown(self):
        self.closing=True
        for panel in self.panels.values():panel.stop()
        self.pool.shutdown(wait=False,cancel_futures=True)

class FileConnections(QWidget):
    """Source tethers; offscreen files retain a named proxy orb at the cloud edge."""
    def __init__(self,parent,workspace,hub,config):
        super().__init__(parent);self.workspace=workspace;self.hub=hub;self.config=config;self.audio=None;self.source='';self.segments=[]
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents);self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.timer=QTimer(self);self.timer.setInterval(33);self.timer.timeout.connect(self.refresh);self.hide()
    def set_source(self,path):self.source=path;self.refresh()
    def refresh(self):
        if not self.parentWidget().isVisible():return
        sources=[(source,panel) for p,panel in self.hub.panels.items() if panel.isVisible() for source in (getattr(panel.editor,'sources',None) or [p])]
        if self.source and self.audio and self.audio.isVisible():sources.append((self.source,self.audio))
        if not sources:self.hide();self.timer.stop();self.segments=[];return
        self.setGeometry(self.parentWidget().rect());self.show();self.raise_();segments=[]
        for i,(path,panel) in enumerate(sources):
            candidates=[t for t in self.workspace.tiles if path in t.graph.projected and QRectF(t.graph.rect()).intersects(t.graph.projected[path][0])]
            proxy=not candidates;tile=self.workspace.active if self.workspace.active in candidates or proxy else candidates[0];g=tile.graph
            point=QPoint(g.width()-28,100+i*54) if proxy else g.projected[path][0].center().toPoint()
            if not proxy and g.live_resizing and g._layer:
                point=QPoint(round(point.x()*g.width()/g._layer.width()),round(point.y()*g.height()/g._layer.height()))
            point=g.mapTo(self.parentWidget(),point);end=panel.mapTo(self.parentWidget(),QPoint(min(70,panel.width()//2),4))
            segments.append((point,end,path,proxy))
        if segments!=self.segments:self.segments=segments;self.update()
        if not self.timer.isActive():self.timer.start()
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors=self.config['colors'];color=QColor(colors['primary']);color.setAlpha(185);painter.setPen(QPen(color,1.5,Qt.PenStyle.DotLine))
        for point,end,path,proxy in self.segments:
            painter.drawLine(point,end)
            if proxy:
                painter.setBrush(QColor(colors['panel']));painter.drawEllipse(point,11,11)
                painter.drawText(point+QPoint(-150,-16),painter.fontMetrics().elidedText(Path(path).name,Qt.TextElideMode.ElideMiddle,155))

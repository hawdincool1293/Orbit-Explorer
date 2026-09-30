"""Type-aware, explicit conversion using installed Qt writers and FFmpeg."""
import os,mimetypes,tempfile,tarfile,shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import Signal,QObject
from PySide6.QtGui import QTextDocument,QPdfWriter
from PySide6.QtWidgets import QVBoxLayout,QFormLayout,QLabel,QPushButton,QProgressBar,QFileDialog,QHBoxLayout
from design import SurfaceDialog,ComboBox,SpinBox
from media_tools import video_formats,audio_formats,conversion_args
from image_editor import image_formats,read_image,write_image
from file_tools import read_text,extract_archive,compress_zip
from export_job import ExportJob

def options_for(path):
    from viewers import viewer_kind
    kind=viewer_kind(path);mime=mimetypes.guess_type(path)[0] or ''
    if kind=='video':return 'media',video_formats()+audio_formats()
    if mime.startswith('audio/'):return 'media',audio_formats()
    if kind in ('image','gif'):return 'image',image_formats()
    if kind=='archive':return 'archive',['zip','tar','tar.gz','tar.bz2','tar.xz']
    if Path(path).suffix.lower() in ('.txt','.md','.markdown','.html','.htm'):return 'document',['txt','md','html','pdf']
    return '',[]

def convert_document(path,target,fmt):
    data=read_text(path)['text'];document=QTextDocument();suffix=Path(path).suffix.lower()
    if suffix in ('.html','.htm'):document.setHtml(data)
    elif suffix in ('.md','.markdown'):document.setMarkdown(data)
    else:document.setPlainText(data)
    if fmt=='pdf':
        fd,temp=tempfile.mkstemp(prefix='.orbit-pdf-',suffix='.pdf',dir=Path(target).parent);os.close(fd)
        try:
            writer=QPdfWriter(temp);document.print_(writer);del writer;os.link(temp,target)
        finally:Path(temp).unlink(missing_ok=True)
    else:
        text=document.toHtml() if fmt=='html' else document.toMarkdown() if fmt=='md' else document.toPlainText()
        with open(target,'x',encoding='utf8') as output:output.write(text)
    return str(target)

def convert_archive(path,target,fmt):
    target=Path(target)
    if target.exists():raise FileExistsError('Choose a new filename.')
    with tempfile.TemporaryDirectory(prefix='.orbit-convert-',dir=target.parent) as temp:
        content=Path(extract_archive(path,temp));items=list(content.iterdir())
        if fmt=='zip':compress_zip([str(p) for p in items],target)
        else:
            mode={'tar':'w','tar.gz':'w:gz','tar.bz2':'w:bz2','tar.xz':'w:xz'}[fmt];output=Path(temp)/'output.tar'
            with tarfile.open(output,mode) as archive:
                for item in items:archive.add(item,arcname=item.name)
            os.link(output,target)
    return str(target)

class ConvertBus(QObject):done=Signal(str,str)

class ConversionDialog(SurfaceDialog):
    converted=Signal()
    def __init__(self,path,config,parent):
        super().__init__(config,parent);self.path=path;self.busy=False;self.job=None;self.pool=ThreadPoolExecutor(max_workers=1);self.bus=ConvertBus(self);self.bus.done.connect(self.completed)
        self.kind,formats=options_for(path);self.setWindowTitle('Convert '+Path(path).name);self.resize(460,310)
        box=QVBoxLayout(self);form=QFormLayout();box.addLayout(form);self.format=ComboBox();self.format.addItems(formats);form.addRow('Output format',self.format)
        self.quality=SpinBox();self.quality.setRange(1,100);self.quality.setValue(85)
        if self.kind=='image':form.addRow('Image quality',self.quality)
        self.note=QLabel('Export a new file; the original is never changed.' if formats else 'No compatible converter for this file type. Supported: images, audio, video, ZIP/TAR, TXT/Markdown/HTML documents.');self.note.setWordWrap(True);box.addWidget(self.note)
        if Path(path).suffix.lower()=='.gif':self.note.setText('Image conversion exports the first GIF frame. Use video export for animation.')
        self.progress=QProgressBar();box.addWidget(self.progress);row=QHBoxLayout();box.addLayout(row)
        self.go=QPushButton('Convert to…');self.go.clicked.connect(self.convert);self.go.setEnabled(bool(formats));row.addWidget(self.go)
        self.cancel=QPushButton('Close');self.cancel.clicked.connect(self.reject);row.addWidget(self.cancel)
    def convert(self):
        if self.busy:return
        fmt=self.format.currentText();target,_=QFileDialog.getSaveFileName(self,'Converted file',str(Path(self.path).with_name(Path(self.path).stem+' converted.'+fmt)),f'{fmt.upper()} (*.{fmt})')
        if not target:return
        if not target.lower().endswith('.'+fmt):target+='.'+fmt
        if os.path.lexists(target):self.note.setText('Choose a new filename. Existing files are never replaced.');return
        self.busy=True;self.go.setEnabled(False);self.note.setText('Converting…')
        if self.kind=='media':
            self.job=ExportJob(self);self.job.progress.connect(lambda v:self.progress.setValue(round(v)));self.job.finished.connect(self.completed)
            try:self.job.start(conversion_args(self.path,fmt),target)
            except Exception as exc:self.completed('',str(exc))
            self.cancel.setText('Cancel conversion');return
        quality=self.quality.value()
        def work():
            try:
                if self.kind=='image':write_image(read_image(self.path),target,fmt,quality)
                elif self.kind=='document':convert_document(self.path,target,fmt)
                elif self.kind=='archive':convert_archive(self.path,target,fmt)
                self.bus.done.emit(target,'')
            except Exception as exc:self.bus.done.emit('',str(exc))
        self.pool.submit(work)
    def completed(self,path,error):
        self.busy=False;self.job=None;self.go.setEnabled(True);self.cancel.setText('Close');self.note.setText(error or 'Saved '+path)
        if path:self.progress.setValue(100);self.converted.emit()
    def reject(self):
        if self.busy:
            if self.job:self.job.cancel()
            return
        self.pool.shutdown(wait=False);super().reject()
    def closeEvent(self,event):
        if self.busy:
            if self.job:self.job.cancel()
            event.ignore()
        else:self.pool.shutdown(wait=False);super().closeEvent(event)

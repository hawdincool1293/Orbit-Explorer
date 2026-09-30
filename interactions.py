"""Native file drags and a cancelable, three-blink spring-open controller."""
import os
from PySide6.QtCore import QObject, Signal, QTimer, QMimeData, QUrl, Qt, QPoint
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QFont

INTERNAL_MIME = 'application/x-orbit-files'

def file_mime(paths):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(os.path.abspath(p)) for p in paths])
    mime.setData(INTERNAL_MIME, b'1')
    return mime

def mime_paths(mime):
    return [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]

def drag_pixmap(paths, config):
    pix = QPixmap(160,112); pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(config['colors']['primary']),1.5))
    p.setBrush(QColor(config['colors']['panel']))
    for i in range(min(12,len(paths))):
        p.drawEllipse(QPoint(22+(i%4)*25,32+(i//4)*23),11,11)
    p.setFont(QFont(config['font'],9));p.setPen(QColor(config['colors']['text']))
    p.drawText(10,15,f'{len(paths)} selected');p.end()
    return pix

class SpringOpen(QObject):
    """600ms dwell, then three 300ms blinks; open at exactly 1.5 seconds.

    Leaving at any phase resets the machine, including after a previous open.
    Native drag events, rather than global cursor polling, drive this on Wayland.
    """
    pulse = Signal(str,bool)
    opened = Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.path='';self.phase=-1;self.finished=False
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.advance)
    def hover(self,path):
        if path==self.path:return
        self.cancel()
        if path:
            self.path=path;self.phase=-1;self.timer.start(600)
    def advance(self):
        if not self.path:return
        self.phase+=1
        if self.phase==6:
            self.finished=True;self.pulse.emit(self.path,False);self.opened.emit(self.path)
        else:
            self.pulse.emit(self.path,self.phase%2==0);self.timer.start(150)
    def cancel(self):
        old=self.path;self.timer.stop();self.path='';self.phase=-1;self.finished=False
        if old:self.pulse.emit(old,False)

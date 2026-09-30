"""In-app PDF fallback for distributions with split QtPdf packages."""
import shutil,subprocess,re
from PySide6.QtGui import QImage,QPixmap
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel
from design import SpinBox

class PdfFallback(QWidget):
    def __init__(self,panel,reason):
        super().__init__();self.panel=panel;self.pages=1;self.generation=0;box=QVBoxLayout(self)
        if not shutil.which('pdftoppm'):
            hint=QLabel('PDF support is missing from this system.\n\nCachyOS / Arch: install qt6-webengine or poppler.\nDebian / Ubuntu: install poppler-utils.\nFedora: install poppler-utils.\n\nThen reopen this PDF. The portable build includes QtPdf.');hint.setWordWrap(True);box.addWidget(hint)
            panel.status.setText('Missing PDF engine: '+reason);return
        from viewers import ImageCanvas
        self.canvas=ImageCanvas();box.addWidget(self.canvas,1);bar=QHBoxLayout();box.addLayout(bar)
        previous=QPushButton('Previous');previous.clicked.connect(lambda:self.number.setValue(self.number.value()-1));bar.addWidget(previous)
        self.number=SpinBox();self.number.setRange(1,1);self.number.valueChanged.connect(self.render);bar.addWidget(self.number)
        following=QPushButton('Next');following.clicked.connect(lambda:self.number.setValue(self.number.value()+1));bar.addWidget(following)
        def metadata():
            result=subprocess.run(['pdfinfo',panel.path],capture_output=True,text=True,timeout=20)
            if result.returncode:raise ValueError(result.stderr.strip())
            match=re.search(r'^Pages:\s+(\d+)',result.stdout,re.M)
            return int(match.group(1)) if match else 1
        def ready(pages):self.pages=pages;self.number.setMaximum(pages);self.render(1)
        panel.hub.run(panel,metadata,ready)
    def render(self,page):
        self.generation+=1;token=self.generation;panel=self.panel
        def work():
            result=subprocess.run(['pdftoppm','-f',str(page),'-l',str(page),'-singlefile','-scale-to','1800','-png',panel.path],capture_output=True,timeout=40)
            if result.returncode:raise ValueError(result.stderr.decode(errors='replace'))
            image=QImage.fromData(result.stdout)
            if image.isNull():raise ValueError('PDF renderer did not return an image.')
            return image
        def ready(image):
            if token!=self.generation:return
            self.canvas.pixmap=QPixmap.fromImage(image);self.canvas.update();panel.status.setText(f'Page {page} / {self.pages} · native Poppler fallback')
        panel.hub.run(panel,work,ready)

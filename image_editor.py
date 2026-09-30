"""Native raster editing with source-coordinate crop/ink and explicit export."""
import os
from pathlib import Path
from PySide6.QtCore import Qt,Signal,QRectF,QPointF,QBuffer,QIODevice,QByteArray
from PySide6.QtGui import QImage,QImageReader,QImageWriter,QPainter,QPen,QColor,QTransform
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QFileDialog,QColorDialog,QFormLayout,QSlider,QMessageBox
from design import SurfaceDialog,ComboBox,SpinBox

def image_formats():
    names={bytes(f).decode().lower() for f in QImageWriter.supportedImageFormats()}
    return sorted(names,key=lambda f:(f not in ('png','jpeg','webp'),f))

def read_image(path):
    reader=QImageReader(str(path));reader.setAutoTransform(True);size=reader.size()
    if size.width()*size.height()>64_000_000:raise ValueError('Editing supports images up to 64 megapixels. Use an external editor for larger images.')
    image=reader.read()
    if image.isNull():raise ValueError(reader.errorString())
    return image

def image_bytes(image,fmt,quality=85,width=None,height=None):
    if image.isNull():raise ValueError('No image is loaded.')
    if fmt not in image_formats():raise ValueError('This image writer is not installed.')
    if width and height:
        if width*height>64_000_000:raise ValueError('Export is limited to 64 megapixels.')
        image=image.scaled(width,height,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
    if fmt in ('jpg','jpeg') and image.hasAlphaChannel():
        background=QImage(image.size(),QImage.Format.Format_RGB32);background.fill(Qt.GlobalColor.white)
        p=QPainter(background);p.drawImage(0,0,image);p.end();image=background
    data=QByteArray();buffer=QBuffer(data);buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer=QImageWriter(buffer,fmt.encode());writer.setQuality(int(quality));writer.setOptimizedWrite(True)
    if not writer.write(image):raise ValueError(writer.errorString())
    return bytes(data)

def write_image(image,path,fmt,quality=85,width=None,height=None):
    data=image_bytes(image,fmt,quality,width,height)
    # Exclusive create keeps every original and any existing destination intact.
    with open(path,'xb') as output:output.write(data)
    return len(data)

class EditCanvas(QWidget):
    commit=Signal();changed=Signal()
    def __init__(self,config):
        super().__init__();self.config=config;self.image=QImage();self.mode='View';self.crop=QRectF();self.anchor=None;self.stroke=[];self.color=QColor(config['colors']['primary']);self.pen_width=6
        self.setMinimumSize(120,100);self.setMouseTracking(True)
    def target(self):
        if self.image.isNull():return QRectF()
        size=self.image.size().scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF((self.width()-size.width())/2,(self.height()-size.height())/2,size.width(),size.height())
    def source_point(self,pos):
        rect=self.target()
        if rect.isEmpty():return QPointF()
        return QPointF(max(0,min(self.image.width()-1,(pos.x()-rect.x())/rect.width()*self.image.width())),max(0,min(self.image.height()-1,(pos.y()-rect.y())/rect.height()*self.image.height())))
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor(self.config['colors']['background']));rect=self.target()
        if rect.isEmpty():return
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform);p.drawImage(rect,self.image)
        p.translate(rect.topLeft());p.scale(rect.width()/self.image.width(),rect.height()/self.image.height())
        if self.stroke:self.draw_stroke(p)
        if not self.crop.isEmpty():
            p.setPen(QPen(QColor(self.config['colors']['primary']),max(1,self.image.width()/rect.width()),Qt.PenStyle.DashLine));p.setBrush(Qt.BrushStyle.NoBrush);p.drawRect(self.crop)
    def draw_stroke(self,p):
        p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setPen(QPen(self.color,self.pen_width,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
        if len(self.stroke)==1:p.drawPoint(self.stroke[0])
        for a,b in zip(self.stroke,self.stroke[1:]):p.drawLine(a,b)
    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or self.image.isNull() or not self.target().contains(event.position()):return
        self.anchor=self.source_point(event.position())
        if self.mode=='Crop':self.crop=QRectF(self.anchor,self.anchor)
        elif self.mode=='Draw':self.stroke=[self.anchor]
        self.update()
    def mouseMoveEvent(self,event):
        if self.anchor is None or not event.buttons()&Qt.MouseButton.LeftButton:return
        point=self.source_point(event.position())
        if self.mode=='Crop':self.crop=QRectF(self.anchor,point).normalized()
        elif self.mode=='Draw':self.stroke.append(point)
        self.update()
    def mouseReleaseEvent(self,event):
        if self.stroke:
            self.commit.emit();p=QPainter(self.image);self.draw_stroke(p);p.end();self.stroke=[];self.changed.emit()
        self.anchor=None;self.update()

class ImageExport(SurfaceDialog):
    def __init__(self,editor):
        super().__init__(editor.config,editor);self.editor=editor;self.setWindowTitle('Export image');self.resize(440,360)
        box=QVBoxLayout(self);form=QFormLayout();box.addLayout(form)
        self.format=ComboBox();self.format.addItems(image_formats());self.format.setCurrentText('png');form.addRow('File type',self.format)
        self.width=SpinBox();self.height=SpinBox()
        for field,value in ((self.width,editor.canvas.image.width()),(self.height,editor.canvas.image.height())):field.setRange(1,32000);field.setValue(value)
        form.addRow('Width (pixels)',self.width);form.addRow('Height (pixels)',self.height)
        self.width.valueChanged.connect(self.change_width);self.height.valueChanged.connect(self.change_height)
        self.quality=QSlider(Qt.Orientation.Horizontal);self.quality.setRange(1,100);self.quality.setValue(85);form.addRow('Quality / compression',self.quality)
        self.note=QLabel('Dimensions keep the aspect ratio. Lower JPEG/WebP quality or resolution to reduce file size. PNG stays lossless.');self.note.setWordWrap(True);box.addWidget(self.note)
        row=QHBoxLayout();box.addLayout(row)
        for label,fn in (('Estimate size',self.estimate),('Export to…',self.export),('Close',self.accept)):
            b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
    def change_width(self,value):
        self.height.blockSignals(True);self.height.setValue(max(1,round(value*self.editor.canvas.image.height()/self.editor.canvas.image.width())));self.height.blockSignals(False)
    def change_height(self,value):
        self.width.blockSignals(True);self.width.setValue(max(1,round(value*self.editor.canvas.image.width()/self.editor.canvas.image.height())));self.width.blockSignals(False)
    def options(self):return self.format.currentText(),self.quality.value(),self.width.value(),self.height.value()
    def estimate(self):
        panel=self.editor.panel
        if panel.busy:return
        options=self.options();image=self.editor.canvas.image.copy()
        panel.hub.run(panel,lambda:len(image_bytes(image,*options)),lambda size:self.note.setText(f'Estimated encoded size: {size/1024:,.1f} KiB'))
    def export(self):
        panel=self.editor.panel
        if panel.busy:return
        options=self.options();fmt=options[0]
        path,_=QFileDialog.getSaveFileName(self,'Export edited image',str(Path(panel.path).with_name(Path(panel.path).stem+' edited.'+fmt)),f'{fmt.upper()} (*.{fmt})')
        if not path:return
        if Path(path).suffix.lower()!='.'+fmt:path+='.'+fmt
        image=self.editor.canvas.image.copy()
        def ready(size):
            self.editor.modified=False;self.note.setText(f'Exported {size/1024:,.1f} KiB to {path}');panel.hub.changed.emit()
        panel.hub.run(panel,lambda:write_image(image,path,*options),ready)
    def closeEvent(self,event):
        if self.editor.panel.busy:event.ignore()
        else:super().closeEvent(event)
    def reject(self):
        if not self.editor.panel.busy:super().reject()
    def accept(self):
        if not self.editor.panel.busy:super().accept()

class ImageEditor(QWidget):
    def __init__(self,panel):
        super().__init__();self.panel=panel;self.config=panel.config;self.modified=False;self.undo_stack=[];box=QVBoxLayout(self);box.setContentsMargins(0,0,0,0);self.setMinimumWidth(450)
        tools=QHBoxLayout();box.addLayout(tools)
        self.mode=ComboBox();self.mode.addItems(['View','Crop','Draw']);tools.addWidget(self.mode)
        self.canvas=EditCanvas(self.config);self.mode.currentTextChanged.connect(lambda value:setattr(self.canvas,'mode',value))
        for label,fn in (('Apply crop',self.crop),('↶ 90°',lambda:self.rotate(-90)),('↷ 90°',lambda:self.rotate(90))):
            b=QPushButton(label);b.clicked.connect(fn);tools.addWidget(b)
        drawing=QHBoxLayout();box.addLayout(drawing);color=QPushButton('Pen color');color.clicked.connect(self.choose_color);drawing.addWidget(color)
        drawing.addWidget(QLabel('Width'));width=SpinBox();width.setRange(1,150);width.setValue(6);width.setSuffix(' px');width.setMaximumWidth(85);width.valueChanged.connect(lambda v:setattr(self.canvas,'pen_width',v));drawing.addWidget(width)
        for label,fn in (('Undo',self.undo),('Export…',self.export)):
            b=QPushButton(label);b.clicked.connect(fn);drawing.addWidget(b)
        box.addWidget(self.canvas,1);self.canvas.commit.connect(self.checkpoint);self.canvas.changed.connect(self.edited)
        panel.hub.run(panel,lambda:read_image(panel.path),self.loaded)
    def loaded(self,image):self.canvas.image=image;self.canvas.update();self.panel.status.setText(f'{image.width()} × {image.height()} · original pixels · export saves a new file')
    def checkpoint(self):
        self.undo_stack.append(self.canvas.image.copy())
        while len(self.undo_stack)>1 and (len(self.undo_stack)>12 or sum(i.sizeInBytes() for i in self.undo_stack)>128*1024*1024):self.undo_stack.pop(0)
    def edited(self):self.modified=True;self.canvas.update()
    def crop(self):
        rect=self.canvas.crop.toAlignedRect().intersected(self.canvas.image.rect())
        if rect.width()<2 or rect.height()<2:self.panel.status.setText('Choose Crop and drag a rectangle across the image first.');return
        self.checkpoint();self.canvas.image=self.canvas.image.copy(rect);self.canvas.crop=QRectF();self.edited()
    def rotate(self,degrees):
        if self.canvas.image.isNull():return
        self.checkpoint();self.canvas.image=self.canvas.image.transformed(QTransform().rotate(degrees));self.canvas.crop=QRectF();self.edited()
    def undo(self):
        if self.undo_stack:self.canvas.image=self.undo_stack.pop();self.canvas.crop=QRectF();self.edited()
    def choose_color(self):
        color=QColorDialog.getColor(self.canvas.color,self)
        if color.isValid():self.canvas.color=color
    def export(self):
        if self.canvas.image.isNull():return
        dialog=ImageExport(self);dialog.exec();dialog.deleteLater()
    def can_close(self):
        if self.modified:return QMessageBox.question(self,'Unexported image edits','Discard these image edits? Export first to keep them. The original image is unchanged.',QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)==QMessageBox.StandardButton.Discard
        return True
    def stop(self):pass

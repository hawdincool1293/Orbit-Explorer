"""Asynchronous selected-file details, drawn as compact tree branches."""
import os,mimetypes
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import Signal,Qt,QSize,QRect,QRectF
from PySide6.QtGui import QColor,QFont,QPen,QPainterPath
from PySide6.QtWidgets import QStyledItemDelegate,QStyle
from ui import PathModel
from core import Node

def human_size(size):
    value=float(size)
    for unit in ('B','KiB','MiB','GiB','TiB'):
        if value<1024 or unit=='TiB':return f'{value:.1f} {unit}' if unit!='B' else f'{size:,} B'
        value/=1024

def describe_path(path,canceled=None):
    try:
        st=os.lstat(path);folder=os.path.isdir(path);items=None;size=human_size(st.st_size)
        if folder:
            count=0;direct_bytes=0
            with os.scandir(path) as entries:
                for entry in entries:
                    count+=1
                    if count%256==0 and canceled and canceled():return dict(first="",second="")
                    try:
                        if entry.is_file(follow_symlinks=False):direct_bytes+=entry.stat(follow_symlinks=False).st_size
                    except OSError:pass
            items=count;size=f'{human_size(direct_bytes)} direct files'
        kind='Folder' if folder else (mimetypes.guess_type(path)[0] or (Path(path).suffix.lstrip('.').upper()+' file' if Path(path).suffix else 'File'))
        if os.path.islink(path):kind='Link to '+kind.lower()
        date=datetime.fromtimestamp(st.st_mtime).strftime('%d/%m/%Y %H:%M')
        return dict(first=f'{size} · {items:,} items' if folder else size,
                    second=kind,third=f'Modified {date}',type=kind,size=st.st_size,items=items,modified=date,
                    preview_node=Node(path,Path(path).name,folder,st.st_size,0,(0,0,0),None,modified_ns=st.st_mtime_ns))
    except OSError as exc:return dict(first='Unavailable',second=str(exc))

class SelectionModel(PathModel):
    ready=Signal(int,str,object)
    def __init__(self,parent=None):
        super().__init__(parent);self.names_only=True;self.details={};self.nodes={};self.token=0
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='orbit-details');self.ready.connect(self.accept)
    def clear(self):
        self.token+=1;self.details.clear();self.nodes.clear();super().clear()
    def append(self,paths):
        fresh=[p for p in paths if p not in self.seen];super().append(fresh);token=self.token
        for path in fresh:self.pool.submit(self.load,token,path)
    def load(self,token,path):
        if token==self.token:self.ready.emit(token,path,describe_path(path,lambda:token!=self.token))
    def accept(self,token,path,details):
        if token!=self.token or path not in self.seen:return
        if 'preview_node' in details:self.nodes[path]=details['preview_node']
        self.details[path]=details;i=self.index(self.paths.index(path),0);self.dataChanged.emit(i,i)
    def shutdown(self):
        self.token+=1;self.pool.shutdown(wait=False,cancel_futures=True)

class SelectionDelegate(QStyledItemDelegate):
    def __init__(self,config,thumbnails,parent=None):super().__init__(parent);self.config=config;self.thumbnails=thumbnails
    def sizeHint(self,option,index):return QSize(300,122+max(0,self.config['font_size']-11)*7)
    def paint(self,painter,option,index):
        painter.save();painter.setClipRect(option.rect);painter.setRenderHint(painter.RenderHint.Antialiasing)
        c=self.config['colors'];r=option.rect.adjusted(1,4,-1,-4)
        tint=QColor(c['primary'] if option.state & (QStyle.StateFlag.State_Selected|QStyle.StateFlag.State_MouseOver) else c['background']);tint.setAlpha(24 if option.state & QStyle.StateFlag.State_MouseOver else 150)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(tint);painter.drawRoundedRect(QRectF(r),18,18)
        path=index.data(Qt.ItemDataRole.UserRole);details=index.model().details.get(path,dict(first='Reading details…',second=''))
        node=index.model().nodes.get(path)
        thumb=QRectF(r.x()+12,r.y()+14,54,54);painter.setBrush(QColor(c['panel']));painter.drawRoundedRect(thumb,14,14)
        if node:
            pix,category=self.thumbnails.pixmap(node)
            if not pix.isNull():
                area=thumb if category in ('image','video') else thumb.adjusted(8,8,-8,-8)
                painter.save();clip=QPainterPath();clip.addRoundedRect(thumb,14,14);painter.setClipPath(clip)
                scaled=pix.scaled(area.size().toSize(),Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
                painter.drawPixmap(area,scaled,QRectF((scaled.width()-area.width())/2,(scaled.height()-area.height())/2,area.width(),area.height()));painter.restore()
        x=r.x()+80;width=r.width()-92;size=self.config['font_size']
        painter.setFont(QFont(self.config['font'],max(10,size-1),QFont.Weight.DemiBold));painter.setPen(QColor(c['text']))
        fm=painter.fontMetrics();baseline=r.y()+12+fm.ascent()
        painter.drawText(x,baseline,fm.elidedText(index.data(Qt.ItemDataRole.DisplayRole) or '',Qt.TextElideMode.ElideMiddle,width))
        baseline+=fm.descent()+8
        painter.setFont(QFont(self.config['font'],max(8,size-2)));fm=painter.fontMetrics();step=fm.height()+4
        line_color=QColor(c['secondary']);line_color.setAlpha(110);painter.setPen(QPen(line_color,1))
        painter.drawLine(x+2,baseline,x+2,baseline+2*step+fm.ascent())
        for number,line in enumerate((details['first'],details['second'],details.get('third',''))):
            y=baseline+number*step+fm.ascent();painter.setPen(QPen(line_color,1));painter.drawLine(x+2,y-4,x+8,y-4)
            painter.setPen(QColor(c['muted']));painter.drawText(x+13,y,fm.elidedText(line,Qt.TextElideMode.ElideRight,width-13))
        painter.restore()

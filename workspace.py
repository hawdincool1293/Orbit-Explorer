"""Independent file viewports arranged in a tree of resizable splitters."""
from pathlib import Path
from PySide6.QtCore import Signal, Qt, QEvent, QPointF,QRectF,QSize
from PySide6.QtGui import QPainterPath,QRegion
from PySide6.QtWidgets import QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QSplitter
from graph import Graph
from design import ui_icon,Panel
from panes import LiveSplitter

def new_state():
    return dict(location='',back_paths=[],forward_paths=[],trip=[],trip_target='',force_target='',
                animation=None,devices={},scan_preserve=False,scan_token=0)

class ViewTile(QFrame):
    def __init__(self,config,thumbnails,owner):
        super().__init__();self.owner=owner;self.state=new_state();self.setObjectName('viewTile')
        layout=QVBoxLayout(self);layout.setContentsMargins(1,1,1,1);layout.setSpacing(0)
        bar=Panel();bar.setObjectName("viewportHeader");line=QHBoxLayout(bar);line.setContentsMargins(18,8,10,8)
        self.folder_icon=QLabel();line.addWidget(self.folder_icon)
        self.title=QLabel('New viewport');self.title.setObjectName('viewName');self.title.setTextFormat(Qt.TextFormat.PlainText)
        line.addWidget(self.title,1)
        self.fit=QPushButton();self.fit.setProperty('role','icon');self.fit.setFixedSize(30,30);self.fit.setToolTip('Fit this node cloud');self.fit.clicked.connect(lambda:self.graph.fit_cloud());line.addWidget(self.fit)
        self.close_button=QPushButton();self.close_button.setProperty('role','icon');self.close_button.setFixedSize(30,30)
        self.close_button.setToolTip('Close this viewport');self.close_button.clicked.connect(lambda:owner.close_tile(self))
        line.addWidget(self.close_button);layout.addWidget(bar)
        self.graph=Graph(config,thumbnails);layout.addWidget(self.graph,1)
        self.refresh_style()
        self.graph.installEventFilter(self);bar.installEventFilter(self);self.title.installEventFilter(self)
    def refresh_style(self):
        colors=self.owner.config['colors'];self.folder_icon.setPixmap(ui_icon('folder',colors['primary'],18).pixmap(18,18))
        self.fit.setIcon(ui_icon('fit',colors['muted'],17));self.close_button.setIcon(ui_icon('close',colors['muted'],17))
    def resizeEvent(self,event):
        super().resizeEvent(event)
        clip=QPainterPath();clip.addRoundedRect(QRectF(self.rect()),24,24)
        self.setMask(QRegion(clip.toFillPolygon().toPolygon()))
    def eventFilter(self,obj,event):
        if event.type() in (QEvent.Type.MouseButtonPress,QEvent.Type.FocusIn):self.owner.activate(self)
        return super().eventFilter(obj,event)
    def set_path(self,path):
        self.title.setText(Path(path).name or path);self.title.setToolTip(path)

class ViewWorkspace(QWidget):
    activated=Signal(object)
    tile_created=Signal(object)
    tile_closed=Signal(object)
    def __init__(self,config,thumbnails,parent=None):
        super().__init__(parent);self.config=config;self.thumbnails=thumbnails;self.tiles=[];self.splitters=[]
        self.layout=QVBoxLayout(self);self.layout.setContentsMargins(0,0,0,0)
        self.active=self._make();self.layout.addWidget(self.active);self.root=self.active;self.activate(self.active)
    def _make(self):
        tile=ViewTile(self.config,self.thumbnails,self);self.tiles.append(tile);return tile
    def activate(self,tile):
        if tile not in self.tiles:return
        changed=getattr(self,'active',None) is not tile;self.active=tile
        for t in self.tiles:
            t.setProperty('activeTile',t is tile);t.style().unpolish(t);t.style().polish(t)
            t.close_button.setVisible(len(self.tiles)>1)
        if changed:self.activated.emit(tile)
    def split(self,duplicate=False):
        old=self.active;tile=self._make();parent=old.parentWidget()
        orientation=Qt.Orientation.Horizontal if old.width()>=old.height() else Qt.Orientation.Vertical
        splitter=LiveSplitter(orientation)
        self.splitters.append(splitter)
        if isinstance(parent,QSplitter):
            sizes=parent.sizes();parent.replaceWidget(parent.indexOf(old),splitter);parent.setSizes(sizes)
        else:
            self.layout.replaceWidget(old,splitter);self.root=splitter
        splitter.addWidget(old);splitter.addWidget(tile);splitter.setSizes([500,500])
        self.tile_created.emit(tile)
        if duplicate:
            tile.state['location']=old.state['location'];tile.state['devices']=dict(old.state['devices'])
            tile.graph.set_graph(old.graph.root,list(old.graph.nodes),old.graph.hidden_count)
            tile.graph.yaw=old.graph.yaw;tile.graph.pitch=old.graph.pitch;tile.graph.zoom=old.graph.zoom
            tile.graph.offset=QPointF(old.graph.offset);tile.graph.set_selection(old.graph.selected_paths)
            tile.set_path(tile.state['location'])
        self.activate(tile);tile.graph.setFocus();return tile
    def close_tile(self,tile):
        if len(self.tiles)<2:return
        parent=tile.parentWidget();sibling=parent.widget(1-parent.indexOf(tile));grand=parent.parentWidget()
        sibling.setParent(None)
        if isinstance(grand,QSplitter):
            sizes=grand.sizes();grand.replaceWidget(grand.indexOf(parent),sibling);grand.setSizes(sizes)
        else:self.layout.replaceWidget(parent,sibling);self.root=sibling
        self.tiles.remove(tile)
        self.tile_closed.emit(tile)
        if self.active is tile:self.activate(next(t for t in self.tiles if t is sibling or sibling.isAncestorOf(t)))
        self.splitters.remove(parent);parent.setParent(None);parent.deleteLater();self.activate(self.active)

    def snapshot(self):
        def record(widget):
            if isinstance(widget,ViewTile):
                g=widget.graph
                return {'path':widget.state['location'],'active':widget is self.active,
                        'camera':[g.yaw,g.pitch,g.zoom,g.offset.x(),g.offset.y()]}
            return {'orientation':'h' if widget.orientation()==Qt.Orientation.Horizontal else 'v',
                    'sizes':widget.stored_sizes(),'children':[record(widget.widget(i)) for i in range(widget.count())]}
        return record(self.root)

    def restore(self,data):
        if not isinstance(data,dict) or not data:return []
        restored=[];sizes=[];active=None
        def build(item,depth=0):
            nonlocal active
            if not isinstance(item,dict) or depth>8 or len(restored)>=16:raise ValueError('Invalid viewport layout')
            if 'path' in item:
                tile=self._make();self.tile_created.emit(tile);restored.append((tile,item))
                if item.get('active'):active=tile
                return tile
            children=item.get('children',[])
            if len(children)!=2:raise ValueError('Invalid viewport split')
            split=LiveSplitter(Qt.Orientation.Horizontal if item.get('orientation')=='h' else Qt.Orientation.Vertical)
            self.splitters.append(split)
            for child in children:split.addWidget(build(child,depth+1))
            sizes.append((split,item.get('sizes',[])));return split
        old=self.root
        try:root=build(data)
        except (ValueError,TypeError):
            for tile,item in restored:self.tiles.remove(tile);tile.deleteLater()
            return []
        self.layout.replaceWidget(old,root);self.root=root
        self.tiles.remove(old);old.setParent(None);old.deleteLater();self.activate(active or restored[0][0])
        from PySide6.QtCore import QTimer
        for splitter,values in sizes:QTimer.singleShot(0,lambda s=splitter,v=values:s.restore_sizes(v))
        return restored

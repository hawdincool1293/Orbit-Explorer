"""Live PipeWire patchbay. Uses the existing session's pw-dump and pw-link."""
import json,shutil,os
from desktop_backend import host_command,configure_host_process
from dataclasses import dataclass,field
from PySide6.QtCore import Qt,QProcess,QTimer,QPointF,QRectF,Signal,QObject
from PySide6.QtGui import QColor,QPen,QBrush,QPainter,QPainterPath,QFont
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QGraphicsView,
    QGraphicsScene,QGraphicsItem,QGraphicsRectItem,QGraphicsEllipseItem,QGraphicsSimpleTextItem,QGraphicsPathItem)
from design import Menu as QMenu

@dataclass
class Port:
    id:int
    node:int
    name:str
    direction:str
    serial:str=''
@dataclass
class AudioNode:
    id:int
    name:str
    kind:str
    ports:list=field(default_factory=list)
@dataclass
class Link:
    id:int
    output:int
    input:int
    state:str=''

def object_id(value):
    try:return int(value)
    except (TypeError,ValueError):return -1

def parse_dump(payload):
    nodes={};ports={};links={};devices={}
    for item in payload:
        info=item.get('info') or {};props=info.get('props') or {};kind=item.get('type','').rsplit(':',1)[-1];ident=item.get('id')
        if kind=='Node' and ('Audio' in props.get('media.class','') or props.get('media.type')=='Audio'):
            label=props.get('node.description') or props.get('application.name') or props.get('node.nick') or props.get('node.name') or str(ident)
            nodes[ident]=AudioNode(ident,label,props.get('media.class','Audio'))
        elif kind=='Device' and props.get('media.class')=='Audio/Device':
            devices[ident]=props
    for item in payload:
        info=item.get('info') or {};props=info.get('props') or {};kind=item.get('type','').rsplit(':',1)[-1];ident=item.get('id')
        if kind=='Port':
            node=object_id(props.get('node.id',-1));direction=info.get('direction') or props.get('port.direction','')
            direction={'input':'in','output':'out'}.get(direction,direction)
            if node not in nodes or direction not in ('in','out'):continue
            port=Port(ident,node,props.get('port.alias') or props.get('port.name') or str(ident),direction,str(props.get('object.serial','')))
            ports[ident]=port;nodes[node].ports.append(port)
    for item in payload:
        if item.get('type','').endswith(':Link'):
            info=item.get('info') or {};props=info.get('props') or {}
            output=object_id(info.get('output-port-id',props.get('link.output.port',-1)))
            input_=object_id(info.get('input-port-id',props.get('link.input.port',-1)))
            if output in ports and input_ in ports:links[item['id']]=Link(item['id'],output,input_,info.get('state',''))
    # Cards with no currently exposed audio node remain visible as inactive devices.
    used={object_id(((x.get('info') or {}).get('props') or {}).get('device.id',-1)) for x in payload if x.get('type','').endswith(':Node')}
    for ident,props in devices.items():
        if ident not in used:nodes[-ident-1]=AudioNode(-ident-1,props.get('device.description') or props.get('device.name',str(ident)),'Audio/Device · no active ports')
    return nodes,ports,links

class PipeWire(QObject):
    snapshot=Signal(object)
    status=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.nodes={};self.ports={};self.links={};self.action=None;self.enabled=False
        self.poll=QTimer(self);self.poll.setInterval(1800);self.poll.timeout.connect(self.refresh)
        self.process=QProcess(self);self.process.finished.connect(self.receive)
        self.process.errorOccurred.connect(lambda _:self.status.emit(self.process.errorString()))
        self.timeout=QTimer(self);self.timeout.setSingleShot(True);self.timeout.setInterval(5000);self.timeout.timeout.connect(self.process.kill)
    def start(self):
        self.enabled=True;self.refresh();self.poll.start()
    def stop(self):
        self.enabled=False;self.poll.stop();self.timeout.stop();self.process.kill()
        if self.action:self.action.kill()
    def refresh(self):
        if not self.enabled or self.process.state()!=QProcess.ProcessState.NotRunning:return
        if not os.environ.get('FLATPAK_ID') and (not shutil.which('pw-dump') or not shutil.which('pw-link')):
            self.status.emit('Install pipewire (pw-dump and pw-link) to use audio routing.');return
        command=host_command(['pw-dump']);configure_host_process(self.process);self.process.start(command[0],command[1:]);self.timeout.start()
    def receive(self,code,status):
        self.timeout.stop()
        if not self.enabled:return
        if code:
            message=bytes(self.process.readAllStandardError()).decode(errors='replace').strip()
            self.status.emit(message or 'Cannot connect to the current PipeWire session.');return
        try:
            payload=json.loads(bytes(self.process.readAllStandardOutput()))
            self.nodes,self.ports,self.links=parse_dump(payload);self.snapshot.emit((self.nodes,self.ports,self.links))
            self.status.emit(f'{len(self.nodes)} devices / applications · {len(self.links)} connections')
        except (ValueError,TypeError,KeyError) as exc:self.status.emit(f'Cannot read audio graph: {exc}')
    def connect_ports(self,first,second):
        a=self.ports.get(first);b=self.ports.get(second)
        if not a or not b or a.direction==b.direction:self.status.emit('Connect an output to an input.');return
        output,input_=(a,b) if a.direction=='out' else (b,a)
        if any(l.output==output.id and l.input==input_.id for l in self.links.values()):return
        self.command([str(output.id),str(input_.id)])
    def disconnect(self,link_id):
        if link_id in self.links:self.command(['-d',str(link_id)])
    def command(self,args):
        if self.action and self.action.state()!=QProcess.ProcessState.NotRunning:
            self.status.emit('An audio connection change is still running.');return
        process=QProcess(self);self.action=process
        timeout=QTimer(process);timeout.setSingleShot(True);timeout.setInterval(5000);timeout.timeout.connect(process.kill)
        def finish(code,status):
            timeout.stop();err=bytes(process.readAllStandardError()).decode(errors='replace').strip()
            self.action=None;process.deleteLater()
            if code:self.status.emit(err or 'PipeWire refused this connection change.')
            else:self.refresh()
        process.finished.connect(finish);process.errorOccurred.connect(lambda _:self.status.emit(process.errorString()))
        command=host_command(['pw-link',*args]);configure_host_process(process);process.start(command[0],command[1:]);timeout.start()

class PortItem(QGraphicsEllipseItem):
    def __init__(self,port,parent,color):
        super().__init__(-6,-6,12,12,parent);self.port=port
        self.setBrush(QColor(color));self.setPen(QPen(QColor(color).lighter(135),1))
        self.setToolTip(port.name+' · '+port.direction);self.setCursor(Qt.CursorShape.CrossCursor);self.setZValue(4)
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.scene().begin_link(self,event.scenePos());event.accept()
        else:super().mousePressEvent(event)
    def mouseMoveEvent(self,event):self.scene().drag_link(event.scenePos());event.accept()
    def mouseReleaseEvent(self,event):self.scene().finish_link(event.scenePos());event.accept()

class NodeItem(QGraphicsRectItem):
    def __init__(self,node,config):
        self.node=node;self.ports={};ins=[p for p in node.ports if p.direction=='in'];outs=[p for p in node.ports if p.direction=='out']
        super().__init__(0,0,320,68+max(len(ins),len(outs),1)*27)
        self.setBrush(QColor(config['colors']['panel']));self.setPen(QPen(QColor(config['colors']['secondary']),1.5))
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable|QGraphicsItem.GraphicsItemFlag.ItemIsSelectable|QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setZValue(1)
        label=QGraphicsSimpleTextItem(node.name[:36],self);label.setBrush(QColor(config['colors']['text']));label.setFont(QFont(config['font'],10));label.setPos(12,9)
        label.setToolTip(node.name);kind=QGraphicsSimpleTextItem(node.kind,self);kind.setBrush(QColor(config['colors']['muted']));kind.setFont(QFont(config['font'],8));kind.setPos(12,32)
        for collection,output in ((ins,False),(outs,True)):
            for i,port in enumerate(collection):
                item=PortItem(port,self,config['colors']['accent' if output else 'primary']);item.setPos(320 if output else 0,69+i*27);self.ports[port.id]=item
                text=port.name.rsplit(':',1)[-1];text=text if len(text)<=18 else text[:17]+'…'
                label=QGraphicsSimpleTextItem(text,self);label.setFont(QFont(config['font'],8));label.setBrush(QColor(config['colors']['muted']))
                label.setPos(308-label.boundingRect().width() if output else 12,60+i*27);label.setToolTip(port.name)
    def itemChange(self,change,value):
        if change==QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():self.scene().update_links()
        return super().itemChange(change,value)

class CableItem(QGraphicsPathItem):
    def __init__(self,link,scene):
        super().__init__();self.link=link;self.owner=scene;self.setZValue(0)
        self.setPen(QPen(QColor(scene.config['colors']['primary']),2.3));self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setToolTip('Right-click or select and press Delete to disconnect')
    def contextMenuEvent(self,event):
        menu=QMenu();menu.config=self.owner.config;action=menu.addAction('Disconnect')
        if menu.exec(event.screenPos()) is action:self.owner.backend.disconnect(self.link.id)
    def itemChange(self,change,value):
        if change==QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.setPen(QPen(QColor(self.owner.config['colors']['accent' if value else 'primary']),3 if value else 2.3))
        return super().itemChange(change,value)

def cable_path(start,end):
    p=QPainterPath(start);dx=max(60,abs(end.x()-start.x())*.45);p.cubicTo(start+QPointF(dx,0),end-QPointF(dx,0),end);return p

class RoutingScene(QGraphicsScene):
    def __init__(self,config,backend,parent=None):
        super().__init__(parent);self.config=config;self.backend=backend;self.nodes={};self.ports={};self.links={};self.positions={};self.draft=None;self.start_port=None;self.signature=None
    def rebuild(self,data):
        nodes,ports,links=data
        signature=repr((nodes,links))
        if signature==self.signature or self.draft:return
        self.signature=signature;self.positions.update({k:v.pos() for k,v in self.nodes.items()})
        selected={k for k,v in self.links.items() if v.isSelected()}
        self.clear();self.nodes={};self.ports={};self.links={};columns={0:0,1:0,2:0}
        for ident,node in sorted(nodes.items(),key=lambda pair:(pair[1].kind,pair[1].name)):
            item=NodeItem(node,self.config);self.addItem(item);self.nodes[ident]=item;self.ports.update(item.ports)
            has_in=any(p.direction=='in' for p in node.ports);has_out=any(p.direction=='out' for p in node.ports)
            col=1 if has_in and has_out else (2 if has_in else 0)
            item.setPos(self.positions.get(ident,QPointF(col*490,columns[col])));columns[col]+=item.rect().height()+40
        for ident,link in links.items():
            item=CableItem(link,self);self.addItem(item);self.links[ident]=item;item.setSelected(ident in selected)
        self.update_links();self.setSceneRect(self.itemsBoundingRect().adjusted(-100,-100,100,100))
    def update_links(self):
        for item in self.links.values():
            a=self.ports.get(item.link.output);b=self.ports.get(item.link.input)
            if a and b:item.setPath(cable_path(a.scenePos(),b.scenePos()))
    def begin_link(self,port,pos):
        self.start_port=port;self.draft=QGraphicsPathItem();self.draft.setPen(QPen(QColor(self.config['colors']['accent']),2,Qt.PenStyle.DashLine));self.addItem(self.draft);self.drag_link(pos)
    def drag_link(self,pos):
        if self.draft:
            start=self.start_port.scenePos();self.draft.setPath(cable_path(start,pos) if self.start_port.port.direction=='out' else cable_path(pos,start))
    def finish_link(self,pos):
        if not self.draft:return
        target=next((item for item in self.items(pos) if isinstance(item,PortItem) and item is not self.start_port),None)
        self.removeItem(self.draft);self.draft=None
        if target:self.backend.connect_ports(self.start_port.port.id,target.port.id)
        self.start_port=None

class RoutingView(QGraphicsView):
    def __init__(self,scene):
        super().__init__(scene);self.setRenderHint(QPainter.RenderHint.Antialiasing);self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
    def wheelEvent(self,event):
        scale=1.15 if event.angleDelta().y()>0 else 1/1.15
        if .15<self.transform().m11()*scale<4:self.scale(scale,scale)
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Delete:
            for item in self.scene().selectedItems():
                if isinstance(item,CableItem):self.scene().backend.disconnect(item.link.id)
            return
        super().keyPressEvent(event)

class RoutingDialog(QDialog):
    def __init__(self,config,parent=None):
        super().__init__(parent);self.config=config;self.setWindowTitle('Orbit · Audio routing');self.resize(1080,680)
        self.backend=PipeWire(self);self.scene=RoutingScene(config,self.backend,self);self.view=RoutingView(self.scene)
        self.view.setBackgroundBrush(QColor(config['colors']['background']))
        layout=QVBoxLayout(self);row=QHBoxLayout();row.addWidget(QLabel('AUDIO ROUTING'),1)
        fit=QPushButton('Fit view');fit.clicked.connect(lambda:self.view.fitInView(self.scene.itemsBoundingRect(),Qt.AspectRatioMode.KeepAspectRatio));row.addWidget(fit)
        refresh=QPushButton('Refresh');refresh.clicked.connect(self.backend.refresh);row.addWidget(refresh)
        self.close_button=QPushButton('Close');self.close_button.setObjectName('closeAudioRouting');self.close_button.setAutoDefault(False)
        self.close_button.setToolTip('Close audio routing');self.close_button.clicked.connect(self.close);row.addWidget(self.close_button);layout.addLayout(row)
        layout.addWidget(QLabel('Drag an output socket to an input · Right-click a connection to disconnect · Wheel to zoom'))
        layout.addWidget(self.view,1);self.status=QLabel('Reading the current PipeWire session…');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.backend.snapshot.connect(self.scene.rebuild);self.backend.status.connect(self.status.setText)
        self.initial_fit=True;self.backend.snapshot.connect(self.fit_once)
        from panel_motion import bind_dialog
        bind_dialog(self,config)
    def fit_once(self,data):
        if self.initial_fit and data[0]:self.view.fitInView(self.scene.itemsBoundingRect(),Qt.AspectRatioMode.KeepAspectRatio);self.initial_fit=False
    def done(self,result):
        from panel_motion import dismiss
        self.backend.stop();dismiss(self,self.config,'dialogs',lambda:QDialog.done(self,result))
    def closeEvent(self,event):
        event.ignore();self.reject()
    def showEvent(self,event):super().showEvent(event);self.backend.start()
    def hideEvent(self,event):self.backend.stop();super().hideEvent(event)
    def shutdown(self):self.backend.stop()

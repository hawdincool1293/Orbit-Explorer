"""Projected sphere, selection gestures, and a readable held-key label view."""
# Orbit input patch: trackpad-opening-2026-09-30
import orbit_controls
import math
import os
import time
from pathlib import Path
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal, QLineF, QEvent, QSize
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap, QTextOption
from PySide6.QtWidgets import QWidget
from core import node_radius
from search_query import parse_query
from appearance import pin_color


class Graph(QWidget):
    selection_changed = Signal(object)
    entered = Signal(str)
    context_requested = Signal(str, object)
    drag_started = Signal(object, object)
    drag_moved = Signal(object)
    drag_finished = Signal(object)

    def __init__(self, config, thumbnails, parent=None):
        super().__init__(parent)
        self.config, self.thumbnails = config, thumbnails
        self.nodes, self.selected_paths = [], set()
        self.root, self.hidden_count = str(Path.home()), 0
        self.parsed_query=parse_query('');self.content_paths=set();self._match_cache={}
        self._dirty=True;self._layer=None;self._projection_key=None;self._positions={};self._radii={}
        self.live_resizing=False;self.right_drag=False;self.flight_previous=None;self.flight_mix=1.
        self.query = self.hover_path = self.audio_source = self.drop_hover = ""
        self.yaw, self.pitch, self.zoom = .28, -.16, 1.
        self.offset = QPointF()
        self.projected, self.favorite_rects = {}, []
        self.press = self.last = QPointF()
        self.press_path, self.dragging, self.moved = "", False, False
        self.rectangle, self.rectangle_anchor, self.rectangle_base = None, None, set()
        self.label_amount, self.label_target = 0., 0.
        self.label_start, self.label_started = 0., time.monotonic()
        self.label_layout = {}
        self.blink_until = 0.;self.drop_bright=False
        self.moon_time=time.monotonic()
        self.moon_timer=QTimer(self);self.moon_timer.setInterval(33);self.moon_timer.timeout.connect(self.animate_moons)
        self.setMouseTracking(True); self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(220,220);self.setAcceptDrops(True)
        self.timer = QTimer(self); self.timer.setInterval(16); self.timer.timeout.connect(self.tick)
        self.thumbnails.changed.connect(self.update)
        self._favorite_thumbs={}
        self.favorite_pressed=''

    def set_graph(self, root, nodes, hidden=0, preserve=False):
        self.root, self.nodes, self.hidden_count = root, nodes, hidden
        self._radii={n.path:max(11,min(30,node_radius(n)+6)) for n in nodes};self._projection_key=None
        self.refresh_matches()
        self.label_layout.clear()
        if self.label_target:self.build_labels()
        if not preserve: self.set_selection(set())
        self.update()

    def set_selection(self, paths):
        self.selected_paths = set(paths)
        self.selection_changed.emit(sorted(self.selected_paths))
        self.update()

    def set_query(self, query):
        self.query = query;self.parsed_query=parse_query(query,strict=self.config.get('search_strict',False));self.content_paths=set()
        self.refresh_matches()
        self.update()

    def matches(self, node):
        if node.path in self._match_cache:return self._match_cache[node.path]
        return not self.query or (self.parsed_query.matches(node.path,node.modified_ns,node.directory) and (not self.parsed_query.contains or node.path in self.content_paths))

    def refresh_matches(self):
        self._match_cache={}
        self._match_cache={n.path:self.matches(n) for n in self.nodes}

    def labels(self, held):
        if self.label_target==float(held):return
        self.label_start=self.label_amount;self.label_started=time.monotonic()
        self.label_target = 1. if held else 0.
        self.timer.start()

    def build_labels(self):
        # Circle diameters adapt to wrapped full filenames. A grid guarantees
        # separation; dense label views remain pannable rather than shrinking type.
        fm = QFontMetrics(QFont(self.config["font"],10))
        max_width = 180
        radii = {}
        for n in self.nodes:
            text_rect = fm.boundingRect(0,0,max_width,1000,int(Qt.TextFlag.TextWordWrap|Qt.TextFlag.TextWrapAnywhere),n.name)
            radii[n.path] = max(61, math.hypot(min(max_width,text_rect.width()),text_rect.height())/2 + 15)
        spacing = max(radii.values(),default=61)*2 + 16
        columns = max(1, math.ceil(math.sqrt(len(self.nodes)*1.5)))
        rows = math.ceil(len(self.nodes)/columns)
        ordered=sorted(self.nodes,key=lambda n:(round(n.xyz[1]/80),n.xyz[0],n.path))
        for i,n in enumerate(ordered):
            self.label_layout[n.path] = ((i%columns-(columns-1)/2)*spacing,
                                         (i//columns-(rows-1)/2)*spacing,radii[n.path])

    def tick(self):
        progress=min(1.,(time.monotonic()-self.label_started)/.28)
        self.label_amount=self.label_start+(self.label_target-self.label_start)*(1-(1-progress)**3)
        if progress==1:
            if time.monotonic()>self.blink_until:self.timer.stop()
        self.update()

    def blink(self, path):
        self.drop_hover=path;self.blink_until=time.monotonic()+.65;self.timer.start()

    def color(self,key,alpha=255):
        c=QColor(self.config["colors"][key]);c.setAlpha(max(0,min(255,int(alpha))));return c

    def connection_style(self,node):
        """An edge belongs to its child, not its parent. Selection wins over search."""
        selected=node.path in self.selected_paths
        dim=(bool(self.selected_paths) and not selected) or (not selected and not self.matches(node))
        if dim:
            color=QColor('#787878');color.setAlpha(30);return color,1.
        return self.color('folder' if node.directory else 'file',205 if selected else 105),1.8 if selected else 1.

    def point(self, node):
        x,y,z=node.xyz
        cy,sy,cp,sp=self._trig
        xx=x*cy+z*sy;zz=z*cy-x*sy
        yy=y*cp-zz*sp;depth=y*sp+zz*cp
        perspective=max(.62,min(1.55,690/max(120,690-depth*.32)))
        size=max(11 if node.directory else 9,self._radii.get(node.path,15)*self.zoom*perspective)
        px,py=xx*self.zoom*perspective,yy*self.zoom*perspective
        return QPointF(self.width()/2+self.offset.x()+px,self.height()/2+12+self.offset.y()+py),size,depth

    def update(self,*args):
        self._dirty=True
        super().update(*args)

    def resizeEvent(self,event):
        self._dirty=True;self._projection_key=None
        super().resizeEvent(event)

    def event(self,event):
        if event.type() in (QEvent.Type.DevicePixelRatioChange,QEvent.Type.ScreenChangeInternal) and hasattr(self,'_layer'):
            self._layer=None;self._dirty=True
            self.update()
        return super().event(event)

    def showEvent(self,event):
        self.live_resizing=False;self._layer=None;self._projection_key=None;self.update()
        self.moon_timer.start();super().showEvent(event)

    def hideEvent(self,event):
        self.favorite_pressed='';self.hover_path=''
        self.live_resizing=False;self.moon_timer.stop();super().hideEvent(event)

    def animate_moons(self):
        if self.config.get('moons',True) and not self.label_target and self.root in self.projected:
            rect=self.projected[self.root][0].adjusted(-75,-55,75,55).toAlignedRect()
            QWidget.update(self,rect)

    def paintEvent(self,event):
        dpr=self.devicePixelRatioF()
        if self._layer is not None and self._layer.devicePixelRatioF()!=dpr:self._layer=None
        if self.live_resizing and self._layer is not None:
            # Translate the sharp cached cloud instead of resampling a large
            # high-DPI texture for every splitter mouse-move. Layout stays live.
            size=self._layer.deviceIndependentSize();painter=QPainter(self)
            painter.drawPixmap(QPointF(round((self.width()-size.width())*dpr/2)/dpr,
                                       round((self.height()-size.height())*dpr/2)/dpr),self._layer)
            self.paint_favorites(painter);return
        if self._dirty or self._layer is None:
            self._layer=QPixmap(QSize(math.ceil(self.width()*dpr),math.ceil(self.height()*dpr)))
            self._layer.setDevicePixelRatio(dpr);self._layer.fill(Qt.GlobalColor.transparent)
            scene=QPainter(self._layer);self.render_scene(scene);scene.end();self._dirty=False
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform);p.drawPixmap(0,0,self._layer)
        if self.flight_previous is not None and self.flight_mix<1:
            p.setOpacity((1-self.flight_mix)*self.config.get('navigation_fade',65)/100)
            p.drawPixmap(self.rect(),self.flight_previous);p.setOpacity(1.)
        if self.config.get('moons',True) and self.label_amount<.05 and self.root in self.projected:
            center=self.projected[self.root][0].center();radius=self.projected[self.root][0].width()/2+30
            t=time.monotonic()-self.moon_time;p.setRenderHint(QPainter.RenderHint.Antialiasing)
            for i in range(2):
                angle=t*(.65 if i==0 else -.42)+i*math.pi
                point=center+QPointF(math.cos(angle)*(radius+i*15),math.sin(angle)*(radius*.42+i*8))
                p.setPen(QPen(self.color('primary',155),1));p.setBrush(self.color('accent' if i else 'secondary'))
                p.drawEllipse(point,4+i*1.5,3+i*1.5)
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(self.color('muted',160));p.drawEllipse(point+QPointF(-1,-1),1.2,1.2)
        self.paint_favorites(p)

    def render_scene(self,p):
        p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        # Shell owns the translucent backplane. Painting another surface here
        # (or an opaque viewTile parent) defeats the user's opacity setting.
        key=(self.yaw,self.pitch,self.zoom,self.offset.x(),self.offset.y(),self.label_amount,self.width(),self.height())
        if key!=self._projection_key:
            self._trig=(math.cos(self.yaw),math.sin(self.yaw),math.cos(self.pitch),math.sin(self.pitch))
            self._positions={n.path:self.point(n) for n in self.nodes};self._projection_key=key
        positions=self._positions
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(self.color("secondary",30*(1-self.label_amount)),1))
        center=QPointF(self.width()/2+self.offset.x(),self.height()/2+12+self.offset.y())
        p.drawEllipse(center,285*self.zoom,275*self.zoom)
        connections={}
        for n in self.nodes:
            if n.parent in positions:
                line=QLineF(positions[n.parent][0],positions[n.path][0])
                color,width=self.connection_style(n)
                connections.setdefault((color.rgba(),width),[]).append(line)
        for (rgba,width),lines in connections.items():
            p.setPen(QPen(QColor.fromRgba(rgba),width))
            if lines:p.drawLines(lines)
        if self.audio_source:
            point=positions.get(self.audio_source,(QPointF(75,self.height()-185),0,0))[0]
            p.setPen(QPen(self.color("primary",160),1.5,Qt.PenStyle.DotLine))
            p.drawLine(point,QPointF(160,self.height()-77))
            if self.audio_source not in positions:
                p.setBrush(self.color("panel"));p.drawEllipse(point,20,20)
                p.drawText(QRectF(point.x()-55,point.y()-48,180,23),Path(self.audio_source).name)
        self.projected={}
        for n in sorted(self.nodes,key=lambda n:positions[n.path][2]):
            center,r,depth=positions[n.path]
            rect=QRectF(center.x()-r,center.y()-r,2*r,2*r)
            self.projected[n.path]=(rect,n,depth)
            if not rect.intersects(QRectF(self.rect())):continue
            matched=self.matches(n); selected=n.path in self.selected_paths
            if self.label_amount<.001 and n.path!=self.hover_path and not (n.path==self.drop_hover and self.drop_bright):
                stamp=self.thumbnails.stamp(n,2*r,matched,selected,bool(self.query) and matched,self.dragging and selected,dpr=self.devicePixelRatioF())
                size=stamp.deviceIndependentSize()
                p.drawPixmap(QPointF(center.x()-size.width()/2,center.y()-size.height()/2),stamp)
                continue
            p.save()
            if not matched:p.setOpacity(.17)
            if self.dragging and selected:p.setOpacity(.2)
            color=self.color("accent" if selected else ("folder" if n.directory else "file")) if matched else QColor("#616976")
            p.setPen(QPen(color,2 if selected or self.query and matched else 1))
            p.setBrush(self.color("primary",210) if n.path==self.drop_hover and self.drop_bright else self.color("panel",240))
            p.drawEllipse(rect)
            if selected or self.query and matched:
                p.setPen(QPen(self.color("primary",150),2));p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(rect.adjusted(-5,-5,5,5))
            if r>=7:
                sprite=self.thumbnails.sprite(n,max(8,2*r-5),not matched,dpr=self.devicePixelRatioF())
                p.save()
                p.drawPixmap(rect.adjusted(2,2,-2,-2),sprite,QRectF(sprite.rect()));p.restore()
            if self.label_amount>.02:
                p.save();p.setOpacity(p.opacity()*self.label_amount);p.setPen(self.color("text"))
                p.setFont(QFont(self.config["font"],10))
                text=p.fontMetrics().elidedText(n.name,Qt.TextElideMode.ElideMiddle,190)
                width=p.fontMetrics().horizontalAdvance(text)+12
                text_rect=QRectF(center.x()-width/2,center.y()+r+5,width,23)
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(self.color('panel',235));p.drawRoundedRect(text_rect,5,5)
                p.setPen(self.color('text'));p.drawText(text_rect,Qt.AlignmentFlag.AlignCenter,text);p.restore()
            elif n.path==self.hover_path:
                p.setFont(QFont(self.config["font"],10));fm=p.fontMetrics()
                text=fm.elidedText(n.name,Qt.TextElideMode.ElideMiddle,260)
                box=QRectF(center.x()-fm.horizontalAdvance(text)/2-9,center.y()+r+9,fm.horizontalAdvance(text)+18,27)
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(self.color("panel",250));p.drawRoundedRect(box,7,7)
                p.setPen(self.color("text"));p.drawText(box,Qt.AlignmentFlag.AlignCenter,text)
            p.restore()
        if self.rectangle:
            p.setPen(QPen(self.color("primary"),1));p.setBrush(self.color("primary",35));p.drawRect(self.rectangle)
        p.setPen(self.color("muted"));p.setFont(QFont(self.config["font"],9))
        matching=sum(self.matches(n) for n in self.nodes)
        text=f"{len(self.nodes)} nodes"
        if self.query:text+=f"  ·  {matching} matching"
        if self.hidden_count:text+=f"  ·  {self.hidden_count} folded"
        if self.label_amount>.5:text+="  ·  Names visible · release key to hide"
        p.drawText(18,self.height()-14,text)

    def paint_favorites(self,p):
        self.favorite_rects=[];x=18
        p.setFont(QFont(self.config["font"],9))
        for fav in self.config["favorites"]:
            name=Path(fav["path"]).name or fav["path"]
            width=min(178,max(116,p.fontMetrics().horizontalAdvance(name[:19])+54))
            if x+width>self.width()-12:break
            rect=QRectF(x,16,width,46);hover=fav["path"] in (self.drop_hover,self.hover_path)
            pressed=fav['path']==self.favorite_pressed;selected=fav['path'] in self.selected_paths or fav['path']==self.root
            blink=self.drop_bright
            p.save()
            if pressed:
                p.translate(rect.center());p.scale(.97,.97);p.translate(-rect.center())
            color=QColor(pin_color(fav,self.config));color.setAlpha(235 if pressed else 210 if hover else 160 if selected else 55)
            p.setPen(QPen(color,2 if pressed else 1.5 if hover or selected else 1))
            p.setBrush(self.color("primary",110) if fav['path']==self.drop_hover and blink else self.color("panel",244))
            p.drawRoundedRect(rect,23,23)
            if pressed or hover or selected:
                tint=QColor(pin_color(fav,self.config));tint.setAlpha(55 if pressed else 28 if hover else 16)
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(tint);p.drawRoundedRect(rect,23,23)
            thumb_path=fav.get('thumbnail','')
            if thumb_path not in self._favorite_thumbs:self._favorite_thumbs[thumb_path]=QPixmap(thumb_path)
            thumb=self._favorite_thumbs[thumb_path]
            if not thumb.isNull():
                target=QRectF(x+7,23,32,32);p.save();clip=QPainterPath();clip.addRoundedRect(target,6,6);p.setClipPath(clip)
                scaled=thumb.scaled(32,32,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
                p.drawPixmap(target,scaled,QRectF((scaled.width()-32)/2,(scaled.height()-32)/2,32,32));p.restore()
            else:
                p.setBrush(QColor(pin_color(fav,self.config)));p.drawEllipse(QPointF(x+24,39),6,6)
            p.setPen(self.color("text"));p.drawText(QRectF(x+46,16,width-51,46),Qt.AlignmentFlag.AlignVCenter,
                p.fontMetrics().elidedText(name,Qt.TextElideMode.ElideRight,width-51))
            self.favorite_rects.append((rect,fav["path"]));x+=width+9
            p.restore()

    def hit(self,pos,exclude=None):
        for rect,path in self.favorite_rects:
            if rect.contains(pos) and path not in (exclude or set()):return path
        for path,(rect,n,depth) in reversed(list(self.projected.items())):
            if rect.contains(pos) and path not in (exclude or set()):
                delta=pos-rect.center()
                if delta.x()**2+delta.y()**2<=(rect.width()/2)**2:return path
        return ""

    def mousePressEvent(self,event):
        if orbit_controls.begin_pointer(self,event):return
        self.favorite_pressed=next((path for rect,path in self.favorite_rects if rect.contains(event.position())), '') if event.button()==Qt.MouseButton.LeftButton else ''
        if self.favorite_pressed:self.update()
        self.setFocus();self.press=self.last=event.position();self.moved=False;self.press_path=self.hit(self.press)
        self.ctrl=bool(event.modifiers()&Qt.KeyboardModifier.ControlModifier)
        self.shift=bool(event.modifiers()&Qt.KeyboardModifier.ShiftModifier)
        if event.button()==Qt.MouseButton.LeftButton:
            if self.shift:
                anchor=self.rectangle_anchor or self.press
                self.rectangle=QRectF(anchor,self.press).normalized()
                self.rectangle_base=set(self.selected_paths) if self.ctrl else set()
            elif self.press_path:
                if self.ctrl:self.set_selection(self.selected_paths^{self.press_path})
                elif self.press_path not in self.selected_paths:self.set_selection({self.press_path})
            elif not self.ctrl:self.set_selection(set())
        elif event.button() in (Qt.MouseButton.MiddleButton,Qt.MouseButton.RightButton):
            self.right_drag=event.button()==Qt.MouseButton.RightButton
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self,event):
        if orbit_controls.move_pointer(self,event):return
        pos=event.position();delta=pos-self.last
        if self.favorite_pressed and not any(rect.contains(pos) and path==self.favorite_pressed for rect,path in self.favorite_rects):
            self.favorite_pressed='';self.update()
        if (pos-self.press).manhattanLength()>6:self.moved=True
        if event.buttons()&Qt.MouseButton.MiddleButton:
            self.yaw+=delta.x()*.008*(-1 if self.config["invert_horizontal"] else 1)
            self.pitch=max(-1.48,min(1.48,self.pitch+delta.y()*.008*(1 if self.config["invert_vertical"] else -1)))
            self.update()
        elif event.buttons()&Qt.MouseButton.RightButton:
            if self.press_path and self.moved:
                if not self.dragging:
                    if self.press_path not in self.selected_paths:self.set_selection({self.press_path})
                    self.dragging=True;self.right_drag=True
                    self.drag_started.emit(sorted(self.selected_paths),event.globalPosition().toPoint())
                    self.dragging=False;self.press_path='';self.update()
                return
            self.offset+=delta;self.update()
        elif event.buttons()&Qt.MouseButton.LeftButton:
            self.right_drag=False
            if self.shift:
                self.rectangle=QRectF(self.rectangle_anchor or self.press,pos).normalized();self.update()
            elif self.press_path and self.moved:
                if not self.dragging:
                    if self.press_path not in self.selected_paths:self.set_selection({self.press_path})
                    self.dragging=True;self.update()
                    self.drag_started.emit(sorted(self.selected_paths),event.globalPosition().toPoint())
                    self.dragging=False;self.press_path="";self.update()
                return
        else:
            hover=self.hit(pos)
            if hover!=self.hover_path:
                self.hover_path=hover;self.setToolTip(hover);self.update()
            self.setCursor(Qt.CursorShape.PointingHandCursor if any(rect.contains(pos) for rect,path in self.favorite_rects) else Qt.CursorShape.ArrowCursor)
            if self.rectangle_anchor:self.rectangle=QRectF(self.rectangle_anchor,pos).normalized();self.update()
        self.last=pos

    def mouseReleaseEvent(self,event):
        if self.favorite_pressed:self.favorite_pressed='';self.update()
        if orbit_controls.end_pointer(self,event):return
        self.setCursor(Qt.CursorShape.ArrowCursor)
        if event.button()==Qt.MouseButton.RightButton:
            if not self.moved:self.context_requested.emit(self.hit(event.position()),event.globalPosition().toPoint())
        elif event.button()==Qt.MouseButton.LeftButton:
            if self.dragging:
                self.drag_finished.emit(event.globalPosition().toPoint());self.dragging=False
            elif self.shift:
                if self.moved or self.rectangle_anchor:
                    rect=QRectF(self.rectangle_anchor or self.press,event.position()).normalized()
                    self.set_selection(self.rectangle_base|{p for p,(r,n,d) in self.projected.items() if rect.contains(r.center())})
                    self.rectangle_anchor=None;self.rectangle=None
                else:self.rectangle_anchor=self.press
            elif self.press_path and not self.ctrl and not self.moved:self.set_selection({self.press_path})
        self.update()

    def mouseDoubleClickEvent(self,event):
        self.favorite_pressed='';self.update()
        orbit_controls.double_click(self,event)

    def leaveEvent(self,event):
        self.favorite_pressed='';self.hover_path='';self.setToolTip('');self.update()
        super().leaveEvent(event)

    def wheelEvent(self,event):
        if orbit_controls.trackpad_scroll(self,event):return
        self.zoom=max(.15,min(3.2,self.zoom*(1.13 if event.angleDelta().y()>0 else 1/1.13)));self.update()

    def fit_cloud(self):
        self.zoom=1.;self.offset=QPointF()
        self._trig=(math.cos(self.yaw),math.sin(self.yaw),math.cos(self.pitch),math.sin(self.pitch))
        points=[self.point(n)[0] for n in self.nodes]
        if points:
            cx=self.width()/2;cy=self.height()/2+12
            extent_x=max(abs(p.x()-cx) for p in points)+40;extent_y=max(abs(p.y()-cy) for p in points)+40
            self.zoom=max(.15,min(1.,(self.width()-70)/(2*extent_x),(self.height()-130)/(2*extent_y)))
        self._projection_key=None;self.update()

    def focusNextPrevChild(self,next):
        # Tab is a held viewport action; never hand it to QWidget focus traversal.
        return False

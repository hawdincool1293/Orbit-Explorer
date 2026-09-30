"""Orbit's original cubic fades, with reversible live-layout file transitions."""
from PySide6.QtCore import QObject,QEvent,QVariantAnimation,QEasingCurve,QTimer,QElapsedTimer,Qt
from PySide6.QtWidgets import QWidget,QSplitter,QGraphicsOpacityEffect
from shiboken6 import isValid


def number(config,key,default,low,high):
    try:return max(low,min(high,int(config.get(key,default))))
    except (TypeError,ValueError):return default


def enabled(config,kind):
    return bool(config.get('panel_motion_enabled',True) and config.get('panel_motion_'+kind,True))


def finish(widget,complete_exit=True):
    controller=getattr(widget,'_entrance_controller',None)
    if controller:controller.finish(complete_exit)


def finish_all(window):
    for controller in window.findChildren(Entrance):controller.finish()


def reveal(widget,config,kind='files',effect=None):
    previous=getattr(widget,'_entrance_controller',None)
    initial=previous.value if previous and previous.active else 0.
    finish(widget,False)
    if effect:effect.setOpacity(1.)
    if not widget.isVisible() or not enabled(config,kind):return
    controller=Entrance(widget,config,effect,initial=initial,kind=kind);widget._entrance_controller=controller
    controller.start()


def dismiss(widget,config,kind='files',done=None,effect=None):
    previous=getattr(widget,'_entrance_controller',None)
    if previous and previous.exiting:return
    initial=previous.value if previous and previous.active else 1.
    finish(widget,False)
    if not widget.isVisible() or not enabled(config,kind):
        if done:done()
        else:widget.hide()
        return
    controller=Entrance(widget,config,effect,exiting=True,done=done or widget.hide,initial=initial,kind=kind)
    widget._entrance_controller=controller;controller.start()


def later(widget,config,kind='files'):
    def start():
        controller=getattr(widget,'_entrance_controller',None)
        if not controller or not controller.exiting:reveal(widget,config,kind)
    QTimer.singleShot(0,widget,start)


class ShowMotion(QObject):
    def __init__(self,widget,config):
        super().__init__(widget);self.widget=widget;self.config=config;widget.installEventFilter(self)
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.Show:later(self.widget,self.config,'dialogs')
        elif event.type()==QEvent.Type.Hide:finish(self.widget)
        return False


def bind_dialog(widget,config):
    widget._show_motion=ShowMotion(widget,config)


class Entrance(QObject):
    def __init__(self,widget,config,effect,exiting=False,done=None,initial=0.,kind='files'):
        super().__init__(widget);self.widget=widget;self.config=config;self.effect=effect;self.active=False
        # Restore the old fade-only presentation for bars and dialogs. File
        # panels use live geometry: opacity effects break native video surfaces.
        if not effect and kind=='dialogs':
            effect=getattr(widget,'_motion_effect',None)
            if effect is None and widget.graphicsEffect() is None:
                effect=QGraphicsOpacityEffect(widget);widget.setGraphicsEffect(effect);widget._motion_effect=effect
            self.effect=effect
        self.fade_only=self.effect is not None
        self.exiting=exiting;self.done=done;self.value=initial
        self.was_enabled=widget.isEnabled()
        self.animation=QVariantAnimation(self);self.animation.setStartValue(initial);self.animation.setEndValue(0. if exiting else 1.)
        self.animation.setDuration(max(1,round(number(config,'panel_motion_duration',240,100,1200)*abs((0. if exiting else 1.)-initial))))
        # Exactly the curve used by the original info sidebar and node-label
        # fades; stale bounce settings never reintroduce overshoot.
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.step);self.animation.finished.connect(self.finish)
        self.clock=QElapsedTimer();self.frame_timer=QTimer(self);self.frame_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.frame_timer.setInterval(max(4,round(1000/number(config,'panel_motion_fps',120,60,240))))
        self.frame_timer.timeout.connect(self.advance)
        self.splitter=widget.parentWidget() if isinstance(widget.parentWidget(),QSplitter) else None
        self.axis=self.splitter.orientation() if self.splitter else Qt.Orientation.Vertical
        self.minimum=widget.minimumSize();self.maximum=widget.maximumSize();self.layout=None;self.graphs=[]
        self.geometry=widget.geometry();parent=widget.parentWidget()
        # Several Orbit containers expose `layout` as a Python attribute. Call
        # QWidget's methods explicitly instead of treating that object as callable.
        parent_layout=QWidget.layout(parent) if parent else None
        self.manual_geometry=not widget.isWindow() and not self.splitter and not (parent_layout and parent_layout.indexOf(widget)>=0)
        self.window=QWidget.window(widget);self.travel=number(config,'panel_motion_travel',100,0,100)/100;self.last_extent=None
    def start(self):
        widget=self.widget
        if self.splitter:
            self.index=self.splitter.indexOf(widget);self.goals=self.splitter.sizes()
            if self.index<0 or not self.goals[self.index]:self.abandon();return
            self.extent=self.goals[self.index]
            for index in range(1,self.splitter.count()):self.splitter.handle(index).installEventFilter(self)
        elif widget.isWindow() and not self.fade_only:
            self.layout=QWidget.layout(widget)
            if self.layout is None:self.abandon();return
            self.margins=self.layout.contentsMargins();self.extent=30
        else:
            self.extent=max(widget.sizeHint().height(),widget.height())
        if self.fade_only and not self.config.get('panel_motion_fade',True):
            self.effect.setOpacity(1.);self.effect.setEnabled(False);self.abandon();return
        self.active=True;widget.installEventFilter(self)
        if self.exiting:widget.setEnabled(False)
        if self.effect:self.effect.setEnabled(True)
        if not self.layout and not self.fade_only:
            from graph import Graph
            self.graphs=self.window.findChildren(Graph) if self.splitter else []
            for graph in self.graphs:
                graph._entrance_users=getattr(graph,'_entrance_users',0)+1;graph.live_resizing=True
            if self.axis==Qt.Orientation.Horizontal:widget.setMinimumWidth(0)
            else:widget.setMinimumHeight(0)
        self.step(self.value);self.animation.start()
        # Qt's normal animation driver is typically ~60 Hz. Drive its standard
        # interpolator from monotonic time at the requested rate instead. A late
        # frame jumps to current time, rather than queuing catch-up frames.
        if self.active:
            self.animation.pause();self.clock.start();self.frame_timer.start()
    def advance(self):
        if not self.active:return
        elapsed=min(self.animation.duration(),self.clock.elapsed())
        self.animation.setCurrentTime(elapsed)
        if self.active and elapsed>=self.animation.duration():self.finish()
    def abandon(self):
        self.widget._entrance_controller=None;self.deleteLater()
        if self.exiting and self.done:self.done()
    def step(self,value):
        if not self.active:return
        value=float(value);self.value=value
        if self.effect:
            self.effect.setOpacity(max(0.,min(1.,value)) if self.config.get('panel_motion_fade',True) else 1.)
        if self.fade_only:return
        if self.layout:
            m=self.margins;offset=round(self.extent*self.travel*(1-value))
            self.layout.setContentsMargins(m.left(),max(0,m.top()+offset),m.right(),m.bottom())
        else:
            extent=max(1,round(self.extent*(1-self.travel+self.travel*value)))
            if extent==self.last_extent:return
            self.last_extent=extent
            if self.axis==Qt.Orientation.Horizontal:self.widget.setMaximumWidth(extent)
            else:self.widget.setMaximumHeight(extent)
            if self.manual_geometry:self.widget.resize(self.geometry.width(),extent)
            if self.splitter:
                sizes=self.goals[:];remaining=max(0,sum(sizes)-extent);other=sum(sizes)-self.extent
                for index,size in enumerate(sizes):
                    sizes[index]=extent if index==self.index else round(size*remaining/max(1,other))
                self.splitter.setSizes(sizes)
    def finish(self,complete_exit=True):
        if not self.active:return
        self.active=False;self.frame_timer.stop();self.animation.stop()
        if self.layout:self.layout.setContentsMargins(self.margins)
        elif not self.fade_only:
            self.widget.setMaximumSize(self.maximum);self.widget.setMinimumSize(self.minimum)
            if self.manual_geometry:self.widget.setGeometry(self.geometry)
            if self.splitter and self.widget.isVisible():self.splitter.setSizes(self.goals)
            # Concurrent entrances and a pointer-held splitter share the cache.
            from panes import LiveSplitter
            dragging=any(pane.dragging for pane in self.window.findChildren(LiveSplitter))
            for graph in self.graphs:
                if not isValid(graph):continue
                graph._entrance_users=max(0,getattr(graph,'_entrance_users',1)-1)
                graph.live_resizing=bool(graph._entrance_users or dragging)
                if not graph.live_resizing:graph.update()
        if self.effect:
            self.effect.setOpacity(1.);self.effect.setEnabled(False)
        if self.exiting:self.widget.setEnabled(self.was_enabled)
        self.widget.removeEventFilter(self)
        if self.splitter:
            for index in range(1,self.splitter.count()):self.splitter.handle(index).removeEventFilter(self)
        if getattr(self.widget,'_entrance_controller',None) is self:self.widget._entrance_controller=None
        self.deleteLater()
        if self.exiting and complete_exit and self.done:self.done()
    def eventFilter(self,obj,event):
        if event.type() in (QEvent.Type.Hide,QEvent.Type.MouseButtonPress):self.finish()
        return False

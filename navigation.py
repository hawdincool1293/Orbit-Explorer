"""One continuous camera flight over prepared directory scenes."""
import math
from PySide6.QtCore import QVariantAnimation,QEasingCurve,QPointF

class Flight:
    def __init__(self,window,tile,target,scenes):
        self.window=window;self.tile=tile;self.graph=tile.graph;self.target=target
        self.scenes=[(tile.state['location'],list(self.graph.nodes),self.graph.hidden_count)]+scenes
        self.current=0;self.yaw=self.graph.yaw;self.pitch=self.graph.pitch;self.zoom=self.graph.zoom;self.offset=QPointF(self.graph.offset)
    def start(self):
        w=self.window;self.anim=QVariantAnimation(w);self.tile.state['animation']=self.anim
        self.anim.setDuration(max(150,int(w.config['navigation_duration'])))
        self.anim.setStartValue(0.);self.anim.setEndValue(1.)
        easing={'Smooth':QEasingCurve.Type.InOutCubic,'Gentle':QEasingCurve.Type.InOutSine,'Linear':QEasingCurve.Type.Linear}
        self.anim.setEasingCurve(easing.get(w.config['navigation_easing'],QEasingCurve.Type.InOutCubic))
        self.anim.valueChanged.connect(self.frame);self.anim.finished.connect(self.finish);self.anim.start()
    def frame(self,value):
        g=self.graph;w=self.window;n=len(self.scenes);position=value*(n-.001);index=min(n-1,int(position))
        if index!=self.current:
            g.flight_previous=g._layer.copy() if g._layer is not None else None
            path,nodes,hidden=self.scenes[index];g.set_graph(path,nodes,hidden);self.tile.set_path(path)
            self.tile.state['location']=path;self.tile.state['devices']={};w.address.set_location(path);self.current=index
        fraction=min(1.,(position-index)/.55);g.flight_mix=fraction*fraction*(3-2*fraction)
        angle=1.25*value if w.config['navigation_rotate'] else 0
        g.yaw=self.yaw+angle;g.pitch=self.pitch+(.1*math.sin(math.pi*value) if angle else 0)
        g.zoom=self.zoom*(1-.22*math.sin(math.pi*value));g.offset=self.offset*(1-value);g.update()
    def finish(self):
        w=self.window;g=self.graph;path=self.scenes[-1][0]
        g.flight_previous=None;g.flight_mix=1.;g.set_selection({self.target});g.update()
        w.record_recent(path);w.config['last_path']=path;w.status.setText(path)
        from appearance import save_config
        save_config(w.config)

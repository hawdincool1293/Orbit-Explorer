"""Live splitters with a cheap graph-preview path while the pointer is held."""
from PySide6.QtCore import Qt,QEvent
from PySide6.QtWidgets import QSplitter,QSplitterHandle,QApplication

class LiveHandle(QSplitterHandle):
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.splitter().resizing(True)
        super().mousePressEvent(event)
    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event);self.splitter().resizing(False)
    def event(self,event):
        if event.type()==QEvent.Type.UngrabMouse:self.splitter().resizing(False)
        return super().event(event)

class LiveSplitter(QSplitter):
    def __init__(self,orientation=Qt.Orientation.Horizontal,parent=None):
        super().__init__(orientation,parent);self.setOpaqueResize(True);self.setHandleWidth(8)
        self.setChildrenCollapsible(False);self.dragging=False;self.remembered=[]
        self.splitterMoved.connect(self.remember)
    def createHandle(self):return LiveHandle(self.orientation(),self)
    def remember(self,*args):
        sizes=self.sizes()
        if len(self.remembered)!=len(sizes):self.remembered=sizes[:]
        for i,size in enumerate(sizes):
            if size and not self.widget(i).isHidden():self.remembered[i]=size
    def stored_sizes(self):
        self.remember();return self.remembered[:]
    def restore_sizes(self,sizes):
        if isinstance(sizes,list) and len(sizes)==self.count() and all(isinstance(s,int) and 0<=s<100000 for s in sizes):
            self.remembered=sizes[:];self.setSizes(sizes)
    def restore_visible(self):
        if self.remembered:self.setSizes(self.remembered)
    def resizing(self,active):
        if self.dragging==active:return
        self.dragging=active
        from graph import Graph
        for graph in self.window().findChildren(Graph):
            graph.live_resizing=bool(active or getattr(graph,'_entrance_users',0))
            if not active:graph.update()

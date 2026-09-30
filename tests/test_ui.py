"""Offscreen widget interaction tests; requires the application's dependencies."""
import json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint,QPointF,QByteArray
from PySide6.QtGui import QImage,QColor
from PySide6.QtTest import QTest
from app import Orbit
from core import Node
from appearance import read_palette,defaults

APP=QApplication.instance() or QApplication([])
def pump(ms=100):
    end=time.monotonic()+ms/1000
    while time.monotonic()<end:
        APP.processEvents();time.sleep(.005)

class InteractionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.config_patch=patch("appearance.CONFIG",self.root/"settings.json");self.config_patch.start()
        self.drive_patch=patch("app.visible_mounts",return_value=[]);self.drive_patch.start()
        self.w=Orbit();self.errors=[];self.w.error=self.errors.append;self.w.show();self.w.visit(str(self.root),history=False)
        for _ in range(60):
            pump(20)
            if self.w.location==str(self.root):break
        self.assertEqual(self.w.location,str(self.root))
        self.a=self.root/"Delta.txt";self.a.write_text("one");self.b=self.root/"Alpha.txt";self.b.write_text("two")
        self.target=self.root/"Pinned";self.target.mkdir()
        self.nodes=[Node(str(self.a),"Delta.txt",False,3,1,(-130,0,0),None),
                    Node(str(self.b),"Alpha.txt",False,3,1,(130,0,0),None)]
        self.w.graph.set_graph(str(self.root),self.nodes);self.w.graph.setFocus();pump(100)
    def tearDown(self):
        self.w.close();pump(70);self.config_patch.stop();self.drive_patch.stop();self.temp.cleanup()
    def center(self,path):
        return self.w.graph.projected[str(path)][0].center().toPoint()
    def test_vertical_orbit_and_inversion_setting(self):
        g=self.w.graph;p=QPoint(200,180);before=g.pitch
        QTest.mousePress(g,Qt.MouseButton.MiddleButton,pos=p);QTest.mouseMove(g,p+QPoint(0,40));QTest.mouseRelease(g,Qt.MouseButton.MiddleButton,pos=p+QPoint(0,40))
        self.assertLess(g.pitch,before)
        g.config["invert_vertical"]=True;before=g.pitch
        QTest.mousePress(g,Qt.MouseButton.MiddleButton,pos=p);QTest.mouseMove(g,p+QPoint(0,40));QTest.mouseRelease(g,Qt.MouseButton.MiddleButton,pos=p+QPoint(0,40))
        self.assertGreater(g.pitch,before)
    def test_ctrl_selection_and_rectangle(self):
        g=self.w.graph
        QTest.mouseClick(g,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ControlModifier,self.center(self.a));pump(300)
        QTest.mouseClick(g,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ControlModifier,self.center(self.b));pump(30)
        self.assertEqual(g.selected_paths,{str(self.a),str(self.b)})
        start=self.center(self.a)-QPoint(40,50);end=self.center(self.b)+QPoint(40,50)
        g.set_selection(set());pump(300)
        start=self.center(self.a)-QPoint(40,50);end=self.center(self.b)+QPoint(40,50)
        QTest.mousePress(g,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ShiftModifier,start)
        QTest.mouseMove(g,end);QTest.mouseRelease(g,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ShiftModifier,end)
        self.assertEqual(g.selected_paths,{str(self.a),str(self.b)})
    def test_live_filter_spotlight_and_held_names(self):
        g=self.w.graph
        QTest.keyClicks(g,"D");pump(250)
        self.assertTrue(self.w.spotlight.isVisible());self.assertTrue(g.matches(self.nodes[0]));self.assertFalse(g.matches(self.nodes[1]))
        self.w.clear_search();g.setFocus()
        QTest.keyPress(g,Qt.Key.Key_Tab);pump(380);self.assertGreater(g.label_amount,.95)
        rectangles=[r for r,n,d in g.projected.values()]
        self.assertFalse(rectangles[0].intersects(rectangles[1]))
        QTest.keyRelease(g,Qt.Key.Key_Tab);pump(380);self.assertLess(g.label_amount,.03)
    def test_image_preview_and_system_palette(self):
        path=self.root/"picture.png";image=QImage(160,80,QImage.Format.Format_ARGB32);image.fill(QColor("red"));image.save(str(path))
        node=Node(str(path),path.name,False,path.stat().st_size,1,(0,0,0),None)
        self.w.thumbnails.pixmap(node);pump(200)
        pix,category=self.w.thumbnails.pixmap(node)
        self.assertEqual(category,"image");self.assertEqual(pix.toImage().pixelColor(40,40).red(),255)
        palette=self.root/"scheme.json";palette.write_text(json.dumps({"colours":{"primary":"abcdef","background":"123456","onSurface":"fedcba"}}))
        self.assertEqual(read_palette(palette)["primary"],"#abcdef")
        self.w.config["preset"]="System (Caelestia)";self.w.config["palette_file"]=str(palette);self.w.sync_palette()
        self.assertEqual(self.w.config["colors"]["primary"],"#abcdef")
        palette.write_text(json.dumps({"colours":{"primary":"fedcba"}}));self.w.sync_palette()
        self.assertEqual(self.w.config["colors"]["primary"],"#fedcba")


class AudioTests(unittest.TestCase):
    def test_spectrum_responds_to_real_pcm(self):
        import numpy as np
        from PySide6.QtMultimedia import QAudioBuffer,QAudioFormat
        from media import Spectrum
        fmt=QAudioFormat();fmt.setSampleRate(48000);fmt.setChannelCount(1);fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
        samples=(.5*np.sin(2*np.pi*1000*np.arange(2048)/48000)).astype(np.float32)
        visualizer=Spectrum(defaults());visualizer.feed(QAudioBuffer(QByteArray(samples.tobytes()),fmt))
        self.assertGreater(max(visualizer.levels),.6)

if __name__=="__main__":unittest.main()

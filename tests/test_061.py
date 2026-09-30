"""Wayland rendering, event propagation, exact search and bundled icon regressions."""
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QEvent,QPoint,QSize
from PySide6.QtGui import QKeyEvent,QIcon,QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget
import test_04 as fixtures
from test_04 import APP,pump,until
from app import Header
from appearance import defaults,load_config
from core import Node
from search_query import parse_query
from search_worker import run,content_matches
from thumbnails import BUNDLED_ICONS

class SearchTests(unittest.TestCase):
    def test_native_wayland_preference_keeps_explicit_platform_overrides(self):
        from desktop_backend import runtime_setup
        with patch.dict(os.environ,{'WAYLAND_DISPLAY':'wayland-test'},clear=True),patch('desktop_backend.sys.platform','linux'):
            runtime_setup();self.assertEqual(os.environ['QT_QPA_PLATFORM'],'wayland;xcb')
            os.environ['QT_QPA_PLATFORM']='offscreen';runtime_setup();self.assertEqual(os.environ['QT_QPA_PLATFORM'],'offscreen')
    def test_exact_filename_case_extension_spaces_and_literal_symbols(self):
        for name in ('Report.txt','two  spaces.txt','[draft]*?.txt'):
            q=parse_query(name,strict=True)
            self.assertTrue(q.matches('/home/me/'+name))
            self.assertFalse(q.matches('/home/me/old '+name))
            self.assertFalse(q.matches('/home/me/'+name+'.bak'))
        self.assertFalse(parse_query('Report.txt',True).matches('/home/me/report.txt'))
        self.assertFalse(parse_query('Report',True).matches('/home/me/Report.txt'))
        self.assertTrue(parse_query('report').matches('/home/me/Report.txt'))
        self.assertTrue(parse_query('Report.txt is: txt',True).matches('/home/me/Report.txt'))
        self.assertEqual(parse_query('Report.txt is: txt',True).patterns(),['*Report.txt*'])
    def test_worker_filters_index_candidates_and_visible_files_identically(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);paths=[root/n for n in ('Report.txt','report.txt','Report.txt.bak')]
            for p in paths:p.write_text('data')
            messages=[]
            with patch('search_worker.shutil.which',return_value=None),patch('search_worker.emit',side_effect=lambda k,v:messages.append((k,v))):
                run({'query':'Report.txt','strict':True,'local_paths':[str(p) for p in paths]})
            self.assertEqual([p for k,values in messages if k=='paths' for p in values],[str(paths[0])])
    def test_strict_contents_remain_literal_and_become_case_sensitive(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);upper=root/'upper.txt';lower=root/'lower.txt'
            upper.write_text('Remember [this].');lower.write_text('remember [this].')
            paths=list(map(str,(upper,lower)))
            self.assertEqual(set(content_matches(paths,'Remember [this]',False)),set(paths))
            self.assertEqual(content_matches(paths,'Remember [this]',True),[str(upper)])

class DesktopTests(unittest.TestCase):
    setUp=fixtures.FlowTests.setUp
    tearDown=fixtures.FlowTests.tearDown
    def test_header_key_events_do_not_shadow_qwidget_window(self):
        header=self.w.findChild(Header);self.assertIs(header.window(),self.w)
        self.w.graph.setFocus();errors=[]
        with patch('sys.excepthook',side_effect=lambda *e:errors.append(e)):
            QTest.keyPress(header,Qt.Key.Key_Tab);pump(310)
            self.assertGreater(self.w.graph.label_amount,.95)
            QTest.keyRelease(header,Qt.Key.Key_Tab);pump(310)
        self.assertFalse(errors);self.assertLess(self.w.graph.label_amount,.02)
        # The application-level filter remains robust to another widget/plugin
        # carrying a similarly named Python attribute.
        child=QWidget(self.w);child.window=self.w
        self.w.eventFilter(child,QKeyEvent(QEvent.Type.ShortcutOverride,Qt.Key.Key_A,Qt.KeyboardModifier.NoModifier))
    def test_canvas_opacity_survives_all_ancestor_surfaces(self):
        alphas=[]
        for value in (100,50,25):
            self.w.config['opacity']=value;self.w.apply_theme();pump(40)
            image=self.w.grab().toImage();point=self.w.graph.mapTo(self.w,QPoint(15,35));dpr=image.devicePixelRatio()
            alpha=image.pixelColor(round(point.x()*dpr),round(point.y()*dpr)).alpha();alphas.append(alpha)
            self.assertAlmostEqual(alpha,round(value*2.55),delta=2)
        self.assertGreater(alphas[0],alphas[1]);self.assertGreater(alphas[1],alphas[2])
    def test_exact_toggle_updates_graph_results_spotlight_and_saved_setting(self):
        self.w.search_box.setText('p note');pump(20)
        self.assertIn(str(self.source),self.w.search_model.paths)
        self.w.search_exact.click();pump(30)
        self.assertNotIn(str(self.source),self.w.search_model.paths)
        self.w.search_box.setText('p note.txt');pump(30)
        self.assertIn(str(self.source),self.w.search_model.paths)
        self.assertTrue(self.w.spotlight.exact.isChecked());self.assertTrue(until(lambda:load_config()['search_strict']))
        self.w.spotlight.exact.click();self.assertFalse(self.w.search_exact.isChecked())
    def test_bundled_sweet_icons_load_without_a_host_theme_and_overrides_win(self):
        self.assertEqual(defaults()['icon_theme'],'Sweet (bundled)')
        old=QIcon.themeSearchPaths()
        try:
            QIcon.setThemeSearchPaths([]);self.w.config['icon_theme']='Sweet (bundled)';self.w.thumbnails.set_theme()
            for name in ('folder','document','image','video','audio','archive','file','pdf','drive','partition'):
                self.assertFalse(QIcon(str(BUNDLED_ICONS/(name+'.svg'))).pixmap(512,512).isNull(),name)
            node=next(n for n in self.w.graph.nodes if n.path==str(self.source))
            pix,_=self.w.thumbnails.pixmap(node);self.assertGreaterEqual(pix.width(),256)
            self.assertIn('sweet:document',self.w.thumbnails.icons)
            image=QImage(64,64,QImage.Format.Format_RGB32);image.fill(Qt.GlobalColor.red);path=self.root/'red.png';image.save(str(path))
            self.w.config['type_icons']['document']=str(path);self.w.thumbnails.set_theme()
            pix,_=self.w.thumbnails.pixmap(node);self.assertGreater(pix.toImage().pixelColor(20,20).red(),240)
        finally:QIcon.setThemeSearchPaths(old)
    def test_dpr_change_discards_old_layer_and_rebuilds_caches(self):
        g=self.w.graph;g.repaint();old=g._layer.cacheKey()
        APP.sendEvent(g,QEvent(QEvent.Type.DevicePixelRatioChange));pump(30)
        self.assertNotEqual(g._layer.cacheKey(),old)

class ScaleTests(unittest.TestCase):
    def test_fractional_and_double_scale_are_rendered_at_physical_resolution(self):
        code='''
from test_04 import FlowTests,pump
from PySide6.QtCore import QEvent
f=FlowTests();f.setUp()
try:
 g=f.w.graph;g.repaint();dpr=g.devicePixelRatioF();assert dpr>1
 assert g._layer.devicePixelRatioF()==dpr
 assert abs(g._layer.width()-g.width()*dpr)<=1
 thumb=f.w.thumbnails;node=g.nodes[0]
 sprite=thumb.sprite(node,60,dpr=dpr);stamp=thumb.stamp(node,60,dpr=dpr)
 assert sprite.width()==round(60*dpr) and sprite.devicePixelRatioF()==dpr
 assert abs(stamp.deviceIndependentSize().width()-74)<1
 assert thumb.stamp(node,60,dpr=dpr).cacheKey()==stamp.cacheKey()
 assert thumb.stamp(node,60,dpr=1).cacheKey()!=stamp.cacheKey()
 g.live_resizing=True;g.resize(g.width()-40,g.height());g.repaint()
 g.live_resizing=False;g.update();pump(40)
 assert abs(g._layer.width()-g.width()*dpr)<=1
 print('DPI OK',dpr)
finally:f.tearDown()
'''
        for scale in ('1.5','2'):
            result=subprocess.run([sys.executable,'-c',code],env=dict(os.environ,QT_SCALE_FACTOR=scale),capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr);self.assertIn('DPI OK',result.stdout)

if __name__=='__main__':unittest.main()

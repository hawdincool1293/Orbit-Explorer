"""Connection semantics, selective settings updates, Niri and font packaging."""
import os,runpy,shutil,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QCheckBox,QLabel,QSlider
from PySide6.QtGui import QColor
import test_04 as fixtures
from test_04 import APP,pump,until
from ui import Settings
from design import Panel,stylesheet

class FlowTests(unittest.TestCase):
    setUp=fixtures.FlowTests.setUp
    tearDown=fixtures.FlowTests.tearDown
    def settings(self):
        dialog=Settings(self.w.config,self.w);dialog.changed.connect(self.w.settings_changed)
        self.addCleanup(dialog.deleteLater);return dialog
    def test_edges_use_child_type_color_and_dim_only_unselected_edges(self):
        g=self.w.graph;self.w.config['colors'].update(folder='#ffffff',file='#ff0000')
        folder=next(n for n in g.nodes if n.directory and n.parent);file=next(n for n in g.nodes if n.path==str(self.source))
        self.assertEqual(g.connection_style(folder)[0].name(),'#ffffff')
        self.assertEqual(g.connection_style(file)[0].name(),'#ff0000')
        g.set_selection({file.path});selected,width=g.connection_style(file);dim,dimwidth=g.connection_style(folder)
        self.assertEqual(selected.name(),'#ff0000');self.assertGreater(width,dimwidth)
        self.assertEqual(dim.red(),dim.green());self.assertEqual(dim.green(),dim.blue());self.assertLess(dim.alpha(),selected.alpha())
        g.set_selection({file.path,folder.path});self.assertEqual(g.connection_style(folder)[0].name(),'#ffffff')
        g.set_selection(set());self.assertEqual(g.connection_style(folder)[0].name(),'#ffffff')
        g.set_query('no matching name');self.assertEqual(g.connection_style(file)[0].name(),'#787878')
        g.set_selection({file.path});self.assertEqual(g.connection_style(file)[0].name(),'#ff0000')
    def test_checkbox_does_not_restyle_clear_icons_rebuild_pins_or_restart_search(self):
        dialog=self.settings();check=dialog.findChild(QCheckBox,'invert_vertical')
        with patch.object(self.w,'apply_theme') as theme,patch.object(self.w.thumbnails,'set_theme') as icons,patch.object(self.w,'refresh_favorites') as pins,patch.object(self.w,'query_changed') as search,patch('app.save_config') as save:
            for _ in range(20):check.click()
            self.assertEqual(save.call_count,0);pump(50)
            theme.assert_not_called();icons.assert_not_called();pins.assert_not_called();search.assert_not_called()
            pump(300);self.assertEqual(save.call_count,1)
    def test_opacity_slider_is_live_without_rebuilding_graph_or_stylesheet(self):
        dialog=self.settings();slider=dialog.findChild(QSlider,'opacitySlider');pump(50)
        g=self.w.graph;before=g._layer.cacheKey();style=stylesheet(self.w.config)
        with patch.object(self.w,'apply_theme') as theme,patch.object(self.w.thumbnails,'set_theme') as icons,patch.object(self.w,'refresh_favorites') as pins:
            for value in range(90,24,-1):slider.setValue(value)
            pump(50);theme.assert_not_called();icons.assert_not_called();pins.assert_not_called()
            self.assertEqual(style,stylesheet(self.w.config));self.assertEqual(g._layer.cacheKey(),before)
            image=self.w.grab().toImage();point=g.mapTo(self.w,QPoint(15,35));dpr=image.devicePixelRatio()
            self.assertAlmostEqual(image.pixelColor(round(point.x()*dpr),round(point.y()*dpr)).alpha(),64,delta=2)
            self.assertIsInstance(self.w.sidebar,Panel)
            point=self.w.sidebar.mapTo(self.w,QPoint(30,100));alpha=image.pixelColor(round(point.x()*dpr),round(point.y()*dpr)).alpha()
            self.assertLess(alpha,180)
    def test_spacing_updates_are_coalesced_and_do_not_trigger_unrelated_work(self):
        dialog=self.settings();g=self.w.graph;selected={str(self.source)};g.set_selection(selected)
        with patch.object(g,'set_graph',wraps=g.set_graph) as redraw,patch.object(self.w,'query_changed') as search:
            for value in range(140,181):dialog.set_value('node_spacing',value/100)
            self.assertEqual(redraw.call_count,0);pump(45);self.assertEqual(redraw.call_count,1)
            self.assertEqual(g.selected_paths,selected);search.assert_not_called()
    def test_flight_minimum_is_visible_and_niri_rule_is_scoped(self):
        with patch.dict(os.environ,{'NIRI_SOCKET':'/test/niri'}):dialog=self.settings()
        text=' '.join(label.text() for label in dialog.findChildren(QLabel))
        self.assertIn('minimum 150 ms',text.lower());self.assertIn('solid border/focus-ring background',text)
        rule=(Path(__file__).resolve().parents[1]/'assets/niri-window-rule.kdl').read_text()
        self.assertIn('match app-id="^io[.]github[.]orbitexplorer[.]Orbit$"',rule)
        self.assertIn('draw-border-with-background false',rule)

class FontTests(unittest.TestCase):
    def test_packaged_policy_respects_explicit_overrides_and_does_not_leak_to_host(self):
        root=Path(__file__).resolve().parents[1]
        with patch.object(sys,'frozen',True,create=True),patch.object(sys,'_MEIPASS',str(root),create=True),patch.dict(os.environ,{},clear=True):
            runpy.run_path(str(root/'packaging/runtime_fontconfig.py'))
            self.assertEqual(os.environ['FONTCONFIG_FILE'],str(root/'assets/fontconfig/fonts.conf'))
            from desktop_backend import host_environment
            env=host_environment();self.assertNotIn('FONTCONFIG_FILE',env);self.assertNotIn('_ORBIT_BUNDLED_FONTCONFIG',env)
        with patch.object(sys,'frozen',True,create=True),patch.object(sys,'_MEIPASS',str(root),create=True),patch.dict(os.environ,{'FONTCONFIG_FILE':'/my/fonts.conf'},clear=True):
            runpy.run_path(str(root/'packaging/runtime_fontconfig.py'));self.assertEqual(os.environ['FONTCONFIG_FILE'],'/my/fonts.conf')
            self.assertNotIn('_ORBIT_BUNDLED_FONTCONFIG',os.environ)
    @unittest.skipUnless(shutil.which('fc-match'),'Fontconfig tools unavailable')
    def test_bundled_policy_parses_and_finds_installed_fonts(self):
        root=Path(__file__).resolve().parents[1]/'assets/fontconfig'
        result=subprocess.run(['fc-match','sans-serif'],env=dict(os.environ,FONTCONFIG_FILE=str(root/'fonts.conf'),FONTCONFIG_PATH=str(root)),capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('.ttf',result.stdout)
        self.assertNotIn('invalid',result.stderr.lower())

if __name__=='__main__':unittest.main()

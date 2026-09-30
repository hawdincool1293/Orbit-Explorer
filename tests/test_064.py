"""Entrance lifetimes, real geometry, top-pin feedback and patchbay close."""
import json,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint,QEvent,QEasingCurve
from PySide6.QtWidgets import QLabel,QVBoxLayout,QWidget,QPushButton,QCheckBox
from PySide6.QtTest import QTest
import test_04 as fixtures
from test_04 import APP,pump,until
from appearance import load_config
from ui import Settings
from panel_motion import reveal,finish,finish_all

class PolishTests(unittest.TestCase):
    setUp=fixtures.FlowTests.setUp
    def tearDown(self):
        finish_all(self.w)
        fixtures.FlowTests.tearDown(self)
    def test_sidebar_uses_original_cubic_fade_without_resizing(self):
        w=self.w;minimum=w.right.minimumSize();maximum=w.right.maximumSize()
        w.config['panel_motion_duration']=240
        w.graph.set_selection({str(self.source)})
        controller=w.right._entrance_controller
        self.assertTrue(controller.active);self.assertFalse(w.graph.live_resizing)
        self.assertEqual(controller.animation.easingCurve().type(),QEasingCurve.Type.OutCubic)
        pump(35);first=w.right_effect.opacity();pump(75);second=w.right_effect.opacity()
        self.assertGreater(second,first);self.assertLess(first,1.)
        self.assertAlmostEqual(w.right.width(),w.detail_width,delta=2)
        self.assertTrue(until(lambda:w.right._entrance_controller is None))
        self.assertEqual(w.right.minimumSize(),minimum);self.assertEqual(w.right.maximumSize(),maximum)
        self.assertFalse(w.graph.live_resizing);self.assertAlmostEqual(w.right_effect.opacity(),1.)
        self.assertAlmostEqual(w.right.width(),w.detail_width,delta=2)
    def test_disabled_opening_is_instant_and_changes_cancel_active_motion(self):
        w=self.w;w.config['panel_motion_enabled']=False;w.graph.set_selection({str(self.source)})
        self.assertIsNone(getattr(w.right,'_entrance_controller',None));self.assertAlmostEqual(w.right.width(),w.detail_width,delta=2)
        w.graph.set_selection(set());w.config['panel_motion_enabled']=True;w.graph.set_selection({str(self.source)})
        self.assertTrue(w.right._entrance_controller.active)
        w.config['panel_motion_enabled']=False;w.settings_changed()
        self.assertIsNone(w.right._entrance_controller);self.assertFalse(w.graph.live_resizing)
    def test_rapid_open_close_and_divider_interaction_release_animation_cache(self):
        w=self.w;w.graph.set_selection({str(self.source)});w.graph.set_selection(set());pump(20)
        self.assertTrue(until(w.right.isHidden));self.assertFalse(w.graph.live_resizing)
        w.graph.set_selection({str(self.source)})
        handle=w.middle.handle(2)
        QTest.mousePress(handle,Qt.MouseButton.LeftButton,pos=handle.rect().center())
        self.assertIsNone(w.right._entrance_controller)
        self.assertTrue(w.graph.live_resizing)
        QTest.mouseRelease(handle,Qt.MouseButton.LeftButton,pos=handle.rect().center());pump(30)
        self.assertFalse(w.graph.live_resizing)
    def test_new_text_panel_animates_without_replacing_the_editor(self):
        self.w.open_node(str(self.source));self.assertTrue(until(lambda:getattr(self.w.documents,'_entrance_controller',None) is not None))
        controller=self.w.documents._entrance_controller;panel=self.w.documents.panels[str(self.source)];text=panel.text
        self.assertTrue(controller.active);self.assertTrue(until(lambda:panel.busy==0))
        finish(self.w.documents)
        self.assertIs(panel.text,text);self.assertEqual(text.toPlainText(),'unchanged')
        self.assertEqual(self.w.documents.maximumHeight(),16777215)
    def test_concurrent_file_entrances_keep_the_graph_cache_until_both_finish(self):
        from PySide6.QtGui import QImage,QColor
        self.w.config['panel_motion_duration']=1000
        self.w.open_node(str(self.source));self.assertTrue(until(lambda:getattr(self.w.documents,'_entrance_controller',None) is not None))
        image=self.root/'picture.png';pixels=QImage(40,20,QImage.Format.Format_RGB32);pixels.fill(QColor('#55aacc'));pixels.save(str(image))
        self.w.open_node(str(image));panel=self.w.documents.panels[str(image)]
        self.assertTrue(until(lambda:getattr(panel,'_entrance_controller',None) is not None))
        finish(panel);self.assertTrue(self.w.graph.live_resizing)
        finish(self.w.documents);self.assertFalse(self.w.graph.live_resizing)
        self.assertTrue(until(lambda:all(not p.busy for p in self.w.documents.panels.values())))
        self.assertEqual(panel.maximumWidth(),16777215)
        self.assertEqual(panel.maximumHeight(),16777215)

    def test_closing_a_viewport_during_file_motion_does_not_use_deleted_graphs(self):
        self.w.new_tile(True);pump(30)
        self.w.config['panel_motion_duration']=1000
        self.w.open_node(str(self.source));self.assertTrue(until(lambda:getattr(self.w.documents,'_entrance_controller',None) is not None))
        self.w.workspace.close_tile(self.w.workspace.active);pump(40)
        finish(self.w.documents);self.assertFalse(self.w.graph.live_resizing)
        self.assertTrue(until(lambda:all(not p.busy for p in self.w.documents.panels.values())))

    def test_animation_settings_persist_and_legacy_bounce_does_not_change_curve(self):
        dialog=Settings(self.w.config,self.w);dialog.changed.connect(self.w.settings_changed)
        dialog.findChild(QCheckBox,'panel_motion_files').setChecked(False)
        dialog.set_value('panel_motion_duration',540);dialog.set_value('panel_motion_fps',144)
        self.w.save_settings_now();config=load_config()
        self.assertEqual(config['panel_motion_duration'],540);self.assertFalse(config['panel_motion_files'])
        self.assertEqual(config['panel_motion_fps'],144)
        self.w.graph.set_selection({str(self.source)});controller=self.w.right._entrance_controller
        self.assertEqual(controller.animation.easingCurve().type(),QEasingCurve.Type.OutCubic)
        dialog.deleteLater()
    def test_dialog_content_motion_restores_margins_and_close_stops_backend(self):
        from routing import RoutingDialog,PipeWire
        with patch.object(PipeWire,'start') as start,patch.object(PipeWire,'stop') as stop:
            dialog=RoutingDialog(self.w.config,self.w);margins=dialog.layout().contentsMargins();dialog.show();pump(35)
            self.assertTrue(dialog._entrance_controller.active);start.assert_called_once()
            QTest.mouseClick(dialog.close_button,Qt.MouseButton.LeftButton);pump(30)
            self.assertTrue(until(lambda:not dialog.isVisible()));self.assertIsNone(dialog._entrance_controller)
            self.assertEqual(dialog.layout().contentsMargins(),margins);self.assertTrue(stop.called)
            dialog.show();pump(20);self.assertEqual(start.call_count,2);dialog.close();dialog.deleteLater()
    def test_top_pins_hover_press_and_leave_give_visible_feedback(self):
        g=self.w.graph;self.w.config['panel_motion_enabled']=False
        self.w.pin(str(self.destination));pump(30);g.grab()
        rect=next(rect for rect,path in g.favorite_rects if path==str(self.destination));pos=rect.center().toPoint()
        QTest.mouseMove(g,QPoint(5,g.height()-50));pump(20);normal=g.grab().toImage()
        QTest.mouseMove(g,pos);pump(20);hover=g.grab().toImage()
        self.assertEqual(g.hover_path,str(self.destination));self.assertEqual(g.cursor().shape(),Qt.CursorShape.PointingHandCursor)
        self.assertNotEqual(normal,hover)
        QTest.mousePress(g,Qt.MouseButton.LeftButton,pos=pos);pump(20)
        self.assertEqual(g.favorite_pressed,str(self.destination));pressed=g.grab().toImage();self.assertNotEqual(hover,pressed)
        QTest.mouseRelease(g,Qt.MouseButton.LeftButton,pos=pos);pump(20);self.assertEqual(g.favorite_pressed,'')
        APP.sendEvent(g,QEvent(QEvent.Type.Leave));self.assertEqual(g.hover_path,'')
    def test_live_panel_motion_keeps_pin_feedback_and_does_not_rebuild_cloud_per_frame(self):
        w=self.w;g=w.graph;w.pin(str(self.destination));pump(30);g.grab()
        with patch.object(g,'render_scene',wraps=g.render_scene) as render:
            g.set_selection({str(self.source)});pump(70)
            self.assertFalse(g.live_resizing);QTest.mouseMove(g,QPoint(45,39));pump(30)
            # One scene update for the initial width/selection, one for hover;
            # no scene rebuild for each opacity frame.
            self.assertLessEqual(render.call_count,2);self.assertEqual(g.hover_path,str(self.destination))
            self.assertTrue(g.favorite_rects)
            finish(w.right);pump(20);self.assertGreater(render.call_count,0)

if __name__=='__main__':unittest.main()

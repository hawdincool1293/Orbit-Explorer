"""Exit completion, reversal, data safety and existing bar lifetimes."""
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt,QEasingCurve
from PySide6.QtWidgets import QLabel,QVBoxLayout,QDialog
import test_04 as fixtures
from test_04 import APP,pump,until
from panel_motion import finish,finish_all
from design import SurfaceDialog

class ExitTests(unittest.TestCase):
    setUp=fixtures.FlowTests.setUp
    def tearDown(self):
        finish_all(self.w)
        fixtures.FlowTests.tearDown(self)
    def select(self):
        self.w.graph.set_selection({str(self.source)});finish(self.w.right)
    def test_sidebar_fades_out_in_place_and_hides_only_after_completion(self):
        self.select();width=self.w.right.width();self.w.config['panel_motion_duration']=240
        self.w.graph.set_selection(set());controller=self.w.right._entrance_controller
        self.assertTrue(controller.exiting);self.assertTrue(self.w.right.isVisible())
        self.assertEqual(controller.animation.easingCurve().type(),QEasingCurve.Type.OutCubic)
        pump(50);first=self.w.right_effect.opacity();self.assertEqual(self.w.right.width(),width)
        pump(100);self.assertLess(self.w.right_effect.opacity(),first)
        self.assertTrue(until(self.w.right.isHidden));self.assertEqual(self.w.detail_width,width)
        self.assertFalse(self.w.graph.live_resizing);self.assertEqual(self.w.right.minimumWidth(),250)
    def test_sidebar_reopen_reverses_pending_hide_and_keeps_sizes(self):
        self.select();width=self.w.right.width();self.w.graph.set_selection(set());pump(70)
        self.w.graph.set_selection({str(self.source)});controller=self.w.right._entrance_controller
        self.assertFalse(controller.exiting);self.assertTrue(self.w.right.isEnabled())
        self.assertTrue(until(lambda:self.w.right._entrance_controller is None));pump(80)
        self.assertTrue(self.w.right.isVisible());self.assertAlmostEqual(self.w.right.width(),width,delta=2)
    def test_disabled_motion_closes_instantly_and_stale_bounce_is_ignored(self):
        self.select();self.w.config['panel_motion_bounce']=0;self.w.graph.set_selection(set())
        self.assertEqual(self.w.right._entrance_controller.animation.easingCurve().type(),QEasingCurve.Type.OutCubic)
        finish(self.w.right);self.w.graph.set_selection({str(self.source)});finish(self.w.right)
        self.w.config['panel_motion_enabled']=False;self.w.graph.set_selection(set());self.assertTrue(self.w.right.isHidden())
    def test_file_close_defers_removal_blocks_edits_and_reopen_cancels_close(self):
        w=self.w;w.open_node(str(self.source));panel=w.documents.panels[str(self.source)]
        self.assertTrue(until(lambda:not panel.busy));finish(w.documents)
        w.documents.close_panel(panel);self.assertIn(panel.path,w.documents.panels)
        self.assertFalse(panel.isEnabled());self.assertTrue(w.documents._entrance_controller.exiting)
        pump(60);w.open_node(panel.path);self.assertIs(w.documents.panels[panel.path],panel);self.assertTrue(panel.isEnabled())
        self.assertTrue(until(lambda:getattr(w.documents,'_entrance_controller',None) is None));pump(70)
        self.assertIn(panel.path,w.documents.panels);self.assertFalse(panel.closed)
        w.documents.close_panel(panel);self.assertTrue(until(lambda:panel.path not in w.documents.panels))
        self.assertTrue(w.documents.isHidden());self.assertFalse(w.graph.live_resizing)
    def test_dialog_accept_emits_result_once_after_exit_and_early_close_is_not_reopened(self):
        dialog=SurfaceDialog(self.w.config,self.w);box=QVBoxLayout(dialog);box.addWidget(QLabel('Dialog'))
        result=[];dialog.finished.connect(result.append);dialog.show();pump(30);finish(dialog)
        dialog.accept();self.assertTrue(dialog.isVisible());self.assertEqual(result,[])
        self.assertTrue(dialog._entrance_controller.exiting);self.assertTrue(until(lambda:not dialog.isVisible()))
        self.assertEqual(result,[QDialog.DialogCode.Accepted]);dialog.deleteLater()
        early=SurfaceDialog(self.w.config,self.w);QVBoxLayout(early).addWidget(QLabel('Early close'))
        early.show();early.close();self.assertTrue(until(lambda:not early.isVisible()));pump(60);self.assertFalse(early.isVisible());early.deleteLater()
    def test_spotlight_and_command_bar_have_exit_motion_and_reopen_correctly(self):
        w=self.w;w.open_search('p note');pump(30);finish(w.spotlight);finish(w.right)
        self.assertFalse(w.graph.live_resizing)
        w.clear_search();self.assertTrue(w.spotlight._entrance_controller.exiting);self.assertTrue(w.spotlight.isVisible())
        w.open_search('p note');self.assertFalse(w.spotlight._entrance_controller.exiting)
        self.assertTrue(w.spotlight.edit.hasFocus());finish(w.spotlight)
        w.spotlight.dismiss();self.assertTrue(until(w.spotlight.isHidden))
        w.command.reveal();pump(20);finish(w.command);height=w.command.height()
        w.command.dismiss();self.assertTrue(w.command._entrance_controller.exiting)
        w.command.reveal();pump(30);finish(w.command);self.assertTrue(w.command.isVisible());self.assertAlmostEqual(w.command.height(),height,delta=2)
        w.command.dismiss();self.assertTrue(until(w.command.isHidden))
    def test_fade_exit_does_not_rebuild_cloud_per_frame(self):
        self.select();graph=self.w.graph;graph.grab()
        with patch.object(graph,'render_scene',wraps=graph.render_scene) as render:
            self.w.graph.set_selection(set());pump(100);self.assertLessEqual(render.call_count,1)
            count=render.call_count;finish(self.w.right);pump(20)
            # Hiding the bar restores the graph's final width once.
            self.assertLessEqual(render.call_count,count+1)

if __name__=='__main__':unittest.main()

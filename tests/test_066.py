"""Original-style curves and bounded, high-rate panel animation work."""
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt,QEasingCurve
from PySide6.QtWidgets import QComboBox,QCheckBox
import test_04 as fixtures
from test_04 import APP,pump,until
from appearance import defaults,load_config
from panel_motion import finish,finish_all,reveal
from ui import Settings
from core import Node,_sphere


class MotionTests(unittest.TestCase):
    setUp=fixtures.FlowTests.setUp
    def tearDown(self):
        finish_all(self.w);fixtures.FlowTests.tearDown(self)

    def test_curve_matches_original_sidebar_and_labels_even_with_stale_bounce(self):
        self.w.config['panel_motion_bounce']=100
        self.w.graph.set_selection({str(self.source)});motion=self.w.right._entrance_controller
        curve=motion.animation.easingCurve()
        self.assertEqual(curve.type(),QEasingCurve.Type.OutCubic)
        for i in range(101):
            t=i/100;self.assertAlmostEqual(curve.valueForProgress(t),1-(1-t)**3)
        motion.step(.25);self.assertAlmostEqual(self.w.right_effect.opacity(),.25)
        finish(self.w.right);self.w.graph.set_selection(set())
        self.assertEqual(self.w.right._entrance_controller.animation.easingCurve().type(),curve.type())

    def test_frame_rate_choices_and_area_toggles_persist_without_bounce_control(self):
        self.assertEqual(defaults()['panel_motion_fps'],120)
        self.assertEqual(defaults()['panel_motion_duration'],240)
        dialog=Settings(self.w.config,self.w);dialog.changed.connect(self.w.settings_changed)
        self.addCleanup(dialog.deleteLater)
        rate=dialog.findChild(QComboBox,'panelMotionFrameRate')
        self.assertEqual([rate.itemData(i) for i in range(rate.count())],[60,120,144,240])
        rate.setCurrentIndex(2)
        for key in ('panel_motion_sidebar','panel_motion_dialogs','panel_motion_files'):
            dialog.findChild(QCheckBox,key).setChecked(False)
        self.w.save_settings_now();saved=load_config()
        self.assertEqual(saved['panel_motion_fps'],144)
        self.assertFalse(saved['panel_motion_sidebar']);self.assertFalse(saved['panel_motion_dialogs']);self.assertFalse(saved['panel_motion_files'])
        self.assertIsNone(dialog.findChild(QCheckBox,'panel_motion_bounce'))
        self.w.graph.set_selection({str(self.source)})
        self.assertIsNone(getattr(self.w.right,'_entrance_controller',None))

    def test_wall_clock_progress_does_not_queue_catchup_and_timer_stops(self):
        self.w.config.update(panel_motion_duration=1000,panel_motion_fps=240)
        self.w.graph.set_selection({str(self.source)});motion=self.w.right._entrance_controller
        self.assertEqual(motion.frame_timer.timerType(),Qt.TimerType.PreciseTimer)
        self.assertEqual(motion.frame_timer.interval(),4);self.assertTrue(motion.frame_timer.isActive())
        motion.frame_timer.stop()
        class Clock:
            time=700
            def elapsed(self):return self.time
        clock=Clock();motion.clock=clock
        with patch.object(motion,'step',wraps=motion.step):
            motion.advance()
            self.assertAlmostEqual(motion.value,1-(1-.7)**3)
        clock.time=9000;motion.advance()
        self.assertFalse(motion.active);self.assertFalse(motion.frame_timer.isActive())
        self.assertIsNone(self.w.right._entrance_controller)
        self.assertFalse(self.w.right_effect.isEnabled())

    def test_fades_do_not_change_geometry_and_disabling_fade_is_instant(self):
        self.w.command.reveal();pump(20);motion=self.w.command._entrance_controller
        rect=self.w.command.geometry();margins=self.w.command.layout().contentsMargins()
        motion.step(.2);self.assertEqual(self.w.command.geometry(),rect)
        self.assertEqual(self.w.command.layout().contentsMargins(),margins)
        finish(self.w.command)
        self.w.config['panel_motion_fade']=False;self.w.command.dismiss()
        self.assertTrue(self.w.command.isHidden());self.assertIsNone(self.w.command._entrance_controller)
        self.w.command.reveal();pump(20);self.assertTrue(self.w.command.isVisible())
        self.assertIsNone(self.w.command._entrance_controller)

    def test_reversal_starts_at_current_opacity_and_uses_remaining_duration(self):
        self.w.config['panel_motion_duration']=1000
        self.w.graph.set_selection({str(self.source)});opening=self.w.right._entrance_controller
        opening.frame_timer.stop();opening.step(.4)
        self.w.graph.set_selection(set());closing=self.w.right._entrance_controller
        self.assertAlmostEqual(closing.value,.4)
        self.assertAlmostEqual(self.w.right_effect.opacity(),.4)
        self.assertEqual(closing.animation.duration(),400)
        closing.frame_timer.stop();closing.step(.2)
        self.w.graph.set_selection({str(self.source)});reopened=self.w.right._entrance_controller
        self.assertAlmostEqual(reopened.value,.2);self.assertEqual(reopened.animation.duration(),800)
        self.assertFalse(closing.active);self.assertFalse(closing.frame_timer.isActive())

    def test_dense_cloud_is_not_reprojected_or_rendered_each_file_transition_frame(self):
        g=self.w.graph;root=str(self.root)
        nodes=[Node(root,'root',True,0,0,(0,0,0),None)]
        nodes.extend(Node(root+f'/node-{i}.txt',f'node-{i}.txt',False,4096,1,_sphere(i,679,700),root) for i in range(679))
        g.set_graph(root,nodes);g.grab()
        self.w.config['panel_motion_duration']=1000
        self.w.open_node(str(self.source))
        self.assertTrue(until(lambda:getattr(self.w.documents,'_entrance_controller',None) is not None))
        motion=self.w.documents._entrance_controller;motion.frame_timer.stop()
        with patch.object(g,'render_scene',wraps=g.render_scene) as render:
            for i in range(1,61):motion.step(i/80);APP.processEvents()
            self.assertEqual(render.call_count,0)
            finish(self.w.documents);APP.processEvents();self.assertGreater(render.call_count,0)
        self.assertTrue(until(lambda:all(not p.busy for p in self.w.documents.panels.values())))

    def test_identical_pixel_extents_skip_redundant_splitter_layout(self):
        self.w.config['panel_motion_duration']=1000;self.w.open_node(str(self.source))
        self.assertTrue(until(lambda:getattr(self.w.documents,'_entrance_controller',None) is not None))
        motion=self.w.documents._entrance_controller;motion.frame_timer.stop()
        with patch.object(motion.splitter,'setSizes',wraps=motion.splitter.setSizes) as resize:
            motion.step(.5);motion.step(.5);motion.step(.5)
            self.assertEqual(resize.call_count,1)
        finish(self.w.documents)
        self.assertTrue(until(lambda:all(not p.busy for p in self.w.documents.panels.values())))


if __name__=='__main__':unittest.main()

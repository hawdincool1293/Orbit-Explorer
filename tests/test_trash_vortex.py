"""Trash target behavior without touching the user's real Trash."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from app import Orbit
from interactions import file_mime

APP = QApplication.instance() or QApplication([])


def pump(ms=100):
    deadline = time.monotonic()+ms/1000
    while time.monotonic() < deadline:
        APP.processEvents(); time.sleep(.005)


def until(condition):
    deadline = time.monotonic()+3
    while time.monotonic() < deadline:
        if condition(): return True
        pump(15)
    return condition()


class TrashVortexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="orbit-trash-test-")
        self.root = Path(self.temp.name)
        self.file = self.root/"A note.txt"; self.file.write_text("Keep this")
        self.folder = self.root/"Folder"; self.folder.mkdir()
        self.child = self.folder/"Nested.txt"; self.child.write_text("Also keep this")
        config = self.root/"settings.json"; config.write_text(json.dumps({"last_path":str(self.root)}))
        self.patches = [patch("appearance.CONFIG", config), patch("app.visible_mounts", return_value=[])]
        for item in self.patches: item.start()
        self.w = Orbit(); self.errors = []; self.w.error = self.errors.append
        self.w.show()
        self.assertTrue(until(lambda:self.w.location==str(self.root)))
        QTest.mouseMove(self.w.graph, QPoint(40, 85)); pump(100)
        self.target = self.w.trash_vortex

    def tearDown(self):
        self.w.close(); pump(100)
        for item in self.patches: item.stop()
        self.temp.cleanup()

    def enter_drag(self, paths=None, action=Qt.DropAction.CopyAction):
        mime = file_mime(paths or [str(self.file)])
        event = QDragEnterEvent(QPoint(88, 62), action, mime,
                                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        APP.sendEvent(self.target, event)
        return mime, event

    def drop(self, mime):
        event = QDropEvent(QPointF(88, 62), Qt.DropAction.CopyAction|Qt.DropAction.MoveAction,
                          mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        APP.sendEvent(self.target, event)
        return event

    def test_hover_reveals_and_leaving_hides_core_but_keeps_beacon_running(self):
        QTest.mouseMove(self.target, QPoint(88, 62)); pump(360)
        self.assertGreater(self.target.reveal, .95)
        QTest.mouseMove(self.w.graph, QPoint(40, 85)); pump(600)
        self.assertLess(self.target.reveal, .01)
        self.assertTrue(self.target.timer.isActive())
        self.w.hide(); pump(20); self.assertFalse(self.target.timer.isActive())

    def test_click_opens_local_trash_in_orbit_without_deleting_anything(self):
        with patch.dict(os.environ,{'XDG_DATA_HOME':str(self.root/'data')}),patch("app.QDesktopServices.openUrl") as opened:
            QTest.mouseClick(self.target, Qt.MouseButton.LeftButton, pos=QPoint(88, 62))
            self.assertTrue(until(lambda:self.w.location==str(self.root/'data/Trash/files')))
            opened.assert_not_called()
        self.assertTrue(self.file.exists())

    def test_idle_caption_area_passes_node_clicks_and_minimizing_pauses_animation(self):
        pump(600)
        self.assertFalse(self.target.mask().contains(QPoint(20,135)))
        self.w.showMinimized(); pump(40)
        self.assertFalse(self.target.timer.isActive())
        self.w.showNormal(); pump(50)
        self.assertTrue(self.target.timer.isActive())

    def test_drag_hover_cancels_spring_open_and_can_be_retried(self):
        self.w.spring.hover(str(self.folder)); self.assertTrue(self.w.spring.timer.isActive())
        _, entered = self.enter_drag()
        self.assertTrue(entered.isAccepted()); self.assertTrue(self.target.dragging)
        self.assertFalse(self.w.spring.timer.isActive())
        APP.sendEvent(self.target, QDragLeaveEvent())
        self.assertFalse(self.target.dragging)
        _, retried = self.enter_drag(); self.assertTrue(retried.isAccepted())
        self.assertTrue(self.file.exists())

    def test_canceling_drop_never_trashes_or_requests_source_deletion(self):
        with patch("app.QMessageBox.question", return_value=QMessageBox.StandardButton.No), \
             patch("app.subprocess.run") as run:
            mime, _ = self.enter_drag(); event = self.drop(mime); pump(100)
            self.assertTrue(event.isAccepted())
            self.assertEqual(event.dropAction(), Qt.DropAction.CopyAction)
            run.assert_not_called()
        self.assertTrue(self.file.exists()); self.assertLess(self.target._success_at, 0)

    def test_confirmed_multi_file_drop_uses_gio_and_celebrates_after_success(self):
        result = subprocess.CompletedProcess([], 0, "", "")
        with patch("app.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes), \
             patch("app.subprocess.run", return_value=result) as run:
            mime, _ = self.enter_drag([str(self.file), str(self.child)])
            self.drop(mime)
            self.assertTrue(until(lambda:self.target._success_at > 0))
            command = run.call_args.args[0]
            self.assertEqual(command[:3], ["gio", "trash", "--"])
            self.assertEqual(set(command[3:]), {str(self.file), str(self.child)})
            self.assertGreater(self.target._success_at, 0)
        self.assertFalse(self.errors)

    def test_failed_trash_reports_error_without_success_animation(self):
        result = subprocess.CompletedProcess([], 1, "", "Permission denied")
        with patch("app.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes), \
             patch("app.subprocess.run", return_value=result):
            mime, _ = self.enter_drag(); self.drop(mime)
            self.assertTrue(until(lambda:bool(self.errors)))
            self.assertEqual(self.errors, ["Permission denied"])
            self.assertLess(self.target._success_at, 0)
        self.assertTrue(self.file.exists())

    def test_rejects_protected_locations_and_move_only_source(self):
        _, event = self.enter_drag(["/", str(self.root)])
        self.assertFalse(event.isAccepted()); self.assertFalse(self.target.dragging)
        _, event = self.enter_drag(action=Qt.DropAction.MoveAction)
        self.assertFalse(event.isAccepted())
        self.assertEqual(self.w.trash_candidates([str(self.folder),str(self.child)]), [str(self.folder)])

    def test_corner_anchor_follows_sidebar_splits_and_resize(self):
        self.w.graph.set_selection({str(self.file)}); pump(300)
        self.w.new_tile(True); self.w.resize(1240, 760); pump(100)
        self.assertEqual(self.target.x()+self.target.width(), self.w.workspace.width()-8)
        self.assertEqual(self.target.y()+self.target.height(), self.w.workspace.height()-6)
        self.assertIs(self.w.workspace.childAt(self.target.geometry().center()), self.target)


if __name__ == "__main__":
    unittest.main()

"""Live layout behavior, real media/documents, drive aliases and safe file writes."""
import io,json,os,shutil,stat,subprocess,tarfile,tempfile,time,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QImage,QColor,QPainter,QPdfWriter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
import test_04 as fixtures
from test_04 import APP,pump,until
from core import drive_inventory,drive_key,drive_name
from file_tools import read_text,save_text,extract_archive,archive_contents
from trash_paths import home_trash,trash_locations

class FileSafetyTests(unittest.TestCase):
    def test_text_saves_preserve_encoding_newlines_permissions_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);file=root/'script.sh';file.write_bytes(b'one\r\ntwo\r\n');file.chmod(0o750)
            link=root/'alias.sh';link.symlink_to(file);original=read_text(link)
            save_text(link,'new\nlines\n',original)
            self.assertTrue(link.is_symlink());self.assertEqual(file.read_bytes(),b'new\r\nlines\r\n')
            self.assertEqual(stat.S_IMODE(file.stat().st_mode),0o750)
            original=read_text(file);file.write_text('External edit')
            with self.assertRaisesRegex(ValueError,'changed outside'):save_text(file,'My edit',original)
            self.assertEqual(file.read_text(),'External edit')
    def test_binary_data_is_never_silently_edited(self):
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/'data.txt';file.write_bytes(b'bad\0binary')
            with self.assertRaises(ValueError):read_text(file)
    def test_zip_and_tar_extract_to_fresh_folders_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive=root/'notes.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('folder/note.txt','hello')
            a=Path(extract_archive(archive,root));b=Path(extract_archive(archive,root))
            self.assertNotEqual(a,b);self.assertEqual((a/'folder/note.txt').read_text(),'hello')
            tar=root/'notes.tar.gz'
            with tarfile.open(tar,'w:gz') as t:
                item=tarfile.TarInfo('./');item.type=tarfile.DIRTYPE;t.addfile(item)
                item=tarfile.TarInfo('nested.txt');item.size=5;t.addfile(item,io.BytesIO(b'hello'))
            self.assertEqual((Path(extract_archive(tar,root))/'nested.txt').read_bytes(),b'hello')
    def test_archive_traversal_and_links_are_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('../escaped.txt','/absolute.txt','C:\\bad.txt','..\\escaped.txt'):
                archive=root/'bad.zip'
                with zipfile.ZipFile(archive,'w') as z:z.writestr(name,'bad')
                with self.assertRaises(ValueError):extract_archive(archive,root)
                self.assertEqual(list(root.iterdir()),[archive])
            with zipfile.ZipFile(archive,'w') as z:
                item=zipfile.ZipInfo('link');item.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(item,'/etc/passwd')
            with self.assertRaises(ValueError):archive_contents(archive)
    def test_xdg_home_and_per_user_mounted_trash_locations(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with patch.dict(os.environ,{'XDG_DATA_HOME':str(root/'data')}):self.assertEqual(home_trash(),root/'data/Trash/files')
            with patch.dict(os.environ,{'XDG_DATA_HOME':'relative'}),patch('trash_paths.Path.home',return_value=root):self.assertEqual(home_trash(),root/'.local/share/Trash/files')
            mounted=root/f'.Trash-{os.getuid()}/files';mounted.mkdir(parents=True)
            self.assertIn(mounted,[p for label,p in trash_locations([{'mount':temp,'name':'USB'}])])

class NativePanelTests(unittest.TestCase):
    setUp=fixtures.FlowTests.setUp
    def tearDown(self):
        for panel in self.w.documents.panels.values():
            until(lambda:panel.busy==0)
            if panel.text:panel.text.document().setModified(False)
        fixtures.FlowTests.tearDown(self)
    def open(self,path):
        self.w.open_node(str(path));self.assertIn(str(path),self.w.documents.panels,self.errors)
        panel=self.w.documents.panels[str(path)];self.assertTrue(until(lambda:panel.busy==0));return panel
    def test_drive_alias_survives_device_order_and_appears_in_graph(self):
        drive=drive_inventory({'blockdevices':[{'name':'sda','path':'/dev/sda','type':'disk','serial':'ABC','model':'Hardware name','size':'1T'}]})[0]
        self.w.got_drives([drive],'');self.w.set_drive_alias(drive,'Games')
        moved=dict(drive,path='/dev/sdc',name='sdc')
        self.assertEqual(drive_key(drive),drive_key(moved));self.assertEqual(drive_name(moved,self.w.config),'Games')
        self.w.show_drive(moved);self.assertEqual(self.w.graph.nodes[0].name,'Games')
        self.assertEqual(json.loads((self.root/'settings.json').read_text())['drive_aliases']['serial:ABC'],'Games')
    def test_divider_resizes_before_release_and_reuses_graph_cache(self):
        splitter=self.w.middle;handle=splitter.handle(1);g=self.w.graph;pump(60)
        before=self.w.sidebar.width();point=handle.rect().center()
        with patch.object(g,'render_scene',wraps=g.render_scene) as render:
            QTest.mousePress(handle,Qt.MouseButton.LeftButton,pos=point)
            self.assertTrue(g.live_resizing)
            QTest.mouseMove(handle,point+QPoint(90,0));pump(30)
            self.assertGreater(self.w.sidebar.width(),before+30);self.assertEqual(render.call_count,0)
            QTest.mouseRelease(handle,Qt.MouseButton.LeftButton,pos=handle.rect().center());pump(50)
            self.assertFalse(g.live_resizing);self.assertGreater(render.call_count,0)
        for pane in self.w.saved_splitters.values():self.assertTrue(pane.opaqueResize())
        self.assertEqual(self.w.center.count(),2)
    def test_text_editor_save_conflict_and_unsaved_close(self):
        path=self.root/'notes.md';path.write_text('Original')
        panel=self.open(path);self.assertEqual(panel.text.toPlainText(),'Original')
        panel.text.appendPlainText('New');panel.save();self.assertTrue(until(lambda:panel.busy==0))
        self.assertIn('New',path.read_text());self.assertFalse(panel.text.document().isModified())
        path.write_text('External');panel.text.appendPlainText('Mine');panel.save();self.assertTrue(until(lambda:panel.busy==0))
        self.assertIn('changed outside',panel.status.text());self.assertEqual(path.read_text(),'External')
        with patch('viewers.QMessageBox.question',return_value=QMessageBox.StandardButton.Cancel):self.w.documents.close_panel(panel)
        self.assertIn(str(path),self.w.documents.panels)
        with patch('viewers.QMessageBox.question',return_value=QMessageBox.StandardButton.Discard):self.w.documents.close_panel(panel)
        self.assertTrue(until(lambda:str(path) not in self.w.documents.panels))
        panel=self.open(path);panel.text.appendPlainText('Save before close')
        with patch('viewers.QMessageBox.question',return_value=QMessageBox.StandardButton.Save):
            self.w.documents.close_panel(panel)
            self.assertTrue(until(lambda:str(path) not in self.w.documents.panels))
        self.assertIn('Save before close',path.read_text())
    def test_images_pdf_archive_and_tethers_open_inside_orbit(self):
        picture=self.root/'photo.png';image=QImage(180,100,QImage.Format.Format_RGB32);image.fill(QColor('#55aa88'));image.save(str(picture))
        image_panel=self.open(picture);self.assertEqual(image_panel.canvas.image.width(),180)
        pdf=self.root/'read.pdf';writer=QPdfWriter(str(pdf));painter=QPainter(writer);painter.drawText(80,160,'Native PDF');painter.end();del writer
        pdf_panel=self.open(pdf);self.assertEqual(pdf_panel.pdf.pageCount(),1)
        archive=self.root/'sample.zip'
        with zipfile.ZipFile(archive,'w') as z:z.writestr('notes.txt','Inside archive')
        panel=self.open(archive);self.assertEqual(panel.entries.topLevelItemCount(),1)
        panel.extract_to(self.root);self.assertTrue(until(lambda:panel.busy==0));self.assertEqual((self.root/'sample extracted/notes.txt').read_text(),'Inside archive')
        self.w.connections.refresh();self.assertEqual({p for _,_,p,_ in self.w.connections.segments},{str(picture),str(pdf),str(archive)})
        self.w.documents.close_panel(pdf_panel)
        self.assertTrue(until(lambda:str(pdf) not in self.w.documents.panels))
        self.w.connections.refresh();self.assertEqual(len(self.w.connections.segments),2)
    def test_audio_buttons_use_visible_vector_icons(self):
        from media import AudioDock
        audio=AudioDock(self.w.config,self.w.workspace);audio.show();pump(30)
        for button in (audio.toggle,audio.mute,audio.close_button):
            self.assertFalse(button.icon().isNull());self.assertEqual(button.property('role'),'icon');self.assertGreaterEqual(button.height(),30)
        audio.mute.click();self.assertTrue(audio.output.isMuted());audio.close_button.click()
        self.assertTrue(until(lambda:not audio.isVisible()));audio.deleteLater()
    @unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg required for real media fixtures')
    def test_video_and_animated_gif_use_native_decoders(self):
        video=self.root/'clip.mp4';gif=self.root/'animation.gif'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc=size=128x96:rate=5','-t','0.6','-pix_fmt','yuv420p',str(video)],check=True,capture_output=True,timeout=15)
        subprocess.run(['ffmpeg','-v','error','-i',str(video),str(gif)],check=True,capture_output=True,timeout=15)
        panel=self.open(video);self.assertTrue(until(lambda:panel.player.duration()>0))
        self.assertTrue(until(lambda:panel.editor.video.videoSink().videoFrame().isValid()));panel.player.pause()
        animated=self.open(gif);self.assertTrue(until(lambda:not animated.canvas.pixmap.isNull()))
        self.assertGreater(animated.movie.frameCount(),1)

if __name__=='__main__':unittest.main()

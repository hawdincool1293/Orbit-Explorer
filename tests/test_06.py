import os,copy,json,tempfile,unittest,subprocess,zipfile,shutil
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QEvent,QPoint,QPointF,QRectF
from PySide6.QtGui import QImage,QColor,QPainter,QPdfWriter,QDropEvent,QDragEnterEvent
from PySide6.QtWidgets import QMessageBox
from PySide6.QtTest import QTest
import test_04 as fixtures
from test_04 import APP,pump,until
from app import Orbit
from media_tools import Clip,probe,split_clip,stitch,timeline_args,video_formats,conversion_args,audio_formats
from export_job import ExportJob
from image_editor import image_bytes,write_image
from file_tools import compress_zip,extract_here,extract_archive
from trash_paths import delete_trashed,containing_trash
from interactions import file_mime
from conversion import convert_document,convert_archive

class DataTests(unittest.TestCase):
    def test_zip_roundtrip_extract_here_and_collision_refusal(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();(source/'file.txt').write_text('payload');(source/'empty').mkdir()
            archive=root/'bundle.zip';compress_zip([str(source)],archive);dest=root/'dest';dest.mkdir();extract_here(archive,dest)
            self.assertEqual((dest/'source/file.txt').read_text(),'payload');self.assertTrue((dest/'source/empty').is_dir())
            with self.assertRaises(FileExistsError):extract_here(archive,dest)
            tar=root/'converted.tar.xz';convert_archive(archive,tar,'tar.xz');out=Path(extract_archive(tar,root))
            self.assertEqual((out/'source/file.txt').read_text(),'payload')
    def test_permanent_trash_delete_never_follows_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);trash=root/'Trash/files';trash.mkdir(parents=True);info=root/'Trash/info';info.mkdir()
            outside=root/'precious.txt';outside.write_text('keep');link=trash/'link';link.symlink_to(outside);(info/'link.trashinfo').write_text('metadata')
            delete_trashed([str(link)],[trash]);self.assertTrue(outside.exists());self.assertFalse(link.is_symlink());self.assertFalse((info/'link.trashinfo').exists())
            with self.assertRaises(ValueError):delete_trashed([str(outside)],[trash])
            with self.assertRaises(ValueError):delete_trashed([str(trash)],[trash])
            escape=trash/'escape';escape.symlink_to(root,target_is_directory=True)
            self.assertIsNone(containing_trash(escape/'precious.txt',[trash]))
    def test_image_export_dimensions_quality_and_no_overwrite(self):
        image=QImage(180,120,QImage.Format.Format_ARGB32);image.fill(QColor('red'))
        encoded=image_bytes(image,'jpeg',50,90,60);decoded=QImage.fromData(encoded);self.assertEqual(decoded.size().toTuple(),(90,60))
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'new.png';write_image(image,target,'png');before=target.read_bytes()
            with self.assertRaises(FileExistsError):write_image(image,target,'png')
            self.assertEqual(target.read_bytes(),before)
    def test_document_conversion_produces_real_pdf_and_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'read.md';source.write_text('# A heading\n\nHello **Orbit**.')
            convert_document(source,root/'out.pdf','pdf');self.assertTrue((root/'out.pdf').read_bytes().startswith(b'%PDF'))
            convert_document(source,root/'out.txt','txt');self.assertIn('Hello Orbit.',(root/'out.txt').read_text())
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
    def test_real_timeline_exports_trim_stitch_gap_and_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);a=root/'red.mp4';b=root/'blue.mp4'
            for path,color,sound in ((a,'red',True),(b,'blue',False)):
                args=['ffmpeg','-v','error','-f','lavfi','-i',f'color={color}:s=96x64:r=25']
                if sound:args+=['-f','lavfi','-i','sine=frequency=440:sample_rate=48000']
                subprocess.run(args+['-t','1','-pix_fmt','yuv420p',str(path)],check=True,capture_output=True,timeout=15)
            clips=[Clip(str(a),.2,.6,.2,probe(a)),Clip(str(b),.1,.5,1.,probe(b))]
            parts=split_clip(clips[0],.4);self.assertAlmostEqual(sum(c.duration for c in parts),.4)
            joined=copy.deepcopy(clips);stitch(joined);self.assertAlmostEqual(joined[1].start,.4)
            for fmt in video_formats():
                target=root/('out.'+fmt);args=timeline_args(clips,fmt,96,64,25)
                result=subprocess.run(['ffmpeg','-v','error','-filter_complex_threads','1',*args,'-threads','1',str(target)],capture_output=True,timeout=30)
                self.assertEqual(result.returncode,0,(fmt,result.stderr.decode()));self.assertAlmostEqual(probe(target)['duration'],1.4,delta=.2)
            for second,expected in ((.1,'black'),(.3,'red'),(.8,'black'),(1.2,'blue')):
                result=subprocess.run(['ffmpeg','-v','error','-ss',str(second),'-i',str(root/'out.mp4'),'-frames:v','1','-vf','scale=1:1','-pix_fmt','rgb24','-f','rawvideo','pipe:1'],capture_output=True,check=True,timeout=10)
                r,g,b=result.stdout[:3]
                if expected=='black':self.assertLess(max(r,g,b),20)
                elif expected=='red':self.assertGreater(r,150);self.assertLess(b,40)
                else:self.assertGreater(b,150);self.assertLess(r,40)
            for fmt in audio_formats():
                target=root/('sound.'+fmt);result=subprocess.run(['ffmpeg','-v','error',*conversion_args(a,fmt),str(target)],capture_output=True,timeout=15)
                self.assertEqual(result.returncode,0,(fmt,result.stderr.decode()));self.assertTrue(probe(target)['audio'])
    def test_macos_queries_use_spotlight_not_linux_index(self):
        from desktop_backend import index_command
        from search_query import parse_query
        with patch('desktop_backend.IS_MAC',True):
            command=index_command(parse_query('a"b is: png'));self.assertEqual(command[0],'/usr/bin/mdfind');self.assertIn('a\\"b',command[-1])

class Flow06Tests(unittest.TestCase):
    setUp=fixtures.FlowTests.setUp
    def tearDown(self):
        for panel in self.w.documents.panels.values():
            until(lambda:panel.busy==0)
            if panel.editor:panel.editor.modified=False
        fixtures.FlowTests.tearDown(self)
    def open(self,path):
        self.w.open_node(str(path));self.assertIn(str(path),self.w.documents.panels,self.errors)
        panel=self.w.documents.panels[str(path)];self.assertTrue(until(lambda:panel.busy==0));return panel
    def test_left_drop_moves_on_release_without_chooser(self):
        w=self.w;w.pin(str(self.destination));button=w.pin_buttons[str(self.destination)];mime=file_mime([str(self.source)])
        enter=QDragEnterEvent(QPoint(15,15),Qt.DropAction.CopyAction|Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier);APP.sendEvent(button,enter)
        drop=QDropEvent(QPointF(15,15),Qt.DropAction.CopyAction|Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier);APP.sendEvent(button,drop)
        self.assertTrue(until(lambda:(self.destination/self.source.name).exists()));self.assertFalse(self.source.exists());self.assertIsNone(w.drop_dialog)
    def test_cursor_chooser_cancel_is_non_destructive(self):
        self.w.config['drop_popup']='cursor';self.w.choose_drop_action([str(self.source)],str(self.destination),QPoint(300,200));pump(30)
        menu=self.w.drop_dialog;self.assertEqual(menu.actions()[0].text(),'Move here');menu.close();pump(20)
        self.assertTrue(self.source.exists());self.assertFalse((self.destination/self.source.name).exists())
    def test_tab_leaves_every_node_and_camera_stationary(self):
        g=self.w.graph;g.setFocus();pump(40);before={p:QRectF(v[0]) for p,v in g.projected.items()};camera=(g.yaw,g.pitch,g.zoom,g.offset)
        QTest.keyPress(g,Qt.Key.Key_Tab);pump(350)
        self.assertGreater(g.label_amount,.95);self.assertEqual(before,{p:v[0] for p,v in g.projected.items()});self.assertEqual(camera,(g.yaw,g.pitch,g.zoom,g.offset))
        QTest.keyRelease(g,Qt.Key.Key_Tab);pump(350);self.assertLess(g.label_amount,.02)
    def test_workspace_deactivate_resets_stuck_resize_and_repaints(self):
        w=self.w;w.middle.resizing(True);self.assertTrue(w.graph.live_resizing)
        APP.sendEvent(w,QEvent(QEvent.Type.WindowDeactivate));self.assertFalse(w.graph.live_resizing)
        APP.sendEvent(w,QEvent(QEvent.Type.WindowActivate));pump(40);self.assertIsNotNone(w.graph._layer)
        before=w.graph.yaw;QTest.mousePress(w.graph,Qt.MouseButton.MiddleButton,pos=QPoint(100,100));QTest.mouseMove(w.graph,QPoint(150,100));QTest.mouseRelease(w.graph,Qt.MouseButton.MiddleButton,pos=QPoint(150,100));self.assertNotEqual(w.graph.yaw,before)
    def test_layout_and_viewport_split_restore_on_relaunch(self):
        w=self.w;w.resize(1350,900);w.middle.setSizes([325,1000,0]);w.side_sections.setSizes([170,290,190]);w.new_tile(True);pump(50)
        split=w.workspace.splitters[0];split.setSizes([340,560]);before_side=w.sidebar.width();before_sections=w.side_sections.sizes();before_split=split.sizes();w.close();pump(50)
        self.w=Orbit();self.w.error=self.errors.append;self.w.show();pump(250)
        self.assertEqual(len(self.w.workspace.tiles),2);self.assertAlmostEqual(self.w.sidebar.width(),before_side,delta=3)
        self.assertEqual(self.w.side_sections.sizes(),before_sections);self.assertEqual(self.w.workspace.splitters[0].sizes(),before_split)
    def test_ctrl_q_closes_active_duplicate_not_all_tiles(self):
        self.w.new_tile(True);self.assertEqual(len(self.w.workspace.tiles),2)
        QTest.keyClick(self.w.graph,Qt.Key.Key_Q,Qt.KeyboardModifier.ControlModifier);pump(20);self.assertEqual(len(self.w.workspace.tiles),1);self.assertTrue(self.w.isVisible())
    def test_navigation_off_loads_only_destination_and_flight_is_one_animation(self):
        w=self.w;w.config['navigation_enabled']=False
        with patch('app.scan_neighbourhood',wraps=__import__('core').scan_neighbourhood) as scan:
            w.fly_to(str(self.destination));self.assertTrue(until(lambda:w.location==str(self.destination)));self.assertEqual(scan.call_count,1)
        w.config['navigation_enabled']=True;w.config['navigation_duration']=220
        w.fly_to(str(self.source));self.assertTrue(until(lambda:hasattr(w,'flight')));flight=w.flight
        self.assertTrue(until(lambda:str(self.source) in w.graph.selected_paths));self.assertIs(w.animation,flight.anim);self.assertIsNone(w.graph.flight_previous)
    def test_native_image_crop_rotate_draw_and_undo(self):
        path=self.root/'photo.png';image=QImage(120,80,QImage.Format.Format_ARGB32);image.fill(QColor('white'));image.save(str(path))
        editor=self.open(path).editor;editor.canvas.crop=QRectF(10,10,60,40);editor.crop();self.assertEqual(editor.canvas.image.size().toTuple(),(60,40))
        editor.rotate(90);self.assertEqual(editor.canvas.image.size().toTuple(),(40,60));editor.undo();self.assertEqual(editor.canvas.image.size().toTuple(),(60,40))
        editor.canvas.mode='Draw';editor.canvas.color=QColor('red');center=editor.canvas.target().center().toPoint()
        QTest.mousePress(editor.canvas,Qt.MouseButton.LeftButton,pos=center);QTest.mouseMove(editor.canvas,center+QPoint(15,10));QTest.mouseRelease(editor.canvas,Qt.MouseButton.LeftButton,pos=center+QPoint(15,10))
        self.assertTrue(editor.modified);self.assertEqual(QImage(str(path)).size().toTuple(),(120,80))
    @unittest.skipUnless(shutil.which('pdftoppm'),'Poppler fallback unavailable')
    def test_missing_qtpdf_uses_in_app_fallback(self):
        path=self.root/'test.pdf';writer=QPdfWriter(str(path));p=QPainter(writer);p.drawText(100,200,'PDF fallback');p.end();del writer
        with patch('viewers.FilePanel.build_qt_pdf',side_effect=ImportError('libQt6Pdf.so.6 missing')):panel=self.open(path)
        self.assertTrue(until(lambda:not panel.pdf_fallback.canvas.pixmap.isNull()),panel.status.text());self.assertIn('Poppler',panel.status.text())
    def test_empty_trash_requires_confirmation_and_deletes_contents(self):
        data=self.root/'data';trash=data/'Trash/files';trash.mkdir(parents=True);file=trash/'gone.txt';file.write_text('trash')
        with patch.dict(os.environ,{'XDG_DATA_HOME':str(data)}),patch('app.QMessageBox.question',return_value=QMessageBox.StandardButton.No):self.w.empty_trash()
        self.assertTrue(file.exists())
        with patch.dict(os.environ,{'XDG_DATA_HOME':str(data)}),patch('app.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):
            self.w.empty_trash();self.assertTrue(until(lambda:not file.exists()))
        self.assertTrue(trash.exists());self.assertTrue(self.source.exists())

if __name__=='__main__':unittest.main()

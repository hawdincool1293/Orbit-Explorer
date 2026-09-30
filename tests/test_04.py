"""Live path completion, explicit drop choices, typography, and previews."""
import json,os,shutil,subprocess,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPoint,QPointF,Qt
from PySide6.QtGui import QDragEnterEvent,QDropEvent,QFont,QFontDatabase,QImage,QColor
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from app import Orbit
from core import transfer_files
from ui import Settings
from path_bar import SuggestionDelegate

APP=QApplication.instance() or QApplication([])
def pump(ms=100):
    end=time.monotonic()+ms/1000
    while time.monotonic()<end:APP.processEvents();time.sleep(.005)
def until(predicate,seconds=4):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if predicate():return True
        pump(20)
    return predicate()

class FlowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='orbit-flow-');self.root=Path(self.temp.name)
        for folder in ('Pictures','Projects','Public','Archive','My pictures','.private'):(self.root/folder).mkdir()
        self.source=self.root/'p note.txt';self.source.write_text('unchanged')
        self.destination=self.root/'Archive'
        config=self.root/'settings.json';config.write_text(json.dumps({'last_path':str(self.root),'font':'Manrope'}))
        self.patches=[patch('appearance.CONFIG',config),patch('app.visible_mounts',return_value=[])]
        for p in self.patches:p.start()
        self.w=Orbit();self.errors=[];self.w.error=self.errors.append;self.w.show()
        self.assertTrue(until(lambda:self.w.location==str(self.root)));pump(80)
    def tearDown(self):
        self.w.close();pump(100)
        for p in self.patches:p.stop()
        self.temp.cleanup()
    def type_path(self,text):
        entry=self.w.address;entry.setFocus();entry.selectAll();QTest.keyClicks(entry,text)
    def paths(self):return [p for p,_,_ in self.w.address.suggestions.items]
    def drop(self):
        from interactions import file_mime
        self.w.pin(str(self.destination));button=self.w.pin_buttons[str(self.destination)];mime=file_mime([str(self.source)])
        enter=QDragEnterEvent(QPoint(15,15),Qt.DropAction.CopyAction|Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        APP.sendEvent(button,enter);self.assertTrue(enter.isAccepted())
        drop=QDropEvent(QPointF(15,15),Qt.DropAction.CopyAction|Qt.DropAction.MoveAction,mime,Qt.MouseButton.RightButton,Qt.KeyboardModifier.NoModifier)
        APP.sendEvent(button,drop);self.assertTrue(drop.isAccepted());self.assertEqual(drop.dropAction(),Qt.DropAction.CopyAction)
        self.assertTrue(until(lambda:self.w.drop_dialog is not None))
        self.assertTrue(self.source.exists());self.assertFalse((self.destination/self.source.name).exists())
        return self.w.drop_dialog
    def test_native_completion_is_case_insensitive_and_ranks_pins_prefixes_and_folders(self):
        self.w.pin(str(self.root/'Projects'))
        self.type_path(str(self.root)+'/p')
        self.assertTrue(until(lambda:len(self.paths())>=4),self.paths())
        paths=self.paths();self.assertEqual(paths[0],str(self.root/'Projects'))
        self.assertIn(str(self.root/'Pictures'),paths)
        self.assertLess(paths.index(str(self.root/'Pictures')),paths.index(str(self.source)))
        self.assertLess(paths.index(str(self.root/'Public')),paths.index(str(self.root/'My pictures')))
        self.assertNotIn(str(self.root/'.private'),paths)
        self.assertIsInstance(self.w.address.completion.popup().itemDelegate(),SuggestionDelegate)
        self.assertGreaterEqual(self.w.address.completion.popup().sizeHintForRow(0),57)
    def test_enter_confirms_without_navigation_and_second_enter_navigates(self):
        self.type_path(str(self.root)+'/pic')
        self.assertTrue(until(lambda:self.w.address.completion.popup().isVisible()))
        QTest.keyClick(self.w.address,Qt.Key.Key_Return);pump(60)
        self.assertEqual(self.w.address.text(),str(self.root/'Pictures')+'/')
        self.assertEqual(self.w.location,str(self.root))
        QTest.keyClick(self.w.address,Qt.Key.Key_Return)
        self.assertTrue(until(lambda:self.w.location==str(self.root/'Pictures')))
    def test_enter_chooses_a_suggestion_and_rapid_edit_discards_stale_results(self):
        self.type_path(str(self.root)+'/pic')
        self.assertTrue(until(lambda:self.w.address.completion.popup().isVisible()))
        QTest.keyClick(self.w.address,Qt.Key.Key_Return)
        self.assertEqual(self.w.location,str(self.root))
        QTest.keyClick(self.w.address,Qt.Key.Key_Return)
        self.assertTrue(until(lambda:self.w.location==str(self.root/'Pictures')))
        self.type_path(str(self.root)+'/p');self.type_path(str(self.root)+'/arc')
        self.assertTrue(until(lambda:self.paths()==[str(self.root/'Archive')]))
        QTest.keyClick(self.w.address,Qt.Key.Key_Escape);pump(80)
        self.assertFalse(self.w.address.completion.popup().isVisible())
    def test_relative_paths_and_hidden_directory_completion(self):
        self.type_path('pic');self.assertTrue(until(lambda:str(self.root/'Pictures') in self.paths()))
        self.type_path(str(self.root)+'/.p')
        self.assertTrue(until(lambda:self.paths()==[str(self.root/'.private')]))
    def test_click_only_stages_suggestion_and_enter_accepts_files_without_a_slash(self):
        self.type_path(str(self.root)+'/pic')
        popup=self.w.address.completion.popup()
        self.assertTrue(until(popup.isVisible))
        first=popup.model().index(0,0)
        QTest.mouseClick(popup.viewport(),Qt.MouseButton.LeftButton,pos=popup.visualRect(first).center());pump(60)
        self.assertEqual(self.w.address.text(),str(self.root)+'/pic')
        QTest.keyClick(self.w.address,Qt.Key.Key_Return)
        self.assertEqual(self.w.address.text(),str(self.root/'Pictures')+'/')
        self.assertEqual(self.w.location,str(self.root))
        self.type_path(str(self.root)+'/p n');self.assertTrue(until(popup.isVisible))
        QTest.keyClick(self.w.address,Qt.Key.Key_Return)
        self.assertEqual(self.w.address.text(),str(self.source))
    def test_drop_cancel_leaves_files_unchanged(self):
        dialog=self.drop();dialog.buttons['cancel'].click();pump(100)
        self.assertIsNone(self.w.drop_dialog);self.assertTrue(self.source.exists())
        self.assertFalse((self.destination/self.source.name).exists())
    def test_drop_copy_keeps_original(self):
        self.drop().buttons['copy'].click()
        self.assertTrue(until(lambda:(self.destination/self.source.name).exists()))
        self.assertEqual(self.source.read_text(),'unchanged')
        self.assertEqual((self.destination/self.source.name).read_text(),'unchanged')
    def test_drop_link_creates_symlink_without_moving_original(self):
        self.drop().buttons['link'].click();output=self.destination/self.source.name
        self.assertTrue(until(output.is_symlink));self.assertTrue(self.source.exists())
        self.assertEqual(output.resolve(),self.source);self.assertFalse(self.errors)
    def test_fonts_are_bundled_and_dropdown_updates_selection(self):
        families=set(QFontDatabase.families())
        self.assertTrue({'Manrope','Nunito Sans','Inter'} <= families,families)
        for family in ('Manrope','Nunito Sans','Inter'):
            self.assertIn('Regular',QFontDatabase.styles(family))
            self.assertIn('SemiBold',QFontDatabase.styles(family))
        settings=Settings(self.w.config,self.w);settings.changed.connect(self.w.settings_changed)
        settings.navigation.setCurrentRow(1);settings.show();pump(50)
        settings.font_presets.setCurrentIndex(2)
        self.assertEqual(self.w.config['font'],'Nunito Sans')
        self.assertEqual(settings.font_picker.currentFont().family(),'Nunito Sans')
        settings.font_size.setValue(13);self.assertEqual(self.w.config['font_size'],13)
        self.assertEqual(APP.font().family(),'Nunito Sans');settings.close();settings.deleteLater()
    def test_selection_uses_actual_image_and_custom_folder_thumbnails(self):
        picture=self.root/'Pictures'/'photo.png';image=QImage(140,80,QImage.Format.Format_RGB32);image.fill(QColor('#db4a68'));image.save(str(picture))
        self.w.pin(str(self.root/'Projects'));self.w.config['favorites'][-1]['thumbnail']=str(picture)
        self.w.graph.set_selection({str(picture),str(self.root/'Projects')})
        self.assertTrue(until(lambda:len(self.w.selection_model.nodes)==2))
        for path in (str(picture),str(self.root/'Projects')):
            node=self.w.selection_model.nodes[path]
            self.w.thumbnails.pixmap(node)
            self.assertTrue(until(lambda:self.w.thumbnails.pixmap(node)[1]=='image' and self.w.thumbnails.pixmap(node)[0].toImage().pixelColor(20,20).red()>180))
        self.assertTrue(until(lambda:self.w.selected_list.width()>200))
    @unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg is required for video preview testing')
    def test_selected_video_preview_decodes_a_real_frame(self):
        video=self.root/'preview.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=0x46c3b5:s=128x80',
                        '-t','0.2','-c:v','mpeg4',str(video)],check=True,capture_output=True,timeout=10)
        self.w.graph.set_selection({str(video)})
        self.assertTrue(until(lambda:str(video) in self.w.selection_model.nodes))
        node=self.w.selection_model.nodes[str(video)]
        def decoded():
            pix,kind=self.w.thumbnails.pixmap(node);pixel=pix.toImage().pixelColor(25,25)
            return kind=='video' and pixel.green()>170 and pixel.red()<100
        self.assertTrue(until(decoded))
        self.assertTrue(until(lambda:self.w.selected_list.width()>200))

class LinkTests(unittest.TestCase):
    def test_links_to_files_and_directories_and_collision_protection(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'Source';folder.mkdir();file=root/'file.txt';file.write_text('original');target=root/'Destination';target.mkdir()
            done,error=transfer_files([str(folder),str(file)],str(target),action='link')
            self.assertFalse(error);self.assertEqual(len(done),2)
            self.assertTrue((target/'Source').is_symlink());self.assertEqual((target/'file.txt').read_text(),'original')
            with self.assertRaises(FileExistsError):transfer_files([str(file)],str(target),action='link')
            self.assertEqual(file.read_text(),'original')

if __name__=='__main__':unittest.main()

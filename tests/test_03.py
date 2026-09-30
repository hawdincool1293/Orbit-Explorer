"""Behavioral checks for native payloads, tiled interaction and real search engines."""
import os,sys,tempfile,time,unittest,json,subprocess,shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent
from PySide6.QtGui import QKeyEvent,QDrag,QDragEnterEvent,QDropEvent
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtTest import QTest
from app import Orbit
from core import Node,scan_neighbourhood
from appearance import defaults
from interactions import SpringOpen,file_mime
from search_query import parse_query
from metadata import describe_path
from routing import parse_dump,PipeWire,RoutingScene

APP=QApplication.instance() or QApplication([])
def pump(ms=100):
    end=time.monotonic()+ms/1000
    while time.monotonic()<end:APP.processEvents();time.sleep(.005)
def until(predicate,seconds=4):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if predicate():return True
        pump(15)
    return predicate()

class Drop:
    """The native event boundary; source denotes Qt's drag source widget."""
    def __init__(self,mime,source,pos,kind=QEvent.Type.Drop,ctrl=False):self.mime=mime;self.origin=source;self.pos=pos;self.kind=kind;self.ctrl=ctrl;self.accepted=False;self.action=None
    def type(self):return self.kind
    def mimeData(self):return self.mime
    def source(self):return self.origin
    def position(self):return self.pos
    def modifiers(self):return Qt.KeyboardModifier.ControlModifier if self.ctrl else Qt.KeyboardModifier.NoModifier
    def buttons(self):return Qt.MouseButton.RightButton
    def possibleActions(self):return Qt.DropAction.CopyAction|Qt.DropAction.MoveAction
    def setDropAction(self,action):self.action=action
    def accept(self):self.accepted=True
    def ignore(self):self.accepted=False

class WindowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/'source';self.source.mkdir();self.target=self.root/'destination';self.target.mkdir()
        self.a=self.source/'a name.txt';self.a.write_text('I REMEMBER WHEN the moon rose')
        self.b=self.source/'second.txt';self.b.write_text('another file')
        self.patches=[patch('appearance.CONFIG',self.root/'settings.json'),patch('app.visible_mounts',return_value=[])]
        for p in self.patches:p.start()
        self.w=Orbit();self.errors=[];self.w.error=self.errors.append;self.w.show();self.w.visit(str(self.source),history=False)
        self.assertTrue(until(lambda:self.w.location==str(self.source)));self.w.graph.setFocus();pump(100)
    def tearDown(self):
        self.w.close();pump(100)
        for p in self.patches:p.stop()
        self.temp.cleanup()
    def test_native_drag_exports_real_file_urls_without_removing_sources(self):
        w=self.w;seen=[]
        def receive(drag,*actions):
            seen.extend(u.toLocalFile() for u in drag.mimeData().urls())
            self.assertIn('text/uri-list',drag.mimeData().formats())
            self.assertEqual(actions[1],Qt.DropAction.CopyAction)
            return Qt.DropAction.CopyAction
        with patch.object(QDrag,'exec',receive):w.start_drag([str(self.a),str(self.b)],w.graph.mapToGlobal(QPoint(100,100)))
        self.assertEqual(set(seen),{str(self.a),str(self.b)});self.assertTrue(self.a.exists());self.assertEqual(w.drag_paths,[])
    def test_native_drag_enter_and_external_drop_copies(self):
        w=self.w;w.pin(str(self.target));button=w.pin_buttons[str(self.target)];mime=file_mime([str(self.a)])
        enter=QDragEnterEvent(QPoint(15,15),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(button,enter);self.assertTrue(enter.isAccepted())
        drop=QDropEvent(QPointF(15,15),Qt.DropAction.CopyAction,mime,Qt.MouseButton.RightButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(button,drop);self.assertTrue(drop.isAccepted())
        self.assertTrue(until(lambda:w.drop_dialog is not None));w.drop_dialog.choose('copy')
        self.assertTrue(until(lambda:(self.target/self.a.name).exists()));self.assertTrue(self.a.exists())
    def test_transfer_between_independent_tiles_after_move_choice(self):
        w=self.w;first=w.workspace.active;w.new_tile(True);second=w.workspace.active
        self.assertEqual(second.state['location'],first.state['location'])
        w.visit(str(self.target),tile=second);self.assertTrue(until(lambda:second.state['location']==str(self.target)))
        self.assertEqual(first.state['location'],str(self.source))
        mime=file_mime([str(self.a),str(self.b)])
        ev=Drop(mime,first.graph,QPointF(30,second.graph.height()-50))
        w.handle_drop_event(second.graph,ev)
        self.assertTrue(ev.accepted);self.assertEqual(ev.action,Qt.DropAction.CopyAction)
        self.assertTrue(until(lambda:w.drop_dialog is not None));w.drop_dialog.choose('move')
        self.assertTrue(until(lambda:(self.target/self.a.name).exists() and not self.b.exists()))
        self.assertFalse(self.a.exists());self.assertFalse(self.errors)
        w.workspace.close_tile(second);self.assertEqual(len(w.workspace.tiles),1);self.assertIs(w.workspace.active,first)
    def test_tab_hold_survives_repeat_and_text_inputs_are_unaffected(self):
        g=self.w.graph;QTest.keyPress(g,Qt.Key.Key_Tab);pump(330);self.assertGreater(g.label_amount,.95)
        repeat=QKeyEvent(QEvent.Type.KeyRelease,Qt.Key.Key_Tab,Qt.KeyboardModifier.NoModifier,'\t',True,1)
        QApplication.sendEvent(g,repeat);pump(40);self.assertEqual(g.label_target,1.)
        QTest.keyRelease(g,Qt.Key.Key_Tab);pump(330);self.assertEqual(g.label_target,0.)
        self.w.address.setFocus();QTest.keyPress(self.w.address,Qt.Key.Key_Tab);self.assertIsNone(self.w._held_labels)
    def test_ctrl_shortcuts_duplicate_and_new_view(self):
        w=self.w;original=w.workspace.active;original.graph.yaw=1.1
        QTest.keyClick(original.graph,Qt.Key.Key_D,Qt.KeyboardModifier.ControlModifier);pump(80)
        self.assertEqual(len(w.workspace.tiles),2);self.assertEqual(w.graph.yaw,1.1)
        QTest.keyClick(w.graph,Qt.Key.Key_T,Qt.KeyboardModifier.ControlModifier);pump(80)
        self.assertEqual(len(w.workspace.tiles),3)
        self.assertTrue(until(lambda:w.location==str(Path.home())))
        self.assertEqual(original.state['location'],str(self.source))
        w.workspace.close_tile(w.workspace.active);w.workspace.close_tile(w.workspace.active)
        self.assertEqual(len(w.workspace.tiles),1);self.assertIs(w.workspace.active,original)
    def test_spring_warning_cancels_and_retries_then_opens_on_third_blink(self):
        w=self.w;w.pin(str(self.target));w.drag_paths=[str(self.a),str(self.b)];w.drop_tile=w.workspace.active
        w.hover_destination=str(self.target);pulses=[];opened=[]
        w.spring.pulse.connect(lambda path,on:pulses.append(on));w.spring.opened.connect(opened.append)
        w.spring.hover(str(self.target));pump(660);self.assertTrue(any(pulses));self.assertFalse(opened)
        w.spring.cancel();pump(900);self.assertFalse(opened);self.assertEqual(w.location,str(self.source))
        pulses.clear();started=time.monotonic();w.spring.hover(str(self.target));pump(1380);self.assertFalse(opened)
        self.assertTrue(until(lambda:bool(opened)));self.assertGreaterEqual(time.monotonic()-started,1.45)
        self.assertEqual(sum(pulses),3);self.assertTrue(until(lambda:w.location==str(self.target)))
        self.assertEqual(w.drag_paths,[str(self.a),str(self.b)])
    def test_command_runs_in_active_directory_and_recent_paths_persist(self):
        self.w.command.reveal();self.w.command.entry.setText('pwd');self.w.command.run()
        self.assertTrue(until(lambda:'Exit 0' in self.w.command.output.toPlainText()))
        self.assertIn(str(self.source),self.w.command.output.toPlainText())
        self.assertIn(str(self.source),self.w.config['recent_folders'])
    def test_volume_and_mute_are_connected_to_audio_output(self):
        from media import AudioDock
        dock=AudioDock(self.w.config,self.w.workspace);dock.volume.setValue(27)
        self.assertAlmostEqual(dock.output.volume(),.27,places=4);dock.mute.setChecked(True);self.assertTrue(dock.output.isMuted());dock.stop()
    def test_visible_content_query_updates_graph_and_list(self):
        self.w.open_search('contains: i remember when')
        self.assertTrue(until(lambda:str(self.a) in self.w.search_model.paths))
        a=next(n for n in self.w.graph.nodes if n.path==str(self.a));b=next(n for n in self.w.graph.nodes if n.path==str(self.b))
        self.assertTrue(self.w.graph.matches(a));self.assertFalse(self.w.graph.matches(b))
        self.w.clear_search();self.assertTrue(self.w.graph.matches(b))

class QueryTests(unittest.TestCase):
    def test_combined_filters_and_quoted_contents(self):
        q=parse_query('notes is: txt,md date: 28/09/2026 contains: "I remember when"')
        ns=int(datetime(2026,9,28,15).timestamp()*1e9)
        self.assertFalse(q.error);self.assertTrue(q.matches('/tmp/notes.md',ns));self.assertFalse(q.matches('/tmp/notes.png',ns));self.assertEqual(q.contains,'I remember when')
        self.assertTrue(parse_query('date: 31/02/2026').error);self.assertTrue(parse_query('is: ').error)
    def test_literal_content_uses_ripgrep_case_insensitive(self):
        from search_worker import content_matches
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'yes.txt';a.write_text('I REMEMBER WHEN [a.b]')
            b=Path(tmp)/'no.txt';b.write_text('i remember later')
            self.assertEqual(content_matches([str(a),str(b)],'i remember when [a.b]'),[str(a)])
    def test_metadata_has_file_size_type_date_and_folder_item_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'note.txt';p.write_text('hello')
            details=describe_path(str(p));self.assertEqual(details['size'],5);self.assertEqual(details['type'],'text/plain');self.assertIn('/',details['modified'])
            folder=describe_path(tmp);self.assertEqual(folder['items'],1);self.assertIn('direct files',folder['first'])
    def test_spacing_moves_clusters_further_from_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'one';folder.mkdir()
            for i in range(20):(folder/f'{i}.txt').touch()
            old,_=scan_neighbourhood(tmp,spacing=1);wide,_=scan_neighbourhood(tmp,spacing=1.8)
            self.assertGreater(sum(v*v for v in wide[1].xyz),sum(v*v for v in old[1].xyz))

AUDIO=[
 {'id':1,'type':'PipeWire:Interface:Node','info':{'props':{'media.class':'Stream/Output/Audio','node.name':'Music'}}},
 {'id':2,'type':'PipeWire:Interface:Node','info':{'props':{'media.class':'Audio/Sink','node.description':'Speakers'}}},
 {'id':11,'type':'PipeWire:Interface:Port','info':{'direction':'output','props':{'node.id':1,'port.name':'output_FL','object.serial':100}}},
 {'id':22,'type':'PipeWire:Interface:Port','info':{'direction':'input','props':{'node.id':2,'port.name':'playback_FL','object.serial':101}}},
 {'id':30,'type':'PipeWire:Interface:Link','info':{'output-port-id':11,'input-port-id':22,'state':'active'}}]
class RoutingTests(unittest.TestCase):
    def test_live_topology_builds_cards_ports_and_cables(self):
        data=parse_dump(AUDIO);backend=PipeWire();scene=RoutingScene(defaults(),backend);scene.rebuild(data)
        self.assertEqual(len(scene.nodes),2);self.assertEqual(len(scene.links),1);self.assertEqual(len(scene.ports),2)
        before=scene.links[30].path();scene.nodes[2].setPos(900,60);self.assertNotEqual(before,scene.links[30].path())
    def test_connect_disconnect_arguments_and_direction_validation(self):
        backend=PipeWire();backend.nodes,backend.ports,backend.links=parse_dump(AUDIO);calls=[];backend.command=calls.append
        backend.disconnect(30);self.assertEqual(calls,[['-d','30']]);backend.links={}
        backend.connect_ports(22,11);self.assertEqual(calls[-1],['11','22'])
        n=len(calls);backend.connect_ports(11,11);self.assertEqual(len(calls),n)

class BackendIntegrationTests(unittest.TestCase):
    def test_indexed_worker_applies_extension_date_and_content_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);good=root/'memory.txt';good.write_text('I Remember When the stars came out')
            bad=root/'memory.png';bad.write_text('I Remember When the stars came out')
            index=root/'index.bin';index.write_bytes(os.fsencode(good)+b'\0'+os.fsencode(bad)+b'\0')
            bindir=root/'bin';bindir.mkdir();plocate=bindir/'plocate'
            plocate.write_text('#!'+sys.executable+'\nimport os,sys\nopen(os.environ["TEST_ARGUMENTS"],"w").write(repr(sys.argv[1:]))\nsys.stdout.buffer.write(open(os.environ["TEST_INDEX"],"rb").read())\n');plocate.chmod(0o755)
            env=dict(os.environ,PATH=str(bindir)+os.pathsep+os.environ['PATH'],TEST_INDEX=str(index),TEST_ARGUMENTS=str(root/'args'))
            query='is: txt date: '+datetime.now().strftime('%d/%m/%Y')+' contains: i remember when'
            run=subprocess.run([sys.executable,str(Path(__file__).parents[1]/'search_worker.py'),json.dumps({'query':query})],capture_output=True,text=True,env=env,timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)
            paths=[p for line in run.stdout.splitlines() for p in json.loads(line).get('paths',[])]
            self.assertEqual(paths,[str(good)]);self.assertIn("'-0', '-i', '-b', '--'",(root/'args').read_text())
    def test_pipewire_process_adapter_refreshes_and_disconnects_a_live_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);dump=root/'pw-dump';link=root/'pw-link';log=root/'calls'
            dump.write_text('#!'+sys.executable+'\nprint('+repr(json.dumps(AUDIO))+')\n');dump.chmod(0o755)
            link.write_text('#!'+sys.executable+'\nimport sys,os\nopen(os.environ["TEST_LINK_LOG"],"a").write(repr(sys.argv[1:])+"\\n")\n');link.chmod(0o755)
            with patch.dict(os.environ,{'PATH':str(root)+os.pathsep+os.environ['PATH'],'TEST_LINK_LOG':str(log)}):
                backend=PipeWire();backend.start();self.assertTrue(until(lambda:30 in backend.links))
                backend.disconnect(30);self.assertTrue(until(lambda:log.exists()))
                self.assertIn("['-d', '30']",log.read_text());backend.stop();pump(50)


if __name__=='__main__':unittest.main()

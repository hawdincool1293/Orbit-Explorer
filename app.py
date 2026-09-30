"""Orbit Explorer 0.6.6 — native spatial file browsing and editing."""
from __future__ import annotations
# Orbit input patch: trackpad-opening-2026-09-30
import orbit_controls
import panel_motion
import os,sys,stat,subprocess,math,copy
from datetime import datetime
from pathlib import Path
# Hold the installation lock before importing any of the app's other modules.
# The descriptor lives until process exit, including worker shutdown.
if __name__ == "__main__" and not getattr(sys,'frozen',False):
    from install_lock import lock_installation
    try:
        _installation_lock = lock_installation(Path(__file__).resolve().parent, shared=True)
    except (OSError, RuntimeError) as error:
        print(f"Orbit: {error}", file=sys.stderr)
        sys.exit(1)
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import Qt,QObject,Signal,QTimer,QPointF,QRectF,QEvent,QUrl,QVariantAnimation,QEasingCurve,QPoint,QSize
from PySide6.QtGui import QFont,QColor,QPalette,QIcon,QDesktopServices,QKeySequence,QPainter,QDrag,QPixmap,QCursor,QSurfaceFormat
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QFrame,QHBoxLayout,QVBoxLayout,QLabel,
    QPushButton,QLineEdit,QScrollArea,QListView,QMessageBox,QInputDialog,QFileDialog,
    QColorDialog,QDialog,QSizeGrip,QGraphicsOpacityEffect,QComboBox,QStyle,QPlainTextEdit,QTextEdit,QAbstractSpinBox)
from appearance import load_config,save_config,SYSTEM_PRESET,palette_path,read_palette,default_font,pin_color
from core import Node,scan_neighbourhood,path_journey,visible_mounts,drive_graph,mount_device,file_category,transfer_files,drive_name,drive_key
from graph import Graph
from thumbnails import Thumbnails
from ui import Settings,PathModel,IndexedSearch,Spotlight,DragOverlay,SendTo
from workspace import ViewWorkspace,new_state
from interactions import SpringOpen,file_mime,mime_paths,drag_pixmap,INTERNAL_MIME
from metadata import SelectionModel,SelectionDelegate
from commandbar import CommandBar
from search_query import parse_query
from trash_vortex import TrashVortex
from path_bar import PathBar
from drop_actions import DropActionDialog
from design import stylesheet,ui_icon,Menu as QMenu,Panel
from panes import LiveSplitter
from viewers import FileHub,FileConnections,viewer_kind
from trash_paths import home_trash,trash_locations,containing_trash,delete_trashed
from desktop_backend import IS_MAC,run_host,trash_command,runtime_setup
runtime_setup()

class Bus(QObject):
    scanned=Signal(int,str,object,int,str)
    drives=Signal(object,str)
    done=Signal(str,object,str)
    flight=Signal(int,object,object,str)

class Header(QFrame):
    def __init__(self,window):
        super().__init__();self.owner=window;self.setObjectName("header")
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.owner.windowHandle():self.owner.windowHandle().startSystemMove()
    def mouseDoubleClickEvent(self,event):
        if not self.owner.hyprland:self.owner.toggle_maximize()

class Shell(QWidget):
    def __init__(self,config):super().__init__();self.config=config
    def paintEvent(self,event):
        painter=QPainter(self);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(),Qt.GlobalColor.transparent)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color=QColor(self.config['colors']['background']);color.setAlpha(round(255*self.config['opacity']/100))
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(color);painter.drawRoundedRect(QRectF(self.rect()),30,30)

def viewport_property(key):
    def get(self):return (self.workspace.active.state if hasattr(self,'workspace') else self._initial_state)[key]
    def set(self,value):(self.workspace.active.state if hasattr(self,'workspace') else self._initial_state).__setitem__(key,value)
    return property(get,set)

class Orbit(QMainWindow):
    drop_requested=Signal(object,str,object)
    location=viewport_property('location')
    back_paths=viewport_property('back_paths')
    forward_paths=viewport_property('forward_paths')
    trip=viewport_property('trip')
    trip_target=viewport_property('trip_target')
    force_target=viewport_property('force_target')
    animation=viewport_property('animation')
    devices=viewport_property('devices')
    scan_preserve=viewport_property('scan_preserve')
    scan_token=viewport_property('scan_token')
    @property
    def graph(self):return self.workspace.active.graph

    def __init__(self):
        super().__init__()
        self._initial_state=new_state();self.scan_requests={};self.next_scan=0;self._held_labels=None;self.routing=None
        self.config=load_config(default_font());self.ui_icons=[];self.drop_dialog=None
        self._settings_seen=copy.deepcopy(self.config);self._pending_settings=set()
        self.settings_save_timer=QTimer(self);self.settings_save_timer.setSingleShot(True);self.settings_save_timer.setInterval(250);self.settings_save_timer.timeout.connect(self.save_settings_now)
        self.settings_apply_timer=QTimer(self);self.settings_apply_timer.setSingleShot(True);self.settings_apply_timer.setInterval(16);self.settings_apply_timer.timeout.connect(self.apply_pending_settings)
        self.saved_splitters={};self.detail_width=self.config.get('detail_width',348);self.flight_token=0;self.recovering=False
        self.hyprland=bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")) or "hyprland" in os.environ.get("XDG_CURRENT_DESKTOP","").lower()
        self.setWindowTitle("Orbit Explorer");self.setWindowIcon(QIcon(str(Path(__file__).parent/"assets/orbit.svg")))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint);self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground);self.resize(1440,880)
        size=self.config.get('window_size',[])
        if len(size)==2 and all(isinstance(v,int) and 500<=v<=10000 for v in size):self.resize(*size)
        self.pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix="orbit-job")
        self.bus=Bus(self);self.bus.scanned.connect(self.scanned);self.bus.drives.connect(self.got_drives);self.bus.done.connect(self.job_done)
        self.bus.flight.connect(self.flight_ready)
        self.scan_token=0;self.location="";self.back_paths=[];self.forward_paths=[];self.trip=[];self.trip_target="";self.force_target=""
        self.animation=None;self.drives=[];self.devices={};self.clipboard=[];self.cut=False;self._closing=False
        self.drag_paths=[];self.hover_destination="";self.pending_send=None;self.audio=None
        self.palette_stamp=None;self.last_hidden=self.config["show_hidden"];self.last_spacing=self.config["node_spacing"]
        self.thumbnails=Thumbnails(self.config,self)
        self.build_ui();self.apply_theme()
        self.palette_timer=QTimer(self);self.palette_timer.setInterval(1200);self.palette_timer.timeout.connect(self.sync_palette);self.palette_timer.start();self.sync_palette()
        self.refresh_favorites();self.refresh_drives();self.refresh_recents()
        restored=self.workspace.restore(self.config.get('workspace_layout'))
        if restored:
            for tile,item in restored:
                path=item.get('path','');tile.state['restore_camera']=item.get('camera')
                self.visit(path if os.path.isdir(path) else str(Path.home()),history=False,tile=tile)
        else:
            start=self.config["last_path"];self.visit(start if os.path.isdir(start) else str(Path.home()),history=False)
        self.documents.restore(self.config.get('file_layout'))
        QApplication.instance().installEventFilter(self)
        orbit_controls.update_hint(self)

    def button(self,text,fn,tooltip=""):
        b=QPushButton(text);b.setToolTip(tooltip);b.clicked.connect(fn);return b
    def tool_button(self,icon,fn,tooltip,text=''):
        b=self.button(text,fn,tooltip);b.setAccessibleName(tooltip)
        b.setProperty('role','toolbar' if text else 'icon');b.setIconSize(QSize(19,19))
        if not text:b.setFixedSize(38,38)
        self.ui_icons.append((b,icon));return b
    def caption(self,text):
        w=QLabel(text);w.setObjectName("caption");return w
    def build_ui(self):
        self.shell=Shell(self.config);self.shell.setObjectName("shell");self.setCentralWidget(self.shell)
        outer=QVBoxLayout(self.shell);outer.setContentsMargins(14,10,14,8);outer.setSpacing(12)
        self.rows=self.pane('rows',Qt.Orientation.Vertical);outer.addWidget(self.rows)
        title=Header(self);row=QHBoxLayout(title);row.setContentsMargins(14,4,4,0);row.setSpacing(8)
        self.brand_icon=QLabel();self.brand_icon.setFixedSize(34,34);row.addWidget(self.brand_icon)
        brand=QLabel("Orbit");brand.setObjectName("brand");row.addWidget(brand);row.addSpacing(8)
        row.addWidget(self.caption('EXPLORER'));row.addStretch()
        row.addWidget(self.tool_button('split',lambda:self.new_tile(False),'New viewport · Ctrl+T','Split view'))
        row.addWidget(self.tool_button('duplicate',lambda:self.new_tile(True),'Duplicate viewport · Ctrl+D','Duplicate'))
        row.addSpacing(8)
        row.addWidget(self.tool_button('terminal',self.toggle_command,'Command bar · Ctrl+`'))
        row.addWidget(self.tool_button('audio',self.open_routing,'Audio routing'))
        self.gear=self.tool_button('settings',self.open_settings,'Settings');row.addWidget(self.gear)
        self.window_buttons=[]
        if not self.hyprland:
            for icon,fn,tip in (("minus",self.showMinimized,'Minimize'),("maximize",self.toggle_maximize,'Maximize'),("close",self.close,'Close')):
                b=self.tool_button(icon,fn,tip);b.setFixedSize(32,34);row.addWidget(b);self.window_buttons.append(b)
        title.setMinimumHeight(42);self.rows.addWidget(title)
        bar=Panel();bar.setObjectName("navigation");nav=QHBoxLayout(bar);nav.setContentsMargins(9,7,10,7);nav.setSpacing(8)
        for icon,fn,tip in (('back',self.go_back,"Back"),('forward',self.go_forward,"Forward"),
                            ('home',lambda:self.navigate(str(Path.home())),"Home")):
            nav.addWidget(self.tool_button(icon,fn,tip))
        self.inputs=self.pane('path_search');nav.addWidget(self.inputs,1)
        self.address=PathBar(self.config,self.current_folder);self.address.returnPressed.connect(self.navigate_address);self.inputs.addWidget(self.address)
        self.address_icon=self.address.addAction(QIcon(),QLineEdit.ActionPosition.LeadingPosition)
        self.search_box=QLineEdit();self.search_box.setPlaceholderText("Search your files · Ctrl+F")
        self.search_icon=self.search_box.addAction(QIcon(),QLineEdit.ActionPosition.LeadingPosition)
        self.search_box.textChanged.connect(lambda text:self.query_changed(text,self.search_box));self.inputs.addWidget(self.search_box);self.inputs.setSizes([700,400])
        self.search_exact=QPushButton('Exact');self.search_exact.setCheckable(True);self.search_exact.setChecked(self.config['search_strict'])
        self.search_exact.setFocusPolicy(Qt.FocusPolicy.NoFocus);self.search_exact.setToolTip('Strict search: exact filename, including extension and letter case. Filters still apply.')
        self.search_exact.toggled.connect(self.set_strict_search);nav.addWidget(self.search_exact)
        self.search_box.returnPressed.connect(self.open_first_result);bar.setMinimumHeight(50);self.rows.addWidget(bar)
        self.send_banner=Panel();self.send_banner.setObjectName("panel");sendrow=QHBoxLayout(self.send_banner)
        self.send_hint=QLabel();sendrow.addWidget(self.send_hint,1);sendrow.addWidget(self.button("Send here",self.finish_network_send));sendrow.addWidget(self.button("Cancel",self.cancel_send))
        self.rows.addWidget(self.send_banner);self.send_banner.hide()
        self.middle=self.pane('columns');middle=self.middle;self.rows.addWidget(middle);middle.setMinimumHeight(280)
        self.sidebar=Panel();self.sidebar.setObjectName("panel");self.sidebar.setMinimumWidth(180)
        side=QVBoxLayout(self.sidebar);side.setContentsMargins(14,16,14,12);side.setSpacing(5)
        self.side_sections=self.pane('sidebar',Qt.Orientation.Vertical);side.addWidget(self.side_sections,1)
        pins=QWidget();pinbox=QVBoxLayout(pins);pinbox.setContentsMargins(0,0,0,0);pinbox.addWidget(self.caption('PINNED PLACES'))
        self.side_sections.addWidget(pins)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
        contents=QWidget();self.pin_layout=QVBoxLayout(contents);self.pin_layout.setContentsMargins(0,0,0,0);self.pin_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(contents);self.pin_scroll=scroll;pinbox.addWidget(scroll,1)
        pin=self.tool_button('pin',lambda:self.pin(self.current_folder()),'Pin this directory','Pin this folder');pin.setObjectName('softButton');pinbox.addWidget(pin)
        disks=QWidget();diskbox=QVBoxLayout(disks);diskbox.setContentsMargins(0,0,0,0);self.side_sections.addWidget(disks)
        heading=QHBoxLayout();heading.addWidget(self.caption("DRIVES"));heading.addStretch();heading.addWidget(self.tool_button('refresh',self.refresh_drives,'Refresh drives'));diskbox.addLayout(heading)
        ds=QScrollArea();ds.setWidgetResizable(True);ds.setFrameShape(QFrame.Shape.NoFrame)
        dc=QWidget();self.drive_layout=QVBoxLayout(dc);self.drive_layout.setContentsMargins(0,0,0,0);self.drive_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        ds.setWidget(dc);self.drive_scroll=ds;diskbox.addWidget(ds,1)
        recents=QWidget();recentbox=QVBoxLayout(recents);recentbox.setContentsMargins(0,0,0,0);self.side_sections.addWidget(recents);recentbox.addWidget(self.caption('RECENT FOLDERS'))
        recent=QScrollArea();recent.setWidgetResizable(True);recent.setFrameShape(QFrame.Shape.NoFrame)
        rc=QWidget();self.recent_layout=QVBoxLayout(rc);self.recent_layout.setContentsMargins(0,0,0,0);self.recent_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        recent.setWidget(rc);recentbox.addWidget(recent,1);self.side_sections.setSizes([240,240,180])
        for area in (scroll,ds,recent):area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        hint=QLabel('Middle drag to orbit\nRight drag to pan');hint.setObjectName('muted');side.addWidget(hint);middle.addWidget(self.sidebar)
        self.center=self.pane('cloud_files',Qt.Orientation.Vertical);middle.addWidget(self.center)
        self.workspace=ViewWorkspace(self.config,self.thumbnails);self.center.addWidget(self.workspace)
        self.documents=FileHub(self.config);self.center.addWidget(self.documents)
        self.documents.locate.connect(self.fly_to);self.documents.changed.connect(self.refresh_views);self.documents.panels_changed.connect(self.document_panels_changed)
        self.connections=FileConnections(self.shell,self.workspace,self.documents,self.config)
        self.workspace.active.state.update(self._initial_state);self.connect_tile(self.workspace.active)
        self.workspace.tile_created.connect(self.connect_tile);self.workspace.activated.connect(self.active_tile_changed)
        self.workspace.tile_closed.connect(self.tile_closed)
        self.right=Panel();self.right.setObjectName("panel");self.right.setMinimumWidth(250)
        right=QVBoxLayout(self.right);right.setContentsMargins(16,22,16,16)
        self.detail_sections=self.pane('details',Qt.Orientation.Vertical);right.addWidget(self.detail_sections)
        self.search_section=QWidget();searchdetails=QVBoxLayout(self.search_section);searchdetails.setContentsMargins(0,0,0,0);self.detail_sections.addWidget(self.search_section)
        self.selection_section=QWidget();selecteddetails=QVBoxLayout(self.selection_section);selecteddetails.setContentsMargins(0,0,0,0);self.detail_sections.addWidget(self.selection_section)
        self.search_caption=self.caption("SEARCH");searchdetails.addWidget(self.search_caption)
        self.search_status=QLabel();self.search_status.setWordWrap(True);searchdetails.addWidget(self.search_status)
        self.search_model=PathModel(self);self.result_list=QListView();self.result_list.setModel(self.search_model);self.result_list.setUniformItemSizes(True)
        self.result_list.clicked.connect(self.activate_result);searchdetails.addWidget(self.result_list,1)
        self.selected_caption=self.caption("SELECTED");selecteddetails.addWidget(self.selected_caption)
        self.selection_model=SelectionModel(self)
        self.selected_list=QListView();self.selected_list.setModel(self.selection_model);self.selected_list.setUniformItemSizes(True)
        self.selected_list.setItemDelegate(SelectionDelegate(self.config,self.thumbnails,self.selected_list))
        self.thumbnails.changed.connect(self.selected_list.viewport().update)
        self.selected_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.selected_list.customContextMenuRequested.connect(self.selection_menu)
        selecteddetails.addWidget(self.selected_list,1);middle.addWidget(self.right);self.right.hide();middle.setSizes([248,900,348]);middle.setStretchFactor(1,1)
        self.right_effect=QGraphicsOpacityEffect(self.right);self.right.setGraphicsEffect(self.right_effect)
        self.command=CommandBar(self.current_folder,self.shell);self.command.finished.connect(lambda _:self.refresh_views());self.rows.addWidget(self.command);self.command.hide()
        bottom=QHBoxLayout();self.status=QLabel("Ready");self.status.setObjectName("muted");bottom.addWidget(self.status,1);bottom.addWidget(self.tool_button('fit',self.reset_camera,'Reset view'))
        if not self.hyprland:bottom.addWidget(QSizeGrip(self))
        footer=QFrame();footer.setObjectName("footer");footer.setLayout(bottom);bottom.setContentsMargins(12,0,0,0);self.rows.addWidget(footer)
        self.rows.setSizes([48,60,0,680,0,40]);self.rows.setStretchFactor(3,1)
        self.spotlight=Spotlight(self.search_model,self.shell);self.spotlight.edit.textChanged.connect(lambda text:self.query_changed(text,self.spotlight.edit))
        self.spotlight.edit.returnPressed.connect(self.open_first_result);self.spotlight.list.clicked.connect(self.activate_result)
        self.index_search=IndexedSearch(self);self.index_search.batch.connect(self.search_batch);self.index_search.status.connect(self.search_progress)
        self.search_timer=QTimer(self);self.search_timer.setSingleShot(True);self.search_timer.setInterval(150);self.search_timer.timeout.connect(lambda:self.index_search.search(self.search_box.text().strip(),self.visible_paths(),strict=self.config['search_strict']))
        self.spotlight.exact.setChecked(self.config['search_strict']);self.spotlight.exact.toggled.connect(self.set_strict_search)
        self.overlay=DragOverlay(self.config,self.shell)
        for view in (self.selected_list,self.result_list,self.spotlight.list):
            view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);view.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.spring=SpringOpen(self);self.spring.pulse.connect(self.spring_pulse);self.spring.opened.connect(self.spring_open)
        self.drag_object=None;self.drag_origin=None;self.drop_tile=None
        self.trash_vortex=TrashVortex(self.config,self.trash_candidates,self.workspace)
        self.trash_vortex.clicked.connect(self.open_trash)
        self.trash_vortex.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.trash_vortex.customContextMenuRequested.connect(self.trash_menu)
        self.trash_vortex.files_dropped.connect(self.trash,Qt.ConnectionType.QueuedConnection)
        self.trash_vortex.drag_hovered.connect(self.trash_hover)
        self.drop_requested.connect(self.finish_drop,Qt.ConnectionType.QueuedConnection)
        QTimer.singleShot(0,self.restore_panes)

    def pane(self,name,orientation=Qt.Orientation.Horizontal):
        pane=LiveSplitter(orientation);self.saved_splitters[name]=pane
        pane.splitterMoved.connect(lambda *_:self.position_overlays() if hasattr(self,'spotlight') else None)
        return pane
    def restore_panes(self):
        for name,sizes in self.config.get('pane_sizes',{}).items():
            pane=self.saved_splitters.get(name)
            if pane:pane.restore_sizes(sizes)
        if self.config.get('window_maximized') and not self.hyprland:self.showMaximized()
    def document_panels_changed(self):
        if self.documents.panels and self.center.sizes()[-1]<150:
            previous=self.config['pane_sizes'].get('cloud_files',[])
            if len(previous)==2 and previous[-1]>=150:self.center.restore_sizes(previous)
            else:self.center.setSizes([max(280,self.center.height()-300),300])
        self.connections.refresh()

    def apply_theme(self):
        c=self.config["colors"];self.setStyleSheet(stylesheet(self.config));self.shell.update();self.address.apply_theme()
        self.brand_icon.setPixmap(ui_icon('orbit',c['primary'],30).pixmap(30,30))
        for button,icon in self.ui_icons:button.setIcon(ui_icon(icon,c['text']))
        self.address_icon.setIcon(ui_icon('folder',c['muted']));self.search_icon.setIcon(ui_icon('search',c['muted']))
        palette=QApplication.palette()
        for role,key in ((QPalette.ColorRole.Window,"panel"),(QPalette.ColorRole.WindowText,"text"),(QPalette.ColorRole.Text,"text"),
                         (QPalette.ColorRole.Base,"background"),(QPalette.ColorRole.Button,"panel"),(QPalette.ColorRole.ButtonText,"text"),
                         (QPalette.ColorRole.Highlight,"secondary"),(QPalette.ColorRole.HighlightedText,"text")):palette.setColor(role,QColor(c[key]))
        QApplication.instance().setPalette(palette);QApplication.instance().setFont(QFont(self.config["font"],self.config['font_size']))
        for tile in self.workspace.tiles:tile.refresh_style();tile.graph.label_layout.clear();tile.graph._projection_key=None;tile.graph.update()
        # Update existing pin icons on live Caelestia changes too, without
        # replacing drop-target widgets in the middle of a native drag.
        for favorite in self.config['favorites']:
            button=getattr(self,'pin_buttons',{}).get(favorite['path'])
            if button and not favorite.get('thumbnail'):button.setIcon(ui_icon('folder',pin_color(favorite,self.config),22))
        for child in self.findChildren(QComboBox):
            if child.view().isVisible():
                from design import prepare_popup
                prepare_popup(child.view(),c)
        if self.audio:self.audio.refresh_icons()
        self.trash_vortex.update()
    def open_settings(self):
        self.graph.labels(False);dialog=Settings(self.config,self);dialog.changed.connect(self.settings_changed);dialog.exec();self.apply_pending_settings();self.save_settings_now();dialog.deleteLater()
    def settings_changed(self):
        orbit_controls.update_hint(self)
        changed={k for k,v in self.config.items() if self._settings_seen.get(k)!=v}
        if not changed:return
        if any(key.startswith('panel_motion_') for key in changed):panel_motion.finish_all(self)
        self._settings_seen=copy.deepcopy(self.config);self._pending_settings.update(changed)
        self.settings_save_timer.start()
        # Native controls react immediately; expensive visual work is coalesced
        # to one event-loop frame, never performed for unrelated checkboxes.
        if changed & {'font','font_size'}:
            QApplication.instance().setFont(QFont(self.config['font'],self.config['font_size']))
        if not self.settings_apply_timer.isActive():self.settings_apply_timer.start()
    def save_settings_now(self):
        self.settings_save_timer.stop();save_config(self.config)
    def apply_pending_settings(self):
        self.settings_apply_timer.stop();changed=self._pending_settings;self._pending_settings=set()
        if not changed:return
        if changed & {'preset','palette_file'}:self.palette_stamp=None;self.sync_palette()
        if changed & {'colors','preset','font','font_size'}:self.apply_theme()
        elif 'opacity' in changed:
            self.shell.update()
            for panel in self.findChildren(Panel):panel.update()
        if changed & {'icon_theme','type_icons','thumbnails'}:self.thumbnails.set_theme()
        if 'favorites' in changed:self.refresh_favorites()
        if 'search_strict' in changed:self.set_strict_search(self.config['search_strict'])
        if 'node_spacing' in changed and self.last_spacing!=self.config['node_spacing']:
            from dataclasses import replace
            ratio=self.config['node_spacing']/self.last_spacing;self.last_spacing=self.config['node_spacing']
            for tile in self.workspace.tiles:
                g=tile.graph;g.set_graph(g.root,[replace(n,xyz=tuple(v*ratio for v in n.xyz)) for n in g.nodes],g.hidden_count,preserve=True)
        if 'moons' in changed:
            for tile in self.workspace.tiles:tile.graph.update()
        if 'audio_internal' in changed and not self.config["audio_internal"] and self.audio:self.audio.stop()
        if 'spotlight' in changed and not self.config["spotlight"]:self.spotlight.dismiss()
        if 'show_hidden' in changed and self.last_hidden!=self.config["show_hidden"]:
            self.last_hidden=self.config["show_hidden"]
            self.refresh_views()
    def sync_palette(self):
        if self.config["preset"]!=SYSTEM_PRESET:return
        path=palette_path(self.config)
        try:
            stamp=(str(path),path.stat().st_mtime_ns)
            if stamp!=self.palette_stamp:self.config["colors"].update(read_palette(path));self.palette_stamp=stamp;self.apply_theme()
        except (OSError,ValueError,TypeError):self.status.setText(f"System palette unavailable: {path}")
    def toggle_maximize(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()
    def reset_camera(self):
        self.graph.yaw,self.graph.pitch=.28,-.16;self.graph.fit_cloud()
    def current_folder(self):
        return self.location if os.path.isdir(self.location) else str(Path.home())
    def navigate_address(self):
        self.address.setModified(False);self.address.completion.popup().hide();self.navigate(self.address.text())
    def remember(self,path):
        if self.location and self.location!=path:self.back_paths.append(self.location);self.forward_paths.clear()
    def cancel_trip(self):
        self.flight_token+=1
        self.trip=[];self.trip_target="";self.force_target=""
        if self.animation:self.animation.stop()
        self.graph.flight_previous=None;self.graph.flight_mix=1.;self.graph.update()
    def navigate(self,path,preserve=False):
        self.cancel_trip();path=os.path.expanduser(path.strip())
        if path.startswith("drive:"):
            drive=next((d for d in self.drives if "drive:"+d["path"]==path),None)
            if drive:self.show_drive(drive)
        else:
            if not os.path.isabs(path):path=os.path.join(self.current_folder(),path)
            if os.path.isfile(path):self.force_target=os.path.abspath(path);path=os.path.dirname(os.path.abspath(path))
            self.visit(path,preserve=preserve)
    def visit(self,path,history=True,preserve=False,tile=None):
        path=os.path.abspath(os.path.expanduser(path));tile=tile or self.workspace.active
        if not os.path.isdir(path):self.error(f"Directory unavailable: {path}");return
        if history and tile.state['location'] and tile.state['location']!=path:
            tile.state['back_paths'].append(tile.state['location']);tile.state['forward_paths'].clear()
        self.next_scan+=1;token=self.next_scan;tile.state['scan_token']=token;tile.state['scan_preserve']=preserve
        self.scan_requests[token]=tile;hidden=self.config['show_hidden'];spacing=self.config['node_spacing'];limit=self.config['node_limit']
        if tile is self.workspace.active:self.status.setText(f"Opening {path}…")
        def work():
            try:
                nodes,folded=scan_neighbourhood(path,limit=limit,show_hidden=hidden,spacing=spacing);self.bus.scanned.emit(token,path,nodes,folded,"")
            except Exception as exc:self.bus.scanned.emit(token,path,[],0,str(exc))
        self.pool.submit(work)
    def scanned(self,token,path,nodes,hidden,error):
        tile=self.scan_requests.pop(token,None)
        if self._closing or tile not in self.workspace.tiles or token!=tile.state['scan_token']:return
        if error:self.error(error);return
        state=tile.state;first=not state['location'];state['location']=path;state['devices']={};target=state['trip_target'] or state['force_target']
        if target and os.path.dirname(target)==path and target not in {n.path for n in nodes}:
            try:
                info=os.lstat(target);nodes.append(Node(target,Path(target).name,os.path.isdir(target),info.st_size,1,(260,120,210),path,modified_ns=info.st_mtime_ns))
            except OSError:pass
        tile.graph.set_graph(path,nodes,hidden,preserve=state['scan_preserve'] or bool(self.drag_paths));tile.set_path(path)
        if first:tile.graph.fit_cloud()
        camera=state.pop('restore_camera',None)
        if isinstance(camera,list) and len(camera)==5 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in camera):
            tile.graph.yaw,tile.graph.pitch,tile.graph.zoom=camera[:3];tile.graph.offset=QPointF(*camera[3:]);tile.graph.update()
        self.record_recent(path)
        if tile is self.workspace.active:
            if not (self.address.hasFocus() and self.address.isModified()):self.address.set_location(path)
            self.config['last_path']=path;save_config(self.config);self.status.setText(path)
            if state['trip']:QTimer.singleShot(70,self.next_flight)
            elif target:tile.graph.set_selection({target});state['trip_target']='';state['force_target']=''
        if self.search_box.text() and not self.graph.parsed_query.contains:self.search_batch([n.path for n in nodes if tile.graph.matches(n)])

    def connect_tile(self,tile):
        g=tile.graph;g.installEventFilter(self)
        g.selection_changed.connect(lambda paths,t=tile:self.selection_changed(paths) if t is self.workspace.active else None)
        def active_call(fn,*args):self.workspace.activate(tile);fn(*args)
        g.entered.connect(lambda path:active_call(self.open_node,path))
        g.context_requested.connect(lambda path,pos:active_call(self.context_menu,path,pos))
        g.drag_started.connect(lambda paths,pos:active_call(self.start_drag,paths,pos))
        g.set_query(self.search_box.text() if hasattr(self,'search_box') else '')
    def active_tile_changed(self,tile):
        self.flight_token+=1
        for other in self.workspace.tiles:
            if other is not tile:
                other.graph.labels(False);anim=other.state['animation']
                if anim:anim.stop()
                other.graph.flight_previous=None;other.graph.flight_mix=1.;other.graph.update()
                other.state['trip']=[];other.state['trip_target']=''
        self._held_labels=None;self.address.set_location(tile.state['location']);self.selection_changed(sorted(tile.graph.selected_paths))
        if hasattr(self,'command'):self.command.location.setText(self.current_folder())
    def new_tile(self,duplicate=False):
        self.graph.labels(False);self.cancel_trip();tile=self.workspace.split(duplicate)
        if not duplicate:self.visit(str(Path.home()),history=False,tile=tile)
        self.position_overlays()
    def tile_closed(self,tile):
        animation=tile.state['animation']
        if animation:animation.stop()
        tile.graph.labels(False);tile.graph.moon_timer.stop()
        self.scan_requests={k:v for k,v in self.scan_requests.items() if v is not tile}
        self.trash_vortex.reposition()
    def visible_paths(self):return list({n.path for t in self.workspace.tiles for n in t.graph.nodes if not n.kind})
    def refresh_views(self):
        if self._closing:return
        for tile in self.workspace.tiles:
            if os.path.isdir(tile.state['location']):self.visit(tile.state['location'],history=False,tile=tile)
    def record_recent(self,path):
        self.config['recent_folders']=[path]+[p for p in self.config['recent_folders'] if p!=path][:11]
        self.refresh_recents()
    def refresh_recents(self):
        self.clear_layout(self.recent_layout)
        for path in self.config['recent_folders'][:12]:
            name=self.fontMetrics().elidedText(Path(path).name or path,Qt.TextElideMode.ElideMiddle,158)
            b=self.button(name,lambda checked=False,p=path:self.navigate(p),path)
            b.setProperty('role','place');b.setIcon(ui_icon('clock',self.config['colors']['muted']));self.recent_layout.addWidget(b)
    def toggle_command(self):
        self.rows.remember()
        controller=getattr(self.command,'_entrance_controller',None)
        if self.command.isVisible() and not (controller and controller.exiting):self.command.dismiss()
        else:self.command.reveal();self.rows.restore_visible()
    def open_routing(self):
        if IS_MAC:self.error('The PipeWire patchbay is Linux-only. Use Audio MIDI Setup for macOS device routing.');return
        from routing import RoutingDialog
        if self.routing is None:self.routing=RoutingDialog(self.config,self)
        controller=getattr(self.routing,'_entrance_controller',None)
        if controller and controller.exiting:panel_motion.reveal(self.routing,self.config,'dialogs');self.routing.backend.start()
        self.routing.show();self.routing.raise_();self.routing.activateWindow()

    def go_back(self):
        if self.back_paths:self.cancel_trip();self.forward_paths.append(self.location);self.restore_location(self.back_paths.pop())
    def go_forward(self):
        if self.forward_paths:self.cancel_trip();self.back_paths.append(self.location);self.restore_location(self.forward_paths.pop())
    def restore_location(self,path):
        if path.startswith("drive:"):
            drive=next((d for d in self.drives if "drive:"+d["path"]==path),None)
            if drive:self.show_drive(drive,history=False)
        else:self.visit(path,history=False)
    def fly_to(self,path):
        if not os.path.exists(path):self.error("This indexed result is no longer available.");return
        self.cancel_trip();self.remember(path if os.path.isdir(path) else os.path.dirname(path))
        self.clear_search()
        if not self.config['navigation_enabled']:
            self.force_target=path;self.visit(path if os.path.isdir(path) else os.path.dirname(path),history=False);return
        route=path_journey(self.current_folder(),path)
        if len(route)>8:route=[route[round(i*(len(route)-1)/7)] for i in range(8)]
        token=self.flight_token;tile=self.workspace.active
        self.next_scan+=1;tile.state['scan_token']=self.next_scan
        hidden=self.config['show_hidden'];spacing=self.config['node_spacing'];limit=self.config['node_limit']
        self.status.setText('Preparing flight…')
        def work():
            try:
                scenes=[]
                for folder in route:
                    if token!=self.flight_token:return
                    nodes,folded=scan_neighbourhood(folder,limit=limit,show_hidden=hidden,spacing=spacing)
                    if folder==route[-1] and path not in {node.path for node in nodes}:
                        info=os.lstat(path);nodes.append(Node(path,Path(path).name,os.path.isdir(path),info.st_size,1,(260,120,210),folder,modified_ns=info.st_mtime_ns))
                    scenes.append((folder,nodes,folded))
                self.bus.flight.emit(token,(tile,path),scenes,'')
            except Exception as exc:self.bus.flight.emit(token,(tile,path),[],str(exc))
        self.pool.submit(work)
    def flight_ready(self,token,context,scenes,error):
        tile,target=context
        if self._closing or token!=self.flight_token or tile not in self.workspace.tiles or tile is not self.workspace.active:return
        if error:self.error(error);return
        from navigation import Flight
        self.flight=Flight(self,tile,target,scenes);self.flight.start()
    def animate(self,duration,fn,finished=None):
        if self.animation:self.animation.stop()
        self.animation=QVariantAnimation(self);self.animation.setDuration(duration);self.animation.setStartValue(0.);self.animation.setEndValue(1.)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic);self.animation.valueChanged.connect(fn)
        if finished:self.animation.finished.connect(finished)
        self.animation.start()
    def next_flight(self):
        if not self.trip:return
        path=self.trip.pop(0);zoom=self.graph.zoom;yaw=self.graph.yaw;offset=QPointF(self.graph.offset)
        def frame(v):
            self.graph.zoom=zoom+(max(.58,zoom*.84)-zoom)*v;self.graph.yaw=yaw+.22*v;self.graph.offset=offset*(1-v);self.graph.update()
        self.animate(400,frame,lambda:self.visit(path,history=False))
    def animate_arrival(self):
        initial=self.graph.zoom;self.animate(500,lambda v:(setattr(self.graph,"zoom",initial+(1.08-initial)*v),self.graph.update()))

    def set_strict_search(self,strict):
        self.config['search_strict']=bool(strict)
        for button in (self.search_exact,self.spotlight.exact):
            button.blockSignals(True);button.setChecked(strict);button.blockSignals(False)
        self._settings_seen['search_strict']=bool(strict);self.settings_save_timer.start();self.query_changed(self.search_box.text(),self.search_box)
    def query_changed(self,text,source):
        for edit in (self.search_box,self.spotlight.edit):
            if edit is not source:edit.blockSignals(True);edit.setText(text);edit.blockSignals(False)
        for tile in self.workspace.tiles:tile.graph.set_query(text.strip())
        self.index_search.stop();self.search_model.clear()
        if text.strip():
            self.search_batch([n.path for t in self.workspace.tiles for n in t.graph.nodes if t.graph.matches(n)])
            self.search_status.setText(parse_query(text).error or "Searching…");self.search_timer.start()
        else:self.search_timer.stop();self.spotlight.dismiss()
        self.refresh_panel()
    def search_batch(self,paths):
        for tile in self.workspace.tiles:
            if tile.graph.parsed_query.contains:tile.graph.content_paths.update(paths);tile.graph.refresh_matches();tile.graph.update()
        self.search_model.append(paths);self.search_status.setText(f"{len(self.search_model.paths):,} matches")
        self.spotlight.hint.setText(f"{len(self.search_model.paths):,} matches  ·  Enter to travel  ·  Escape to dismiss")
    def search_progress(self,message):
        self.search_status.setText(f"{len(self.search_model.paths):,} matches\n{message}")
    def clear_search(self):
        self.search_box.setText("");self.spotlight.dismiss()
    def open_search(self,text=""):
        if self.config["spotlight"]:
            self.position_overlays();self.spotlight.reveal()
            if text:self.spotlight.edit.setText(self.spotlight.edit.text()+text)
        else:
            self.search_box.setFocus()
            if text:self.search_box.setText(self.search_box.text()+text)
    def activate_result(self,index):
        path=index.data(Qt.ItemDataRole.UserRole)
        if path:self.fly_to(path)
    def open_first_result(self):
        view=self.spotlight.list if self.spotlight.isVisible() else self.result_list;index=view.currentIndex()
        if not index.isValid() and self.search_model.paths:index=self.search_model.index(0,0)
        self.activate_result(index)
    def selection_changed(self,paths):
        self.selection_model.clear();self.selection_model.nodes={n.path:n for t in self.workspace.tiles for n in t.graph.nodes if n.path in paths}
        self.selection_model.append(paths);self.selected_caption.setText(f"SELECTED · {len(paths)}")
        if self.pending_send:
            candidate=next((p for p in paths if os.path.isdir(p)),self.current_folder())
            self.send_hint.setText(f"Destination: {candidate}");self.pending_send["destination"]=candidate
        self.refresh_panel()
    def refresh_panel(self):
        searching=bool(self.search_box.text().strip());selected=bool(self.graph.selected_paths)
        for w in (self.search_caption,self.search_status,self.result_list):w.setVisible(searching)
        self.selected_caption.setVisible(selected);self.selected_list.setVisible(selected)
        self.search_section.setVisible(searching);self.selection_section.setVisible(selected)
        controller=getattr(self.right,'_entrance_controller',None)
        if searching or selected:
            if self.right.isHidden() or controller and controller.exiting:
                if self.right.isHidden():
                    self.right.show();sizes=self.middle.sizes();self.middle.setSizes([sizes[0],max(250,sum(sizes[1:])-self.detail_width),self.detail_width])
                panel_motion.reveal(self.right,self.config,'sidebar',self.right_effect)
        elif not self.right.isHidden():
            if not controller or not controller.exiting:
                self.detail_width=controller.extent if controller and controller.active else self.right.width()
                panel_motion.dismiss(self.right,self.config,'sidebar',self.right.hide,self.right_effect)
    def panel_step(self,value):
        self.right_effect.setOpacity(float(value));self.position_overlays()
    def clear_layout(self,layout):
        while layout.count():
            item=layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
            elif item.layout():self.clear_layout(item.layout())
    def refresh_favorites(self):
        self.clear_layout(self.pin_layout);self.pin_buttons={}
        self.pin_scroll.setMinimumHeight(35)
        for favorite in self.config["favorites"]:
            path=favorite["path"];name=self.fontMetrics().elidedText(Path(path).name or path,Qt.TextElideMode.ElideMiddle,152)
            b=self.button(name,lambda checked=False,p=path:self.navigate(p),path)
            b.setProperty('role','place');b.setIconSize(QSize(22,22));b.setIcon(ui_icon('folder',pin_color(favorite,self.config),22))
            if favorite.get("thumbnail"):b.setIcon(QIcon(favorite["thumbnail"]))
            b.setAcceptDrops(True);b.setProperty("pinPath",path);b.installEventFilter(self)
            b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);b.customContextMenuRequested.connect(lambda pos,p=path,w=b:self.favorite_menu(p,w.mapToGlobal(pos)))
            self.pin_layout.addWidget(b);self.pin_buttons[path]=b
        for tile in self.workspace.tiles:tile.graph.update()
    def pin(self,path):
        if not os.path.isdir(path):return
        if path not in {f["path"] for f in self.config["favorites"]}:
            self.config["favorites"].append({"path":path,"color_mode":"theme","thumbnail":""});save_config(self.config);self.refresh_favorites()
    def favorite_menu(self,path,pos):
        favorite=next((f for f in self.config["favorites"] if f["path"]==path),None)
        if not favorite:return
        menu=QMenu(self)
        for label,fn in (("Open",lambda:self.navigate(path)),("Color…",lambda:self.favorite_color(favorite)),
                         ("Use theme color",lambda:favorite.update(color_mode='theme')),
                         ("Thumbnail…",lambda:self.favorite_thumbnail(favorite)),("Clear thumbnail",lambda:favorite.update(thumbnail="")),
                         ("Unpin",lambda:self.config["favorites"].remove(favorite))):menu.addAction(label,fn)
        menu.exec(pos);save_config(self.config);self.refresh_favorites()
    def favorite_color(self,favorite):
        color=QColorDialog.getColor(QColor(pin_color(favorite,self.config)),self)
        if color.isValid():favorite.update(color=color.name(),color_mode='custom')
    def favorite_thumbnail(self,favorite):
        path,_=QFileDialog.getOpenFileName(self,"Choose thumbnail",str(Path.home()),"Images (*.png *.jpg *.jpeg *.webp)")
        if path:favorite["thumbnail"]=path
    def refresh_drives(self):
        def work():
            try:self.bus.drives.emit(visible_mounts(),"")
            except Exception as exc:self.bus.drives.emit([],str(exc))
        self.pool.submit(work)
    def got_drives(self,drives,error):
        self.drives=drives;self.clear_layout(self.drive_layout)
        if error:
            label=QLabel("Drive inventory unavailable");label.setToolTip(error);self.drive_layout.addWidget(label);return
        for drive in drives:
            label=drive_name(drive,self.config)
            label=self.fontMetrics().elidedText(label,Qt.TextElideMode.ElideRight,158)
            b=self.button(f"{label}\n{Path(drive['path']).name} · {drive['size']}",lambda checked=False,d=drive:self.show_drive(d),drive["path"])
            b.setProperty('role','place');b.setIcon(ui_icon('drive',self.config['colors']['muted']));self.drive_layout.addWidget(b)
            b.setToolTip(f'{drive_name(drive,self.config)}\n{drive["model"]}\n{drive["path"]}\nRight-click to rename in Orbit')
            b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);b.customContextMenuRequested.connect(lambda pos,d=drive,button=b:self.drive_menu(d,button.mapToGlobal(pos)))
        if self.location.startswith("drive:"):
            drive=next((d for d in drives if "drive:"+d["path"]==self.location),None)
            if drive:self.show_drive(drive,history=False)
    def show_drive(self,drive,history=True):
        self.cancel_trip();self.next_scan+=1;self.scan_token=self.next_scan;location="drive:"+drive["path"]
        if history:self.remember(location)
        self.location=location;nodes,self.devices=drive_graph(dict(drive,display_name=drive_name(drive,self.config)));self.graph.set_graph(location,nodes)
        self.workspace.active.set_path(drive_name(drive,self.config));self.address.set_location(location);self.status.setText("Double-click a partition to open or mount it. Right-click for drive actions.")
    def drive_menu(self,drive,pos):
        menu=QMenu(self);menu.addAction('Open drive',lambda:self.show_drive(drive));menu.addAction('Rename in Orbit…',lambda:self.rename_drive(drive))
        menu.addAction('Use hardware name',lambda:self.set_drive_alias(drive,''));menu.exec(pos)
    def rename_drive(self,drive):
        name,ok=QInputDialog.getText(self,'Rename drive in Orbit','Display name:',text=drive_name(drive,self.config))
        if ok:self.set_drive_alias(drive,name)
    def set_drive_alias(self,drive,name):
        key=drive_key(drive);name=name.strip()[:120]
        if name:self.config['drive_aliases'][key]=name
        else:self.config['drive_aliases'].pop(key,None)
        save_config(self.config);self.got_drives(self.drives,'')
    def device_action(self,device):
        if device["mount"]=="/":self.error("The running system filesystem cannot be unmounted.");return
        def work():
            try:self.bus.done.emit("mount",[],mount_device(device["path"],bool(device["mount"]),device["fs"]=="crypto_LUKS"))
            except Exception as exc:self.bus.done.emit("error",[],str(exc))
        self.pool.submit(work)
    def open_node(self,path):
        if path in self.devices:
            d=self.devices[path]
            if d["mount"]:self.navigate(d["mount"])
            elif d["fs"]:self.device_action(d)
            return
        if os.path.isdir(path):self.navigate(path)
        elif os.path.isfile(path):
            if file_category(path)=="audio" and self.config["audio_internal"]:self.play_audio(path)
            elif self.config['files_internal'] and viewer_kind(path):self.open_internal(path)
            else:QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    def open_internal(self,path):
        try:
            if not self.documents.open_file(path):QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception as exc:self.error(f'Could not open built-in viewer: {exc}. You can use Open externally from the node menu.')
    def play_audio(self,path):
        try:
            if self.audio is None:
                from media import AudioDock
                self.audio=AudioDock(self.config,self.workspace);self.audio.opened.connect(self.audio_opened)
                self.audio.closed.connect(lambda:self.audio_opened(""));self.audio.error.connect(self.error)
                self.audio_connection=self.connections;self.connections.audio=self.audio
            self.position_overlays();self.audio.play(path)
        except ImportError as exc:self.error(f"Audio requires pyside6 with Qt Multimedia and python-numpy: {exc}")
    def audio_opened(self,path):
        self.audio_connection.set_source(path)
        for tile in self.workspace.tiles:
            tile.graph.audio_source='';tile.graph.update()
    def selected_files(self):
        return [p for p in sorted(self.graph.selected_paths) if p not in self.devices and os.path.lexists(p)]
    def context_menu(self,path,pos):
        if path and path not in self.graph.selected_paths:self.graph.set_selection({path})
        menu=QMenu(self)
        if path in self.devices:
            d=self.devices[path]
            if d['type'] in ('disk','rom'):menu.addAction('Rename in Orbit…',lambda:self.rename_drive(d))
            if d["mount"]:menu.addAction("Open filesystem",lambda:self.navigate(d["mount"]))
            if d["fs"]:
                label="Unmount" if d["mount"] else ("Unlock" if d["fs"]=="crypto_LUKS" else "Mount")
                action=menu.addAction(label,lambda:self.device_action(d));action.setEnabled(d["mount"]!="/")
            menu.addAction("Properties",lambda:self.properties([path]));menu.exec(pos);return
        paths=self.selected_files() if path else []
        if paths:
            if len(paths)==1:
                menu.addAction("Open",lambda:self.open_node(paths[0]))
                if os.path.isdir(paths[0]):menu.addAction("Pin directory",lambda:self.pin(paths[0]))
                elif file_category(paths[0])=="audio":menu.addAction("Play in Orbit",lambda:self.play_audio(paths[0]))
                elif viewer_kind(paths[0]):menu.addAction('Open in Orbit',lambda:self.open_internal(paths[0]))
                if os.path.isfile(paths[0]):menu.addAction('Open externally',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(paths[0])))
                if os.path.isfile(paths[0]):menu.addAction('Convert to…',lambda:self.convert_file(paths[0]))
            archives=[p for p in paths if viewer_kind(p)=='archive']
            if archives and len(archives)==len(paths):
                menu.addSeparator();menu.addAction('Extract to Home',lambda:self.extract_files(archives,'home'))
                menu.addAction('Extract here',lambda:self.extract_files(archives,'here'))
                menu.addAction('Extract to…',lambda:self.extract_files(archives,'choose'))
            menu.addAction('Compress to ZIP…',lambda:self.compress_files(paths))
            menu.addSeparator();menu.addAction("Cut",lambda:self.copy_selection(paths,True));menu.addAction("Copy",lambda:self.copy_selection(paths,False))
            menu.addAction("Send to…",lambda:self.send_to(paths))
            if len(paths)==1:menu.addAction("Rename…",lambda:self.rename(paths[0]))
            trash_label='Delete permanently…' if all(containing_trash(p,self.trash_roots()) for p in paths) else 'Move to trash'
            menu.addAction(trash_label,lambda:self.trash(paths));menu.addAction("Properties",lambda:self.properties(paths))
        directory=path if path and os.path.isdir(path) and len(paths)<=1 else (self.current_folder() if not path else "")
        if directory:
            menu.addSeparator();menu.addAction("New folder…",lambda:self.create(directory,True));menu.addAction("New text file…",lambda:self.create(directory,False))
            if self.clipboard:menu.addAction("Paste here",lambda:self.transfer(self.clipboard,directory,copy=not self.cut))
        if path in {f["path"] for f in self.config["favorites"]}:menu.addAction("Favorite appearance…",lambda:self.favorite_menu(path,pos))
        menu.exec(pos)
    def convert_file(self,path):
        from conversion import ConversionDialog
        dialog=ConversionDialog(path,self.config,self);dialog.converted.connect(self.refresh_views);dialog.exec();dialog.deleteLater()
    def extract_files(self,paths,mode):
        from file_tools import extract_archive,extract_here
        destination=str(Path.home()) if mode=='home' else ''
        if mode=='choose':
            destination=QFileDialog.getExistingDirectory(self,'Extract into directory',self.current_folder())
            if not destination:return
        self.status.setText('Extracting archives…')
        def work():
            completed=[]
            try:
                for path in paths:
                    result=extract_here(path,Path(path).parent) if mode=='here' else extract_archive(path,destination)
                    completed.append(result)
                self.bus.done.emit('extracted',completed,'')
            except Exception as exc:self.bus.done.emit('extracted',completed,str(exc))
        self.pool.submit(work)
    def compress_files(self,paths):
        from file_tools import compress_zip
        target,_=QFileDialog.getSaveFileName(self,'Compress selected items',str(Path(self.current_folder())/'Archive.zip'),'ZIP archives (*.zip)')
        if not target:return
        if not target.lower().endswith('.zip'):target+='.zip'
        self.status.setText('Compressing ZIP…')
        def work():
            try:self.bus.done.emit('compressed',[compress_zip(paths,target)],'')
            except Exception as exc:self.bus.done.emit('compressed',[],str(exc))
        self.pool.submit(work)
    def selection_menu(self,pos):
        index=self.selected_list.indexAt(pos);path=index.data(Qt.ItemDataRole.UserRole)
        if path:self.context_menu(path,self.selected_list.mapToGlobal(pos))
    def copy_selection(self,paths,cut):
        self.clipboard=list(paths);self.cut=cut;self.status.setText(f"{len(paths)} item(s) {'cut' if cut else 'copied'}")
    def rename(self,path):
        if path=="/":self.error("The filesystem root cannot be renamed.");return
        name,ok=QInputDialog.getText(self,"Rename","Name:",text=Path(path).name)
        if not ok or not name or name in (".","..") or "/" in name:return
        output=str(Path(path).parent/name)
        if os.path.lexists(output):self.error("That name already exists.");return
        try:
            os.rename(path,output);self.update_favorite_paths([(path,output)]);self.navigate(output if path==self.location else self.current_folder())
        except OSError as exc:self.error(str(exc))
    def create(self,directory,folder):
        name,ok=QInputDialog.getText(self,"New folder" if folder else "New file","Name:",text="" if folder else "Untitled.txt")
        if not ok or not name or name in (".","..") or "/" in name:return
        try:
            path=os.path.join(directory,name)
            if folder:os.mkdir(path)
            else:
                with open(path,"x",encoding="utf8"):pass
            self.visit(self.current_folder(),history=False)
        except OSError as exc:self.error(str(exc))
    def properties(self,paths):
        if len(paths)==1 and paths[0] in self.devices:
            d=self.devices[paths[0]];text=f"{d['name']}\n{d['path']}\n\nSize: {d['size']}\nFilesystem: {d['fs'] or 'Partitioned drive'}\nMounted at: {d['mount'] or 'Not mounted'}"
        else:
            size=0;details=[]
            for path in paths:
                try:
                    st=os.lstat(path);size+=st.st_size
                    if len(paths)==1:details=[path,f"Type: {'Directory' if os.path.isdir(path) else 'File'}",
                        f"Size: {st.st_size:,} bytes"+(" (directory entry; contents not included)" if os.path.isdir(path) else ""),
                        f"Modified: {datetime.fromtimestamp(st.st_mtime):%Y-%m-%d %H:%M:%S}",f"Permissions: {stat.filemode(st.st_mode)}"]
                except OSError as exc:details.append(str(exc))
            text="\n\n".join(details) if len(paths)==1 else f"{len(paths)} items\n\nEntry size total: {size:,} bytes"
        dialog=QDialog(self);dialog.setWindowTitle("Properties");dialog.resize(540,280);layout=QVBoxLayout(dialog)
        label=QLabel(text);label.setTextFormat(Qt.TextFormat.PlainText);label.setWordWrap(True);label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);layout.addWidget(label)
        if len(paths)==1 and os.path.isdir(paths[0]):
            size_label=QLabel("Calculating contents size…");layout.addWidget(size_label)
            from PySide6.QtCore import QProcess
            process=QProcess(dialog)
            process.finished.connect(lambda code,status:size_label.setText(
                "Contents (apparent bytes): "+bytes(process.readAllStandardOutput()).decode(errors="replace").split("\t")[0] if code==0 else "Contents size unavailable for this directory"))
            process.start("du",["-sb","--",paths[0]]);dialog.finished.connect(lambda _:process.kill())
        layout.addWidget(self.button("Close",dialog.accept));dialog.exec()
    def open_trash(self):
        try:
            path=home_trash();path.mkdir(parents=True,exist_ok=True,mode=0o700);self.navigate(str(path))
        except OSError as exc:self.error(str(exc))
    def trash_menu(self,pos):
        menu=QMenu(self)
        for label,path in trash_locations(self.drives):menu.addAction(label,lambda checked=False,p=path:self.open_trash() if p==home_trash() else self.navigate(str(p)))
        menu.addSeparator();menu.addAction('Empty Trash…',self.empty_trash)
        menu.exec(self.trash_vortex.mapToGlobal(pos))
    def trash_roots(self):return [path for label,path in trash_locations(self.drives)]
    def empty_trash(self):
        if QMessageBox.question(self,'Empty Trash','Permanently delete all items from Home Trash and detected mounted-drive Trash? This cannot be undone.')!=QMessageBox.StandardButton.Yes:return
        roots=self.trash_roots()
        def work():
            try:
                paths=[str(p) for root in roots if root.is_dir() for p in root.iterdir()]
                self.bus.done.emit('deleted',delete_trashed(paths,roots),'')
            except Exception as exc:self.bus.done.emit('deleted',[],str(exc))
        self.pool.submit(work)
    def trash_hover(self,active):
        if active:
            self.spring.cancel();self.hover_destination='';self.overlay.hide()
            for tile in self.workspace.tiles:
                if tile.graph.drop_hover:tile.graph.drop_hover='';tile.graph.drop_bright=False;tile.graph.update()
    def trash_candidates(self,paths):
        protected={'/'}
        for tile in self.workspace.tiles:
            protected.add(os.path.abspath(tile.state['location'] or '/'))
            protected.update(tile.state['devices'])
        accepted=[]
        for path in sorted({os.path.abspath(p) for p in paths},key=lambda p:(p.count(os.sep),p)):
            if path in protected:continue
            try:mode=os.lstat(path).st_mode
            except OSError:continue
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode) or stat.S_ISLNK(mode)):continue
            if not stat.S_ISLNK(mode) and os.path.ismount(path):continue
            # A selected folder already includes its selected children.
            if any(path.startswith(parent+os.sep) and not os.path.islink(parent) for parent in accepted):continue
            accepted.append(path)
        return accepted
    def trash(self,paths):
        paths=self.trash_candidates(paths)
        if not paths:return
        roots=self.trash_roots();inside=[bool(containing_trash(p,roots)) for p in paths]
        if any(inside):
            if not all(inside):self.error('Select items inside Trash separately from other files.');return
            if QMessageBox.question(self,'Delete permanently',f'Permanently delete {len(paths)} item(s) from Trash? This cannot be undone.')!=QMessageBox.StandardButton.Yes:return
            def remove():
                try:self.bus.done.emit('deleted',delete_trashed(paths,roots),'')
                except Exception as exc:self.bus.done.emit('deleted',[],str(exc))
            self.pool.submit(remove);return
        if QMessageBox.question(self,"Move to trash",f"Move {len(paths)} selected item(s) to trash?")!=QMessageBox.StandardButton.Yes:return
        self.status.setText(f"Moving {len(paths)} item(s) to Trash…")
        def work():
            try:
                result=run_host(trash_command(paths),capture_output=True,text=True,timeout=120)
                self.bus.done.emit("trash",paths,(result.stderr.strip() or "Could not move the selected files to Trash.") if result.returncode else "")
            except Exception as exc:self.bus.done.emit("trash",[],str(exc))
        self.pool.submit(work)
    def send_to(self,paths):
        dialog=SendTo(paths,self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        copy=dialog.mode.currentText()=="Copy"
        if dialog.network:
            self.pending_send={"paths":list(paths),"copy":copy,"destination":self.current_folder()}
            self.send_hint.setText("Choose a destination folder in Orbit, then Send here");self.send_banner.show()
        else:self.transfer(paths,os.path.expanduser(dialog.path.text().strip()),copy)
    def finish_network_send(self):
        if self.pending_send:self.transfer(self.pending_send["paths"],self.pending_send["destination"],self.pending_send["copy"]);self.cancel_send()
    def cancel_send(self):
        self.pending_send=None;self.send_banner.hide()
    def transfer(self,paths,destination,copy=False,*,action=None):
        paths=list(paths)
        if not paths:return
        action=action or ('copy' if copy else 'move')
        verb={'copy':'Copying','move':'Moving','link':'Linking'}[action]
        self.status.setText(f"{verb} {len(paths)} item(s)…")
        def work():
            try:
                done,error=transfer_files(paths,destination,action=action);self.bus.done.emit(action,done,error)
            except Exception as exc:self.bus.done.emit("error",[],str(exc))
        self.pool.submit(work)
    def update_favorite_paths(self,moves):
        for old,new in moves:
            for favorite in self.config["favorites"]:
                p=favorite["path"]
                if p==old or p.startswith(old+os.sep):favorite["path"]=new+p[len(old):]
        save_config(self.config);self.refresh_favorites()
    def job_done(self,kind,completed,error):
        if self._closing:return
        if kind=="mount":self.status.setText(error);self.refresh_drives();return
        if kind=="move":self.update_favorite_paths(completed);self.clipboard=[];self.cut=False
        if error:self.error(error)
        elif kind in ("copy","move","link"):self.status.setText(f"{len(completed)} item(s) {'linked' if kind=='link' else 'transferred'}")
        elif kind=="trash":
            self.status.setText(f"{len(completed)} item(s) moved to Trash");self.trash_vortex.celebrate()
            self.clipboard=[p for p in self.clipboard if os.path.lexists(p)]
        elif kind=='deleted':self.status.setText(f'{len(completed)} item(s) permanently deleted')
        elif kind in ('extracted','compressed'):self.status.setText(f'{len(completed)} archive operation(s) completed')
        if kind!="error":self.refresh_views()

    def start_drag(self,paths,global_pos):
        self.drag_paths=[p for p in paths if p not in self.devices and os.path.lexists(p) and p!='/']
        if not self.drag_paths:return
        self.drag_origin=self.workspace.active;self.drop_tile=self.drag_origin;g=self.drag_origin.graph
        self.drag_chooser=g.right_drag
        origins=[QPointF(g.mapTo(self.shell,g.projected.get(p,(QRectF(),None,0))[0].center().toPoint())) for p in self.drag_paths[:16]]
        self.overlay.start(self.drag_paths,origins,self.shell.mapFromGlobal(global_pos))
        drag=QDrag(g);drag.setMimeData(file_mime(self.drag_paths));pix=drag_pixmap(self.drag_paths,self.config);drag.setPixmap(pix);drag.setHotSpot(QPoint(4,4));self.drag_object=drag
        def target_changed(target):
            inside=isinstance(target,QWidget) and (target is self or self.isAncestorOf(target))
            if inside:
                transparent=QPixmap(1,1);transparent.fill(Qt.GlobalColor.transparent);drag.setPixmap(transparent)
            else:
                drag.setPixmap(pix);self.overlay.hide();self.spring.cancel()
        drag.targetChanged.connect(target_changed)
        try:
            # File URLs are the standard inter-app payload. Copy is the default
            # for upload targets; internal drops open an explicit action chooser.
            drag.exec(Qt.DropAction.CopyAction|Qt.DropAction.MoveAction,Qt.DropAction.CopyAction)
        finally:
            self.end_drag();g.dragging=False;g.update();self.refresh_views()
    def end_drag(self):
        self.spring.cancel();self.overlay.hide();self.overlay.timer.stop();self.drag_paths=[];self.hover_destination='';self.drop_tile=None;self.drag_object=None
        self.trash_vortex.set_dragging(False)
        for tile in self.workspace.tiles:tile.graph.drop_hover='';tile.graph.drop_bright=False;tile.graph.update()
        for b in self.pin_buttons.values():b.setProperty('dropHover',False);b.style().unpolish(b);b.style().polish(b)
    def drag_destination(self,obj,pos):
        if obj.property('pinPath'):return obj.property('pinPath'),self.workspace.active
        tile=next((t for t in self.workspace.tiles if t.graph is obj),None)
        if not tile:return '',None
        path=tile.graph.hit(pos,set(self.drag_paths))
        if path and os.path.isdir(path):return path,tile
        return (tile.state['location'] if not path and os.path.isdir(tile.state['location']) else ''),tile
    def move_drag(self,global_pos,destination='',tile=None):
        if self.drop_tile is not (tile or self.workspace.active):self.spring.cancel()
        self.drop_tile=tile or self.workspace.active
        if self.drag_object:
            self.overlay.pointer=QPointF(self.shell.mapFromGlobal(global_pos));self.overlay.show();self.overlay.raise_();self.overlay.update()
        self.hover_destination=destination
        # Spring-open folders and pinned badges, but never the empty canvas/root.
        spring=destination if destination and destination!=self.drop_tile.state['location'] else ''
        self.spring.hover(spring)
        for t in self.workspace.tiles:
            if t.graph.drop_hover!=spring:t.graph.drop_hover=spring;t.graph.update()
    def spring_pulse(self,path,bright):
        for t in self.workspace.tiles:
            t.graph.drop_bright=bright;t.graph.update()
        b=self.pin_buttons.get(path)
        if b:b.setProperty('dropHover',bright);b.style().unpolish(b);b.style().polish(b)
    def spring_open(self,path):
        if self.drag_paths and self.hover_destination==path and self.drop_tile in self.workspace.tiles:
            self.visit(path,preserve=True,tile=self.drop_tile)
    def handle_drop_event(self,obj,event):
        kind=event.type()
        if kind==QEvent.Type.DragLeave:
            self.spring.cancel();self.hover_destination='';self.overlay.hide()
            if self.drag_object is None:self.end_drag()
            return True
        paths=mime_paths(event.mimeData())
        if not paths:event.ignore();return True
        self.drag_paths=paths
        destination,tile=self.drag_destination(obj,event.position())
        if not destination:event.ignore();self.spring.cancel();return True
        # Acknowledge receipt only. The chosen action runs after the native drag
        # ends; returning Move now could let another app delete on Cancel.
        action=Qt.DropAction.CopyAction
        if not event.possibleActions()&action:event.ignore();return True
        event.setDropAction(action);event.accept()
        if kind==QEvent.Type.Drop:
            chooser=getattr(self,'drag_chooser',False) if self.drag_object else bool(event.buttons()&Qt.MouseButton.RightButton)
            point=obj.mapToGlobal(event.position().toPoint())
            self.spring.cancel();self.overlay.hide();self.drop_requested.emit(list(paths),destination,(chooser,point))
            if self.drag_object is None:self.end_drag()
        else:self.move_drag(obj.mapToGlobal(event.position().toPoint()),destination,tile)
        return True
    def finish_drop(self,paths,destination,options):
        chooser,point=options
        if chooser:self.choose_drop_action(paths,destination,point)
        else:
            paths=[p for p in paths if Path(p).parent.resolve()!=Path(destination).resolve()]
            if paths:self.transfer(paths,destination,action='move')
            else:self.status.setText('These items are already in this directory.')
    def choose_drop_action(self,paths,destination,point=None):
        if self._closing:return
        if self.drop_dialog:
            self.drop_dialog.raise_();return
        if self.config['drop_popup']=='cursor':
            menu=QMenu(self);self.drop_dialog=menu
            for action,label in (('move','Move here'),('copy','Copy here'),('link','Link here')):
                menu.addAction(label,lambda checked=False,a=action:self.transfer(paths,destination,action=a))
            menu.addSeparator();menu.addAction('Cancel')
            menu.aboutToHide.connect(lambda:(setattr(self,'drop_dialog',None),menu.deleteLater()))
            menu.popup(point or QCursor.pos());return
        dialog=DropActionDialog(paths,destination,self.config,self);self.drop_dialog=dialog
        def finished(result):
            self.drop_dialog=None
            if result==QDialog.DialogCode.Accepted and not self._closing:
                self.transfer(paths,destination,action=dialog.action)
            dialog.deleteLater()
        dialog.finished.connect(finished);dialog.open()
    def eventFilter(self,obj,event):
        if orbit_controls.open_selection_key(self,obj,event):return True
        kind=event.type()
        if obj is self and kind in (QEvent.Type.WindowDeactivate,QEvent.Type.Hide):self.release_interactions()
        if obj is self and kind in (QEvent.Type.WindowActivate,QEvent.Type.Show,QEvent.Type.WindowStateChange):QTimer.singleShot(0,self.recover_surface)
        if kind==QEvent.Type.Expose and obj is self.windowHandle():QTimer.singleShot(0,self.recover_surface)
        if kind in (QEvent.Type.DragEnter,QEvent.Type.DragMove,QEvent.Type.DragLeave,QEvent.Type.Drop) and (isinstance(obj,Graph) or isinstance(obj,QPushButton) and obj.property('pinPath')):
            return self.handle_drop_event(obj,event)
        if kind==QEvent.Type.WindowDeactivate and obj is self:
            for tile in self.workspace.tiles:tile.graph.labels(False)
            self._held_labels=None
        if kind in (QEvent.Type.KeyPress,QEvent.Type.KeyRelease,QEvent.Type.ShortcutOverride):
            if obj is self.trash_vortex:return super().eventFilter(obj,event)
            if isinstance(obj,PathBar) and (obj.candidate or obj.completion.popup().isVisible()):return super().eventFilter(obj,event)
            if QApplication.activeModalWidget() or (isinstance(obj,QWidget) and QWidget.window(obj) is not self):return super().eventFilter(obj,event)
            focus=QApplication.focusWidget();editing=isinstance(focus,(QLineEdit,QComboBox,QPlainTextEdit,QTextEdit,QAbstractSpinBox))
            sequence=QKeySequence(self.config['label_key']);combo=sequence[0] if not sequence.isEmpty() else QKeySequence('Tab')[0]
            key=event.key();ctrl=bool(event.modifiers()&Qt.KeyboardModifier.ControlModifier)
            if kind==QEvent.Type.ShortcutOverride:
                if not editing and key==combo.key():event.accept();return True
                return super().eventFilter(obj,event)
            if kind==QEvent.Type.KeyRelease and self._held_labels is not None and key==combo.key():
                if not event.isAutoRepeat():self._held_labels.labels(False);self._held_labels=None
                return True
            if kind==QEvent.Type.KeyPress and not editing and key==combo.key() and event.modifiers()==combo.keyboardModifiers():
                if not event.isAutoRepeat():self._held_labels=self.graph;self.graph.labels(True)
                return True
            if kind==QEvent.Type.KeyPress:
                if ctrl and key==Qt.Key.Key_T:self.new_tile(False);return True
                if ctrl and key==Qt.Key.Key_D:self.new_tile(True);return True
                if ctrl and key==Qt.Key.Key_W:self.workspace.close_tile(self.workspace.active);return True
                if ctrl and key==Qt.Key.Key_Q:
                    if len(self.workspace.tiles)>1:self.workspace.close_tile(self.workspace.active)
                    else:self.close()
                    return True
                if ctrl and key==Qt.Key.Key_QuoteLeft:self.toggle_command();return True
                if key==Qt.Key.Key_Escape:
                    if self.drag_object:QDrag.cancel()
                    self.spring.cancel();self.graph.labels(False);self._held_labels=None
                    self.clear_search();self.graph.rectangle=None;self.graph.rectangle_anchor=None;self.cancel_send();return True
                if ctrl and key==Qt.Key.Key_F:self.open_search();return True
                if ctrl and key==Qt.Key.Key_L:self.address.setFocus();self.address.selectAll();return True
                if not editing:
                    if ctrl and key in (Qt.Key.Key_C,Qt.Key.Key_X):self.copy_selection(self.selected_files(),key==Qt.Key.Key_X);return True
                    if ctrl and key==Qt.Key.Key_V:self.transfer(self.clipboard,self.current_folder(),copy=not self.cut);return True
                    if key==Qt.Key.Key_Delete:self.trash(self.selected_files());return True
                    if key==Qt.Key.Key_F2 and len(self.selected_files())==1:self.rename(self.selected_files()[0]);return True
                    if event.modifiers()&Qt.KeyboardModifier.AltModifier:
                        if key==Qt.Key.Key_Left:self.go_back();return True
                        if key==Qt.Key.Key_Right:self.go_forward();return True
                    if event.text() and event.text().isprintable() and not event.modifiers()&(Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.AltModifier|Qt.KeyboardModifier.MetaModifier):
                        self.open_search(event.text());return True
        return super().eventFilter(obj,event)
    def release_interactions(self):
        for pane in self.findChildren(LiveSplitter):pane.resizing(False)
        for tile in self.workspace.tiles:
            tile.graph.live_resizing=False;tile.graph.dragging=False;tile.graph.press_path='';tile.graph.setCursor(Qt.CursorShape.ArrowCursor)
        grab=QWidget.mouseGrabber()
        if grab and (grab is self or self.isAncestorOf(grab)):grab.releaseMouse()
    def recover_surface(self):
        if self._closing or not self.isVisible() or self.recovering:return
        self.recovering=True
        if not QApplication.mouseButtons()&Qt.MouseButton.LeftButton:self.release_interactions()
        for tile in self.workspace.tiles:
            tile.graph._layer=None;tile.graph._projection_key=None;tile.graph.update()
        self.shell.update();self.position_overlays();self.recovering=False
    def showEvent(self,event):
        super().showEvent(event)
        if self.windowHandle():self.windowHandle().installEventFilter(self)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,"spotlight"):self.position_overlays()
    def position_overlays(self):
        self.spotlight.move(max(10,(self.shell.width()-self.spotlight.width())//2),max(85,int(self.shell.height()*.15)))
        self.overlay.setGeometry(self.shell.rect())
        if hasattr(self,'trash_vortex'):self.trash_vortex.reposition()
        if self.audio:
            self.audio.resize(min(550,max(320,self.workspace.width()-24)),112);self.audio.move(12,max(70,self.workspace.height()-124))
        if hasattr(self,'connections'):self.connections.refresh()
    def error(self,message):
        self.status.setText(message);QMessageBox.warning(self,"Orbit",message)
    def closeEvent(self,event):
        if not self.documents.can_close():event.ignore();return
        panel_motion.finish_all(self)
        self.apply_pending_settings();self.settings_save_timer.stop()
        self.config['pane_sizes']={name:pane.stored_sizes() for name,pane in self.saved_splitters.items()}
        self.config['detail_width']=self.right.width() if self.right.isVisible() else self.detail_width
        self.config['workspace_layout']=self.workspace.snapshot()
        self.config['file_layout']=self.documents.snapshot()
        self.config['window_size']=[self.normalGeometry().width(),self.normalGeometry().height()]
        self.config['window_maximized']=self.isMaximized();save_config(self.config)
        self._closing=True
        self.documents.shutdown();self.connections.timer.stop()
        self.index_search.stop();self.search_timer.stop();self.cancel_trip()
        self.address.stop()
        if self.drop_dialog:self.drop_dialog.close()
        if self.audio:self.audio.player.stop();self.audio_connection.timer.stop()
        QApplication.instance().removeEventFilter(self)
        self.spring.cancel();self.command.stop();self.selection_model.shutdown()
        self.trash_vortex.stop()
        if self.routing:self.routing.shutdown()
        for tile in self.workspace.tiles:tile.graph.moon_timer.stop();tile.graph.timer.stop()
        self.pool.shutdown(wait=False,cancel_futures=True);self.thumbnails.shutdown()
        super().closeEvent(event)

def main():
    if '--version' in sys.argv:print('Orbit Explorer 0.6.6');return
    if '--search-worker' in sys.argv:
        import json,signal
        from search_worker import run,stop
        signal.signal(signal.SIGTERM,stop);run(json.loads(sys.argv[sys.argv.index('--search-worker')+1]));return
    surface=QSurfaceFormat.defaultFormat();surface.setAlphaBufferSize(8);QSurfaceFormat.setDefaultFormat(surface)
    app=QApplication(sys.argv);app.setApplicationName("orbit-explorer");app.setDesktopFileName("io.github.orbitexplorer.Orbit")
    window=Orbit();window.show()
    if '--smoke-test' in sys.argv or '--diagnostics' in sys.argv:
        def finish():
            if '--smoke-test' in sys.argv:
                from PySide6.QtPdf import QPdfDocument
                from PySide6.QtMultimediaWidgets import QVideoWidget
            else:
                import json
                print(json.dumps({'qt_platform':app.platformName(),'device_pixel_ratio':window.devicePixelRatioF(),
                    'surface_alpha_bits':window.windowHandle().format().alphaBufferSize(),
                    'translucent_surface':window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground),
                    'opacity_percent':window.config['opacity'],'bundled_fontconfig':bool(os.environ.get('_ORBIT_BUNDLED_FONTCONFIG')),
                    'niri_detected':bool(os.environ.get('NIRI_SOCKET') or 'niri' in os.environ.get('XDG_CURRENT_DESKTOP','').lower())},indent=2),flush=True)
            assert not window.grab().isNull()
            print('Orbit 0.6.6: UI, QtPdf and native video imports OK' if '--smoke-test' in sys.argv else 'Orbit 0.6.6: diagnostic render OK',flush=True);window.close();app.quit()
        QTimer.singleShot(1200,finish)
    sys.exit(app.exec())

if __name__=="__main__":main()

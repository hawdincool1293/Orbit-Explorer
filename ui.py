"""Small UI components, live indexed search, and configurable appearance."""
# Orbit input patch: trackpad-opening-2026-09-30
import orbit_controls
import os
import shutil
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QObject, QProcess, QTimer, QAbstractListModel, QModelIndex, QPointF, QRectF, QPropertyAnimation
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPen, QKeySequence
from PySide6.QtWidgets import (QWidget,QFrame,QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,
    QPushButton,QLineEdit,QListView,QCheckBox,QSlider,QColorDialog,
    QFileDialog,QScrollArea,QGraphicsOpacityEffect,QTabWidget,QListWidget,QStackedWidget,QGridLayout,QApplication)
from appearance import PRESETS,COLOR_NAMES,SYSTEM_PRESET,icon_themes,register_fonts
from design import SurfaceDialog,DialogHandle,ui_icon,Panel,ComboBox as QComboBox,FontComboBox as QFontComboBox,SpinBox as QSpinBox


class PathModel(QAbstractListModel):
    def __init__(self,parent=None):
        super().__init__(parent);self.paths=[];self.seen=set();self.names_only=False
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.paths)
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row()>=len(self.paths):return None
        path=self.paths[index.row()]
        if role==Qt.ItemDataRole.DisplayRole:return (Path(path).name or path) if self.names_only else f"{Path(path).name or path}\n{path}"
        if role in (Qt.ItemDataRole.UserRole,Qt.ItemDataRole.ToolTipRole):return path
    def clear(self):
        self.beginResetModel();self.paths=[];self.seen=set();self.endResetModel()
    def append(self,paths):
        fresh=[]
        for p in paths:
            if p not in self.seen:self.seen.add(p);fresh.append(p)
        if fresh:
            n=len(self.paths);self.beginInsertRows(QModelIndex(),n,n+len(fresh)-1);self.paths.extend(fresh);self.endInsertRows()


class IndexedSearch(QObject):
    batch=Signal(object)
    status=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.generation=0;self.process=None;self.directories_only=False
    def stop(self):
        self.generation+=1
        if self.process:
            process=self.process;self.process=None;process.terminate()
            QTimer.singleShot(1500,process,lambda:process.kill() if process.state()!=QProcess.ProcessState.NotRunning else None)
    def search(self,query,local_paths=(),strict=False):
        import json,sys
        from search_query import parse_query
        self.stop()
        if not query:return
        parsed=parse_query(query,strict=strict)
        if parsed.error:self.status.emit(parsed.error);return
        token=self.generation;process=QProcess(self);self.process=process;pending=bytearray()
        def receive():
            pending.extend(bytes(process.readAllStandardOutput()))
            while b"\n" in pending:
                line,_,tail=pending.partition(b"\n");pending[:]=tail
                if token!=self.generation:continue
                try:
                    message=json.loads(line)
                    if 'paths' in message:self.batch.emit(message['paths'])
                    elif 'status' in message:self.status.emit(message['status'])
                except (ValueError,KeyError):pass
        def finish(code,status):
            receive()
            if token==self.generation:
                if code and process.readAllStandardError():self.status.emit('Search helper stopped unexpectedly.')
                self.process=None
            process.deleteLater()
        process.readyReadStandardOutput.connect(receive);process.finished.connect(finish)
        process.errorOccurred.connect(lambda e:self.status.emit(process.errorString()) if token==self.generation else None)
        payload=json.dumps(dict(query=query,local_paths=list(local_paths),directories_only=self.directories_only,strict=bool(strict)))
        process.start(sys.executable,['--search-worker',payload] if getattr(sys,'frozen',False) else [str(Path(__file__).with_name('search_worker.py')),payload])


class KeyButton(QPushButton):
    changed=Signal(str)
    def __init__(self,value):
        super().__init__(value);self.value=value;self.recording=False
        self.clicked.connect(self.begin)
    def begin(self):
        self.recording=True;self.setText("Press a key…");self.setFocus()
    def focusNextPrevChild(self,next):
        return False if self.recording else super().focusNextPrevChild(next)
    def keyPressEvent(self,event):
        if self.recording and event.key() not in (Qt.Key.Key_Control,Qt.Key.Key_Shift,Qt.Key.Key_Alt,Qt.Key.Key_Meta):
            self.value=QKeySequence(event.keyCombination()).toString();self.setText(self.value);self.recording=False;self.changed.emit(self.value);event.accept()
        else:super().keyPressEvent(event)


class Settings(SurfaceDialog):
    changed=Signal()
    def __init__(self,config,parent):
        super().__init__(config,parent);register_fonts();self.setWindowTitle("Orbit settings");self.resize(820,690);self.setMinimumSize(760,580)
        layout=QVBoxLayout(self);layout.setContentsMargins(24,20,24,22);layout.setSpacing(18)
        header=DialogHandle();row=QHBoxLayout(header);row.setContentsMargins(4,0,0,0)
        title=QLabel('Make Orbit yours');title.setObjectName('dialogTitle');row.addWidget(title);row.addStretch()
        close=QPushButton();close.setProperty('role','icon');close.setAutoDefault(False);close.setFixedSize(36,36);close.setIcon(ui_icon('close',config['colors']['muted']))
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close.setToolTip('Close settings');close.clicked.connect(self.accept);row.addWidget(close);layout.addWidget(header)
        body=QHBoxLayout();body.setSpacing(22);layout.addLayout(body,1)
        self.navigation=QListWidget();self.navigation.setObjectName('settingsNav');body.addWidget(self.navigation)
        self.pages=QStackedWidget();body.addWidget(self.pages,1);self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        def page(name,description):
            self.navigation.addItem(name)
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
            content=QWidget();box=QVBoxLayout(content);box.setContentsMargins(4,6,16,14);box.setSpacing(16)
            heading=QLabel(name);heading.setObjectName('sectionTitle');box.addWidget(heading)
            note=QLabel(description);note.setObjectName('muted');note.setWordWrap(True);box.addWidget(note)
            scroll.setWidget(content);self.pages.addWidget(scroll);return box
        appearance=page('Appearance','Soft surfaces, your colors. System mode follows your Caelestia palette.')
        form=QFormLayout();form.setVerticalSpacing(14);appearance.addLayout(form)
        preset=QComboBox();preset.addItems(list(PRESETS)+[SYSTEM_PRESET,"Custom"]);preset.setCurrentText(config["preset"]);form.addRow("Color palette",preset)
        preset.currentTextChanged.connect(self.preset)
        opacity=QSlider(Qt.Orientation.Horizontal);opacity.setObjectName('opacitySlider');opacity.setRange(25,100);opacity.setValue(config["opacity"]);form.addRow("Window opacity",opacity)
        opacity.valueChanged.connect(lambda v:self.set_value("opacity",v))
        if os.environ.get('NIRI_SOCKET') or 'niri' in os.environ.get('XDG_CURRENT_DESKTOP','').lower():
            note=QLabel('Niri can place a solid border/focus-ring background behind transparent windows. If opacity looks ineffective, add the Orbit-only window rule to your Niri config and validate it.');note.setWordWrap(True);form.addRow(note)
            rule=QPushButton('Copy Niri transparency rule');rule.clicked.connect(lambda:QApplication.clipboard().setText((Path(__file__).parent/'assets/niri-window-rule.kdl').read_text()));form.addRow(rule)
        palette=QLineEdit(config["palette_file"]);palette.setPlaceholderText("Automatic Caelestia scheme.json");form.addRow("Palette file",palette)
        palette.editingFinished.connect(lambda:self.set_value("palette_file",palette.text().strip()))
        grid=QGridLayout();grid.setSpacing(12);appearance.addLayout(grid);self.color_buttons={}
        for i,(key,label) in enumerate(COLOR_NAMES.items()):
            cell=QVBoxLayout();caption=QLabel(label);caption.setObjectName('muted');cell.addWidget(caption)
            button=QPushButton();button.clicked.connect(lambda checked=False,k=key:self.color(k));cell.addWidget(button)
            self.color_buttons[key]=button;grid.addLayout(cell,i//2,i%2)
        appearance.addStretch();self.refresh_colors()
        typography=page('Typography','Three fonts are included with Orbit. Your installed fonts are available in the same dropdown.')
        form=QFormLayout();form.setVerticalSpacing(16);typography.addLayout(form)
        self.font_presets=QComboBox();self.font_presets.addItem('Choose a type style…','')
        for label,family in (('Manrope · modern','Manrope'),('Nunito Sans · rounded','Nunito Sans'),('Inter · clean','Inter')):
            self.font_presets.addItem(label,family)
        form.addRow('Quick styles',self.font_presets)
        self.font_picker=QFontComboBox();self.font_picker.setObjectName('fontPicker');self.font_picker.setEditable(True)
        self.font_picker.setCurrentFont(QFont(config['font']));self.font_picker.setMaxVisibleItems(10);self.font_picker.setMinimumWidth(245)
        form.addRow('Font family',self.font_picker)
        self.font_size=QSpinBox();self.font_size.setRange(9,16);self.font_size.setSuffix(' pt');self.font_size.setValue(config['font_size'])
        form.addRow('Interface size',self.font_size)
        self.font_preview=QLabel('The quick brown fox\njumps over the lazy dog.\n\nOrbit · Pictures · Projects\nAa Bb Cc  0123456789')
        self.font_preview.setObjectName('fontPreview');self.font_preview.setWordWrap(True);self.font_preview.setMinimumHeight(230);typography.addWidget(self.font_preview)
        self.font_picker.currentFontChanged.connect(self.select_font)
        self.font_presets.currentIndexChanged.connect(lambda _:self.font_picker.setCurrentFont(QFont(self.font_presets.currentData())) if self.font_presets.currentData() else None)
        self.font_size.valueChanged.connect(lambda v:(self.set_value('font_size',v),self.preview_font()))
        self.preview_font();typography.addStretch()
        behavior=page('Controls','Tune the way you navigate, select, preview and listen.')
        form=QFormLayout();form.setVerticalSpacing(16);behavior.addLayout(form)
        orbit_controls.add_settings(self,form)
        for key,label in (("invert_vertical","Invert vertical orbit"),("invert_horizontal","Invert horizontal orbit"),
                          ("spotlight","Spotlight when I start typing"),("search_strict","Strict search (exact filename and case)"),("show_hidden","Show hidden files"),
                          ("audio_internal","Play audio inside Orbit"),("files_internal","Open supported files inside Orbit"),("thumbnails","Image and video previews"),("moons","Animate center moons")):
            check=QCheckBox();check.setObjectName(key);check.setChecked(config[key]);check.toggled.connect(lambda value,k=key:self.set_value(k,value));form.addRow(label,check)
        spacing=QSlider(Qt.Orientation.Horizontal);spacing.setObjectName('spacingSlider');spacing.setRange(100,220);spacing.setValue(round(config['node_spacing']*100))
        spacing.valueChanged.connect(lambda v:self.set_value('node_spacing',v/100));form.addRow('Node spacing',spacing)
        keybind=KeyButton(config["label_key"]);keybind.changed.connect(lambda value:self.set_value("label_key",value));form.addRow("Hold to reveal names",keybind)
        note=QLabel("Hold to show names below the existing nodes. The camera, node positions and node sizes do not change.")
        note.setObjectName('muted');note.setWordWrap(True);form.addRow(note);behavior.addStretch()
        drop=QComboBox();drop.addItem('Centered dialog','center');drop.addItem('Menu beside cursor','cursor')
        drop.setCurrentIndex(max(0,drop.findData(config['drop_popup'])))
        drop.currentIndexChanged.connect(lambda _:self.set_value('drop_popup',drop.currentData()));form.addRow('Right-drag action chooser',drop)
        note=QLabel('Left-drag moves on release. Right-drag a file for Move / Copy / Link / Cancel; right-drag empty canvas to pan.')
        note.setWordWrap(True);note.setObjectName('muted');form.addRow(note)
        motion=page('Navigation','A single continuous flight through directory clouds, with adjustable rotation, easing and crossfade.')
        form=QFormLayout();motion.addLayout(form)
        for key,label in (('navigation_enabled','Animate search navigation'),('navigation_rotate','Orbit around the center during flight')):
            check=QCheckBox();check.setChecked(config[key]);check.toggled.connect(lambda v,k=key:self.set_value(k,v));form.addRow(label,check)
        speed=QSpinBox();speed.setObjectName('flightDuration');speed.setRange(150,6000);speed.setSuffix(' ms');speed.setSingleStep(100);speed.setValue(config['navigation_duration'])
        speed.setToolTip('Minimum animated duration: 150 ms. Turn off Animate search navigation for an instant jump (no flight animation).')
        speed.valueChanged.connect(lambda v:self.set_value('navigation_duration',v));form.addRow('Total flight duration (minimum 150 ms)',speed)
        fade=QSlider(Qt.Orientation.Horizontal);fade.setRange(0,100);fade.setValue(config['navigation_fade'])
        fade.valueChanged.connect(lambda v:self.set_value('navigation_fade',v));form.addRow('Directory crossfade amount',fade)
        easing=QComboBox();easing.addItems(['Smooth','Gentle','Linear']);easing.setCurrentText(config['navigation_easing'])
        easing.currentTextChanged.connect(lambda v:self.set_value('navigation_easing',v));form.addRow('Camera easing',easing)
        note=QLabel('Animated flights: 150–6000 ms (minimum 150 ms). For no animation, disable Animate search navigation: the destination loads directly as soon as its files are ready. Higher duration means slower motion. Fade 0 switches scenes without blending.')
        note.setWordWrap(True);motion.addWidget(note);motion.addStretch()
        entrances=page('Panel animations','Original Orbit-style cubic transitions and fades, without bounce or overshoot. Your desktop window animations remain separate.')
        form=QFormLayout();entrances.addLayout(form)
        for key,label in (('panel_motion_enabled','Enable panel animations'),('panel_motion_sidebar','Search and info bars'),
                          ('panel_motion_files','File players, editors and video tools'),('panel_motion_dialogs','Dialogs, routing and command bar'),('panel_motion_fade','Fade search, info, audio bars and dialogs')):
            check=QCheckBox();check.setObjectName(key);check.setChecked(config.get(key,True))
            check.toggled.connect(lambda value,k=key:self.set_value(k,value));form.addRow(label,check)
        duration=QSpinBox();duration.setObjectName('panelMotionDuration');duration.setRange(100,1200);duration.setSingleStep(20);duration.setSuffix(' ms');duration.setValue(config.get('panel_motion_duration',240))
        duration.valueChanged.connect(lambda value:self.set_value('panel_motion_duration',value));form.addRow('Animation duration',duration)
        rate=QComboBox();rate.setObjectName('panelMotionFrameRate')
        for fps in (60,120,144,240):rate.addItem(f'{fps} FPS target',fps)
        rate.setCurrentIndex(max(0,rate.findData(config.get('panel_motion_fps',120))))
        rate.currentIndexChanged.connect(lambda _:self.set_value('panel_motion_fps',rate.currentData()));form.addRow('Frame-rate target',rate)
        for key,label,initial in (('panel_motion_travel','File panels and video tools: travel (0 = none)',100),):
            slider=QSlider(Qt.Orientation.Horizontal);slider.setObjectName(key);slider.setRange(0,100);slider.setValue(config.get(key,initial))
            slider.valueChanged.connect(lambda value,k=key:self.set_value(k,value));form.addRow(label,slider)
        note=QLabel('Opening and closing use the original cubic ease-out. Bars and dialogs fade in place; file panels and video tools slide without bounce so native video remains live. Turn off the master switch for instant changes, or choose which areas animate. Reopening reverses a pending close. Frame rate is a target, not a guarantee: display refresh rate, compositor and workload determine actual presentation. Changes are saved automatically.')
        note.setWordWrap(True);note.setObjectName('muted');entrances.addWidget(note);entrances.addStretch()
        icons=page('Icons & previews','Use your desktop icon theme, or add your own file-type artwork.')
        form=QFormLayout();form.setVerticalSpacing(12);icons.addLayout(form)
        theme=QComboBox();theme.setEditable(True);theme.addItems(icon_themes());theme.setCurrentText(config["icon_theme"]);form.addRow("Icon theme",theme)
        theme.currentTextChanged.connect(lambda value:self.set_value("icon_theme",value))
        note=QLabel("Sweet (bundled) includes Sweet Rainbow folders and Candy file icons, with no system installation needed. System follows your desktop icon selection. Per-type overrides take priority.")
        note.setWordWrap(True);form.addRow(note)
        for category in ("folder","document","image","video","audio","archive","file","drive","partition"):
            row=QHBoxLayout();edit=QLineEdit(config["type_icons"].get(category,""));edit.setPlaceholderText("Theme icon name or image path")
            edit.editingFinished.connect(lambda k=category,e=edit:self.type_icon(k,e.text().strip()))
            browse=QPushButton("…");browse.setFixedWidth(35);browse.clicked.connect(lambda checked=False,k=category,e=edit:self.browse_icon(k,e))
            row.addWidget(edit);row.addWidget(browse);form.addRow(category.title(),row)
        icons.addStretch();self.navigation.setCurrentRow(0)
        bottom=QHBoxLayout();hint=QLabel('Changes are saved automatically');hint.setObjectName('muted');bottom.addWidget(hint);bottom.addStretch()
        done=QPushButton('Done');done.setObjectName('primaryButton');done.clicked.connect(self.accept);bottom.addWidget(done);layout.addLayout(bottom)
    def select_font(self,font):
        self.set_value('font',font.family());self.preview_font()
    def preview_font(self):
        self.font_preview.setFont(QFont(self.config['font'],self.config['font_size']+4))
    def refresh_colors(self):
        for key,button in self.color_buttons.items():
            value=self.config['colors'][key];color=QColor(value)
            button.setText(value.upper());button.setStyleSheet(f'background:{value};color:{"#111820" if color.lightnessF()>.55 else "#f2f5f8"};border:1px solid rgba(170,190,200,40);border-radius:12px;padding:8px;')
    def set_value(self,key,value):
        if self.config.get(key)==value:return
        self.config[key]=value;self.changed.emit()
    def preset(self,name):
        self.config["preset"]=name
        if name in PRESETS:self.config["colors"]=dict(PRESETS[name])
        self.changed.emit();self.refresh_colors()
    def color(self,key):
        c=QColorDialog.getColor(QColor(self.config["colors"][key]),self)
        if c.isValid():self.config["colors"][key]=c.name();self.config["preset"]="Custom";self.changed.emit();self.refresh_colors()
    def type_icon(self,key,value):
        self.config["type_icons"][key]=value;self.changed.emit()
    def browse_icon(self,key,edit):
        path,_=QFileDialog.getOpenFileName(self,"Choose icon",str(Path.home()),"Images (*.png *.jpg *.webp *.svg)")
        if path:edit.setText(path);self.type_icon(key,path)


class Spotlight(Panel):
    def __init__(self,model,parent):
        super().__init__(parent);self.config=parent.config;self.setObjectName("spotlight");self.setFixedWidth(610)
        layout=QVBoxLayout(self);layout.setContentsMargins(20,16,20,16)
        row=QHBoxLayout();layout.addLayout(row)
        self.edit=QLineEdit();self.edit.setPlaceholderText("Search files…");self.edit.setObjectName("spotlightInput");row.addWidget(self.edit,1)
        self.exact=QCheckBox('Exact');self.exact.setFocusPolicy(Qt.FocusPolicy.NoFocus);self.exact.setToolTip('Exact filename including extension and letter case; contains: becomes case-sensitive.');row.addWidget(self.exact)
        self.hint=QLabel("is: png  ·  date: dd/mm/yyyy  ·  contains: text");self.hint.setObjectName("caption");layout.addWidget(self.hint)
        self.list=QListView();self.list.setModel(model);self.list.setUniformItemSizes(True);self.list.setMinimumHeight(215);layout.addWidget(self.list)
        self.setFixedHeight(325);self.hide()
        self.effect=QGraphicsOpacityEffect(self);self.setGraphicsEffect(self.effect);self.fade=QPropertyAnimation(self.effect,b"opacity",self);self.fade.setDuration(180)
    def reveal(self):
        self.show();self.raise_();self.fade.stop()
        from panel_motion import reveal
        reveal(self,self.config,'sidebar',self.effect);self.edit.setFocus()
    def dismiss(self):
        self.fade.stop()
        from panel_motion import dismiss
        dismiss(self,self.config,'sidebar',self.hide,self.effect)


class DragOverlay(QWidget):
    """Animated node fan that follows the pointer across both graph and sidebar."""
    def __init__(self,config,parent):
        super().__init__(parent);self.config=config;self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.paths=[];self.origins=[];self.pointer=QPointF();self.progress=0.;self.hide()
        self.timer=QTimer(self);self.timer.setInterval(16);self.timer.timeout.connect(self.tick)
    def start(self,paths,origins,point):
        self.paths=paths;self.origins=origins;self.pointer=QPointF(point);self.progress=0.
        self.setGeometry(self.parentWidget().rect());self.show();self.raise_();self.timer.start()
    def tick(self):
        self.progress+=(1-self.progress)*.18
        if self.progress>.995:self.progress=1.;self.timer.stop()
        self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setFont(QFont(self.config["font"],9))
        for i,path in enumerate(self.paths[:16]):
            target=self.pointer+QPointF(22+(i%4)*23,22+(i//4)*23)
            origin=self.origins[i] if i<len(self.origins) else self.pointer
            center=origin*(1-self.progress)+target*self.progress
            p.setPen(QPen(QColor(self.config["colors"]["primary"]),1.5))
            p.setBrush(QColor(self.config["colors"]["panel"]));p.drawEllipse(center,12,12)
        p.setPen(QColor(self.config["colors"]["text"]));p.drawText(self.pointer+QPointF(24,-9),f"{len(self.paths)} item{'s' if len(self.paths)!=1 else ''}")


class SendTo(QDialog):
    def __init__(self,paths,parent):
        super().__init__(parent);self.setWindowTitle("Send to");self.resize(560,390);self.network=False
        layout=QVBoxLayout(self);layout.addWidget(QLabel(f"Send {len(paths)} selected item(s)"))
        self.path=QLineEdit();self.path.setPlaceholderText("Type a directory path, or search its name");layout.addWidget(self.path)
        self.model=PathModel(self);self.list=QListView();self.list.setModel(self.model);layout.addWidget(self.list)
        self.search=IndexedSearch(self);self.search.directories_only=True;self.search.batch.connect(self.results)
        self.hint=QLabel();self.hint.setWordWrap(True);layout.addWidget(self.hint);self.search.status.connect(self.hint.setText)
        self.debounce=QTimer(self);self.debounce.setSingleShot(True);self.debounce.setInterval(180);self.debounce.timeout.connect(self.lookup)
        self.path.textChanged.connect(lambda _:self.debounce.start())
        self.list.clicked.connect(lambda index:self.path.setText(index.data(Qt.ItemDataRole.UserRole)))
        self.mode=QComboBox();self.mode.addItems(["Move","Copy"]);layout.addWidget(self.mode)
        row=QHBoxLayout()
        for text,fn in (("Browse…",self.browse),("Choose in Orbit",self.choose_network),("Send",self.confirm)):
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        layout.addLayout(row);self.finished.connect(lambda _:self.search.stop())
    def lookup(self):
        self.model.clear();text=self.path.text().strip()
        if text and not os.path.isdir(os.path.expanduser(text)):self.search.search(text)
        else:self.search.stop()
    def results(self,paths):
        self.model.append(paths)
    def browse(self):
        path=QFileDialog.getExistingDirectory(self,"Destination")
        if path:self.path.setText(path)
    def choose_network(self):
        self.network=True;self.accept()
    def confirm(self):
        if os.path.isdir(os.path.expanduser(self.path.text().strip())):self.accept()
        else:self.hint.setText("Choose an existing directory.")

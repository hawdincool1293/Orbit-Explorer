"""Native single-track video timeline, live preview and non-destructive export."""
# Orbit video tools patch: hidden-by-default-2026-09-30
import video_playback_controls
import copy,json,time
from dataclasses import asdict
from pathlib import Path
from PySide6.QtCore import Qt,Signal,QTimer,QUrl,QRectF,QPointF
from PySide6.QtGui import QPainter,QColor,QPen
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QScrollArea,QSlider,
    QDoubleSpinBox,QFileDialog,QMessageBox,QDialog,QFormLayout,QProgressBar,QStackedWidget,QGridLayout)
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from design import SurfaceDialog,ComboBox,SpinBox
from media_tools import Clip,probe,split_clip,stitch,timeline_args,video_formats,validate_timeline
from export_job import ExportJob

class Timeline(QWidget):
    changed=Signal();selected=Signal();seek=Signal(float);editing=Signal()
    def __init__(self,config):
        super().__init__();self.config=config;self.clips=[];self.selection=None;self.playhead=0.;self.scale=45.;self.drag=None
        self.setMinimumHeight(100);self.setMouseTracking(True);self.resize_track()
    @property
    def duration(self):return max((c.end for c in self.clips),default=0.)
    def resize_track(self):self.setMinimumWidth(round(max(15,self.duration+5)*self.scale)+30);self.update()
    def rect_for(self,clip):return QRectF(12+clip.start*self.scale,34,max(4,clip.duration*self.scale),44)
    def paintEvent(self,event):
        p=QPainter(self);c=self.config['colors'];p.fillRect(self.rect(),QColor(c['background']));p.setRenderHint(QPainter.RenderHint.Antialiasing)
        step=max(1,round(70/self.scale));p.setPen(QColor(c['muted']))
        left=max(0,int(event.rect().left()/self.scale)//step*step)
        for second in range(left,int(event.rect().right()/self.scale)+step,step):
            x=12+second*self.scale;p.drawLine(x,24,x,29);p.drawText(QPointF(x+3,18),f'{second//60}:{second%60:02}')
        for clip in self.clips:
            rect=self.rect_for(clip)
            if not rect.intersects(QRectF(event.rect())):continue
            p.setBrush(QColor(c['secondary']));p.setPen(QPen(QColor(c['primary'] if clip is self.selection else c['lines']),2))
            p.drawRoundedRect(rect,7,7);p.setPen(QColor(c['text']))
            p.drawText(rect.adjusted(10,0,-10,0),Qt.AlignmentFlag.AlignVCenter,p.fontMetrics().elidedText(Path(clip.path).name,Qt.TextElideMode.ElideMiddle,int(max(0,rect.width()-20))))
            for x in (rect.left()+4,rect.right()-4):p.drawLine(QPointF(x,44),QPointF(x,68))
        p.setPen(QPen(QColor(c['accent']),2));x=12+self.playhead*self.scale;p.drawLine(QPointF(x,22),QPointF(x,90))
    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return
        pos=event.position();clip=next((c for c in reversed(self.clips) if self.rect_for(c).contains(pos)),None)
        if not clip:self.seek.emit(max(0,(pos.x()-12)/self.scale));return
        self.selection=clip;self.selected.emit();self.editing.emit();rect=self.rect_for(clip)
        mode='in' if pos.x()-rect.left()<8 else 'out' if rect.right()-pos.x()<8 else 'move'
        self.drag=(clip,mode,pos.x(),clip.start,clip.source_in,clip.source_out);self.update()
    def mouseMoveEvent(self,event):
        if not self.drag or not event.buttons()&Qt.MouseButton.LeftButton:return
        clip,mode,x,start,source_in,source_out=self.drag;delta=round((event.position().x()-x)/self.scale*100)/100
        others=[c for c in self.clips if c is not clip]
        if mode=='move':
            desired=max(0,start+delta);candidates=[desired,0.]+[c.end for c in others]+[c.start-clip.duration for c in others]
            valid=[v for v in candidates if v>=0 and all(v>=c.end-.001 or v+clip.duration<=c.start+.001 for c in others)]
            if valid:clip.start=min(valid,key=lambda v:abs(v-desired))
        elif mode=='in':
            previous=max((c.end for c in others if c.end<=start+.001),default=0.)
            delta=max(-source_in,previous-start,min(delta,source_out-source_in-.04))
            clip.source_in=source_in+delta;clip.start=start+delta
        else:
            following=min((c.start for c in others if c.start>=start+source_out-source_in-.001),default=float('inf'))
            clip.source_out=max(source_in+.04,min(source_out+delta,clip.info['duration'],source_in+following-clip.start))
        self.resize_track();self.changed.emit()
    def mouseReleaseEvent(self,event):self.drag=None

class VideoExport(SurfaceDialog):
    exported=Signal(str)
    def __init__(self,clips,config,parent):
        super().__init__(config,parent);self.clips=copy.deepcopy(clips);self.job=None;self.setWindowTitle('Export timeline');self.resize(450,330)
        box=QVBoxLayout(self);form=QFormLayout();box.addLayout(form)
        self.format=ComboBox();self.format.addItems(video_formats());form.addRow('File type',self.format)
        self.size=ComboBox()
        info=clips[0].info;self.size.addItem(f'Source · {info["width"]} × {info["height"]}',(info['width'],info['height']))
        for label,size in (('1080p',(1920,1080)),('720p',(1280,720)),('480p',(854,480))):self.size.addItem(label,size)
        form.addRow('Canvas size',self.size)
        self.fps=SpinBox();self.fps.setRange(1,60);self.fps.setValue(30);form.addRow('Frames per second',self.fps)
        self.note=QLabel('Gaps export as black video and silence. Audio follows each clip. Originals stay unchanged.');self.note.setWordWrap(True);box.addWidget(self.note)
        self.progress=QProgressBar();box.addWidget(self.progress)
        row=QHBoxLayout();self.go=QPushButton('Export to…');self.go.clicked.connect(self.export);row.addWidget(self.go)
        self.cancel=QPushButton('Close');self.cancel.clicked.connect(self.reject);row.addWidget(self.cancel);box.addLayout(row)
    def export(self):
        fmt=self.format.currentText()
        if not fmt:self.note.setText('Install ffmpeg with a supported video encoder.');return
        path,_=QFileDialog.getSaveFileName(self,'Export timeline',str(Path(self.clips[0].path).with_name('Edited.'+fmt)),f'{fmt.upper()} (*.{fmt})')
        if not path:return
        if Path(path).suffix.lower()!='.'+fmt:path+='.'+fmt
        try:
            width,height=self.size.currentData();args=timeline_args(self.clips,fmt,width,height,self.fps.value())
            self.job=ExportJob(self);self.job.progress.connect(lambda v:self.progress.setValue(round(v)));self.job.finished.connect(self.finished_export)
            self.job.start(args,path,max(c.end for c in self.clips));self.go.setEnabled(False);self.cancel.setText('Cancel export');self.note.setText('Exporting…')
        except Exception as exc:self.note.setText(str(exc));self.job=None
    def finished_export(self,path,error):
        self.go.setEnabled(True);self.cancel.setText('Close');self.job=None
        self.note.setText(error or 'Exported to '+path)
        if path:self.progress.setValue(100);self.exported.emit(path)
    def reject(self):
        if self.job:self.job.cancel();return
        super().reject()
    def closeEvent(self,event):
        if self.job:self.job.cancel();event.ignore()
        else:super().closeEvent(event)

class VideoEditor(QWidget):
    def __init__(self,panel):
        super().__init__();self.panel=panel;self.config=panel.config;self.modified=False;self.undo_stack=[];self.playing=False;self.current_clip=None;self.pending_seek=None;self.preview_only=False
        self.setMinimumWidth(450)
        self.box=QVBoxLayout(self);self.box.setContentsMargins(0,0,0,0);self.box.setSpacing(5)
        self.stack=QStackedWidget();self.video=QVideoWidget();self.video.setMinimumHeight(90);self.stack.addWidget(self.video)
        blank=QLabel('Gap · black video / silence');blank.setAlignment(Qt.AlignmentFlag.AlignCenter);self.stack.addWidget(blank);self.box.addWidget(self.stack,1)
        self.player=QMediaPlayer(self);self.output=QAudioOutput(self);self.player.setAudioOutput(self.output);self.player.setVideoOutput(self.video);self.output.setVolume(self.config['volume']/100)
        self.player.errorOccurred.connect(lambda *_:panel.status.setText(self.player.errorString()))
        self.player.mediaStatusChanged.connect(self.media_ready)
        self.video.videoSink().videoFrameChanged.connect(self.preview_frame)
        controls=QGridLayout();self.box.addLayout(controls)
        for i,(label,fn) in enumerate((('Play / pause',self.toggle),('Add clip…',self.add_file),('Split',self.split),('Remove',self.remove),('Stitch',self.join),('Undo',self.undo),('Export…',self.export))):
            b=QPushButton(label);b.clicked.connect(fn);controls.addWidget(b,i//4,i%4)
        sound=QHBoxLayout();controls.addLayout(sound,1,3)
        mute=QPushButton('Mute');mute.setCheckable(True);mute.toggled.connect(self.output.setMuted);mute.setToolTip('Mute video audio');sound.addWidget(mute)
        self.volume=QSlider(Qt.Orientation.Horizontal);self.volume.setRange(0,100);self.volume.setValue(self.config['volume']);self.volume.setMaximumWidth(65);self.volume.setToolTip('Video volume');self.volume.valueChanged.connect(lambda v:self.output.setVolume(v/100));sound.addWidget(self.volume)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFixedHeight(121);self.timeline=Timeline(self.config);scroll.setWidget(self.timeline);self.box.addWidget(scroll)
        self.timeline.seek.connect(self.seek);self.timeline.changed.connect(self.edited);self.timeline.selected.connect(self.refresh_fields);self.timeline.editing.connect(self.checkpoint)
        bar=QHBoxLayout();self.box.addLayout(bar);self.fields=[]
        for label in ('Source in','Source out','Position'):
            column=QVBoxLayout();bar.addLayout(column);column.addWidget(QLabel(label));spin=QDoubleSpinBox();spin.setDecimals(2);spin.setRange(0,864000);spin.setSuffix(' s');spin.setMaximumWidth(115);spin.editingFinished.connect(self.trim_fields);self.fields.append(spin);column.addWidget(spin)
        column=QVBoxLayout();bar.addLayout(column);self.clock=QLabel('0.00 s');column.addWidget(self.clock)
        zoom=QSlider(Qt.Orientation.Horizontal);zoom.setRange(2,160);zoom.setValue(45);zoom.setToolTip('Timeline zoom');zoom.setMaximumWidth(90);zoom.valueChanged.connect(lambda v:(setattr(self.timeline,'scale',v),self.timeline.resize_track()));column.addWidget(zoom)
        projects=QHBoxLayout();self.box.addLayout(projects)
        for text,fn in (('Save timeline…',self.save_project),('Open timeline…',self.open_project)):
            b=QPushButton(text);b.clicked.connect(fn);projects.addWidget(b)
        projects.addStretch();tip=QLabel('Drag clip edges to trim · drag the body to move · click ruler to seek');tip.setWordWrap(True);tip.setObjectName('muted');projects.addWidget(tip)
        self.timer=QTimer(self);self.timer.setInterval(30);self.timer.timeout.connect(self.tick)
        self.add_path(panel.path,initial=True)
        video_playback_controls.install(self)
    @property
    def sources(self):return list(dict.fromkeys(c.path for c in self.timeline.clips))
    def checkpoint(self):
        self.pause();self.undo_stack.append(copy.deepcopy(self.timeline.clips));self.undo_stack=self.undo_stack[-30:]
    def edited(self):
        self.modified=True;self.refresh_fields();self.timeline.resize_track();self.panel.hub.panels_changed.emit()
        video_playback_controls.sync(self)
    def refresh_fields(self):
        clip=self.timeline.selection
        for field,value in zip(self.fields,(clip.source_in,clip.source_out,clip.start) if clip else (0,0,0)):
            field.blockSignals(True);field.setValue(value);field.setEnabled(clip is not None);field.blockSignals(False)
    def add_file(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Add video clips',str(Path(self.panel.path).parent),'Videos (*.mp4 *.mkv *.webm *.mov *.avi *.m4v *.ogv *.mpg *.mpeg)')
        for path in paths:self.add_path(path)
    def add_path(self,path,initial=False):
        def ready(info):
            if not info['video']:self.panel.status.setText('Choose a file containing video.');return
            if not initial:self.checkpoint()
            clip=Clip(path,0.,info['duration'],self.timeline.duration,info);self.timeline.clips.append(clip);self.timeline.selection=clip
            self.timeline.resize_track();self.refresh_fields();self.modified=not initial or self.modified
            self.panel.status.setText('Non-destructive timeline · export creates a new file')
            self.seek(clip.start);self.panel.hub.panels_changed.emit()
        self.panel.hub.run(self.panel,lambda:probe(path),ready)
    def trim_fields(self):
        clip=self.timeline.selection
        if not clip:return
        before=copy.deepcopy(self.timeline.clips);old=(clip.source_in,clip.source_out,clip.start)
        clip.source_in,clip.source_out,clip.start=[f.value() for f in self.fields]
        try:validate_timeline(self.timeline.clips)
        except ValueError as exc:
            clip.source_in,clip.source_out,clip.start=old;self.panel.status.setText(str(exc));self.refresh_fields();return
        if old!=(clip.source_in,clip.source_out,clip.start):self.undo_stack.append(before);self.pause();self.edited()
    def split(self):
        clip=self.timeline.selection
        if not clip:return
        try:parts=split_clip(clip,self.timeline.playhead)
        except ValueError as exc:self.panel.status.setText(str(exc));return
        self.checkpoint();index=self.timeline.clips.index(clip);self.timeline.clips[index:index+1]=parts;self.timeline.selection=parts[1];self.edited()
    def remove(self):
        if not self.timeline.selection:return
        self.checkpoint();self.timeline.clips.remove(self.timeline.selection);self.timeline.selection=None;self.edited()
    def join(self):self.checkpoint();stitch(self.timeline.clips);self.edited()
    def undo(self):
        if not self.undo_stack:return
        self.pause();self.timeline.clips=self.undo_stack.pop();self.timeline.selection=None;self.edited()
    def pause(self):self.playing=False;self.timer.stop();self.player.pause()
    def toggle(self):
        if self.playing:self.pause();return
        if not self.timeline.clips:return
        if self.timeline.playhead>=self.timeline.duration:self.seek(0.)
        self.playing=True;self.preview_only=False;self.output.setVolume(self.volume.value()/100);self.anchor=time.monotonic()-self.timeline.playhead;self.timer.start();self.preview(self.timeline.playhead,True)
    def seek(self,value):
        value=max(0.,min(float(value),self.timeline.duration));self.timeline.playhead=value
        self.anchor=time.monotonic()-value;self.preview(value,True);self.timeline.update();self.clock.setText(f'{value:.2f} / {self.timeline.duration:.2f} s')
        video_playback_controls.sync(self)
    def tick(self):
        value=min(self.timeline.duration,time.monotonic()-self.anchor);self.timeline.playhead=value;self.preview(value)
        self.timeline.update();self.clock.setText(f'{value:.2f} / {self.timeline.duration:.2f} s')
        if value>=self.timeline.duration:self.pause()
    def media_ready(self,status):
        if status in (QMediaPlayer.MediaStatus.LoadedMedia,QMediaPlayer.MediaStatus.BufferedMedia) and self.pending_seek is not None:
            value=self.pending_seek;self.pending_seek=None;self.player.setPosition(value)
            if self.playing:self.player.play()
            else:
                # Decode one silent preview frame; StoppedState has no poster frame.
                self.preview_only=True;self.output.setVolume(0.);self.player.play()
    def preview_frame(self,frame):
        if self.preview_only and frame.isValid():
            self.preview_only=False
            if not self.playing:self.player.pause()
            self.output.setVolume(self.volume.value()/100)
    def preview(self,value,force=False):
        clip=next((c for c in self.timeline.clips if c.start<=value<c.end),None)
        if not clip:self.player.pause();self.stack.setCurrentIndex(1);self.current_clip=None;return
        self.stack.setCurrentIndex(0);position=round((clip.source_in+value-clip.start)*1000)
        if self.current_clip is not clip:
            self.current_clip=clip;self.pending_seek=position
            if self.player.source()!=QUrl.fromLocalFile(clip.path):self.player.setSource(QUrl.fromLocalFile(clip.path))
            else:self.pending_seek=None;self.player.setPosition(position)
            if self.playing:self.player.play()
        elif force:self.player.setPosition(position)
        if self.playing and not self.player.isPlaying():self.player.play()
    def export(self):
        if not self.timeline.clips:return
        self.pause()
        try:
            validate_timeline(self.timeline.clips);dialog=VideoExport(self.timeline.clips,self.config,self)
            dialog.exported.connect(lambda path:(self.panel.hub.changed.emit(),self.panel.status.setText('Exported '+path)))
            self.export_dialog=dialog;dialog.exec();dialog.deleteLater();self.export_dialog=None
        except Exception as exc:self.panel.status.setText(str(exc))
    def save_project(self):
        path,_=QFileDialog.getSaveFileName(self,'Save timeline',str(Path(self.panel.path).with_suffix('.orbit-video.json')),'Orbit timeline (*.json)')
        if not path:return
        try:
            with open(path,'x',encoding='utf8') as f:json.dump({'orbit_video':1,'clips':[asdict(c) for c in self.timeline.clips]},f,indent=2)
            self.modified=False;self.panel.status.setText('Timeline saved')
        except Exception as exc:self.panel.status.setText(str(exc))
    def open_project(self):
        path,_=QFileDialog.getOpenFileName(self,'Open timeline',str(Path(self.panel.path).parent),'Orbit timeline (*.json)')
        if not path or not self.can_close():return
        def read():
            if Path(path).stat().st_size>1024*1024:raise ValueError('Timeline file is too large.')
            data=json.loads(Path(path).read_text());rows=data.get('clips',[])
            if data.get('orbit_video')!=1 or not 1<=len(rows)<=100:raise ValueError('Invalid Orbit timeline.')
            clips=[]
            for row in rows:
                source=str(Path(row['path']).expanduser().resolve(strict=True));info=probe(source)
                if not info['video']:raise ValueError('A timeline source has no video.')
                clips.append(Clip(source,float(row['source_in']),float(row['source_out']),float(row['start']),info))
            validate_timeline(clips);return clips
        def ready(clips):
            self.checkpoint();self.timeline.clips=clips;self.timeline.selection=None;self.edited();self.modified=False;self.seek(0.)
        self.panel.hub.run(self.panel,read,ready)
    def can_close(self):
        if getattr(self,'export_dialog',None) and self.export_dialog.job:return False
        if self.modified:
            return QMessageBox.question(self,'Unsaved timeline','Close without saving this timeline? Exported videos are already saved; original media is unchanged.',QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)==QMessageBox.StandardButton.Discard
        return True
    def stop(self):self.pause();self.player.stop()

"""Audio playback and a spectrum derived from the playing file's decoded PCM."""
import math
from pathlib import Path
from appearance import save_config
from PySide6.QtCore import Qt, QUrl, QTimer, Signal, QPropertyAnimation, QRectF,QSize
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QSlider, QWidget, QGraphicsOpacityEffect
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QAudioBufferOutput, QAudioFormat
from design import ui_icon,Panel


class SeekSlider(QSlider):
    seek = Signal(int)
    def mousePressEvent(self,event):
        value=round(self.minimum()+(self.maximum()-self.minimum())*max(0,min(1,event.position().x()/max(1,self.width()))))
        self.setValue(value);self.seek.emit(value)
        super().mousePressEvent(event)


class Spectrum(QWidget):
    def __init__(self,config,parent=None):
        super().__init__(parent);self.config=config;self.levels=[0.]*22;self.setFixedWidth(92)
        self.timer=QTimer(self);self.timer.setInterval(33);self.timer.timeout.connect(self.decay);
    def decay(self):
        if not self.isVisible() or max(self.levels)<.002:self.timer.stop();return
        self.levels=[v*.88 for v in self.levels];self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(self.config["colors"]["primary"]))
        for i,level in enumerate(self.levels):
            h=max(2,level*(self.height()-12));p.drawRoundedRect(QRectF(i*4,self.height()-6-h,2.5,h),1,1)
    def feed(self,buffer):
        if not buffer.isValid():return
        import numpy as np
        fmt=buffer.format()
        mapping={QAudioFormat.SampleFormat.UInt8:(np.uint8,128.),QAudioFormat.SampleFormat.Int16:(np.int16,32768.),
                 QAudioFormat.SampleFormat.Int32:(np.int32,2147483648.),QAudioFormat.SampleFormat.Float:(np.float32,1.)}
        if fmt.sampleFormat() not in mapping:return
        dtype,scale=mapping[fmt.sampleFormat()]
        samples=np.frombuffer(buffer.constData(),dtype=dtype,count=buffer.sampleCount()).astype(np.float32)
        if fmt.sampleFormat()==QAudioFormat.SampleFormat.UInt8:samples-=128
        channels=max(1,fmt.channelCount())
        samples=samples.reshape(-1,channels).mean(axis=1)/scale
        if len(samples)<32:return
        samples=samples[-4096:]
        spectrum=np.abs(np.fft.rfft(samples*np.hanning(len(samples))))/max(1,len(samples)/4)
        frequencies=np.fft.rfftfreq(len(samples),1/max(1,fmt.sampleRate()))
        edges=np.geomspace(35,min(18000,fmt.sampleRate()/2),23)
        for i in range(22):
            values=spectrum[(frequencies>=edges[i])&(frequencies<edges[i+1])]
            strength=float(np.max(values)) if len(values) else 0.
            level=max(0.,min(1.,(20*math.log10(max(1e-6,strength))+65)/65))
            self.levels[i]=max(level,self.levels[i]*.5)
        if not self.timer.isActive():self.timer.start()
        self.update()


class AudioDock(Panel):
    opened = Signal(str)
    closed = Signal()
    error = Signal(str)
    def __init__(self,config,parent=None):
        super().__init__(parent);self.config=config;self.path='';self.setObjectName("audioDock");self.resize(550,112);self.setMinimumSize(320,112)
        layout=QHBoxLayout(self);layout.setContentsMargins(12,8,10,8);layout.setSpacing(10)
        self.toggle=QPushButton();self.toggle.setProperty('role','icon');self.toggle.setFixedSize(32,32);self.toggle.setToolTip('Play / pause');layout.addWidget(self.toggle)
        column=QVBoxLayout();column.setSpacing(2);self.title=QLabel();column.addWidget(self.title)
        self.seek=SeekSlider(Qt.Orientation.Horizontal);self.seek.setRange(0,0);column.addWidget(self.seek)
        self.time=QLabel("0:00 / 0:00");self.time.setObjectName("caption")
        controls=QHBoxLayout();controls.addWidget(self.time,1)
        self.mute=QPushButton();self.mute.setProperty('role','icon');self.mute.setCheckable(True);self.mute.setToolTip('Mute audio');self.mute.setFixedSize(30,30);controls.addWidget(self.mute)
        self.volume=QSlider(Qt.Orientation.Horizontal);self.volume.setRange(0,100);self.volume.setValue(config.get('volume',80));self.volume.setFixedWidth(75);controls.addWidget(self.volume)
        column.addLayout(controls);layout.addLayout(column,1)
        self.spectrum=Spectrum(config);layout.addWidget(self.spectrum)
        self.close_button=QPushButton();self.close_button.setProperty('role','icon');self.close_button.setFixedSize(30,30);self.close_button.setToolTip('Close audio');layout.addWidget(self.close_button);self.close_button.clicked.connect(self.stop)
        self.player=QMediaPlayer(self);self.output=QAudioOutput(self);self.player.setAudioOutput(self.output)
        self.output.setVolume(self.volume.value()/100)
        self.volume.valueChanged.connect(self.set_volume);self.volume.sliderReleased.connect(lambda:save_config(self.config))
        self.mute.toggled.connect(self.output.setMuted)
        self.mute.toggled.connect(lambda _:self.refresh_icons())
        self.set_volume(self.volume.value())
        self.buffers=QAudioBufferOutput(self);self.player.setAudioBufferOutput(self.buffers)
        self.buffers.audioBufferReceived.connect(self.spectrum.feed)
        self.player.positionChanged.connect(self.position);self.player.durationChanged.connect(self.seek.setMaximum)
        self.player.playbackStateChanged.connect(lambda _:self.refresh_icons())
        self.player.errorOccurred.connect(lambda *_:self.error.emit(self.player.errorString()))
        self.toggle.clicked.connect(self.toggle_play);self.seek.seek.connect(self.player.setPosition);self.seek.sliderMoved.connect(self.player.setPosition)
        self.effect=QGraphicsOpacityEffect(self);self.setGraphicsEffect(self.effect)
        self.fade=QPropertyAnimation(self.effect,b"opacity",self);self.fade.setDuration(300)
        self.refresh_icons();self.hide()
    def refresh_icons(self):
        for button,name in ((self.toggle,'pause' if self.player.isPlaying() else 'play'),(self.mute,'muted' if self.mute.isChecked() else 'volume'),(self.close_button,'close')):
            button.setIcon(ui_icon(name,self.config['colors']['text'],19));button.setIconSize(QSize(19,19));button.setAccessibleName(button.toolTip())
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'spectrum'):self.spectrum.setVisible(self.width()>=460)
        if self.path:self.title.setText(self.fontMetrics().elidedText(Path(self.path).name,Qt.TextElideMode.ElideMiddle,max(80,self.width()-250)))
    def set_volume(self,value):
        self.output.setVolume(value/100);self.config['volume']=value;self.volume.setToolTip(f'Volume {value}%')
    def position(self,value):
        if not self.seek.isSliderDown():self.seek.setValue(value)
        def clock(ms):s=ms//1000;return f"{s//60}:{s%60:02}"
        self.time.setText(f"{clock(value)} / {clock(self.player.duration())}")
    def play(self,path):
        self.path=path
        self.title.setText(self.fontMetrics().elidedText(Path(path).name,Qt.TextElideMode.ElideMiddle,236))
        self.player.setSource(QUrl.fromLocalFile(path));self.player.play()
        self.spectrum.timer.start();self.show();self.raise_();self.fade.stop()
        from panel_motion import reveal
        reveal(self,self.config,'files',self.effect);self.opened.emit(path)
    def toggle_play(self):
        self.player.pause() if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState else self.player.play()
    def stop(self):
        self.player.stop();self.spectrum.timer.stop();self.fade.stop()
        from panel_motion import dismiss
        dismiss(self,self.config,'files',lambda:(self.hide(),self.closed.emit()),self.effect)


class AudioConnection(QWidget):
    """Draw the source tether across tile boundaries without intercepting input."""
    def __init__(self,workspace,dock,config):
        super().__init__(workspace);self.workspace=workspace;self.dock=dock;self.config=config;self.source=''
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.timer=QTimer(self);self.timer.setInterval(33);self.timer.timeout.connect(self.update);self.hide()
    def set_source(self,path):
        self.source=path
        if path:self.setGeometry(self.workspace.rect());self.show();self.raise_();self.dock.raise_();self.timer.start()
        else:self.timer.stop();self.hide()
    def paintEvent(self,event):
        if not self.source or not self.dock.isVisible():return
        from PySide6.QtCore import QPointF,QPoint
        from PySide6.QtGui import QPen
        candidates=[t for t in self.workspace.tiles if self.source in t.graph.projected]
        if not candidates:return
        tile=self.workspace.active if self.workspace.active in candidates else candidates[0]
        rect=tile.graph.projected[self.source][0];point=tile.graph.mapTo(self.workspace,rect.center().toPoint())-self.pos()
        end=self.dock.pos()+QPoint(100,0)-self.pos();p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color=QColor(self.config['colors']['primary']);color.setAlpha(165);p.setPen(QPen(color,1.5,Qt.PenStyle.DotLine));p.drawLine(point,end)

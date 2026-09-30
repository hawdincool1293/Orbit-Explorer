"""A bounded-output command bar that runs in the active viewport's folder."""
import os,signal,shutil
from PySide6.QtCore import Qt,QProcess,Signal,QTimer
from PySide6.QtWidgets import QFrame,QVBoxLayout,QHBoxLayout,QLineEdit,QPlainTextEdit,QPushButton,QLabel
from desktop_backend import configure_host_process,host_path

class CommandInput(QLineEdit):
    def __init__(self):super().__init__();self.history=[];self.position=0
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Up,Qt.Key.Key_Down) and self.history:
            self.position=max(0,min(len(self.history),self.position+(-1 if event.key()==Qt.Key.Key_Up else 1)))
            self.setText(self.history[self.position] if self.position<len(self.history) else '');return
        super().keyPressEvent(event)

from design import Panel

class CommandBar(Panel):
    finished=Signal(str)
    def __init__(self,cwd_provider,parent=None):
        super().__init__(parent);self.config=parent.config;self.cwd_provider=cwd_provider;self.cwd='';self.setObjectName('panel')
        layout=QVBoxLayout(self);layout.setContentsMargins(10,7,10,7)
        row=QHBoxLayout();self.location=QLabel();self.location.setTextFormat(Qt.TextFormat.PlainText);row.addWidget(self.location,1)
        self.stop_button=QPushButton('Stop');self.stop_button.clicked.connect(self.stop);self.stop_button.setEnabled(False);row.addWidget(self.stop_button)
        close=QPushButton('×');close.clicked.connect(self.dismiss);row.addWidget(close);layout.addLayout(row)
        self.output=QPlainTextEdit();self.output.setReadOnly(True);self.output.setMaximumBlockCount(1200);self.output.setMinimumHeight(40);layout.addWidget(self.output,1)
        self.entry=CommandInput();self.entry.setPlaceholderText('Shell command in this folder · Enter to run · ↑ history');self.entry.returnPressed.connect(self.run);layout.addWidget(self.entry)
        self.process=QProcess(self);self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output);self.process.finished.connect(self.done)
        self.process.errorOccurred.connect(lambda _:self.output.appendPlainText(self.process.errorString()))
        self.hide()
    def reveal(self):
        from panel_motion import finish
        finish(self,False)
        self.show();self.location.setText(self.cwd_provider());self.entry.setFocus()
        from panel_motion import later
        later(self,self.config,'dialogs')
    def dismiss(self):
        from panel_motion import dismiss
        dismiss(self,self.config,'dialogs',self.hide)
    def run(self):
        command=self.entry.text().strip()
        if not command or self.process.state()!=QProcess.ProcessState.NotRunning:return
        self.cwd=self.cwd_provider();self.location.setText(self.cwd)
        self.entry.history.append(command);self.entry.position=len(self.entry.history);self.entry.clear()
        self.output.appendPlainText(f'{self.cwd}\n$ {command}\n')
        self.process.setWorkingDirectory(self.cwd);shell=os.environ.get('SHELL') or '/bin/bash'
        configure_host_process(self.process)
        if os.environ.get('FLATPAK_ID'):
            self.group=False;self.process.start('flatpak-spawn',['--host','--watch-bus','--directory='+host_path(self.cwd),shell,'-c',command]);self.stop_button.setEnabled(True);return
        self.group=bool(shutil.which('setsid'))
        self.process.start('setsid' if self.group else shell,[shell,'-c',command] if self.group else ['-c',command])
        self.stop_button.setEnabled(True)
    def read_output(self):
        text=bytes(self.process.readAllStandardOutput()).decode(errors='replace')
        # Very large output chunks cannot grow the widget without bound.
        cursor=self.output.textCursor();cursor.movePosition(cursor.MoveOperation.End);cursor.insertText(text[-262144:]);self.output.setTextCursor(cursor)
    def done(self,code,status):
        self.read_output();self.output.appendPlainText(f'Exit {code}');self.stop_button.setEnabled(False);self.finished.emit(self.cwd)
    def stop(self):
        if self.process.state()==QProcess.ProcessState.NotRunning:return
        pid=self.process.processId()
        try:
            if self.group:os.killpg(pid,signal.SIGTERM)
            else:self.process.terminate()
        except ProcessLookupError:pass
        def kill():
            if self.process.state()!=QProcess.ProcessState.NotRunning:
                try:
                    if self.group:os.killpg(pid,signal.SIGKILL)
                    else:self.process.kill()
                except ProcessLookupError:pass
        QTimer.singleShot(1500,self,kill)

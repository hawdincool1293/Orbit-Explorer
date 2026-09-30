"""Cancellable native export process; publish completed output without overwrite."""
import os,tempfile
from pathlib import Path
from PySide6.QtCore import QObject,Signal,QProcess,QTimer

class ExportJob(QObject):
    progress=Signal(float);finished=Signal(str,str)
    def __init__(self,parent=None):super().__init__(parent);self.process=None;self.temp='';self.target='';self.canceled=False;self.log='';self.pending=''
    def start(self,args,target,duration=0):
        target=Path(target).absolute()
        if os.path.lexists(target):raise ValueError('Choose a new filename. Existing files are never replaced.')
        if not target.parent.is_dir():raise ValueError('The destination directory does not exist.')
        fd,self.temp=tempfile.mkstemp(prefix='.orbit-export-',suffix=target.suffix,dir=target.parent);os.close(fd)
        self.target=str(target);self.duration=duration;self.canceled=False;self.log='';self.pending=''
        p=QProcess(self);self.process=p;p.readyReadStandardError.connect(self.read_error);p.readyReadStandardOutput.connect(self.read_progress)
        p.finished.connect(self.complete);p.errorOccurred.connect(lambda e:self.complete(-1,QProcess.ExitStatus.CrashExit) if e==QProcess.ProcessError.FailedToStart else None)
        p.start('ffmpeg',['-hide_banner','-nostdin','-loglevel','error','-y','-filter_complex_threads','2','-progress','pipe:1',*args,'-threads','2',self.temp])
    def read_error(self):self.log=(self.log+bytes(self.process.readAllStandardError()).decode(errors='replace'))[-6000:]
    def read_progress(self):
        self.pending+=bytes(self.process.readAllStandardOutput()).decode(errors='replace')
        lines=self.pending.split('\n');self.pending=lines.pop()
        for line in lines:
            if line.startswith('out_time_us=') and self.duration:
                try:self.progress.emit(min(100,float(line.split('=',1)[1])/1e6/self.duration*100))
                except ValueError:pass
    def complete(self,code,status):
        if not self.temp:return
        self.read_error();error='Canceled' if self.canceled else (self.log.strip() or self.process.errorString()) if code else ''
        if not error:
            try:
                if os.path.getsize(self.temp)==0:raise ValueError('The encoder produced no output.')
                os.link(self.temp,self.target) # Atomic no-clobber publication on the same filesystem.
            except Exception as exc:error=str(exc)
        Path(self.temp).unlink(missing_ok=True);self.temp='';self.finished.emit(self.target if not error else '',error)
    def cancel(self):
        self.canceled=True
        if self.process and self.process.state()!=QProcess.ProcessState.NotRunning:
            self.process.terminate();QTimer.singleShot(1200,self.process,lambda:self.process.kill() if self.process.state()!=QProcess.ProcessState.NotRunning else None)

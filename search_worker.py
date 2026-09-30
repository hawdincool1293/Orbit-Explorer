"""Cancellable search subprocess. Never walks or builds a filesystem index.

Read candidate paths from plocate, apply metadata predicates, and use rg's
literal text engine only on those candidates. Results are JSON lines.
"""
import json,os,signal,subprocess,sys,shutil,stat
from pathlib import Path
from search_query import parse_query
from desktop_backend import IS_MAC,index_command,host_environment,visible_path

children=set()
def stop(*_):
    for child in tuple(children):
        try:child.terminate()
        except OSError:pass
    raise SystemExit(0)

def emit(kind,value):
    print(json.dumps({kind:value}),flush=True)

def content_matches(paths,phrase,strict=False):
    if not paths:return []
    # rg skips binary files and does not follow directories; every argument is
    # an existing regular file from the index, never a traversal root.
    proc=subprocess.Popen(['rg','--files-with-matches','--null',*([] if strict else ['--ignore-case']),'--fixed-strings',
                           '--no-messages','--color','never','-e',phrase,'--',*paths],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    children.add(proc)
    try:
        out,err=proc.communicate(timeout=30)
        if proc.returncode not in (0,1,2):emit('status',err.decode(errors='replace'))
        return [os.fsdecode(p) for p in out.split(b'\0') if p]
    except subprocess.TimeoutExpired:
        proc.kill();proc.communicate();emit('status','One content-search batch timed out; continuing.');return []
    finally:children.discard(proc)

def run(payload):
    query=parse_query(payload['query'],strict=payload.get('strict',False))
    if query.error:emit('status',query.error);return
    if query.contains and not shutil.which('rg'):
        emit('status','Install ripgrep to use contains: text search.');return
    seen=set();batch=[];examined=0;matches=0
    directories_only=payload.get('directories_only',False)
    def consume(paths):
        nonlocal batch,examined,matches
        for path in paths:
            if path in seen:continue
            seen.add(path)
            try:
                st=os.stat(path);directory=stat.S_ISDIR(st.st_mode)
                if directories_only and not directory:continue
                if query.contains and not stat.S_ISREG(st.st_mode):continue
                if not query.matches(path,st.st_mtime_ns,directory):continue
            except OSError:continue
            examined+=1;batch.append(path)
            if len(batch)>=96:flush()
    def flush():
        nonlocal batch,matches
        if not batch:return
        found=content_matches(batch,query.contains,query.strict) if query.contains else batch
        matches+=len(found)
        if found:emit('paths',found)
        batch=[]
    consume(payload.get('local_paths',[]));flush()
    if not IS_MAC and not os.environ.get('FLATPAK_ID') and not shutil.which('plocate'):
        emit('status','Visible files searched. Install plocate and run updatedb for computer-wide results.');return
    proc=subprocess.Popen(index_command(query),stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=host_environment())
    children.add(proc);pending=b''
    try:
        while True:
            chunk=proc.stdout.read1(32768)
            if not chunk:break
            parts=(pending+chunk).split(b'\0');pending=parts.pop()
            consume(visible_path(os.fsdecode(p)) for p in parts if p)
        flush();code=proc.wait();message=proc.stderr.read().decode(errors='replace').strip()
        emit('status',message if code not in (0,1) else f'{matches:,} indexed/visible matches · modified dates use local time')
    finally:
        if proc.poll() is None:proc.terminate();proc.wait()
        children.discard(proc)

if __name__=='__main__':
    signal.signal(signal.SIGTERM,stop)
    try:run(json.loads(sys.argv[1]))
    except Exception as exc:emit('status',str(exc))

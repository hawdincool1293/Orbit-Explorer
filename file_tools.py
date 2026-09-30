"""Bounded document reads, conflict-aware saves and safe standard-library extraction."""
import hashlib,os,stat,tempfile,zipfile,tarfile,shutil
from pathlib import Path,PurePosixPath

TEXT_LIMIT=8*1024*1024
ARCHIVE_LIMIT=4*1024*1024*1024

def read_text(path):
    target=Path(path).resolve(strict=True)
    with target.open('rb') as stream:data=stream.read(TEXT_LIMIT+1)
    if len(data)>TEXT_LIMIT:raise ValueError('This editor supports text files up to 8 MiB. Use Open externally for larger files.')
    encoding='utf-16' if data.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig' if data.startswith(b'\xef\xbb\xbf') else 'utf-8'
    if encoding=='utf-8' and b'\0' in data:raise ValueError('This file contains binary data and cannot be edited as text.')
    text=data.decode(encoding)
    return {'text':text,'encoding':encoding,'newline':'\r\n' if '\r\n' in text else '\n','digest':hashlib.sha256(data).hexdigest(),'target':str(target)}

def save_text(path,text,original):
    target=Path(path).resolve(strict=True)
    if str(target)!=original['target']:raise ValueError('The file target changed. Reopen it before saving.')
    with target.open('rb') as stream:current=stream.read(TEXT_LIMIT+1)
    if hashlib.sha256(current).hexdigest()!=original['digest']:raise ValueError('This file changed outside Orbit. Your edits are kept; use Save as to preserve them.')
    data=text.replace('\r\n','\n').replace('\n',original['newline']).encode(original['encoding'])
    if len(data)>TEXT_LIMIT:raise ValueError('The edited file exceeds the 8 MiB editor limit. Save a copy or shorten it before saving.')
    mode=stat.S_IMODE(target.stat().st_mode)
    fd,name=tempfile.mkstemp(prefix='.orbit-save-',dir=target.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno());os.fchmod(stream.fileno(),mode)
        # Recheck just before commit, including a symlink retarget.
        with target.open('rb') as stream:latest=stream.read(TEXT_LIMIT+1)
        if Path(path).resolve()!=target or hashlib.sha256(latest).hexdigest()!=original['digest']:
            raise ValueError('The file changed while saving. Use Save as to keep your edits.')
        os.replace(name,target)
    finally:
        if os.path.exists(name):os.unlink(name)
    return dict(original,digest=hashlib.sha256(data).hexdigest(),text=text)

def safe_member(name):
    normalized=name.replace('\\','/')
    path=PurePosixPath(normalized)
    if not name or '\0' in name or path.is_absolute() or '..' in path.parts or any(':' in p for p in path.parts):
        raise ValueError(f'Unsafe archive path: {name}')
    if not path.parts:raise ValueError('Empty archive path.')
    return path

def archive_contents(path):
    rows=[]
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for item in archive.infolist():
                if len(rows)>=10000:raise ValueError('Archive has more than 10,000 entries. Open it externally.')
                safe_member(item.filename)
                mode=item.external_attr>>16
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR)):raise ValueError('Archive links and special files are not extracted.')
                if item.flag_bits&1:raise ValueError('Encrypted archives must be opened externally.')
                rows.append((item.filename,item.file_size,item.is_dir()))
    elif tarfile.is_tarfile(path):
        with tarfile.open(path) as archive:
            for item in archive:
                if item.isdir() and item.name in ('.','./'):continue
                if len(rows)>=10000:raise ValueError('Archive has more than 10,000 entries. Open it externally.')
                safe_member(item.name)
                if not (item.isfile() or item.isdir()):raise ValueError('Archive links and special files are not extracted.')
                rows.append((item.name,item.size,item.isdir()))
    else:raise ValueError('Built-in extraction supports ZIP and TAR (including .tar.gz, .tar.bz2 and .tar.xz).')
    if sum(r[1] for r in rows)>ARCHIVE_LIMIT:raise ValueError('Archive expands beyond 4 GiB. Open it externally.')
    return rows

def extract_archive(path,parent,canceled=lambda:False):
    rows=archive_contents(path);parent=Path(parent).resolve(strict=True)
    if not parent.is_dir():raise ValueError('Choose an existing destination folder.')
    stem=Path(path).name
    for suffix in ('.tar.gz','.tar.bz2','.tar.xz','.tgz','.tbz2','.txz','.zip','.tar'):
        if stem.lower().endswith(suffix):stem=stem[:-len(suffix)];break
    stem=(stem or 'Archive')+' extracted'
    root=None
    for number in range(10000):
        candidate=parent/(stem+(f' ({number})' if number else ''))
        try:candidate.mkdir(mode=0o700);root=candidate;break
        except FileExistsError:continue
    if root is None:raise ValueError('Cannot create a fresh extraction directory.')
    written=0
    try:
        is_zip=zipfile.is_zipfile(path)
        with (zipfile.ZipFile(path) if is_zip else tarfile.open(path)) as archive:
            for name,size,directory in rows:
                if canceled():raise InterruptedError('Extraction canceled.')
                output=root.joinpath(*safe_member(name).parts)
                if directory:output.mkdir(parents=True,exist_ok=True);continue
                output.parent.mkdir(parents=True,exist_ok=True)
                source=archive.open(name) if is_zip else archive.extractfile(name)
                with source,output.open('xb') as target:
                    while True:
                        if canceled():raise InterruptedError('Extraction canceled.')
                        chunk=source.read(1024*1024)
                        if not chunk:break
                        written+=len(chunk)
                        if written>ARCHIVE_LIMIT:raise ValueError('Archive exceeded the extraction size limit.')
                        target.write(chunk)
        return str(root)
    except BaseException:
        # Only this freshly created extraction tree is removed on failure.
        shutil.rmtree(root);raise

def extract_here(path,parent):
    """Stage and validate first, then place top-level entries without overwrites."""
    parent=Path(parent).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='.orbit-extract-',dir=parent) as temporary:
        staged=Path(extract_archive(path,temporary));items=list(staged.iterdir())
        for source in items:
            if os.path.lexists(parent/source.name):raise FileExistsError(f'{source.name} already exists. Extract to a new folder instead.')
        created=[]
        try:
            for source in items:
                output=parent/source.name
                if source.is_dir():
                    output.mkdir(mode=0o700);created.append(output)
                    shutil.copytree(source,output,dirs_exist_ok=True)
                else:os.link(source,output);created.append(output)
        except Exception:
            for output in reversed(created):
                if output.is_dir():shutil.rmtree(output)
                else:output.unlink(missing_ok=True)
            raise
    return str(parent)

def compress_zip(paths,target):
    target=Path(target).absolute()
    if os.path.lexists(target):raise FileExistsError('Choose a new ZIP filename; existing files are not replaced.')
    sources=[];names=set()
    for raw in sorted(set(paths),key=lambda p:len(Path(p).parts)):
        path=Path(raw).absolute()
        if any(path.is_relative_to(parent) for parent in sources):continue
        if path.is_symlink():raise ValueError('ZIP compression does not follow symbolic links.')
        if path.name in names:raise ValueError('Selected items have duplicate names; compress them separately.')
        if path.is_dir() and target.is_relative_to(path):raise ValueError('Save the ZIP outside the folders being compressed.')
        sources.append(path);names.add(path.name)
    if not sources:raise ValueError('Select at least one file or folder.')
    fd,temporary=tempfile.mkstemp(prefix='.orbit-zip-',suffix='.zip',dir=target.parent);os.close(fd)
    try:
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as archive:
            for source in sources:
                if source.is_file():archive.write(source,source.name);continue
                if not source.is_dir():raise ValueError('Only regular files and folders can be compressed.')
                archive.write(source,source.name+'/')
                for root,dirs,files in os.walk(source,followlinks=False):
                    for name in dirs+files:
                        entry=Path(root)/name
                        if entry.is_symlink():raise ValueError('ZIP compression does not follow symbolic links: '+str(entry))
                        mode=entry.stat().st_mode
                        if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):raise ValueError('Special files cannot be compressed.')
                        archive.write(entry,str(Path(source.name)/entry.relative_to(source)))
        os.link(temporary,target)
    finally:Path(temporary).unlink(missing_ok=True)
    return str(target)

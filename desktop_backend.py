"""Linux/Flatpak/macOS service adapters; never create a private search index."""
import os,sys,subprocess,plistlib,shutil
from pathlib import Path

IS_MAC=sys.platform=='darwin'

def host_command(args):
    return ['flatpak-spawn','--host',*args] if os.environ.get('FLATPAK_ID') else list(args)

def host_environment():
    env=dict(os.environ)
    if env.pop('_ORBIT_BUNDLED_FONTCONFIG',None):
        env.pop('FONTCONFIG_FILE',None);env.pop('FONTCONFIG_PATH',None)
    if getattr(sys,'frozen',False):
        if 'LD_LIBRARY_PATH_ORIG' in env:env['LD_LIBRARY_PATH']=env['LD_LIBRARY_PATH_ORIG']
        else:env.pop('LD_LIBRARY_PATH',None)
    return env

def run_host(args,**kwargs):return subprocess.run(host_command(args),env=host_environment(),**kwargs)

def visible_path(path):
    if os.environ.get('FLATPAK_ID'):
        for prefix in ('/usr','/etc'):
            if path==prefix or path.startswith(prefix+'/'):return '/run/host'+path
    return path

def host_path(path):
    if os.environ.get('FLATPAK_ID') and (path.startswith('/run/host/usr') or path.startswith('/run/host/etc')):return path[len('/run/host'):]
    return path

def configure_host_process(process):
    from PySide6.QtCore import QProcessEnvironment
    env=QProcessEnvironment()
    for key,value in host_environment().items():env.insert(key,value)
    process.setProcessEnvironment(env)

def index_command(query):
    if IS_MAC:
        value=query.name.replace('\\','\\\\').replace('"','\\"')
        return ['/usr/bin/mdfind','-0',f'kMDItemFSName == "*{value}*"cd']
    return host_command(['plocate','-0','-i','-b','--',*query.patterns()])

def mac_drives():
    result=run_host(['/usr/sbin/diskutil','list','-plist','physical'],capture_output=True,check=True)
    data=plistlib.loads(result.stdout)
    containers={}
    apfs=run_host(['/usr/sbin/diskutil','apfs','list','-plist'],capture_output=True)
    if apfs.returncode==0:
        for container in plistlib.loads(apfs.stdout).get('Containers',[]):
            for physical in container.get('PhysicalStores',[]):containers[physical.get('DeviceIdentifier')]=container.get('Volumes',[])
    def convert(item,root=False):
        identifier=item.get('DeviceIdentifier','');info={}
        if identifier:
            detail=run_host(['/usr/sbin/diskutil','info','-plist',identifier],capture_output=True)
            if detail.returncode==0:info=plistlib.loads(detail.stdout)
        size=item.get('Size',info.get('TotalSize',0))
        return {'name':item.get('VolumeName') or info.get('VolumeName') or identifier,'path':'/dev/'+identifier,
                'label':item.get('VolumeName',''),'model':info.get('MediaName') or info.get('DeviceModel') or identifier,
                'size':f'{size/1024**3:.1f} GiB','mount':info.get('MountPoint',item.get('MountPoint','')),
                'type':'disk' if root else 'part','fs':info.get('FilesystemType') or item.get('Content',''),
                'serial':info.get('SerialNumber',''),'wwn':'','uuid':info.get('VolumeUUID') or info.get('DiskUUID',''),
                'children':[convert(child) for child in item.get('Partitions',[])]+[convert(child) for child in item.get('APFSVolumes',[])]+[convert(child) for child in containers.get(identifier,[])]}
    return [convert(item,True) for item in data.get('AllDisksAndPartitions',[])]

def trash_command(paths):
    if IS_MAC:
        script='on run argv\ntell application "Finder"\nrepeat with p in argv\ndelete (POSIX file p as alias)\nend repeat\nend tell\nend run'
        return ['/usr/bin/osascript','-e',script,*paths]
    return ['gio','trash','--',*paths]

def runtime_setup():
    # Native Wayland avoids compositor upscaling of an XWayland window. Keep
    # explicit user overrides, and allow X11 fallback when Wayland is unavailable.
    if sys.platform.startswith('linux') and os.environ.get('WAYLAND_DISPLAY'):
        os.environ.setdefault('QT_QPA_PLATFORM','wayland;xcb')
    # Bundled helpers are preferred; Homebrew remains discoverable for source runs.
    helpers=[]
    if getattr(sys,'frozen',False):helpers.append(str(Path(sys._MEIPASS)/'bin'))
    if IS_MAC:helpers+=['/opt/homebrew/bin','/usr/local/bin']
    if helpers:os.environ['PATH']=os.pathsep.join(helpers+[os.environ.get('PATH','')])

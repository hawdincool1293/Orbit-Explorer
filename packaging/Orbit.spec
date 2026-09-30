# Build on the target OS and architecture. PyInstaller is not a cross-compiler.
from pathlib import Path
import shutil,sys,importlib.metadata
root=Path(SPECPATH).parent
helpers=[]
for name in ('ffmpeg','ffprobe','rg'):
    path=shutil.which(name)
    if not path:raise RuntimeError('Install build dependency: '+name)
    helpers.append((path,'bin'))
data=[(str(root/'assets'),'assets'),(str(root/'THIRD_PARTY.md'),'licenses')]
for package in ('PySide6','PySide6_Addons','PySide6_Essentials','shiboken6','numpy','pyinstaller'):
    try:dist=importlib.metadata.distribution(package)
    except importlib.metadata.PackageNotFoundError:continue
    for item in dist.files or []:
        if any(part.lower().startswith(('license','copying','copyright')) for part in item.parts):
            path=Path(dist.locate_file(item))
            if path.is_file():data.append((str(path),'licenses/'+package+'/'+str(Path(item).parent)))
for name in ('ffmpeg','ripgrep'):
    path=Path('/usr/share/doc')/name/'copyright'
    if path.is_file():data.append((str(path),'licenses/'+name))
for name in ('GPL-2','GPL-3','LGPL-2.1','LGPL-3'):
    path=Path('/usr/share/common-licenses')/name
    if path.is_file():data.append((str(path),'licenses'))
a=Analysis([str(root/'app.py')],pathex=[str(root)],binaries=helpers,
    datas=data,
    hiddenimports=['PySide6.QtPdf','PySide6.QtPdfWidgets','PySide6.QtMultimedia',
                   'PySide6.QtMultimediaWidgets','PySide6.QtSvg','numpy'],
    hookspath=[],runtime_hooks=[str(root/'packaging/runtime_fontconfig.py')],excludes=['tkinter','matplotlib','pandas','IPython'])
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='Orbit',debug=False,bootloader_ignore_signals=False,
        strip=False,upx=False,console=sys.platform!='darwin',argv_emulation=False)
collection=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='Orbit')
if sys.platform=='darwin':
    app=BUNDLE(collection,name='Orbit.app',bundle_identifier='io.github.orbitexplorer.Orbit',
        info_plist={'CFBundleShortVersionString':'0.6.6','CFBundleVersion':'0.6.6',
        'NSHighResolutionCapable':True,'LSMinimumSystemVersion':'13.0',
        'NSAppleEventsUsageDescription':'Orbit uses Finder to move selected files to Trash.',
        'NSMicrophoneUsageDescription':'Optional media device access.'})

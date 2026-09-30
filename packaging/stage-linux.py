"""Prepare AppDir and Flatpak trees from the same frozen Linux application."""
import os,shutil,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
frozen=Path(sys.argv[1]).resolve();output=Path(sys.argv[2]).resolve();output.mkdir(parents=True,exist_ok=True)
appdir=output/'Orbit.AppDir';flatpak=output/'flatpak'
for destination in (appdir/'usr/lib/orbit',flatpak/'files/lib/orbit'):
    if destination.exists():raise RuntimeError(f'Use a new staging directory: {destination}')
    shutil.copytree(frozen,destination,symlinks=True)
identifier='io.github.orbitexplorer.Orbit'
shutil.copy2(root/'packaging/AppRun',appdir/'AppRun');(appdir/'AppRun').chmod(0o755)
shutil.copy2(root/'packaging'/f'{identifier}.desktop',appdir/f'{identifier}.desktop')
shutil.copy2(root/'assets/orbit.svg',appdir/f'{identifier}.svg')
shutil.copy2(root/'packaging/flatpak-metadata',flatpak/'metadata')
binpath=flatpak/'files/bin';binpath.mkdir(parents=True);(binpath/'Orbit').symlink_to('../lib/orbit/Orbit')
for relative,source in ((f'applications/{identifier}.desktop',root/'packaging'/f'{identifier}.desktop'),
                       (f'icons/hicolor/scalable/apps/{identifier}.svg',root/'assets/orbit.svg'),
                       (f'metainfo/{identifier}.metainfo.xml',root/'packaging'/f'{identifier}.metainfo.xml')):
    dest=flatpak/'files/share'/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
print(appdir);print(flatpak)

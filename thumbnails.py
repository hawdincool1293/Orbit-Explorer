"""Async image/video previews, installed MIME icons, and distinct fallback artwork."""
from collections import OrderedDict
from functools import lru_cache
import hashlib
import math
import os
import shutil
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import QObject, Signal, QSize, Qt, QMimeDatabase, QRectF, QTimer
from PySide6.QtGui import QImage, QImageReader, QPixmap, QIcon, QPainter, QColor, QPen, QPainterPath
from core import file_category
from appearance import system_icons

BUNDLED_ICONS=Path(__file__).parent/'assets/icons/sweet'


class Thumbnails(QObject):
    ready = Signal(str, object)
    changed = Signal()
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.cache, self.pending, self.icons, self.gray = {}, set(), {}, {}
        self.sprites=OrderedDict();self.stamps=OrderedDict();self.resolved={};self.closed=False
        self.sprite_bytes=self.stamp_bytes=0
        self.notify=QTimer(self);self.notify.setSingleShot(True);self.notify.setInterval(33);self.notify.timeout.connect(self.changed)
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="orbit-preview")
        self.mime = QMimeDatabase()
        self.ready.connect(self.accept)
        self.set_theme()

    def set_theme(self):
        theme = self.config["icon_theme"]
        QIcon.setThemeName(system_icons() if theme in ("System","Sweet (bundled)") else theme)
        self.icons.clear();self.gray.clear();self.sprites.clear();self.stamps.clear();self.resolved.clear()
        self.sprite_bytes=self.stamp_bytes=0
        self.changed.emit()

    def grayscale(self,pixmap):
        key=pixmap.cacheKey()
        if key not in self.gray:
            self.gray[key]=QPixmap.fromImage(pixmap.toImage().convertToFormat(QImage.Format.Format_Grayscale8))
            if len(self.gray)>1000:self.gray.clear()
        return self.gray.get(key,pixmap)

    def accept(self, key, image):
        self.pending.discard(key)
        self.cache[key] = QPixmap.fromImage(image) if not image.isNull() else QPixmap()
        if len(self.cache) > 512:
            for k in list(self.cache)[:128]: del self.cache[k]
        self.resolved.clear()
        if not self.notify.isActive():self.notify.start()

    def pixmap(self, node):
        folder_thumb=next((f.get('thumbnail','') for f in self.config['favorites'] if f['path']==node.path),'') if node.directory else ''
        identity=(node.path,node.directory,node.kind,node.modified_ns,node.size,self.config['thumbnails'],folder_thumb)
        if identity in self.resolved:return self.resolved[identity]
        category = node.kind if node.kind in ("drive","partition") else category_for(node.path,node.directory)
        result=None;preview_category=category;custom = self.config["type_icons"].get(category, "")
        if folder_thumb:
            key=f'folder:{node.path}:{folder_thumb}'
            if key in self.cache and not self.cache[key].isNull():result=self.cache[key];preview_category='image'
            if not self.closed and key not in self.cache and key not in self.pending:
                self.pending.add(key);self.pool.submit(self.load,folder_thumb,'image',key)
        if custom and result is None:
            key='custom:'+custom
            if key not in self.icons:
                icon=QIcon(custom) if os.path.isfile(custom) else QIcon.fromTheme(custom)
                self.icons[key]=icon.pixmap(512,512)
            if not self.icons[key].isNull():result=self.icons[key]
        if result is None and self.config["thumbnails"] and category in ("image","video"):
            key = f"{node.path}:{node.modified_ns}:{node.size}"
            if key in self.cache and not self.cache[key].isNull():result=self.cache[key]
            if not self.closed and key not in self.cache and key not in self.pending:
                self.pending.add(key);self.pool.submit(self.load,node.path,category,key)
        if result is None and self.config['icon_theme']=='Sweet (bundled)':
            name='pdf' if Path(node.path).suffix.lower()=='.pdf' and not node.directory else category
            key='sweet:'+name
            if key not in self.icons:
                path=BUNDLED_ICONS/(name+'.svg')
                if not path.is_file():path=BUNDLED_ICONS/'file.svg'
                self.icons[key]=QIcon(str(path)).pixmap(512,512)
            if not self.icons[key].isNull():result=self.icons[key]
        if result is None and self.config["icon_theme"] != "Orbit":
            key = category if node.directory or node.kind else self.mime.mimeTypeForFile(node.path,QMimeDatabase.MatchMode.MatchExtension).iconName()
            if key not in self.icons:
                fallback={"folder":"folder","drive":"drive-harddisk","partition":"drive-harddisk","document":"text-x-generic",
                          "audio":"audio-x-generic","video":"video-x-generic","image":"image-x-generic","archive":"package-x-generic"}
                icon=QIcon.fromTheme(key)
                if icon.isNull():icon=QIcon.fromTheme(fallback.get(category,"application-x-generic"))
                self.icons[key]=icon.pixmap(512,512)
            if not self.icons[key].isNull():result=self.icons[key]
        if result is None:
            key='fallback:'+category
            if key not in self.icons:self.icons[key]=self.fallback(category)
            result=self.icons[key]
        if len(self.resolved)>4000:self.resolved.clear()
        self.resolved[identity]=(result,preview_category)
        return result,preview_category

    def cache_raster(self,cache,key,pixmap,counter):
        cache[key]=pixmap
        used=getattr(self,counter)+pixmap.width()*pixmap.height()*4
        # High-DPI stamps need more pixels; bound memory as well as item count.
        while len(cache)>1 and (len(cache)>2048 or used>32*1024*1024):
            _,old=cache.popitem(last=False);used-=old.width()*old.height()*4
        setattr(self,counter,used)

    def sprite(self,node,diameter,gray=False,dpr=1.):
        pix,category=self.pixmap(node)
        size=max(8,min(256,round(diameter/4)*4))
        key=(pix.cacheKey(),size,gray,category,dpr)
        if key in self.sprites:
            self.sprites.move_to_end(key);return self.sprites[key]
        source=self.grayscale(pix) if gray else pix
        result=QPixmap(math.ceil(size*dpr),math.ceil(size*dpr));result.setDevicePixelRatio(dpr);result.fill(Qt.GlobalColor.transparent)
        p=QPainter(result);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        clip=QPainterPath();clip.addEllipse(QRectF(1,1,size-2,size-2));p.setClipPath(clip)
        inset=1 if category in ('image','video') else size*.18
        target=QRectF(inset,inset,size-2*inset,size-2*inset)
        physical=QSize(math.ceil(target.width()*dpr),math.ceil(target.height()*dpr))
        scaled=source.scaled(physical,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(target,scaled,QRectF((scaled.width()-physical.width())/2,(scaled.height()-physical.height())/2,physical.width(),physical.height()));p.end()
        self.cache_raster(self.sprites,key,result,'sprite_bytes')
        return result

    def shutdown(self):
        self.closed=True;self.notify.stop();self.pool.shutdown(wait=False,cancel_futures=True)

    def stamp(self,node,diameter,matched=True,selected=False,highlight=False,ghost=False,dpr=1.):
        """Pre-render the whole normal node, including border and highlight.

        Rasterizing hundreds of antialiased ellipses was the dominant cost.
        Quantized cached stamps make orbit frames mostly pixmap blits.
        """
        size=max(8,min(256,round(diameter/4)*4));c=self.config['colors']
        sprite=self.sprite(node,max(8,size-5),not matched,dpr=dpr)
        border=c['accent' if selected else ('folder' if node.directory else 'file')] if matched else '#616976'
        key=(sprite.cacheKey(),size,border,c['panel'],c['primary'],matched,selected,highlight,ghost,dpr)
        if key in self.stamps:self.stamps.move_to_end(key);return self.stamps[key]
        result=QPixmap(math.ceil((size+14)*dpr),math.ceil((size+14)*dpr));result.setDevicePixelRatio(dpr);result.fill(Qt.GlobalColor.transparent)
        p=QPainter(result);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setOpacity(.2 if ghost else (1 if matched else .17))
        rect=QRectF(7,7,size,size);p.setPen(QPen(QColor(border),2 if selected or highlight else 1));p.setBrush(QColor(c['panel']));p.drawEllipse(rect)
        if selected or highlight:
            color=QColor(c['primary']);color.setAlpha(150);p.setPen(QPen(color,2));p.setBrush(Qt.BrushStyle.NoBrush);p.drawEllipse(rect.adjusted(-5,-5,5,5))
        p.drawPixmap(rect.adjusted(2,2,-2,-2),sprite,QRectF(sprite.rect()))
        p.end();self.cache_raster(self.stamps,key,result,'stamp_bytes')
        return result

    def load(self, path, category, key):
        image = QImage()
        try:
            if category == "image":
                reader = QImageReader(path); reader.setAutoTransform(True)
                size = reader.size()
                if size.isValid(): reader.setScaledSize(size.scaled(QSize(512,512),Qt.AspectRatioMode.KeepAspectRatio))
                image = reader.read()
            else:
                cache_dir = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home()/".cache")))
                uri = Path(path).as_uri()
                digest = hashlib.md5(uri.encode()).hexdigest()
                for folder in ("xx-large","x-large","large","normal"):
                    cached = QImage(str(cache_dir/f"thumbnails/{folder}/{digest}.png"))
                    if not cached.isNull() and cached.text("Thumb::MTime") == str(int(os.stat(path).st_mtime)):
                        image = cached; break
                if image.isNull() and shutil.which("ffmpeg"):
                    result = subprocess.run(["ffmpeg","-v","error","-i",path,"-frames:v","1",
                                             "-vf","scale=512:512:force_original_aspect_ratio=decrease",
                                             "-f","image2pipe","-c:v","png","-"],capture_output=True,timeout=12)
                    image = QImage.fromData(result.stdout)
        except (OSError, subprocess.SubprocessError): pass
        self.ready.emit(key,image)

    @staticmethod
    def fallback(category):
        colors = {"folder":"#66cfbc","document":"#ad94ef","image":"#ed94b7","video":"#eeaa7b",
                  "audio":"#78bfd9","archive":"#c4b177","drive":"#76b9b6","partition":"#86a5d8","file":"#a0b0c1"}
        pix = QPixmap(128,128); pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(colors.get(category,"#a0b0c1"))
        p.setPen(QPen(c.lighter(135),3)); p.setBrush(c.darker(170))
        if category == "folder":
            path=QPainterPath(); path.moveTo(18,39);path.lineTo(18,26);path.lineTo(54,26);path.lineTo(65,39);path.lineTo(110,39);path.lineTo(110,98);path.lineTo(18,98);path.closeSubpath();p.drawPath(path)
        else: p.drawRoundedRect(QRectF(28,16,72,96),10,10)
        p.setPen(QPen(c.lighter(150),5))
        if category == "document":
            for y in (44,59,74,89): p.drawLine(43,y,84 if y!=89 else 69,y)
        elif category == "audio":
            for x,h in ((44,18),(55,32),(66,46),(77,26),(88,14)):p.drawLine(x,64-h//2,x,64+h//2)
        elif category == "video":
            path=QPainterPath();path.moveTo(52,43);path.lineTo(83,64);path.lineTo(52,85);path.closeSubpath();p.fillPath(path,c.lighter(160))
        elif category == "archive":
            for y in range(27,103,10):p.drawLine(61,y,69,y)
        elif category == "image":
            p.drawEllipse(75,36,10,10);p.drawLine(39,89,58,60);p.drawLine(58,60,89,89)
        elif category in ("drive","partition"):
            p.drawRoundedRect(QRectF(39,40,50,30),5,5);p.drawPoint(80,87)
        p.end();return pix


category_for=lru_cache(maxsize=8192)(file_category)

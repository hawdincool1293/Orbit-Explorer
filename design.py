"""Shared, softly rounded surfaces and small vector interface icons."""
from functools import lru_cache
from PySide6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap, QPalette
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QDialog, QFrame, QComboBox, QFontComboBox, QSpinBox, QListView, QMenu

ICONS={
 'play':'<path d="m8 4 12 8-12 8Z"/>',
 'pause':'<path d="M8 4v16M16 4v16"/>',
 'volume':'<path d="M3 9h4l5-5v16l-5-5H3Zm13-2a7 7 0 0 1 0 10m3-13a11 11 0 0 1 0 16"/>',
 'muted':'<path d="M3 9h4l5-5v16l-5-5H3Zm13 0 5 6m0-6-5 6"/>',
 'orbit':'<ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(-30 12 12)"/><circle cx="12" cy="12" r="5"/><circle cx="20" cy="7" r="1.2" fill="currentColor"/>',
 'back':'<path d="m14 6-6 6 6 6M8 12h12"/>',
 'forward':'<path d="m10 6 6 6-6 6M4 12h12"/>',
 'home':'<path d="m3 11 9-8 9 8M5 10v10h5v-6h4v6h5V10"/>',
 'split':'<rect x="3" y="4" width="18" height="16" rx="4"/><path d="M12 4v16"/>',
 'duplicate':'<rect x="8" y="8" width="12" height="12" rx="3"/><path d="M15 4H6a2 2 0 0 0-2 2v9"/>',
 'terminal':'<rect x="3" y="4" width="18" height="16" rx="4"/><path d="m7 9 3 3-3 3m6 0h4"/>',
 'audio':'<path d="M5 5v14M12 3v18M19 6v12"/><circle cx="5" cy="10" r="2"/><circle cx="12" cy="15" r="2"/><circle cx="19" cy="9" r="2"/>',
 'settings':'<path d="m9 3-.7 2.2-2 .9-2.1-.5-1.5 2.6 1.5 1.7V12l-1.5 1.7 1.5 2.6 2.1-.5 2 .9L9 19h3l.7-2.3 2-.9 2.1.5 1.5-2.6-1.5-1.7V9.9l1.5-1.7-1.5-2.6-2.1.5-2-.9L12 3Z" transform="translate(1.5 1)"/><circle cx="12" cy="12" r="3"/>',
 'pin':'<path d="m15 3 6 6-3 1-3 5-2 1-5-5 1-2 5-3ZM8 16l-5 5"/>',
 'refresh':'<path d="M20 8a8 8 0 1 0 0 8M20 3v5h-5"/>',
 'folder':'<path d="M3 7a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
 'file':'<path d="M13 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10ZM13 3v7h7M8 14h8m-8 3h5"/>',
 'drive':'<rect x="3" y="4" width="18" height="16" rx="4"/><path d="M3 14h18m-5 3h1m-10 0h3"/>',
 'clock':'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
 'close':'<path d="m6 6 12 12M6 18 18 6"/>',
 'minus':'<path d="M5 12h14"/>',
 'maximize':'<rect x="5" y="5" width="14" height="14" rx="3"/>',
 'search':'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
 'link':'<path d="m10 14 4-4m-6 6-2 2a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m4 0 2-2a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0" transform="translate(1 1) scale(.9)"/>',
 'copy':'<rect x="8" y="8" width="12" height="12" rx="3"/><path d="M15 4H6a2 2 0 0 0-2 2v9"/>',
 'move':'<path d="M4 7v11a2 2 0 0 0 2 2h11M10 4h10v10M8 16 20 4"/>',
 'fit':'<path d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6"/>',
 'chevron':'<path d="m7 10 5 5 5-5"/>',
}


@lru_cache(maxsize=192)
def ui_icon(name, color, size=20):
    shape=ICONS.get(name,ICONS['folder']).replace('currentColor',color)
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">{shape}</svg>'
    pixmap=QPixmap(size*2,size*2); pixmap.setDevicePixelRatio(2); pixmap.fill(Qt.GlobalColor.transparent)
    painter=QPainter(pixmap); QSvgRenderer(QByteArray(svg.encode())).render(painter,QRectF(0,0,size,size)); painter.end()
    return QIcon(pixmap)


def stylesheet(config):
    c=config['colors']
    def rgba(key, alpha=255):
        color=QColor(c[key]);return f'rgba({color.red()},{color.green()},{color.blue()},{round(alpha)})'
    return f'''
        QSplitter {{background:transparent;}}
        QSplitter::handle {{background:transparent;border-radius:3px;}}
        QSplitter::handle:hover,QSplitter::handle:pressed {{background:{rgba('primary',105)};}}
        QMainWindow, QWidget#shell, QFrame#header, QFrame#footer {{background:transparent; border:0;}}
        QFrame#panel,QFrame#navigation,QFrame#spotlight,QFrame#audioDock {{background:transparent; border:1px solid {rgba('secondary',28)}; border-radius:24px;}}
        QFrame#viewportHeader {{background:transparent; border:0;}}
        QFrame#viewTile {{background:transparent;border:1px solid {rgba('secondary',48)};border-radius:24px;}}
        QFrame#viewTile[activeTile="true"] {{border-color:{rgba('primary',90)};}}
        QLabel,QCheckBox {{color:{c['text']};background:transparent;}}
        QLabel#brand {{color:{c['text']};font-size:22px;font-weight:650;letter-spacing:-.4px;}}
        QLabel#caption {{color:{c['muted']};font-size:10px;font-weight:600;letter-spacing:1.2px;}}
        QLabel#muted {{color:{c['muted']};font-size:12px;}}
        QLabel#viewName {{font-weight:600;color:{c['text']};}}
        QLabel#dialogTitle {{font-size:23px;font-weight:650;color:{c['text']};}}
        QLabel#sectionTitle {{font-size:17px;font-weight:600;}}
        QLabel#fontPreview {{background:{rgba('background',180)};border-radius:20px;padding:20px;color:{c['text']};}}
        QPushButton {{background:{rgba('secondary',38)};color:{c['text']};border:1px solid transparent;border-radius:14px;padding:8px 14px;min-height:20px;}}
        QPushButton:hover {{background:{rgba('primary',32)};}}
        QPushButton:checked {{background:{rgba('primary',65)};border-color:{rgba('primary',150)};}}
        QPushButton:pressed {{background:{rgba('primary',55)};}}
        QPushButton:focus {{border-color:{rgba('primary',160)};}}
        QPushButton:disabled {{color:{c['muted']};background:{rgba('secondary',15)};}}
        QPushButton[role="icon"] {{padding:0;border-radius:18px;background:transparent;min-height:28px;min-width:28px;}}
        QPushButton[role="icon"]:hover {{background:{rgba('primary',34)};}}
        QPushButton[role="toolbar"] {{border-radius:18px;background:{rgba('secondary',28)};padding:7px 13px;}}
        QPushButton[role="toolbar"]:hover {{background:{rgba('primary',32)};}}
        QPushButton[role="place"] {{text-align:left;background:transparent;border-radius:15px;padding:10px 12px;}}
        QPushButton[role="place"]:hover {{background:{rgba('primary',25)};}}
        QPushButton[dropHover="true"] {{background:{rgba('primary',64)};border:1px solid {rgba('primary',150)};}}
        QPushButton#primaryButton {{background:{c['primary']};color:{c['background']};font-weight:600;border-radius:18px;padding:10px 22px;}}
        QPushButton#primaryButton:hover {{background:{c['folder']};}}
        QPushButton#softButton {{background:{rgba('secondary',35)};border-radius:18px;}}
        QPushButton#dropAction {{text-align:left;padding:14px 18px;background:{rgba('background',150)};border-radius:18px;min-height:42px;}}
        QPushButton#dropAction:hover {{background:{rgba('primary',28)};border-color:{rgba('primary',90)};}}
        QLineEdit,QComboBox,QFontComboBox,QSpinBox,QDoubleSpinBox {{background:{rgba('background',180)};color:{c['text']};border:1px solid transparent;border-radius:14px;padding:9px 12px;selection-background-color:{c['secondary']};}}
        QLineEdit:focus,QComboBox:focus,QFontComboBox:focus,QSpinBox:focus {{border-color:{rgba('primary',170)};}}
        QLineEdit#addressInput {{font-weight:500;}}
        QLineEdit#spotlightInput {{font-size:24px;padding:14px 8px;background:transparent;border:0;}}
        QComboBox,QFontComboBox {{padding-right:30px;}}
        QComboBox::drop-down,QFontComboBox::drop-down {{border:0;width:30px;}}
        QComboBox::down-arrow,QFontComboBox::down-arrow {{image:none;}}
        QSpinBox {{padding-right:30px;}}
        QSpinBox::up-button {{subcontrol-origin:border;subcontrol-position:top right;border:0;background:transparent;width:28px;}}
        QSpinBox::down-button {{subcontrol-origin:border;subcontrol-position:bottom right;border:0;background:transparent;width:28px;}}
        QSpinBox::up-arrow,QSpinBox::down-arrow {{image:none;}}
        QComboBox QAbstractItemView,QFontComboBox QAbstractItemView {{background:{c['panel']};color:{c['text']};selection-background-color:{c['secondary']};border:1px solid {rgba('secondary',70)};border-radius:12px;outline:0;padding:6px;}}
        QListView {{background:transparent;color:{c['text']};border:0;outline:0;}}
        QListView::item {{padding:10px;border-radius:14px;}}
        QListView::item:selected,QListView::item:hover {{background:{rgba('primary',25)};}}
        QListView#settingsNav {{background:transparent;min-width:160px;max-width:160px;}}
        QListView#settingsNav::item {{padding:13px 15px;margin-bottom:4px;border-radius:16px;}}
        QListView#settingsNav::item:selected {{background:{rgba('primary',34)};color:{c['primary']};}}
        QListView#pathSuggestions {{background:{c['panel']};border:1px solid {rgba('secondary',70)};border-radius:18px;padding:6px;}}
        QPlainTextEdit {{background:{rgba('background',180)};color:{c['text']};border:0;border-radius:14px;padding:10px;}}
        QScrollArea,QScrollArea>QWidget>QWidget {{background:transparent;border:0;}}
        QMenu {{background:{c['panel']};color:{c['text']};border:1px solid {rgba('secondary',60)};border-radius:16px;padding:7px;}}
        QMenu::item {{padding:10px 22px;border-radius:10px;}}
        QMenu::item:selected {{background:{rgba('primary',35)};}}
        QMenu::separator {{height:1px;background:{rgba('secondary',60)};margin:5px 12px;}}
        QDialog {{background:{c['panel']};color:{c['text']};}}
        QDialog#surfaceDialog {{background:transparent;}}
        QTabWidget::pane {{border:0;}}
        QTabBar::tab {{padding:10px 16px;color:{c['muted']};border-radius:14px;}}
        QTabBar::tab:selected {{color:{c['primary']};background:{rgba('primary',25)};}}
        QSlider::groove:horizontal {{background:{rgba('secondary',100)};height:5px;border-radius:2px;}}
        QSlider::sub-page:horizontal {{background:{c['primary']};border-radius:2px;}}
        QSlider::handle:horizontal {{background:{c['primary']};width:16px;height:16px;margin:-6px 0;border-radius:8px;}}
        QCheckBox::indicator {{width:18px;height:18px;border:1px solid {c['secondary']};border-radius:6px;background:{rgba('background',200)};}}
        QCheckBox::indicator:checked {{background:{c['primary']};border-color:{c['primary']};}}
        QScrollBar:vertical {{background:transparent;width:6px;margin:6px 0;}}
        QScrollBar::handle:vertical {{background:{rgba('secondary',110)};border-radius:3px;min-height:24px;}}
        QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{height:0;}}
        QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {{background:transparent;}}
        QToolTip {{background:{c['panel']};color:{c['text']};border:1px solid {rgba('secondary',60)};border-radius:10px;padding:8px 12px;}}
    '''


class Panel(QFrame):
    """Live alpha without reparsing/repolishing the entire application stylesheet."""
    def paintEvent(self,event):
        parent=self;config=None
        while parent is not None:
            config=getattr(parent,'config',None)
            if isinstance(config,dict) and 'colors' in config:break
            parent=parent.parentWidget()
        if config:
            header=self.objectName()=='viewportHeader'
            painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            color=QColor(config['colors']['panel']);color.setAlpha(round((200 if header else 255)*config['opacity']/100))
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(color)
            painter.drawRoundedRect(QRectF(self.rect()),0 if header else 24,0 if header else 24);painter.end()
        super().paintEvent(event)


class SurfaceDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config=config; self.setObjectName('surfaceDialog')
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        from panel_motion import bind_dialog
        bind_dialog(self,config)
    def done(self,result):
        from panel_motion import dismiss
        dismiss(self,self.config,'dialogs',lambda:QDialog.done(self,result))
    def closeEvent(self,event):
        event.ignore();self.reject()
    def paintEvent(self, event):
        painter=QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color=QColor(self.config['colors']['secondary']); color.setAlpha(70)
        painter.setPen(color); painter.setBrush(QColor(self.config['colors']['panel']))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),26,26)


class DialogHandle(QFrame):
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()


class ChevronMixin:
    """Keep the dropdown affordance visible with any desktop/widget theme."""
    def paintEvent(self, event):
        super().paintEvent(event)
        painter=QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color=self.palette().text().color()
        ui_icon('chevron',color.name(),16).paint(painter,self.width()-26,(self.height()-16)//2,16,16)

    def showPopup(self):
        colors=popup_colors(self)
        prepare_popup(self.view(),colors)
        super().showPopup()
        prepare_popup(self.view(),colors)


class ComboBox(ChevronMixin,QComboBox):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.setView(PopupList())
class FontComboBox(ChevronMixin,QFontComboBox):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        delegate=self.itemDelegate();delegate.setParent(self)
        self.setView(PopupList());self.setItemDelegate(delegate)


def popup_colors(widget):
    parent=widget
    while parent:
        config=getattr(parent,'config',None)
        if isinstance(config,dict) and 'colors' in config:return config['colors']
        parent=parent.parentWidget()
    palette=widget.palette()
    return {'panel':palette.window().color().name(),'text':palette.text().color().name(),
            'secondary':palette.highlight().color().name(),'primary':palette.highlight().color().name()}


def prepare_popup(view,colors):
    """Paint view, viewport and native popup independently of inherited QSS."""
    palette=QPalette(view.palette())
    for role,key in ((QPalette.ColorRole.Base,'panel'),(QPalette.ColorRole.Window,'panel'),
                     (QPalette.ColorRole.Text,'text'),(QPalette.ColorRole.WindowText,'text'),
                     (QPalette.ColorRole.Highlight,'secondary'),(QPalette.ColorRole.HighlightedText,'text')):
        palette.setColor(role,QColor(colors[key]))
    view.setProperty('popupPanelColor',colors['panel'])
    view.setStyleSheet(f'''QListView {{background-color:{colors['panel']};color:{colors['text']};
        border:1px solid {colors['secondary']};border-radius:12px;padding:6px;outline:0;}}
        QListView::item {{padding:9px 12px;border-radius:7px;}}
        QListView::item:selected,QListView::item:hover {{background:{colors['secondary']};color:{colors['text']};}}
        QScrollBar:vertical {{background:{colors['panel']};width:6px;margin:4px 0;}}
        QScrollBar::handle:vertical {{background:{colors['secondary']};border-radius:3px;min-height:24px;}}
        QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{height:0;}}
        QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {{background:{colors['panel']};}}''')
    for surface in (view,view.viewport(),view.window()):
        surface.setPalette(palette);surface.setBackgroundRole(QPalette.ColorRole.Base)
        surface.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,False)
        surface.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground,False)
        surface.setAutoFillBackground(True)
    view.viewport().setStyleSheet(f'background-color:{colors["panel"]};')
    view.window().setWindowOpacity(1.0)


class PopupList(QListView):
    def paintEvent(self,event):
        painter=QPainter(self.viewport())
        painter.fillRect(event.rect(),QColor(self.property('popupPanelColor') or self.palette().base().color()))
        painter.end();super().paintEvent(event)


class Menu(QMenu):
    """Opaque even when the application window and desktop theme are translucent."""
    def showEvent(self,event):
        colors=popup_colors(self);self._surface_color=QColor(colors['panel'])
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground,False)
        self.setWindowOpacity(1.0)
        self.setStyleSheet(f'''QMenu {{background-color:{colors['panel']};color:{colors['text']};
            border:1px solid {colors['secondary']};padding:6px;}}
            QMenu::item {{padding:9px 20px;border-radius:8px;}}
            QMenu::item:selected {{background:{colors['secondary']};}}
            QMenu::separator {{height:1px;background:{colors['secondary']};margin:5px 10px;}}''')
        super().showEvent(event)
    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(event.rect(),getattr(self,'_surface_color',self.palette().window().color()));painter.end()
        super().paintEvent(event)


class SpinBox(QSpinBox):
    def paintEvent(self,event):
        super().paintEvent(event)
        painter=QPainter(self);color=self.palette().text().color().name()
        icon=ui_icon('chevron',color,12)
        painter.save();painter.translate(self.width()-14,self.height()*.27);painter.rotate(180)
        icon.paint(painter,-6,-6,12,12);painter.restore()
        icon.paint(painter,self.width()-20,round(self.height()*.73)-6,12,12)

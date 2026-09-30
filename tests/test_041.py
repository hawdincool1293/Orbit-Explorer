"""Regressions for passive suggestions, opaque popup windows and themed pins."""
import json,unittest
from unittest.mock import patch
from PySide6.QtCore import QPoint,Qt
from PySide6.QtGui import QColor,QImage,QPainter
from PySide6.QtWidgets import QComboBox
from PySide6.QtTest import QTest
import test_04 as fixtures
from test_04 import pump,until
from ui import Settings
from design import Menu,PopupList
from appearance import PRESETS,pin_color,load_config

class FixTests(unittest.TestCase):
    setUp=fixtures.FlowTests.setUp
    tearDown=fixtures.FlowTests.tearDown
    type_path=fixtures.FlowTests.type_path

    def test_suggestions_do_not_rewrite_text_on_hover_arrows_or_typing(self):
        entry=self.w.address;typed=str(self.root)+'/p';self.type_path(typed)
        self.assertTrue(until(lambda:bool(entry.ghost_text)))
        self.assertEqual(entry.text(),typed);self.assertFalse(entry.hasSelectedText())
        popup=entry.completion.popup()
        QTest.keyClick(entry,Qt.Key.Key_Down);QTest.keyClick(entry,Qt.Key.Key_Down);pump(30)
        self.assertEqual(entry.text(),typed)
        index=popup.model().index(2,0)
        QTest.mouseMove(popup.viewport(),popup.visualRect(index).center());pump(30)
        self.assertEqual(entry.text(),typed)
        QTest.keyClicks(entry,'ic');pump(140)
        self.assertEqual(entry.text(),typed+'ic');self.assertEqual(entry.ghost_text,'tures/')
        self.assertEqual(self.w.location,str(self.root))

    def test_tab_and_escape_never_accept_and_slash_does_not_suggest_first_child(self):
        entry=self.w.address;typed=str(self.root)+'/pic';self.type_path(typed)
        self.assertTrue(until(lambda:bool(entry.candidate)))
        QTest.keyClick(entry,Qt.Key.Key_Tab);pump(80)
        self.assertEqual(entry.text(),typed);self.assertFalse(entry.candidate)
        self.type_path(typed);self.assertTrue(until(lambda:bool(entry.candidate)))
        QTest.keyClick(entry,Qt.Key.Key_Escape);pump(180)
        self.assertEqual(entry.text(),typed);self.assertFalse(entry.candidate)
        self.type_path(str(self.root)+'/');pump(200)
        self.assertFalse(entry.candidate);self.assertFalse(entry.completion.popup().isVisible())

    def test_all_settings_dropdowns_paint_opaque_themed_backgrounds(self):
        settings=Settings(self.w.config,self.w);settings.changed.connect(self.w.settings_changed)
        settings.show();settings.preset('Black & Deep Red');self.w.config['opacity']=25;self.w.apply_theme()
        pump(40)
        for combo in settings.findChildren(QComboBox):
            page=next(i for i in range(settings.pages.count()) if settings.pages.widget(i).isAncestorOf(combo))
            settings.navigation.setCurrentRow(page);pump(15)
            combo.view().setStyleSheet('background:transparent;')
            combo.view().viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
            combo.showPopup();pump(40)
            view=combo.view();self.assertIsInstance(view,PopupList)
            image=view.viewport().grab().toImage()
            self.assertFalse(view.window().testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
            panel=QColor(self.w.config['colors']['panel'])
            pixels=[image.pixelColor(x,y) for x in range(2,image.width()-2,5) for y in range(2,image.height()-2,5)]
            self.assertTrue(pixels)
            self.assertTrue(all(p.alpha()==255 for p in pixels))
            self.assertGreater(sum(p==panel for p in pixels),len(pixels)*.1)
            combo.hidePopup()
        settings.close();settings.deleteLater()

    def test_context_menu_is_opaque_and_uses_current_palette(self):
        self.w.config['colors']=dict(PRESETS['Purple & Dark Gray']);self.w.apply_theme()
        menu=Menu(self.w);menu.addAction('Properties');menu.addAction('Send to…');menu.popup(QPoint(50,50));pump(40)
        image=menu.grab().toImage();color=image.pixelColor(3,image.height()//2)
        self.assertEqual(color,QColor(self.w.config['colors']['panel']));self.assertEqual(color.alpha(),255)
        menu.close();menu.deleteLater()

    def test_pins_and_badge_surfaces_follow_every_preset_and_live_system_colors(self):
        self.w.pin(str(self.root/'Pictures'));favorite=self.w.config['favorites'][0]
        custom={'path':str(self.root/'Projects'),'color':'#ffb322','color_mode':'custom'}
        self.w.config['favorites'].append(custom);self.w.refresh_favorites()
        for colors in [*PRESETS.values(),dict(PRESETS['Midnight Teal'],primary='#49ccdd',panel='#1c2030',text='#ffffff')]:
            self.w.config['colors']=dict(colors);self.w.apply_theme();pump(20)
            self.assertEqual(pin_color(favorite,self.w.config),colors['primary'])
            self.assertEqual(pin_color(custom,self.w.config),'#ffb322')
            image=QImage(500,80,QImage.Format.Format_ARGB32);image.fill(QColor(colors['background']))
            painter=QPainter(image);self.w.graph.paint_favorites(painter);painter.end()
            self.assertEqual(image.pixelColor(42,39),QColor(colors['primary']))
            pixel=image.pixelColor(80,22);expected=QColor(colors['panel'])
            self.assertLess(max(abs(pixel.red()-expected.red()),abs(pixel.green()-expected.green()),abs(pixel.blue()-expected.blue())),5)
            icon=self.w.pin_buttons[favorite['path']].icon().pixmap(22,22).toImage()
            solid=[icon.pixelColor(x,y) for x in range(icon.width()) for y in range(icon.height()) if icon.pixelColor(x,y).alpha()>220]
            self.assertTrue(solid)
            self.assertTrue(any(p.name()==colors['primary'] for p in solid))

    def test_legacy_default_colors_migrate_but_custom_colors_survive(self):
        settings=self.root/'old.json'
        settings.write_text(json.dumps({'favorites':[{'path':'/home','color':'#66cfbc'},{'path':'/var','color':'#dd9900'}]}))
        with patch('appearance.CONFIG',settings):config=load_config()
        self.assertEqual([p['color_mode'] for p in config['favorites']],['theme','custom'])
        config['colors']=dict(PRESETS['Black & Deep Red'])
        self.assertEqual(pin_color(config['favorites'][0],config),'#ec586e')
        self.assertEqual(pin_color(config['favorites'][1],config),'#dd9900')

if __name__=='__main__':unittest.main()

"""Settings persistence and system palette integration."""
# Orbit input patch: trackpad-opening-2026-09-30
import orbit_controls
import json
import os
from pathlib import Path
from PySide6.QtGui import QColor, QIcon, QFontDatabase

PRESETS = {
    "Midnight Teal": {"background": "#080d17", "panel": "#101d2b", "primary": "#66cfbc",
                       "secondary": "#326678", "accent": "#8666dc", "text": "#ddede9",
                       "muted": "#86a9aa", "lines": "#417d86", "folder": "#73c9b3", "file": "#78a7ba"},
    "Black & Deep Red": {"background": "#0c090d", "panel": "#1a1017", "primary": "#ec586e",
                          "secondary": "#773543", "accent": "#bb374d", "text": "#f3e5e7",
                          "muted": "#ac8993", "lines": "#79404d", "folder": "#df6875", "file": "#bd8790"},
    "Purple & Dark Gray": {"background": "#111019", "panel": "#211e2c", "primary": "#b99afa",
                            "secondary": "#625280", "accent": "#e69cca", "text": "#efebf8",
                            "muted": "#a6a0bc", "lines": "#665584", "folder": "#ac91ed", "file": "#a5a0bf"},
}

COLOR_NAMES = {"background": "Canvas", "panel": "Panels", "primary": "Primary", "secondary": "Secondary",
               "accent": "Accent", "text": "Text", "muted": "Muted text", "lines": "Connections",
               "folder": "Folders", "file": "Files"}

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "orbit-explorer/settings.json"
if os.environ.get('FLATPAK_ID'):CONFIG=Path.home()/'.config/orbit-explorer/settings.json'
SYSTEM_PRESET = "System (Caelestia)"
_fonts_registered = False

def register_fonts():
    global _fonts_registered
    if _fonts_registered:return
    assets=Path(__file__).parent/'assets/fonts'
    for family in ('Manrope','NunitoSans','Inter'):
        for style in ('Regular','SemiBold'):
            QFontDatabase.addApplicationFont(str(assets/f'{family}-{style}.ttf'))
    _fonts_registered=True

def default_font():
    register_fonts()
    available=set(QFontDatabase.families())
    return next((family for family in ('Manrope','Inter','Noto Sans','Sans Serif') if family in available),'Sans Serif')

def defaults(font="Sans Serif"):
    return {"colors": dict(PRESETS["Midnight Teal"]), "preset": "Midnight Teal", "opacity": 92,
            "font": font, "favorites": [], "last_path": str(Path.home()), "show_hidden": False,
            "invert_vertical": False, "invert_horizontal": False, "label_key": "Tab",
            "spotlight": True, "audio_internal": True, "thumbnails": True,
            "icon_theme": "Sweet (bundled)", "type_icons": {}, "palette_file": "", "volume": 80,"search_strict":False,
            "recent_folders": [], "node_spacing": 1.35, "node_limit": 680, "moons": True,
            "font_size": 11,"drive_aliases":{},"pane_sizes":{},"files_internal":True,
            "drop_popup":"center","navigation_enabled":True,"navigation_duration":1400,
            "navigation_fade":65,"navigation_rotate":True,"navigation_easing":"Smooth",
            "workspace_layout":{},"file_layout":{},"window_size":[],"window_maximized":False,"detail_width":348, "rotation_gesture":"middle", "trackpad_scroll_rotate":False,
            "panel_motion_enabled":True,"panel_motion_sidebar":True,"panel_motion_files":True,"panel_motion_dialogs":True,
            "panel_motion_duration":240,"panel_motion_fps":120,"panel_motion_travel":100,"panel_motion_fade":True}

def pin_color(favorite,config):
    color=favorite.get('color','')
    if favorite.get('color_mode')=='custom' and isinstance(color,str) and QColor(color).isValid():return color
    return config['colors']['primary']

def migrate_pin_colors(config):
    # Older releases stored a snapshot of the primary even for default pins.
    defaults={QColor(p['primary']).name() for p in PRESETS.values()}|{QColor(config['colors']['primary']).name()}
    for favorite in config['favorites']:
        if favorite.get('color_mode') in ('theme','custom'):continue
        raw=favorite.get('color','');color=QColor(raw) if isinstance(raw,str) else QColor()
        favorite['color_mode']='custom' if color.isValid() and color.name() not in defaults else 'theme'

def load_config(font="Sans Serif"):
    result = defaults(font)
    try:
        saved = json.loads(CONFIG.read_text())
        result.update({k: v for k, v in saved.items() if k in result})
        result["colors"] = {**PRESETS.get(result['preset'],PRESETS["Midnight Teal"]), **{k:v for k,v in result["colors"].items()
                              if k in COLOR_NAMES and isinstance(v,str) and QColor(v).isValid()}}
        result["favorites"] = [f for f in result["favorites"] if isinstance(f,dict) and isinstance(f.get("path"),str)]
        migrate_pin_colors(result)
        result["opacity"] = max(25, min(100, int(result["opacity"])))
        result["font_size"] = max(9, min(16, int(result["font_size"])))
    except (OSError, ValueError, TypeError, AttributeError):
        result = defaults(font)
    return result

def save_config(config):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG.with_suffix(".tmp")
    temporary.write_text(json.dumps(config, indent=2))
    temporary.replace(CONFIG)

def palette_path(config):
    if config["palette_file"]: return Path(config["palette_file"]).expanduser()
    state=str(Path.home()/'.local/state') if os.environ.get('FLATPAK_ID') else os.environ.get("XDG_STATE_HOME",str(Path.home()/'.local/state'))
    return Path(state)/'caelestia/scheme.json'

def read_palette(path):
    data = json.loads(Path(path).read_text())
    colors = data.get("colours", data.get("colors", data))
    mapping = {"background": ("background","surface"), "panel": ("surfaceContainer","surface"),
               "primary": ("primary",), "secondary": ("secondary",), "accent": ("tertiary",),
               "text": ("onSurface","onBackground"), "muted": ("onSurfaceVariant","outline"),
               "lines": ("outlineVariant","outline"), "folder": ("primary",), "file": ("secondary",)}
    result = {}
    for target, candidates in mapping.items():
        for name in candidates:
            raw = colors.get(name, colors.get("m3"+name))
            if isinstance(raw, str):
                value = raw if raw.startswith("#") else "#"+raw
                if QColor(value).isValid():
                    result[target] = value; break
    if not result: raise ValueError("No recognized Caelestia colors in this file.")
    return result

def icon_themes():
    paths = list(QIcon.themeSearchPaths()) + [str(Path.home()/".icons"), str(Path.home()/".local/share/icons"), "/usr/share/icons"]
    names = set()
    for folder in paths:
        try:
            for p in Path(folder).iterdir():
                if (p/"index.theme").is_file(): names.add(p.name)
        except OSError: pass
    return ["Sweet (bundled)", "System", "Orbit"] + sorted(names, key=str.casefold)

def system_icons():
    # Dolphin's selection is useful under Hyprland where Qt may have no theme provider.
    import configparser
    for candidate in (Path.home()/".config/kdeglobals",):
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(candidate)
            name = parser.get("Icons", "Theme", fallback="")
            if name: return name
        except configparser.Error: pass
    return QIcon.themeName() or "breeze"

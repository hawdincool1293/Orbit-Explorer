"""Configure bundled Fontconfig before any Qt/font library is imported."""
import os,sys
from pathlib import Path
if sys.platform.startswith('linux') and getattr(sys,'frozen',False):
    config=Path(sys._MEIPASS)/'assets/fontconfig/fonts.conf'
    # Preserve explicit launch-time choices; never change the host's files.
    if config.is_file() and not os.environ.get('FONTCONFIG_FILE') and not os.environ.get('FONTCONFIG_PATH'):
        os.environ['FONTCONFIG_FILE']=str(config)
        os.environ['FONTCONFIG_PATH']=str(config.parent)
        os.environ['_ORBIT_BUNDLED_FONTCONFIG']='1'

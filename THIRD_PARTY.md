# Third-party components

Orbit's portable builds contain Python, PySide6/Qt, NumPy, PyInstaller's
bootloader, FFmpeg/FFprobe, ripgrep, and their dynamically linked dependencies.
The components keep their respective licenses; this document does not relicense
them or grant a new license to Orbit's own source. Packaged license files are
under the frozen application's `licenses/` directory where supplied by the
installed distributions.

Source and build information:

- Python: https://www.python.org/downloads/source/
- Qt 6.11.2: https://download.qt.io/archive/qt/6.11/6.11.2/
- PySide/Shiboken: https://code.qt.io/cgit/pyside/pyside-setup.git/
- NumPy: https://github.com/numpy/numpy
- PyInstaller 6.16.0: https://github.com/pyinstaller/pyinstaller/tree/v6.16.0
- FFmpeg: https://ffmpeg.org/download.html and https://ffmpeg.org/legal.html
- Ubuntu FFmpeg source packages and packaging patches:
  https://archive.ubuntu.com/ubuntu/pool/universe/f/ffmpeg/
- ripgrep: https://github.com/BurntSushi/ripgrep
- AppImage runtime/tool sources: https://github.com/AppImage/type2-runtime
  and https://github.com/AppImage/appimagetool

FFmpeg is a separate executable, not linked into Orbit's Python application.
Run the bundled `ffmpeg -version` and `ffmpeg -L` for its exact configuration
and license notice. Qt's multimedia backend also includes its own FFmpeg
libraries. The source ZIP includes the build specification so the application
can be rebuilt, and the onedir layout permits replacement of bundled dynamic
libraries. Keep license notices and satisfy the relevant source obligations
before redistributing your own builds.

The included fonts retain their OFL notices in `assets/fonts/`.

Sweet Rainbow folder artwork and Candy file/device artwork by EliverLara and
contributors are supplied as editable SVG source under GPL-3.0. Exact upstream
commits, original filenames, and both license texts are in
`assets/icons/sweet/NOTICE.md`, `LICENSE-Sweet`, and `LICENSE-Candy`.

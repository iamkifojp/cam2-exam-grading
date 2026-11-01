# PyInstaller recipe for CAM2. Run it through tools/build_windows.py.
# One folder rather than one file: a single .exe would unpack itself to a temp
# folder on every start, which is slow and upsets antivirus programs.
# No console window: launcher.py sends its output to <app data>/logs/cam2.log.

from pathlib import Path

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    # Read through __file__ by app.py and engine/i18n.py, which PyInstaller
    # points inside the bundle.
    datas=[(str(ROOT / folder), folder) for folder in ("i18n", "static", "templates")],
    # PyMuPDF 2.0 installs and imports an AI page-layout add-on (pymupdf.layout,
    # pymupdf4llm and what they need) if it finds it. CAM2 never uses it, and it
    # would add about 100 MB and a model file PyInstaller doesn't collect.
    excludes=["tkinter", "unittest", "setuptools", "pymupdf.layout", "pymupdf_layout",
              "pymupdf4llm", "onnxruntime", "numpy", "networkx", "yaml", "tabulate", "psutil"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="Start CAM2 Exam Grading",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="CAM2 Exam Grading", upx=False)

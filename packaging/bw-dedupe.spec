# PyInstaller spec for the standalone executable (Python is bundled inside).
# Build: pyinstaller packaging/bw-dedupe.spec
import os

root = os.path.dirname(SPECPATH)

a = Analysis(
    [os.path.join(root, "bw_dedupe.py")],
    pathex=[root],
    datas=[
        (os.path.join(root, "bwdedupe", "web"), "bwdedupe/web"),
        (os.path.join(root, "bwdedupe", "public_suffix_list.dat"), "bwdedupe"),
    ],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="bw-dedupe", console=True, upx=False)

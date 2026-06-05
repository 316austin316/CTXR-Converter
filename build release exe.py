import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")

hidden = [
    "ps3_ctxr_module",
    "image_viewer",
    "dds_module",
    "ctxr_utils",
    "PIL.ImageTk",
    "numpy",
]

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--name", "ctxr3",
]

if os.path.exists(os.path.join(HERE, "resources", "face.PNG")):
    cmd += ["--add-data", f"resources/face.PNG{os.pathsep}resources"]

ico = os.path.join(HERE, "resources", "face.ico")
if os.path.exists(ico):
    cmd += ["--icon", ico]

for h in hidden:
    cmd += ["--hidden-import", h]

cmd.append("ctxr3.py")

print("Building exe...")
rc = subprocess.call(cmd, cwd=HERE)
if rc != 0:
    sys.exit(rc)

# copy settings and shit
for name in ["no_mip_regex.txt", "must_be_dxt5.txt", "ctxr3.ini"]:
    src = os.path.join(HERE, name)
    dst = os.path.join(DIST, name)
    if os.path.exists(src):
        shutil.copy2(src, dst)
        print(f"Copied {name} -> dist/")
    else:
        print(f"WARNING: {name} not found in repo root, skipping.")

print("\nDone.")

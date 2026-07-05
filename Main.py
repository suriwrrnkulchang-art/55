"""
Custom App Installer
=====================
GUI installer ที่:
  - ใส่โลโก้ / ชื่อโปรแกรมได้ (แก้ตัวแปรด้านล่าง หรือทำเป็น config)
  - มีหน้าติดตั้งพร้อม progress bar + สถานะ
  - ให้เลือกโฟลเดอร์ปลายทางที่จะติดตั้ง
  - ดาวน์โหลดโปรเจกต์จาก GitHub (zip)
  - เช็ค/ติดตั้ง Python 3.12 ถ้ายังไม่มี
  - รันคำสั่งติดตั้ง pip package ผ่าน cmd (subprocess)
  - รันไฟล์ .py หลักหลังติดตั้งเสร็จ + สร้าง shortcut บนเดสก์ท็อป
  - ถ้าขั้นตอนไหน error จะแจ้งเตือนแล้วปิดโปรแกรม

หลังจากแก้โค้ดตามต้องการแล้ว ให้แปลงเป็น .exe ด้วยคำสั่ง (ดูท้ายไฟล์ README.txt)
"""

import os
import sys
import shutil
import zipfile
import ctypes
import subprocess
import tempfile
import traceback
import threading
import urllib.request
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ------------------------------------------------------------------
# ตั้งค่าตรงนี้ตามโปรแกรมของคุณ (จุดที่ "เปลี่ยนโลโก้ได้ เปลี่ยนชื่อได้")
# ------------------------------------------------------------------
APP_NAME = "MyProgram"                 # ชื่อโปรแกรมที่จะแสดง
APP_LOGO_PATH = "logo.ico"             # ไฟล์โลโก้ (.ico สำหรับ exe/shortcut, .png ใช้แสดงใน GUI ได้)
GITHUB_ZIP_URL = "https://github.com/suriwrrnkulchang-art/master"
MAIN_PY_FILE = "main.py"               # ไฟล์ .py หลักในโปรเจกต์ที่จะให้รันหลังติดตั้ง
PYTHON_VERSION = "3.12.4"              # เวอร์ชัน python ที่จะติดตั้งถ้าเครื่องยังไม่มี
PIP_PACKAGES = ["numpy", "speechrecognition", "soundfile", "pyaudio"]
SHORTCUT_PACKAGES = ["pywin32", "winshell"]   # ใช้เฉพาะตอนสร้าง shortcut บนเดสก์ท็อป

DEFAULT_INSTALL_DIR = str(Path.home() / APP_NAME)


def resource_path(relative_path):
    """
    หาพาธไฟล์ที่แนบมากับตัว exe ให้ถูกต้อง
    ทั้งตอนรันเป็น .py ปกติ และตอนถูก build เป็น .exe แบบ --onefile ด้วย PyInstaller
    (PyInstaller จะแตกไฟล์แนบไปไว้ที่โฟลเดอร์ temp ชื่อ sys._MEIPASS ชั่วคราว)
    """
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


class InstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"ติดตั้ง {APP_NAME}")
        self.root.geometry("480x360")
        self.root.resizable(False, False)

        # ใส่ไอคอนหน้าต่าง ถ้ามีไฟล์ .ico
        logo_src = resource_path(APP_LOGO_PATH)
        if os.path.exists(logo_src):
            try:
                self.root.iconbitmap(logo_src)
            except Exception:
                pass

        self.install_dir = tk.StringVar(value=DEFAULT_INSTALL_DIR)
        self._build_ui()

    # ---------------- UI ----------------
    def _build_ui(self):
        title = tk.Label(self.root, text=f"ตัวติดตั้ง {APP_NAME}", font=("Segoe UI", 16, "bold"))
        title.pack(pady=(20, 5))

        subtitle = tk.Label(self.root, text="กด 'เริ่มติดตั้ง' เพื่อดาวน์โหลดและติดตั้งโปรแกรม")
        subtitle.pack(pady=(0, 15))

        # เลือกโฟลเดอร์ปลายทาง
        frame_path = tk.Frame(self.root)
        frame_path.pack(fill="x", padx=20)
        tk.Label(frame_path, text="ตำแหน่งติดตั้ง:").pack(anchor="w")
        path_row = tk.Frame(frame_path)
        path_row.pack(fill="x")
        tk.Entry(path_row, textvariable=self.install_dir).pack(side="left", fill="x", expand=True)
        tk.Button(path_row, text="เลือก...", command=self.choose_dir).pack(side="left", padx=5)

        # progress bar + label สถานะ
        self.status_label = tk.Label(self.root, text="รอเริ่มการติดตั้ง...", anchor="w")
        self.status_label.pack(fill="x", padx=20, pady=(20, 5))

        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=430, mode="determinate")
        self.progress.pack(padx=20, pady=5)

        self.install_btn = tk.Button(
            self.root, text="เริ่มติดตั้ง", bg="#2d7ff9", fg="white",
            font=("Segoe UI", 11, "bold"), command=self.start_install_thread
        )
        self.install_btn.pack(pady=20, ipadx=10, ipady=5)

    def choose_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.install_dir.set(d)

    def set_status(self, text, percent=None):
        self.status_label.config(text=text)
        if percent is not None:
            self.progress["value"] = percent
        self.root.update_idletasks()

    # ---------------- Logic ----------------
    def start_install_thread(self):
        self.install_btn.config(state="disabled")
        t = threading.Thread(target=self.run_install, daemon=True)
        t.start()

    def run_install(self):
        try:
            target_dir = self.install_dir.get()
            os.makedirs(target_dir, exist_ok=True)

            # ขั้นที่ 1: เช็ค/ติดตั้ง python 3.12
            self.set_status("กำลังตรวจสอบ Python...", 5)
            if not self.check_python():
                self.set_status("ไม่พบ Python 3.12 กำลังดาวน์โหลด...", 10)
                self.install_python()

            # ขั้นที่ 2: ดาวน์โหลดโปรเจกต์จาก GitHub
            self.set_status("กำลังดาวน์โหลดไฟล์จาก GitHub...", 30)
            extracted_path = self.download_and_extract(target_dir)

            # ขั้นที่ 3: ติดตั้ง pip package ผ่าน cmd
            self.set_status("กำลังติดตั้งไลบรารีที่จำเป็น...", 55)
            self.install_pip_packages()

            # ขั้นที่ 4: ตรวจสอบว่าไฟล์หลักรันได้ไหม
            self.set_status("กำลังตรวจสอบโปรแกรม...", 80)
            main_file = self.find_main_file(extracted_path)
            self.verify_runnable(main_file)

            # ขั้นที่ 5: สร้าง shortcut บนเดสก์ท็อป
            self.set_status("กำลังสร้างทางลัดบนเดสก์ท็อป...", 90)
            self.create_desktop_shortcut(main_file, extracted_path)

            # ขั้นที่ 6: เปิดโปรแกรมทันที
            self.set_status("ติดตั้งเสร็จสมบูรณ์! กำลังเปิดโปรแกรม...", 100)
            self.launch_program(main_file)

            messagebox.showinfo("สำเร็จ", f"ติดตั้ง {APP_NAME} เรียบร้อยแล้ว")
            self.root.after(500, self.root.destroy)

        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("เกิดข้อผิดพลาด", f"การติดตั้งล้มเหลว:\n{e}")
            self.root.destroy()
            sys.exit(1)

    # ---- Python check/install ----
    def check_python(self):
        try:
            out = subprocess.run(
                ["py", "-3.12", "--version"],
                capture_output=True, text=True, shell=True
            )
            return out.returncode == 0
        except Exception:
            return False

    def install_python(self):
        url = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-amd64.exe"
        tmp_exe = os.path.join(tempfile.gettempdir(), "python_installer.exe")
        urllib.request.urlretrieve(url, tmp_exe)
        # ติดตั้งแบบ silent พร้อมเพิ่ม PATH และ py launcher
        result = subprocess.run(
            [tmp_exe, "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_launcher=1"],
            shell=True
        )
        if result.returncode != 0:
            raise RuntimeError("ติดตั้ง Python ไม่สำเร็จ")

    # ---- Download from GitHub ----
    def download_and_extract(self, target_dir):
        tmp_zip = os.path.join(tempfile.gettempdir(), "repo.zip")
        urllib.request.urlretrieve(GITHUB_ZIP_URL, tmp_zip)
        with zipfile.ZipFile(tmp_zip, "r") as z:
            z.extractall(target_dir)
        os.remove(tmp_zip)
        return target_dir

    def find_main_file(self, base_dir):
        return self.find_file(base_dir, MAIN_PY_FILE, required=True)

    def find_file(self, base_dir, filename, required=False):
        for root_dir, _, files in os.walk(base_dir):
            if filename in files:
                return os.path.join(root_dir, filename)
        if required:
            raise FileNotFoundError(f"หาไฟล์ {filename} ไม่พบหลังแตกไฟล์")
        return None

    # ---- pip install ผ่าน cmd (ใช้ซ้ำได้กับรายการ package ใดก็ได้) ----
    def pip_install(self, packages):
        pkg_str = " ".join(packages)
        # รันผ่าน cmd จริง ๆ ตามที่ขอ: py -m pip install ...
        cmd = f'py -3.12 -m pip install {pkg_str}'
        result = subprocess.run(
            ["cmd", "/c", cmd],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"ติดตั้งไลบรารีล้มเหลว ({pkg_str}):\n{result.stderr}")

    def install_pip_packages(self):
        self.pip_install(PIP_PACKAGES)

    # ---- ตรวจสอบว่าโปรแกรมรันได้ ----
    def verify_runnable(self, main_file):
        result = subprocess.run(
            ["py", "-3.12", "-c", "import ast; ast.parse(open(r'%s', encoding='utf-8').read())" % main_file],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"ไฟล์โปรแกรมมีปัญหา รันไม่ได้:\n{result.stderr}")

    # ---- สร้าง shortcut บนเดสก์ท็อป ----
    def create_desktop_shortcut(self, main_file, extracted_path=None):
        install_dir = os.path.dirname(main_file)

        # 1) ติดตั้ง pywin32 / winshell ให้ Python 3.12 ที่เพิ่งลงไว้โดยอัตโนมัติ
        self.pip_install(SHORTCUT_PACKAGES)

        # 2) หาไฟล์โลโก้: ให้ความสำคัญกับโลโก้ที่ดาวน์โหลดมาจาก repo GitHub ก่อน
        #    ถ้าใน repo ไม่มีไฟล์โลโก้ ค่อย fallback ไปใช้ตัวที่ฝังมากับ installer.exe เอง
        logo_filename = os.path.basename(APP_LOGO_PATH)
        logo_src = None
        if extracted_path:
            logo_src = self.find_file(extracted_path, logo_filename, required=False)
        if not logo_src:
            fallback = resource_path(APP_LOGO_PATH)
            if os.path.exists(fallback):
                logo_src = fallback

        # copy โลโก้ไปเก็บถาวรไว้ในโฟลเดอร์ที่ติดตั้ง
        # (สำคัญมาก: ถ้าไม่ copy ไอคอนจะหายไปทันทีหลังปิด installer
        #  เพราะไฟล์ต้นฉบับที่แนบมากับ .exe แบบ --onefile จะอยู่ใน temp ชั่วคราวเท่านั้น
        #  ส่วนไฟล์ที่โหลดมาจาก GitHub ก็อาจอยู่คนละที่กับ main_file ถ้า repo มีโฟลเดอร์ย่อย)
        icon_path = ""
        if logo_src:
            icon_dest = os.path.join(install_dir, logo_filename)
            try:
                if os.path.abspath(logo_src) != os.path.abspath(icon_dest):
                    shutil.copyfile(logo_src, icon_dest)
                icon_path = icon_dest
            except Exception:
                icon_path = ""

        # 3) สร้าง shortcut โดยสั่งให้ Python 3.12 (ตัวที่เพิ่งลง pywin32/winshell ไป)
        #    เป็นคนรันโค้ดสร้าง .lnk เอง แทนที่ installer.exe จะ import winshell ตรง ๆ
        #    (ตัว exe เองไม่จำเป็นต้องฝัง winshell มาด้วยตอน build)
        shortcut_script = f'''
import os, winshell
from win32com.client import Dispatch

desktop = winshell.desktop()
shortcut_path = os.path.join(desktop, r"{APP_NAME}.lnk")
shell = Dispatch("WScript.Shell")
shortcut = shell.CreateShortCut(shortcut_path)
shortcut.Targetpath = "pythonw.exe"
shortcut.Arguments = r'"{main_file}"'
shortcut.WorkingDirectory = r"{install_dir}"
icon = r"{icon_path}"
if icon and os.path.exists(icon):
    shortcut.IconLocation = icon
shortcut.save()
'''
        script_path = os.path.join(tempfile.gettempdir(), "make_shortcut.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(shortcut_script)

        result = subprocess.run(
            ["py", "-3.12", script_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"สร้างทางลัดบนเดสก์ท็อปล้มเหลว:\n{result.stderr}")

    # ---- เปิดโปรแกรม ----
    def launch_program(self, main_file):
        subprocess.Popen(["py", "-3.12", main_file], cwd=os.path.dirname(main_file))


def main():
    root = tk.Tk()
    app = InstallerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

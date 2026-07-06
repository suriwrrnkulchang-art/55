"""
install.py — ตัวติดตั้งโปรแกรม (แบบง่าย เข้าใจง่าย)
======================================================
ทำหน้าที่:
  1) ให้ผู้ใช้เลือกโฟลเดอร์ที่จะติดตั้ง
  2) ดาวน์โหลดโปรเจกต์จาก GitHub (zip) แล้วแตกไฟล์ลงโฟลเดอร์นั้น
  3) ติดตั้งไลบรารีที่จำเป็นด้วย pip
  4) สร้างทางลัด (shortcut) บนเดสก์ท็อป
  5) *สำคัญ* บันทึก "ข้อมูลการติดตั้ง" ลงไฟล์ install_info.json
     ไว้ที่ %APPDATA%\\<ชื่อโปรแกรม>\\install_info.json
     -> ไฟล์นี้คือตัวที่ทำให้ uninstall.py หาโปรแกรมเจอเอง
        โดยผู้ใช้ไม่ต้องกรอกอะไรซ้ำเลย

ใช้งานบน Windows เท่านั้น
build เป็น .exe ได้ด้วย:
    pip install pyinstaller
    pyinstaller --onefile --noconsole install.py
"""

import os
import sys
import json
import time
import shutil
import zipfile
import tempfile
import traceback
import threading
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ------------------------------------------------------------------
# ตั้งค่าโปรแกรมของคุณตรงนี้ที่เดียว
# ------------------------------------------------------------------
APP_NAME = "FilterCore"
GITHUB_ZIP_URL = "https://github.com/suriwrrnkulchang-art/master/archive/refs/heads/main.zip"
MAIN_PY_FILE = "main.py"
PIP_PACKAGES = ["numpy", "speechrecognition", "soundfile", "pyaudio", "pywin32", "winshell"]

DEFAULT_INSTALL_DIR = str(Path.home() / APP_NAME)

# ที่เก็บ "ไฟล์บันทึกข้อมูลการติดตั้ง" ให้ uninstall.py มาอ่านทีหลัง
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", tempfile.gettempdir()), APP_NAME)
CONFIG_FILE = os.path.join(CONFIG_DIR, "install_info.json")

# ปลอมตัวเป็นเบราว์เซอร์ตอนดาวน์โหลด กัน GitHub/proxy ตอบ 404 ปลอม
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


# ==================================================================
# ฟังก์ชันช่วยเหลือทั่วไป
# ==================================================================

def download_file(url, dest_path, tries=3):
    """ดาวน์โหลดไฟล์ ใส่ User-Agent เสมอ + ลองใหม่อัตโนมัติถ้าพลาด"""
    last_err = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp, open(dest_path, "wb") as f:
                shutil.copyfileobj(resp, f)
            return
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            last_err = e
            time.sleep(2)
    raise RuntimeError(f"ดาวน์โหลดไม่สำเร็จ: {last_err}")


def find_file(base_dir, filename):
    """หาไฟล์ชื่อ filename ในโฟลเดอร์ base_dir (ค้นทุกโฟลเดอร์ย่อย)"""
    for root_dir, _, files in os.walk(base_dir):
        if filename in files:
            return os.path.join(root_dir, filename)
    return None


def get_python_exe():
    """หา python.exe ที่ใช้งานได้บนเครื่อง (ใช้ตัวที่รันโปรแกรมนี้อยู่ก็ได้ ง่ายสุด)"""
    return sys.executable


def get_pythonw_exe(python_exe):
    """หา pythonw.exe (ตัวไม่มีหน้าต่างดำ) ที่อยู่โฟลเดอร์เดียวกับ python.exe"""
    folder = os.path.dirname(python_exe)
    pyw = os.path.join(folder, "pythonw.exe")
    return pyw if os.path.exists(pyw) else python_exe


def save_install_info(data: dict):
    """บันทึกข้อมูลการติดตั้งไว้ให้ uninstall.py อ่านต่ออัตโนมัติ"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ==================================================================
# หน้าต่างโปรแกรมติดตั้ง
# ==================================================================

class InstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"ติดตั้ง {APP_NAME}")
        self.root.geometry("460x300")
        self.root.resizable(False, False)

        self.install_dir = tk.StringVar(value=DEFAULT_INSTALL_DIR)
        self._build_ui()

    def _build_ui(self):
        tk.Label(self.root, text=f"ตัวติดตั้ง {APP_NAME}", font=("Segoe UI", 15, "bold")).pack(pady=(20, 10))

        row = tk.Frame(self.root)
        row.pack(fill="x", padx=20)
        tk.Label(row, text="ติดตั้งที่:").pack(anchor="w")
        row2 = tk.Frame(row)
        row2.pack(fill="x")
        tk.Entry(row2, textvariable=self.install_dir).pack(side="left", fill="x", expand=True)
        tk.Button(row2, text="เลือก...", command=self._choose_dir).pack(side="left", padx=5)

        self.status = tk.Label(self.root, text="รอเริ่มการติดตั้ง...", anchor="w")
        self.status.pack(fill="x", padx=20, pady=(25, 5))

        self.progress = ttk.Progressbar(self.root, length=400, mode="determinate")
        self.progress.pack(padx=20, pady=5)

        self.btn = tk.Button(self.root, text="เริ่มติดตั้ง", bg="#2d7ff9", fg="white",
                              font=("Segoe UI", 11, "bold"), command=self._start)
        self.btn.pack(pady=20, ipadx=10, ipady=5)

    def _choose_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.install_dir.set(d)

    def _set_status(self, text, pct=None):
        def update():
            self.status.config(text=text)
            if pct is not None:
                self.progress["value"] = pct
        self.root.after(0, update)

    def _error_and_close(self, msg):
        self.root.after(0, lambda: (messagebox.showerror("เกิดข้อผิดพลาด", msg), self.root.destroy()))

    def _done_and_close(self, msg):
        self.root.after(0, lambda: (messagebox.showinfo("สำเร็จ", msg), self.root.destroy()))

    def _start(self):
        self.btn.config(state="disabled")
        threading.Thread(target=self._run, daemon=True).start()

    # ---------------- ขั้นตอนติดตั้งจริง ----------------
    def _run(self):
        try:
            install_dir = self.install_dir.get().strip()
            if not install_dir:
                raise ValueError("กรุณาเลือกโฟลเดอร์ติดตั้ง")
            os.makedirs(install_dir, exist_ok=True)

            # 1) ดาวน์โหลดจาก GitHub
            self._set_status("กำลังดาวน์โหลดโปรแกรม...", 15)
            zip_path = os.path.join(tempfile.gettempdir(), "project.zip")
            download_file(GITHUB_ZIP_URL, zip_path)

            if not zipfile.is_zipfile(zip_path):
                raise RuntimeError("ไฟล์ที่ดาวน์โหลดมาไม่ใช่ zip ที่ถูกต้อง (ลิงก์อาจผิด หรือเน็ตมีปัญหา)")

            self._set_status("กำลังแตกไฟล์...", 40)
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(install_dir)
            os.remove(zip_path)

            main_file = find_file(install_dir, MAIN_PY_FILE)
            if not main_file:
                raise RuntimeError(f"หาไฟล์ {MAIN_PY_FILE} ไม่พบหลังแตกไฟล์")

            # 2) ติดตั้งไลบรารีที่จำเป็น
            self._set_status("กำลังติดตั้งไลบรารีที่จำเป็น...", 60)
            python_exe = get_python_exe()
            result = subprocess.run(
                [python_exe, "-m", "pip", "install", "--upgrade", *PIP_PACKAGES],
                capture_output=True, text=True, creationflags=CREATE_NO_WINDOW
            )
            if result.returncode != 0:
                raise RuntimeError(f"ติดตั้งไลบรารีล้มเหลว:\n{result.stderr}")

            # 3) สร้างทางลัดบนเดสก์ท็อป
            self._set_status("กำลังสร้างทางลัดบนเดสก์ท็อป...", 80)
            pythonw_exe = get_pythonw_exe(python_exe)
            shortcut_path = self._create_shortcut(python_exe, pythonw_exe, main_file, install_dir)

            # 4) บันทึกข้อมูลการติดตั้ง (ให้ uninstall.py อ่านต่ออัตโนมัติ)
            save_install_info({
                "app_name": APP_NAME,
                "install_dir": install_dir,
                "main_file": main_file,
                "shortcut_path": shortcut_path,
                "python_exe": python_exe,
                "pip_packages": PIP_PACKAGES,
                "installed_at": datetime.now().isoformat(timespec="seconds"),
            })

            # 5) เปิดโปรแกรมทันที (ไม่โชว์หน้าต่างดำ)
            self._set_status("ติดตั้งเสร็จสมบูรณ์! กำลังเปิดโปรแกรม...", 100)
            log_path = os.path.join(install_dir, "run_log.txt")
            with open(log_path, "w", encoding="utf-8") as log:
                clean_env = os.environ.copy()
                clean_env.pop("TCL_LIBRARY", None)  # กัน error Tcl version conflict
                clean_env.pop("TK_LIBRARY", None)
                clean_env.pop("PYTHONHOME", None)
                subprocess.Popen(
                    [pythonw_exe, main_file], cwd=install_dir,
                    stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW, env=clean_env,
                )

            self._done_and_close(f"ติดตั้ง {APP_NAME} เรียบร้อยแล้ว")

        except Exception as e:
            traceback.print_exc()
            self._error_and_close(str(e))

    def _create_shortcut(self, python_exe, pythonw_exe, main_file, install_dir):
        """สร้าง .lnk บนเดสก์ท็อป โดยใช้ pywin32/winshell ที่ติดตั้งไปแล้ว"""
        script = f'''
import os, winshell
from win32com.client import Dispatch
desktop = winshell.desktop()
path = os.path.join(desktop, r"{APP_NAME}.lnk")
shell = Dispatch("WScript.Shell")
sc = shell.CreateShortCut(path)
sc.Targetpath = r"{pythonw_exe}"
sc.Arguments = r'"{main_file}"'
sc.WorkingDirectory = r"{install_dir}"
sc.save()
print(path)
'''
        tmp_script = os.path.join(tempfile.gettempdir(), "make_shortcut.py")
        with open(tmp_script, "w", encoding="utf-8") as f:
            f.write(script)
        result = subprocess.run(
            [python_exe, tmp_script], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW
        )
        if result.returncode != 0:
            raise RuntimeError(f"สร้างทางลัดล้มเหลว:\n{result.stderr}")
        return result.stdout.strip()


def main():
    root = tk.Tk()
    InstallerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

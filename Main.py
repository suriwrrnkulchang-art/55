"""
Custom App Installer
=====================
GUI installer ที่:
  - ใส่โลโก้ / ชื่อโปรแกรมได้ (แก้ตัวแปรด้านล่าง หรือทำเป็น config)
  - มีหน้าติดตั้งพร้อม progress bar + สถานะ
  - ให้เลือกโฟลเดอร์ปลายทางที่จะติดตั้ง
  - ดาวน์โหลดโปรเจกต์จาก GitHub (zip)
  - เช็ค/ติดตั้ง Python 3.12 ถ้ายังไม่มี (ขอ confirm จากผู้ใช้ก่อน)
  - รันคำสั่งติดตั้ง pip package ผ่าน cmd (subprocess)
  - รันไฟล์ .py หลักหลังติดตั้งเสร็จ "ผ่าน cmd" (ตามที่ main.py ของโปรเจกต์ต้องการ)
    + สร้าง shortcut บนเดสก์ท็อป
  - ถ้าขั้นตอนไหน error จะแจ้งเตือนแล้วปิดโปรแกรม

ใช้งานได้บน Windows เท่านั้น (ใช้ py launcher, cmd.exe, .lnk shortcut, pywin32/winshell)

หลังจากแก้โค้ดตามต้องการแล้ว ให้แปลงเป็น .exe ด้วยคำสั่ง เช่น:
    pip install pyinstaller
    pyinstaller --onefile --noconsole --icon=logo.ico --add-data "logo.ico;." main.py

--------------------------------------------------------------------
[แก้ไขล่าสุด] ปัญหาเดิม: ดาวน์โหลดจาก GitHub ได้ HTTP 404 / "File is not a zip file"
สาเหตุที่แท้จริง: urllib.request.urlretrieve() ไม่ส่ง User-Agent header
  -> บาง edge/CDN ของ GitHub หรือ proxy/แอนตี้ไวรัสบนเครื่องผู้ใช้ปฏิเสธ
     request ที่ไม่มี User-Agent แล้วตอบกลับเป็นหน้า error (HTML/404)
     แทนที่จะเป็นไฟล์ zip จริง ทำให้ zipfile.ZipFile() พังตอน extract
วิธีแก้ในไฟล์นี้:
  1) เปลี่ยนไปใช้ urllib.request.Request + urlopen พร้อมใส่ User-Agent header
  2) เพิ่ม retry (ลองใหม่อัตโนมัติ 3 ครั้งก่อนยอมแพ้)
  3) เช็ค zipfile.is_zipfile() ก่อน extract เสมอ ถ้าไม่ใช่ zip จริง
     จะโชว์ error message ที่บอกสาเหตุชัดเจน (เช่น เนื้อหาที่ได้รับจริงๆ คืออะไร)
     แทนที่จะขึ้นแค่ "File is not a zip file" เฉยๆ
--------------------------------------------------------------------
"""

import os
import sys
import shutil
import zipfile
import subprocess
import tempfile
import traceback
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ------------------------------------------------------------------
# ตั้งค่าตรงนี้ตามโปรแกรมของคุณ (จุดที่ "เปลี่ยนโลโก้ได้ เปลี่ยนชื่อได้")
# ------------------------------------------------------------------
APP_NAME = "FilterCore"
APP_LOGO_PATH = "logo.ico"
GITHUB_ZIP_URL = "https://github.com/suriwrrnkulchang-art/master/archive/refs/heads/main.zip"
MAIN_PY_FILE = "main.py"
PYTHON_VERSION = "3.12.4"
PIP_PACKAGES = ["numpy", "speechrecognition", "soundfile", "pyaudio"]
SHORTCUT_PACKAGES = ["pywin32", "winshell"]

DEFAULT_INSTALL_DIR = str(Path.home() / APP_NAME)

# ตัวเบราว์เซอร์ปลอมส่งไปกับ request ทุกครั้งที่ติดต่อ GitHub / python.org
# กัน 404/403 ปลอมจาก edge บางตัวที่ block request ที่ไม่มี User-Agent
HTTP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

DOWNLOAD_MAX_RETRIES = 3
DOWNLOAD_RETRY_DELAY_SEC = 2

# ซ่อนหน้าต่าง cmd ดำๆ ตอนรันคำสั่งเบื้องหลัง (ไม่ใช้กับตอนเปิดโปรแกรมสุดท้ายที่ตั้งใจให้เห็น cmd)
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _quote_if_needed(path):
    """
    Windows quirk: ถ้า quote ชื่อ executable ที่ไม่มี path/extension (เช่น "py")
    cmd.exe จะไม่ทำ PATHEXT lookup (ที่แปลง py -> py.exe) ทำให้หา command ไม่เจอ
    -> quote เฉพาะตอนที่ path มีช่องว่างจริงๆ (เช่น "C:\\Program Files\\...")
    """
    return f'"{path}"' if " " in path else path


def resource_path(relative_path):
    """หาพาธไฟล์ที่แนบมากับตัว exe ทั้งตอนรันเป็น .py และตอน build ด้วย PyInstaller"""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def _download_with_headers(url, dest_path, progress_hook=None):
    """
    ดาวน์โหลดไฟล์โดยใส่ User-Agent header เสมอ (ต่างจาก urlretrieve เดิมที่ไม่ใส่)
    รองรับ progress callback รูปแบบเดียวกับ reporthook ของ urlretrieve:
        progress_hook(block_num, block_size, total_size)
    """
    req = urllib.request.Request(url, headers={"User-Agent": HTTP_USER_AGENT})
    block_size = 8192
    with urllib.request.urlopen(req, timeout=30) as response:
        total_size = int(response.headers.get("Content-Length", 0))
        downloaded = 0
        block_num = 0
        with open(dest_path, "wb") as out_file:
            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                out_file.write(buffer)
                downloaded += len(buffer)
                block_num += 1
                if progress_hook:
                    progress_hook(block_num, block_size, total_size)


def _download_with_retry(url, dest_path, progress_hook=None, max_retries=DOWNLOAD_MAX_RETRIES):
    """
    เรียก _download_with_headers ซ้ำสูงสุด max_retries ครั้งถ้าเจอปัญหาเน็ตชั่วคราว
    (HTTP 404/403/5xx บางทีเป็นปัญหาแค่ชั่วขณะจาก edge/CDN ไม่ใช่ปัญหาถาวรเสมอไป)
    คืนค่า exception สุดท้ายถ้าล้มเหลวครบทุกครั้ง (raise ออกไป)
    """
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            _download_with_headers(url, dest_path, progress_hook)
            return
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            last_error = e
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
            if attempt < max_retries:
                time.sleep(DOWNLOAD_RETRY_DELAY_SEC)
    raise last_error


class InstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"ติดตั้ง {APP_NAME}")
        self.root.geometry("480x360")
        self.root.resizable(False, False)

        logo_src = resource_path(APP_LOGO_PATH)
        if os.path.exists(logo_src):
            try:
                self.root.iconbitmap(logo_src)
            except Exception:
                pass

        self.install_dir = tk.StringVar(value=DEFAULT_INSTALL_DIR)
        self._python_cmd_cache = None  # cache (full_path_or_exe, [extra_args])
        self._build_ui()

    # ---------------- UI ----------------
    def _build_ui(self):
        title = tk.Label(self.root, text=f"ตัวติดตั้ง {APP_NAME}", font=("Segoe UI", 16, "bold"))
        title.pack(pady=(20, 5))

        subtitle = tk.Label(self.root, text="กด 'เริ่มติดตั้ง' เพื่อดาวน์โหลดและติดตั้งโปรแกรม")
        subtitle.pack(pady=(0, 15))

        frame_path = tk.Frame(self.root)
        frame_path.pack(fill="x", padx=20)
        tk.Label(frame_path, text="ตำแหน่งติดตั้ง:").pack(anchor="w")
        path_row = tk.Frame(frame_path)
        path_row.pack(fill="x")
        tk.Entry(path_row, textvariable=self.install_dir).pack(side="left", fill="x", expand=True)
        tk.Button(path_row, text="เลือก...", command=self.choose_dir).pack(side="left", padx=5)

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

    # ---- ทุกอย่างที่แตะ Tk widget จากเธรดพื้นหลัง ต้องผ่าน root.after เท่านั้น ----
    def set_status(self, text, percent=None):
        def _update():
            self.status_label.config(text=text)
            if percent is not None:
                self.progress["value"] = percent
        self.root.after(0, _update)

    def show_error_and_close(self, message):
        def _do():
            messagebox.showerror("เกิดข้อผิดพลาด", message)
            self.root.destroy()
        self.root.after(0, _do)

    def show_info_and_close(self, message):
        def _do():
            messagebox.showinfo("สำเร็จ", message)
            self.root.destroy()
        self.root.after(0, _do)

    def ask_confirm_from_thread(self, title, message):
        """ขอ yes/no จากผู้ใช้ แต่เรียกจากเธรดพื้นหลัง ต้อง block รอผลลัพธ์"""
        result = {}
        event = threading.Event()

        def _ask():
            result["value"] = messagebox.askyesno(title, message)
            event.set()

        self.root.after(0, _ask)
        event.wait()
        return result.get("value", False)

    # ---------------- Logic ----------------
    def start_install_thread(self):
        self.install_btn.config(state="disabled")
        t = threading.Thread(target=self.run_install, daemon=True)
        t.start()

    def run_install(self):
        try:
            target_dir = self.install_dir.get().strip()
            if not target_dir:
                raise ValueError("กรุณาระบุตำแหน่งติดตั้ง")
            os.makedirs(target_dir, exist_ok=True)

            self.set_status("กำลังตรวจสอบ Python...", 5)
            if not self.check_python():
                proceed = self.ask_confirm_from_thread(
                    "ติดตั้ง Python",
                    f"ไม่พบ Python {PYTHON_VERSION} บนเครื่องนี้\n"
                    "โปรแกรมจะดาวน์โหลดและติดตั้งให้อัตโนมัติ ต้องการดำเนินการต่อหรือไม่?"
                )
                if not proceed:
                    raise RuntimeError("ผู้ใช้ยกเลิกการติดตั้ง Python")
                self.set_status("กำลังดาวน์โหลด Python...", 10)
                self.install_python()

            self.set_status("กำลังดาวน์โหลดไฟล์จาก GitHub...", 30)
            extracted_path = self.download_and_extract(target_dir)

            self.set_status("กำลังติดตั้งไลบรารีที่จำเป็น...", 55)
            self.install_pip_packages()

            self.set_status("กำลังตรวจสอบโปรแกรม...", 80)
            main_file = self.find_main_file(extracted_path)
            self.verify_runnable(main_file)

            self.set_status("กำลังสร้างทางลัดบนเดสก์ท็อป...", 90)
            self.create_desktop_shortcut(main_file, extracted_path)

            self.set_status("ติดตั้งเสร็จสมบูรณ์! กำลังเปิดโปรแกรม...", 100)
            self.launch_program(main_file)

            self.show_info_and_close(f"ติดตั้ง {APP_NAME} เรียบร้อยแล้ว")

        except Exception as e:
            traceback.print_exc()
            self.show_error_and_close(f"การติดตั้งล้มเหลว:\n{e}")

    # ---- ตำแหน่งที่ตัวติดตั้งของ python.org จะวาง python.exe ไว้จริง ๆ
    #      สำหรับ per-user install (InstallAllUsers=0) เช่น
    #      C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe
    #      คำนวณจาก major.minor ของ PYTHON_VERSION เพื่อไม่ต้อง hardcode ----
    def _python_major_minor_tag(self):
        parts = PYTHON_VERSION.split(".")
        return f"{parts[0]}{parts[1]}"  # "3.12.4" -> "312"

    def python_install_dir(self):
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            return None
        return os.path.join(
            local_appdata, "Programs", "Python", f"Python{self._python_major_minor_tag()}"
        )

    def find_known_python312(self):
        """
        หา python.exe ของเวอร์ชันที่เราติดตั้งเอง จากตำแหน่งติดตั้งมาตรฐาน
        โดยไม่พึ่ง PATH หรือ py launcher เลย -> เชื่อถือได้แม้เพิ่งติดตั้งเสร็จใหม่ ๆ
        (สาเหตุหลักที่ของเดิมพังคือ: หลังติดตั้ง python เสร็จ ตัวโปรเซสของ installer
        ที่รันอยู่ยังใช้ PATH เก่าค้างอยู่ ทำให้ 'py -3.12'/'python' หาไม่เจอ
        ทั้งที่ติดตั้งสำเร็จแล้วจริง ๆ)
        """
        install_dir = self.python_install_dir()
        if install_dir:
            exe_path = os.path.join(install_dir, "python.exe")
            if os.path.exists(exe_path):
                return exe_path
        return None

    # ---- หา python ที่ใช้งานได้จริงบนเครื่องนี้ ----
    def get_python_cmd(self):
        if self._python_cmd_cache:
            return self._python_cmd_cache

        # 1) ตำแหน่งติดตั้งมาตรฐานที่เรารู้ล่วงหน้า (เชื่อถือได้สุด ไม่พึ่ง PATH)
        known = self.find_known_python312()
        if known:
            self._python_cmd_cache = (known, [])
            return self._python_cmd_cache

        # 2) py launcher / python บน PATH (กรณีเครื่องมี python อยู่แล้วก่อนหน้า)
        candidates = [("py", ["-3.12"]), ("py", []), ("python", [])]
        for exe, args in candidates:
            try:
                out = subprocess.run(
                    [exe] + args + ["--version"],
                    capture_output=True, text=True,
                    creationflags=CREATE_NO_WINDOW
                )
                if out.returncode == 0:
                    self._python_cmd_cache = (exe, args)
                    return self._python_cmd_cache
            except FileNotFoundError:
                continue
        raise RuntimeError("ไม่พบ Python ที่ใช้งานได้บนเครื่องนี้")

    # ---- Python check/install ----
    def check_python(self):
        if self.find_known_python312():
            return True
        try:
            out = subprocess.run(
                ["py", "-3.12", "--version"],
                capture_output=True, text=True,
                creationflags=CREATE_NO_WINDOW
            )
            return out.returncode == 0
        except FileNotFoundError:
            return False

    def install_python(self):
        url = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-amd64.exe"
        tmp_exe = os.path.join(tempfile.gettempdir(), "python_installer.exe")
        try:
            _download_with_retry(url, tmp_exe, progress_hook=self._make_progress_hook(10, 25))
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            raise RuntimeError(f"ดาวน์โหลด Python ไม่สำเร็จ (เช็คอินเทอร์เน็ต): {e}")

        if not os.path.exists(tmp_exe) or os.path.getsize(tmp_exe) == 0:
            raise RuntimeError("ไฟล์ตัวติดตั้ง Python ที่ดาวน์โหลดมาไม่สมบูรณ์ ลองใหม่อีกครั้ง")

        self.set_status("กำลังติดตั้ง Python (อาจใช้เวลาสักครู่ อย่าปิดโปรแกรม)...", 27)

        install_log = os.path.join(tempfile.gettempdir(), "python_install.log")
        result = subprocess.run(
            [
                tmp_exe,
                "/quiet",
                "InstallAllUsers=0",
                "PrependPath=1",
                "Include_launcher=1",
                "Include_test=0",
                f"/log={install_log}",
            ],
        )

        try:
            os.remove(tmp_exe)
        except OSError:
            pass

        # exit code 0 = สำเร็จ, 3010 = สำเร็จแต่ต้องรีสตาร์ทเครื่อง (ยังใช้งานต่อได้ทันทีในกรณีส่วนใหญ่)
        if result.returncode not in (0, 3010):
            raise RuntimeError(
                f"ติดตั้ง Python ไม่สำเร็จ (exit code {result.returncode})\n"
                f"ดู log เพิ่มเติมได้ที่: {install_log}"
            )

        # reset cache เพราะเพิ่งลง python ใหม่ แล้วยืนยันว่าหาไฟล์ python.exe เจอจริง ๆ
        # (แทนที่จะเชื่อว่า PATH/py launcher จะพร้อมใช้ทันที ซึ่งเป็นสาเหตุหลักของบั๊กเดิม)
        self._python_cmd_cache = None
        if not self.find_known_python312():
            raise RuntimeError(
                "ติดตั้ง Python เสร็จแล้ว แต่หาไฟล์ python.exe ไม่พบที่ตำแหน่งที่คาดไว้\n"
                f"({self.python_install_dir()})\n"
                "ลองปิดโปรแกรมนี้แล้วเปิดใหม่อีกครั้ง"
            )

    # ---- progress hook สำหรับดาวน์โหลด ----
    def _make_progress_hook(self, start_pct, end_pct):
        def hook(block_num, block_size, total_size):
            if total_size <= 0:
                return
            downloaded = block_num * block_size
            frac = min(downloaded / total_size, 1.0)
            pct = start_pct + frac * (end_pct - start_pct)
            self.set_status(f"กำลังดาวน์โหลด... {int(frac * 100)}%", pct)
        return hook

    # ---- Download from GitHub ----
    def download_and_extract(self, target_dir):
        tmp_zip = os.path.join(tempfile.gettempdir(), "repo.zip")

        try:
            _download_with_retry(
                GITHUB_ZIP_URL, tmp_zip, progress_hook=self._make_progress_hook(30, 50)
            )
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"ดาวน์โหลดโปรเจกต์จาก GitHub ไม่สำเร็จ (HTTP {e.code}) ลองแล้ว {DOWNLOAD_MAX_RETRIES} ครั้ง\n"
                f"URL: {GITHUB_ZIP_URL}\n"
                "สาเหตุที่เป็นไปได้: อินเทอร์เน็ต/proxy บริษัทบล็อก github.com, "
                "หรือ GitHub จำกัด request ชั่วคราว ลองต่อเน็ตอื่นแล้วรันใหม่"
            )
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"ดาวน์โหลดโปรเจกต์จาก GitHub ไม่สำเร็จ (เช็คอินเทอร์เน็ต/ลิงก์): {e}"
            )

        # เช็คก่อนว่าไฟล์ที่โหลดมาเป็น zip จริง ไม่ใช่หน้า HTML/error page
        if not zipfile.is_zipfile(tmp_zip):
            preview = ""
            try:
                with open(tmp_zip, "rb") as f:
                    preview = f.read(200).decode("utf-8", errors="ignore")
            except OSError:
                pass
            if os.path.exists(tmp_zip):
                os.remove(tmp_zip)
            raise RuntimeError(
                "ไฟล์ที่ดาวน์โหลดมาไม่ใช่ zip ที่ถูกต้อง\n"
                f"URL: {GITHUB_ZIP_URL}\n"
                f"เนื้อหาที่ได้รับ (ตัวอย่าง): {preview[:150]!r}"
            )

        try:
            with zipfile.ZipFile(tmp_zip, "r") as z:
                z.extractall(target_dir)
        except zipfile.BadZipFile:
            raise RuntimeError("ไฟล์ zip เสียหายระหว่างดาวน์โหลด ลองรันโปรแกรมติดตั้งใหม่อีกครั้ง")
        finally:
            if os.path.exists(tmp_zip):
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

    # ---- pip install ผ่าน cmd จริง ----
    def pip_install(self, packages):
        exe, args = self.get_python_cmd()
        pkg_str = " ".join(packages)
        exe_part = _quote_if_needed(exe)
        cmd = f'{exe_part} {" ".join(args)} -m pip install --upgrade {pkg_str}'.strip()
        result = subprocess.run(
            ["cmd", "/c", cmd],
            capture_output=True, text=True,
            creationflags=CREATE_NO_WINDOW
        )
        if result.returncode != 0:
            raise RuntimeError(f"ติดตั้งไลบรารีล้มเหลว ({pkg_str}):\n{result.stderr}")

    def install_pip_packages(self):
        self.pip_install(PIP_PACKAGES)

    # ---- ตรวจสอบว่าโปรแกรมรันได้ (syntax check) ----
    def verify_runnable(self, main_file):
        exe, args = self.get_python_cmd()
        code = "import ast; ast.parse(open(r'%s', encoding='utf-8').read())" % main_file
        result = subprocess.run(
            [exe] + args + ["-c", code],
            capture_output=True, text=True,
            creationflags=CREATE_NO_WINDOW
        )
        if result.returncode != 0:
            raise RuntimeError(f"ไฟล์โปรแกรมมีปัญหา รันไม่ได้:\n{result.stderr}")

    # ---- หา full path ของ pythonw.exe จริงๆ (shortcut ต้องการ path เต็ม ใช้ PATH search แบบ cmd ไม่ได้) ----
    def find_pythonw_path(self, exe, args):
        result = subprocess.run(
            [exe] + args + ["-c", "import sys; print(sys.executable)"],
            capture_output=True, text=True,
            creationflags=CREATE_NO_WINDOW
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError(f"หา path ของ Python ไม่สำเร็จ:\n{result.stderr}")

        python_exe_path = result.stdout.strip()
        python_dir = os.path.dirname(python_exe_path)
        pythonw_path = os.path.join(python_dir, "pythonw.exe")

        if os.path.exists(pythonw_path):
            return pythonw_path
        # บางระบบ (เช่น venv บางแบบ) ไม่มี pythonw.exe แยก -> fallback ไปใช้ python.exe ตัวเต็ม path แทน
        if os.path.exists(python_exe_path):
            return python_exe_path
        raise RuntimeError(f"หาไม่พบทั้ง pythonw.exe และ python.exe ที่ {python_dir}")

    # ---- สร้าง shortcut บนเดสก์ท็อป ----
    def create_desktop_shortcut(self, main_file, extracted_path=None):
        install_dir = os.path.dirname(main_file)

        # ติดตั้ง pywin32 / winshell ให้ python ที่จะใช้สร้าง shortcut
        self.pip_install(SHORTCUT_PACKAGES)

        logo_filename = os.path.basename(APP_LOGO_PATH)
        logo_src = None
        if extracted_path:
            logo_src = self.find_file(extracted_path, logo_filename, required=False)
        if not logo_src:
            fallback = resource_path(APP_LOGO_PATH)
            if os.path.exists(fallback):
                logo_src = fallback

        icon_path = ""
        if logo_src:
            icon_dest = os.path.join(install_dir, logo_filename)
            try:
                if os.path.abspath(logo_src) != os.path.abspath(icon_dest):
                    shutil.copyfile(logo_src, icon_dest)
                icon_path = icon_dest
            except Exception:
                icon_path = ""
        else:
            # ไม่เจอไฟล์โลโก้เลย ทั้งใน repo และในตัว installer เอง
            # -> แจ้งเตือนแทนการเงียบแล้วปล่อยให้ shortcut ใช้ไอคอนดีฟอลต์
            self.set_status(f"ไม่พบไฟล์ {logo_filename} จะใช้ไอคอนเริ่มต้นของ Python แทน", None)

        exe, args = self.get_python_cmd()
        pyw_exe = self.find_pythonw_path(exe, args)

        # ให้ python ตัวที่เพิ่งลง pywin32/winshell รันโค้ดสร้าง .lnk เอง
        shortcut_script = f'''
import os, winshell
from win32com.client import Dispatch

desktop = winshell.desktop()
shortcut_path = os.path.join(desktop, r"{APP_NAME}.lnk")
shell = Dispatch("WScript.Shell")
shortcut = shell.CreateShortCut(shortcut_path)
shortcut.Targetpath = r"{pyw_exe}"
shortcut.Arguments = r'"{main_file}"'
shortcut.WorkingDirectory = r"{install_dir}"
icon = r"{icon_path}"
if icon and os.path.exists(icon):
    shortcut.IconLocation = icon + ",0"
shortcut.save()
'''
        script_path = os.path.join(tempfile.gettempdir(), "make_shortcut.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(shortcut_script)

        result = subprocess.run(
            [exe] + args + [script_path],
            capture_output=True, text=True,
            creationflags=CREATE_NO_WINDOW
        )
        if result.returncode != 0:
            raise RuntimeError(f"สร้างทางลัดบนเดสก์ท็อปล้มเหลว:\n{result.stderr}")

    # ---- เปิดโปรแกรม: ต้องผ่าน cmd จริงๆ ตามที่ main.py ของโปรเจกต์ต้องการ ----
    def launch_program(self, main_file):
        install_dir = os.path.dirname(main_file)
        exe, args = self.get_python_cmd()
        exe_part = _quote_if_needed(exe)
        py_call = f'{exe_part} {" ".join(args)} "{main_file}"'.strip()
        # เปิดหน้าต่าง cmd ใหม่แล้วรันโปรแกรมข้างใน (/k = เปิดค้างไว้ให้เห็น log/error)
        cmd_line = f'start "" cmd /k {py_call}'
        subprocess.Popen(cmd_line, cwd=install_dir, shell=True)


def main():
    root = tk.Tk()
    InstallerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

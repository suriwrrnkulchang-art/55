"""
uninstall.py — ตัวถอนการติดตั้งโปรแกรม (แบบง่าย เข้าใจง่าย)
=============================================================
ทำงานคู่กับ install.py:
  - ตอนติดตั้ง install.py จะบันทึกข้อมูลไว้ที่
        %APPDATA%\\<ชื่อโปรแกรม>\\install_info.json
  - ไฟล์นี้ (uninstall.py) จะ "อ่านไฟล์นั้นเอง" อัตโนมัติ
    ไม่ต้องให้ผู้ใช้กรอกโฟลเดอร์ติดตั้งซ้ำเลย

สิ่งที่ทำตอนถอนการติดตั้ง:
  1) อ่านไฟล์ install_info.json
  2) ถามยืนยันจากผู้ใช้
  3) ลบทางลัดบนเดสก์ท็อป
  4) ลบโฟลเดอร์ที่ติดตั้งโปรแกรมทั้งหมด
  5) (ถามแยก) จะถอนไลบรารีที่ pip ติดตั้งไว้ด้วยหรือไม่
  6) ลบไฟล์ install_info.json ทิ้ง (ถือว่าถอนเสร็จสมบูรณ์)

ใช้งานบน Windows เท่านั้น
build เป็น .exe ได้ด้วย:
    pip install pyinstaller
    pyinstaller --onefile --noconsole uninstall.py
"""

import os
import json
import shutil
import tempfile
import subprocess
import tkinter as tk
from tkinter import messagebox

APP_NAME = "FilterCore"  # ต้องตรงกับ APP_NAME ใน install.py

CONFIG_DIR = os.path.join(os.environ.get("APPDATA", tempfile.gettempdir()), APP_NAME)
CONFIG_FILE = os.path.join(CONFIG_DIR, "install_info.json")

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def load_install_info():
    """อ่านข้อมูลการติดตั้งที่ install.py บันทึกไว้ ถ้าไม่พบไฟล์ = ยังไม่เคยติดตั้ง/ถอนไปแล้ว"""
    if not os.path.exists(CONFIG_FILE):
        return None
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def remove_shortcut(shortcut_path):
    if shortcut_path and os.path.exists(shortcut_path):
        os.remove(shortcut_path)


def remove_install_dir(install_dir):
    if install_dir and os.path.exists(install_dir):
        shutil.rmtree(install_dir, ignore_errors=True)


def uninstall_pip_packages(python_exe, packages):
    if not python_exe or not packages:
        return
    subprocess.run(
        [python_exe, "-m", "pip", "uninstall", "-y", *packages],
        capture_output=True, text=True, creationflags=CREATE_NO_WINDOW
    )


def remove_config():
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)
    if os.path.isdir(CONFIG_DIR) and not os.listdir(CONFIG_DIR):
        os.rmdir(CONFIG_DIR)


def main():
    root = tk.Tk()
    root.withdraw()  # ไม่ต้องมีหน้าต่างหลัก ใช้กล่องข้อความพอ

    info = load_install_info()
    if info is None:
        messagebox.showerror(
            "ไม่พบข้อมูลการติดตั้ง",
            f"ไม่พบไฟล์ข้อมูลการติดตั้งของ {APP_NAME}\n"
            "อาจยังไม่เคยติดตั้ง หรือถอนการติดตั้งไปแล้ว"
        )
        return

    app_name = info.get("app_name", APP_NAME)
    install_dir = info.get("install_dir", "")
    shortcut_path = info.get("shortcut_path", "")
    python_exe = info.get("python_exe", "")
    pip_packages = info.get("pip_packages", [])

    confirm = messagebox.askyesno(
        "ยืนยันการถอนการติดตั้ง",
        f"ต้องการถอนการติดตั้ง {app_name} หรือไม่?\n\n"
        f"จะลบโฟลเดอร์: {install_dir}\n"
        f"และทางลัดบนเดสก์ท็อป"
    )
    if not confirm:
        return

    try:
        remove_shortcut(shortcut_path)
        remove_install_dir(install_dir)

        # ถามแยกเรื่องไลบรารี เพราะไลบรารีบางตัวอาจถูกโปรแกรมอื่นใช้ร่วมด้วย
        if pip_packages:
            remove_libs = messagebox.askyesno(
                "ถอนไลบรารีด้วยหรือไม่",
                "ต้องการถอนไลบรารีที่ติดตั้งไว้สำหรับโปรแกรมนี้ด้วยหรือไม่?\n"
                f"({', '.join(pip_packages)})\n\n"
                "หากไม่แน่ใจว่าโปรแกรมอื่นใช้ไลบรารีเหล่านี้อยู่หรือไม่ ให้เลือก 'ไม่'"
            )
            if remove_libs:
                uninstall_pip_packages(python_exe, pip_packages)

        remove_config()

        messagebox.showinfo("สำเร็จ", f"ถอนการติดตั้ง {app_name} เรียบร้อยแล้ว")

    except Exception as e:
        messagebox.showerror("เกิดข้อผิดพลาด", f"ถอนการติดตั้งไม่สำเร็จ:\n{e}")


if __name__ == "__main__":
    main()

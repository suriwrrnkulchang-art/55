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

✅ เวอร์ชันนี้แก้ไขแล้ว: แต่ละขั้นตอนแยก error handling ของตัวเอง
   ถ้าขั้นตอนใดขั้นตอนหนึ่งพัง (เช่น หา python สำหรับถอน pip ไม่เจอ)
   จะไม่ทำให้ขั้นตอนอื่นที่สำเร็จไปแล้วถูกรายงานว่า "ล้มเหลว" ทั้งหมด

ใช้งานบน Windows เท่านั้น
build เป็น .exe ได้ด้วย:
    pip install pyinstaller
    pyinstaller --onefile --noconsole uninstall.py
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess
import tkinter as tk
from tkinter import messagebox

# 🔧 แก้ปัญหา UnicodeEncodeError ตอน print ข้อความภาษาไทยบน Windows console
if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr is not None:
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

APP_NAME = "FilterCore"  # ต้องตรงกับ APP_NAME ใน install.py

CONFIG_DIR = os.path.join(os.environ.get("APPDATA", tempfile.gettempdir()), APP_NAME)
CONFIG_FILE = os.path.join(CONFIG_DIR, "install_info.json")

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def load_install_info():
    """อ่านข้อมูลการติดตั้งที่ install.py บันทึกไว้ ถ้าไม่พบไฟล์ = ยังไม่เคยติดตั้ง/ถอนไปแล้ว"""
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # ไฟล์เสียหายหรืออ่านไม่ได้ ถือว่าไม่มีข้อมูลการติดตั้งที่ใช้งานได้
        return None


def remove_shortcut(shortcut_path):
    """ลบทางลัดบนเดสก์ท็อป — แยก error ของตัวเอง ไม่ให้ล้มขั้นตอนอื่น"""
    errors = []
    try:
        if shortcut_path and os.path.exists(shortcut_path):
            os.remove(shortcut_path)
    except Exception as e:
        errors.append(f"ลบทางลัดไม่สำเร็จ: {e}")
    return errors


def remove_install_dir(install_dir):
    """ลบโฟลเดอร์ที่ติดตั้ง — แยก error ของตัวเอง ไม่ให้ล้มขั้นตอนอื่น"""
    errors = []
    try:
        if install_dir and os.path.exists(install_dir):
            shutil.rmtree(install_dir, ignore_errors=False)
    except Exception as e:
        errors.append(f"ลบโฟลเดอร์ติดตั้งไม่สำเร็จ: {e}")
    return errors


def uninstall_pip_packages(python_exe, packages):
    """
    ถอนไลบรารีที่ pip ติดตั้งไว้ — แยก error ของตัวเอง
    ตรวจสอบก่อนว่า python_exe มีอยู่จริง ป้องกัน WinError 2 (หาไฟล์ไม่เจอ)
    """
    errors = []
    if not packages:
        return errors

    if not python_exe or not os.path.isfile(python_exe):
        errors.append(
            "ไม่พบตัว Python ที่ใช้ติดตั้งไลบรารีไว้ (อาจถูกลบหรือย้ายเครื่องไปแล้ว) "
            "ข้ามขั้นตอนถอนไลบรารี — โปรแกรมหลักถูกลบเรียบร้อยแล้ว"
        )
        return errors

    try:
        result = subprocess.run(
            [python_exe, "-m", "pip", "uninstall", "-y", *packages],
            capture_output=True, text=True, creationflags=CREATE_NO_WINDOW,
            timeout=120
        )
        if result.returncode != 0:
            errors.append(f"ถอนไลบรารีบางส่วนไม่สำเร็จ (รหัส {result.returncode})")
    except FileNotFoundError:
        errors.append("ไม่พบไฟล์ python ที่ระบุไว้ ข้ามขั้นตอนถอนไลบรารี")
    except subprocess.TimeoutExpired:
        errors.append("ถอนไลบรารีใช้เวลานานเกินไป ข้ามขั้นตอนนี้")
    except Exception as e:
        errors.append(f"ถอนไลบรารีไม่สำเร็จ: {e}")

    return errors


def remove_config():
    """ลบไฟล์ config — แยก error ของตัวเอง"""
    errors = []
    try:
        if os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE)
        if os.path.isdir(CONFIG_DIR) and not os.listdir(CONFIG_DIR):
            os.rmdir(CONFIG_DIR)
    except Exception as e:
        errors.append(f"ลบไฟล์ข้อมูลการติดตั้งไม่สำเร็จ: {e}")
    return errors


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

    # 🔧 รวม error จากทุกขั้นตอน โดยแต่ละขั้นตอนทำงานอิสระจากกัน
    all_errors = []

    all_errors += remove_shortcut(shortcut_path)
    all_errors += remove_install_dir(install_dir)

    # ถามแยกเรื่องไลบรารี เพราะไลบรารีบางตัวอาจถูกโปรแกรมอื่นใช้ร่วมด้วย
    if pip_packages:
        remove_libs = messagebox.askyesno(
            "ถอนไลบรารีด้วยหรือไม่",
            "ต้องการถอนไลบรารีที่ติดตั้งไว้สำหรับโปรแกรมนี้ด้วยหรือไม่?\n"
            f"({', '.join(pip_packages)})\n\n"
            "หากไม่แน่ใจว่าโปรแกรมอื่นใช้ไลบรารีเหล่านี้อยู่หรือไม่ ให้เลือก 'ไม่'"
        )
        if remove_libs:
            all_errors += uninstall_pip_packages(python_exe, pip_packages)

    all_errors += remove_config()

    # แสดงผลลัพธ์สุดท้าย: สำเร็จหรือมีคำเตือนบางส่วน แต่ไม่ทำให้เข้าใจผิดว่า "ล้มเหลวทั้งหมด"
    if not all_errors:
        messagebox.showinfo("สำเร็จ", f"ถอนการติดตั้ง {app_name} เรียบร้อยแล้ว")
    else:
        detail = "\n".join(f"- {err}" for err in all_errors)
        messagebox.showwarning(
            "ถอนการติดตั้งเสร็จสิ้น (มีบางรายการข้าม)",
            f"ถอนการติดตั้ง {app_name} เสร็จสิ้นแล้ว แต่มีบางขั้นตอนที่ข้ามไป:\n\n{detail}"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        try:
            messagebox.showerror("เกิดข้อผิดพลาดร้ายแรง", f"ถอนการติดตั้งไม่สำเร็จ:\n{e}")
        except Exception:
            print(f"เกิดข้อผิดพลาดร้ายแรง: {e}")

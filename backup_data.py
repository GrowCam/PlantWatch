#!/usr/bin/env python3
"""
Daily rotating backup of grow_data.json and sensor_data.db.
Run via cron, e.g. once a day at 03:00. Keeps the last BACKUP_RETENTION_DAYS days.
"""

import os
import shutil
import sqlite3
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, "grow_data.json")
SENSOR_DB = os.path.join(SCRIPT_DIR, "sensor_data.db")
BACKUP_ROOT = os.path.join(SCRIPT_DIR, "backups")

try:
    RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "14"))
except ValueError:
    RETENTION_DAYS = 14


def backup_grow_data(dest_dir: str) -> None:
    if not os.path.exists(DATA_FILE):
        print("[backup] grow_data.json nicht gefunden, überspringe.")
        return
    shutil.copy2(DATA_FILE, os.path.join(dest_dir, "grow_data.json"))
    print("[backup] grow_data.json gesichert.")


def backup_sensor_db(dest_dir: str) -> None:
    if not os.path.exists(SENSOR_DB):
        print("[backup] sensor_data.db nicht gefunden, überspringe.")
        return
    dest_path = os.path.join(dest_dir, "sensor_data.db")
    src_conn = sqlite3.connect(SENSOR_DB)
    dest_conn = sqlite3.connect(dest_path)
    try:
        src_conn.backup(dest_conn)
        print("[backup] sensor_data.db gesichert (hot backup).")
    finally:
        dest_conn.close()
        src_conn.close()


def prune_old_backups() -> None:
    if not os.path.isdir(BACKUP_ROOT):
        return
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    for name in os.listdir(BACKUP_ROOT):
        path = os.path.join(BACKUP_ROOT, name)
        if not os.path.isdir(path):
            continue
        try:
            folder_date = datetime.strptime(name, "%Y-%m-%d")
        except ValueError:
            continue
        if folder_date < cutoff:
            shutil.rmtree(path, ignore_errors=True)
            print(f"[backup] Altes Backup entfernt: {name}")


def main() -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    dest_dir = os.path.join(BACKUP_ROOT, today)
    os.makedirs(dest_dir, exist_ok=True)
    backup_grow_data(dest_dir)
    backup_sensor_db(dest_dir)
    prune_old_backups()


if __name__ == "__main__":
    main()

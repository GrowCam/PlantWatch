#!/usr/bin/env python3
"""
Daily Image Sender Script
Sends the latest timelapse image from /images folder via Telegram
Runs daily at 7AM via cronjob
"""

import os
import re
import sys
import glob
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Telegram Configuration - set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your .env file
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
LOCKFILE = "/tmp/tele.lock"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(SCRIPT_DIR, "images")


def get_latest_image():
    """Find the most recent image in the /images directory"""
    try:
        # Get all jpg files in the images directory
        image_files = glob.glob(os.path.join(IMAGES_DIR, "*.jpg"))
        
        if not image_files:
            print("No images found in /images directory")
            return None
        
        # Sort by modification time (most recent first)
        latest_image = max(image_files, key=os.path.getmtime)
        
        print(f"Latest image found: {latest_image}")
        return latest_image
        
    except Exception as e:
        print(f"Error finding latest image: {str(e)}")
        return None


def send_telegram_photo(image_path):
    """Send photo via Telegram Bot API with formatted caption"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        filename = os.path.basename(image_path)

        # Beispiel-Filenames:
        # 26-05-2025-10:25:07_ForbiddenFruit_23.9C_53.8p.jpg
        # 26-05-2025-10:25:07_ForbiddenFruit_noTemp_noHum.jpg

        name_part = os.path.splitext(filename)[0]
        parts = name_part.split('_')

        if len(parts) < 4:
            print("❌ Dateiname konnte nicht erkannt werden.")
            return False

        timestamp = parts[0]
        grow_name = parts[1].replace("_", " ")
        temp_raw = parts[2]
        hum_raw = parts[3]

        # Datum/Zeit extrahieren
        try:
            date_obj = datetime.strptime(timestamp, "%d-%m-%Y-%H:%M:%S")
            date_display = date_obj.strftime("%d/%m/%Y")
            time_display = date_obj.strftime("%H:%M:%S")
        except Exception:
            date_display = timestamp
            time_display = "??:??:??"

        # Temperatur/Luftfeuchte prüfen
        temp = f"{temp_raw.replace('C', ' °C')}" if "noTemp" not in temp_raw else "nicht verfügbar"
        hum = f"{hum_raw.replace('p', ' %')}" if "noHum" not in hum_raw else "nicht verfügbar"

        # Aktuelle Zeit für „Gesendet am“
        now = datetime.now().strftime("%d/%m/%Y um %H:%M Uhr")

        # 📩 Telegram Caption mit Klima-Infos
        caption = (
            "🌱 <b>Daily Grow Update</b> 📸\n\n"
            f"<b>📅 Datum:</b> {date_display}\n"
            f"<b>🕙 Zeit:</b> {time_display}\n"
            f"<b>🌿 Grow:</b> {grow_name}\n"
            f"<b>🌡 Temperatur:</b> {temp}\n"
            f"<b>💧 Luftfeuchte:</b> {hum}\n\n"
            f"<i>📤 Gesendet am {now}</i>"
        )

        with open(image_path, 'rb') as photo:
            files = {'photo': photo}
            data = {
                'chat_id': CHAT_ID,
                'caption': caption,
                'parse_mode': 'HTML'
            }

            response = requests.post(url, files=files, data=data, timeout=30)

        if response.status_code == 200:
            print("✅ Image sent successfully via Telegram")
            return True
        else:
            print(f"❌ Failed to send image. Status: {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Error sending image via Telegram: {str(e)}")
        return False


def check_configuration():
    """Check if Telegram bot is configured properly"""
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ Please configure your Telegram bot token and chat ID first!")
        print("\nSetup instructions:")
        print("1. Message @BotFather on Telegram")
        print("2. Create a new bot with /newbot command")
        print("3. Copy the bot token to BOT_TOKEN variable")
        print("4. Message @userinfobot to get your chat ID")
        print("5. Copy your chat ID to CHAT_ID variable")
        return False
    return True


def is_locked():
    return os.path.exists(LOCKFILE)

def create_lock():
    with open(LOCKFILE, 'w') as f:
        f.write("locked")

def remove_lock():
    if os.path.exists(LOCKFILE):
        os.remove(LOCKFILE)


def main():
    print("🚀 Starting daily image sender...")

    if not check_configuration():
        sys.exit(1)

    if is_locked():
        print("⏳ tele.py läuft bereits. Abbruch.")
        sys.exit(0)

    create_lock()

    try:
        if not os.path.exists(IMAGES_DIR):
            print(f"❌ Images directory {IMAGES_DIR} does not exist")
            sys.exit(1)

        latest_image = get_latest_image()
        if not latest_image:
            print("❌ No images to send")
            sys.exit(1)

        success = send_telegram_photo(latest_image)
        if success:
            print("✅ Daily image update sent successfully!")
            sys.exit(0)
        else:
            print("❌ Failed to send daily image update")
            sys.exit(1)
    finally:
        remove_lock()


if __name__ == "__main__":
    main()

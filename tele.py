#!/usr/bin/env python3
"""
Daily Image Sender Script
Sends the latest timelapse image from /images folder via Telegram.
Runs daily at 7AM via cronjob.
"""

import os
import sys
import glob
import requests
from datetime import datetime
from dotenv import load_dotenv
from lang import t

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Telegram Configuration - set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your .env file
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
LOCKFILE = "/tmp/tele.lock"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(SCRIPT_DIR, "images")


def get_latest_image():
    """Find the most recent image in the /images directory."""
    try:
        image_files = glob.glob(os.path.join(IMAGES_DIR, "*.jpg"))

        if not image_files:
            print("No images found in /images directory")
            return None

        latest_image = max(image_files, key=os.path.getmtime)
        print(f"Latest image found: {latest_image}")
        return latest_image

    except Exception as e:
        print(f"Error finding latest image: {str(e)}")
        return None


def send_telegram_photo(image_path):
    """Send photo via Telegram Bot API with formatted caption."""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        filename = os.path.basename(image_path)

        # Filename format: 26-05-2025-10:25:07_GrowName_23.9C_53.8p.jpg
        name_part = os.path.splitext(filename)[0]
        parts = name_part.split('_')

        if len(parts) < 4:
            print("❌ Filename format not recognised.")
            return False

        timestamp = parts[0]
        grow_name = parts[1].replace("_", " ")
        temp_raw = parts[2]
        hum_raw = parts[3]

        try:
            date_obj = datetime.strptime(timestamp, "%d-%m-%Y-%H:%M:%S")
            date_display = date_obj.strftime(t("date_format"))
            time_display = date_obj.strftime("%H:%M:%S")
        except Exception:
            date_display = timestamp
            time_display = "??:??:??"

        temp = f"{temp_raw.replace('C', ' °C')}" if "noTemp" not in temp_raw else t("not_available")
        hum = f"{hum_raw.replace('p', ' %')}" if "noHum" not in hum_raw else t("not_available")

        now = datetime.now().strftime(t("datetime_format"))

        caption = (
            f"🌱 <b>{t('daily_update_title')}</b> 📸\n\n"
            f"<b>📅 {t('caption_date')}:</b> {date_display}\n"
            f"<b>🕙 {t('caption_time')}:</b> {time_display}\n"
            f"<b>🌿 {t('caption_grow')}:</b> {grow_name}\n"
            f"<b>🌡 {t('caption_temp')}:</b> {temp}\n"
            f"<b>💧 {t('caption_humidity')}:</b> {hum}\n\n"
            f"<i>📤 {t('tele_caption_sent', dt=now)}</i>"
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
    """Check if Telegram bot is configured properly."""
    if not BOT_TOKEN or not CHAT_ID:
        print(t("tele_not_configured"))
        print("\nSetup instructions:")
        print("1. Message @BotFather on Telegram")
        print("2. Create a new bot with /newbot command")
        print("3. Copy the bot token to TELEGRAM_BOT_TOKEN in .env")
        print("4. Message @userinfobot to get your chat ID")
        print("5. Copy your chat ID to TELEGRAM_CHAT_ID in .env")
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
        print(t("tele_locked"))
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

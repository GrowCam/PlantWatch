#!/usr/bin/env python3

"""
Timelapse camera script for Raspberry Pi
Captures photos and saves them with German timezone timestamps and sequential numbering
Adds SwitchBot Outdoor Thermo-Hygrometer temperature/humidity data to filename
Perfect for monitoring indoor grow tents via cronjobs or Telegram
"""

import os
import sys
import json
import re
import subprocess
import argparse
import asyncio
import math
import sqlite3
import cv2
from datetime import datetime
from zoneinfo import ZoneInfo
from time import sleep
from typing import Dict, Optional, Tuple
from bleak import BleakScanner

# Konfiguration
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grow_data.json")


def load_grow_settings() -> Dict[str, str | int]:
    """Read grow metadata and photo settings from the local data file."""
    default_settings = {
        "grow_name": "Unbekannt",
        "photo_rotation_degrees": 0,
        "timelapse_rotation_degrees": 0,
        "timelapse_enabled": True,
        "timelapse_light_only": False,
        "timelapse_interval_minutes": 30,
        "lights_on_start": os.getenv("LIGHTS_ON_START", "18:01"),
        "lights_on_end": os.getenv("LIGHTS_ON_END", "11:59"),
        "switchbot_mac": os.getenv("SWITCHBOT_MAC", ""),
        "switchbot_scan_timeout": int(os.getenv("SWITCHBOT_SCAN_TIMEOUT", "15") or 15),
        "camera_auto_focus": True,
        "camera_focus": -1,
        "camera_auto_exposure": True,
        "camera_exposure": -1,
        "camera_brightness": -1,
        "camera_contrast": -1,
        "camera_saturation": -1,
        "camera_sharpness": -1,
    }
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            rotation = int(data.get("photo_rotation_degrees", 0) or 0)
            app_settings = data.get("app_settings") if isinstance(data.get("app_settings"), dict) else {}
            timelapse_settings = data.get("timelapse_settings") if isinstance(data.get("timelapse_settings"), dict) else {}
            light_cycle_settings = data.get("light_cycle_settings") if isinstance(data.get("light_cycle_settings"), dict) else {}
            default_settings["grow_name"] = data.get("grow_name", default_settings["grow_name"])
            default_settings["photo_rotation_degrees"] = rotation
            default_settings["timelapse_rotation_degrees"] = int(timelapse_settings.get("rotation_degrees", rotation) or rotation)
            default_settings["timelapse_enabled"] = bool(timelapse_settings.get("enabled", True))
            default_settings["timelapse_light_only"] = bool(timelapse_settings.get("light_only", False))
            default_settings["timelapse_interval_minutes"] = int(timelapse_settings.get("interval_minutes", 30) or 30)
            default_settings["lights_on_start"] = str(light_cycle_settings.get("lights_on_start") or default_settings["lights_on_start"])
            default_settings["lights_on_end"] = str(light_cycle_settings.get("lights_on_end") or default_settings["lights_on_end"])
            default_settings["switchbot_mac"] = str(app_settings.get("switchbot_mac") or default_settings["switchbot_mac"]).upper()
            default_settings["switchbot_scan_timeout"] = int(app_settings.get("switchbot_scan_timeout", default_settings["switchbot_scan_timeout"]) or default_settings["switchbot_scan_timeout"])
            default_settings["camera_auto_focus"] = bool(app_settings.get("camera_auto_focus", True))
            default_settings["camera_auto_exposure"] = bool(app_settings.get("camera_auto_exposure", True))
            for key in ("camera_focus", "camera_exposure", "camera_brightness", "camera_contrast", "camera_saturation", "camera_sharpness"):
                default_settings[key] = int(app_settings.get(key, default_settings[key]) or default_settings[key])
    except Exception as exc:
        print(f"⚠️ Konnte grow_data.json nicht lesen: {exc}")
    return default_settings


GROW_SETTINGS = load_grow_settings()
GROW_NAME = GROW_SETTINGS["grow_name"]
PHOTO_ROTATION_DEGREES = GROW_SETTINGS["photo_rotation_degrees"]
TIMELAPSE_ROTATION_DEGREES = GROW_SETTINGS["timelapse_rotation_degrees"]
TIMELAPSE_ENABLED = bool(GROW_SETTINGS["timelapse_enabled"])
TIMELAPSE_LIGHT_ONLY = bool(GROW_SETTINGS["timelapse_light_only"])
TIMELAPSE_INTERVAL_MINUTES = int(GROW_SETTINGS["timelapse_interval_minutes"])
LIGHTS_ON_START = str(GROW_SETTINGS["lights_on_start"])
LIGHTS_ON_END = str(GROW_SETTINGS["lights_on_end"])
CAMERA_AUTO_FOCUS = bool(GROW_SETTINGS["camera_auto_focus"])
CAMERA_FOCUS = int(GROW_SETTINGS["camera_focus"])
CAMERA_AUTO_EXPOSURE = bool(GROW_SETTINGS["camera_auto_exposure"])
CAMERA_EXPOSURE = int(GROW_SETTINGS["camera_exposure"])
CAMERA_BRIGHTNESS = int(GROW_SETTINGS["camera_brightness"])
CAMERA_CONTRAST = int(GROW_SETTINGS["camera_contrast"])
CAMERA_SATURATION = int(GROW_SETTINGS["camera_saturation"])
CAMERA_SHARPNESS = int(GROW_SETTINGS["camera_sharpness"])

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_IMAGES_DIR = os.path.join(SCRIPT_DIR, "images")  # Für Telegram
TIMELAPSE_IMAGES_DIR = os.path.join(SCRIPT_DIR, "timelapse")  # Für Cron
COUNTER_FILE = os.path.join(SCRIPT_DIR, "counter.json")
SENSOR_DB = os.path.join(SCRIPT_DIR, "sensor_data.db")


def init_sensor_db():
    """Ensure the SQLite store for sensor readings exists."""
    try:
        with sqlite3.connect(SENSOR_DB) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sensor_readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    temperature REAL,
                    humidity REAL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sensor_ts ON sensor_readings(timestamp)"
            )
    except Exception as exc:
        print(f"⚠️ Konnte Sensor-Datenbank nicht initialisieren: {exc}")


def store_sensor_reading(timestamp_iso: str, temperature: float | None, humidity: float | None):
    if temperature is None and humidity is None:
        return
    try:
        with sqlite3.connect(SENSOR_DB) as conn:
            conn.execute(
                "INSERT INTO sensor_readings(timestamp, temperature, humidity) VALUES (?, ?, ?)",
                (timestamp_iso, temperature, humidity),
            )
    except Exception as exc:
        print(f"⚠️ Konnte Sensorwerte nicht speichern: {exc}")


init_sensor_db()

# SwitchBot-Sensor
SWITCHBOT_MAC = str(GROW_SETTINGS["switchbot_mac"])
SENSOR_TIMEOUT = int(GROW_SETTINGS["switchbot_scan_timeout"])  # Sekunden für BLE-Scan

# Lockfile
LOCKFILE = "/tmp/cam.lock"

# Wird im Script dynamisch angepasst
IMAGES_DIR = DEFAULT_IMAGES_DIR


class SwitchBotOutdoorMeterDecoder:
    """
    Decoder for SwitchBot Outdoor Thermo-Hygrometer BLE advertisements.
    """
    
    def __init__(self, mac_address: str):
        self.mac_address = mac_address.upper()
    
    def decode_battery(self, service_data: bytes) -> Optional[int]:
        """Decode battery percentage from service data."""
        if len(service_data) != 3:
            return None
        battery_pct = service_data[2] & 0x7F
        return battery_pct
    
    def decode_humidity(self, manufacturer_data: bytes) -> Optional[int]:
        """Decode humidity percentage from manufacturer data."""
        if len(manufacturer_data) != 12:
            return None
        humidity_pct = manufacturer_data[10] & 0x7F
        return humidity_pct
    
    def decode_temperature(self, manufacturer_data: bytes) -> Optional[float]:
        """Decode temperature from manufacturer data."""
        if len(manufacturer_data) != 12:
            return None
        
        fractional_byte = manufacturer_data[8]
        whole_byte = manufacturer_data[9]
        
        fractional_part = float(fractional_byte & 0x0F) * 0.1
        whole_part = float(whole_byte & 0x7F)
        temperature = fractional_part + whole_part
        
        if not (whole_byte & 0x80):
            temperature = -temperature
            
        return round(temperature, 1)
    
    def decode_ble_advertisement(self, service_data: bytes, manufacturer_data: bytes) -> Dict:
        """Decode complete BLE advertisement data."""
        result = {
            'mac_address': self.mac_address,
            'battery': None,
            'temperature': None,
            'humidity': None,
            'timestamp': None
        }
        
        if service_data and len(service_data) == 3:
            result['battery'] = self.decode_battery(service_data)
        
        if manufacturer_data and len(manufacturer_data) == 12:
            result['temperature'] = self.decode_temperature(manufacturer_data)
            result['humidity'] = self.decode_humidity(manufacturer_data)
        
        return result
    
    @staticmethod
    def calculate_absolute_humidity(temperature: float, humidity: float) -> float:
        """Calculate absolute humidity from temperature and relative humidity."""
        if temperature is None or humidity is None:
            return None
        numerator = 6.112 * math.exp((17.67 * temperature) / (temperature + 243.5)) * humidity * 2.1674
        denominator = 273.15 + temperature
        return round(numerator / denominator, 2)
    
    @staticmethod
    def calculate_dew_point(temperature: float, humidity: float) -> float:
        """Calculate dew point from temperature and relative humidity."""
        if temperature is None or humidity is None:
            return None
        a = 17.67
        b = 243.5
        alpha = ((a * temperature) / (b + temperature)) + math.log(humidity / 100.0)
        dew_point = (b * alpha) / (a - alpha)
        return round(dew_point, 1)
    
    @staticmethod
    def calculate_vapor_pressure_deficit(temperature: float, humidity: float) -> float:
        """Calculate vapor pressure deficit from temperature and relative humidity."""
        if temperature is None or humidity is None:
            return None
        es = 6.112 * math.exp((17.67 * temperature) / (temperature + 243.5))
        vpd = (1.0 - (humidity / 100.0)) * es
        return round(vpd / 10.0, 2)  # Convert from hPa to kPa


class SwitchBotBLEScanner:
    """BLE Scanner for SwitchBot devices."""
    
    def __init__(self, mac_address: str):
        self.decoder = SwitchBotOutdoorMeterDecoder(mac_address)
        self.target_mac = mac_address.upper()
        self.sensor_data = None
        self.found_device = False
        
    def extract_advertisement_data(self, advertisement_data):
        """Extract service and manufacturer data from BLE advertisement."""
        service_data = None
        manufacturer_data = None
        
        if hasattr(advertisement_data, 'service_data') and advertisement_data.service_data:
            for uuid, data in advertisement_data.service_data.items():
                service_data = data
                break
        
        if hasattr(advertisement_data, 'manufacturer_data') and advertisement_data.manufacturer_data:
            for company_id, data in advertisement_data.manufacturer_data.items():
                manufacturer_data = data
                break
                
        return service_data, manufacturer_data
    
    def on_advertisement_received(self, device, advertisement_data):
        """Callback when BLE advertisement is received."""
        if device.address.upper() == self.target_mac:
            self.found_device = True
            service_data, manufacturer_data = self.extract_advertisement_data(advertisement_data)
            
            result = self.decoder.decode_ble_advertisement(service_data, manufacturer_data)
            
            if any(result[key] is not None for key in ['temperature', 'humidity']):
                self.sensor_data = result
                print(f"📡 SwitchBot gefunden!")


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="PlantWatch mit SwitchBot-Sensor und Timelapse-Unterstützung",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python cam.py                     # Sensoren + Foto (Telegram-Modus)
  python cam.py --photo-only        # Nur Foto (Telegram oder Cron)
  python cam.py --sensors-only      # Nur Sensorwerte anzeigen
  python cam.py --photo-only --timelapse   # Foto für Timelapse (Cron-Modus)
        """
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--photo-only', action='store_true', help='Nur Foto aufnehmen (Sensorwerte = "none")')
    group.add_argument('--sensors-only', action='store_true', help='Nur Sensorwerte anzeigen, kein Foto')
    parser.add_argument('--timelapse', action='store_true', help='Speichere Bild im Timelapse-Ordner (für Cron)')

    # NEW: stage argument
    parser.add_argument('--stage', choices=['earlyveg', 'veg', 'earlyflower', 'flower'],
                        help='Pflanzenstadium für VPD-Bewertung')

    return parser.parse_args()


OPTIMAL_VPD = {
    "earlyveg": (0.4, 0.8),
    "veg": (0.8, 1.2),
    "earlyflower": (1.0, 1.4),
    "flower": (1.2, 1.6)
}


def suggest_vpd_adjustment(vpd, stage):
    if stage not in OPTIMAL_VPD or vpd is None:
        return None
    low, high = OPTIMAL_VPD[stage]
    if vpd < low:
        return f"🔼 VPD ist zu niedrig (optimal {low}-{high} kPa). → Senke Luftfeuchtigkeit oder erhöhe Temperatur."
    elif vpd > high:
        return f"🔽 VPD ist zu hoch (optimal {low}-{high} kPa). → Erhöhe Luftfeuchtigkeit oder senke Temperatur."
    else:
        return f"✅ VPD liegt im optimalen Bereich für {stage} ({low}-{high} kPa)."


async def read_switchbot_values(mac=SWITCHBOT_MAC, timeout=SENSOR_TIMEOUT):
    """Read temperature and humidity from SwitchBot via BLE."""
    try:
        print(f"🌡️ Lese SwitchBot-Sensor ({mac})...")
        scanner = SwitchBotBLEScanner(mac)
        
        async with BleakScanner(detection_callback=scanner.on_advertisement_received):
            # Wait for sensor data or timeout
            loop = asyncio.get_running_loop()
            start_time = loop.time()
            while not scanner.sensor_data and (loop.time() - start_time) < timeout:
                await asyncio.sleep(0.5)
        
        if scanner.sensor_data:
            temp = scanner.sensor_data['temperature']
            hum = scanner.sensor_data['humidity']
            return temp, hum
        elif scanner.found_device:
            print("⚠️ SwitchBot gefunden, aber keine gültigen Sensordaten erhalten.")
        else:
            print("⚠️ SwitchBot nicht gefunden. Gerät in Reichweite und aktiv?")
            
    except Exception as e:
        print(f"❌ Fehler beim SwitchBot-Sensorabruf: {e}")
    
    return None, None


def read_switchbot_values_sync(mac=SWITCHBOT_MAC):
    """Synchronous wrapper for the async BLE reading function."""
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, read_switchbot_values(mac))
                return future.result()
        else:
            return asyncio.run(read_switchbot_values(mac))
    except Exception as e:
        print(f"❌ Fehler beim Starten des BLE-Scans: {e}")
        return None, None


def get_german_timestamp():
    now = datetime.now(ZoneInfo("Europe/Berlin"))
    return now.strftime("%d-%m-%Y-%H:%M:%S")


def display_sensor_values(stage=None):
    """Display current sensor readings with calculated values and VPD check."""
    temp, hum = read_switchbot_values_sync()
    print("\n📊 SwitchBot Sensorwerte\n")
    if temp is not None and hum is not None:
        print(f"🌡️ Temperatur: {temp:.1f}°C")
        print(f"💧 Luftfeuchtigkeit: {hum:.1f}%")
        print(f"🕐 Zeitstempel: {get_german_timestamp()}")
        
        decoder = SwitchBotOutdoorMeterDecoder(SWITCHBOT_MAC)
        abs_humidity = decoder.calculate_absolute_humidity(temp, hum)
        dew_point = decoder.calculate_dew_point(temp, hum)
        vpd = decoder.calculate_vapor_pressure_deficit(temp, hum)
        
        print(f"\n📈 Berechnete Werte:")
        print(f"💨 Absolute Luftfeuchtigkeit: {abs_humidity} g/m³")
        print(f"🌊 Taupunkt: {dew_point}°C")
        print(f"📊 VPD (Sättigungsdefizit): {vpd} kPa")
        
        if stage:
            suggestion = suggest_vpd_adjustment(vpd, stage)
            if suggestion:
                print("\n🌱 VPD-Check basierend auf Stadium:")
                print(suggestion)
    else:
        print("❌ Sensorwerte konnten nicht gelesen werden.")


def capture_photo(temp=None, hum=None):
    """Capture a photo with optional sensor data in filename."""
    try:
        print("📸 Starte Fotoaufnahme...")
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            raise RuntimeError("USB-Kamera konnte nicht geöffnet werden (/dev/video0).")

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 2592)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1944)
        apply_camera_settings(cap)
        sleep(1)
        ret, frame = cap.read()
        final_camera_settings = read_camera_settings(cap)
        cap.release()
        if not ret or frame is None:
            raise RuntimeError("Kein Bild von der USB-Kamera erhalten.")

        rotation_base = TIMELAPSE_ROTATION_DEGREES if IMAGES_DIR == TIMELAPSE_IMAGES_DIR else PHOTO_ROTATION_DEGREES
        rotation = rotation_base % 360
        if rotation == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif rotation == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif rotation == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

        now = datetime.now(ZoneInfo("Europe/Berlin"))
        timestamp = now.strftime("%d-%m-%Y-%H:%M:%S")
        safe_grow = GROW_NAME.replace(" ", "_")
        temp_str = f"{temp:.1f}C" if temp is not None else "00.0C"
        hum_str = f"{hum:.1f}p" if hum is not None else "00.0p"
        filename = f"{IMAGES_DIR}/{timestamp}_{safe_grow}_{temp_str}_{hum_str}.jpg"

        if not cv2.imwrite(filename, frame):
            raise RuntimeError("Speichern des Bildes ist fehlgeschlagen.")

        if temp is not None or hum is not None:
            store_sensor_reading(now.isoformat(), temp, hum)

        print(f"✅ Bild gespeichert: {filename}")
        print(f"CAMERA_FINAL_SETTINGS={json.dumps(final_camera_settings, ensure_ascii=True)}")
        return filename
    except Exception as e:
        print(f"❌ Fehler bei Fotoaufnahme: {str(e)}")
        return None


def is_locked():
    return os.path.exists(LOCKFILE)


def create_lock():
    with open(LOCKFILE, 'w') as f:
        f.write("locked")


def remove_lock():
    if os.path.exists(LOCKFILE):
        os.remove(LOCKFILE)


def set_camera_property(cap, prop, value, label):
    try:
        ok = cap.set(prop, value)
        print(f"{'✅' if ok else '⚠️'} Kamera {label}: {value}")
    except Exception as exc:
        print(f"⚠️ Kamera {label} konnte nicht gesetzt werden: {exc}")


def apply_camera_settings(cap):
    set_camera_property(cap, cv2.CAP_PROP_AUTOFOCUS, 1 if CAMERA_AUTO_FOCUS else 0, "Autofokus")
    if not CAMERA_AUTO_FOCUS and CAMERA_FOCUS >= 0:
        set_camera_property(cap, cv2.CAP_PROP_FOCUS, CAMERA_FOCUS, "Fokus")

    if CAMERA_AUTO_EXPOSURE:
        for value in (3, 0.75):
            set_camera_property(cap, cv2.CAP_PROP_AUTO_EXPOSURE, value, "Auto-Belichtung")
    else:
        for value in (1, 0.25):
            set_camera_property(cap, cv2.CAP_PROP_AUTO_EXPOSURE, value, "Manuelle Belichtung")
        if CAMERA_EXPOSURE >= 0:
            set_camera_property(cap, cv2.CAP_PROP_EXPOSURE, CAMERA_EXPOSURE, "Belichtung")

    if CAMERA_BRIGHTNESS >= 0:
        set_camera_property(cap, cv2.CAP_PROP_BRIGHTNESS, CAMERA_BRIGHTNESS, "Helligkeit")
    if CAMERA_CONTRAST >= 0:
        set_camera_property(cap, cv2.CAP_PROP_CONTRAST, CAMERA_CONTRAST, "Kontrast")
    if CAMERA_SATURATION >= 0:
        set_camera_property(cap, cv2.CAP_PROP_SATURATION, CAMERA_SATURATION, "Sättigung")
    if hasattr(cv2, "CAP_PROP_SHARPNESS") and CAMERA_SHARPNESS >= 0:
        set_camera_property(cap, cv2.CAP_PROP_SHARPNESS, CAMERA_SHARPNESS, "Schärfe")


def read_camera_settings(cap):
    def read_prop(prop):
        try:
            value = cap.get(prop)
            if value is None:
                return None
            if isinstance(value, float) and abs(value - round(value)) < 0.001:
                return int(round(value))
            return round(float(value), 3)
        except Exception:
            return None

    def normalize_autofocus(value):
        if value is None:
            return None
        try:
            return float(value) >= 0.5
        except Exception:
            return None

    def normalize_auto_exposure(value):
        if value is None:
            return None
        try:
            numeric = float(value)
        except Exception:
            return None
        if numeric >= 2.0:
            return True
        if numeric <= 1.0:
            return False
        if abs(numeric - 0.75) < 0.2:
            return True
        if abs(numeric - 0.25) < 0.2:
            return False
        return numeric > 0.5

    settings = {
        "camera_auto_focus": normalize_autofocus(read_prop(cv2.CAP_PROP_AUTOFOCUS)),
        "camera_focus": read_prop(cv2.CAP_PROP_FOCUS),
        "camera_auto_exposure": normalize_auto_exposure(read_prop(cv2.CAP_PROP_AUTO_EXPOSURE)),
        "camera_exposure": read_prop(cv2.CAP_PROP_EXPOSURE),
        "camera_brightness": read_prop(cv2.CAP_PROP_BRIGHTNESS),
        "camera_contrast": read_prop(cv2.CAP_PROP_CONTRAST),
        "camera_saturation": read_prop(cv2.CAP_PROP_SATURATION),
        "camera_sharpness": read_prop(cv2.CAP_PROP_SHARPNESS) if hasattr(cv2, "CAP_PROP_SHARPNESS") else None,
    }
    return settings


def parse_clock_time(value: str):
    hour, minute = value.split(":", 1)
    return int(hour), int(minute)


def time_in_window(now_dt: datetime, start_str: str, end_str: str) -> bool:
    start_hour, start_minute = parse_clock_time(start_str)
    end_hour, end_minute = parse_clock_time(end_str)
    start_tuple = (start_hour, start_minute)
    end_tuple = (end_hour, end_minute)
    current_tuple = (now_dt.hour, now_dt.minute)
    if start_tuple == end_tuple:
        return False
    if start_tuple < end_tuple:
        return start_tuple <= current_tuple <= end_tuple
    return current_tuple >= start_tuple or current_tuple <= end_tuple


def latest_timelapse_capture_time() -> Optional[datetime]:
    if not os.path.isdir(TIMELAPSE_IMAGES_DIR):
        return None
    latest_mtime = None
    for name in os.listdir(TIMELAPSE_IMAGES_DIR):
        if not name.lower().endswith(".jpg"):
            continue
        path = os.path.join(TIMELAPSE_IMAGES_DIR, name)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if latest_mtime is None or mtime > latest_mtime:
            latest_mtime = mtime
    if latest_mtime is None:
        return None
    return datetime.fromtimestamp(latest_mtime, tz=ZoneInfo("Europe/Berlin"))


def should_capture_timelapse() -> bool:
    if not TIMELAPSE_ENABLED:
        print("⏭️ Timelapse deaktiviert.")
        return False
    now = datetime.now(ZoneInfo("Europe/Berlin"))
    if TIMELAPSE_LIGHT_ONLY and not time_in_window(now, LIGHTS_ON_START, LIGHTS_ON_END):
        print("⏭️ Timelapse nur bei Licht an aktiv.")
        return False
    latest = latest_timelapse_capture_time()
    if latest is not None:
        elapsed_seconds = (now - latest).total_seconds()
        if elapsed_seconds < TIMELAPSE_INTERVAL_MINUTES * 60:
            print(f"⏭️ Timelapse-Intervall noch nicht erreicht ({int(elapsed_seconds // 60)} / {TIMELAPSE_INTERVAL_MINUTES} min).")
            return False
    return True


def main():
    global IMAGES_DIR

    args = parse_arguments()

    # Zielordner wählen
    IMAGES_DIR = TIMELAPSE_IMAGES_DIR if args.timelapse else DEFAULT_IMAGES_DIR
    ensure_images_directory()

    if args.timelapse and not should_capture_timelapse():
        return

    if args.sensors_only:
        display_sensor_values(stage=args.stage)
        return

    if not args.sensors_only and is_locked():
        print("⏳ cam.py läuft bereits. Abbruch.")
        sys.exit(0)

    create_lock()

    try:
        if args.photo_only:
            capture_photo()
        else:
            temp, hum = read_switchbot_values_sync()

            # Nur im Timelapse-Modus bis zu 3 Versuche bei fehlenden Sensorwerten
            if args.timelapse:
                attempts = 1
                while (temp is None or hum is None) and attempts < 3:
                    print(f"🔄 Sensorwerte fehlen – Versuch {attempts + 1}/3 in 5s...")
                    sleep(5)
                    temp, hum = read_switchbot_values_sync()
                    attempts += 1

            if temp is None or hum is None:
                print("⚠️ Sensorwerte fehlen – setze Temperatur/Luftfeuchtigkeit auf 0.0.")
                temp = 0.0 if temp is None else temp
                hum = 0.0 if hum is None else hum

            capture_photo(temp, hum)

    except KeyboardInterrupt:
        print("\nℹ️ Vom Benutzer abgebrochen")
    except Exception as e:
        print(f"❌ Unerwarteter Fehler: {e}")
    finally:
        remove_lock()


def ensure_images_directory():
    if not os.path.exists(IMAGES_DIR):
        try:
            os.makedirs(IMAGES_DIR)
            print(f"📁 Ordner erstellt: {IMAGES_DIR}")
        except PermissionError:
            print(f"❌ Keine Berechtigung für {IMAGES_DIR}")
            sys.exit(1)


if __name__ == "__main__":
    main()

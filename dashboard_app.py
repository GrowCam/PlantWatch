#!/usr/bin/env python3
"""Local PlantWatch dashboard with Telegram-integrated controls."""

from __future__ import annotations

import glob
import json
import math
import os
import html
import re
import sqlite3
import subprocess
import threading
import time
import traceback
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, Any, List
from collections import deque

import requests

try:
    import cv2  # type: ignore
except Exception:
    cv2 = None

try:
    import paho.mqtt.client as mqtt  # type: ignore
except Exception:
    mqtt = None

from flask import Flask, jsonify, render_template, request, send_file, abort

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, "grow_data.json")
ENV_FILE = os.path.join(SCRIPT_DIR, ".env")
IMAGES_DIR = os.path.join(SCRIPT_DIR, "images")
BOT_LOG_FILE = os.path.join(SCRIPT_DIR, "bot_log.txt")
CHECK_INTERVAL_DAYS = 3
TIMELAPSE_DIRS = [
    os.path.join(SCRIPT_DIR, "timelapse"),
    IMAGES_DIR,
]
TIMELAPSE_ONLY_DIRS = [
    os.path.join(SCRIPT_DIR, "timelapse"),
]
PHOTO_DIRS = list(dict.fromkeys(TIMELAPSE_DIRS))
SENSOR_DB = os.path.join(SCRIPT_DIR, "sensor_data.db")
CAM_LOG_FILE = os.path.join(SCRIPT_DIR, "cam_timelapse.log")
CAM_SCRIPT = os.path.join(SCRIPT_DIR, "cam.py")
TL_SCRIPT = os.path.join(SCRIPT_DIR, "tl.py")
TIMELAPSE_VIDEO_FILE = os.path.join(SCRIPT_DIR, "timelapse", "video", "timelapse.mp4")
VENV_PYTHON = os.path.join(SCRIPT_DIR, ".venv", "bin", "python")

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600  # cache static files for 1 hour

TRANSLATIONS = {
    "nav_dashboard": {"de": "Dashboard", "en": "Dashboard"},
    "nav_fertilizer": {"de": "Dünger", "en": "Fertilizer"},
    "nav_watering": {"de": "Bewässerung", "en": "Watering"},
    "nav_climate": {"de": "Klima", "en": "Climate"},
    "nav_power": {"de": "Verbrauch", "en": "Power"},
    "nav_light": {"de": "Licht", "en": "Light"},
    "nav_timelapse": {"de": "Timelapse", "en": "Timelapse"},
    "nav_settings": {"de": "Einstellungen", "en": "Settings"},
    "weekly_summary_enabled": {"de": "Wochenbericht (Telegram)", "en": "Weekly digest (Telegram)"},
    "weekly_summary_time": {"de": "Sendezeit (Mo.)", "en": "Send time (Mon.)"},
    "dark_mode": {"de": "Dark Mode", "en": "Dark Mode"},
    "settings_title": {"de": "Einstellungen", "en": "Settings"},
    "settings_intro": {"de": "Sprache, Layout und persönliche UI-Vorlieben.", "en": "Language, layout and personal UI preferences."},
    "language": {"de": "Sprache", "en": "Language"},
    "language_de": {"de": "Deutsch", "en": "German"},
    "language_en": {"de": "Englisch", "en": "English"},
    "datetime_format": {"de": "Datums- & Zeitformat", "en": "Date & time format"},
    "datetime_eu": {"de": "Europa (TT.MM.JJJJ 24h)", "en": "Europe (DD.MM.YYYY 24h)"},
    "datetime_us": {"de": "USA (MM/DD/YYYY 12h)", "en": "US (MM/DD/YYYY 12h)"},
    "datetime_iso": {"de": "ISO (YYYY-MM-DD 24h)", "en": "ISO (YYYY-MM-DD 24h)"},
    "measurement_system": {"de": "Maßsystem", "en": "Measurement system"},
    "metric": {"de": "Metrisch (ml/L, g/L)", "en": "Metric (ml/L, g/L)"},
    "imperial": {"de": "Imperial (fl oz/gal, oz/gal)", "en": "Imperial (fl oz/gal, oz/gal)"},
    "temperature_unit": {"de": "Temperatur", "en": "Temperature"},
    "currency": {"de": "Währung", "en": "Currency"},
    "currency_eur": {"de": "Euro (EUR)", "en": "Euro (EUR)"},
    "currency_usd": {"de": "US Dollar (USD)", "en": "US Dollar (USD)"},
    "currency_gbp": {"de": "Pfund (GBP)", "en": "Pound (GBP)"},
    "currency_custom": {"de": "Benutzerdefiniert", "en": "Custom"},
    "currency_custom_value": {"de": "Währung / Symbol", "en": "Currency / symbol"},
    "celsius": {"de": "Celsius (°C)", "en": "Celsius (°C)"},
    "fahrenheit": {"de": "Fahrenheit (°F)", "en": "Fahrenheit (°F)"},
    "compact_mode": {"de": "Kompakter Modus", "en": "Compact mode"},
    "reduce_motion": {"de": "Weniger Bewegung", "en": "Reduce motion"},
    "appearance_theme": {"de": "Farbschema", "en": "Appearance"},
    "theme_dark_blue": {"de": "Dunkel Blau", "en": "Dark Blue"},
    "theme_dark_grey": {"de": "Dunkel Grau", "en": "Dark Grey"},
    "theme_light": {"de": "Hell", "en": "Light"},
    "accent_theme": {"de": "Akzentfarbe", "en": "Accent theme"},
    "accent_preset": {"de": "Akzent-Preset", "en": "Accent preset"},
    "accent_teal": {"de": "Teal", "en": "Teal"},
    "accent_sunset": {"de": "Sunset", "en": "Sunset"},
    "accent_mint": {"de": "Mint", "en": "Mint"},
    "accent_ocean": {"de": "Ocean", "en": "Ocean"},
    "accent_rose": {"de": "Rose", "en": "Rose"},
    "accent_gold": {"de": "Gold", "en": "Gold"},
    "accent_lime": {"de": "Lime", "en": "Lime"},
    "select_preset": {"de": "Preset wählen", "en": "Choose preset"},
    "accent_primary": {"de": "Primärfarbe", "en": "Primary color"},
    "accent_secondary": {"de": "Sekundärfarbe", "en": "Secondary color"},
    "telegram_settings": {"de": "Telegram", "en": "Telegram"},
    "telegram_enabled": {"de": "Telegram aktiv", "en": "Telegram enabled"},
    "telegram_bot_token": {"de": "Bot-Token", "en": "Bot token"},
    "telegram_chat_id": {"de": "Chat-ID", "en": "Chat ID"},
    "show_secret": {"de": "Anzeigen", "en": "Show"},
    "hide_secret": {"de": "Verbergen", "en": "Hide"},
    "edit_layout": {"de": "Layout bearbeiten", "en": "Edit layout"},
    "save_layout": {"de": "Layout speichern", "en": "Save layout"},
    "telegram_disabled_copy": {"de": "Bei Deaktivierung werden keine Telegram-Nachrichten gesendet.", "en": "When disabled, no Telegram messages will be sent."},
    "zigbee_settings": {"de": "Zigbee2MQTT", "en": "Zigbee2MQTT"},
    "mqtt_host": {"de": "MQTT-Host", "en": "MQTT host"},
    "mqtt_port": {"de": "MQTT-Port", "en": "MQTT port"},
    "mqtt_transport": {"de": "Transport", "en": "Transport"},
    "mqtt_transport_tcp": {"de": "TCP", "en": "TCP"},
    "mqtt_transport_ws": {"de": "WebSockets", "en": "WebSockets"},
    "mqtt_ws_path": {"de": "WebSocket-Pfad", "en": "WebSocket path"},
    "mqtt_username": {"de": "MQTT-Benutzer", "en": "MQTT username"},
    "mqtt_password": {"de": "MQTT-Passwort", "en": "MQTT password"},
    "device_availability": {"de": "Geräte aktiv", "en": "Enabled devices"},
    "pump_enabled": {"de": "Pumpe aktiv", "en": "Pump enabled"},
    "heater_enabled": {"de": "Heizung aktiv", "en": "Heater enabled"},
    "exhaust_enabled": {"de": "Abluft aktiv", "en": "Exhaust enabled"},
    "water_sensor_enabled": {"de": "Reservoir-Sensor aktiv", "en": "Reservoir sensor enabled"},
    "light_enabled": {"de": "Licht aktiv", "en": "Light enabled"},
    "dehumidifier_enabled": {"de": "Entfeuchter aktiv", "en": "Dehumidifier enabled"},
    "humidifier_enabled": {"de": "Luftbefeuchter aktiv", "en": "Humidifier enabled"},
    "heater_debug_card_enabled": {"de": "Heizungs-Debug anzeigen", "en": "Show heater debug"},
    "exhaust_debug_card_enabled": {"de": "Abluft-Debug anzeigen", "en": "Show exhaust debug"},
    "light_debug_card_enabled": {"de": "Licht-Debug anzeigen", "en": "Show light debug"},
    "pump_topic": {"de": "Pumpen-Topic", "en": "Pump topic"},
    "heater_topic": {"de": "Heizungs-Topic", "en": "Heater topic"},
    "exhaust_topic": {"de": "Abluft-Topic", "en": "Exhaust topic"},
    "light_topic": {"de": "Licht-Topic", "en": "Light topic"},
    "dehumidifier_topic": {"de": "Entfeuchter-Topic", "en": "Dehumidifier topic"},
    "humidifier_topic": {"de": "Luftbefeuchter-Topic", "en": "Humidifier topic"},
    "water_sensor_topic": {"de": "Reservoir-Sensor-Topic", "en": "Reservoir sensor topic"},
    "mqtt_restart_hint": {"de": "Topic- oder Broker-Änderungen greifen für Hintergrund-Monitore nach einem Service-Neustart sicher vollständig.", "en": "Broker or topic changes apply fully for background monitors after a service restart."},
    "switchbot_settings": {"de": "SwitchBot Sensor", "en": "SwitchBot Sensor"},
    "camera_settings": {"de": "Kamera", "en": "Camera"},
    "camera_test_image": {"de": "Testbild", "en": "Test image"},
    "camera_test_settings": {"de": "Erkannte Werte", "en": "Detected values"},
    "apply_test_settings": {"de": "In Einstellungen übernehmen", "en": "Apply to settings"},
    "camera_auto_focus": {"de": "Autofokus", "en": "Autofocus"},
    "camera_focus": {"de": "Fokus", "en": "Focus"},
    "camera_auto_exposure": {"de": "Auto-Belichtung", "en": "Auto exposure"},
    "camera_exposure": {"de": "Belichtung", "en": "Exposure"},
    "camera_brightness": {"de": "Helligkeit", "en": "Brightness"},
    "camera_contrast": {"de": "Kontrast", "en": "Contrast"},
    "camera_saturation": {"de": "Sättigung", "en": "Saturation"},
    "camera_sharpness": {"de": "Schärfe", "en": "Sharpness"},
    "camera_hint": {"de": "Nicht jede USB-Kamera unterstützt alle Werte. -1 bedeutet: unverändert lassen.", "en": "Not every USB camera supports every value. -1 means: leave unchanged."},
    "menu_settings": {"de": "Menü", "en": "Menu"},
    "menu_default_page": {"de": "Startseite", "en": "Default page"},
    "menu_visibility": {"de": "Sichtbar", "en": "Visible"},
    "menu_order": {"de": "Reihenfolge", "en": "Order"},
    "menu_item": {"de": "Menüpunkt", "en": "Menu item"},
    "menu_settings_hint": {"de": "Sichtbarkeit und Reihenfolge der Navigation. Einstellungen bleibt immer sichtbar.", "en": "Control navigation visibility and order. Settings always stays visible."},
    "switchbot_mac": {"de": "SwitchBot MAC", "en": "SwitchBot MAC"},
    "switchbot_timeout": {"de": "BLE-Scan-Timeout (Sek.)", "en": "BLE scan timeout (sec)"},
    "switchbot_hint": {"de": "MAC-Adresse des Temperatur-/Feuchtesensors und Scan-Timeout für andere SwitchBot-Geräte.", "en": "Temperature/humidity sensor MAC address and scan timeout for other SwitchBot devices."},
    "switchbot_scan_btn": {"de": "Sensor suchen", "en": "Scan for sensor"},
    "switchbot_scanning": {"de": "Suche läuft… (bis zu 10 Sek.)", "en": "Scanning… (up to 10 sec)"},
    "switchbot_no_devices": {"de": "Keine SwitchBot-Geräte gefunden. Bluetooth aktiv?", "en": "No SwitchBot devices found. Is Bluetooth enabled?"},
    "switchbot_found": {"de": "Gefundene Geräte – tippen zum Auswählen:", "en": "Devices found — tap to select:"},
    "switchbot_scan_error": {"de": "Scan fehlgeschlagen. Bluetooth aktiv und bleak installiert?", "en": "Scan failed. Is Bluetooth enabled and bleak installed?"},
    "switchbot_not_set": {"de": "Kein Sensor ausgewählt", "en": "No sensor selected"},
    "save_settings": {"de": "Einstellungen speichern", "en": "Save settings"},
    "saved": {"de": "Gespeichert", "en": "Saved"},
    "on": {"de": "An", "en": "On"},
    "off": {"de": "Aus", "en": "Off"},
    "ui_preview": {"de": "UI-Vorschau", "en": "UI Preview"},
    "save_failed": {"de": "Speichern fehlgeschlagen", "en": "Save failed"},
    "climate_overview": {"de": "Klimaübersicht", "en": "Climate Overview"},
    "latest_reading": {"de": "Letzte Messung", "en": "Latest Reading"},
    "heater_settings": {"de": "Heizungseinstellungen", "en": "Heater Settings"},
    "heater_debug": {"de": "Heater Debug", "en": "Heater Debug"},
    "light_settings": {"de": "Lichteinstellungen", "en": "Light Settings"},
    "light_cycle_settings": {"de": "Lichtzyklus", "en": "Light Cycle"},
    "light_debug": {"de": "Light Debug", "en": "Light Debug"},
    "light_card_title": {"de": "Licht", "en": "Light"},
    "dehumidifier_card_title": {"de": "Entfeuchter", "en": "Dehumidifier"},
    "humidifier_card_title": {"de": "Luftbefeuchter", "en": "Humidifier"},
    "humidity_control": {"de": "Luftfeuchteregelung", "en": "Humidity Control"},
    "humidity_settings": {"de": "Luftfeuchteregelung", "en": "Humidity Settings"},
    "humidity_debug": {"de": "Humidity Debug", "en": "Humidity Debug"},
    "humidity_control_method": {"de": "Luftfeuchtigkeit steuern über", "en": "Control humidity via"},
    "humidity_via_devices": {"de": "Befeuchter / Entfeuchter", "en": "Humidifier / dehumidifier"},
    "humidity_via_exhaust": {"de": "Abluft", "en": "Exhaust"},
    "exhaust_control_mode": {"de": "Abluft-Modus", "en": "Exhaust mode"},
    "mode_sensor": {"de": "Per Sensor", "en": "By sensor"},
    "mode_cycle": {"de": "Per Zyklus", "en": "By cycle"},
    "cycle_on_seconds": {"de": "Zyklus EIN (Sek.)", "en": "Cycle ON (sec)"},
    "cycle_off_seconds": {"de": "Zyklus AUS (Sek.)", "en": "Cycle OFF (sec)"},
    "rh_upper_threshold": {"de": "RLF EIN Entfeuchter ab (%)", "en": "RH dehumidifier on above (%)"},
    "rh_lower_threshold": {"de": "RLF EIN Befeuchter unter (%)", "en": "RH humidifier on below (%)"},
    "lights_on_start": {"de": "Licht an beginnt", "en": "Lights on starts"},
    "lights_on_end": {"de": "Licht an endet", "en": "Lights on ends"},
    "lights_on_window": {"de": "Licht-an-Fenster", "en": "Lights-on window"},
    "debug_panel_enabled": {"de": "Debug anzeigen", "en": "Show debug"},
    "humidity_band": {"de": "RLF Sollband", "en": "RH band"},
    "active_device": {"de": "Aktives Gerät", "en": "Active device"},
    "mutual_exclusion": {"de": "Gegenseitiger Ausschluss", "en": "Mutual exclusion"},
    "power_title": {"de": "Strom", "en": "Power"},
    "power_intro": {"de": "Leistung, Energieverbrauch und Kosten pro Gerät.", "en": "Power, energy consumption and cost per device."},
    "power_settings": {"de": "Strom-Einstellungen", "en": "Power Settings"},
    "price_per_kwh": {"de": "Preis pro kWh", "en": "Price per kWh"},
    "current_power": {"de": "Aktuelle Leistung", "en": "Current power"},
    "energy_yesterday": {"de": "Energie gestern", "en": "Energy yesterday"},
    "energy_today": {"de": "Energie heute", "en": "Energy today"},
    "energy_month": {"de": "Energie Monat", "en": "Energy month"},
    "cost_yesterday": {"de": "Kosten gestern", "en": "Cost yesterday"},
    "cost_today": {"de": "Kosten heute", "en": "Cost today"},
    "cost_month": {"de": "Kosten Monat", "en": "Cost month"},
    "total_energy_yesterday": {"de": "Gesamt gestern", "en": "Total yesterday"},
    "total_energy_today": {"de": "Gesamt heute", "en": "Total today"},
    "total_energy_month": {"de": "Gesamt Monat", "en": "Total month"},
    "total_power": {"de": "Gesamtleistung", "en": "Total power"},
    "total_cost_yesterday": {"de": "Kosten gestern", "en": "Cost yesterday"},
    "total_cost_today": {"de": "Kosten heute", "en": "Cost today"},
    "total_cost_month": {"de": "Kosten Monat", "en": "Cost month"},
    "show_in_chart": {"de": "Im Chart anzeigen", "en": "Show in chart"},
    "timelapse_settings": {"de": "Timelapse-Einstellungen", "en": "Timelapse Settings"},
    "timelapse_enabled": {"de": "Timelapse aktiv", "en": "Timelapse enabled"},
    "timelapse_light_only": {"de": "Nur bei Licht an", "en": "Only while lights on"},
    "rotation": {"de": "Rotation", "en": "Rotation"},
    "interval_minutes": {"de": "Intervall (Minuten)", "en": "Interval (minutes)"},
    "updated": {"de": "Aktualisiert", "en": "Updated"},
    "power_devices": {"de": "Geräte", "en": "Devices"},
    "power_charts": {"de": "Diagramme", "en": "Charts"},
    "power_no_devices": {"de": "Keine aktivierten Power-Geräte vorhanden.", "en": "No enabled power devices available."},
    "exhaust_control": {"de": "Abluftsteuerung", "en": "Exhaust Control"},
    "exhaust_settings": {"de": "Ablufteinstellungen", "en": "Exhaust Settings"},
    "exhaust_debug": {"de": "Abluft Debug", "en": "Exhaust Debug"},
    "exhaust_card_title": {"de": "Abluft", "en": "Exhaust"},
    "exhaust_schedule_copy": {
        "de": "Automatische Abluft basierend auf Luftfeuchtigkeit, Temperatur, Sensor-Failsafe und erzwungenem Luftaustausch.",
        "en": "Automatic exhaust control based on humidity, temperature, sensor failsafe and forced air exchange.",
    },
    "exhaust_device_id": {"de": "Abluft Smart Plug / Topic", "en": "Exhaust smart plug / topic"},
    "rh_turn_on_above": {"de": "RLF einschalten ab (%)", "en": "RH turn on above (%)"},
    "rh_turn_off_below": {"de": "RLF ausschalten unter (%)", "en": "RH turn off below (%)"},
    "temp_force_on_above": {"de": "Temp Zwang EIN ab (°C)", "en": "Temp force on above (°C)"},
    "temp_allow_off_below": {"de": "Temp AUS erlaubt unter (°C)", "en": "Temp allow off below (°C)"},
    "max_off_time_before_refresh": {"de": "Max. AUS-Zeit vor Refresh (Sek.)", "en": "Max off-time before refresh (sec)"},
    "forced_refresh_run_time": {"de": "Refresh-Laufzeit (Sek.)", "en": "Forced refresh run-time (sec)"},
    "forced_refresh_active": {"de": "Refresh aktiv", "en": "Forced refresh active"},
    "last_change_reason": {"de": "Letzter Wechselgrund", "en": "Last change reason"},
    "day_target": {"de": "Licht an Soll (°C)", "en": "Lights on target (°C)"},
    "night_target": {"de": "Licht aus Soll (°C)", "en": "Lights off target (°C)"},
    "day_start": {"de": "Licht an beginnt", "en": "Lights on starts"},
    "day_end": {"de": "Licht an endet", "en": "Lights on ends"},
    "active_settings": {"de": "Aktive Einstellungen", "en": "Active settings"},
    "auto_mode_state": {"de": "Automatik", "en": "Automation"},
    "debug_state": {"de": "Debug", "en": "Debug"},
    "day_night_targets": {"de": "Licht an / aus", "en": "Lights on / off"},
    "day_window": {"de": "Licht-an-Fenster", "en": "Lights-on window"},
    "rh_band": {"de": "RLF EIN / AUS", "en": "RH on / off"},
    "temp_band": {"de": "Temp EIN / AUS", "en": "Temp on / off"},
    "on_below": {"de": "Ein unter Soll um (°C)", "en": "Turn on below target by (°C)"},
    "off_above": {"de": "Aus über Soll um (°C)", "en": "Turn off above target by (°C)"},
    "min_on": {"de": "Min. Laufzeit an (Sek.)", "en": "Min on-time (sec)"},
    "min_off": {"de": "Min. Pause aus (Sek.)", "en": "Min off-time (sec)"},
    "max_sensor_age": {"de": "Max. Sensoralter (Sek.)", "en": "Max sensor age (sec)"},
    "control_interval": {"de": "Regelintervall (Sek.)", "en": "Control interval (sec)"},
    "median_samples": {"de": "Median-Samples", "en": "Median samples"},
    "auto_enabled": {"de": "Automatik aktiv", "en": "Automation enabled"},
    "debug_notify": {"de": "Debug Telegram Notify", "en": "Debug Telegram Notify"},
    "climate_chart_title": {"de": "Temperatur, Luftfeuchte & VPD", "en": "Temperature, Humidity & VPD"},
    "display_mode": {"de": "Darstellung:", "en": "Display:"},
    "original": {"de": "Original", "en": "Original"},
    "smoothed": {"de": "Geglättet (Moving Avg)", "en": "Smoothed (Moving Avg)"},
    "delta": {"de": "Differenz", "en": "Delta"},
    "climate_24h": {"de": "24h Werte", "en": "24h Stats"},
    "climate_7d": {"de": "7 Tage", "en": "7 Days"},
    "temp_avg": {"de": "Temp ⌀", "en": "Temp Avg"},
    "temp_max": {"de": "Temp Max", "en": "Temp Max"},
    "temp_min": {"de": "Temp Min", "en": "Temp Min"},
    "hum_avg": {"de": "RLF ⌀", "en": "Hum Avg"},
    "hum_max": {"de": "RLF Max", "en": "Hum Max"},
    "hum_min": {"de": "RLF Min", "en": "Hum Min"},
    "current_reading": {"de": "Aktuelle Messung", "en": "Current Reading"},
    "median": {"de": "Median", "en": "Median"},
    "plug_state": {"de": "Steckdosenstatus", "en": "Plug State"},
    "plug_power": {"de": "Steckdosenleistung", "en": "Plug Power"},
    "reading_time": {"de": "Zeitpunkt", "en": "Reading Time"},
    "target_thresholds": {"de": "Ziel / Schwellen", "en": "Target / Thresholds"},
    "last_decision": {"de": "Letzte Entscheidung", "en": "Last Decision"},
    "last_command": {"de": "Letzter Befehl", "en": "Last Command"},
    "command_ack": {"de": "Befehlsbestätigung", "en": "Command Ack"},
    "heater_card_title": {"de": "Heizung (Keller)", "en": "Heater (Basement)"},
    "heater_schedule_copy": {
        "de": "Automatische Regelung mit separaten Licht-an/Licht-aus-Zielen, Hysterese und Mindestlaufzeiten gegen Kurzzyklen.",
        "en": "Automatic control with separate lights-on/lights-off targets, hysteresis and minimum runtimes to avoid short cycling.",
    },
    "status_unknown": {"de": "Status: unbekannt", "en": "Status: unknown"},
    "power_unknown": {"de": "Leistung: – W", "en": "Power: – W"},
    "open_menu": {"de": "Menü öffnen", "en": "Open menu"},
    "no_sensor_values": {"de": "Noch keine Sensorwerte gespeichert.", "en": "No sensor readings stored yet."},
    "all": {"de": "Alle", "en": "All"},
    "custom_range": {"de": "Eigenes Zeitfenster", "en": "Custom timeframe"},
    "from": {"de": "Von", "en": "From"},
    "to": {"de": "Bis", "en": "To"},
    "hours": {"de": "Stunden", "en": "Hours"},
    "days_unit": {"de": "Tage", "en": "Days"},
    "apply": {"de": "Anwenden", "en": "Apply"},
    "no_data": {"de": "Keine Daten.", "en": "No data."},
    "dashboard_sync": {"de": "Synchronisation", "en": "Sync"},
    "dashboard_synced": {"de": "Synchronisiert", "en": "Synced"},
    "dashboard_status": {"de": "Status", "en": "Status"},
    "dashboard_phase": {"de": "Phase", "en": "Phase"},
    "dashboard_days": {"de": "Tage", "en": "Days"},
    "dashboard_weeks": {"de": "Wochen", "en": "Weeks"},
    "last_watering": {"de": "Letzte Bewässerung", "en": "Last watering"},
    "start_date": {"de": "Startdatum", "en": "Start date"},
    "sprout": {"de": "Sämling", "en": "Sprout"},
    "climate_values": {"de": "Klimawerte", "en": "Climate values"},
    "temperature": {"de": "Temperatur", "en": "Temperature"},
    "humidity": {"de": "Luftfeuchte", "en": "Humidity"},
    "vpd": {"de": "VPD", "en": "VPD"},
    "recorded_at": {"de": "Stand", "en": "Recorded"},
    "optimal": {"de": "Optimal", "en": "Optimal"},
    "flower": {"de": "Blüte", "en": "Flower"},
    "flower_day": {"de": "Blütetag", "en": "Flower day"},
    "flower_week": {"de": "Blütewoche", "en": "Flower week"},
    "flower_start": {"de": "Blütestart", "en": "Start flower"},
    "reset": {"de": "Reset", "en": "Reset"},
    "latest_photo": {"de": "Letztes Bild", "en": "Latest photo"},
    "new_photo": {"de": "Neue Aufnahme", "en": "New capture"},
    "grow_info": {"de": "Grow Info", "en": "Grow Info"},
    "climate": {"de": "Klima", "en": "Climate"},
    "sensor_refresh": {"de": "Sensor aktualisieren", "en": "Refresh sensor"},
    "min": {"de": "Min", "en": "Min"},
    "max": {"de": "Max", "en": "Max"},
    "timelapse_images": {"de": "Timelapse Video", "en": "Timelapse video"},
    "total_images": {"de": "Gesamtbilder", "en": "Total images"},
    "oldest_image": {"de": "Ältestes Bild", "en": "Oldest image"},
    "latest_image": {"de": "Aktuellstes Bild", "en": "Latest image"},
    "storage": {"de": "Speicher", "en": "Storage"},
    "create_video": {"de": "Video erstellen", "en": "Create video"},
    "download_video": {"de": "Video herunterladen", "en": "Download video"},
    "created": {"de": "Erstellt", "en": "Created"},
    "duration": {"de": "Dauer", "en": "Duration"},
    "file_size": {"de": "Dateigröße", "en": "File size"},
    "watering_title": {"de": "Bewässerung", "en": "Watering"},
    "last_saved": {"de": "Letzte Speicherung", "en": "Last saved"},
    "days_ago": {"de": "vor {days} Tagen", "en": "{days} days ago"},
    "next_check": {"de": "Nächster Check", "en": "Next check"},
    "open_plan": {"de": "Plan offen", "en": "Open plan"},
    "interval_days": {"de": "Intervall: {days} Tage", "en": "Interval: {days} days"},
    "save_watering": {"de": "Bewässerung speichern", "en": "Save watering"},
    "date": {"de": "Datum", "en": "Date"},
    "save": {"de": "Speichern", "en": "Save"},
    "add_today": {"de": "Heute eintragen", "en": "Add today"},
    "clear_date": {"de": "Datum löschen", "en": "Clear date"},
    "control_pump": {"de": "Pumpe steuern", "en": "Control pump"},
    "pump_on": {"de": "Pumpe an", "en": "Pump on"},
    "pump_off": {"de": "Pumpe aus", "en": "Pump off"},
    "runtime_minutes": {"de": "Laufzeit (Minuten)", "en": "Runtime (minutes)"},
    "example_two": {"de": "z. B. 2", "en": "e.g. 2"},
    "start_auto_off": {"de": "Starten & Auto-Off", "en": "Start & Auto-off"},
    "pump_auto_off_copy": {"de": "Die Pumpe wird automatisch nach der angegebenen Zeit ausgeschaltet.", "en": "The pump switches off automatically after the selected time."},
    "reservoir_sensor": {"de": "Reservoir Sensor", "en": "Reservoir Sensor"},
    "wick_reservoir": {"de": "Reservoir", "en": "Reservoir"},
    "reservoir_copy": {"de": "Trocken = leer, nass = Wasser vorhanden", "en": "Dry = empty, wet = water available"},
    "fertilizer_title": {"de": "Düngerplanung", "en": "Fertilizer Planning"},
    "current_week_phase": {"de": "Aktuelle Woche: {week} · {phase}", "en": "Current week: {week} · {phase}"},
    "current_dosage": {"de": "Aktuelle Dosierung", "en": "Current dosage"},
    "no_fertilizers": {"de": "Keine Dünger hinterlegt.", "en": "No fertilizers configured."},
    "manage_fertilizers": {"de": "Dünger verwalten", "en": "Manage fertilizers"},
    "fertilizer_name": {"de": "Name", "en": "Name"},
    "unit": {"de": "Einheit", "en": "Unit"},
    "per_liter": {"de": "pro Liter", "en": "per liter"},
    "weekly_dosage": {"de": "Wöchentliche Dosierung", "en": "Weekly dosage"},
    "week_short": {"de": "W", "en": "W"},
    "save_fertilizer": {"de": "Dünger speichern", "en": "Save fertilizer"},
    "new_fertilizer": {"de": "Neuer Dünger", "en": "New fertilizer"},
    "delete_fertilizer": {"de": "Dünger löschen", "en": "Delete fertilizer"},
    "edit": {"de": "Bearbeiten", "en": "Edit"},
    "delete": {"de": "Löschen", "en": "Delete"},
    "fertilizer_saved": {"de": "Dünger gespeichert", "en": "Fertilizer saved"},
    "fertilizer_deleted": {"de": "Dünger gelöscht", "en": "Fertilizer deleted"},
    "choose_fertilizer": {"de": "Wähle einen Dünger zum Bearbeiten oder lege einen neuen an.", "en": "Choose a fertilizer to edit or create a new one."},
    "amount": {"de": "Menge", "en": "Amount"},
    "week_label": {"de": "Woche {week}", "en": "Week {week}"},
    "week_count": {"de": "Wochen", "en": "Weeks"},
    "same_amount_all_weeks": {"de": "Gleiche Menge für alle Wochen", "en": "Same amount for all weeks"},
    "same_amount_value": {"de": "Menge für alle Wochen", "en": "Amount for all weeks"},
    "calculate_plan": {"de": "Düngerplan berechnen", "en": "Calculate fertilizer plan"},
    "liters": {"de": "Liter", "en": "Liters"},
    "percent": {"de": "Prozent", "en": "Percent"},
    "calculate": {"de": "Plan berechnen", "en": "Calculate plan"},
    "save_default": {"de": "Als Standard speichern", "en": "Save as default"},
    "total": {"de": "Gesamt", "en": "Total"},
    "save_default_copy": {"de": "Nutze „Als Standard speichern“, um deine Lieblingskonfiguration zu sichern.", "en": "Use “Save as default” to keep this setup for later."},
    "week_overview": {"de": "Wochenübersicht", "en": "Weekly overview"},
    "values_per_l": {"de": "Werte pro Liter", "en": "Values per liter"},
    "values_per_gallon": {"de": "Werte pro Gallone", "en": "Values per gallon"},
    "fertilizer": {"de": "Dünger", "en": "Fertilizer"},
    "no_data_available": {"de": "Keine Daten vorhanden.", "en": "No data available."},
    "phase_veg": {"de": "Veg", "en": "Veg"},
    "phase_flower": {"de": "Blüte", "en": "Flower"},
    "unknown": {"de": "unbekannt", "en": "unknown"},
    "info_grow_name": {"de": "Grow-Name", "en": "Grow name"},
    "info_start": {"de": "Start", "en": "Start"},
    "info_sprout": {"de": "Sprout", "en": "Sprout"},
    "info_last_watering": {"de": "Letzte Bewässerung", "en": "Last watering"},
    "info_phase": {"de": "Phase", "en": "Phase"},
    "info_current_week": {"de": "Aktuelle Woche", "en": "Current week"},
    "info_flower_start": {"de": "Blüte-Beginn", "en": "Flower start"},
}


def load_env(env_path: str) -> None:
    """Populate os.environ entries from a simple KEY=VALUE .env file."""
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


load_env(ENV_FILE)

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PUMP_TOPIC = os.getenv("PUMP_TOPIC", "zigbee2mqtt/pump/set")
HEATER_TOPIC = os.getenv("HEATER_TOPIC", os.getenv("DEHUMIDIFIER_TOPIC", "zigbee2mqtt/heizung_keller/set"))
LIGHT_TOPIC = os.getenv("LIGHT_TOPIC", "zigbee2mqtt/light/set")
DEHUMIDIFIER_TOPIC = os.getenv("DEHUMIDIFIER_TOPIC", "zigbee2mqtt/dehumidifier/set")
HUMIDIFIER_TOPIC = os.getenv("HUMIDIFIER_TOPIC", "zigbee2mqtt/humidifier/set")
MQTT_TRANSPORT = os.getenv("MQTT_TRANSPORT", "tcp").lower()
MQTT_WS_PATH = os.getenv("MQTT_WS_PATH", "/")
WATER_SENSOR_TOPIC = os.getenv("WATER_SENSOR_TOPIC", "zigbee2mqtt/Wassermelder_keller")
SWITCHBOT_MAC = os.getenv("SWITCHBOT_MAC", "")
SWITCHBOT_SCAN_TIMEOUT = int(os.getenv("SWITCHBOT_SCAN_TIMEOUT", "15"))
WATER_GUARD_ENABLED = os.getenv("WATER_GUARD_ENABLED", "1").lower() in ("1", "true", "yes")
DEFAULT_HEATER_SETTINGS = {
    "enabled": os.getenv("HEATER_CONTROL_ENABLED", "1").lower() in ("1", "true", "yes"),
    "day_target_c": float(os.getenv("HEATER_DAY_TARGET_C", "19")),
    "night_target_c": float(os.getenv("HEATER_NIGHT_TARGET_C", "23")),
    "day_start": os.getenv("HEATER_DAY_START", "18:01"),
    "day_end": os.getenv("HEATER_DAY_END", "11:59"),
    "on_below_offset_c": float(os.getenv("HEATER_ON_BELOW_OFFSET_C", "0.4")),
    "off_above_offset_c": float(os.getenv("HEATER_OFF_ABOVE_OFFSET_C", "0.3")),
    "min_on_seconds": int(os.getenv("HEATER_MIN_ON_SECONDS", "900")),
    "min_off_seconds": int(os.getenv("HEATER_MIN_OFF_SECONDS", "600")),
    "sensor_max_age_seconds": int(os.getenv("HEATER_SENSOR_MAX_AGE_SECONDS", "2700")),
    "control_interval_seconds": int(os.getenv("HEATER_CONTROL_INTERVAL_SECONDS", "60")),
    "sensor_median_samples": max(1, int(os.getenv("HEATER_SENSOR_MEDIAN_SAMPLES", "3"))),
    "debug_notify": os.getenv("HEATER_DEBUG_NOTIFY", "0").lower() in ("1", "true", "yes"),
}
# Emergency shutoff threshold: heater is forced OFF regardless of short-cycle protection
# if temperature reaches or exceeds this value. Override via env var HEATER_EMERGENCY_OFF_TEMP_C.
HEATER_EMERGENCY_OFF_TEMP_C = float(os.getenv("HEATER_EMERGENCY_OFF_TEMP_C", "30.0"))
LIGHT_MONITOR_MAX_AGE_SECONDS = int(os.getenv("LIGHT_MONITOR_MAX_AGE_SECONDS", "300"))
MQTT_OFFLINE_ALERT_SECONDS = int(os.getenv("MQTT_OFFLINE_ALERT_SECONDS", "120"))
SENSOR_OFFLINE_ALERT_SECONDS = int(os.getenv("SENSOR_OFFLINE_ALERT_SECONDS", "600"))
POWER_ANOMALY_MIN_WATTS = float(os.getenv("POWER_ANOMALY_MIN_WATTS", "5.0"))
POWER_ANOMALY_GRACE_SECONDS = int(os.getenv("POWER_ANOMALY_GRACE_SECONDS", "120"))
ALERT_MIN_INTERVAL_SECONDS = int(os.getenv("ALERT_MIN_INTERVAL_SECONDS", "1800"))
DEFAULT_EXHAUST_SETTINGS = {
    "enabled": False,
    "debug_notify": False,
    "plug_topic": "zigbee2mqtt/abluft/set",
    "rh_turn_on_above": 66.0,
    "rh_turn_off_below": 60.0,
    "temp_force_on_above": 25.5,
    "temp_allow_off_below": 24.5,
    "min_on_seconds": 600,
    "min_off_seconds": 900,
    "max_off_time_before_refresh": 5400,
    "forced_refresh_run_time": 600,
    "sensor_max_age_seconds": 300,
    "control_interval_seconds": 30,
    "sensor_median_samples": 5,
}
DEFAULT_LIGHT_SETTINGS = {
    "enabled": False,
    "debug_notify": False,
    "control_interval_seconds": int(os.getenv("LIGHT_CONTROL_INTERVAL_SECONDS", "30")),
}
DEFAULT_LIGHT_CYCLE_SETTINGS = {
    "lights_on_start": os.getenv("LIGHTS_ON_START", "18:01"),
    "lights_on_end": os.getenv("LIGHTS_ON_END", "11:59"),
}
DEFAULT_TIMELAPSE_SETTINGS = {
    "enabled": True,
    "light_only": False,
    "rotation_degrees": int(os.getenv("TIMELAPSE_ROTATION_DEGREES", "0")),
    "interval_minutes": int(os.getenv("TIMELAPSE_INTERVAL_MINUTES", "30")),
}
DEFAULT_HUMIDITY_SETTINGS = {
    "enabled": False,
    "debug_notify": False,
    "control_method": "devices",
    "exhaust_control_mode": "sensor",
    "rh_upper_threshold": float(os.getenv("RH_UPPER_THRESHOLD", "66")),
    "rh_lower_threshold": float(os.getenv("RH_LOWER_THRESHOLD", "60")),
    "cycle_on_seconds": int(os.getenv("EXHAUST_CYCLE_ON_SECONDS", "600")),
    "cycle_off_seconds": int(os.getenv("EXHAUST_CYCLE_OFF_SECONDS", "1800")),
    "min_on_seconds": int(os.getenv("RH_MIN_ON_SECONDS", "600")),
    "min_off_seconds": int(os.getenv("RH_MIN_OFF_SECONDS", "600")),
    "sensor_max_age_seconds": int(os.getenv("RH_SENSOR_MAX_AGE_SECONDS", "300")),
    "control_interval_seconds": int(os.getenv("RH_CONTROL_INTERVAL_SECONDS", "30")),
    "sensor_median_samples": max(1, int(os.getenv("RH_SENSOR_MEDIAN_SAMPLES", "5"))),
}
DEFAULT_POWER_SETTINGS = {
    "price_per_kwh": float(os.getenv("POWER_PRICE_PER_KWH", "0.30")),
}

PUMP_TIMER_LOCK = threading.Lock()
PUMP_TIMER_DEADLINE: datetime | None = None
PUMP_TIMER_THREAD: threading.Timer | None = None
LIVE_SENSOR_CACHE_LOCK = threading.Lock()
LIVE_SENSOR_CACHE: Dict[str, Any] = {"reading": None, "fetched_at": None}
_FS_CACHE: Dict[str, tuple] = {}  # key -> (monotonic_time, result)
_FS_CACHE_TTL = 30.0  # seconds
ACCENT_PRESETS = {
    "teal": {"primary": "#14b8a6", "secondary": "#6366f1"},
    "sunset": {"primary": "#f97316", "secondary": "#ef4444"},
    "mint": {"primary": "#10b981", "secondary": "#06b6d4"},
    "ocean": {"primary": "#0ea5e9", "secondary": "#2563eb"},
    "rose": {"primary": "#ec4899", "secondary": "#8b5cf6"},
    "gold": {"primary": "#f59e0b", "secondary": "#d97706"},
    "lime": {"primary": "#84cc16", "secondary": "#22c55e"},
}
MENU_ITEM_DEFS = [
    {"id": "dashboard", "endpoint": "index", "icon": "📊", "label_key": "nav_dashboard"},
    {"id": "fertilizer", "endpoint": "fertilizer_page", "icon": "🧪", "label_key": "nav_fertilizer"},
    {"id": "watering", "endpoint": "watering_page", "icon": "💧", "label_key": "nav_watering"},
    {"id": "climate", "endpoint": "climate_page", "icon": "🌡️", "label_key": "nav_climate"},
    {"id": "power", "endpoint": "power_page", "icon": "⚡", "label_key": "nav_power"},
    {"id": "light", "endpoint": "light_page", "icon": "💡", "label_key": "nav_light"},
    {"id": "timelapse", "endpoint": "timelapse_page", "icon": "🎞️", "label_key": "nav_timelapse"},
    {"id": "settings", "endpoint": "settings_page", "icon": "⚙️", "label_key": "nav_settings"},
]


def load_data() -> Dict[str, Any]:
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def save_data(data: Dict[str, Any]) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _default_menu_order() -> List[str]:
    return [item["id"] for item in MENU_ITEM_DEFS]


def _normalize_menu_config(raw_order: Any, raw_visibility: Any) -> tuple[list[str], dict[str, bool]]:
    known_ids = _default_menu_order()
    order = [str(item) for item in raw_order] if isinstance(raw_order, list) else []
    order = [item for item in order if item in known_ids]
    for item_id in known_ids:
        if item_id not in order:
            order.append(item_id)
    visibility = {item_id: True for item_id in known_ids}
    if isinstance(raw_visibility, dict):
        for item_id in known_ids:
            if item_id in raw_visibility:
                visibility[item_id] = bool(raw_visibility[item_id])
    visibility["settings"] = True
    return order, visibility


def get_navigation_items(ui_settings: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    settings = ui_settings or get_app_settings()
    order, visibility = _normalize_menu_config(settings.get("menu_order"), settings.get("menu_visibility"))
    item_map = {item["id"]: item for item in MENU_ITEM_DEFS}
    items: List[Dict[str, Any]] = []
    for item_id in order:
        if not visibility.get(item_id, True):
            continue
        if item_id == "light" and not settings.get("light_enabled", True):
            continue
        items.append(item_map[item_id])
    return items


def get_menu_editor_items(ui_settings: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    settings = ui_settings or get_app_settings()
    order, visibility = _normalize_menu_config(settings.get("menu_order"), settings.get("menu_visibility"))
    item_map = {item["id"]: item for item in MENU_ITEM_DEFS}
    default_page = settings.get("default_page", "dashboard")
    return [
        {
            **item_map[item_id],
            "visible": visibility.get(item_id, True),
            "locked": item_id == "settings",
            "is_default": item_id == default_page,
        }
        for item_id in order
    ]


def _normalize_hex_color(value: Any, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    value = value.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value.lower()
    return fallback


def get_app_settings() -> Dict[str, Any]:
    data = load_data()
    raw = data.get("app_settings", {})
    settings = {
        "language": "de",
        "datetime_format": "eu",
        "measurement_system": "metric",
        "temperature_unit": "c",
        "currency": "EUR",
        "compact_mode": True,
        "reduce_motion": False,
        "appearance_theme": "dark-blue",
        "accent_theme": "teal",
        "accent_primary": ACCENT_PRESETS["teal"]["primary"],
        "accent_secondary": ACCENT_PRESETS["teal"]["secondary"],
        "telegram_enabled": True,
        "telegram_bot_token": TELEGRAM_BOT_TOKEN or "",
        "telegram_chat_id": TELEGRAM_CHAT_ID or "",
        "mqtt_host": MQTT_HOST,
        "mqtt_port": MQTT_PORT,
        "mqtt_transport": MQTT_TRANSPORT,
        "mqtt_ws_path": MQTT_WS_PATH,
        "mqtt_username": MQTT_USERNAME or "",
        "mqtt_password": MQTT_PASSWORD or "",
        "pump_enabled": True,
        "heater_enabled": True,
        "exhaust_enabled": True,
        "water_sensor_enabled": True,
        "light_enabled": True,
        "dehumidifier_enabled": True,
        "humidifier_enabled": True,
        "heater_debug_card_enabled": True,
        "exhaust_debug_card_enabled": True,
        "light_debug_card_enabled": True,
        "pump_topic": PUMP_TOPIC,
        "heater_topic": HEATER_TOPIC,
        "exhaust_topic": DEFAULT_EXHAUST_SETTINGS["plug_topic"],
        "light_topic": LIGHT_TOPIC,
        "dehumidifier_topic": DEHUMIDIFIER_TOPIC,
        "humidifier_topic": HUMIDIFIER_TOPIC,
        "water_sensor_topic": WATER_SENSOR_TOPIC,
        "switchbot_mac": SWITCHBOT_MAC,
        "switchbot_scan_timeout": SWITCHBOT_SCAN_TIMEOUT,
        "camera_auto_focus": True,
        "camera_focus": -1,
        "camera_auto_exposure": True,
        "camera_exposure": -1,
        "camera_brightness": -1,
        "camera_contrast": -1,
        "camera_saturation": -1,
        "camera_sharpness": -1,
        "menu_order": _default_menu_order(),
        "menu_visibility": {item_id: True for item_id in _default_menu_order()},
        "default_page": "dashboard",
        "weekly_summary_enabled": False,
        "weekly_summary_time": "09:00",
    }
    if isinstance(raw, dict):
        settings.update(raw)
    settings["language"] = settings["language"] if settings.get("language") in {"de", "en"} else "de"
    settings["datetime_format"] = settings["datetime_format"] if settings.get("datetime_format") in {"eu", "us", "iso"} else "eu"
    settings["measurement_system"] = settings["measurement_system"] if settings.get("measurement_system") in {"metric", "imperial"} else "metric"
    settings["temperature_unit"] = settings["temperature_unit"] if settings.get("temperature_unit") in {"c", "f"} else "c"
    settings["currency"] = str(settings.get("currency") or "EUR").strip() or "EUR"
    settings["compact_mode"] = True
    settings["reduce_motion"] = False
    settings["appearance_theme"] = settings["appearance_theme"] if settings.get("appearance_theme") in {"dark-blue", "dark-grey", "light"} else "dark-blue"
    settings["accent_theme"] = settings["accent_theme"] if settings.get("accent_theme") in set(ACCENT_PRESETS) | {"custom"} else "teal"
    settings["accent_primary"] = _normalize_hex_color(settings.get("accent_primary"), ACCENT_PRESETS["teal"]["primary"])
    settings["accent_secondary"] = _normalize_hex_color(settings.get("accent_secondary"), ACCENT_PRESETS["teal"]["secondary"])
    settings["telegram_enabled"] = bool(settings.get("telegram_enabled", True))
    settings["telegram_bot_token"] = str(settings.get("telegram_bot_token") or TELEGRAM_BOT_TOKEN or "")
    settings["telegram_chat_id"] = str(settings.get("telegram_chat_id") or TELEGRAM_CHAT_ID or "")
    settings["mqtt_host"] = str(settings.get("mqtt_host") or MQTT_HOST).strip() or MQTT_HOST
    try:
        settings["mqtt_port"] = int(settings.get("mqtt_port", MQTT_PORT))
    except (TypeError, ValueError):
        settings["mqtt_port"] = MQTT_PORT
    settings["mqtt_transport"] = settings["mqtt_transport"] if settings.get("mqtt_transport") in {"tcp", "websockets"} else MQTT_TRANSPORT
    settings["mqtt_ws_path"] = str(settings.get("mqtt_ws_path") or MQTT_WS_PATH or "/").strip() or "/"
    settings["mqtt_username"] = str(settings.get("mqtt_username") or MQTT_USERNAME or "")
    settings["mqtt_password"] = str(settings.get("mqtt_password") or MQTT_PASSWORD or "")
    settings["pump_enabled"] = bool(settings.get("pump_enabled", True))
    settings["heater_enabled"] = bool(settings.get("heater_enabled", True))
    settings["exhaust_enabled"] = bool(settings.get("exhaust_enabled", True))
    settings["water_sensor_enabled"] = bool(settings.get("water_sensor_enabled", True))
    settings["light_enabled"] = bool(settings.get("light_enabled", True))
    settings["dehumidifier_enabled"] = bool(settings.get("dehumidifier_enabled", True))
    settings["humidifier_enabled"] = bool(settings.get("humidifier_enabled", True))
    settings["heater_debug_card_enabled"] = bool(settings.get("heater_debug_card_enabled", True))
    settings["exhaust_debug_card_enabled"] = bool(settings.get("exhaust_debug_card_enabled", True))
    settings["light_debug_card_enabled"] = bool(settings.get("light_debug_card_enabled", True))
    settings["pump_topic"] = str(settings.get("pump_topic") or PUMP_TOPIC).strip() or PUMP_TOPIC
    settings["heater_topic"] = str(settings.get("heater_topic") or HEATER_TOPIC).strip() or HEATER_TOPIC
    legacy_exhaust_topic = None
    if isinstance(raw, dict):
        legacy_exhaust_topic = raw.get("exhaust_topic")
    exhaust_defaults = data.get("exhaust_settings", {}) if isinstance(data.get("exhaust_settings"), dict) else {}
    settings["exhaust_topic"] = (
        str(settings.get("exhaust_topic") or legacy_exhaust_topic or exhaust_defaults.get("plug_topic") or DEFAULT_EXHAUST_SETTINGS["plug_topic"]).strip()
        or DEFAULT_EXHAUST_SETTINGS["plug_topic"]
    )
    settings["light_topic"] = str(settings.get("light_topic") or LIGHT_TOPIC).strip() or LIGHT_TOPIC
    settings["dehumidifier_topic"] = str(settings.get("dehumidifier_topic") or DEHUMIDIFIER_TOPIC).strip() or DEHUMIDIFIER_TOPIC
    settings["humidifier_topic"] = str(settings.get("humidifier_topic") or HUMIDIFIER_TOPIC).strip() or HUMIDIFIER_TOPIC
    settings["water_sensor_topic"] = str(settings.get("water_sensor_topic") or WATER_SENSOR_TOPIC).strip() or WATER_SENSOR_TOPIC
    settings["switchbot_mac"] = str(settings.get("switchbot_mac") or SWITCHBOT_MAC).strip().upper() or SWITCHBOT_MAC
    try:
        settings["switchbot_scan_timeout"] = int(settings.get("switchbot_scan_timeout", SWITCHBOT_SCAN_TIMEOUT))
    except (TypeError, ValueError):
        settings["switchbot_scan_timeout"] = SWITCHBOT_SCAN_TIMEOUT
    settings["camera_auto_focus"] = bool(settings.get("camera_auto_focus", True))
    settings["camera_auto_exposure"] = bool(settings.get("camera_auto_exposure", True))
    for key in ("camera_focus", "camera_exposure", "camera_brightness", "camera_contrast", "camera_saturation", "camera_sharpness"):
        try:
            settings[key] = int(settings.get(key, -1))
        except (TypeError, ValueError):
            settings[key] = -1
    settings["menu_order"], settings["menu_visibility"] = _normalize_menu_config(
        settings.get("menu_order"), settings.get("menu_visibility")
    )
    settings["weekly_summary_enabled"] = bool(settings.get("weekly_summary_enabled", False))
    settings["weekly_summary_time"] = str(settings.get("weekly_summary_time") or "09:00").strip() or "09:00"
    return settings


def save_app_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = load_data()
    settings = get_app_settings()
    settings["language"] = payload.get("language", settings["language"])
    settings["datetime_format"] = payload.get("datetime_format", settings["datetime_format"])
    settings["measurement_system"] = payload.get("measurement_system", settings["measurement_system"])
    settings["temperature_unit"] = payload.get("temperature_unit", settings["temperature_unit"])
    settings["currency"] = payload.get("currency", settings["currency"])
    settings["compact_mode"] = True
    settings["reduce_motion"] = False
    settings["appearance_theme"] = payload.get("appearance_theme", settings["appearance_theme"])
    requested_accent_theme = payload.get("accent_theme", settings["accent_theme"])
    settings["accent_theme"] = requested_accent_theme if requested_accent_theme in ACCENT_PRESETS else "custom"
    settings["accent_primary"] = _normalize_hex_color(payload.get("accent_primary"), settings["accent_primary"])
    settings["accent_secondary"] = _normalize_hex_color(payload.get("accent_secondary"), settings["accent_secondary"])
    settings["telegram_enabled"] = bool(payload.get("telegram_enabled", False))
    settings["telegram_bot_token"] = str(payload.get("telegram_bot_token", settings["telegram_bot_token"]) or "").strip()
    settings["telegram_chat_id"] = str(payload.get("telegram_chat_id", settings["telegram_chat_id"]) or "").strip()
    settings["mqtt_host"] = str(payload.get("mqtt_host", settings["mqtt_host"]) or "").strip()
    settings["mqtt_transport"] = str(payload.get("mqtt_transport", settings["mqtt_transport"]) or "").strip().lower()
    settings["mqtt_ws_path"] = str(payload.get("mqtt_ws_path", settings["mqtt_ws_path"]) or "").strip() or "/"
    settings["mqtt_username"] = str(payload.get("mqtt_username", settings["mqtt_username"]) or "").strip()
    settings["mqtt_password"] = str(payload.get("mqtt_password", settings["mqtt_password"]) or "")
    settings["pump_enabled"] = bool(payload.get("pump_enabled", settings["pump_enabled"]))
    settings["heater_enabled"] = bool(payload.get("heater_enabled", settings["heater_enabled"]))
    settings["exhaust_enabled"] = bool(payload.get("exhaust_enabled", settings["exhaust_enabled"]))
    settings["water_sensor_enabled"] = bool(payload.get("water_sensor_enabled", settings["water_sensor_enabled"]))
    settings["light_enabled"] = bool(payload.get("light_enabled", settings["light_enabled"]))
    settings["dehumidifier_enabled"] = bool(payload.get("dehumidifier_enabled", settings["dehumidifier_enabled"]))
    settings["humidifier_enabled"] = bool(payload.get("humidifier_enabled", settings["humidifier_enabled"]))
    settings["heater_debug_card_enabled"] = bool(payload.get("heater_debug_card_enabled", settings["heater_debug_card_enabled"]))
    settings["exhaust_debug_card_enabled"] = bool(payload.get("exhaust_debug_card_enabled", settings["exhaust_debug_card_enabled"]))
    settings["light_debug_card_enabled"] = bool(payload.get("light_debug_card_enabled", settings["light_debug_card_enabled"]))
    settings["pump_topic"] = str(payload.get("pump_topic", settings["pump_topic"]) or "").strip()
    settings["heater_topic"] = str(payload.get("heater_topic", settings["heater_topic"]) or "").strip()
    settings["exhaust_topic"] = str(payload.get("exhaust_topic", settings["exhaust_topic"]) or "").strip()
    settings["light_topic"] = str(payload.get("light_topic", settings["light_topic"]) or "").strip()
    settings["dehumidifier_topic"] = str(payload.get("dehumidifier_topic", settings["dehumidifier_topic"]) or "").strip()
    settings["humidifier_topic"] = str(payload.get("humidifier_topic", settings["humidifier_topic"]) or "").strip()
    settings["water_sensor_topic"] = str(payload.get("water_sensor_topic", settings["water_sensor_topic"]) or "").strip()
    settings["switchbot_mac"] = str(payload.get("switchbot_mac", settings["switchbot_mac"]) or "").strip().upper()
    settings["camera_auto_focus"] = bool(payload.get("camera_auto_focus", settings["camera_auto_focus"]))
    settings["camera_auto_exposure"] = bool(payload.get("camera_auto_exposure", settings["camera_auto_exposure"]))
    settings["menu_order"], settings["menu_visibility"] = _normalize_menu_config(
        payload.get("menu_order", settings.get("menu_order")),
        payload.get("menu_visibility", settings.get("menu_visibility")),
    )
    known_page_ids = {item["id"] for item in MENU_ITEM_DEFS}
    raw_default = str(payload.get("default_page", settings.get("default_page", "dashboard")))
    settings["default_page"] = raw_default if raw_default in known_page_ids else "dashboard"
    settings["weekly_summary_enabled"] = bool(payload.get("weekly_summary_enabled", False))
    settings["weekly_summary_time"] = str(payload.get("weekly_summary_time", settings.get("weekly_summary_time", "09:00")) or "09:00").strip() or "09:00"
    try:
        settings["mqtt_port"] = int(payload.get("mqtt_port", settings["mqtt_port"]))
    except (TypeError, ValueError):
        return {"error": "Ungültiger MQTT-Port."}
    try:
        settings["switchbot_scan_timeout"] = int(payload.get("switchbot_scan_timeout", settings["switchbot_scan_timeout"]))
    except (TypeError, ValueError):
        return {"error": "Ungültiger SwitchBot-Timeout."}
    for key in ("camera_focus", "camera_exposure", "camera_brightness", "camera_contrast", "camera_saturation", "camera_sharpness"):
        try:
            settings[key] = int(payload.get(key, settings[key]))
        except (TypeError, ValueError):
            return {"error": f"Ungültiger Kamerawert: {key}."}
    if settings["language"] not in {"de", "en"}:
        return {"error": "Ungültige Sprache."}
    if settings["datetime_format"] not in {"eu", "us", "iso"}:
        return {"error": "Ungültiges Datumsformat."}
    if settings["measurement_system"] not in {"metric", "imperial"}:
        return {"error": "Ungültiges Maßsystem."}
    if settings["temperature_unit"] not in {"c", "f"}:
        return {"error": "Ungültige Temperatureinheit."}
    if not re.fullmatch(r"[A-Za-z0-9€$£¥._ -]{1,12}", settings["currency"]):
        return {"error": "Ungültige Währung."}
    if settings["appearance_theme"] not in {"dark-blue", "dark-grey", "light"}:
        return {"error": "Ungültiges Farbschema."}
    if settings["accent_theme"] not in set(ACCENT_PRESETS) | {"custom"}:
        return {"error": "Ungültige Akzentfarbe."}
    if settings["telegram_enabled"] and (not settings["telegram_bot_token"] or not settings["telegram_chat_id"]):
        return {"error": "Telegram benötigt Bot-Token und Chat-ID."}
    if not settings["mqtt_host"]:
        return {"error": "MQTT-Host fehlt."}
    if settings["mqtt_port"] <= 0 or settings["mqtt_port"] > 65535:
        return {"error": "Ungültiger MQTT-Port."}
    if settings["mqtt_transport"] not in {"tcp", "websockets"}:
        return {"error": "Ungültiger MQTT-Transport."}
    if settings["water_sensor_enabled"] and not settings["water_sensor_topic"]:
        return {"error": "Reservoir-Sensor-Topic darf nicht leer sein."}
    if settings["pump_enabled"] and not settings["pump_topic"]:
        return {"error": "Pumpen-Topic darf nicht leer sein."}
    if settings["heater_enabled"] and not settings["heater_topic"]:
        return {"error": "Heizungs-Topic darf nicht leer sein."}
    if settings["exhaust_enabled"] and not settings["exhaust_topic"]:
        return {"error": "Abluft-Topic darf nicht leer sein."}
    if settings["light_enabled"] and not settings["light_topic"]:
        return {"error": "Licht-Topic darf nicht leer sein."}
    if settings["dehumidifier_enabled"] and not settings["dehumidifier_topic"]:
        return {"error": "Entfeuchter-Topic darf nicht leer sein."}
    if settings["humidifier_enabled"] and not settings["humidifier_topic"]:
        return {"error": "Luftbefeuchter-Topic darf nicht leer sein."}
    if settings["switchbot_mac"] and not re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", settings["switchbot_mac"]):
        return {"error": "Ungültige SwitchBot-MAC."}
    if settings["switchbot_scan_timeout"] < 3 or settings["switchbot_scan_timeout"] > 60:
        return {"error": "Ungültiger SwitchBot-Timeout."}
    data["app_settings"] = settings
    save_data(data)
    return {"message": tr("saved", settings["language"]), "app_settings": settings}


def save_camera_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = load_data()
    settings = get_app_settings()
    extracted = extract_camera_settings_from_payload(payload, settings)
    if "error" in extracted:
        return extracted
    settings.update(extracted)
    data["app_settings"] = settings
    save_data(data)
    return {"message": "📷 Kameraeinstellungen gespeichert.", "app_settings": settings}


def extract_camera_settings_from_payload(payload: Dict[str, Any] | None, base_settings: Dict[str, Any] | None = None) -> Dict[str, Any]:
    base = dict(base_settings or get_app_settings())
    incoming = payload or {}
    updates: Dict[str, Any] = {}
    updates["camera_auto_focus"] = bool(incoming.get("camera_auto_focus", base["camera_auto_focus"]))
    updates["camera_auto_exposure"] = bool(incoming.get("camera_auto_exposure", base["camera_auto_exposure"]))
    for key in ("camera_focus", "camera_exposure", "camera_brightness", "camera_contrast", "camera_saturation", "camera_sharpness"):
        try:
            updates[key] = int(incoming.get(key, base[key]))
        except (TypeError, ValueError):
            return {"error": f"Ungültiger Kamerawert: {key}."}
    return updates


def tr(key: str, language: str | None = None) -> str:
    lang = language or get_app_settings()["language"]
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get("de") or key


def format_local_date(date_str: str | None, language: str | None = None) -> str:
    if not date_str:
        return "–"
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return date_str
    return format_local_datetime(parsed, date_only=True, language=language)


def format_local_datetime(
    value: datetime | str | None,
    date_only: bool = False,
    language: str | None = None,
    datetime_format: str | None = None,
) -> str:
    if value is None:
        return "–"
    dt: datetime
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        parsed = None
        for parser in (datetime.fromisoformat,):
            try:
                parsed = parser(value)
                break
            except ValueError:
                continue
        if parsed is None:
            return value
        dt = parsed
    else:
        return str(value)
    settings = get_app_settings()
    lang = language or settings["language"]
    fmt = datetime_format or settings["datetime_format"]
    if fmt == "iso":
        return dt.strftime("%Y-%m-%d" if date_only else "%Y-%m-%d %H:%M")
    if fmt == "us":
        return dt.strftime("%m/%d/%Y" if date_only else "%m/%d/%Y %I:%M %p")
    return dt.strftime("%d/%m/%Y" if date_only else "%d/%m/%Y %H:%M")


def convert_temp_value(value: float | int | None, unit: str | None = None) -> float | None:
    if value is None:
        return None
    chosen = unit or get_app_settings()["temperature_unit"]
    numeric = float(value)
    if chosen == "f":
        return (numeric * 9 / 5) + 32
    return numeric


def format_temp(value: float | int | None, decimals: int = 1, unit: str | None = None) -> str:
    converted = convert_temp_value(value, unit)
    if converted is None:
        return "–"
    suffix = "°F" if (unit or get_app_settings()["temperature_unit"]) == "f" else "°C"
    return f"{converted:.{decimals}f}{suffix}"


def volume_unit_label(system: str | None = None) -> str:
    chosen = system or get_app_settings()["measurement_system"]
    return "gal" if chosen == "imperial" else "L"


def convert_volume_value(value: float | int | None, system: str | None = None) -> float | None:
    if value is None:
        return None
    chosen = system or get_app_settings()["measurement_system"]
    numeric = float(value)
    return numeric * 0.264172 if chosen == "imperial" else numeric


def display_fertilizer_rate_unit(unit: str, system: str | None = None) -> str:
    chosen = system or get_app_settings()["measurement_system"]
    normalized = "g/L" if str(unit).lower().startswith("g") else "ml/L"
    if chosen == "imperial":
        return "oz/gal" if normalized == "g/L" else "fl oz/gal"
    return normalized


def display_fertilizer_total_unit(unit: str, system: str | None = None) -> str:
    chosen = system or get_app_settings()["measurement_system"]
    normalized = "g/L" if str(unit).lower().startswith("g") else "ml/L"
    if chosen == "imperial":
        return "oz" if normalized == "g/L" else "fl oz"
    return "g" if normalized == "g/L" else "ml"


def convert_fertilizer_rate_value(value: float | int | None, unit: str, system: str | None = None) -> float | None:
    if value is None:
        return None
    chosen = system or get_app_settings()["measurement_system"]
    numeric = float(value)
    normalized = "g/L" if str(unit).lower().startswith("g") else "ml/L"
    if chosen != "imperial":
        return numeric
    if normalized == "g/L":
        return numeric * 3.785411784 / 28.349523125
    return numeric * 3.785411784 / 29.5735295625


def convert_fertilizer_total_value(value: float | int | None, unit: str, system: str | None = None) -> float | None:
    if value is None:
        return None
    chosen = system or get_app_settings()["measurement_system"]
    numeric = float(value)
    normalized = "g/L" if str(unit).lower().startswith("g") else "ml/L"
    if chosen != "imperial":
        return numeric
    if normalized == "g/L":
        return numeric / 28.349523125
    return numeric / 29.5735295625


def _normalize_clock_time(value: Any, fallback: str) -> str:
    candidate = str(value or "").strip()
    if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", candidate):
        return candidate
    return fallback


def _parse_clock_time(value: str) -> dt_time:
    hour, minute = value.split(":", 1)
    return dt_time(int(hour), int(minute))


def _time_in_window(current: dt_time, start: dt_time, end: dt_time) -> bool:
    if start == end:
        return False
    if start < end:
        return start <= current <= end
    return current >= start or current <= end


def get_fertilizer_units(data: Dict[str, Any]) -> Dict[str, str]:
    units = data.get("fertilizer_units") or {}
    if not isinstance(units, dict):
        return {}
    normalized: Dict[str, str] = {}
    for name, unit in units.items():
        normalized[str(name)] = "g/L" if str(unit).lower().startswith("g") else "ml/L"
    return normalized


def get_fertilizer_catalog(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    ferts = data.get("fertilizers", {})
    units = get_fertilizer_units(data)
    catalog: List[Dict[str, Any]] = []
    for name, schedule in ferts.items():
        if not isinstance(schedule, dict):
            continue
        cleaned_schedule: Dict[str, float] = {}
        for week_key, value in schedule.items():
            try:
                cleaned_schedule[str(int(float(week_key)))] = round(float(value or 0), 2)
            except (TypeError, ValueError):
                continue
        catalog.append(
            {
                "name": name,
                "unit": units.get(name, "ml/L"),
                "schedule": cleaned_schedule,
            }
        )
    return sorted(catalog, key=lambda item: item["name"].lower())

@app.context_processor
def inject_template_helpers() -> Dict[str, Any]:
    ui_settings = get_app_settings()
    _endpoint_map = {item["id"]: item["endpoint"] for item in MENU_ITEM_DEFS}
    _default_endpoint = _endpoint_map.get(ui_settings.get("default_page", "dashboard"), "index")
    from flask import url_for as _url_for
    try:
        _logo_url = _url_for(_default_endpoint)
    except Exception:
        _logo_url = "/"
    return {
        "ui_settings": ui_settings,
        "logo_url": _logo_url,
        "nav_items": get_navigation_items(ui_settings),
        "menu_editor_items": get_menu_editor_items(ui_settings),
        "tr": lambda key: tr(key, ui_settings["language"]),
        "format_local_date": lambda date_str: format_local_date(date_str, ui_settings["language"]),
        "format_local_datetime": lambda value, date_only=False: format_local_datetime(
            value, date_only=date_only, language=ui_settings["language"], datetime_format=ui_settings["datetime_format"]
        ),
        "format_temp": lambda value, decimals=1: format_temp(value, decimals=decimals, unit=ui_settings["temperature_unit"]),
        "volume_unit_label": lambda: volume_unit_label(ui_settings["measurement_system"]),
        "format_volume": lambda value, decimals=1: (
            "–" if convert_volume_value(value, ui_settings["measurement_system"]) is None
            else f"{convert_volume_value(value, ui_settings['measurement_system']):.{decimals}f}"
        ),
        "display_fertilizer_rate_unit": lambda unit: display_fertilizer_rate_unit(unit, ui_settings["measurement_system"]),
        "display_fertilizer_total_unit": lambda unit: display_fertilizer_total_unit(unit, ui_settings["measurement_system"]),
        "format_fertilizer_rate": lambda value, unit, decimals=2: (
            "–" if convert_fertilizer_rate_value(value, unit, ui_settings["measurement_system"]) is None
            else f"{convert_fertilizer_rate_value(value, unit, ui_settings['measurement_system']):.{decimals}f}"
        ),
        "format_fertilizer_total": lambda value, unit, decimals=2: (
            "–" if convert_fertilizer_total_value(value, unit, ui_settings["measurement_system"]) is None
            else f"{convert_fertilizer_total_value(value, unit, ui_settings['measurement_system']):.{decimals}f}"
        ),
    }


def append_bot_log(direction: str, payload: str) -> None:
    safe_payload = (payload or "").replace("\n", "\\n")
    try:
        with open(BOT_LOG_FILE, "a", encoding="utf-8") as f:
            timestamp = datetime.now().isoformat()
            f.write(f"{timestamp}||{direction}||{safe_payload}\n")
    except Exception:
        pass


def get_mqtt_settings() -> Dict[str, Any]:
    settings = get_app_settings()
    return {
        "host": settings["mqtt_host"],
        "port": int(settings["mqtt_port"]),
        "transport": settings["mqtt_transport"],
        "ws_path": settings["mqtt_ws_path"],
        "username": settings["mqtt_username"] or None,
        "password": settings["mqtt_password"] or None,
        "pump_enabled": settings["pump_enabled"],
        "heater_enabled": settings["heater_enabled"],
        "exhaust_enabled": settings["exhaust_enabled"],
        "water_sensor_enabled": settings["water_sensor_enabled"],
        "light_enabled": settings["light_enabled"],
        "dehumidifier_enabled": settings["dehumidifier_enabled"],
        "humidifier_enabled": settings["humidifier_enabled"],
        "pump_topic": settings["pump_topic"],
        "heater_topic": settings["heater_topic"],
        "exhaust_topic": settings["exhaust_topic"],
        "light_topic": settings["light_topic"],
        "dehumidifier_topic": settings["dehumidifier_topic"],
        "humidifier_topic": settings["humidifier_topic"],
        "water_sensor_topic": settings["water_sensor_topic"],
    }


def is_pump_enabled() -> bool:
    return bool(get_app_settings().get("pump_enabled", True))


def is_heater_enabled() -> bool:
    return bool(get_app_settings().get("heater_enabled", True))


def is_exhaust_enabled() -> bool:
    return bool(get_app_settings().get("exhaust_enabled", True))


def is_water_sensor_enabled() -> bool:
    return bool(get_app_settings().get("water_sensor_enabled", True))


def is_light_enabled() -> bool:
    return bool(get_app_settings().get("light_enabled", True))


def is_dehumidifier_enabled() -> bool:
    return bool(get_app_settings().get("dehumidifier_enabled", True))


def is_humidifier_enabled() -> bool:
    return bool(get_app_settings().get("humidifier_enabled", True))


def get_pump_topic() -> str:
    return get_mqtt_settings()["pump_topic"]


def get_heater_topic() -> str:
    return get_mqtt_settings()["heater_topic"]


def get_water_sensor_topic() -> str:
    return get_mqtt_settings()["water_sensor_topic"]


def get_light_topic() -> str:
    return get_mqtt_settings()["light_topic"]


def get_dehumidifier_topic() -> str:
    return get_mqtt_settings()["dehumidifier_topic"]


def get_humidifier_topic() -> str:
    return get_mqtt_settings()["humidifier_topic"]


def get_exhaust_settings() -> Dict[str, Any]:
    data = load_data()
    raw = data.get("exhaust_settings", {})
    settings = dict(DEFAULT_EXHAUST_SETTINGS)
    if isinstance(raw, dict):
        settings.update(raw)
    settings["enabled"] = bool(settings.get("enabled")) and is_exhaust_enabled()
    settings["debug_notify"] = bool(settings.get("debug_notify"))
    settings["plug_topic"] = get_mqtt_settings()["exhaust_topic"]
    settings["rh_turn_on_above"] = float(settings.get("rh_turn_on_above", DEFAULT_EXHAUST_SETTINGS["rh_turn_on_above"]))
    settings["rh_turn_off_below"] = float(settings.get("rh_turn_off_below", DEFAULT_EXHAUST_SETTINGS["rh_turn_off_below"]))
    settings["temp_force_on_above"] = float(settings.get("temp_force_on_above", DEFAULT_EXHAUST_SETTINGS["temp_force_on_above"]))
    settings["temp_allow_off_below"] = float(settings.get("temp_allow_off_below", DEFAULT_EXHAUST_SETTINGS["temp_allow_off_below"]))
    settings["min_on_seconds"] = max(60, int(float(settings.get("min_on_seconds", DEFAULT_EXHAUST_SETTINGS["min_on_seconds"]))))
    settings["min_off_seconds"] = max(60, int(float(settings.get("min_off_seconds", DEFAULT_EXHAUST_SETTINGS["min_off_seconds"]))))
    settings["max_off_time_before_refresh"] = max(300, int(float(settings.get("max_off_time_before_refresh", DEFAULT_EXHAUST_SETTINGS["max_off_time_before_refresh"]))))
    settings["forced_refresh_run_time"] = max(60, int(float(settings.get("forced_refresh_run_time", DEFAULT_EXHAUST_SETTINGS["forced_refresh_run_time"]))))
    settings["sensor_max_age_seconds"] = max(60, int(float(settings.get("sensor_max_age_seconds", DEFAULT_EXHAUST_SETTINGS["sensor_max_age_seconds"]))))
    settings["control_interval_seconds"] = max(15, int(float(settings.get("control_interval_seconds", DEFAULT_EXHAUST_SETTINGS["control_interval_seconds"]))))
    settings["sensor_median_samples"] = max(1, int(float(settings.get("sensor_median_samples", DEFAULT_EXHAUST_SETTINGS["sensor_median_samples"]))))
    return settings


def save_exhaust_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = load_data()
    current = get_exhaust_settings()
    updates = dict(current)
    try:
        updates["enabled"] = bool(payload.get("enabled", False))
        updates["debug_notify"] = bool(payload.get("debug_notify", False))
        updates["plug_topic"] = get_mqtt_settings()["exhaust_topic"]
        updates["rh_turn_on_above"] = float(payload.get("rh_turn_on_above", current["rh_turn_on_above"]))
        updates["rh_turn_off_below"] = float(payload.get("rh_turn_off_below", current["rh_turn_off_below"]))
        updates["temp_force_on_above"] = float(payload.get("temp_force_on_above", current["temp_force_on_above"]))
        updates["temp_allow_off_below"] = float(payload.get("temp_allow_off_below", current["temp_allow_off_below"]))
        updates["min_on_seconds"] = int(float(payload.get("min_on_seconds", current["min_on_seconds"])))
        updates["min_off_seconds"] = int(float(payload.get("min_off_seconds", current["min_off_seconds"])))
        updates["max_off_time_before_refresh"] = int(float(payload.get("max_off_time_before_refresh", current["max_off_time_before_refresh"])))
        updates["forced_refresh_run_time"] = int(float(payload.get("forced_refresh_run_time", current["forced_refresh_run_time"])))
        updates["sensor_max_age_seconds"] = int(float(payload.get("sensor_max_age_seconds", current["sensor_max_age_seconds"])))
        updates["control_interval_seconds"] = int(float(payload.get("control_interval_seconds", current["control_interval_seconds"])))
        updates["sensor_median_samples"] = int(float(payload.get("sensor_median_samples", current["sensor_median_samples"])))
    except (TypeError, ValueError):
        return {"error": "Ungültige Abluftwerte."}

    if updates["rh_turn_off_below"] >= updates["rh_turn_on_above"]:
        return {"error": "RH-AUS muss kleiner als RH-EIN sein."}
    if updates["temp_allow_off_below"] >= updates["temp_force_on_above"]:
        return {"error": "Temp AUS muss kleiner als Temp EIN sein."}
    if updates["control_interval_seconds"] < 15:
        return {"error": "Regelintervall muss mindestens 15 Sekunden betragen."}
    if updates["sensor_median_samples"] < 1 or updates["sensor_median_samples"] > 9:
        return {"error": "Median-Samples müssen zwischen 1 und 9 liegen."}

    data["exhaust_settings"] = updates
    save_data(data)
    settings_msg = (
        "🌬️⚙️ Exhaust settings updated\n"
        f"Auto: {'on' if updates['enabled'] else 'off'}\n"
        f"Debug notify: {'on' if updates['debug_notify'] else 'off'}\n"
        f"Plug: {updates['plug_topic']}\n"
        f"RH on/off: {updates['rh_turn_on_above']:.1f}% / {updates['rh_turn_off_below']:.1f}%\n"
        f"Temp on/off: {updates['temp_force_on_above']:.1f}°C / {updates['temp_allow_off_below']:.1f}°C\n"
        f"Min on/off: {updates['min_on_seconds']}s/{updates['min_off_seconds']}s\n"
        f"Refresh off/run: {updates['max_off_time_before_refresh']}s/{updates['forced_refresh_run_time']}s"
    )
    send_telegram_notification(settings_msg)
    return {"message": "🌬️ Abluft-Einstellungen gespeichert.", "exhaust_settings": updates}


def get_exhaust_topic() -> str:
    return get_mqtt_settings()["exhaust_topic"]


def get_light_cycle_settings() -> Dict[str, Any]:
    data = load_data()
    raw = data.get("light_cycle_settings", {})
    settings = dict(DEFAULT_LIGHT_CYCLE_SETTINGS)
    if isinstance(raw, dict):
        settings.update(raw)
    elif isinstance(data.get("light_settings"), dict):
        legacy = data.get("light_settings", {})
        settings["lights_on_start"] = legacy.get("lights_on_start", settings["lights_on_start"])
        settings["lights_on_end"] = legacy.get("lights_on_end", settings["lights_on_end"])
    elif isinstance(data.get("heater_settings"), dict):
        legacy = data.get("heater_settings", {})
        settings["lights_on_start"] = legacy.get("day_start", settings["lights_on_start"])
        settings["lights_on_end"] = legacy.get("day_end", settings["lights_on_end"])
    settings["lights_on_start"] = _normalize_clock_time(settings.get("lights_on_start"), DEFAULT_LIGHT_CYCLE_SETTINGS["lights_on_start"])
    settings["lights_on_end"] = _normalize_clock_time(settings.get("lights_on_end"), DEFAULT_LIGHT_CYCLE_SETTINGS["lights_on_end"])
    return settings


def save_light_cycle_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = load_data()
    current = get_light_cycle_settings()
    updates = dict(current)
    updates["lights_on_start"] = _normalize_clock_time(payload.get("lights_on_start"), current["lights_on_start"])
    updates["lights_on_end"] = _normalize_clock_time(payload.get("lights_on_end"), current["lights_on_end"])
    if updates["lights_on_start"] == updates["lights_on_end"]:
        return {"error": "Licht-an-Beginn und Licht-an-Ende dürfen nicht identisch sein."}
    if updates == current:
        return {"message": "💡 Lichtzyklus unverändert.", "light_cycle_settings": updates}
    data["light_cycle_settings"] = updates
    save_data(data)
    send_telegram_notification(
        "💡🕒 Light cycle updated\n"
        f"Window: {updates['lights_on_start']}-{updates['lights_on_end']}"
    )
    return {"message": "💡 Lichtzyklus gespeichert.", "light_cycle_settings": updates}


def get_light_settings() -> Dict[str, Any]:
    data = load_data()
    raw = data.get("light_settings", {})
    settings = dict(DEFAULT_LIGHT_SETTINGS)
    if isinstance(raw, dict):
        settings.update(raw)
    settings["enabled"] = bool(settings.get("enabled")) and is_light_enabled()
    settings["debug_notify"] = bool(settings.get("debug_notify"))
    settings["control_interval_seconds"] = max(15, int(float(settings.get("control_interval_seconds", DEFAULT_LIGHT_SETTINGS["control_interval_seconds"]))))
    return settings


def save_light_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = load_data()
    current = get_light_settings()
    updates = dict(current)
    app_settings = get_app_settings()
    try:
        updates["enabled"] = bool(payload.get("enabled", False))
        updates["debug_notify"] = bool(payload.get("debug_notify", False))
        updates["control_interval_seconds"] = int(float(payload.get("control_interval_seconds", current["control_interval_seconds"])))
    except (TypeError, ValueError):
        return {"error": "Ungültige Lichtwerte."}
    if updates["control_interval_seconds"] < 15:
        return {"error": "Regelintervall muss mindestens 15 Sekunden betragen."}
    data["light_settings"] = updates
    if "light_debug_card_enabled" in payload:
        app_settings["light_debug_card_enabled"] = bool(payload.get("light_debug_card_enabled", app_settings["light_debug_card_enabled"]))
        data["app_settings"] = app_settings
    save_data(data)
    return {"message": "💡 Lichteinstellungen gespeichert.", "light_settings": updates, "app_settings": app_settings}


def get_timelapse_settings() -> Dict[str, Any]:
    data = load_data()
    raw = data.get("timelapse_settings", {})
    settings = dict(DEFAULT_TIMELAPSE_SETTINGS)
    if isinstance(raw, dict):
        settings.update(raw)
    settings["enabled"] = bool(settings.get("enabled"))
    settings["light_only"] = bool(settings.get("light_only"))
    try:
        rotation = int(float(settings.get("rotation_degrees", DEFAULT_TIMELAPSE_SETTINGS["rotation_degrees"])))
    except (TypeError, ValueError):
        rotation = DEFAULT_TIMELAPSE_SETTINGS["rotation_degrees"]
    settings["rotation_degrees"] = rotation if rotation in {0, 90, 180, 270} else 0
    settings["interval_minutes"] = max(1, int(float(settings.get("interval_minutes", DEFAULT_TIMELAPSE_SETTINGS["interval_minutes"]))))
    return settings


def save_timelapse_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = load_data()
    current = get_timelapse_settings()
    updates = dict(current)
    try:
        updates["enabled"] = bool(payload.get("enabled", False))
        updates["light_only"] = bool(payload.get("light_only", False))
        updates["rotation_degrees"] = int(float(payload.get("rotation_degrees", current["rotation_degrees"])))
        updates["interval_minutes"] = int(float(payload.get("interval_minutes", current["interval_minutes"])))
    except (TypeError, ValueError):
        return {"error": "Ungültige Timelapse-Werte."}
    if updates["rotation_degrees"] not in {0, 90, 180, 270}:
        return {"error": "Rotation muss 0, 90, 180 oder 270 sein."}
    if updates["interval_minutes"] < 1:
        return {"error": "Intervall muss mindestens 1 Minute betragen."}
    data["timelapse_settings"] = updates
    data["photo_rotation_degrees"] = updates["rotation_degrees"]
    save_data(data)
    return {"message": "🎞️ Timelapse-Einstellungen gespeichert.", "timelapse_settings": updates}


def get_humidity_settings() -> Dict[str, Any]:
    data = load_data()
    raw = data.get("humidity_settings", {})
    settings = dict(DEFAULT_HUMIDITY_SETTINGS)
    if isinstance(raw, dict):
        settings.update(raw)
    has_devices = is_dehumidifier_enabled() or is_humidifier_enabled()
    has_exhaust = is_exhaust_enabled()
    settings["control_method"] = settings.get("control_method") if settings.get("control_method") in {"devices", "exhaust"} else "devices"
    if has_exhaust and not has_devices:
        settings["control_method"] = "exhaust"
    elif has_devices and not has_exhaust:
        settings["control_method"] = "devices"
    settings["exhaust_control_mode"] = settings.get("exhaust_control_mode") if settings.get("exhaust_control_mode") in {"sensor", "cycle"} else "sensor"
    settings["enabled"] = bool(settings.get("enabled"))
    if settings["control_method"] == "devices":
        settings["enabled"] = settings["enabled"] and has_devices
    else:
        settings["enabled"] = settings["enabled"] and has_exhaust
    settings["debug_notify"] = bool(settings.get("debug_notify"))
    settings["rh_upper_threshold"] = float(settings.get("rh_upper_threshold", DEFAULT_HUMIDITY_SETTINGS["rh_upper_threshold"]))
    settings["rh_lower_threshold"] = float(settings.get("rh_lower_threshold", DEFAULT_HUMIDITY_SETTINGS["rh_lower_threshold"]))
    settings["cycle_on_seconds"] = max(60, int(float(settings.get("cycle_on_seconds", DEFAULT_HUMIDITY_SETTINGS["cycle_on_seconds"]))))
    settings["cycle_off_seconds"] = max(60, int(float(settings.get("cycle_off_seconds", DEFAULT_HUMIDITY_SETTINGS["cycle_off_seconds"]))))
    settings["min_on_seconds"] = max(60, int(float(settings.get("min_on_seconds", DEFAULT_HUMIDITY_SETTINGS["min_on_seconds"]))))
    settings["min_off_seconds"] = max(60, int(float(settings.get("min_off_seconds", DEFAULT_HUMIDITY_SETTINGS["min_off_seconds"]))))
    settings["sensor_max_age_seconds"] = max(60, int(float(settings.get("sensor_max_age_seconds", DEFAULT_HUMIDITY_SETTINGS["sensor_max_age_seconds"]))))
    settings["control_interval_seconds"] = max(15, int(float(settings.get("control_interval_seconds", DEFAULT_HUMIDITY_SETTINGS["control_interval_seconds"]))))
    settings["sensor_median_samples"] = max(1, int(float(settings.get("sensor_median_samples", DEFAULT_HUMIDITY_SETTINGS["sensor_median_samples"]))))
    return settings


def save_humidity_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = load_data()
    current = get_humidity_settings()
    updates = dict(current)
    app_settings = get_app_settings()
    try:
        updates["enabled"] = bool(payload.get("enabled", False))
        updates["debug_notify"] = bool(payload.get("debug_notify", False))
        updates["control_method"] = str(payload.get("control_method", current["control_method"]) or "").strip()
        updates["exhaust_control_mode"] = str(payload.get("exhaust_control_mode", current["exhaust_control_mode"]) or "").strip()
        updates["rh_upper_threshold"] = float(payload.get("rh_upper_threshold", current["rh_upper_threshold"]))
        updates["rh_lower_threshold"] = float(payload.get("rh_lower_threshold", current["rh_lower_threshold"]))
        updates["cycle_on_seconds"] = int(float(payload.get("cycle_on_seconds", current["cycle_on_seconds"])))
        updates["cycle_off_seconds"] = int(float(payload.get("cycle_off_seconds", current["cycle_off_seconds"])))
        updates["min_on_seconds"] = int(float(payload.get("min_on_seconds", current["min_on_seconds"])))
        updates["min_off_seconds"] = int(float(payload.get("min_off_seconds", current["min_off_seconds"])))
        updates["sensor_max_age_seconds"] = int(float(payload.get("sensor_max_age_seconds", current["sensor_max_age_seconds"])))
        updates["control_interval_seconds"] = int(float(payload.get("control_interval_seconds", current["control_interval_seconds"])))
        updates["sensor_median_samples"] = int(float(payload.get("sensor_median_samples", current["sensor_median_samples"])))
    except (TypeError, ValueError):
        return {"error": "Ungültige Feuchteregelungswerte."}
    if updates["control_method"] not in {"devices", "exhaust"}:
        return {"error": "Ungültige Feuchte-Steuerung."}
    if updates["exhaust_control_mode"] not in {"sensor", "cycle"}:
        return {"error": "Ungültiger Abluft-Modus."}
    if updates["control_method"] == "exhaust" and not is_exhaust_enabled():
        return {"error": "Abluft muss aktiviert sein."}
    if updates["control_method"] == "devices" and not (is_dehumidifier_enabled() or is_humidifier_enabled()):
        return {"error": "Befeuchter oder Entfeuchter muss aktiviert sein."}
    if updates["rh_lower_threshold"] >= updates["rh_upper_threshold"]:
        return {"error": "Untere RLF-Schwelle muss kleiner als die obere sein."}
    if updates["control_interval_seconds"] < 15:
        return {"error": "Regelintervall muss mindestens 15 Sekunden betragen."}
    if updates["sensor_median_samples"] < 1 or updates["sensor_median_samples"] > 9:
        return {"error": "Median-Samples müssen zwischen 1 und 9 liegen."}
    data["humidity_settings"] = updates
    if "exhaust_debug_card_enabled" in payload:
        app_settings["exhaust_debug_card_enabled"] = bool(payload.get("exhaust_debug_card_enabled", app_settings["exhaust_debug_card_enabled"]))
        data["app_settings"] = app_settings
    save_data(data)
    return {"message": "💧 Feuchteregelung gespeichert.", "humidity_settings": updates, "app_settings": app_settings}


def get_power_settings() -> Dict[str, Any]:
    data = load_data()
    raw = data.get("power_settings", {})
    settings = dict(DEFAULT_POWER_SETTINGS)
    if isinstance(raw, dict):
        settings.update(raw)
    try:
        settings["price_per_kwh"] = max(0.0, float(settings.get("price_per_kwh", DEFAULT_POWER_SETTINGS["price_per_kwh"])))
    except (TypeError, ValueError):
        settings["price_per_kwh"] = DEFAULT_POWER_SETTINGS["price_per_kwh"]
    return settings


def save_power_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = load_data()
    current = get_power_settings()
    settings = dict(current)
    app_settings = get_app_settings()
    try:
        settings["price_per_kwh"] = float(payload.get("price_per_kwh", current["price_per_kwh"]))
    except (TypeError, ValueError):
        return {"error": "Ungültiger kWh-Preis."}
    if settings["price_per_kwh"] < 0:
        return {"error": "kWh-Preis darf nicht negativ sein."}
    currency = payload.get("currency")
    if currency is not None:
        currency = str(currency).strip() or "EUR"
        if not re.fullmatch(r"[A-Za-z0-9€$£¥._ -]{1,12}", currency):
            return {"error": "Ungültige Währung."}
        app_settings["currency"] = currency
        data["app_settings"] = app_settings
    data["power_settings"] = settings
    save_data(data)
    return {
        "message": "⚡ Power-Einstellungen gespeichert.",
        "power_settings": settings,
        "currency": app_settings["currency"],
        "currency_symbol": currency_symbol(app_settings["currency"]),
    }


def _send_telegram_worker(bot_token: str, chat_id: str, text: str) -> None:
    """Runs in a background thread so Telegram failures never block automation loops."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.ok:
            append_bot_log("OUT", text)
        else:
            print(f"[telegram] Fehler: {response.status_code} {response.text[:200]}", flush=True)
    except Exception as exc:
        print(f"[telegram] Sendefehler: {exc}", flush=True)


def send_telegram_notification(text: str) -> None:
    settings = get_app_settings()
    if not settings.get("telegram_enabled", True):
        return
    bot_token = settings.get("telegram_bot_token") or TELEGRAM_BOT_TOKEN
    chat_id = settings.get("telegram_chat_id") or TELEGRAM_CHAT_ID
    if not bot_token or not chat_id:
        return
    # Run in background thread so network latency/errors never block the calling thread
    t = threading.Thread(
        target=_send_telegram_worker,
        args=(bot_token, chat_id, text),
        daemon=True,
    )
    t.start()


def get_heater_settings() -> Dict[str, Any]:
    data = load_data()
    raw = data.get("heater_settings", {})
    settings = dict(DEFAULT_HEATER_SETTINGS)
    if isinstance(raw, dict):
        settings.update(raw)
    settings["enabled"] = bool(settings.get("enabled")) and is_heater_enabled()
    settings["debug_notify"] = bool(settings.get("debug_notify"))
    settings["day_target_c"] = float(settings.get("day_target_c", DEFAULT_HEATER_SETTINGS["day_target_c"]))
    settings["night_target_c"] = float(settings.get("night_target_c", DEFAULT_HEATER_SETTINGS["night_target_c"]))
    settings["on_below_offset_c"] = max(0.05, float(settings.get("on_below_offset_c", DEFAULT_HEATER_SETTINGS["on_below_offset_c"])))
    settings["off_above_offset_c"] = max(0.05, float(settings.get("off_above_offset_c", DEFAULT_HEATER_SETTINGS["off_above_offset_c"])))
    settings["min_on_seconds"] = max(60, int(float(settings.get("min_on_seconds", DEFAULT_HEATER_SETTINGS["min_on_seconds"]))))
    settings["min_off_seconds"] = max(60, int(float(settings.get("min_off_seconds", DEFAULT_HEATER_SETTINGS["min_off_seconds"]))))
    settings["sensor_max_age_seconds"] = max(300, int(float(settings.get("sensor_max_age_seconds", DEFAULT_HEATER_SETTINGS["sensor_max_age_seconds"]))))
    settings["control_interval_seconds"] = max(15, int(float(settings.get("control_interval_seconds", DEFAULT_HEATER_SETTINGS["control_interval_seconds"]))))
    settings["sensor_median_samples"] = max(1, int(float(settings.get("sensor_median_samples", DEFAULT_HEATER_SETTINGS["sensor_median_samples"]))))
    return settings


def save_heater_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = load_data()
    current = get_heater_settings()
    updates = dict(current)
    app_settings = get_app_settings()
    try:
        updates["enabled"] = bool(payload.get("enabled", False))
        updates["debug_notify"] = bool(payload.get("debug_notify", False))
        updates["day_target_c"] = float(payload.get("day_target_c", current["day_target_c"]))
        updates["night_target_c"] = float(payload.get("night_target_c", current["night_target_c"]))
        updates["on_below_offset_c"] = float(payload.get("on_below_offset_c", current["on_below_offset_c"]))
        updates["off_above_offset_c"] = float(payload.get("off_above_offset_c", current["off_above_offset_c"]))
        updates["min_on_seconds"] = int(float(payload.get("min_on_seconds", current["min_on_seconds"])))
        updates["min_off_seconds"] = int(float(payload.get("min_off_seconds", current["min_off_seconds"])))
        updates["sensor_max_age_seconds"] = int(float(payload.get("sensor_max_age_seconds", current["sensor_max_age_seconds"])))
        updates["control_interval_seconds"] = int(float(payload.get("control_interval_seconds", current["control_interval_seconds"])))
        updates["sensor_median_samples"] = int(float(payload.get("sensor_median_samples", current["sensor_median_samples"])))
    except (TypeError, ValueError):
        return {"error": "Ungültige Heizungswerte."}

    if updates["day_target_c"] < 5 or updates["day_target_c"] > 35:
        return {"error": "Licht-an-Temperatur muss zwischen 5 und 35°C liegen."}
    if updates["night_target_c"] < 5 or updates["night_target_c"] > 35:
        return {"error": "Licht-aus-Temperatur muss zwischen 5 und 35°C liegen."}
    if updates["on_below_offset_c"] <= 0 or updates["off_above_offset_c"] <= 0:
        return {"error": "Hysterese-Werte müssen größer als 0 sein."}
    if updates["control_interval_seconds"] < 15:
        return {"error": "Regelintervall muss mindestens 15 Sekunden betragen."}
    if updates["sensor_median_samples"] < 1 or updates["sensor_median_samples"] > 9:
        return {"error": "Median-Samples müssen zwischen 1 und 9 liegen."}

    data["heater_settings"] = updates
    if "heater_debug_card_enabled" in payload:
        app_settings["heater_debug_card_enabled"] = bool(payload.get("heater_debug_card_enabled", app_settings["heater_debug_card_enabled"]))
        data["app_settings"] = app_settings
    save_data(data)
    settings_msg = (
        "🔥⚙️ Heater settings updated\n"
        f"Auto: {'on' if updates['enabled'] else 'off'}\n"
        f"Debug notify: {'on' if updates['debug_notify'] else 'off'}\n"
        f"Lights on: {updates['day_target_c']:.1f}°C\n"
        f"Lights off: {updates['night_target_c']:.1f}°C\n"
        f"On below: {updates['on_below_offset_c']:.2f}°C\n"
        f"Off above: {updates['off_above_offset_c']:.2f}°C\n"
        f"Min on/off: {updates['min_on_seconds']}s/{updates['min_off_seconds']}s\n"
        f"Interval: {updates['control_interval_seconds']}s\n"
        f"Median samples: {updates['sensor_median_samples']}"
    )
    send_telegram_notification(settings_msg)
    return {"message": "🔥 Heizungs-Defaults gespeichert.", "heater_settings": updates, "app_settings": app_settings}


def parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None


def get_week_and_phase(sprout_date: str | None, flower_date: str | None) -> Dict[str, Any]:
    week_info = "unbekannt"
    phase = "Veg"
    weeks = 0
    sprout_dt = parse_date(sprout_date)
    flower_dt = parse_date(flower_date)
    today = datetime.now()

    if sprout_dt:
        days = (today - sprout_dt).days
        weeks = days // 7 + 1
        week_info = f"Woche {weeks} ({days} Tage)"
    if flower_dt and today >= flower_dt:
        phase = "Blüte"
    return {"week_info": week_info, "phase": phase, "week_number": weeks or 1}


def compute_vpd(temperature: float | None, humidity: float | None) -> float | None:
    """Calculate vapor pressure deficit (kPa) from temperature (°C) and humidity (%)."""
    if temperature is None or humidity is None:
        return None
    try:
        es = 6.112 * math.exp((17.67 * temperature) / (temperature + 243.5))  # hPa
        vpd = (1.0 - (humidity / 100.0)) * es
        return round(vpd / 10.0, 2)  # convert hPa to kPa
    except Exception:
        return None


def determine_vpd_target(stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map grow stage to recommended VPD window.
    Based on DimLux Lighting chart:
      - Propagation / Early Veg: 0.4–0.8 kPa
      - Late Veg / Early Flower: 0.8–1.2 kPa
      - Mid / Late Flower: 1.2–1.6 kPa
    """
    phase = stats.get("phase") or "Veg"
    week = stats.get("week_number") or 1
    flower_week = stats.get("flower_week") or 1

    if phase == "Veg":
        if week <= 3:
            label = "Propagation / Early Veg"
            span = (0.4, 0.8)
        else:
            label = "Late Veg"
            span = (0.8, 1.2)
    else:
        if flower_week <= 2:
            label = "Early Flower"
            span = (0.8, 1.2)
        else:
            label = "Mid / Late Flower"
            span = (1.2, 1.6)

    return {"label": label, "min": span[0], "max": span[1]}


def get_image_stats() -> Dict[str, Any]:
    key = "image_stats"
    now = time.monotonic()
    if key in _FS_CACHE and now - _FS_CACHE[key][0] < _FS_CACHE_TTL:
        return _FS_CACHE[key][1]
    entries: List[tuple[float, int, str]] = []
    seen = set()
    for directory in PHOTO_DIRS:
        if not directory or not os.path.exists(directory):
            continue
        for file_path in glob.glob(os.path.join(directory, "*.jpg")):
            if file_path in seen:
                continue
            try:
                size = os.path.getsize(file_path)
                mtime = os.path.getmtime(file_path)
            except OSError:
                continue
            seen.add(file_path)
            entries.append((mtime, size, file_path))
    if not entries:
        result = {"count": 0, "latest": None, "oldest": None, "size_gb": 0}
        _FS_CACHE[key] = (now, result)
        return result
    entries.sort(key=lambda item: item[0])
    total_size = sum(size for _, size, _ in entries)
    latest = format_local_datetime(datetime.fromtimestamp(entries[-1][0]))
    oldest = format_local_datetime(datetime.fromtimestamp(entries[0][0]))
    result = {
        "count": len(entries),
        "latest": latest,
        "oldest": oldest,
        "size_gb": round(total_size / (1024 ** 3), 2),
    }
    _FS_CACHE[key] = (now, result)
    return result


def read_bot_log(limit: int = 30) -> List[Dict[str, str]]:
    if not os.path.exists(BOT_LOG_FILE):
        return []
    entries = []
    try:
        with open(BOT_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        for line in lines:
            parts = line.strip().split("||", 2)
            if len(parts) == 3:
                entries.append(
                    {
                        "timestamp": parts[0],
                        "direction": parts[1],
                        "text": parts[2].replace("\\n", "\n"),
                    }
                )
    except Exception:
        pass
    return entries


def _get_latest_photo_from_dirs(directories: List[str]) -> Dict[str, Any] | None:
    key = f"latest_photo:{','.join(directories)}"
    now = time.monotonic()
    if key in _FS_CACHE and now - _FS_CACHE[key][0] < _FS_CACHE_TTL:
        return _FS_CACHE[key][1]
    newest_path = None
    newest_mtime = 0.0
    for directory in directories:
        if not os.path.exists(directory):
            continue
        for file_path in glob.glob(os.path.join(directory, "*.jpg")):
            try:
                mtime = os.path.getmtime(file_path)
            except FileNotFoundError:
                continue
            if mtime > newest_mtime:
                newest_mtime = mtime
                newest_path = file_path
    if not newest_path:
        _FS_CACHE[key] = (now, None)
        return None
    dt = datetime.fromtimestamp(newest_mtime)
    ts = format_local_datetime(dt)
    result = {"path": newest_path, "timestamp": ts, "raw_timestamp": dt.isoformat()}
    _FS_CACHE[key] = (now, result)
    return result


def get_latest_timelapse_photo() -> Dict[str, Any] | None:
    return _get_latest_photo_from_dirs(TIMELAPSE_DIRS)


def get_latest_timelapse_capture() -> Dict[str, Any] | None:
    return _get_latest_photo_from_dirs(TIMELAPSE_ONLY_DIRS)


def get_camera_test_image_info() -> Dict[str, Any] | None:
    raw = load_data().get("camera_test_image")
    if not isinstance(raw, dict):
        return None
    path = str(raw.get("path") or "").strip()
    if not path or not os.path.exists(path):
        return None
    timestamp = raw.get("timestamp")
    raw_timestamp = raw.get("raw_timestamp")
    if not timestamp or not raw_timestamp:
        try:
            mtime = os.path.getmtime(path)
            dt = datetime.fromtimestamp(mtime)
            timestamp = timestamp or format_local_datetime(dt)
            raw_timestamp = raw_timestamp or dt.isoformat()
        except Exception:
            pass
    return {
        "path": path,
        "timestamp": timestamp or os.path.basename(path),
        "raw_timestamp": raw_timestamp or timestamp or os.path.basename(path),
        "settings": raw.get("settings") if isinstance(raw.get("settings"), dict) else None,
    }


def _get_video_metadata(path: str) -> Dict[str, Any]:
    """Return duration seconds using OpenCV if available."""
    if not cv2:
        return {"duration": None}
    try:
        cap = cv2.VideoCapture(path)
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        cap.release()
        if fps > 0 and frames > 0:
            return {"duration": round(frames / fps, 1)}
    except Exception:
        pass
    return {"duration": None}


def get_timelapse_video_info() -> Dict[str, Any]:
    """Return info about the rendered timelapse video, if it exists."""
    if not os.path.exists(TIMELAPSE_VIDEO_FILE):
        return {"exists": False, "timestamp": None, "size_bytes": 0, "duration": None}
    try:
        mtime = os.path.getmtime(TIMELAPSE_VIDEO_FILE)
        ts = format_local_datetime(datetime.fromtimestamp(mtime))
        size = os.path.getsize(TIMELAPSE_VIDEO_FILE)
        meta = _get_video_metadata(TIMELAPSE_VIDEO_FILE)
    except Exception:
        ts = None
        size = 0
        meta = {"duration": None}
    return {
        "exists": True,
        "timestamp": ts,
        "size_bytes": size,
        "duration": meta.get("duration"),
    }


def build_info_lines(data: Dict[str, Any], stats: Dict[str, Any]) -> List[Dict[str, str]]:
    lang = get_app_settings()["language"]

    def fmt(date_str):
        if not date_str:
            return tr("unknown", lang)
        try:
            return format_local_date(date_str, lang)
        except ValueError:
            return date_str

    lines = [
        {"label": tr("info_grow_name", lang), "value": data.get("grow_name", "PlantWatch")},
        {"label": tr("info_start", lang), "value": fmt(data.get("start_date"))},
        {"label": tr("info_sprout", lang), "value": fmt(data.get("sprout_date"))},
        {"label": tr("info_last_watering", lang), "value": fmt(data.get("last_watering"))},
        {"label": tr("info_phase", lang), "value": stats["phase"]},
        {"label": tr("info_current_week", lang), "value": stats["week_info"]},
    ]
    if data.get("flower_date"):
        lines.append({"label": tr("info_flower_start", lang), "value": fmt(data.get("flower_date"))})
    return lines


def parse_sensor_from_filename(path: str) -> Dict[str, Any] | None:
    name = os.path.basename(path)
    parts = name.split("_")
    if len(parts) < 4:
        return None
    timestamp_raw = parts[0]
    temp_raw = parts[-2]
    hum_raw = parts[-1].split(".jpg")[0]
    try:
        ts = datetime.strptime(timestamp_raw, "%d-%m-%Y-%H:%M:%S")
        temp = float(temp_raw.replace("C", "").replace(",", "."))
        hum = float(hum_raw.replace("p", "").replace(",", "."))
    except Exception:
        return None
    return {"timestamp": ts, "temperature": temp, "humidity": hum}


def get_sensor_history(hours: int = 72) -> List[Dict[str, Any]]:
    if not os.path.exists(SENSOR_DB):
        return []
    cutoff = datetime.now() - timedelta(hours=hours)
    rows: List[Dict[str, Any]] = []
    try:
        with sqlite3.connect(SENSOR_DB) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT timestamp, temperature, humidity
                FROM sensor_readings
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
                """,
                (cutoff.isoformat(),),
            ).fetchall()
    except Exception:
        return []
    history = []
    for row in rows:
        try:
            dt = datetime.fromisoformat(row["timestamp"])
            label = dt.strftime("%d.%m %H:%M")
        except ValueError:
            label = row["timestamp"]
        vpd = compute_vpd(row["temperature"], row["humidity"])
        history.append(
            {
                "timestamp": label,
                "temperature": row["temperature"],
                "humidity": row["humidity"],
                "vpd": vpd,
            }
        )
    return history


def get_latest_sensor_point() -> Dict[str, Any] | None:
    if not os.path.exists(SENSOR_DB):
        return None
    try:
        with sqlite3.connect(SENSOR_DB) as conn:
            row = conn.execute(
                "SELECT timestamp, temperature, humidity FROM sensor_readings ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    ts_raw, temp, hum = row
    try:
        parsed_dt = datetime.fromisoformat(ts_raw)
        ts_fmt = format_local_datetime(parsed_dt)
        raw_ts = parsed_dt.isoformat()
    except ValueError:
        ts_fmt = ts_raw
        raw_ts = ts_raw
    vpd = compute_vpd(temp, hum)
    return {"timestamp": ts_fmt, "raw_timestamp": raw_ts, "temperature": temp, "humidity": hum, "vpd": vpd}


def get_latest_sensor_reading_raw() -> Dict[str, Any] | None:
    if not os.path.exists(SENSOR_DB):
        return None
    try:
        with sqlite3.connect(SENSOR_DB) as conn:
            row = conn.execute(
                "SELECT timestamp, temperature, humidity FROM sensor_readings ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    ts_raw, temp, hum = row
    try:
        ts = datetime.fromisoformat(ts_raw)
    except ValueError:
        return None
    return {"timestamp": ts, "temperature": temp, "humidity": hum}


def get_recent_temperatures(limit: int = 3) -> List[float]:
    if not os.path.exists(SENSOR_DB) or limit <= 0:
        return []
    try:
        with sqlite3.connect(SENSOR_DB) as conn:
            rows = conn.execute(
                """
                SELECT temperature
                FROM sensor_readings
                WHERE temperature IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    except Exception:
        return []
    return [float(row[0]) for row in rows if row and row[0] is not None]


def get_live_sensor_reading() -> Dict[str, Any] | None:
    with LIVE_SENSOR_CACHE_LOCK:
        cached = LIVE_SENSOR_CACHE.get("reading")
        fetched_at = LIVE_SENSOR_CACHE.get("fetched_at")
        if cached and isinstance(fetched_at, datetime):
            if (datetime.now() - fetched_at).total_seconds() <= 10:
                return dict(cached)
    python_executable = VENV_PYTHON if os.path.exists(VENV_PYTHON) else "python3"
    cmd = [python_executable, CAM_SCRIPT, "--sensors-only"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=35,
            check=False,
            cwd=SCRIPT_DIR,
        )
    except subprocess.TimeoutExpired:
        print("[heater-controller] Live-Sensor Timeout.", flush=True)
        return None
    except Exception as exc:
        print(f"[heater-controller] Live-Sensor Fehler: {exc}", flush=True)
        return None

    output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    temp_match = re.search(r"Temperatur:\s*(-?\d+(?:[.,]\d+)?)°C", output)
    hum_match = re.search(r"Luftfeuchtigkeit:\s*(\d+(?:[.,]\d+)?)%", output)
    if not temp_match:
        print("[heater-controller] Live-Sensor lieferte keine Temperatur.", flush=True)
        return None
    try:
        temperature = float(temp_match.group(1).replace(",", "."))
        humidity = float(hum_match.group(1).replace(",", ".")) if hum_match else None
    except ValueError:
        return None
    reading = {
        "timestamp": datetime.now(),
        "temperature": temperature,
        "humidity": humidity,
        "raw_output": output,
    }
    with LIVE_SENSOR_CACHE_LOCK:
        LIVE_SENSOR_CACHE["reading"] = reading
        LIVE_SENSOR_CACHE["fetched_at"] = datetime.now()
    return reading


def compute_sensor_stats(hours: int | None = None) -> Dict[str, Any]:
    if not os.path.exists(SENSOR_DB):
        return {}
    params: List[Any] = []
    query = """
        SELECT
            MIN(temperature),
            MAX(temperature),
            AVG(temperature),
            MIN(humidity),
            MAX(humidity),
            AVG(humidity)
        FROM sensor_readings
    """
    if hours:
        cutoff = datetime.now() - timedelta(hours=hours)
        query += " WHERE timestamp >= ?"
        params.append(cutoff.isoformat())
    try:
        with sqlite3.connect(SENSOR_DB) as conn:
            row = conn.execute(query, params).fetchone()
    except Exception:
        return {}
    if not row:
        return {}
    t_min, t_max, t_avg, h_min, h_max, h_avg = row
    return {
        "temp_min": round(t_min, 2) if t_min is not None else None,
        "temp_max": round(t_max, 2) if t_max is not None else None,
        "temp_avg": round(t_avg, 2) if t_avg is not None else None,
        "hum_min": round(h_min, 2) if h_min is not None else None,
        "hum_max": round(h_max, 2) if h_max is not None else None,
        "hum_avg": round(h_avg, 2) if h_avg is not None else None,
    }


def fetch_sensor_history(
    hours: int | None = None,
    limit: int = 400,
    start: datetime | None = None,
    end: datetime | None = None,
) -> List[Dict[str, Any]]:
    if not os.path.exists(SENSOR_DB):
        return []
    query = "SELECT timestamp, temperature, humidity FROM sensor_readings"
    params: List[Any] = []
    conditions: List[str] = []
    if start:
        conditions.append("timestamp >= ?")
        params.append(start.isoformat())
    elif hours:
        cutoff = datetime.now() - timedelta(hours=hours)
        conditions.append("timestamp >= ?")
        params.append(cutoff.isoformat())
    if end:
        conditions.append("timestamp <= ?")
        params.append(end.isoformat())
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    try:
        with sqlite3.connect(SENSOR_DB) as conn:
            rows = conn.execute(query, params).fetchall()
    except Exception:
        return []

    history = []
    for ts, temp, hum in reversed(rows):
        try:
            dt = datetime.fromisoformat(ts)
            label = format_local_datetime(dt)
            raw_ts = dt.isoformat()
        except ValueError:
            label = ts
            raw_ts = ts
        vpd = compute_vpd(temp, hum)
        history.append({"timestamp": label, "raw_timestamp": raw_ts, "temperature": temp, "humidity": hum, "vpd": vpd})
    return history


def compute_dashboard_data() -> Dict[str, Any]:
    data = load_data()
    lang = get_app_settings()["language"]
    stats = get_week_and_phase(data.get("sprout_date"), data.get("flower_date"))
    today = datetime.now()

    last_watering = parse_date(data.get("last_watering"))
    days_since_watering = (datetime.now() - last_watering).days if last_watering else None
    next_due = None
    if days_since_watering is not None:
        remaining = CHECK_INTERVAL_DAYS - days_since_watering
        next_due = "Now!" if remaining <= 0 and lang == "en" else "Jetzt!" if remaining <= 0 else (f"in {remaining} days" if lang == "en" else f"in {remaining} Tagen")

    def parse_any(date_str: str | None) -> datetime | None:
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return None

    base_dt = parse_any(data.get("sprout_date")) or parse_any(data.get("start_date"))
    days_since_start = (today - base_dt).days if base_dt else None

    flower_dt = parse_any(data.get("flower_date"))
    flower_days = None
    flower_week = None
    if flower_dt and today >= flower_dt:
        flower_days = (today - flower_dt).days
        flower_week = flower_days // 7 + 1

    ferts = data.get("fertilizers", {})
    fert_units = get_fertilizer_units(data)
    current_week = max(1, stats["week_number"])
    fert_list = []
    for name, schedule in ferts.items():
        ml = float(schedule.get(str(current_week), 0) or 0)
        fert_list.append(
            {
                "name": name,
                "amount_per_l": ml,
                "unit": fert_units.get(name, "ml/L"),
                "current_week": current_week,
            }
        )

    image_stats = get_image_stats()
    latest_photo = get_latest_timelapse_photo()
    timelapse_latest_photo = get_latest_timelapse_capture()
    sensor_history = get_sensor_history()
    latest_sensor = get_latest_sensor_point()
    vpd_target = determine_vpd_target(
        {
            "phase": stats["phase"],
            "week_number": current_week,
            "flower_week": stats.get("flower_week") or flower_week or 1,
        }
    )
    timelapse_info = get_timelapse_video_info()
    phase_label = tr("phase_veg", lang) if stats["phase"] == "Veg" else tr("phase_flower", lang)

    return {
        "grow": {
            "name": data.get("grow_name", "PlantWatch"),
            "start_date": data.get("start_date"),
            "sprout_date": data.get("sprout_date"),
            "flower_date": data.get("flower_date"),
            "last_watering": data.get("last_watering"),
            "fertilizers": data.get("fertilizers", {}),
            "fertilizer_units": fert_units,
            "fert_defaults": data.get("fert_defaults", {"liters": 10, "percent": 100}),
        },
        "stats": {
            "week_info": stats["week_info"],
            "phase": phase_label,
            "current_week": current_week,
            "days_since_start": days_since_start,
            "flower_days": flower_days,
            "flower_week": flower_week,
            "days_since_watering": days_since_watering,
            "next_watering": next_due,
        },
        "fertilizers": fert_list,
        "images": image_stats,
        "latest_photo": latest_photo,
        "timelapse_latest_photo": timelapse_latest_photo,
        "timelapse": timelapse_info,
        "light_cycle": get_light_cycle_settings(),
        "timelapse_settings": get_timelapse_settings(),
        "info_lines": build_info_lines(data, stats),
        "sensor_history": sensor_history,
        "latest_sensor": latest_sensor,
        "vpd": {
            "latest": latest_sensor.get("vpd") if latest_sensor else None,
            "optimal": vpd_target,
        },
        "log": read_bot_log(),
    }


def calculate_fert_plan(liters: float, percent: float) -> Dict[str, Any]:
    data = load_data()
    stats = get_week_and_phase(data.get("sprout_date"), data.get("flower_date"))
    current_week = max(1, stats["week_number"])
    adjustment = percent / 100.0
    ferts = data.get("fertilizers", {})
    fert_units = get_fertilizer_units(data)
    lines = []
    totals_by_unit: Dict[str, float] = {}
    for name, schedule in ferts.items():
        amount_per_l = float(schedule.get(str(current_week), 0) or 0)
        unit = fert_units.get(name, "ml/L")
        total_amount = amount_per_l * liters * adjustment
        totals_by_unit[unit] = totals_by_unit.get(unit, 0.0) + total_amount
        lines.append(
            {
                "name": name,
                "amount_per_l": round(amount_per_l, 2),
                "total_amount": round(total_amount, 2),
                "unit": unit,
            }
        )
    return {
        "liters": liters,
        "percent": percent,
        "week": current_week,
        "phase": stats["phase"],
        "lines": lines,
        "totals": [
            {"unit": unit, "total_amount": round(total, 2)}
            for unit, total in sorted(totals_by_unit.items())
        ],
    }


def run_cam_command(extra_args: List[str]) -> str:
    python_executable = VENV_PYTHON if os.path.exists(VENV_PYTHON) else "python3"
    cmd = [python_executable, CAM_SCRIPT] + extra_args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        output = result.stdout.strip() or result.stderr.strip()
        return output or "Befehl ausgeführt."
    except subprocess.TimeoutExpired:
        return "❌ cam.py hat zu lange gebraucht."
    except Exception as exc:
        return f"❌ Fehler: {exc}"


def extract_camera_final_settings(output: str) -> Dict[str, Any] | None:
    if not output:
        return None
    marker = "CAMERA_FINAL_SETTINGS="
    for line in output.splitlines():
        if not line.startswith(marker):
            continue
        raw = line[len(marker):].strip()
        try:
            parsed = json.loads(raw)
        except Exception:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


def action_photo() -> Dict[str, Any]:
    before = get_latest_timelapse_photo()
    result = run_cam_command([])
    latest = get_latest_timelapse_photo()
    if result.startswith("❌"):
        return {"message": result, "photo_updated": bool(latest)}
    if latest and (not before or latest.get("path") != before.get("path")):
        return {
            "message": f"📸 Neue Aufnahme gespeichert · {latest.get('timestamp')}",
            "photo_updated": True,
        }
    return {
        "message": "📸 Aufnahme abgeschlossen.",
        "photo_updated": bool(latest),
    }


def run_timelapse_command() -> str:
    """Run tl.py to generate the timelapse video."""
    python_executable = VENV_PYTHON if os.path.exists(VENV_PYTHON) else "python3"
    cmd = [python_executable, TL_SCRIPT]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
            cwd=SCRIPT_DIR,
        )
        output = result.stdout.strip() or result.stderr.strip()
        return output or "Timelapse erstellt."
    except subprocess.TimeoutExpired:
        return "❌ tl.py hat zu lange gebraucht."
    except Exception as exc:
        return f"❌ Fehler: {exc}"


def action_timelapse() -> Dict[str, Any]:
    message = "🎥 Timelapse-Erstellung gestartet..."
    result = run_timelapse_command()
    info = get_timelapse_video_info()
    return {
        "message": message + ("\n" + result if result else ""),
        "timelapse_updated": info.get("exists", False),
        "timelapse_timestamp": info.get("timestamp"),
    }


def action_temp() -> Dict[str, Any]:
    before = get_latest_sensor_point()
    output = run_cam_command(["--sensors-only"])
    latest = get_latest_sensor_point()
    if output.startswith("❌"):
        return {"message": output}
    if latest and (
        not before
        or latest.get("raw_timestamp") != before.get("raw_timestamp")
        or latest.get("temperature") != before.get("temperature")
        or latest.get("humidity") != before.get("humidity")
    ):
        return {
            "message": f"🌡️ Sensor aktualisiert · {latest.get('timestamp')}",
            "sensor_updated": True,
        }
    return {
        "message": "🌡️ Sensorabfrage abgeschlossen.",
        "sensor_updated": bool(latest),
    }


def action_camera_test(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = load_data()
    app_settings = get_app_settings()
    camera_settings = extract_camera_settings_from_payload(payload, app_settings)
    if camera_settings.get("error"):
        return {"message": f"❌ {camera_settings['error']}"}

    original_settings = {
        key: app_settings[key]
        for key in (
            "camera_auto_focus",
            "camera_focus",
            "camera_auto_exposure",
            "camera_exposure",
            "camera_brightness",
            "camera_contrast",
            "camera_saturation",
            "camera_sharpness",
        )
    }
    app_settings.update(camera_settings)
    data["app_settings"] = app_settings
    save_data(data)
    before = get_latest_timelapse_photo()
    try:
        output = run_cam_command(["--photo-only"])
        latest = get_latest_timelapse_photo()
    finally:
        restore_data = load_data()
        restore_settings = get_app_settings()
        restore_settings.update(original_settings)
        restore_data["app_settings"] = restore_settings
        save_data(restore_data)
    detected_settings = extract_camera_final_settings(output) or camera_settings
    if output.startswith("❌"):
        return {"message": output, "photo_updated": bool(latest)}
    if latest and (not before or latest.get("path") != before.get("path")):
        data = load_data()
        data["camera_test_image"] = {
            "path": latest.get("path"),
            "timestamp": latest.get("timestamp"),
            "raw_timestamp": latest.get("raw_timestamp"),
            "settings": detected_settings,
        }
        save_data(data)
        return {
            "message": f"📷 Testbild gespeichert · {latest.get('timestamp')}",
            "photo_updated": True,
            "camera_test_image": get_camera_test_image_info(),
        }
    return {
        "message": "📷 Testbild abgeschlossen.",
        "photo_updated": bool(latest),
        "camera_test_image": get_camera_test_image_info(),
    }


def action_camera_test_apply() -> Dict[str, Any]:
    info = get_camera_test_image_info()
    if not info or not isinstance(info.get("settings"), dict):
        return {"error": "Keine Testbild-Einstellungen verfügbar."}
    result = save_camera_settings(info["settings"])
    if result.get("error"):
        return result
    return {
        "message": "📷 Testbild-Einstellungen übernommen.",
        "app_settings": result.get("app_settings"),
    }


def action_flower() -> Dict[str, Any]:
    data = load_data()
    today = datetime.now()
    data["flower_date"] = today.strftime("%Y-%m-%d")
    save_data(data)
    return {"message": f"🌸 Blüte gestartet am {today.strftime('%d.%m.%Y')}"}


def action_flower_reset() -> Dict[str, Any]:
    data = load_data()
    if not data.get("flower_date"):
        return {"message": "🌱 Blüte war bereits deaktiviert."}
    data["flower_date"] = ""
    save_data(data)
    return {"message": "🌱 Blüte zurückgesetzt – wieder Veg-Modus."}


def action_logs() -> Dict[str, Any]:
    if not os.path.exists(CAM_LOG_FILE):
        return {"message": "⚠️ Keine cam.log gefunden."}
    try:
        with open(CAM_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-50:]
        return {"message": "🗒️ Logauszug\n" + "".join(lines)}
    except Exception as exc:
        return {"message": f"❌ Fehler beim Lesen der Logs: {exc}"}


def action_water(date_str: str | None, clear: bool | None = False) -> Dict[str, Any]:
    data = load_data()
    if clear:
        data["last_watering"] = ""
        save_data(data)
        return {"message": "💧 Bewässerungseintrag entfernt."}
    if date_str:
        try:
            parsed = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return {"message": "❌ Ungültiges Datum. Bitte YYYY-MM-DD verwenden."}
    else:
        parsed = datetime.now()
    data["last_watering"] = parsed.strftime("%Y-%m-%d")
    save_data(data)
    return {"message": f"🚿 Bewässerung gespeichert: {parsed.strftime('%d.%m.%Y')}"}


def action_fertilizer_save(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = load_data()
    ferts = data.setdefault("fertilizers", {})
    units = data.setdefault("fertilizer_units", {})
    original_name = str(payload.get("original_name") or "").strip()
    name = str(payload.get("name") or "").strip()
    unit = "g/L" if str(payload.get("unit") or "").lower().startswith("g") else "ml/L"
    raw_schedule = payload.get("schedule") or {}

    if not name:
        return {"error": "Name fehlt."}
    if not isinstance(raw_schedule, dict):
        return {"error": "Ungültiger Wochenplan."}

    cleaned_schedule: Dict[str, float] = {}
    for week_key, value in raw_schedule.items():
        try:
            week_num = int(float(week_key))
            amount = round(float(value or 0), 2)
        except (TypeError, ValueError):
            continue
        if week_num < 1:
            continue
        cleaned_schedule[str(week_num)] = amount

    if not cleaned_schedule:
        return {"error": "Mindestens ein Wochenwert ist erforderlich."}
    if name in ferts and name != original_name:
        return {"error": "Ein Dünger mit diesem Namen existiert bereits."}

    if original_name and original_name in ferts and original_name != name:
        ferts.pop(original_name, None)
        units.pop(original_name, None)

    ferts[name] = cleaned_schedule
    units[name] = unit
    data["fertilizers"] = ferts
    data["fertilizer_units"] = units
    save_data(data)
    return {"message": tr("fertilizer_saved"), "fertilizers": get_fertilizer_catalog(data)}


def action_fertilizer_delete(name: str | None) -> Dict[str, Any]:
    target = str(name or "").strip()
    if not target:
        return {"error": "Name fehlt."}
    data = load_data()
    ferts = data.setdefault("fertilizers", {})
    units = data.setdefault("fertilizer_units", {})
    if target not in ferts:
        return {"error": "Dünger nicht gefunden."}
    ferts.pop(target, None)
    units.pop(target, None)
    data["fertilizers"] = ferts
    data["fertilizer_units"] = units
    save_data(data)
    return {"message": tr("fertilizer_deleted"), "fertilizers": get_fertilizer_catalog(data)}


def publish_pump_state(state: str) -> None:
    publish_device_state(get_pump_topic(), state)


def _clear_pump_timer() -> None:
    global PUMP_TIMER_DEADLINE, PUMP_TIMER_THREAD
    with PUMP_TIMER_LOCK:
        if PUMP_TIMER_THREAD:
            try:
                PUMP_TIMER_THREAD.cancel()
            except Exception:
                pass
        PUMP_TIMER_THREAD = None
        PUMP_TIMER_DEADLINE = None


def _scheduled_pump_off() -> None:
    global PUMP_TIMER_DEADLINE, PUMP_TIMER_THREAD
    try:
        publish_pump_state("OFF")
    finally:
        with PUMP_TIMER_LOCK:
            PUMP_TIMER_THREAD = None
            PUMP_TIMER_DEADLINE = None


def _pump_timer_snapshot() -> Dict[str, Any]:
    with PUMP_TIMER_LOCK:
        deadline = PUMP_TIMER_DEADLINE
    if not deadline:
        return {"remaining_seconds": None, "until": None}
    remaining = max(0, int((deadline - datetime.now()).total_seconds()))
    if remaining <= 0:
        return {"remaining_seconds": None, "until": None}
    return {"remaining_seconds": remaining, "until": deadline.isoformat()}


def publish_device_state(topic: str, state: str) -> None:
    if not mqtt:
        raise RuntimeError("paho-mqtt ist nicht installiert.")
    payload = json.dumps({"state": state.upper()})
    client = mqtt_client()
    mqtt_settings = get_mqtt_settings()
    client.connect(mqtt_settings["host"], mqtt_settings["port"], 60)
    client.publish(topic, payload, qos=1, retain=False)
    client.disconnect()


def action_pump(command: str | None, minutes: Any = None) -> Dict[str, Any]:
    if not is_pump_enabled():
        return {"message": "❌ Pumpe ist deaktiviert."}
    cmd = (command or "").lower()
    if cmd not in {"on", "off", "timer"}:
        return {"message": "❌ Unbekannter Pumpenbefehl."}
    if not mqtt:
        return {"message": "❌ MQTT-Client fehlt (paho-mqtt nicht installiert)."}
    try:
        if cmd == "on":
            _clear_pump_timer()
            publish_pump_state("ON")
            return {"message": "🚿 Pumpe eingeschaltet."}
        if cmd == "off":
            _clear_pump_timer()
            publish_pump_state("OFF")
            return {"message": "🛑 Pumpe ausgeschaltet."}
        minutes_val = None
        try:
            minutes_val = float(minutes)
        except (TypeError, ValueError):
            return {"message": "❌ Bitte eine gültige Minutenanzahl angeben."}
        if minutes_val <= 0:
            return {"message": "❌ Minuten müssen größer als 0 sein."}
        _clear_pump_timer()
        publish_pump_state("ON")
        delay = max(1, int(minutes_val * 60))
        timer = threading.Timer(delay, _scheduled_pump_off)
        timer.daemon = True
        with PUMP_TIMER_LOCK:
            global PUMP_TIMER_THREAD, PUMP_TIMER_DEADLINE
            PUMP_TIMER_THREAD = timer
            PUMP_TIMER_DEADLINE = datetime.now() + timedelta(seconds=delay)
        timer.start()
        return {
            "message": f"🚿 Pumpe für {minutes_val:g} Minuten gestartet (Auto-Off nach Ablauf)."
        }
    except Exception as exc:
        return {"message": f"❌ MQTT-Fehler: {exc}"}


def _pump_state_topics() -> List[str]:
    return _device_state_topics(get_pump_topic())


def _heater_state_topics() -> List[str]:
    return _device_state_topics(get_heater_topic())


def _light_state_topics() -> List[str]:
    return _device_state_topics(get_light_topic())


def _dehumidifier_state_topics() -> List[str]:
    return _device_state_topics(get_dehumidifier_topic())


def _humidifier_state_topics() -> List[str]:
    return _device_state_topics(get_humidifier_topic())


def _sensor_state_topics(base_topic: str) -> List[str]:
    base = base_topic.rstrip("/")
    return [base, base + "/state"]


def _device_state_topics(base_topic: str) -> List[str]:
    base = base_topic.rstrip("/")
    if base.endswith("/set"):
        base = base[: -len("/set")]
    return [base, base + "/state"]


def _normalize_state(value: Any) -> str | None:
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    if isinstance(value, str):
        up = value.strip().upper()
        if up in ("ON", "OFF"):
            return up
        if up in ("OPEN", "CLOSE", "CLOSED"):
            return "ON" if up == "OPEN" else "OFF"
        if up in ("CLEAR", "DRY", "NORMAL"):
            return "OFF"
        if up in ("WET", "LEAK", "DETECTED", "WATER"):
            return "ON"
    return None


def _normalize_power(value: Any) -> float | None:
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return round(num, 2)


def _normalize_energy(value: Any) -> float | None:
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return round(num, 3)


def _extract_payload_value(payload: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _parse_device_metrics_from_msg(msg: Any) -> Dict[str, Any]:
    raw = None
    payload: Dict[str, Any] | None = None
    try:
        raw = msg.payload.decode("utf-8")
        payload = json.loads(raw)
    except Exception:
        try:
            raw = msg.payload.decode("utf-8")
        except Exception:
            raw = None
    state = None
    power = None
    energy_yesterday = None
    energy_today = None
    energy_month = None
    if isinstance(payload, dict):
        state = _normalize_state(_extract_payload_value(payload, ["state", "State", "power"]))
        power = _normalize_power(_extract_payload_value(payload, ["power", "Power", "power_w", "consumption", "current_power"]))
        energy_yesterday = _normalize_energy(_extract_payload_value(payload, ["energy_yesterday", "EnergyYesterday", "energyYesterday"]))
        energy_today = _normalize_energy(_extract_payload_value(payload, ["energy_today", "EnergyToday", "energyToday"]))
        energy_month = _normalize_energy(_extract_payload_value(payload, ["energy_month", "EnergyMonth", "energyMonth"]))
        if isinstance(payload.get("energy"), dict):
            energy = payload["energy"]
            energy_yesterday = energy_yesterday if energy_yesterday is not None else _normalize_energy(_extract_payload_value(energy, ["yesterday", "Yesterday"]))
            energy_today = energy_today if energy_today is not None else _normalize_energy(_extract_payload_value(energy, ["today", "Today"]))
            energy_month = energy_month if energy_month is not None else _normalize_energy(_extract_payload_value(energy, ["month", "Month"]))
    if state is None and isinstance(raw, str):
        state = _normalize_state(raw)
    return {
        "state": state,
        "power_w": power,
        "energy_yesterday_kwh": energy_yesterday,
        "energy_today_kwh": energy_today,
        "energy_month_kwh": energy_month,
    }


def _parse_state_power_from_msg(msg: Any) -> tuple[str | None, float | None]:
    metrics = _parse_device_metrics_from_msg(msg)
    return metrics.get("state"), metrics.get("power_w")


def mqtt_client() -> Any:
    if not mqtt:
        raise RuntimeError("paho-mqtt ist nicht installiert.")
    mqtt_settings = get_mqtt_settings()
    client = mqtt.Client(transport="websockets" if mqtt_settings["transport"] == "websockets" else "tcp")
    if mqtt_settings["username"]:
        client.username_pw_set(mqtt_settings["username"], mqtt_settings["password"] or None)
    if mqtt_settings["transport"] == "websockets":
        client.ws_set_options(path=mqtt_settings["ws_path"] or "/")
    return client


def action_pump_state() -> Dict[str, Any]:
    timer_info = _pump_timer_snapshot()
    if not is_pump_enabled():
        return {
            "message": "Pumpe deaktiviert.",
            "pump_state": None,
            "power_w": None,
            "timer_remaining_seconds": timer_info["remaining_seconds"],
            "timer_until": timer_info["until"],
        }
    if pump_monitor and not pump_monitor.cache_matches_current_topic():
        pump_monitor.invalidate_cache()
    if pump_monitor and pump_monitor.last_state:
        return {
            "message": "Pumpenstatus (Cache).",
            "pump_state": pump_monitor.last_state,
            "power_w": pump_monitor.last_power,
            "timer_remaining_seconds": timer_info["remaining_seconds"],
            "timer_until": timer_info["until"],
        }
    if not mqtt:
        return {
            "message": "MQTT-Client fehlt.",
            "pump_state": None,
            "power_w": None,
            "timer_remaining_seconds": timer_info["remaining_seconds"],
            "timer_until": timer_info["until"],
        }
    state_holder: Dict[str, Any] = {"state": None, "power": None}
    event = threading.Event()

    def on_message(client: Any, _userdata: Any, msg: Any) -> None:
        state, power = _parse_state_power_from_msg(msg)
        if state:
            state_holder["state"] = state
        if power is not None:
            state_holder["power"] = power
        if state or power is not None:
            event.set()

    client = mqtt_client()
    client.on_message = on_message
    mqtt_settings = get_mqtt_settings()
    client.connect(mqtt_settings["host"], mqtt_settings["port"], 60)
    for topic in _pump_state_topics():
        client.subscribe(topic, qos=0)
    client.loop_start()
    event.wait(timeout=2.0)
    client.loop_stop()
    client.disconnect()
    return {
        "message": "Pumpenstatus abgefragt.",
        "pump_state": state_holder.get("state"),
        "power_w": state_holder.get("power"),
        "timer_remaining_seconds": timer_info["remaining_seconds"],
        "timer_until": timer_info["until"],
    }


def action_heater(command: str | None) -> Dict[str, Any]:
    if not is_heater_enabled():
        return {"message": "❌ Heizung ist deaktiviert."}
    cmd = (command or "").lower()
    if cmd not in {"on", "off"}:
        return {"message": "❌ Unbekannter Heizungsbefehl."}
    if not mqtt:
        return {"message": "❌ MQTT-Client fehlt (paho-mqtt nicht installiert)."}
    try:
        publish_device_state(get_heater_topic(), "ON" if cmd == "on" else "OFF")
        return {"message": "🔥 Heizung geschaltet."}
    except Exception as exc:
        return {"message": f"❌ MQTT-Fehler: {exc}"}


def action_heater_state() -> Dict[str, Any]:
    if not is_heater_enabled():
        return {"message": "Heizung deaktiviert.", "heater_state": None, "power_w": None}
    if heater_monitor and not heater_monitor.cache_matches_current_topic():
        heater_monitor.invalidate_cache()
    if heater_monitor and heater_monitor.last_state:
        return {
            "message": "Heizungsstatus (Cache).",
            "heater_state": heater_monitor.last_state,
            "power_w": heater_monitor.last_power,
        }
    if not mqtt:
        return {"message": "MQTT-Client fehlt.", "heater_state": None, "power_w": None}
    state_holder: Dict[str, Any] = {"state": None, "power": None}
    event = threading.Event()

    def on_message(client: Any, _userdata: Any, msg: Any) -> None:
        state, power = _parse_state_power_from_msg(msg)
        if state:
            state_holder["state"] = state
        if power is not None:
            state_holder["power"] = power
        if state or power is not None:
            event.set()

    client = mqtt_client()
    client.on_message = on_message
    mqtt_settings = get_mqtt_settings()
    client.connect(mqtt_settings["host"], mqtt_settings["port"], 60)
    for topic in _heater_state_topics():
        client.subscribe(topic, qos=0)
    client.loop_start()
    event.wait(timeout=2.0)
    client.loop_stop()
    client.disconnect()
    return {
        "message": "Heizungsstatus abgefragt.",
        "heater_state": state_holder.get("state"),
        "power_w": state_holder.get("power"),
    }


def action_exhaust(command: str | None) -> Dict[str, Any]:
    if not is_exhaust_enabled():
        return {"message": "❌ Abluft ist deaktiviert."}
    cmd = (command or "").lower()
    if cmd not in {"on", "off"}:
        return {"message": "❌ Unbekannter Abluft-Befehl."}
    if not mqtt:
        return {"message": "❌ MQTT-Client fehlt (paho-mqtt nicht installiert)."}
    try:
        publish_device_state(get_exhaust_topic(), "ON" if cmd == "on" else "OFF")
        return {"message": "🌬️ Abluft geschaltet."}
    except Exception as exc:
        return {"message": f"❌ MQTT-Fehler: {exc}"}


def action_exhaust_state() -> Dict[str, Any]:
    if not is_exhaust_enabled():
        return {"message": "Abluft deaktiviert.", "exhaust_state": None, "power_w": None}
    if exhaust_monitor and not exhaust_monitor.cache_matches_current_topic():
        exhaust_monitor.invalidate_cache()
    if exhaust_monitor and exhaust_monitor.last_state:
        return {
            "message": "Abluftstatus (Cache).",
            "exhaust_state": exhaust_monitor.last_state,
            "power_w": exhaust_monitor.last_power,
        }
    if not mqtt:
        return {"message": "MQTT-Client fehlt.", "exhaust_state": None, "power_w": None}
    state_holder: Dict[str, Any] = {"state": None, "power": None}
    event = threading.Event()

    def on_message(client: Any, _userdata: Any, msg: Any) -> None:
        state, power = _parse_state_power_from_msg(msg)
        if state:
            state_holder["state"] = state
        if power is not None:
            state_holder["power"] = power
        if state or power is not None:
            event.set()

    client = mqtt_client()
    client.on_message = on_message
    mqtt_settings = get_mqtt_settings()
    client.connect(mqtt_settings["host"], mqtt_settings["port"], 60)
    for topic in _device_state_topics(get_exhaust_topic()):
        client.subscribe(topic, qos=0)
    client.loop_start()
    event.wait(timeout=2.0)
    client.loop_stop()
    client.disconnect()
    return {
        "message": "Abluftstatus abgefragt.",
        "exhaust_state": state_holder.get("state"),
        "power_w": state_holder.get("power"),
    }


def _generic_device_state(
    enabled: bool,
    disabled_message: str,
    monitor: Any,
    state_key: str,
    state_topics_getter: Any,
) -> Dict[str, Any]:
    if not enabled:
        return {"message": disabled_message, state_key: None, "power_w": None}
    if monitor and not monitor.cache_matches_current_topic():
        monitor.invalidate_cache()
    if monitor and monitor.last_state:
        return {"message": f"{state_key} (Cache).", state_key: monitor.last_state, "power_w": monitor.last_power}
    if not mqtt:
        return {"message": "MQTT-Client fehlt.", state_key: None, "power_w": None}
    state_holder: Dict[str, Any] = {"state": None, "power": None}
    event = threading.Event()

    def on_message(client: Any, _userdata: Any, msg: Any) -> None:
        state, power = _parse_state_power_from_msg(msg)
        if state:
            state_holder["state"] = state
        if power is not None:
            state_holder["power"] = power
        if state or power is not None:
            event.set()

    client = mqtt_client()
    client.on_message = on_message
    mqtt_settings = get_mqtt_settings()
    client.connect(mqtt_settings["host"], mqtt_settings["port"], 60)
    for topic in state_topics_getter():
        client.subscribe(topic, qos=0)
    client.loop_start()
    event.wait(timeout=2.0)
    client.loop_stop()
    client.disconnect()
    return {"message": f"{state_key} abgefragt.", state_key: state_holder.get("state"), "power_w": state_holder.get("power")}


def _fetch_device_metrics(enabled: bool, monitor: PlugStateMonitor | None, state_topics_getter: Any) -> Dict[str, Any]:
    if not enabled:
        return {
            "state": None,
            "power_w": None,
            "energy_yesterday_kwh": None,
            "energy_today_kwh": None,
            "energy_month_kwh": None,
            "updated_at": None,
        }
    if monitor and not monitor.cache_matches_current_topic():
        monitor.invalidate_cache()
    if monitor and (
        monitor.last_state is not None
        or monitor.last_power is not None
        or monitor.last_energy_today_kwh is not None
        or monitor.last_energy_yesterday_kwh is not None
        or monitor.last_energy_month_kwh is not None
    ):
        return {
            "state": monitor.last_state,
            "power_w": monitor.last_power,
            "energy_yesterday_kwh": monitor.last_energy_yesterday_kwh,
            "energy_today_kwh": monitor.last_energy_today_kwh,
            "energy_month_kwh": monitor.last_energy_month_kwh,
            "updated_at": format_local_datetime(monitor.last_seen_at) if monitor and monitor.last_seen_at else None,
        }
    if not mqtt:
        return {
            "state": None,
            "power_w": None,
            "energy_yesterday_kwh": None,
            "energy_today_kwh": None,
            "energy_month_kwh": None,
            "updated_at": None,
        }
    metrics: Dict[str, Any] = {
        "state": None,
        "power_w": None,
        "energy_yesterday_kwh": None,
        "energy_today_kwh": None,
        "energy_month_kwh": None,
        "updated_at": None,
    }
    event = threading.Event()

    def on_message(client: Any, _userdata: Any, msg: Any) -> None:
        parsed = _parse_device_metrics_from_msg(msg)
        if parsed.get("state") is not None:
            metrics["state"] = parsed["state"]
        for key in ("power_w", "energy_yesterday_kwh", "energy_today_kwh", "energy_month_kwh"):
            if parsed.get(key) is not None:
                metrics[key] = parsed[key]
        if any(metrics.get(key) is not None for key in ("state", "power_w", "energy_yesterday_kwh", "energy_today_kwh", "energy_month_kwh")):
            metrics["updated_at"] = format_local_datetime(datetime.now())
            event.set()

    client = mqtt_client()
    client.on_message = on_message
    mqtt_settings = get_mqtt_settings()
    client.connect(mqtt_settings["host"], mqtt_settings["port"], 60)
    for topic in state_topics_getter():
        client.subscribe(topic, qos=0)
    client.loop_start()
    event.wait(timeout=2.0)
    client.loop_stop()
    client.disconnect()
    return metrics


def action_light(command: str | None) -> Dict[str, Any]:
    if not is_light_enabled():
        return {"message": "❌ Licht ist deaktiviert."}
    cmd = (command or "").lower()
    if cmd not in {"on", "off"}:
        return {"message": "❌ Unbekannter Licht-Befehl."}
    if not mqtt:
        return {"message": "❌ MQTT-Client fehlt (paho-mqtt nicht installiert)."}
    try:
        publish_device_state(get_light_topic(), "ON" if cmd == "on" else "OFF")
        return {"message": "💡 Licht geschaltet."}
    except Exception as exc:
        return {"message": f"❌ MQTT-Fehler: {exc}"}


def action_light_state() -> Dict[str, Any]:
    return _generic_device_state(is_light_enabled(), "Licht deaktiviert.", light_monitor, "light_state", _light_state_topics)


def action_dehumidifier(command: str | None) -> Dict[str, Any]:
    if not is_dehumidifier_enabled():
        return {"message": "❌ Entfeuchter ist deaktiviert."}
    cmd = (command or "").lower()
    if cmd not in {"on", "off"}:
        return {"message": "❌ Unbekannter Entfeuchter-Befehl."}
    if not mqtt:
        return {"message": "❌ MQTT-Client fehlt (paho-mqtt nicht installiert)."}
    try:
        publish_device_state(get_dehumidifier_topic(), "ON" if cmd == "on" else "OFF")
        return {"message": "💨 Entfeuchter geschaltet."}
    except Exception as exc:
        return {"message": f"❌ MQTT-Fehler: {exc}"}


def action_dehumidifier_state() -> Dict[str, Any]:
    return _generic_device_state(is_dehumidifier_enabled(), "Entfeuchter deaktiviert.", dehumidifier_monitor, "dehumidifier_state", _dehumidifier_state_topics)


def action_humidifier(command: str | None) -> Dict[str, Any]:
    if not is_humidifier_enabled():
        return {"message": "❌ Luftbefeuchter ist deaktiviert."}
    cmd = (command or "").lower()
    if cmd not in {"on", "off"}:
        return {"message": "❌ Unbekannter Luftbefeuchter-Befehl."}
    if not mqtt:
        return {"message": "❌ MQTT-Client fehlt (paho-mqtt nicht installiert)."}
    try:
        publish_device_state(get_humidifier_topic(), "ON" if cmd == "on" else "OFF")
        return {"message": "💧 Luftbefeuchter geschaltet."}
    except Exception as exc:
        return {"message": f"❌ MQTT-Fehler: {exc}"}


def action_humidifier_state() -> Dict[str, Any]:
    return _generic_device_state(is_humidifier_enabled(), "Luftbefeuchter deaktiviert.", humidifier_monitor, "humidifier_state", _humidifier_state_topics)


class WaterLeakGuard:
    def __init__(self) -> None:
        self.thread: threading.Thread | None = None
        self.reminder_thread: threading.Thread | None = None
        self.last_state: str | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="water-leak-guard", daemon=True)
        self.thread.start()
        if not self.reminder_thread or not self.reminder_thread.is_alive():
            self.reminder_thread = threading.Thread(
                target=self._run_reminder_loop,
                name="water-reservoir-reminder",
                daemon=True,
            )
            self.reminder_thread.start()

    def _run(self) -> None:
        while True:
            try:
                if not is_water_sensor_enabled():
                    self.last_state = None
                    time.sleep(5)
                    continue
                client = mqtt_client()
                client.on_connect = self._on_connect  # type: ignore[attr-defined]
                client.on_message = self._on_message  # type: ignore[attr-defined]
                client.reconnect_delay_set(min_delay=1, max_delay=30)
                mqtt_settings = get_mqtt_settings()
                client.connect(mqtt_settings["host"], mqtt_settings["port"], 60)
                client.loop_forever(retry_first_connection=True)
            except Exception as exc:
                print(f"[water-guard] MQTT Fehler: {exc}", flush=True)
                time.sleep(5)

    def _on_connect(self, client: Any, _userdata: Any, _flags: Any, rc: int) -> None:
        if rc != 0:
            print(f"[water-guard] MQTT Connect-Fehler: {rc}", flush=True)
            return
        if not is_water_sensor_enabled():
            return
        sensor_topic = get_water_sensor_topic()
        for topic in _sensor_state_topics(sensor_topic):
            client.subscribe(topic, qos=1)
        print(f"[water-guard] Lausche auf {sensor_topic}", flush=True)

    def _on_message(self, client: Any, _userdata: Any, msg: Any) -> None:
        if not is_water_sensor_enabled():
            self.last_state = None
            return
        state = self._parse_state(msg)
        if state:
            self.last_state = state
            self._handle_reservoir_state(state)

    @staticmethod
    def _parse_state(msg: Any) -> str | None:
        try:
            payload_raw = msg.payload.decode("utf-8")
            payload = json.loads(payload_raw)
            for key in ("water_leak", "leak", "status", "state"):
                if key in payload:
                    val = payload[key]
                    break
            else:
                val = None
        except Exception:
            val = msg.payload.decode("utf-8").strip() or None
        return _normalize_state(val)

    def _handle_reservoir_state(self, state: str) -> None:
        if not is_water_sensor_enabled():
            return
        data = load_data()
        sensor_info = data.get("water_reservoir", {})
        now = datetime.now()

        if state == "OFF":
            dry_since = sensor_info.get("dry_since")
            if not dry_since:
                sensor_info = {
                    "state": "OFF",
                    "dry_since": now.isoformat(),
                    "first_alert_sent": True,
                    "repeat_alert_sent": False,
                }
                data["water_reservoir"] = sensor_info
                save_data(data)
                send_telegram_notification("🪫💧 Reservoir leer: Wassermelder zeigt trocken.")
                print("[water-guard] Reservoir trocken erkannt.", flush=True)
            else:
                sensor_info["state"] = "OFF"
                data["water_reservoir"] = sensor_info
                save_data(data)
            return

        sensor_info = {
            "state": "ON",
            "dry_since": None,
            "first_alert_sent": False,
            "repeat_alert_sent": False,
            "wet_since": now.isoformat(),
        }
        data["water_reservoir"] = sensor_info
        save_data(data)
        print("[water-guard] Reservoir wieder OK.", flush=True)

    def _run_reminder_loop(self) -> None:
        while True:
            try:
                if is_water_sensor_enabled():
                    self._check_dry_reminder()
            except Exception as exc:
                print(f"[water-guard] Reminder-Fehler: {exc}", flush=True)
            time.sleep(300)

    def _check_dry_reminder(self) -> None:
        data = load_data()
        sensor_info = data.get("water_reservoir", {})
        if sensor_info.get("state") != "OFF":
            return
        dry_since_raw = sensor_info.get("dry_since")
        if not dry_since_raw:
            return
        try:
            dry_since = datetime.fromisoformat(dry_since_raw)
        except ValueError:
            return
        if sensor_info.get("repeat_alert_sent"):
            return
        elapsed = datetime.now() - dry_since
        if elapsed >= timedelta(hours=24):
            send_telegram_notification("⏰💧 Reservoir seit 24h trocken. Bitte nachfüllen.")
            sensor_info["repeat_alert_sent"] = True
            data["water_reservoir"] = sensor_info
            save_data(data)
            print("[water-guard] 24h-Reservoir-Erinnerung gesendet.", flush=True)


def _as_naive(dt: datetime) -> datetime:
    """Return a timezone-naive datetime, stripping tzinfo if present.

    All datetime comparisons in controllers use datetime.now() which is
    timezone-naive. Sensor readings stored in the DB may carry timezone
    info (Europe/Berlin). This helper normalises them so subtraction never
    raises 'can't subtract offset-naive and offset-aware datetimes'.
    """
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


_alert_last_sent: Dict[str, datetime] = {}


def _should_alert(key: str, min_interval_seconds: int = ALERT_MIN_INTERVAL_SECONDS) -> bool:
    """Return True (and record the time) if enough time has passed since the last alert with this key.

    Prevents Telegram spam when a fault condition persists across many control cycles.
    """
    now = datetime.now()
    last = _alert_last_sent.get(key)
    if last is None or (now - last).total_seconds() >= min_interval_seconds:
        _alert_last_sent[key] = now
        return True
    return False


class PlugStateMonitor:
    def __init__(self, topic_getter: Any, label: str) -> None:
        self.topic_getter = topic_getter
        self.label = label
        self.thread: threading.Thread | None = None
        self.last_state: str | None = None
        self.last_power: float | None = None
        self.last_energy_yesterday_kwh: float | None = None
        self.last_energy_today_kwh: float | None = None
        self.last_energy_month_kwh: float | None = None
        self.last_changed_at: datetime | None = None
        self.last_seen_at: datetime | None = None
        self.subscribed_topic: str | None = None
        self.is_connected: bool = False
        self.disconnected_since: datetime | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        name = f"{self.label}-state-monitor"
        self.thread = threading.Thread(target=self._run, name=name, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while True:
            try:
                client = mqtt_client()
                client.on_connect = self._on_connect  # type: ignore[attr-defined]
                client.on_message = self._on_message  # type: ignore[attr-defined]
                client.reconnect_delay_set(min_delay=1, max_delay=30)
                mqtt_settings = get_mqtt_settings()
                client.connect(mqtt_settings["host"], mqtt_settings["port"], 60)
                client.loop_forever(retry_first_connection=True)
            except Exception as exc:
                print(f"[{self.label}-monitor] MQTT Fehler: {exc}", flush=True)
                self.is_connected = False
                if self.disconnected_since is None:
                    self.disconnected_since = datetime.now()
                time.sleep(5)

    def _on_connect(self, client: Any, _userdata: Any, _flags: Any, rc: int) -> None:
        if rc != 0:
            print(f"[{self.label}-monitor] MQTT Connect-Fehler: {rc}", flush=True)
            return
        self.is_connected = True
        self.disconnected_since = None
        device_topic = self.topic_getter()
        self.subscribed_topic = device_topic
        for topic in _device_state_topics(device_topic):
            client.subscribe(topic, qos=1)
        print(f"[{self.label}-monitor] Lausche auf {device_topic}", flush=True)

    def _on_message(self, _client: Any, _userdata: Any, msg: Any) -> None:
        metrics = _parse_device_metrics_from_msg(msg)
        state = metrics.get("state")
        power = metrics.get("power_w")
        if state:
            if state != self.last_state:
                self.last_changed_at = datetime.now()
            self.last_state = state
        if power is not None:
            self.last_power = power
        if metrics.get("energy_yesterday_kwh") is not None:
            self.last_energy_yesterday_kwh = metrics["energy_yesterday_kwh"]
        if metrics.get("energy_today_kwh") is not None:
            self.last_energy_today_kwh = metrics["energy_today_kwh"]
        if metrics.get("energy_month_kwh") is not None:
            self.last_energy_month_kwh = metrics["energy_month_kwh"]
        if state or power is not None or metrics.get("energy_yesterday_kwh") is not None or metrics.get("energy_today_kwh") is not None or metrics.get("energy_month_kwh") is not None:
            self.last_seen_at = datetime.now()

    def cache_matches_current_topic(self) -> bool:
        return self.subscribed_topic == self.topic_getter()

    def invalidate_cache(self) -> None:
        self.last_state = None
        self.last_power = None
        self.last_energy_yesterday_kwh = None
        self.last_energy_today_kwh = None
        self.last_energy_month_kwh = None
        self.last_changed_at = None
        self.last_seen_at = None


class HeaterController:
    def __init__(
        self,
        topic_getter: Any,
        monitor: PlugStateMonitor | None,
        light_monitor: PlugStateMonitor | None = None,
    ) -> None:
        self.topic_getter = topic_getter
        self.monitor = monitor
        self.light_monitor = light_monitor
        self.thread: threading.Thread | None = None
        self.last_decision: str | None = None
        self.last_live_reading: Dict[str, Any] | None = None
        self.temperature_history: deque[float] = deque(maxlen=9)
        self._power_anomaly_start: datetime | None = None
        self.last_command_requested_state: str | None = None
        self.last_command_time: datetime | None = None
        self.last_command_confirmed: bool | None = None
        self.last_command_result: str | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="heater-controller", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while True:
            try:
                interval_seconds = self._control_once()
            except Exception as exc:
                print(f"[heater-controller] Fehler: {exc}\n{traceback.format_exc()}", flush=True)
                interval_seconds = DEFAULT_HEATER_SETTINGS["control_interval_seconds"]
            time.sleep(max(15, int(interval_seconds)))

    def _control_once(self) -> int:
        settings = get_heater_settings()
        if not settings.get("enabled"):
            self.last_decision = None
            return int(settings["control_interval_seconds"])

        reading = self._get_control_reading(settings)
        if not reading or reading.get("temperature") is None:
            return int(settings["control_interval_seconds"])

        now = datetime.now()
        age_seconds = (now - _as_naive(reading["timestamp"])).total_seconds()
        if age_seconds > settings["sensor_max_age_seconds"]:
            self._log_once(
                f"[heater-controller] Sensorwert zu alt ({int(age_seconds)}s), keine Regelung."
            )
            return int(settings["control_interval_seconds"])

        current_state = self._current_state()
        if current_state not in {"ON", "OFF"}:
            return int(settings["control_interval_seconds"])

        target = self._target_temperature(now, settings)
        effective_temp = self._effective_temperature(float(reading["temperature"]), settings)
        on_threshold = target - settings["on_below_offset_c"]
        off_threshold = target + settings["off_above_offset_c"]

        # Power draw anomaly: heater ON but drawing near 0W
        if current_state == "ON" and self.monitor and self.monitor.last_power is not None:
            if self.monitor.last_power < POWER_ANOMALY_MIN_WATTS:
                if self._power_anomaly_start is None:
                    self._power_anomaly_start = now
                elif (now - _as_naive(self._power_anomaly_start)).total_seconds() >= POWER_ANOMALY_GRACE_SECONDS:
                    if _should_alert("heater_power_anomaly"):
                        send_telegram_notification(
                            f"⚡ Heizung AN aber nur {self.monitor.last_power:.1f}W — möglicher Hardware-Defekt!"
                        )
            else:
                self._power_anomaly_start = None
        elif current_state != "ON":
            self._power_anomaly_start = None

        # Emergency override: force heater OFF regardless of short-cycle protection
        # if temperature reaches the emergency threshold.
        if current_state == "ON" and effective_temp >= HEATER_EMERGENCY_OFF_TEMP_C:
            print(
                f"[heater-controller] NOTABSCHALTUNG temp={effective_temp:.2f}C >= {HEATER_EMERGENCY_OFF_TEMP_C}C",
                flush=True,
            )
            self._publish("OFF", effective_temp, target, on_threshold, off_threshold)
            send_telegram_notification(
                f"🚨 Notabschaltung! Temperatur {effective_temp:.1f}°C >= {HEATER_EMERGENCY_OFF_TEMP_C}°C. Heizung abgeschaltet."
            )
            return int(settings["control_interval_seconds"])

        if current_state == "OFF" and effective_temp <= on_threshold:
            if self._can_switch("OFF", now, settings):
                self._publish("ON", effective_temp, target, on_threshold, off_threshold)
            return int(settings["control_interval_seconds"])

        if current_state == "ON" and effective_temp >= off_threshold:
            if self._can_switch("ON", now, settings):
                self._publish("OFF", effective_temp, target, on_threshold, off_threshold)
            return int(settings["control_interval_seconds"])

        self.last_decision = None
        return int(settings["control_interval_seconds"])

    def _get_control_reading(self, settings: Dict[str, Any]) -> Dict[str, Any] | None:
        reading = get_live_sensor_reading()
        if reading and reading.get("temperature") is not None:
            self.last_live_reading = reading
            self.temperature_history.append(float(reading["temperature"]))
            max_samples = max(1, int(settings["sensor_median_samples"]))
            while len(self.temperature_history) > max_samples:
                self.temperature_history.popleft()
            return reading

        if self.last_live_reading is None:
            return None

        age_seconds = (datetime.now() - _as_naive(self.last_live_reading["timestamp"])).total_seconds()
        if age_seconds <= settings["sensor_max_age_seconds"]:
            self._log_once(
                f"[heater-controller] Live-Sensor fehlgeschlagen, nutze letzten Wert ({int(age_seconds)}s alt)."
            )
            return self.last_live_reading
        return None

    def _target_temperature(self, now: datetime, settings: Dict[str, Any]) -> float:
        # Prefer actual light state from MQTT plug if available and recently seen.
        # Falls back to schedule automatically for mechanical plugs, MQTT outages, or first startup.
        if self.light_monitor:
            lm_state = self.light_monitor.last_state
            lm_seen = self.light_monitor.last_seen_at
            if lm_state in {"ON", "OFF"} and lm_seen is not None:
                if (now - _as_naive(lm_seen)).total_seconds() <= LIGHT_MONITOR_MAX_AGE_SECONDS:
                    return float(settings["day_target_c"]) if lm_state == "ON" else float(settings["night_target_c"])
        # Fallback: use configured schedule
        current_time = now.time()
        cycle = get_light_cycle_settings()
        day_start = _parse_clock_time(cycle["lights_on_start"])
        day_end = _parse_clock_time(cycle["lights_on_end"])
        if _time_in_window(current_time, day_start, day_end):
            return float(settings["day_target_c"])
        return float(settings["night_target_c"])

    def _effective_temperature(self, latest_temp: float, settings: Dict[str, Any]) -> float:
        recent = list(self.temperature_history)
        if len(recent) < 2:
            return latest_temp
        recent.sort()
        mid = len(recent) // 2
        if len(recent) % 2:
            return recent[mid]
        return round((recent[mid - 1] + recent[mid]) / 2.0, 2)

    def _current_state(self) -> str | None:
        if self.monitor and self.monitor.last_state in {"ON", "OFF"}:
            return self.monitor.last_state
        state_result = action_heater_state()
        state = state_result.get("heater_state")
        if state in {"ON", "OFF"} and self.monitor:
            self.monitor.last_state = state
            if self.monitor.last_changed_at is None:
                self.monitor.last_changed_at = datetime.now()
        return state if state in {"ON", "OFF"} else None

    def _can_switch(self, current_state: str, now: datetime, settings: Dict[str, Any]) -> bool:
        if not self.monitor or not self.monitor.last_changed_at:
            return True
        elapsed = (now - _as_naive(self.monitor.last_changed_at)).total_seconds()
        required = settings["min_on_seconds"] if current_state == "ON" else settings["min_off_seconds"]
        if elapsed >= required:
            return True
        self._log_once(
            f"[heater-controller] Halte {current_state} noch {int(required - elapsed)}s wegen Kurzzyklus-Schutz."
        )
        return False

    def _publish(
        self,
        next_state: str,
        effective_temp: float,
        target: float,
        on_threshold: float,
        off_threshold: float,
    ) -> None:
        self.last_command_requested_state = next_state
        self.last_command_time = datetime.now()
        self.last_command_confirmed = None
        topic = self.topic_getter()
        self.last_command_result = f"Sent {next_state} command to {topic}"
        publish_device_state(topic, next_state)
        self.last_decision = None
        settings = get_heater_settings()
        print(
            (
                f"[heater-controller] Heizung {next_state} | temp={effective_temp:.2f}C "
                f"target={target:.2f}C on<={on_threshold:.2f} off>={off_threshold:.2f}"
            ),
            flush=True,
        )
        confirmed = self._wait_for_confirmation(next_state)
        self.last_command_confirmed = confirmed
        if confirmed:
            self.last_command_result = f"Confirmed {next_state}"
        else:
            self.last_command_result = f"No confirmation for {next_state}"
            print(
                f"[heater-controller] Keine Bestätigung für Zustand {next_state}.",
                flush=True,
            )
        if confirmed and settings.get("debug_notify"):
            icon = "🟢" if next_state == "ON" else "🔴"
            action_text = "on" if next_state == "ON" else "off"
            temp_text = html.escape(f"{effective_temp:.2f}")
            send_telegram_notification(f"{icon} Reached {temp_text}°C, switching {action_text}.")

    def _wait_for_confirmation(self, expected_state: str, timeout_seconds: float = 8.0) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            state = self._current_state()
            if state == expected_state:
                return True
            time.sleep(0.5)
        return False

    def _log_once(self, message: str) -> None:
        if message == self.last_decision:
            return
        self.last_decision = message
        print(message, flush=True)

    def snapshot(self) -> Dict[str, Any]:
        settings = get_heater_settings()
        now = datetime.now()
        target = self._target_temperature(now, settings)
        last_reading = None
        reading_age_seconds = None
        current_reading = None
        if self.last_live_reading:
            reading_age_seconds = round((now - _as_naive(self.last_live_reading["timestamp"])).total_seconds(), 1)
            last_reading = format_local_datetime(self.last_live_reading["timestamp"])
            current_reading = self.last_live_reading.get("temperature")
        median_temp = self._effective_temperature(float(current_reading), settings) if current_reading is not None else None
        state = self._current_state()
        last_command_time = format_local_datetime(self.last_command_time) if self.last_command_time else None
        target_source = "schedule"
        if self.light_monitor:
            lm_seen = self.light_monitor.last_seen_at
            lm_state = self.light_monitor.last_state
            if lm_state in {"ON", "OFF"} and lm_seen is not None:
                if (now - _as_naive(lm_seen)).total_seconds() <= LIGHT_MONITOR_MAX_AGE_SECONDS:
                    target_source = "mqtt_light"
        return {
            "enabled": settings["enabled"],
            "plug_state": state,
            "plug_power_w": self.monitor.last_power if self.monitor else None,
            "current_reading_c": current_reading,
            "median_c": median_temp,
            "target_c": target,
            "target_source": target_source,
            "on_threshold_c": round(target - settings["on_below_offset_c"], 2),
            "off_threshold_c": round(target + settings["off_above_offset_c"], 2),
            "reading_time": last_reading,
            "reading_age_seconds": reading_age_seconds,
            "history": list(self.temperature_history),
            "last_decision": self.last_decision,
            "last_command_requested_state": self.last_command_requested_state,
            "last_command_time": last_command_time,
            "last_command_confirmed": self.last_command_confirmed,
            "last_command_result": self.last_command_result,
            "command_topic": self.topic_getter(),
        }


class ExhaustController:
    def __init__(self, topic_getter: Any, monitor: PlugStateMonitor | None) -> None:
        self.topic_getter = topic_getter
        self.monitor = monitor
        self.thread: threading.Thread | None = None
        self.last_live_reading: Dict[str, Any] | None = None
        self.temperature_history: deque[float] = deque(maxlen=9)
        self.humidity_history: deque[float] = deque(maxlen=9)
        self.last_reason: str | None = None
        self.last_change_reason: str | None = None
        self.last_on_ts: datetime | None = None
        self.last_off_ts: datetime | None = None
        self.forced_refresh_active = False
        self.last_command_requested_state: str | None = None
        self.last_command_time: datetime | None = None
        self.last_command_confirmed: bool | None = None
        self.last_command_result: str | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="exhaust-controller", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while True:
            try:
                interval_seconds = self._control_once()
            except Exception as exc:
                print(f"[exhaust-controller] Fehler: {exc}\n{traceback.format_exc()}", flush=True)
                interval_seconds = DEFAULT_EXHAUST_SETTINGS["control_interval_seconds"]
            time.sleep(max(15, int(interval_seconds)))

    def _control_once(self) -> int:
        settings = get_exhaust_settings()
        if not settings["enabled"]:
            self._log_once(None)
            return int(settings["control_interval_seconds"])
        humidity_settings = get_humidity_settings()
        if humidity_settings["enabled"] and humidity_settings["control_method"] == "exhaust":
            if humidity_settings["exhaust_control_mode"] == "cycle":
                return self._run_cycle_mode(settings, humidity_settings)
        elif humidity_settings["enabled"] and humidity_settings["control_method"] != "exhaust":
            self._log_once("manual_only")
            return int(settings["control_interval_seconds"])

        reading = self._get_control_reading(settings)
        now = datetime.now()
        state = self._current_state()
        if state not in {"ON", "OFF"}:
            return int(settings["control_interval_seconds"])
        self._sync_state_timestamps(state, now)
        on_elapsed = (now - _as_naive(self.last_on_ts)).total_seconds() if self.last_on_ts else None
        off_elapsed = (now - _as_naive(self.last_off_ts)).total_seconds() if self.last_off_ts else None

        if not reading:
            if state == "OFF" and self._can_switch("OFF", now, settings):
                self._publish("ON", None, None, "sensor_failsafe")
            self._log_once("sensor_failsafe")
            return int(settings["control_interval_seconds"])

        sensor_age = (now - _as_naive(reading["timestamp"])).total_seconds()
        temp = reading.get("temperature")
        humidity = reading.get("humidity")
        median_temp = self._median_value(self.temperature_history, temp)
        median_rh = self._median_value(self.humidity_history, humidity)

        if sensor_age > settings["sensor_max_age_seconds"]:
            if state == "OFF" and self._can_switch("OFF", now, settings):
                self._publish("ON", median_temp, median_rh, "sensor_failsafe")
            self._log_once("sensor_failsafe")
            return int(settings["control_interval_seconds"])

        if state == "OFF" and off_elapsed is not None and off_elapsed >= settings["max_off_time_before_refresh"]:
            if self._can_switch("OFF", now, settings):
                self.forced_refresh_active = True
                self._publish("ON", median_temp, median_rh, "refresh_due")
            return int(settings["control_interval_seconds"])

        should_force_on = (
            (median_temp is not None and median_temp >= settings["temp_force_on_above"])
            or (median_rh is not None and median_rh >= settings["rh_turn_on_above"])
        )
        if should_force_on and state == "OFF":
            if self._can_switch("OFF", now, settings):
                reason = "temp_high" if median_temp is not None and median_temp >= settings["temp_force_on_above"] else "rh_high"
                self._publish("ON", median_temp, median_rh, reason)
            return int(settings["control_interval_seconds"])

        if state == "ON":
            if self.forced_refresh_active:
                if on_elapsed is not None and on_elapsed >= settings["forced_refresh_run_time"]:
                    if self._can_turn_off(median_temp, median_rh, settings) and self._can_switch("ON", now, settings):
                        self.forced_refresh_active = False
                        self._publish("OFF", median_temp, median_rh, "refresh_complete")
                    else:
                        self._log_once("refresh_active")
                else:
                    self._log_once("refresh_active")
                return int(settings["control_interval_seconds"])

            if on_elapsed is not None and on_elapsed >= settings["min_on_seconds"]:
                if self._can_turn_off(median_temp, median_rh, settings) and self._can_switch("ON", now, settings):
                    self._publish("OFF", median_temp, median_rh, "rh_and_temp_ok")
                    return int(settings["control_interval_seconds"])

        self._log_once("holding")
        return int(settings["control_interval_seconds"])

    def _run_cycle_mode(self, settings: Dict[str, Any], humidity_settings: Dict[str, Any]) -> int:
        now = datetime.now()
        state = self._current_state()
        if state not in {"ON", "OFF"}:
            return int(settings["control_interval_seconds"])
        self._sync_state_timestamps(state, now)
        if state == "OFF":
            off_elapsed = (now - _as_naive(self.last_off_ts)).total_seconds() if self.last_off_ts else None
            if off_elapsed is None or off_elapsed >= humidity_settings["cycle_off_seconds"]:
                if self._can_switch("OFF", now, settings):
                    self._publish("ON", None, None, "cycle_on")
            self._log_once("cycle_wait_off")
            return int(settings["control_interval_seconds"])
        on_elapsed = (now - _as_naive(self.last_on_ts)).total_seconds() if self.last_on_ts else None
        if on_elapsed is None or on_elapsed >= humidity_settings["cycle_on_seconds"]:
            if self._can_switch("ON", now, settings):
                self._publish("OFF", None, None, "cycle_off")
        self._log_once("cycle_wait_on")
        return int(settings["control_interval_seconds"])

    def _get_control_reading(self, settings: Dict[str, Any]) -> Dict[str, Any] | None:
        reading = get_live_sensor_reading()
        if reading and reading.get("temperature") is not None and reading.get("humidity") is not None:
            self.last_live_reading = reading
            self.temperature_history.append(float(reading["temperature"]))
            self.humidity_history.append(float(reading["humidity"]))
            max_samples = max(1, int(settings["sensor_median_samples"]))
            while len(self.temperature_history) > max_samples:
                self.temperature_history.popleft()
            while len(self.humidity_history) > max_samples:
                self.humidity_history.popleft()
            return reading
        if self.last_live_reading is None:
            return None
        age_seconds = (datetime.now() - _as_naive(self.last_live_reading["timestamp"])).total_seconds()
        if age_seconds <= settings["sensor_max_age_seconds"]:
            return self.last_live_reading
        return None

    @staticmethod
    def _median_value(history: deque[float], fallback: float | None) -> float | None:
        values = list(history)
        if not values:
            return fallback
        values.sort()
        mid = len(values) // 2
        if len(values) % 2:
            return round(values[mid], 2)
        return round((values[mid - 1] + values[mid]) / 2.0, 2)

    def _current_state(self) -> str | None:
        if self.monitor and self.monitor.last_state in {"ON", "OFF"}:
            return self.monitor.last_state
        state_result = action_exhaust_state()
        state = state_result.get("exhaust_state")
        if state in {"ON", "OFF"} and self.monitor:
            self.monitor.last_state = state
            if self.monitor.last_changed_at:
                if state == "ON" and self.last_on_ts is None:
                    self.last_on_ts = self.monitor.last_changed_at
                if state == "OFF" and self.last_off_ts is None:
                    self.last_off_ts = self.monitor.last_changed_at
        return state if state in {"ON", "OFF"} else None

    def _sync_state_timestamps(self, state: str, now: datetime) -> None:
        if state == "ON":
            if self.last_on_ts is None and self.monitor and self.monitor.last_changed_at:
                self.last_on_ts = self.monitor.last_changed_at
        else:
            if self.last_off_ts is None and self.monitor and self.monitor.last_changed_at:
                self.last_off_ts = self.monitor.last_changed_at

    def _can_switch(self, current_state: str, now: datetime, settings: Dict[str, Any]) -> bool:
        reference = self.last_on_ts if current_state == "ON" else self.last_off_ts
        if reference is None:
            return True
        elapsed = (now - _as_naive(reference)).total_seconds()
        required = settings["min_on_seconds"] if current_state == "ON" else settings["min_off_seconds"]
        if elapsed >= required:
            return True
        self._log_once(f"hold_{current_state.lower()}")
        return False

    @staticmethod
    def _can_turn_off(temp: float | None, rh: float | None, settings: Dict[str, Any]) -> bool:
        return (
            temp is not None
            and rh is not None
            and temp <= settings["temp_allow_off_below"]
            and rh <= settings["rh_turn_off_below"]
        )

    def _publish(self, next_state: str, temp: float | None, rh: float | None, reason: str) -> None:
        self.last_command_requested_state = next_state
        self.last_command_time = datetime.now()
        self.last_command_confirmed = None
        topic = self.topic_getter()
        self.last_command_result = f"Sent {next_state} command to {topic}"
        publish_device_state(topic, next_state)
        if next_state == "ON":
            self.last_on_ts = datetime.now()
        else:
            self.last_off_ts = datetime.now()
        self.last_change_reason = reason
        self._log_once(reason)
        confirmed = self._wait_for_confirmation(next_state)
        self.last_command_confirmed = confirmed
        self.last_command_result = f"{'Confirmed' if confirmed else 'No confirmation for'} {next_state}"
        if confirmed and get_exhaust_settings().get("debug_notify"):
            icon = "🟢" if next_state == "ON" else "🔴"
            temp_text = "–" if temp is None else f"{temp:.2f}°C"
            rh_text = "–" if rh is None else f"{rh:.1f}%"
            send_telegram_notification(f"{icon} Exhaust {next_state.lower()} | {reason} | {temp_text} | RH {rh_text}")

    def _wait_for_confirmation(self, expected_state: str, timeout_seconds: float = 8.0) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            state = self._current_state()
            if state == expected_state:
                return True
            time.sleep(0.5)
        return False

    def _log_once(self, reason: str | None) -> None:
        if reason == self.last_reason:
            return
        self.last_reason = reason
        if reason:
            print(f"[exhaust-controller] {reason}", flush=True)

    def snapshot(self) -> Dict[str, Any]:
        settings = get_exhaust_settings()
        now = datetime.now()
        reading_time = format_local_datetime(self.last_live_reading["timestamp"]) if self.last_live_reading else None
        reading_age = round((now - _as_naive(self.last_live_reading["timestamp"])).total_seconds(), 1) if self.last_live_reading else None
        current_temp = self.last_live_reading.get("temperature") if self.last_live_reading else None
        current_rh = self.last_live_reading.get("humidity") if self.last_live_reading else None
        return {
            "enabled": settings["enabled"],
            "plug_state": self._current_state(),
            "plug_power_w": self.monitor.last_power if self.monitor else None,
            "current_temp_c": current_temp,
            "current_rh": current_rh,
            "median_temp_c": self._median_value(self.temperature_history, current_temp),
            "median_rh": self._median_value(self.humidity_history, current_rh),
            "reading_time": reading_time,
            "reading_age_seconds": reading_age,
            "forced_refresh_active": self.forced_refresh_active,
            "last_reason": self.last_reason,
            "last_change_reason": self.last_change_reason,
            "last_on_ts": format_local_datetime(self.last_on_ts) if self.last_on_ts else None,
            "last_off_ts": format_local_datetime(self.last_off_ts) if self.last_off_ts else None,
            "last_command_requested_state": self.last_command_requested_state,
            "last_command_time": format_local_datetime(self.last_command_time) if self.last_command_time else None,
            "last_command_confirmed": self.last_command_confirmed,
            "last_command_result": self.last_command_result,
            "command_topic": self.topic_getter(),
            "rh_turn_on_above": settings["rh_turn_on_above"],
            "rh_turn_off_below": settings["rh_turn_off_below"],
            "temp_force_on_above": settings["temp_force_on_above"],
            "temp_allow_off_below": settings["temp_allow_off_below"],
        }


class LightController:
    def __init__(self, topic_getter: Any, monitor: PlugStateMonitor | None) -> None:
        self.topic_getter = topic_getter
        self.monitor = monitor
        self.thread: threading.Thread | None = None
        self.last_reason: str | None = None
        self.last_command_requested_state: str | None = None
        self.last_command_time: datetime | None = None
        self.last_command_confirmed: bool | None = None
        self.last_command_result: str | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="light-controller", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while True:
            try:
                interval = self._control_once()
            except Exception as exc:
                print(f"[light-controller] Fehler: {exc}\n{traceback.format_exc()}", flush=True)
                interval = DEFAULT_LIGHT_SETTINGS["control_interval_seconds"]
            time.sleep(max(15, int(interval)))

    def _control_once(self) -> int:
        settings = get_light_settings()
        if not settings["enabled"]:
            self.last_reason = None
            return int(settings["control_interval_seconds"])
        current_state = self._current_state()
        if current_state not in {"ON", "OFF"}:
            return int(settings["control_interval_seconds"])
        now_time = datetime.now().time()
        cycle = get_light_cycle_settings()
        should_be_on = _time_in_window(now_time, _parse_clock_time(cycle["lights_on_start"]), _parse_clock_time(cycle["lights_on_end"]))
        if should_be_on and current_state == "OFF":
            self._publish("ON", "cycle_on")
        elif not should_be_on and current_state == "ON":
            self._publish("OFF", "cycle_off")
        return int(settings["control_interval_seconds"])

    def _current_state(self) -> str | None:
        if self.monitor and self.monitor.last_state in {"ON", "OFF"}:
            return self.monitor.last_state
        result = action_light_state()
        state = result.get("light_state")
        return state if state in {"ON", "OFF"} else None

    def _publish(self, state: str, reason: str) -> None:
        self.last_reason = reason
        self.last_command_requested_state = state
        self.last_command_time = datetime.now()
        self.last_command_confirmed = None
        topic = self.topic_getter()
        self.last_command_result = f"Sent {state} command to {topic}"
        publish_device_state(topic, state)
        confirmed = self._wait_for_confirmation(state)
        self.last_command_confirmed = confirmed
        self.last_command_result = f"{'Confirmed' if confirmed else 'No confirmation for'} {state}"
        if confirmed and get_light_settings().get("debug_notify"):
            icon = "🟢" if state == "ON" else "🔴"
            send_telegram_notification(f"{icon} Light {state.lower()} | {reason}")

    def _wait_for_confirmation(self, expected_state: str, timeout_seconds: float = 8.0) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self._current_state() == expected_state:
                return True
            time.sleep(0.5)
        return False

    def snapshot(self) -> Dict[str, Any]:
        settings = get_light_settings()
        cycle = get_light_cycle_settings()
        return {
            "enabled": settings["enabled"],
            "plug_state": self._current_state(),
            "plug_power_w": self.monitor.last_power if self.monitor else None,
            "lights_on_start": cycle["lights_on_start"],
            "lights_on_end": cycle["lights_on_end"],
            "last_reason": self.last_reason,
            "last_command_requested_state": self.last_command_requested_state,
            "last_command_time": format_local_datetime(self.last_command_time) if self.last_command_time else None,
            "last_command_confirmed": self.last_command_confirmed,
            "last_command_result": self.last_command_result,
            "command_topic": self.topic_getter(),
        }


class HumidityController:
    def __init__(self, dehumidifier_monitor: PlugStateMonitor | None, humidifier_monitor: PlugStateMonitor | None) -> None:
        self.dehumidifier_monitor = dehumidifier_monitor
        self.humidifier_monitor = humidifier_monitor
        self.thread: threading.Thread | None = None
        self.humidity_history: deque[float] = deque(maxlen=9)
        self.last_live_reading: Dict[str, Any] | None = None
        self.last_reason: str | None = None
        self.last_change_reason: str | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="humidity-controller", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while True:
            try:
                interval = self._control_once()
            except Exception as exc:
                print(f"[humidity-controller] Fehler: {exc}\n{traceback.format_exc()}", flush=True)
                interval = DEFAULT_HUMIDITY_SETTINGS["control_interval_seconds"]
            time.sleep(max(15, int(interval)))

    def _control_once(self) -> int:
        settings = get_humidity_settings()
        if not settings["enabled"]:
            self.last_reason = None
            return int(settings["control_interval_seconds"])
        if settings["control_method"] != "devices":
            self.last_reason = "handled_by_exhaust"
            return int(settings["control_interval_seconds"])
        reading = get_live_sensor_reading()
        if reading and reading.get("humidity") is not None:
            self.last_live_reading = reading
            self.humidity_history.append(float(reading["humidity"]))
            while len(self.humidity_history) > settings["sensor_median_samples"]:
                self.humidity_history.popleft()
        if not self.last_live_reading:
            self.last_reason = "no_sensor"
            return int(settings["control_interval_seconds"])
        age = (datetime.now() - _as_naive(self.last_live_reading["timestamp"])).total_seconds()
        if age > settings["sensor_max_age_seconds"]:
            self.last_reason = "sensor_stale"
            return int(settings["control_interval_seconds"])
        humidity = self._median_value(self.humidity_history, self.last_live_reading.get("humidity"))
        dehum_state = self._device_state(action_dehumidifier_state, "dehumidifier_state")
        hum_state = self._device_state(action_humidifier_state, "humidifier_state")
        if humidity is None:
            return int(settings["control_interval_seconds"])
        now = datetime.now()
        if humidity > settings["rh_upper_threshold"] and is_dehumidifier_enabled():
            if hum_state == "ON":
                if self._can_switch(self.humidifier_monitor, settings["min_on_seconds"], now):
                    publish_device_state(get_humidifier_topic(), "OFF")
                else:
                    self.last_reason = "wait_humidifier_off"
                    return int(settings["control_interval_seconds"])
            if dehum_state == "OFF" and self._can_switch(self.dehumidifier_monitor, settings["min_off_seconds"], now):
                publish_device_state(get_dehumidifier_topic(), "ON")
                self.last_change_reason = "dehumidify"
                if settings["debug_notify"]:
                    send_telegram_notification(f"🟢 Dehumidifier on | RH {humidity:.1f}%")
            self.last_reason = "dehumidify"
            return int(settings["control_interval_seconds"])
        if humidity < settings["rh_lower_threshold"] and is_humidifier_enabled():
            if dehum_state == "ON":
                if self._can_switch(self.dehumidifier_monitor, settings["min_on_seconds"], now):
                    publish_device_state(get_dehumidifier_topic(), "OFF")
                else:
                    self.last_reason = "wait_dehumidifier_off"
                    return int(settings["control_interval_seconds"])
            if hum_state == "OFF" and self._can_switch(self.humidifier_monitor, settings["min_off_seconds"], now):
                publish_device_state(get_humidifier_topic(), "ON")
                self.last_change_reason = "humidify"
                if settings["debug_notify"]:
                    send_telegram_notification(f"🟢 Humidifier on | RH {humidity:.1f}%")
            self.last_reason = "humidify"
            return int(settings["control_interval_seconds"])
        if dehum_state == "ON" and self._can_switch(self.dehumidifier_monitor, settings["min_on_seconds"], now):
            publish_device_state(get_dehumidifier_topic(), "OFF")
            self.last_change_reason = "deadband"
        if hum_state == "ON" and self._can_switch(self.humidifier_monitor, settings["min_on_seconds"], now):
            publish_device_state(get_humidifier_topic(), "OFF")
            self.last_change_reason = "deadband"
        self.last_reason = "deadband"
        return int(settings["control_interval_seconds"])

    @staticmethod
    def _median_value(history: deque[float], fallback: float | None) -> float | None:
        values = list(history)
        if not values:
            return fallback
        values.sort()
        mid = len(values) // 2
        if len(values) % 2:
            return round(values[mid], 2)
        return round((values[mid - 1] + values[mid]) / 2.0, 2)

    @staticmethod
    def _device_state(fn: Any, key: str) -> str | None:
        result = fn()
        state = result.get(key)
        return state if state in {"ON", "OFF"} else None

    @staticmethod
    def _can_switch(monitor: PlugStateMonitor | None, required_seconds: int, now: datetime) -> bool:
        if not monitor or not monitor.last_changed_at:
            return True
        return (now - _as_naive(monitor.last_changed_at)).total_seconds() >= required_seconds

    def snapshot(self) -> Dict[str, Any]:
        settings = get_humidity_settings()
        current_rh = self.last_live_reading.get("humidity") if self.last_live_reading else None
        return {
            "enabled": settings["enabled"],
            "current_rh": current_rh,
            "median_rh": self._median_value(self.humidity_history, current_rh),
            "reading_time": format_local_datetime(self.last_live_reading["timestamp"]) if self.last_live_reading else None,
            "dehumidifier_state": self._device_state(action_dehumidifier_state, "dehumidifier_state"),
            "humidifier_state": self._device_state(action_humidifier_state, "humidifier_state"),
            "last_reason": self.last_reason,
            "last_change_reason": self.last_change_reason,
            "rh_upper_threshold": settings["rh_upper_threshold"],
            "rh_lower_threshold": settings["rh_lower_threshold"],
        }


def get_heater_debug_status() -> Dict[str, Any]:
    if not heater_controller:
        return {
            "enabled": False,
            "plug_state": None,
            "plug_power_w": None,
            "current_reading_c": None,
            "median_c": None,
            "target_c": None,
            "on_threshold_c": None,
            "off_threshold_c": None,
            "reading_time": None,
            "reading_age_seconds": None,
            "history": [],
            "last_decision": "Heater controller inactive.",
            "last_command_requested_state": None,
            "last_command_time": None,
            "last_command_confirmed": None,
            "last_command_result": None,
            "command_topic": None,
        }
    return heater_controller.snapshot()


def get_exhaust_debug_status() -> Dict[str, Any]:
    if not exhaust_controller:
        return {
            "enabled": False,
            "plug_state": None,
            "plug_power_w": None,
            "current_temp_c": None,
            "current_rh": None,
            "median_temp_c": None,
            "median_rh": None,
            "reading_time": None,
            "reading_age_seconds": None,
            "forced_refresh_active": False,
            "last_reason": "Exhaust controller inactive.",
            "last_change_reason": None,
            "last_on_ts": None,
            "last_off_ts": None,
            "last_command_requested_state": None,
            "last_command_time": None,
            "last_command_confirmed": None,
            "last_command_result": None,
            "command_topic": None,
            "rh_turn_on_above": None,
            "rh_turn_off_below": None,
            "temp_force_on_above": None,
            "temp_allow_off_below": None,
        }
    return exhaust_controller.snapshot()


def get_light_debug_status() -> Dict[str, Any]:
    if not light_controller:
        return {
            "enabled": False,
            "plug_state": None,
            "plug_power_w": None,
            "lights_on_start": None,
            "lights_on_end": None,
            "last_reason": "Light controller inactive.",
            "last_command_requested_state": None,
            "last_command_time": None,
            "last_command_confirmed": None,
            "last_command_result": None,
            "command_topic": None,
        }
    return light_controller.snapshot()


def get_humidity_debug_status() -> Dict[str, Any]:
    if not humidity_controller:
        return {
            "enabled": False,
            "current_rh": None,
            "median_rh": None,
            "reading_time": None,
            "dehumidifier_state": None,
            "humidifier_state": None,
            "last_reason": "Humidity controller inactive.",
            "last_change_reason": None,
            "rh_upper_threshold": None,
            "rh_lower_threshold": None,
        }
    return humidity_controller.snapshot()


def currency_symbol(code: str | None = None) -> str:
    selected = code or get_app_settings()["currency"]
    return {"EUR": "€", "USD": "$", "GBP": "£"}.get(selected, selected or "€")


def get_power_devices() -> List[Dict[str, Any]]:
    settings = get_app_settings()
    price = get_power_settings()["price_per_kwh"]
    device_defs = [
        ("pump", "Pump", "🚰", "teal", settings["pump_enabled"], pump_monitor, _pump_state_topics),
        ("heater", "Heater", "🔥", "orange", settings["heater_enabled"], heater_monitor, _heater_state_topics),
        ("exhaust", "Exhaust", "🌬️", "cyan", settings["exhaust_enabled"], exhaust_monitor, lambda: _device_state_topics(get_exhaust_topic())),
        ("light", "Light", "💡", "gold", settings["light_enabled"], light_monitor, _light_state_topics),
        ("dehumidifier", "Dehumidifier", "💨", "slate", settings["dehumidifier_enabled"], dehumidifier_monitor, _dehumidifier_state_topics),
        ("humidifier", "Humidifier", "💧", "blue", settings["humidifier_enabled"], humidifier_monitor, _humidifier_state_topics),
    ]
    devices: List[Dict[str, Any]] = []
    for device_id, name, icon, color_key, enabled, monitor, topic_getter in device_defs:
        if not enabled:
            continue
        metrics = _fetch_device_metrics(enabled, monitor, topic_getter)
        devices.append(
            {
                "id": device_id,
                "name": name,
                "icon": icon,
                "colorKey": color_key,
                "isOnline": metrics.get("updated_at") is not None,
                "currentPowerW": metrics.get("power_w") or 0.0,
                "energyYesterdayKWh": metrics.get("energy_yesterday_kwh") or 0.0,
                "energyTodayKWh": metrics.get("energy_today_kwh") or 0.0,
                "energyMonthKWh": metrics.get("energy_month_kwh") or 0.0,
                "costYesterday": round((metrics.get("energy_yesterday_kwh") or 0.0) * price, 2),
                "costToday": round((metrics.get("energy_today_kwh") or 0.0) * price, 2),
                "costMonth": round((metrics.get("energy_month_kwh") or 0.0) * price, 2),
                "updatedAt": metrics.get("updated_at"),
                "state": metrics.get("state"),
            }
        )
    return devices


def get_power_summary() -> Dict[str, Any]:
    devices = get_power_devices()
    settings = get_power_settings()
    currency = get_app_settings()["currency"]
    price = settings["price_per_kwh"]
    total_power = round(sum(float(item["currentPowerW"] or 0) for item in devices), 1)
    total_yesterday = round(sum(float(item["energyYesterdayKWh"] or 0) for item in devices), 3)
    total_today = round(sum(float(item["energyTodayKWh"] or 0) for item in devices), 3)
    total_month = round(sum(float(item["energyMonthKWh"] or 0) for item in devices), 3)
    return {
        "devices": devices,
        "currency": currency,
        "currencySymbol": currency_symbol(currency),
        "pricePerKWh": price,
        "totals": {
            "currentPowerW": total_power,
            "energyYesterdayKWh": total_yesterday,
            "energyTodayKWh": total_today,
            "energyMonthKWh": total_month,
            "costYesterday": round(total_yesterday * price, 2),
            "costToday": round(total_today * price, 2),
            "costMonth": round(total_month * price, 2),
        },
    }


def action_water_sensor_state() -> Dict[str, Any]:
    if not is_water_sensor_enabled():
        return {"message": "Reservoir-Sensor deaktiviert.", "water_sensor_state": None}
    if water_guard and water_guard.last_state:
        return {"message": "Wassermelder-Status (Cache).", "water_sensor_state": water_guard.last_state}
    persisted_state = None
    try:
        persisted_state = load_data().get("water_reservoir", {}).get("state")
    except Exception:
        persisted_state = None
    if persisted_state in {"ON", "OFF"}:
        return {
            "message": "Wassermelder-Status (persistiert).",
            "water_sensor_state": persisted_state,
        }
    if not mqtt:
        return {"message": "MQTT-Client fehlt.", "water_sensor_state": None}
    state_holder: Dict[str, Any] = {"state": None}
    event = threading.Event()

    def on_message(client: Any, _userdata: Any, msg: Any) -> None:
        try:
            payload_raw = msg.payload.decode("utf-8")
            payload = json.loads(payload_raw)
            for key in ("water_leak", "leak", "status", "state"):
                if key in payload:
                    val = payload[key]
                    break
            else:
                val = None
        except Exception:
            val = msg.payload.decode("utf-8").strip() or None
        val = _normalize_state(val)
        if val:
            state_holder["state"] = str(val).upper()
            event.set()

    client = mqtt_client()
    client.on_message = on_message
    mqtt_settings = get_mqtt_settings()
    client.connect(mqtt_settings["host"], mqtt_settings["port"], 60)
    for topic in _sensor_state_topics(get_water_sensor_topic()):
        client.subscribe(topic, qos=0)
    client.loop_start()
    event.wait(timeout=2.0)
    client.loop_stop()
    client.disconnect()
    resolved_state = state_holder.get("state")
    if resolved_state in {"ON", "OFF"}:
        try:
            data = load_data()
            sensor_info = data.get("water_reservoir", {})
            sensor_info["state"] = resolved_state
            if resolved_state == "OFF" and not sensor_info.get("dry_since"):
                sensor_info["dry_since"] = datetime.now().isoformat()
                sensor_info["first_alert_sent"] = False
                sensor_info["repeat_alert_sent"] = False
            if resolved_state == "ON":
                sensor_info["dry_since"] = None
                sensor_info["first_alert_sent"] = False
                sensor_info["repeat_alert_sent"] = False
                sensor_info["wet_since"] = datetime.now().isoformat()
            data["water_reservoir"] = sensor_info
            save_data(data)
        except Exception:
            pass
    return {
        "message": "Wassermelder-Status abgefragt.",
        "water_sensor_state": resolved_state,
    }


class WeeklySummaryThread:
    def __init__(self) -> None:
        self.thread: threading.Thread | None = None
        self._last_sent_date: Any = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="weekly-summary", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while True:
            try:
                self._check_and_send()
            except Exception as exc:
                print(f"[weekly-summary] Error: {exc}", flush=True)
            time.sleep(60)

    def _check_and_send(self) -> None:
        settings = get_app_settings()
        if not settings.get("weekly_summary_enabled", False):
            return
        if not settings.get("telegram_enabled", True):
            return
        now = datetime.now()
        if now.weekday() != 0:  # Monday
            return
        send_time_str = settings.get("weekly_summary_time", "09:00")
        try:
            send_h, send_m = map(int, send_time_str.split(":"))
        except Exception:
            send_h, send_m = 9, 0
        if now.hour != send_h or now.minute != send_m:
            return
        today = now.date()
        if self._last_sent_date == today:
            return
        self._last_sent_date = today
        self._send_digest(now)

    def _send_digest(self, now: datetime) -> None:
        data = load_data()
        settings_app = get_app_settings()
        lang = settings_app.get("language", "en")
        stats = get_week_and_phase(data.get("sprout_date"), data.get("flower_date"))
        sensor = compute_sensor_stats(168)
        power = get_power_summary()
        image_stats = get_image_stats()
        last_w = parse_date(data.get("last_watering"))
        days_water = (now - last_w).days if last_w else None
        water_str = (
            (f"{days_water}d ago" if lang == "en" else f"vor {days_water}d")
            if days_water is not None else "–"
        )
        phase = stats.get("phase") or "–"
        week_n = stats.get("week_number") or "–"
        currency = power.get("currencySymbol", "€")
        cost_month = power["totals"]["costMonth"]

        def fmt(v: Any) -> str:
            return f"{v:.1f}" if v is not None else "–"

        if lang == "de":
            msg = (
                f"🌿 <b>PlantWatch Wochenbericht</b> — {now.strftime('%d.%m.%Y')}\n\n"
                f"📅 <b>Phase:</b> {phase}, Woche {week_n}\n"
                f"💧 <b>Letzte Bewässerung:</b> {water_str}\n"
                f"📸 <b>Fotos gesamt:</b> {image_stats['count']}\n\n"
                f"🌡️ <b>Klima (7 Tage)</b>\n"
                f"  Temp: Ø {fmt(sensor.get('temp_avg'))}°C  (↓{fmt(sensor.get('temp_min'))} ↑{fmt(sensor.get('temp_max'))})\n"
                f"  Feuchte: Ø {fmt(sensor.get('hum_avg'))}%  (↓{fmt(sensor.get('hum_min'))} ↑{fmt(sensor.get('hum_max'))})\n\n"
                f"⚡ <b>Strom diesen Monat:</b> {power['totals']['energyMonthKWh']} kWh ({currency}{cost_month})"
            )
        else:
            msg = (
                f"🌿 <b>PlantWatch Weekly Digest</b> — {now.strftime('%b %d, %Y')}\n\n"
                f"📅 <b>Phase:</b> {phase}, Week {week_n}\n"
                f"💧 <b>Last watered:</b> {water_str}\n"
                f"📸 <b>Total photos:</b> {image_stats['count']}\n\n"
                f"🌡️ <b>Climate (7 days)</b>\n"
                f"  Temp: avg {fmt(sensor.get('temp_avg'))}°C  (↓{fmt(sensor.get('temp_min'))} ↑{fmt(sensor.get('temp_max'))})\n"
                f"  Humidity: avg {fmt(sensor.get('hum_avg'))}%  (↓{fmt(sensor.get('hum_min'))} ↑{fmt(sensor.get('hum_max'))})\n\n"
                f"⚡ <b>Power this month:</b> {power['totals']['energyMonthKWh']} kWh ({currency}{cost_month})"
            )
        send_telegram_notification(msg)


class ControllerWatchdog:
    """Watches automation controller threads and restarts any that have silently died.
    Also monitors MQTT connection health and BLE sensor freshness."""

    def __init__(
        self,
        controllers: list,
        critical_monitors: list | None = None,
    ) -> None:
        self.controllers = controllers
        # List of (PlugStateMonitor, label_str) tuples for MQTT health checks
        self.critical_monitors: list = critical_monitors or []
        self.thread: threading.Thread | None = None
        self._sensor_was_alive: bool = False  # avoid alerting before first reading

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="controller-watchdog", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while True:
            time.sleep(60)
            now = datetime.now()

            # --- Thread health: restart dead controller threads ---
            for controller in self.controllers:
                if controller is None:
                    continue
                t = getattr(controller, "thread", None)
                if t is None or not t.is_alive():
                    label = type(controller).__name__
                    print(f"[watchdog] {label} thread dead — restarting.", flush=True)
                    try:
                        controller.start()
                    except Exception as exc:
                        print(f"[watchdog] Failed to restart {label}: {exc}", flush=True)

            # --- MQTT health: alert if critical monitor has been offline too long ---
            for monitor, label in self.critical_monitors:
                if monitor is None:
                    continue
                if not monitor.is_connected and monitor.disconnected_since is not None:
                    offline_secs = (now - _as_naive(monitor.disconnected_since)).total_seconds()
                    if offline_secs >= MQTT_OFFLINE_ALERT_SECONDS:
                        if _should_alert(f"mqtt_offline_{label}"):
                            send_telegram_notification(
                                f"📡 MQTT-Verbindung verloren: {label} seit {int(offline_secs / 60)}min offline."
                            )

            # --- BLE sensor health: alert if no fresh reading for too long ---
            hc = next((c for c in self.controllers if isinstance(c, HeaterController)), None)
            if hc is not None:
                lr = hc.last_live_reading
                if lr is not None:
                    self._sensor_was_alive = True
                    sensor_age = (now - _as_naive(lr["timestamp"])).total_seconds()
                    if sensor_age >= SENSOR_OFFLINE_ALERT_SECONDS:
                        if _should_alert("sensor_offline"):
                            send_telegram_notification(
                                f"🌡️ Sensor seit {int(sensor_age / 60)}min nicht erreichbar — keine Temperaturwerte!"
                            )
                elif self._sensor_was_alive:
                    # Had readings before but now None — sensor disappeared
                    if _should_alert("sensor_offline"):
                        send_telegram_notification(
                            "🌡️ Sensordaten nicht mehr verfügbar — BLE-Sensor offline?"
                        )


water_guard = WaterLeakGuard() if WATER_GUARD_ENABLED and mqtt else None
if water_guard:
    water_guard.start()
pump_monitor = PlugStateMonitor(get_pump_topic, "pump") if mqtt else None
heater_monitor = PlugStateMonitor(get_heater_topic, "heater") if mqtt else None
exhaust_monitor = PlugStateMonitor(get_exhaust_topic, "exhaust") if mqtt else None
light_monitor = PlugStateMonitor(get_light_topic, "light") if mqtt else None
dehumidifier_monitor = PlugStateMonitor(get_dehumidifier_topic, "dehumidifier") if mqtt else None
humidifier_monitor = PlugStateMonitor(get_humidifier_topic, "humidifier") if mqtt else None
if pump_monitor:
    pump_monitor.start()
if heater_monitor:
    heater_monitor.start()
if exhaust_monitor:
    exhaust_monitor.start()
if light_monitor:
    light_monitor.start()
if dehumidifier_monitor:
    dehumidifier_monitor.start()
if humidifier_monitor:
    humidifier_monitor.start()
heater_controller = HeaterController(get_heater_topic, heater_monitor, light_monitor) if mqtt else None
if heater_controller:
    heater_controller.start()
exhaust_controller = ExhaustController(get_exhaust_topic, exhaust_monitor) if mqtt else None
if exhaust_controller:
    exhaust_controller.start()
light_controller = LightController(get_light_topic, light_monitor) if mqtt else None
if light_controller:
    light_controller.start()
humidity_controller = HumidityController(dehumidifier_monitor, humidifier_monitor) if mqtt else None
if humidity_controller:
    humidity_controller.start()
controller_watchdog = ControllerWatchdog(
    [heater_controller, exhaust_controller, light_controller, humidity_controller],
    critical_monitors=[(heater_monitor, "Heizung"), (exhaust_monitor, "Abluft")],
)
controller_watchdog.start()
weekly_summary = WeeklySummaryThread()
weekly_summary.start()


def perform_action(action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    action = action.lower()
    if action == "photo":
        return action_photo()
    if action == "temp":
        return action_temp()
    if action == "camera_test":
        return action_camera_test(payload)
    if action == "camera_test_apply":
        return action_camera_test_apply()
    if action == "flower":
        return action_flower()
    if action == "flower_reset":
        return action_flower_reset()
    if action == "logs":
        return action_logs()
    if action == "water":
        return action_water(payload.get("date"), payload.get("clear"))
    if action == "pump":
        return action_pump(payload.get("command"), payload.get("minutes"))
    if action == "pump_state":
        return action_pump_state()
    if action in {"heater", "dehumidifier"}:
        return action_heater(payload.get("command"))
    if action in {"heater_state", "dehumidifier_state"}:
        return action_heater_state()
    if action == "light":
        return action_light(payload.get("command"))
    if action == "light_state":
        return action_light_state()
    if action == "dehumidifier_device":
        return action_dehumidifier(payload.get("command"))
    if action == "dehumidifier_device_state":
        return action_dehumidifier_state()
    if action == "humidifier":
        return action_humidifier(payload.get("command"))
    if action == "humidifier_state":
        return action_humidifier_state()
    if action == "exhaust":
        return action_exhaust(payload.get("command"))
    if action == "exhaust_state":
        return action_exhaust_state()
    if action == "water_sensor_state":
        return action_water_sensor_state()
    if action == "fert_defaults":
        data = load_data()
        liters = float(payload.get("liters", 10))
        percent = float(payload.get("percent", 100))
        data["fert_defaults"] = {"liters": liters, "percent": percent}
        save_data(data)
        return {"message": f"✅ Standard auf {liters} L @ {percent}% gesetzt."}
    if action == "fertilizer_save":
        result = action_fertilizer_save(payload)
        if result.get("error"):
            return {"message": f"❌ {result['error']}"}
        return result
    if action == "fertilizer_delete":
        result = action_fertilizer_delete(payload.get("name"))
        if result.get("error"):
            return {"message": f"❌ {result['error']}"}
        return result
    if action == "heater_defaults":
        result = save_heater_settings(payload)
        if result.get("error"):
            return {"message": f"❌ {result['error']}"}
        return result
    if action == "light_defaults":
        result = save_light_settings(payload)
        if result.get("error"):
            return {"message": f"❌ {result['error']}"}
        return result
    if action == "light_cycle_settings":
        result = save_light_cycle_settings(payload)
        if result.get("error"):
            return {"message": f"❌ {result['error']}"}
        return result
    if action == "timelapse_settings":
        result = save_timelapse_settings(payload)
        if result.get("error"):
            return {"message": f"❌ {result['error']}"}
        return result
    if action == "power_settings":
        result = save_power_settings(payload)
        if result.get("error"):
            return {"message": f"❌ {result['error']}"}
        return result
    if action == "humidity_defaults":
        result = save_humidity_settings(payload)
        if result.get("error"):
            return {"message": f"❌ {result['error']}"}
        return result
    if action == "exhaust_defaults":
        result = save_exhaust_settings(payload)
        if result.get("error"):
            return {"message": f"❌ {result['error']}"}
        return result
    if action == "app_settings":
        result = save_app_settings(payload)
        if result.get("error"):
            return {"message": f"❌ {result['error']}"}
        return result
    if action == "timelapse_video":
        return action_timelapse()
    return {"message": "❓ Unbekannte Aktion."}


@app.route("/")
def index():
    dash = compute_dashboard_data()
    return render_template(
        "dashboard.html",
        dashboard=dash,
        active_page="dashboard",
        timelapse_settings=get_timelapse_settings(),
    )


@app.route("/fertilizer")
def fertilizer_page():
    dash = compute_dashboard_data()
    fert_raw = dash["grow"].get("fertilizers", {})
    fert_units = dash["grow"].get("fertilizer_units", {})
    fert_defaults = dash["grow"].get("fert_defaults", {"liters": 10, "percent": 100})
    fert_map: Dict[str, Dict[int, Any]] = {}
    week_set = set()
    for name, schedule in fert_raw.items():
        fert_map[name] = {}
        for week_key, value in schedule.items():
            try:
                week_num = int(float(week_key))
            except (ValueError, TypeError):
                continue
            fert_map[name][week_num] = value
            week_set.add(week_num)
    week_list = sorted(week_set) or list(range(1, 17))
    highlight_week = dash["stats"].get("current_week") or 1
    if week_list and highlight_week not in week_list:
        highlight_week = week_list[-1]
    fertilizer_catalog = []
    for name in sorted(fert_map.keys(), key=str.lower):
        fertilizer_catalog.append(
            {
                "name": name,
                "unit": fert_units.get(name, "ml/L"),
                "schedule": {str(week): fert_map[name].get(week, 0) for week in week_list},
            }
        )
    default_plan = calculate_fert_plan(
        float(fert_defaults.get("liters", 10)),
        float(fert_defaults.get("percent", 100)),
    )
    return render_template(
        "fertilizer.html",
        dashboard=dash,
        active_page="fertilizer",
        fertilizer_map=fert_map,
        fertilizer_weeks=week_list,
        fertilizer_catalog=fertilizer_catalog,
        highlight_week=highlight_week,
        default_plan=default_plan,
        fert_defaults=fert_defaults,
    )


@app.route("/watering")
def watering_page():
    dash = compute_dashboard_data()
    return render_template(
        "watering.html",
        dashboard=dash,
        active_page="watering",
        CHECK_INTERVAL_DAYS=CHECK_INTERVAL_DAYS,
    )


@app.route("/light")
def light_page():
    dash = compute_dashboard_data()
    return render_template(
        "light.html",
        dashboard=dash,
        active_page="light",
        light_settings=get_light_settings(),
        light_cycle_settings=get_light_cycle_settings(),
    )


@app.route("/timelapse")
def timelapse_page():
    dash = compute_dashboard_data()
    return render_template(
        "timelapse.html",
        dashboard=dash,
        active_page="timelapse",
        timelapse_settings=get_timelapse_settings(),
        app_settings=get_app_settings(),
        camera_test_image=get_camera_test_image_info(),
    )


@app.route("/power")
def power_page():
    dash = compute_dashboard_data()
    return render_template(
        "power.html",
        dashboard=dash,
        active_page="power",
        power_settings=get_power_settings(),
        power_summary=get_power_summary(),
        app_settings=get_app_settings(),
        currency_symbol=currency_symbol,
    )


@app.route("/climate")
def climate_page():
    dash = compute_dashboard_data()
    latest = get_latest_sensor_point()
    stats_24h = compute_sensor_stats(24)
    stats_7d = compute_sensor_stats(24 * 7)
    vpd_target = dash.get("vpd", {}).get("optimal")
    heater_settings = get_heater_settings()
    exhaust_settings = get_exhaust_settings()
    humidity_settings = get_humidity_settings()
    return render_template(
        "climate.html",
        dashboard=dash,
        active_page="climate",
        latest_sensor=latest,
        stats_24h=stats_24h,
        stats_7d=stats_7d,
        vpd_target=vpd_target,
        heater_settings=heater_settings,
        exhaust_settings=exhaust_settings,
        humidity_settings=humidity_settings,
    )


@app.route("/settings")
def settings_page():
    dash = compute_dashboard_data()
    return render_template(
        "settings.html",
        dashboard=dash,
        active_page="settings",
        app_settings=get_app_settings(),
        light_cycle_settings=get_light_cycle_settings(),
        timelapse_settings=get_timelapse_settings(),
        currency_symbol=currency_symbol,
        camera_test_image=get_camera_test_image_info(),
    )


@app.route("/api/dashboard")
def api_dashboard():
    return jsonify(compute_dashboard_data())


@app.route("/api/fert-plan", methods=["POST"])
def api_fert_plan():
    payload = request.get_json(force=True)
    liters = float(payload.get("liters", 0))
    percent = float(payload.get("percent", 100))
    if liters <= 0:
        return jsonify({"error": "Litermenge muss > 0 sein."}), 400
    if percent <= 0:
        return jsonify({"error": "Prozent muss > 0 sein."}), 400
    result = calculate_fert_plan(liters, percent)
    return jsonify(result)


@app.route("/api/sensor-history")
def api_sensor_history():
    range_param = request.args.get("range", "72h").lower()
    start_raw = request.args.get("start")
    end_raw = request.args.get("end")
    hours = None
    start_dt = None
    end_dt = None
    if range_param.endswith("h"):
        try:
            hours = int(range_param[:-1])
        except ValueError:
            hours = 72
    if start_raw:
        try:
            start_dt = datetime.fromisoformat(start_raw)
        except ValueError:
            return jsonify({"error": "Ungültiger Startzeitpunkt."}), 400
    if end_raw:
        try:
            end_dt = datetime.fromisoformat(end_raw)
        except ValueError:
            return jsonify({"error": "Ungültiger Endzeitpunkt."}), 400
    if start_dt and end_dt and start_dt > end_dt:
        return jsonify({"error": "Start muss vor Ende liegen."}), 400
    data = fetch_sensor_history(hours, start=start_dt, end=end_dt)
    return jsonify({"points": data})


@app.route("/api/heater-debug")
def api_heater_debug():
    return jsonify(get_heater_debug_status())


@app.route("/api/exhaust-debug")
def api_exhaust_debug():
    return jsonify(get_exhaust_debug_status())


@app.route("/api/light-debug")
def api_light_debug():
    return jsonify(get_light_debug_status())


@app.route("/api/humidity-debug")
def api_humidity_debug():
    return jsonify(get_humidity_debug_status())


@app.route("/api/power-summary")
def api_power_summary():
    return jsonify(get_power_summary())


@app.route("/api/scan-switchbot")
def api_scan_switchbot():
    """Run a BLE scan and return nearby SwitchBot devices."""
    try:
        from bleak import BleakScanner  # type: ignore
        import asyncio

        async def _scan():
            devices = await BleakScanner.discover(timeout=10)
            return [
                {"name": d.name, "address": d.address.upper()}
                for d in devices
                if d.name and ("SwitchBot" in d.name or "W3400010" in d.name)
            ]

        found = asyncio.run(_scan())
        return jsonify({"devices": found})
    except ImportError:
        return jsonify({"error": "bleak not installed"}), 500
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/action", methods=["POST"])
def api_action():
    payload = request.get_json(force=True)
    action = payload.get("action")
    if not action:
        return jsonify({"error": "action fehlt"}), 400
    result = perform_action(action, payload)
    return jsonify({"ok": True, **result})


@app.route("/latest-photo")
def latest_photo():
    info = get_latest_timelapse_photo()
    if not info:
        abort(404)
    return send_file(info["path"], mimetype="image/jpeg")


@app.route("/latest-timelapse-photo")
def latest_timelapse_photo():
    info = get_latest_timelapse_capture()
    if not info:
        abort(404)
    return send_file(info["path"], mimetype="image/jpeg")


@app.route("/latest-camera-test")
def latest_camera_test():
    info = get_camera_test_image_info()
    if not info:
        abort(404)
    return send_file(info["path"], mimetype="image/jpeg")


@app.route("/latest-timelapse")
def latest_timelapse():
    if not os.path.exists(TIMELAPSE_VIDEO_FILE):
        abort(404)
    # conditional=True enables HTTP range requests so the video tag can seek/stream
    return send_file(TIMELAPSE_VIDEO_FILE, mimetype="video/mp4", conditional=True)


@app.route("/download-timelapse")
def download_timelapse():
    if not os.path.exists(TIMELAPSE_VIDEO_FILE):
        abort(404)
    return send_file(
        TIMELAPSE_VIDEO_FILE,
        mimetype="video/mp4",
        as_attachment=True,
        download_name="timelapse.mp4",
    )


if __name__ == "__main__":
    debug_mode = os.getenv("GROWCAM_DEBUG", "false").lower() in ("1", "true", "yes")
    # Disable reloader to avoid double-start under systemd
    app.run(host="0.0.0.0", port=5050, debug=debug_mode, use_reloader=False)

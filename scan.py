import asyncio
from bleak import BleakScanner

async def scan_switchbot_meters():
    print("🔎 Scanne nach BLE-Geräten für 10 Sekunden...")
    devices = await BleakScanner.discover(timeout=10)

    found = []
    for d in devices:
        if d.name:  # Nur Geräte mit Namen prüfen
            if "SwitchBot" in d.name or "W3400010" in d.name:
                found.append(d)

    if not found:
        print("❌ Kein SwitchBot Meter gefunden.")
    else:
        print("✅ Gefundene SwitchBot Geräte:")
        for d in found:
            print(f"- Name: {d.name}, MAC: {d.address}")

if __name__ == "__main__":
    asyncio.run(scan_switchbot_meters())

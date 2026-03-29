import asyncio
from bleak import BleakScanner

async def scan_switchbot_meters():
    print("🔎 Scanning for BLE devices for 10 seconds...")
    devices = await BleakScanner.discover(timeout=10)

    found = []
    for d in devices:
        if d.name:
            if "SwitchBot" in d.name or "W3400010" in d.name:
                found.append(d)

    if not found:
        print("❌ No SwitchBot Meter found.")
    else:
        print("✅ SwitchBot devices found:")
        for d in found:
            print(f"- Name: {d.name}, MAC: {d.address}")

if __name__ == "__main__":
    asyncio.run(scan_switchbot_meters())

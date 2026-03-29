# pip install bleak
import os
import asyncio
from bleak import BleakScanner
from datetime import datetime

TARGET_MAC = os.getenv("SWITCHBOT_MAC", "")  # set SWITCHBOT_MAC in your .env

def decode_switchbot(manufacturer: bytes, service_datas: dict):
    """Dekodiert SwitchBot Outdoor Meter aus Manufacturer- u. Service-Data."""
    if len(manufacturer) < 12:
        return None

    # Luftfeuchte
    humidity = manufacturer[10] & 0x7F

    # Temperatur
    frac = (manufacturer[8] & 0x0F) * 0.1
    whole = manufacturer[9] & 0x7F
    temp = whole + frac
    if (manufacturer[9] & 0x80) == 0:
        temp = -temp

    # Batterie (aus Service-Data, 3 Bytes, drittes Byte)
    battery = None
    for _, v in (service_datas or {}).items():
        if len(v) == 3:
            battery = v[2] & 0x7F
            break

    return round(temp, 1), humidity, battery

async def main():
    print(f"Suche nach {TARGET_MAC} … (30s)")
    last = None

    def cb(device, adv):
        if device.address.upper() != TARGET_MAC:
            return

        # passende Manufacturer-Data (12 Byte)
        md = None
        for _, data in (adv.manufacturer_data or {}).items():
            if len(data) == 12:
                md = data
                break
        if not md:
            return

        decoded = decode_switchbot(md, adv.service_data or {})
        if not decoded:
            return

        temp, hum, batt = decoded
        key = (temp, hum, batt)
        if key == last:
            return

        nonlocal last
        last = key

        raw_hex = " ".join(f"{b:02x}" for b in md)
        print("\nRAW (manufacturer):", raw_hex)
        print(f"MAC: {device.address}  RSSI: {adv.rssi}  Zeit: {datetime.now().strftime('%H:%M:%S')}")
        print(f"Temperatur: {temp:.1f} °C")
        print(f"Luftfeuchte: {hum} %")
        print(f"Batterie: {batt if batt is not None else '—'} %")

    scanner = BleakScanner(cb)
    async with scanner:
        await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())

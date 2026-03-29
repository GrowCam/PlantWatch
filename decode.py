#!/usr/bin/env python3
"""
Complete SwitchBot Outdoor Meter BLE Scanner
Requires: pip install bleak

Usage: python switchbot_complete_scanner.py
"""

import asyncio
import logging
import os
import struct
import math
from datetime import datetime
from typing import Dict, Optional, Tuple
from bleak import BleakScanner

# Set up logging to see debug information
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SwitchBotOutdoorMeterDecoder:
    """
    Decoder for SwitchBot Outdoor Thermo-Hygrometer BLE advertisements.

    This class implements the reverse-engineered protocol for parsing
    temperature, humidity, and battery data from BLE advertising packets.
    """

    def __init__(self, mac_address: str):
        """
        Initialize decoder for a specific SwitchBot device.

        Args:
            mac_address: MAC address of the SwitchBot device (e.g., "AA:BB:CC:DD:EE:FF")
        """
        self.mac_address = mac_address.upper()

    def decode_battery(self, service_data: bytes) -> Optional[int]:
        """
        Decode battery percentage from service data.

        Args:
            service_data: 3-byte service data from BLE advertisement

        Returns:
            Battery percentage (0-100) or None if invalid data
        """
        if len(service_data) != 3:
            return None

        # Battery is at byte 2 (zero-indexed) with 0x7F bitmask
        battery_pct = service_data[2] & 0x7F
        return battery_pct

    def decode_humidity(self, manufacturer_data: bytes) -> Optional[int]:
        """
        Decode humidity percentage from manufacturer data.

        Args:
            manufacturer_data: 12-byte manufacturer data from BLE advertisement

        Returns:
            Humidity percentage (0-100) or None if invalid data
        """
        if len(manufacturer_data) != 12:
            return None

        # Humidity is at byte 10 (zero-indexed) with 0x7F bitmask
        humidity_pct = manufacturer_data[10] & 0x7F
        return humidity_pct

    def decode_temperature(self, manufacturer_data: bytes) -> Optional[float]:
        """
        Decode temperature from manufacturer data.

        Temperature is stored across two bytes with fractional and whole parts.

        Args:
            manufacturer_data: 12-byte manufacturer data from BLE advertisement

        Returns:
            Temperature in Celsius or None if invalid data
        """
        if len(manufacturer_data) != 12:
            return None

        # Temperature data is in bytes 8 and 9 (zero-indexed)
        fractional_byte = manufacturer_data[8]  # Contains fractional part
        whole_byte = manufacturer_data[9]       # Contains whole part and sign bit

        # Extract fractional part (last 4 bits of byte 8) and convert to decimal
        fractional_part = float(fractional_byte & 0x0F) * 0.1

        # Extract whole number part (lower 7 bits of byte 9)
        whole_part = float(whole_byte & 0x7F)

        # Combine fractional and whole parts
        temperature = fractional_part + whole_part

        # Check sign bit (MSB of byte 9): 0 = negative, 1 = positive
        if not (whole_byte & 0x80):
            temperature = -temperature

        return round(temperature, 1)

    def decode_ble_advertisement(self, service_data: bytes, manufacturer_data: bytes) -> Dict:
        """
        Decode complete BLE advertisement data.

        Args:
            service_data: Service data bytes from BLE advertisement
            manufacturer_data: Manufacturer data bytes from BLE advertisement

        Returns:
            Dictionary containing decoded sensor values
        """
        result = {
            'mac_address': self.mac_address,
            'battery': None,
            'temperature': None,
            'humidity': None,
            'timestamp': None
        }

        # Decode battery from service data
        if service_data and len(service_data) == 3:
            result['battery'] = self.decode_battery(service_data)

        # Decode temperature and humidity from manufacturer data
        if manufacturer_data and len(manufacturer_data) == 12:
            result['temperature'] = self.decode_temperature(manufacturer_data)
            result['humidity'] = self.decode_humidity(manufacturer_data)

        return result

    @staticmethod
    def calculate_absolute_humidity(temperature: float, humidity: float) -> float:
        """
        Calculate absolute humidity from temperature and relative humidity.

        Args:
            temperature: Temperature in Celsius
            humidity: Relative humidity percentage

        Returns:
            Absolute humidity in g/m³
        """
        if temperature is None or humidity is None:
            return None

        # Formula from the article
        numerator = 6.112 * math.exp((17.67 * temperature) / (temperature + 243.5)) * humidity * 2.1674
        denominator = 273.15 + temperature
        return round(numerator / denominator, 2)

    @staticmethod
    def calculate_dew_point(temperature: float, humidity: float) -> float:
        """
        Calculate dew point from temperature and relative humidity.

        Args:
            temperature: Temperature in Celsius
            humidity: Relative humidity percentage

        Returns:
            Dew point in Celsius
        """
        if temperature is None or humidity is None:
            return None

        # Magnus formula constants
        a = 17.67
        b = 243.5

        # Calculate alpha
        alpha = ((a * temperature) / (b + temperature)) + math.log(humidity / 100.0)

        # Calculate dew point
        dew_point = (b * alpha) / (a - alpha)
        return round(dew_point, 1)

    @staticmethod
    def calculate_vapor_pressure_deficit(temperature: float, humidity: float) -> float:
        """
        Calculate vapor pressure deficit from temperature and relative humidity.

        Args:
            temperature: Temperature in Celsius
            humidity: Relative humidity percentage

        Returns:
            Vapor pressure deficit in kPa
        """
        if temperature is None or humidity is None:
            return None

        # Calculate saturation vapor pressure (es)
        es = 6.112 * math.exp((17.67 * temperature) / (temperature + 243.5))

        # Calculate VPD
        vpd = (1.0 - (humidity / 100.0)) * es

        # Convert from hPa to kPa
        return round(vpd / 10.0, 2)


class SwitchBotBLEScanner:
    def __init__(self, mac_address: str):
        self.decoder = SwitchBotOutdoorMeterDecoder(mac_address)
        self.target_mac = mac_address.upper()
        self.last_data = {}

    def extract_advertisement_data(self, advertisement_data):
        """Extract service and manufacturer data from BLE advertisement."""
        service_data = None
        manufacturer_data = None

        # Extract service data (usually keyed by UUID)
        if hasattr(advertisement_data, 'service_data') and advertisement_data.service_data:
            # SwitchBot typically uses service data - get the first available
            for uuid, data in advertisement_data.service_data.items():
                service_data = data
                logger.debug(f"Service data ({uuid}): {data.hex()}")
                break

        # Extract manufacturer data
        if hasattr(advertisement_data, 'manufacturer_data') and advertisement_data.manufacturer_data:
            # Get manufacturer data - typically keyed by company ID
            for company_id, data in advertisement_data.manufacturer_data.items():
                manufacturer_data = data
                logger.debug(f"Manufacturer data (ID: {company_id}): {data.hex()}")
                break

        return service_data, manufacturer_data

    def on_advertisement_received(self, device, advertisement_data):
        """Callback when BLE advertisement is received."""
        if device.address.upper() == self.target_mac:
            logger.info(f"📡 Advertisement from SwitchBot: {device.address}")
            logger.debug(f"RSSI: {advertisement_data.rssi} dBm")
            logger.debug(f"Local name: {advertisement_data.local_name}")

            # Extract raw data
            service_data, manufacturer_data = self.extract_advertisement_data(advertisement_data)

            # Log raw bytes for debugging
            if service_data:
                logger.info(f"Service data ({len(service_data)} bytes): {service_data.hex()}")
            if manufacturer_data:
                logger.info(f"Manufacturer data ({len(manufacturer_data)} bytes): {manufacturer_data.hex()}")

            # Decode the sensor data
            result = self.decoder.decode_ble_advertisement(service_data, manufacturer_data)

            # Only print if we got valid data
            if any(result[key] is not None for key in ['battery', 'temperature', 'humidity']):
                result['timestamp'] = datetime.now().strftime("%H:%M:%S")
                self.print_sensor_data(result)
                self.last_data = result
            else:
                logger.warning("❌ No valid sensor data found in advertisement")
                # Still show what we found for debugging
                self.print_debug_data(service_data, manufacturer_data)

    def print_debug_data(self, service_data, manufacturer_data):
        """Print raw data for debugging when decoding fails."""
        print("\n" + "🔍 DEBUG: Raw Advertisement Data")
        print("-" * 40)
        if service_data:
            print(f"Service data: {service_data.hex()} ({len(service_data)} bytes)")
            for i, byte in enumerate(service_data):
                print(f"  Byte {i}: 0x{byte:02x} ({byte}) & 0x7F = {byte & 0x7F}")

        if manufacturer_data:
            print(f"Manufacturer data: {manufacturer_data.hex()} ({len(manufacturer_data)} bytes)")
            for i, byte in enumerate(manufacturer_data):
                masked = byte & 0x7F
                print(f"  Byte {i}: 0x{byte:02x} ({byte}) & 0x7F = {masked}")
        print("-" * 40)

    def print_sensor_data(self, data):
        """Print formatted sensor data."""
        print("\n" + "="*50)
        print(f"🌡️  SwitchBot Outdoor Meter Data - {data['timestamp']}")
        print("="*50)

        if data['battery'] is not None:
            print(f"🔋 Battery:     {data['battery']}%")

        if data['temperature'] is not None:
            print(f"🌡️  Temperature: {data['temperature']}°C")

        if data['humidity'] is not None:
            print(f"💧 Humidity:    {data['humidity']}%")

        # Calculate derived values if we have temp and humidity
        if data['temperature'] is not None and data['humidity'] is not None:
            abs_humidity = self.decoder.calculate_absolute_humidity(data['temperature'], data['humidity'])
            dew_point = self.decoder.calculate_dew_point(data['temperature'], data['humidity'])
            vpd = self.decoder.calculate_vapor_pressure_deficit(data['temperature'], data['humidity'])

            print(f"💨 Abs. Humidity: {abs_humidity} g/m³")
            print(f"🌊 Dew Point:     {dew_point}°C")
            print(f"📊 VPD:          {vpd} kPa")

        print("="*50)


def test_with_sample_data():
    """Test the decoder with sample data before starting BLE scan."""
    print("🧪 Testing decoder with sample data...")

    decoder = SwitchBotOutdoorMeterDecoder("AA:BB:CC:DD:EE:FF")

    # Sample data that should decode to: Battery=100%, Temp=23.3°C, Humidity=46%
    sample_service_data = bytes([0x00, 0x00, 0x64])  # Battery at 100%
    sample_manufacturer_data = bytes([
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # Bytes 0-7
        0x03,  # Byte 8: Fractional part (0x03 & 0x0F = 3, so 0.3°C)
        0x97,  # Byte 9: Whole part + sign (0x97 & 0x7F = 23, sign bit set = positive)
        0x2E,  # Byte 10: Humidity (0x2E & 0x7F = 46%)
        0x00   # Byte 11: Unused
    ])

    result = decoder.decode_ble_advertisement(sample_service_data, sample_manufacturer_data)

    print("Sample decode result:")
    print(f"  Battery: {result['battery']}%")
    print(f"  Temperature: {result['temperature']}°C")
    print(f"  Humidity: {result['humidity']}%")
    print("✅ Decoder test complete!\n")


async def main():
    """Main scanning loop."""
    # Your SwitchBot MAC address
    MAC_ADDRESS = os.getenv("SWITCHBOT_MAC", "")

    # Test decoder first
    test_with_sample_data()

    print("🚀 Starting SwitchBot BLE Scanner...")
    print(f"🎯 Target MAC: {MAC_ADDRESS}")
    print("📡 Scanning for BLE advertisements...")
    print("💡 Make sure your SwitchBot device is nearby and active!")
    print("🔍 Debug info will be shown if data can't be decoded")
    print("\nPress Ctrl+C to stop\n")

    scanner = SwitchBotBLEScanner(MAC_ADDRESS)

    # Modern bleak API - use detection_callback parameter
    try:
        async with BleakScanner(detection_callback=scanner.on_advertisement_received) as ble_scanner:
            # Run forever until interrupted
            while True:
                await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping scanner...")

    print("✅ Scanner stopped")

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())

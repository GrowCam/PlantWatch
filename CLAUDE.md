# PlantWatch

Self-hosted Raspberry Pi grow room monitor. Flask dashboard (`dashboard_app.py`) + Telegram bot (`bot_listener.py`) + BLE sensors + MQTT device control + timelapse camera.

## Hard Rules

**No local installs.** Never install services, systemd units, or packages on this machine. Everything runs on the Pi. Deploy with `./sync_pi.sh`.

**Zero personal data in committed files — including comments.** No usernames, hostnames, tokens, MAC addresses, grow names, or any identifiers. Use generic placeholders (`your-hostname`, `YOUR_MAC_ADDRESS`, etc.) everywhere: code, scripts, service files, cron files.

## Architecture

`dashboard_app.py` is intentionally monolithic — all routes, MQTT client, and automation controllers (heater/exhaust/light/humidity) as daemon threads. Don't split into blueprints.

`grow_data.json` and `sensor_data.db` live on the Pi only — not synced back to local.

Automation must degrade gracefully: if sensor data is missing or stale, use cached values; never crash.

## Common Tasks

**New Telegram command** (`bot_listener.py`): match `command.startswith("/...")`, call `_dashboard_action()` for device control, respond with `send_telegram()`.

**New dashboard page**: create `templates/page.html` extending `base.html` → add Flask route in `dashboard_app.py` → add strings to both `translations["en"]` and `translations["de"]` in `lang.py` → add nav link in `base.html`.

**New controlled device**: add MQTT topic to `.env` (placeholder in `.env.example`) → handle in `/api/action` in `dashboard_app.py` → add UI in template.

**New translation string**: add key to both `en` and `de` dicts in `lang.py`. Use `t("key")` in Python; pass via template context for JS.

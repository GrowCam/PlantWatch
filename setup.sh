#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PROJECT_NAME="GrowCam"
PYTHON_BIN="python3"
VENV_PATH="${SCRIPT_DIR}/.venv"
REQUIREMENTS_FILE="${SCRIPT_DIR}/requirements.txt"
ENV_FILE="${SCRIPT_DIR}/.env"
ENV_TEMPLATE="${SCRIPT_DIR}/.env.example"
RUN_USER="${SUDO_USER:-$(whoami)}"
RUN_GROUP="$RUN_USER"
DEFAULT_SUDO=$([[ $EUID -ne 0 ]] && echo "sudo" || echo "")

APT_PACKAGES=(
    python3
    python3-venv
    python3-pip
    python3-picamera2
    libcamera-tools
    v4l-utils
    bluez
    bluez-tools
    git
)

info() {
    echo "[INFO] $*"
}

warn() {
    echo "[WARN] $*" >&2
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        warn "Benötigter Befehl '$1' wurde nicht gefunden."
        return 1
    fi
    return 0
}

install_apt_packages() {
    if ! command -v apt-get >/dev/null 2>&1; then
        warn "apt-get wurde nicht gefunden. Überspringe Installation der Systempakete."
        warn "Bitte installiere die folgenden Pakete manuell: ${APT_PACKAGES[*]}"
        return
    fi

    local SUDO="$DEFAULT_SUDO"

    info "Aktualisiere Paketquellen..."
    $SUDO apt-get update -y

    info "Installiere benötigte Systempakete..."
    $SUDO apt-get install -y "${APT_PACKAGES[@]}"
}

create_directories() {
    mkdir -p "${SCRIPT_DIR}/images"
    mkdir -p "${SCRIPT_DIR}/timelapse"
}

create_venv() {
    if [[ ! -d "$VENV_PATH" ]]; then
        info "Erstelle virtuelles Python-Umfeld unter $VENV_PATH"
        "$PYTHON_BIN" -m venv --system-site-packages "$VENV_PATH"
    else
        info "Virtuelles Umfeld existiert bereits: $VENV_PATH"
    fi
}

install_python_requirements() {
    if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
        warn "Keine requirements.txt gefunden – überspringe Python-Installation."
        return
    fi

    local pip_bin="$VENV_PATH/bin/pip"
    if [[ ! -x "$pip_bin" ]]; then
        warn "pip wurde im virtuellen Umfeld nicht gefunden."
        return
    fi

    info "Aktualisiere pip..."
    "$pip_bin" install --upgrade pip

    info "Installiere Python-Abhängigkeiten aus requirements.txt"
    "$pip_bin" install --upgrade -r "$REQUIREMENTS_FILE"
}

prepare_env_file() {
    if [[ -f "$ENV_FILE" ]]; then
        info ".env existiert bereits – überspringe Kopie."
        return
    fi

    if [[ -f "$ENV_TEMPLATE" ]]; then
        info "Erzeuge .env aus Vorlage"
        cp "$ENV_TEMPLATE" "$ENV_FILE"
        warn "Bitte aktualisiere $ENV_FILE mit deinen API-Schlüsseln und Chat-IDs."
    else
        warn "Keine .env.example gefunden – bitte .env manuell erstellen."
    fi
}

install_systemd_services() {
    if ! command -v systemctl >/dev/null 2>&1; then
        warn "systemd nicht gefunden – überspringe Service-Installation."
        return
    fi

    local svc_dir="/etc/systemd/system"
    local python_bin="${VENV_PATH}/bin/python"

    info "Schreibe systemd-Services nach ${svc_dir}"
    cat <<EOF | ${DEFAULT_SUDO:-sudo} tee "${svc_dir}/growcam-dashboard.service" >/dev/null
[Unit]
Description=GrowCam Dashboard (Flask)
After=network.target

[Service]
Type=simple
User=${RUN_USER}
Group=${RUN_GROUP}
WorkingDirectory=${SCRIPT_DIR}
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=${ENV_FILE}
ExecStart=${python_bin} ${SCRIPT_DIR}/dashboard_app.py
StandardOutput=append:${SCRIPT_DIR}/dashboard.log
StandardError=append:${SCRIPT_DIR}/dashboard.log
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    cat <<EOF | ${DEFAULT_SUDO:-sudo} tee "${svc_dir}/growcam-bot.service" >/dev/null
[Unit]
Description=GrowCam Telegram Bot Listener
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
Group=${RUN_GROUP}
WorkingDirectory=${SCRIPT_DIR}
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=${ENV_FILE}
ExecStart=${python_bin} ${SCRIPT_DIR}/bot_listener.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    info "Aktiviere und starte Services..."
    ${DEFAULT_SUDO:-sudo} systemctl daemon-reload
    ${DEFAULT_SUDO:-sudo} systemctl enable --now growcam-dashboard.service growcam-bot.service
}

install_cron_jobs() {
    if ! command -v crontab >/dev/null 2>&1; then
        warn "crontab nicht gefunden – überspringe Cron-Installation."
        return
    fi

    local cron_tmp
    cron_tmp="$(mktemp)"
    cat <<EOF >"$cron_tmp"
# Timelapse-Foto alle 30 Minuten
*/30 * * * * ${VENV_PATH}/bin/python ${SCRIPT_DIR}/cam.py --timelapse >> ${SCRIPT_DIR}/cam_timelapse.log 2>&1

# Bewässerungs-Check einmal täglich (16:45)
45 16 * * * ${VENV_PATH}/bin/python ${SCRIPT_DIR}/check_watering.py >> ${SCRIPT_DIR}/check_watering.log 2>&1
EOF

    info "Installiere Cronjobs für Benutzer ${RUN_USER}"
    crontab -u "${RUN_USER}" "$cron_tmp"
    rm -f "$cron_tmp"
}

print_summary() {
    cat <<EOF

----------------------------------------
${PROJECT_NAME} Setup abgeschlossen.

Nächste Schritte:
  1. Passe die Datei .env mit deinen realen Werten an.
  2. Aktiviere das virtuelle Umfeld via: source "$VENV_PATH/bin/activate"
  3. Teste den Bot mit: python3 bot_listener.py (innerhalb des venv)
  4. Stelle sicher, dass die Kamera via libcamera funktioniert (z.B. libcamera-still).

Hinweise:
  - Für BLE-Funktionen muss Bluetooth aktiviert sein (sudo systemctl enable --now bluetooth).
  - systemd-Services und Cronjobs wurden eingerichtet (sofern verfügbar).
----------------------------------------
EOF
}

main() {
    info "Starte ${PROJECT_NAME} Setup"

    require_command "$PYTHON_BIN" || {
        warn "Python 3 wird benötigt. Bitte installiere es und führe das Skript erneut aus."
        exit 1
    }

    install_apt_packages
    create_directories
    create_venv
    install_python_requirements
    prepare_env_file
    install_systemd_services
    install_cron_jobs
    print_summary
}

main "$@"

#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PROJECT_NAME="PlantWatch"
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
        warn "Required command '$1' not found."
        return 1
    fi
    return 0
}

install_apt_packages() {
    if ! command -v apt-get >/dev/null 2>&1; then
        warn "apt-get not found. Skipping system package installation."
        warn "Please install the following packages manually: ${APT_PACKAGES[*]}"
        return
    fi

    local SUDO="$DEFAULT_SUDO"

    info "Updating package sources..."
    $SUDO apt-get update -y

    info "Installing required system packages..."
    $SUDO apt-get install -y "${APT_PACKAGES[@]}"
}

create_directories() {
    mkdir -p "${SCRIPT_DIR}/images"
    mkdir -p "${SCRIPT_DIR}/timelapse"
}

create_venv() {
    if [[ ! -d "$VENV_PATH" ]]; then
        info "Creating Python virtual environment at $VENV_PATH"
        "$PYTHON_BIN" -m venv --system-site-packages "$VENV_PATH"
    else
        info "Virtual environment already exists: $VENV_PATH"
    fi
}

install_python_requirements() {
    if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
        warn "requirements.txt not found — skipping Python package installation."
        return
    fi

    local pip_bin="$VENV_PATH/bin/pip"
    if [[ ! -x "$pip_bin" ]]; then
        warn "pip not found in virtual environment."
        return
    fi

    info "Upgrading pip..."
    "$pip_bin" install --upgrade pip

    info "Installing Python dependencies from requirements.txt"
    "$pip_bin" install --upgrade -r "$REQUIREMENTS_FILE"
}

prepare_env_file() {
    if [[ -f "$ENV_FILE" ]]; then
        info ".env already exists — skipping copy."
        return
    fi

    if [[ -f "$ENV_TEMPLATE" ]]; then
        info "Creating .env from template"
        cp "$ENV_TEMPLATE" "$ENV_FILE"
        warn "Please update $ENV_FILE with your API keys and chat IDs."
    else
        warn ".env.example not found — please create .env manually."
    fi
}

install_systemd_services() {
    if ! command -v systemctl >/dev/null 2>&1; then
        warn "systemd not found — skipping service installation."
        return
    fi

    local svc_dir="/etc/systemd/system"
    local python_bin="${VENV_PATH}/bin/python"

    info "Writing systemd services to ${svc_dir}"
    cat <<EOF | ${DEFAULT_SUDO:-sudo} tee "${svc_dir}/plantwatch-dashboard.service" >/dev/null
[Unit]
Description=PlantWatch Dashboard (Flask)
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

    cat <<EOF | ${DEFAULT_SUDO:-sudo} tee "${svc_dir}/plantwatch-bot.service" >/dev/null
[Unit]
Description=PlantWatch Telegram Bot Listener
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

    info "Enabling and starting services..."
    ${DEFAULT_SUDO:-sudo} systemctl daemon-reload
    ${DEFAULT_SUDO:-sudo} systemctl enable --now plantwatch-dashboard.service plantwatch-bot.service
}

install_cron_jobs() {
    if ! command -v crontab >/dev/null 2>&1; then
        warn "crontab not found — skipping cron installation."
        return
    fi

    local cron_tmp
    cron_tmp="$(mktemp)"
    cat <<EOF >"$cron_tmp"
# Timelapse capture every 30 minutes
*/30 * * * * ${VENV_PATH}/bin/python ${SCRIPT_DIR}/cam.py --timelapse >> ${SCRIPT_DIR}/cam_timelapse.log 2>&1

# Watering reminder check once daily at 16:45
45 16 * * * ${VENV_PATH}/bin/python ${SCRIPT_DIR}/check_watering.py >> ${SCRIPT_DIR}/check_watering.log 2>&1
EOF

    info "Installing cron jobs for user ${RUN_USER}"
    crontab -u "${RUN_USER}" "$cron_tmp"
    rm -f "$cron_tmp"
}

print_summary() {
    cat <<EOF

----------------------------------------
${PROJECT_NAME} setup complete.

Next steps:
  1. Edit .env with your real values.
  2. Activate the virtual environment: source "$VENV_PATH/bin/activate"
  3. Test the bot: python3 bot_listener.py (inside venv)
  4. Verify the camera works: libcamera-still -o test.jpg

Notes:
  - BLE features require Bluetooth: sudo systemctl enable --now bluetooth
  - systemd services and cron jobs have been installed (if available).
----------------------------------------
EOF
}

main() {
    info "Starting ${PROJECT_NAME} setup"

    require_command "$PYTHON_BIN" || {
        warn "Python 3 is required. Please install it and run this script again."
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

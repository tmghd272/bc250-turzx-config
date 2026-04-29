#!/usr/bin/env bash
set -e

COLOR="\e[36m"
RESET="\e[0m"

echo -e "${COLOR}== Turing Smart Screen Setup (CachyOS/Arch) ==${RESET}"

# ----------------------------
# 1. Prerequisites
# ----------------------------
echo -e "${COLOR}[1/7] Installing prerequisites...${RESET}"

sudo pacman -Sy --needed --noconfirm \
    git python python-pip python-virtualenv \
    base-devel

# ----------------------------
# 2. USB check
# ----------------------------
echo -e "${COLOR}[2/7] Checking USB device...${RESET}"
lsusb | grep -i qinheng || echo "⚠️ Device not detected yet (plug it in)"

# ----------------------------
# 3. Udev rules
# ----------------------------
echo -e "${COLOR}[3/7] Setting udev rule...${RESET}"

RULE_FILE="/etc/udev/rules.d/99-usbmonitor.rules"

if [ ! -f "$RULE_FILE" ]; then
    echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="5722", MODE="0666"' | sudo tee "$RULE_FILE" >/dev/null
fi

sudo udevadm control --reload-rules
sudo udevadm trigger

echo -e "${COLOR}Replug your USB screen now.${RESET}"

# ----------------------------
# 4. Clone main repo
# ----------------------------
echo -e "${COLOR}[4/7] Cloning main repo...${RESET}"

mkdir -p "$HOME/Apps"
cd "$HOME/Apps"

git config --global http.version HTTP/1.1

if [ ! -d "turing-smart-screen-python" ]; then
    git clone --depth 1 https://github.com/mathoudebine/turing-smart-screen-python.git
fi

cd turing-smart-screen-python

# ----------------------------
# 4.5 Apply BC-250 overlay (TMGHD272's overlay)
# ----------------------------
echo -e "${COLOR}[4.5/7] Applying BC-250 config overlay...${RESET}"

if [ ! -d "$HOME/Apps/bc250-turzx-config" ]; then
    git clone https://github.com/tmghd272/bc250-turzx-config.git "$HOME/Apps/bc250-turzx-config"
fi

echo -e "${COLOR}Copying overlay files...${RESET}"

cp -rf "$HOME/Apps/bc250-turzx-config/turzx-config/"* .

# ----------------------------
# 5. Python venv (Fish-safe)
# ----------------------------
echo -e "${COLOR}[5/7] Creating virtual environment...${RESET}"

python -m venv .venv

bash -c "source .venv/bin/activate && pip install -U pip && pip install -r requirements.txt"

# ----------------------------
# 6. Systemd service
# ----------------------------
echo -e "${COLOR}[6/7] Creating systemd user service...${RESET}"

mkdir -p "$HOME/.config/systemd/user"

cat > "$HOME/.config/systemd/user/turing.service" <<EOF
[Unit]
Description=Turing Smart Screen Startup
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=%h/Apps/turing-smart-screen-python
ExecStart=/bin/bash -c 'source %h/Apps/turing-smart-screen-python/.venv/bin/activate && python %h/Apps/turing-smart-screen-python/startup.py'
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable turing.service

# ----------------------------
# 7. Done
# ----------------------------
echo -e "${COLOR}[7/7] Done!${RESET}"

echo ""
echo -e "${COLOR}Manual test:${RESET}"
echo -e "${COLOR}cd ~/Apps/turing-smart-screen-python${RESET}"
echo -e "${COLOR}bash -c 'source .venv/bin/activate && python startup.py'${RESET}"
echo ""
echo -e "${COLOR}Start service:${RESET}"
echo -e "${COLOR}systemctl --user start turing.service${RESET}"
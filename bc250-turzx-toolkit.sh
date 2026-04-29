#!/usr/bin/env bash

WHITE="\e[38;2;255;255;255m"
CYAN="\e[38;2;0;255;255m"
PURPLE="\e[38;2;160;80;255m"
GREEN="\e[38;2;0;255;0m"
RED="\e[38;2;255;0;0m"
YELLOW="\e[38;2;255;255;0m"
BLUE="\e[38;2;0;0;255m"
RESET="\e[0m"

BASE_DIR="$(dirname "$0")"
APP_DIR="$HOME/Apps/turing-smart-screen-python"
BG_DIR="$APP_DIR/res/backgrounds"

STARTUP_URL="https://github.com/tmghd272/bc250-custom-overlays/releases/download/turing-smart-screen/startup.py"

run_misc_menu() {
  while true; do
    clear
    echo -e "${BLUE}==============================${RESET}"
    echo -e "${WHITE}      MISC / NCT Toolkit      ${RESET}"
    echo -e "${BLUE}==============================${RESET}"
    echo -e "${CYAN}1) Install NCT6687 DKMS driver${RESET}"
    echo -e "${GREEN}2) Enable NCT6687 at boot${RESET}"
    echo -e "${RED}3) Disable NCT6687 at boot${RESET}"
    echo -e "${GREEN}4) Enable NCT6687 now${RESET}"
    echo -e "${RED}5) Disable NCT6687 now${RESET}"
    echo -e "${YELLOW}6) Blacklist NCT6683${RESET}"
    echo -e "${RED}7) Remove blacklist${RESET}"
    echo -e "${CYAN}0) Back${RESET}"
    echo ""

    read -p "Select option: " opt

    case $opt in

      1)
        echo -e "${CYAN}[*] Installing NCT6687 DKMS driver...${RESET}"

        WORKDIR="/tmp/nct6687d"
        rm -rf "$WORKDIR"

        sudo pacman -Sy --needed --noconfirm git base-devel dkms linux-headers

        git clone https://github.com/Fred78290/nct6687d "$WORKDIR"
        cd "$WORKDIR"

        sudo mkdir -p /usr/src/nct6687d-1.0
        sudo cp -r . /usr/src/nct6687d-1.0/

        sudo dkms add nct6687d/1.0
        sudo dkms build nct6687d/1.0
        sudo dkms install nct6687d/1.0

        sudo modprobe nct6687 || echo -e "${CYAN}⚠️ Module load failed (check reboot)${RESET}"
        ;;

      2)
        echo -e "${CYAN}[*] Enabling NCT6687 at boot...${RESET}"
        echo "nct6687" | sudo tee /etc/modules-load.d/nct6687.conf >/dev/null
        echo "options nct6687 force=true" | sudo tee /etc/modprobe.d/nct6687.conf >/dev/null
        ;;

      3)
        echo -e "${CYAN}[*] Disabling NCT6687 at boot...${RESET}"
        sudo rm -f /etc/modules-load.d/nct6687.conf
        sudo rm -f /etc/modprobe.d/nct6687.conf
        ;;

      4)
        echo -e "${CYAN}[*] Loading NCT6687 now...${RESET}"
        sudo modprobe nct6687 force=true || echo -e "${CYAN}❌ Module not installed yet${RESET}"
        ;;

      5)
        echo -e "${CYAN}[*] Unloading NCT6687 now...${RESET}"
        sudo modprobe -r nct6687 || echo -e "${CYAN}⚠️ Module not loaded or busy${RESET}"
        ;;

      6)
        echo -e "${CYAN}[*] Blacklisting NCT6683...${RESET}"
        echo "blacklist nct6683" | sudo tee /etc/modprobe.d/blacklist-nct6683.conf >/dev/null
        ;;

      7)
        echo -e "${CYAN}[*] Removing blacklist...${RESET}"
        sudo rm -f /etc/modprobe.d/blacklist-nct6683.conf
        ;;

      0)
        break
        ;;

      *)
        echo -e "${CYAN}Invalid option${RESET}"
        ;;

    esac

    echo ""
    read -p "Press Enter to continue..."
  done
}

while true; do
clear
echo -e "${BLUE}============================================${RESET}"
echo -e "${YELLOW}   BC-250 3.5*INCH TURZX ULTIMATE TOOLKIT   ${RESET}"
echo -e "${BLUE}============================================${RESET}"
echo -e "${CYAN}1) Install Turzx (full setup) ARCH/CACHYOS${RESET}"
echo -e "${PURPLE}2) Restart turing service${RESET}"
echo -e "${GREEN}3) Start turing service${RESET}"
echo -e "${RED}4) Stop turing service${RESET}"
echo -e "${GREEN}5) Update startup.py (from release)${RESET}"
echo -e "${GREEN}6) Replace turzx background image (.png)${RESET}"
echo -e "${YELLOW}7) View Turing service logs (journalctl)${RESET}"
echo -e "${WHITE}8) Misc tools (NCT sensors)${RESET}"
echo -e "${CYAN}0) Exit${RESET}"
echo ""

read -p "Select option: " opt

case $opt in

1)
  echo -e "${CYAN}[*] Running install script...${RESET}"
  bash "$BASE_DIR/arch-turzx-setup.sh"
  ;;

2)
  echo -e "${CYAN}[*] Restarting service...${RESET}"
  systemctl --user restart turing.service
  ;;

3)
  echo -e "${CYAN}[*] Starting service...${RESET}"
  systemctl --user start turing.service
  ;;

4)
  echo -e "${CYAN}[*] Stopping service...${RESET}"
  systemctl --user stop turing.service
  ;;

5)
  echo -e "${CYAN}[*] Updating startup.py...${RESET}"

  if [ ! -d "$APP_DIR" ]; then
    echo -e "${CYAN}❌ App directory not found: $APP_DIR${RESET}"
  else
    curl -L "$STARTUP_URL" -o "$APP_DIR/startup.py"
    echo -e "${CYAN}✅ startup.py updated${RESET}"
  fi
  ;;

6)
  echo -e "${CYAN}[*] Replace background image${RESET}"
  read -p "Enter full path to your image: " IMG_PATH

  if [ ! -f "$IMG_PATH" ]; then
    echo -e "${CYAN}❌ File not found${RESET}"
  else
    cp "$IMG_PATH" "$BG_DIR/example_320x480.png"
    echo -e "${CYAN}✅ Background replaced${RESET}"
  fi
  ;;

7)
  echo -e "${CYAN}[*] Opening service logs (CTRL+C to exit)...${RESET}"
  journalctl --user -u turing.service -f
  ;;

8)
  run_misc_menu
  ;;

0)
  exit
  ;;

*)
  echo -e "${CYAN}Invalid option${RESET}"
  ;;

esac

echo ""
read -p "Press Enter to continue..."
done
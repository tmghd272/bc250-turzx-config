#!/usr/bin/env python3
import os
import time
import subprocess
import re
from datetime import datetime
from library.lcd.lcd_comm_rev_a import LcdCommRevA, Orientation
from library.log import logger
import psutil
import socket
import copy

# Set working directory to script's location
os.chdir(os.path.dirname(os.path.abspath(__file__)))

COM_PORT = "AUTO"
WIDTH, HEIGHT = 320, 480
REVISION = "A"

# =========================================================
# Hardware Stats Functions
# =========================================================

# Auto-detect card location once
drm_path = "/sys/class/drm"
if not os.path.exists(drm_path):
    logger.error(f"{drm_path} does not exist! Cannot detect GPU cards.")
    card = None
else:
    # find first card directory
    card = next((f"card{i}" for i in range(10) if os.path.exists(os.path.join(drm_path, f"card{i}", "device"))), None)
    if card is None:
        logger.error(f"No GPU card directories found under {drm_path}!")
    else:
        logger.info(f"BC-250 APU detected at {card}")

# ---------------- GPU Load (%) ----------------
def get_gpu_load():
    """
    Read GPU load (%) from patched or unpatched gpu_metrics.
    
    Handles:
      - Old Cyan Skillfish: 1-100 raw values
      - New Cyan Skillfish: 0-10000 raw values (decimal scaling)
      - Unpatched / placeholder: 65535 -> 0

    Returns integer (0-100) for Turzx compatibility.
    """
    try:
        with open(f"/sys/class/drm/{card}/device/gpu_metrics", "rb") as f:
            data = f.read(128)

        raw_load = int.from_bytes(data[28:30], byteorder="little")

        # Null / invalid
        if raw_load == 65535:
            return 0

        # Detect new patch: raw > 100 → scale down from 0-10000 to 0-100
        if raw_load > 100:
            load = raw_load / 100
        else:
            # old patch: use as-is
            load = raw_load

        # Cap at 100% just in case
        if load > 100:
            load = 100

        return int(load)

    except Exception as e:
        # fallback 0
        logger.warning(f"GPU load read error: {e}")
        return 0

# ---------------- GPU Clock (MHz), Temperature (°C), VRAM Usage (GB) ----------------
def get_gpu_stats():
    """Read GPU clock (MHz), temperature (°C), and VRAM usage (GB)."""
    clock = temp = 0
    used_gb = 0.0
    try:
        clock_path = f"/sys/class/drm/{card}/device/pp_dpm_sclk"
        if os.path.exists(clock_path):
            with open(clock_path) as f:
                for line in f:
                    if "*" in line:
                        parts = line.strip().split(":")[-1].strip().split("Mhz")[0]
                        clock = int(parts)
                        break

        temp_path = f"/sys/class/drm/{card}/device/hwmon"
        for entry in os.listdir(temp_path):
            sensor_path = os.path.join(temp_path, entry, "temp1_input")
            if os.path.exists(sensor_path):
                with open(sensor_path) as f:
                    temp = int(f.read()) / 1000
                    break

        try:
            vram_used = int(open(f"/sys/class/drm/{card}/device/mem_info_vram_used").read().strip())
            gtt_used  = int(open(f"/sys/class/drm/{card}/device/mem_info_gtt_used").read().strip())
            used_gb = round((vram_used + gtt_used) / (1024**3), 2)
        except Exception as e:
            logger.warning(f"VRAM sysfs parse error: {e}")
    except Exception as e:
        logger.warning(f"GPU stats error: {e}")
    return clock, temp, used_gb

# ---------------- CPU Frequency (MHz) ----------------
def get_cpu_freq():
    """Compute average CPU frequency across all cores."""
    try:
        freqs = []
        with open("/proc/cpuinfo") as f:
            for line in f:
                if "cpu MHz" in line:
                    freqs.append(float(line.strip().split(":")[1]))
        if freqs:
            return int(sum(freqs) / len(freqs))
        return 0
    except Exception:
        return 0

# ---------------- CPU Temperature (°C) ----------------
def get_cpu_temp_from_sensors():
    """Read CPU temperature from k10temp hwmon driver."""
    try:
        hwmon_path = "/sys/class/hwmon"
        for hw in os.listdir(hwmon_path):
            name_path = os.path.join(hwmon_path, hw, "name")
            if os.path.exists(name_path):
                with open(name_path) as f:
                    name = f.read().strip().lower()
                if "k10temp" in name:
                    temp_path = os.path.join(hwmon_path, hw, "temp1_input")
                    if os.path.exists(temp_path):
                        return int(open(temp_path).read().strip()) // 1000
    except Exception as e:
        logger.warning(f"CPU temp read error: {e}")
    return 0

# ---------------- CPU Load (%) ----------------
def get_cpu_load():
    """Compute CPU usage percentage from /proc/stat."""
    try:
        with open("/proc/stat") as f:
            cpu_line = f.readline()
        fields = [float(x) for x in cpu_line.strip().split()[1:]]
        idle_time = fields[3] + fields[4]
        total_time = sum(fields)
        time.sleep(0.1)
        with open("/proc/stat") as f:
            cpu_line2 = f.readline()
        fields2 = [float(x) for x in cpu_line2.strip().split()[1:]]
        idle_delta = (fields2[3] + fields2[4]) - idle_time
        total_delta = sum(fields2) - total_time
        if total_delta > 0:
            return int(round(100.0 * (1.0 - idle_delta / total_delta), 0))
    except Exception as e:
        logger.warning(f"CPU load error: {e}")
    return 0

# ---------------- RAM Usage (GB) ----------------
def get_ram_usage():
    """Return used and total RAM in GB."""
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
        mem_total = int([x for x in lines if "MemTotal" in x][0].split()[1]) / 1024 / 1024
        mem_free = int([x for x in lines if "MemAvailable" in x][0].split()[1]) / 1024 / 1024
        used = mem_total - mem_free
        return round(used, 1), round(mem_total, 1)
    except Exception as e:
        logger.warning(f"RAM usage error: {e}")
        return 0.0, 0.0

# ---------------- APU Power (W) ----------------
def get_power_usage():
    """Read APU package power in Watts from lm-sensors."""
    try:
        output = subprocess.check_output(["sensors"], text=True)
        for line in output.splitlines():
            if "PPT" in line or "Package Power" in line:
                parts = line.split()
                for i, val in enumerate(parts):
                    if val.endswith("W"):
                        try:
                            return float(parts[i - 1])
                        except (ValueError, IndexError):
                            continue
    except Exception as e:
        logger.warning(f"PPT reading error: {e}")
    return 0.0

# ---------------- APU Voltage (mV) ----------------
def get_voltage_mV():
    """Read APU core voltage in millivolts."""

    try:
        hwmon_path = "/sys/class/hwmon"
        for hw in os.listdir(hwmon_path):
            name_file = os.path.join(hwmon_path, hw, "name")
            if os.path.exists(name_file):
                with open(name_file) as f:
                    name = f.read().strip().lower()
                if "amdgpu" in name:
                    # Usually vddgfx (core voltage) is in in0_input
                    volt_path = os.path.join(hwmon_path, hw, "in0_input")
                    if os.path.exists(volt_path):
                        return int(open(volt_path).read().strip())
    except Exception as e:
        logger.warning(f"APU voltage read error: {e}")
    return None

# ---------------- System Fan Speed (RPM) ----------------
def get_fan_rpm():
    """Read system fan speed in RPM (BC‑250, nct* hwmon, fan2_input)."""
    try:
        hwmon_path = "/sys/class/hwmon"
        for hw in os.listdir(hwmon_path):
            name_file = os.path.join(hwmon_path, hw, "name")
            if os.path.exists(name_file):
                with open(name_file) as f:
                    if "nct" in f.read().strip().lower():
                        fan_path = os.path.join(hwmon_path, hw, "fan2_input")
                        if os.path.exists(fan_path):
                            return int(open(fan_path).read().strip())
    except Exception as e:
        logger.warning(f"Fan RPM read error: {e}")
    return None

# ---------------- System NVMe SSD Temperature (°C) ----------------
def get_nvme_temp():
    """Read internal M.2 NVMe SSD temperature."""
    try:
        hwmon_path = "/sys/class/hwmon"
        for hw in os.listdir(hwmon_path):
            name_path = os.path.join(hwmon_path, hw, "name")
            if os.path.exists(name_path):
                with open(name_path) as f:
                    name = f.read().strip().lower()
                if "nvme" in name:
                    temp_path = os.path.join(hwmon_path, hw, "temp1_input")
                    if os.path.exists(temp_path):
                        return int(open(temp_path).read().strip()) // 1000
    except Exception as e:
        logger.warning(f"NVMe temp read error: {e}")
    return 0

# =========================================================
# Disk Bandwidth Monitoring
# =========================================================
disk_prev = None
disk_prev_time = time.time()

# ---------------- Total Disk Read/Write (MB/s) ----------------
def get_total_disk_rw():
    """Return read/write speed in MB/s for all disks."""
    global disk_prev, disk_prev_time
    now_time = time.time()
    interval = now_time - disk_prev_time
    disk_prev_time = now_time

    total_read = total_write = 0
    if disk_prev is None:
        disk_prev = {}

    for dev in os.listdir("/sys/block/"):
        if dev.startswith(("loop", "ram")):
            continue
        stat_path = f"/sys/block/{dev}/stat"
        if not os.path.exists(stat_path):
            continue
        try:
            with open(stat_path) as f:
                fields = list(map(int, f.read().strip().split()))
            read_bytes = fields[2] * 512
            write_bytes = fields[6] * 512
        except Exception:
            continue

        prev = disk_prev.get(dev, (read_bytes, write_bytes))
        total_read += max(read_bytes - prev[0], 0)
        total_write += max(write_bytes - prev[1], 0)
        disk_prev[dev] = (read_bytes, write_bytes)

    if interval == 0:
        return 0.0, 0.0
    return total_read / interval / 1024 / 1024, total_write / interval / 1024 / 1024

# =========================================================
# Network Speed Monitoring
# =========================================================
net_prev = {}
prev_time = time.time()

# ---------------- Auto Detect Network Interface ----------------
def auto_detect_interface():
    """Return first active physical network interface."""
    virtual_prefixes = ("uap", "virbr", "tap", "docker", "veth")
    
    while True:
        counters = psutil.net_io_counters(pernic=True)
        for iface in counters.keys():
            if iface == "lo" or iface.startswith(virtual_prefixes):
                continue
            # Check if interface has a valid IP
            try:
                addrs = psutil.net_if_addrs().get(iface, [])
                for addr in addrs:
                    if addr.family == socket.AF_INET and not addr.address.startswith("169.254"):
                        return iface
            except Exception:
                continue
        logger.warning("No network with valid IP yet, retrying in 1s...")
        time.sleep(1)

# ---------------- Get Network Speed (Mbps) ----------------
def get_network_speed(interface):
    """Return network Rx/Tx speed in Mbps for given interface."""
    global net_prev, prev_time
    counters = psutil.net_io_counters(pernic=True)
    now = time.time()
    interval = now - prev_time
    prev_time = now

    # Initialize counters if missing
    if interface not in counters:
        net_prev[interface] = counters.get(interface, counters.get("lo"))
        return 0.0, 0.0
    if interface not in net_prev:
        net_prev[interface] = copy.deepcopy(counters[interface])
        return 0.0, 0.0

    rx_bytes = counters[interface].bytes_recv - net_prev[interface].bytes_recv
    tx_bytes = counters[interface].bytes_sent - net_prev[interface].bytes_sent

    net_prev[interface] = copy.deepcopy(counters[interface])

    rx_mbps = max(rx_bytes * 8 / 1024 / 1024 / interval, 0)
    tx_mbps = max(tx_bytes * 8 / 1024 / 1024 / interval, 0)
    return rx_mbps, tx_mbps

# =========================================================
# Main Display Loop
# =========================================================
if __name__ == "__main__":
    interface_name = auto_detect_interface()
    background_path = f"res/backgrounds/example_{WIDTH}x{HEIGHT}.png"

    while True:
        try:
            # --- Connect / Reconnect Turzx ---
            lcd_comm = LcdCommRevA(com_port=COM_PORT, display_width=WIDTH, display_height=HEIGHT)
            lcd_comm.Reset()  # Black screen / full reset
            lcd_comm.InitializeComm()
            lcd_comm.SetBrightness(level=20)
            lcd_comm.SetBackplateLedColor(led_color=(255, 255, 255))
            lcd_comm.SetOrientation(orientation=Orientation.PORTRAIT)
            lcd_comm.DisplayBitmap(background_path)

            # --- Main metrics loop ---
            while True:
                now = datetime.now().strftime("%m/%d/%Y   %I:%M %p")
                gpu_load = get_gpu_load()
                gpu_clock, gpu_temp, vram_used = get_gpu_stats()
                cpu_clock = get_cpu_freq()
                cpu_temp = get_cpu_temp_from_sensors()
                cpu_load = get_cpu_load()
                ram_used, ram_total = get_ram_usage()
                ppt_watts = get_power_usage()
                voltage_mV = get_voltage_mV()
                fan_rpm = get_fan_rpm()
                nvme_temp = get_nvme_temp()
                rx_speed, tx_speed = get_network_speed(interface_name)
                disk_read, disk_write = get_total_disk_rw()

                text = (
                    f"   {now}\n"
                    f"         AMD BC-250\n"
                    f"{'RDNA2:':<6}{int(gpu_load):>3}% {int(gpu_clock):>5} {'MHz':<4}{int(gpu_temp):>3} {'°C':<4}\n"
                    f"{'Zen2:':<6}{int(cpu_load):>3}% {int(cpu_clock):>5} {'MHz':<4}{int(cpu_temp):>3} {'°C':<2}\n\n"
                    f"         16GB GDDR6\n"
                    f"{'VRAM:':<7}{vram_used:>5.1f} {'GB':<4}\n"
                    f"{'RAM:':<7}{ram_used:>5.1f} {'GB':<4}\n\n"
                    f"          Metrics\n"
                    f"{'APU Power:':<14}{ppt_watts:>6} {'W':<4}\n"
                    f"{'APU mV:':<16}{voltage_mV:>4} {'mV':<4}\n"
                    f"{'APU Fan:':<16}{fan_rpm:>4} {'RPM':<4}\n"
                    f"{'NVMe Temp:':<16}{nvme_temp:>4} {'°C':<4}\n"
                    f"{'Disk Read:':<16}{disk_read:>5.1f} {'MB/s↓':<8}\n"
                    f"{'Disk Write:':<16}{disk_write:>5.1f} {'MB/s↑':<8}\n"
                    f"{'Net Mbps:':<13}{rx_speed:>4.1f} {'↓':<3}{tx_speed:>4.1f} {'↑':<2}"
                )

                lcd_comm.DisplayText(
                    text,
                    10,
                    10,
                    font="res/fonts/jetbrains-mono/JetBrainsMono-ExtraBold.ttf",
                    font_size=18,
                    font_color=(220, 220, 255),
                    background_image=background_path
                )
                time.sleep(0.5)

        except Exception as e:
            logger.warning(f"Turzx error detected, reconnecting: {e}")
            try:
                lcd_comm.Reset()
                lcd_comm = None
            except:
                pass
            time.sleep(1)  # wait 1s before trying to reconnect
import subprocess, time, xml.etree.ElementTree as ET
import requests, smtplib, ssl
from datetime import datetime
import json
import platform
import atexit
import os
import signal
import sys

# CONFIG
with open("config.json") as f:
    config = json.load(f)

SUBNET = config["subnet"]
TELEGRAM_TOKEN = config["telegram_token"]
TELEGRAM_CHAT_ID = config["telegram_chat_id"]
EMAIL_SENDER = config["email_sender"]
EMAIL_PASSWORD = config["email_password"]
EMAIL_RECEIVER = config["email_receiver"]
EXCLUDE_MACS = set(config["exclude_macs"])
EXCLUDE_IPS = set(config["exclude_ips"])
ALIASES = config["aliases"]

STATE_FILE = "device_states.json"

if len(sys.argv) > 1 and sys.argv[1] == "--reset-state":
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        print("Saved device state reset.")
    else:
        print("No saved state to reset.")
    sys.exit(0)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            raw = json.load(f)
            return {mac: tuple(val) for mac, val in raw.items()}
    return {}

def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump(device_states, f)

def save_and_exit(signum, frame):
    save_state()
    print("\nSaved state, exiting.")
    sys.exit(0)

signal.signal(signal.SIGINT, save_and_exit)
atexit.register(save_state)

device_states = load_state()

def confirm_offline(ip):
    param = "-n" if platform.system().lower() == "windows" else "-c"
    result = subprocess.run(["ping", param, "1", "-W", "1", ip], stdout=subprocess.DEVNULL)
    return result.returncode != 0  # True = really offline

def is_excluded(mac, ip):
    return mac.lower() in {m.lower() for m in EXCLUDE_MACS} or ip in EXCLUDE_IPS

def log(msg):
    timestamp = datetime.now().strftime("[%d-%m-%Y %H:%M:%S]")
    with open("network_alerts.log", "a") as f:
        f.write(f"{timestamp} {msg}\n")

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

def send_email(msg):
    body = f"Subject: Device Alert\n\n{msg}"
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, body)

def scan():
    output = subprocess.check_output(["sudo", "nmap", "-sn", "-oX", "-", SUBNET])
    root = ET.fromstring(output)
    devices = set()
    for host in root.findall("host"):
        ip_elem = host.find("address[@addrtype='ipv4']")
        ip = ip_elem.attrib["addr"] if ip_elem is not None else "Unknown"
        name_elem = host.find("hostnames/hostname")
        name_fallback = name_elem.attrib["name"] if name_elem is not None else "Unknown"
        mac_elem = host.find("address[@addrtype='mac']")
        mac = mac_elem.attrib["addr"] if mac_elem is not None else None

        if mac:
            name = ALIASES.get(mac.upper(), name_fallback)
            devices.add((mac, ip, name))
        else:
            log(f"No MAC: {ip} ({name_fallback})")
    return devices

while True:
    current_devices = scan()
    current_macs = {mac for mac, _, _ in current_devices}

    for mac, ip, name in current_devices:
        if is_excluded(mac, ip): continue

        prev_state = device_states.get(mac)
        if not prev_state or not prev_state[2]:
            now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            msg = f"{now} ONLINE: {ip} ({name}) - {mac}"
            print(msg)
            log(msg)
            send_telegram(msg)
            send_email(msg)

        device_states[mac] = (ip, name, True)

    for mac, (ip, name, is_online) in list(device_states.items()):
        if mac in current_macs or not is_online: continue
        if is_excluded(mac, ip): continue
        if not confirm_offline(ip): continue

        now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        msg = f"{now} OFFLINE: {ip} ({name}) - {mac}"
        print(msg)
        log(msg)
        send_telegram(msg)
        send_email(msg)
        device_states[mac] = (ip, name, False)

    time.sleep(30)
import cv2
import os
import time
import threading
import requests
from datetime import datetime
from ultralytics import YOLO
import numpy as np
import simpleaudio as sa

# === TELEGRAM SETTINGS ===
BOT_TOKEN = "7700209347:AAHmL1ofY99PaLXalUu7CaBhBkrW6PIEDag"
CHAT_ID = "7882685644"
ENABLE_TELEGRAM = False  # set to False if you don't wanna send messages
telegram_toggle_msg = ""
telegram_toggle_time = 0

def send_telegram_photo(photo_path, caption=""):
    if not ENABLE_TELEGRAM:
        print("[Telegram OFF] Skipped sending:", caption)
        return False

    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        with open(photo_path, "rb") as photo:
            files = {"photo": photo}
            data = {"chat_id": CHAT_ID, "caption": caption}
            r = requests.post(url, files=files, data=data)
            print("Telegram response:", r.status_code, r.text)
            return r.status_code == 200
    except Exception as e:
        print("Telegram Error:", e)
        return False

def save_and_send(filename, frame, msg):
    cv2.imwrite(filename, frame)
    send_telegram_photo(filename, msg)

last_beep_time = 0
beep_cooldown = 1.5  # seconds between beeps
ENABLE_BEEP = True
beep_toggle_msg = ""
beep_toggle_time = 0

def play_beep():
    if not ENABLE_BEEP:
        return
    try:
        sa.WaveObject.from_wave_file("beep.wav").play()
    except Exception as e:
        print("Beep error:", e)

# === SETUP ===
model = YOLO("yolov8n.pt").to('cuda')
TARGET_CLASSES = ["person", "car", "dog", "cat"]
CLASS_NAMES = model.names
TARGET_IDS = [i for i, name in CLASS_NAMES.items() if name in TARGET_CLASSES]

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FRAME_COUNT, 30)
tracked_ids = set()

prev_time = time.time()
fps = 0
brightness = 1.0
contrast = 1.0
last_adjust_msg = ""
last_adjust_time = 0
gamma = 1.0

last_detection_time = 0
detection_cooldown = 0.333  # 3 snapshots per second max
active_types = set()

def adjust_gamma(image, gamma=1.0):
    inv_gamma = 1.0 / gamma
    table = np.array([((i / 255.0) ** inv_gamma) * 255
                     for i in range(256)]).astype("uint8")
    return cv2.LUT(image, table)

# === MAIN LOOP ===
while True:
    ret, frame = cap.read()
    if not ret:
        break

    now = time.time()
    fps = 1 / (now - prev_time)
    prev_time = now

    # Brightness/Contrast
    adjusted = cv2.convertScaleAbs(frame, alpha=contrast, beta=(brightness - 1.0) * 255)
    adjusted = adjust_gamma(adjusted, gamma)

    # Detection
    results = model.track(source=adjusted, persist=True, classes=TARGET_IDS, conf=0.6, verbose=False)[0]
    detection_made = False

    for box in results.boxes:
        cls_id = int(box.cls[0])
        track_id = int(box.id[0]) if box.id is not None else None
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        width, height = x2 - x1, y2 - y1

        if width * height < 1000:
            continue

        if cls_id in TARGET_IDS:
            label = CLASS_NAMES[cls_id]
            cv2.rectangle(adjusted, (x1, y1), (x2, y2), (255, 0, 255), 2)
            id_text = f"{label} {int(track_id)}" if track_id else label
            cv2.putText(adjusted, id_text, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 2)

            if track_id and track_id not in tracked_ids:
                tracked_ids.add(track_id)
            detection_made = True

    # Overlay info
    cv2.putText(adjusted, f"FPS: {fps:.1f}", (adjusted.shape[1]-100, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    cv2.putText(adjusted, date_str, (10, adjusted.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    # Fast snapshot while detected
    types_detected = set(CLASS_NAMES[int(b.cls[0])] for b in results.boxes if int(b.cls[0]) in TARGET_IDS)
    if types_detected:
        now_time = time.time()
        if now_time - last_detection_time > detection_cooldown or types_detected != active_types:
            last_detection_time = now_time
            active_types = types_detected.copy()
            
            if time.time() - last_beep_time > beep_cooldown:
                play_beep()
                last_beep_time = time.time()

            os.makedirs("snapshots", exist_ok=True)
            filename = datetime.now().strftime("snapshots/snapshot_%Y%m%d_%H%M%S_%f.jpg")
            msg = "Detected: " + ", ".join(types_detected).title() + f" at {datetime.now().strftime('%d/%m/%Y %H:%M:%S.%f')[:-3]}"
            threading.Thread(target=save_and_send, args=(filename, adjusted.copy(), msg), daemon=True).start()
    else:
        active_types.clear()

    # Brightness msg
    if time.time() - last_adjust_time < 2:
        cv2.putText(adjusted, last_adjust_msg, (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    # Telegram toggle message
    if time.time() - telegram_toggle_time < 2:
        cv2.putText(adjusted, telegram_toggle_msg, (10, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    # Beep toggle message
    if time.time() - beep_toggle_time < 2:
        cv2.putText(adjusted, beep_toggle_msg, (10, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    cv2.imshow("Tracking Detection", adjusted)
    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'):
        break
    elif key == ord('i'):
        brightness = min(1.5, brightness + 0.1)
        last_adjust_msg = f"Brightness: {brightness:.1f}"
        last_adjust_time = time.time()
    elif key == ord('k'):
        brightness = max(0.5, brightness - 0.1)
        last_adjust_msg = f"Brightness: {brightness:.1f}"
        last_adjust_time = time.time()
    elif key == ord('u'):
        gamma = max(0.1, gamma - 0.1)
        last_adjust_msg = f"Gamma: {gamma:.1f}"
        last_adjust_time = time.time()
    elif key == ord('o'):
        gamma = min(3.0, gamma + 0.1)
        last_adjust_msg = f"Gamma: {gamma:.1f}"
        last_adjust_time = time.time()
    elif key == ord('t'):
        ENABLE_TELEGRAM = not ENABLE_TELEGRAM
        telegram_toggle_msg = f"Telegram: {'ON' if ENABLE_TELEGRAM else 'OFF'}"
        telegram_toggle_time = time.time()
    elif key == ord('b'):
        ENABLE_BEEP = not ENABLE_BEEP
        beep_toggle_msg = f"Beep: {'ON' if ENABLE_BEEP else 'OFF'}"
        beep_toggle_time = time.time()

cap.release()
cv2.destroyAllWindows()
import cv2
import os
import time
import threading
import requests
import numpy as np
from datetime import datetime
from flask import Flask, Response
from ultralytics import YOLO
import simpleaudio as sa
from flask import jsonify
from flask import render_template
from flask import send_from_directory

# === TELEGRAM SETTINGS ===
BOT_TOKEN = ""
CHAT_ID = ""
ENABLE_TELEGRAM = False
ENABLE_BEEP = False
telegram_toggle_msg = ""
beep_toggle_msg = ""
telegram_toggle_time = 0
beep_toggle_time = 0

# === APP SERVER ===
app = Flask(__name__)
output_frame = None
lock = threading.Lock()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    def generate():
        while True:
            with lock:
                if output_frame is None:
                    continue
                ret, buffer = cv2.imencode('.jpg', output_frame)
                if not ret:
                    continue
                frame = buffer.tobytes()
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

def start_flask():
    app.run(host='0.0.0.0', port=5000, threaded=True)

@app.route('/toggle/beep')
def toggle_beep():
    global ENABLE_BEEP
    ENABLE_BEEP = not ENABLE_BEEP
    return jsonify({
        "state": ENABLE_BEEP,
        "label": f"Beep: {'ON 🔊' if ENABLE_BEEP else 'OFF 🔇'}"
    })

@app.route('/toggle/telegram')
def toggle_telegram():
    global ENABLE_TELEGRAM
    ENABLE_TELEGRAM = not ENABLE_TELEGRAM
    return jsonify({
        "state": ENABLE_TELEGRAM,
        "label": f"Telegram: {'ON ✅' if ENABLE_TELEGRAM else 'OFF ❌'}"
    })

@app.route('/status')
def status():
    return jsonify({
        "beep": ENABLE_BEEP,
        "telegram": ENABLE_TELEGRAM
    })

@app.route('/set_brightness/<float:val>')
def set_brightness(val):
    global brightness
    brightness = max(0.5, min(1.5, val))
    return ('', 204)

@app.route('/set_contrast/<float:val>')
def set_contrast(val):
    global contrast
    contrast = max(0.5, min(2.0, val))
    return ('', 204)

@app.route('/snapshots')
def snapshots():
    files = sorted(os.listdir('snapshots'), reverse=True)
    files = [f for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    return render_template('snapshots.html', files=files)

@app.route('/snapshots/<filename>')
def snapshot_file(filename):
    return send_from_directory('snapshots', filename)

@app.route('/delete_snapshots', methods=['POST'])
def delete_snapshots():
    folder = 'snapshots'
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(f"Failed to delete {file_path}: {e}")
    return jsonify({"status": "deleted"})

@app.route('/toggle/night_vision')
def toggle_night_vision():
    global night_vision
    night_vision = not night_vision
    return jsonify({
        "state": night_vision,
        "label": f"Night Vision: {'ON 🌙' if night_vision else 'OFF ☀️'}"
    })

threading.Thread(target=start_flask, daemon=True).start()

# === SETUP ===
model = YOLO("yolov8n.pt").to('cuda')
model.predict(source=np.zeros((640, 480, 3), dtype=np.uint8), verbose=False)  # Warm up GPU
TARGET_CLASSES = ["person", "car", "dog", "cat"]
CLASS_NAMES = model.names
TARGET_IDS = [i for i, name in CLASS_NAMES.items() if name in TARGET_CLASSES]

cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)
tracked_ids = set()

prev_time = time.time()
fps = 0
brightness = 1.0
contrast = 1.0
gamma = 1.0
last_adjust_msg = ""
last_adjust_time = 0

last_detection_time = 0
last_beep_time = 0
detection_cooldown = 0.333
beep_cooldown = 1.5
night_vision = False
active_types = set()

snapshot_queue = []

DETECT_EVERY = 3
frame_count = 0
last_results = None


def night_vision_effect(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    colored = cv2.applyColorMap(gray, cv2.COLORMAP_SUMMER)
    return cv2.addWeighted(colored, 0.7, frame, 0.3, 0)

def play_beep():
    if not ENABLE_BEEP:
        return
    try:
        sa.WaveObject.from_wave_file("beep.wav").play()
    except:
        pass

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

def save_and_send_thread():
    while True:
        if snapshot_queue:
            filename, frame, msg = snapshot_queue.pop(0)
            cv2.imwrite(filename, frame)
            send_telegram_photo(filename, msg)
        time.sleep(0.1)

def adjust_gamma(image, gamma=1.0):
    inv_gamma = 1.0 / gamma
    table = np.array([(i / 255.0) ** inv_gamma * 255 for i in range(256)]).astype("uint8")
    return cv2.LUT(image, table)

threading.Thread(target=save_and_send_thread, daemon=True).start()

# === MAIN LOOP ===
while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1
    now = time.time()
    fps = 1 / (now - prev_time)
    prev_time = now

    if night_vision:
        adjusted = night_vision_effect(frame)
    else:
        adjusted = cv2.convertScaleAbs(frame, alpha=contrast, beta=(brightness - 1.0) * 255)
        adjusted = adjust_gamma(adjusted, gamma)

    if frame_count % DETECT_EVERY == 0:
        small_frame = cv2.resize(adjusted, (320, 240))
        last_results = model.track(source=small_frame, persist=True, classes=TARGET_IDS, conf=0.8, verbose=False)[0]

    detection_made = False
    if last_results:
        for box in last_results.boxes:
            cls_id = int(box.cls[0])
            track_id = int(box.id[0]) if box.id is not None else None
            x1, y1, x2, y2 = map(int, box.xyxy[0] * 2)  # scale back from 320x240 to 640x480
            if (x2 - x1) * (y2 - y1) < 1000:
                continue
            if cls_id in TARGET_IDS:
                label = CLASS_NAMES[cls_id]
                cv2.rectangle(adjusted, (x1, y1), (x2, y2), (255, 0, 255), 2)
                text = f"{label} {track_id}" if track_id else label
                cv2.putText(adjusted, text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 2)
                if track_id and track_id not in tracked_ids:
                    tracked_ids.add(track_id)
                detection_made = True

    cv2.putText(adjusted, f"FPS: {fps:.1f}", (adjusted.shape[1]-100, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    cv2.putText(adjusted, date_str, (10, adjusted.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    types_detected = set(CLASS_NAMES[int(b.cls[0])] for b in last_results.boxes if int(b.cls[0]) in TARGET_IDS) if last_results else set()
    if types_detected:
        now_time = time.time()
        if now_time - last_detection_time > detection_cooldown or types_detected != active_types:
            last_detection_time = now_time
            active_types = types_detected.copy()

            if now_time - last_beep_time > beep_cooldown:
                play_beep()
                last_beep_time = now_time

            os.makedirs("snapshots", exist_ok=True)
            filename = datetime.now().strftime("snapshots/snapshot_%Y%m%d_%H%M%S_%f.jpg")
            msg = "Detected: " + ", ".join(types_detected).title() + f" at {datetime.now().strftime('%d/%m/%Y %H:%M:%S.%f')[:-3]}"
            snapshot_queue.append((filename, adjusted.copy(), msg))
    else:
        active_types.clear()

    if time.time() - last_adjust_time < 2:
        cv2.putText(adjusted, last_adjust_msg, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    if time.time() - telegram_toggle_time < 2:
        cv2.putText(adjusted, telegram_toggle_msg, (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if ENABLE_TELEGRAM else (0, 0, 255), 2)
    if time.time() - beep_toggle_time < 2:
        cv2.putText(adjusted, beep_toggle_msg, (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if ENABLE_BEEP else (0, 0, 255), 2)

    with lock:
        output_frame = adjusted.copy()

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
    elif key == ord('n'):
        night_vision = not night_vision
        last_adjust_msg = f"Night Vision: {'ON' if night_vision else 'OFF'}"
        last_adjust_time = time.time()

cap.release()
cv2.destroyAllWindows()
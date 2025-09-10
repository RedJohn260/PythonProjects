import cv2
import time
import os
from ultralytics import YOLO
import threading
from datetime import datetime
import logging
import simpleaudio as sa  # Assuming you already switched to simpleaudio

# Silence ultralytics logs
logging.getLogger("ultralytics").setLevel(logging.ERROR)

model = YOLO("yolov8n.pt").to('cuda')
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FRAME_COUNT, 30)

mode = 0
show_mask = False

log_file = open("detection_log.txt", "a")

class_names = {0: "Person", 2: "Car", 15: "Cat", 16: "Dog"}
colors = {
    0: (0, 255, 0),
    2: (255, 0, 0),
    15: (255, 100, 100),
    16: (255, 255, 0)
}

if not os.path.exists("snapshots"):
    os.makedirs("snapshots")

last_beep_time = 0
beep_cooldown = 2
prev_time = time.time()

sensitivity = 50
sensitivity_msg = ""
sensitivity_msg_time = 0

brightness_factor = 1.0
brightness_msg = ""
brightness_msg_time = 0

def update_bg_subtractor(thresh):
    global bg_subtractor, sensitivity, sensitivity_msg, sensitivity_msg_time
    sensitivity = thresh
    bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=sensitivity)
    sensitivity_msg = f"MaskSensitivity: {sensitivity}"
    sensitivity_msg_time = time.time()

bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=sensitivity)

def play_beep():
    def _play():
        try:
            wave_obj = sa.WaveObject.from_wave_file("beep.wav")
            wave_obj.play()
        except Exception as e:
            print(f"Sound error: {e}")
    threading.Thread(target=_play, daemon=True).start()

def apply_night_vision_green(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    enhanced = cv2.equalizeHist(gray)
    return cv2.merge([enhanced // 2, enhanced, enhanced // 2])

def apply_thermal_filter(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    normalized = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    colored = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
    return colored

def adjust_brightness(frame, factor):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    v = cv2.multiply(v, factor)
    v = cv2.min(v, 255).astype('uint8')
    final_hsv = cv2.merge((h, s, v))
    return cv2.cvtColor(final_hsv, cv2.COLOR_HSV2BGR)

def detect_objects(frame):
    results = model(frame, classes=list(class_names.keys()))
    counts = {"Person":0,"Car":0,"Cat":0,"Dog":0}
    detected = False

    for r in results:
        for box in r.boxes:
            cls = int(box.cls[0])
            label = class_names.get(cls, "Unknown")
            color = colors.get(cls, (255,255,255))
            x1,y1,x2,y2 = map(int, box.xyxy[0])
            cv2.rectangle(frame, (x1,y1), (x2,y2), color, 2)
            cv2.putText(frame, label, (x1,y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            counts[label] += 1
            detected = True
    return frame, counts, detected

def draw_counts(frame, counts):
    y_offset = 30
    for label, count in counts.items():
        if count > 0:
            cv2.putText(frame, f"{label}: {count}", (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
            y_offset += 25
    return frame

def log_counts(counts):
    if any(counts.values()):
        now = datetime.now().strftime("[%d/%m/%Y %H:%M:%S]")
        line = f"{now} " + " | ".join([f"{label}: {counts[label]}" for label in counts]) + "\n"
        log_file.write(line)
        log_file.flush()

def save_snapshot(frame):
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    # Copy frame to not alter original
    snapshot = frame.copy()
    # Put timestamp text bottom-left
    cv2.putText(snapshot, timestamp, (10, snapshot.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    # Save with timestamp in filename as before
    filename = datetime.now().strftime("snapshots/detection_%d-%m-%Y_%H-%M-%S.jpg")
    cv2.imwrite(filename, snapshot)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    adjusted_frame = adjust_brightness(frame, brightness_factor)

    fg_mask = bg_subtractor.apply(adjusted_frame)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
    fg = cv2.bitwise_and(adjusted_frame, adjusted_frame, mask=fg_mask)

    if mode == 1:
        display_frame = apply_night_vision_green(adjusted_frame)
    elif mode == 2:
        display_frame = apply_thermal_filter(adjusted_frame)
    else:
        display_frame = adjusted_frame.copy()

    detected_frame, counts, detected = detect_objects(fg)

    curr_time_beep = time.time()
    if detected and (curr_time_beep - last_beep_time) > beep_cooldown:
        play_beep()
        last_beep_time = curr_time_beep
        save_snapshot(display_frame)

    display_frame = draw_counts(display_frame, counts)
    log_counts(counts)

    curr_time = time.time()
    fps = 1 / (curr_time - prev_time)
    prev_time = curr_time

    # Move FPS to top right
    fps_text = f"FPS: {int(fps)}"
    (text_w, _), _ = cv2.getTextSize(fps_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    cv2.putText(display_frame, fps_text,
                (display_frame.shape[1] - text_w - 10, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    # Add datetime bottom left
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    cv2.putText(display_frame, now,
                (10, display_frame.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    if sensitivity_msg and (time.time() - sensitivity_msg_time) < 2:
        cv2.putText(display_frame, sensitivity_msg, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    if brightness_msg and (time.time() - brightness_msg_time) < 2:
        cv2.putText(display_frame, brightness_msg, (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    cv2.imshow("YOLOv8 Human Detection Lite", display_frame)

    if show_mask:
        cv2.imshow("Foreground Mask Lite", fg_mask)
    else:
        try:
            cv2.destroyWindow("Foreground Mask Lite")
        except cv2.error:
            pass

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('n'):
        mode = (mode + 1) % 3
    elif key == ord('m'):
        show_mask = not show_mask
    elif key == ord('+') or key == ord('='):
        if sensitivity < 150:
            update_bg_subtractor(sensitivity + 5)
    elif key == ord('-'):
        if sensitivity > 5:
            update_bg_subtractor(sensitivity - 5)
    elif key == ord('i'):
        brightness_factor = min(brightness_factor + 0.1, 6.0)
        brightness_msg = f"Brightness: {brightness_factor:.1f}"
        brightness_msg_time = time.time()
    elif key == ord('k'):
        brightness_factor = max(brightness_factor - 0.1, 0.1)
        brightness_msg = f"Brightness: {brightness_factor:.1f}"
        brightness_msg_time = time.time()

cap.release()
cv2.destroyAllWindows()
log_file.close()
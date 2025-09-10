import cv2
import time
import os
from ultralytics import YOLO
import threading
from datetime import datetime
import logging
import simpleaudio as sa
import queue

# Silence verbose ultralytics logs
logging.getLogger("ultralytics").setLevel(logging.ERROR)

# Class to handle video capture in a separate thread (non-blocking)
class VideoStream:
    def __init__(self, src=0):
        self.cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)  # Open camera with DirectShow backend
        self.ret, self.frame = self.cap.read()  # Initial read
        self.stopped = False
        self.lock = threading.Lock()  # Lock for thread-safe frame access
        threading.Thread(target=self.update, daemon=True).start()  # Start update thread

    def update(self):
        # Continuously capture frames until stopped
        while not self.stopped:
            ret, frame = self.cap.read()
            with self.lock:
                self.ret = ret
                self.frame = frame

    def read(self):
        # Safely return the latest frame
        with self.lock:
            return self.ret, self.frame.copy() if self.ret else None

    def release(self):
        # Signal stop and release camera resource
        self.stopped = True
        self.cap.release()

# Load YOLOv8 model on CUDA with half precision for speed
model = YOLO("yolov8n.pt").to('cuda').half()

# Initialize threaded video capture
stream = VideoStream(0)
stream.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)  # Set capture width
stream.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)  # Set capture height
stream.cap.set(cv2.CAP_PROP_FRAME_COUNT, 30) # Set framerate cap

# Variables for app state and UI
mode = 0  # Vision mode: 0=normal, 1=night green, 2=thermal color, 3=thermal BW
show_mask = False  # Toggle foreground mask display
frame_skip = 2  # Frames to skip for detection
frame_skip_enabled = False
fastmode_msg = ""  # UI message for fast mode toggle
fastmode_msg_time = 0
frame_counter = 0
show_help = False  # Toggle help overlay

log_file = open("detection_log.txt", "a")  # Log file for detection counts

# Object class names and their display colors (BGR)
class_names = {0: "Person", 2: "Car", 15: "Cat", 16: "Dog"}
colors = {
    0: (0, 255, 0),       # Green for Person
    2: (255, 0, 0),       # Blue for Car
    15: (255, 100, 100),  # Light red for Cat
    16: (255, 255, 0)     # Cyan for Dog
}

# Create directory for snapshots if missing
if not os.path.exists("snapshots"):
    os.makedirs("snapshots")

# Timing for beep sound cooldown and FPS calculation
last_beep_time = 0
beep_cooldown = 2
prev_time = time.time()

# Background subtractor sensitivity and messages
sensitivity = 50
sensitivity_msg = ""
sensitivity_msg_time = 0

# Brightness adjustment factor and messages
brightness_factor = 1.0
brightness_msg = ""
brightness_msg_time = 0

# Function to update the background subtractor with new sensitivity threshold
def update_bg_subtractor(thresh):
    global bg_subtractor, sensitivity, sensitivity_msg, sensitivity_msg_time
    sensitivity = thresh
    bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=sensitivity)
    sensitivity_msg = f"MaskSensitivity: {sensitivity}"
    sensitivity_msg_time = time.time()

# Initialize background subtractor
bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=sensitivity)

# Play beep sound in a separate thread to avoid blocking
def play_beep():
    def _play():
        try:
            wave_obj = sa.WaveObject.from_wave_file("beep.wav")
            wave_obj.play()
        except Exception as e:
            print(f"Sound error: {e}")
    threading.Thread(target=_play, daemon=True).start()

# Apply night vision green filter
def apply_night_vision_green(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    enhanced = cv2.equalizeHist(gray)  # Enhance contrast
    # Merge channels to give green tint
    return cv2.merge([enhanced // 2, enhanced, enhanced // 2])

# Apply thermal color filter
def apply_thermal_filter(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    normalized = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    colored = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)  # Thermal colormap
    return colored

# Apply thermal black & white filter (hot areas glow white)
def apply_thermal_bw(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    normalized = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    # COLORMAP_BONE: light areas = hot (glow white)
    return cv2.applyColorMap(normalized, cv2.COLORMAP_BONE)
    #return cv2.applyColorMap(normalized, cv2.COLORMAP_HOT)

# Adjust brightness by modifying the V channel in HSV color space
def adjust_brightness(frame, factor):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    v = cv2.multiply(v, factor)
    v = cv2.min(v, 255).astype('uint8')
    final_hsv = cv2.merge((h, s, v))
    return cv2.cvtColor(final_hsv, cv2.COLOR_HSV2BGR)

# Detect objects in the frame using YOLO model
def detect_objects(frame):
    results = model(frame, classes=list(class_names.keys()))  # Run detection on specified classes
    counts = {"Person":0,"Car":0,"Cat":0,"Dog":0}
    detected = False

    for r in results:
        for box in r.boxes:
            cls = int(box.cls[0])  # Class id
            conf = float(box.conf[0]) * 100  # Confidence %
            label_text = f"{class_names.get(cls, 'Unknown')} ({conf:.0f}%)"

            # Color gradient from red (low conf) to green (high conf)
            green = int(min(max(conf, 0), 100) * 2.55)
            red = 255 - green
            color = (0, green, red)  # BGR format

            x1,y1,x2,y2 = map(int, box.xyxy[0])
            # Draw bounding box
            cv2.rectangle(frame, (x1,y1), (x2,y2), color, 2)
            # Draw label above box
            cv2.putText(frame, label_text, (x1,y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            counts[class_names.get(cls, 'Unknown')] += 1
            detected = True

    return frame, counts, detected

# Draw object counts on the frame
def draw_counts(frame, counts):
    y_offset = 30
    for label, count in counts.items():
        if count > 0:
            cv2.putText(frame, f"{label}: {count}", (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
            y_offset += 25
    return frame

# Log counts to file with timestamp if any object detected
def log_counts(counts):
    if any(counts.values()):
        now = datetime.now().strftime("[%d/%m/%Y %H:%M:%S]")
        line = f"{now} " + " | ".join([f"{label}: {counts[label]}" for label in counts]) + "\n"
        log_file.write(line)
        log_file.flush()

# Save snapshot of current frame with timestamp text
def save_snapshot(frame):
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    snapshot = frame.copy()
    cv2.putText(snapshot, timestamp, (10, snapshot.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    filename = datetime.now().strftime("snapshots/detection_%d-%m-%Y_%H-%M-%S.jpg")
    cv2.imwrite(filename, snapshot)

# Queue to hold frames for detection, max size 1 to avoid backlog
detect_queue = queue.Queue(maxsize=1)
results_lock = threading.Lock()
latest_result = (None, {"Person":0,"Car":0,"Cat":0,"Dog":0}, False)

# Background thread running detection on frames from queue
def detection_worker():
    global latest_result
    while True:
        frame = detect_queue.get()
        if frame is None:  # Exit signal
            break
        detected_frame, counts, detected = detect_objects(frame)
        with results_lock:
            latest_result = (detected_frame, counts, detected)
        detect_queue.task_done()

# Start detection thread
threading.Thread(target=detection_worker, daemon=True).start()

# Main loop
while True:
    ret, frame = stream.read()
    if not ret:
        break

    # Adjust brightness
    adjusted_frame = adjust_brightness(frame, brightness_factor)

    # Apply background subtraction to extract moving objects
    fg_mask = bg_subtractor.apply(adjusted_frame)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)  # Clean mask
    fg = cv2.bitwise_and(adjusted_frame, adjusted_frame, mask=fg_mask)  # Mask applied frame

    # Apply vision mode filters
    if mode == 1:
        display_frame = apply_night_vision_green(adjusted_frame)
    elif mode == 2:
        display_frame = apply_thermal_filter(adjusted_frame)
    elif mode == 3:
        display_frame = apply_thermal_bw(adjusted_frame)
    else:
        display_frame = adjusted_frame.copy()

    frame_counter += 1
    # Submit frame to detection queue if fastmode allows
    if not frame_skip_enabled or (frame_counter % frame_skip == 0):
        # If queue full, drop oldest to avoid lag
        if detect_queue.full():
            try:
                detect_queue.get_nowait()
                detect_queue.task_done()
            except queue.Empty:
                pass
        detect_queue.put(fg)

    # Get latest detection results thread-safely
    with results_lock:
        detected_frame, counts, detected = latest_result

    # Play beep and save snapshot if new detection after cooldown
    if detected and (time.time() - last_beep_time) > beep_cooldown:
        play_beep()
        last_beep_time = time.time()
        save_snapshot(display_frame)

    # Overlay counts on the display frame
    display_frame = draw_counts(display_frame, counts)
    log_counts(counts)

    # Calculate FPS and show on top right
    curr_time = time.time()
    fps = 1 / (curr_time - prev_time)
    prev_time = curr_time
    fps_text = f"FPS: {int(fps)}"
    (text_w, _), _ = cv2.getTextSize(fps_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    cv2.putText(display_frame, fps_text,
                (display_frame.shape[1] - text_w - 10, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    # Show current date/time bottom left
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    cv2.putText(display_frame, now,
                (10, display_frame.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    # Show sensitivity, brightness, fastmode messages for 2 seconds
    if sensitivity_msg and (time.time() - sensitivity_msg_time) < 2:
        cv2.putText(display_frame, sensitivity_msg, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    if brightness_msg and (time.time() - brightness_msg_time) < 2:
        cv2.putText(display_frame, brightness_msg, (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    if fastmode_msg and (time.time() - fastmode_msg_time) < 2:
        cv2.putText(display_frame, fastmode_msg, (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    # Show help overlay if enabled
    if show_help:
        help_text = """
        [H] Toggle Help
        [Q] Quit
        [N] Toggle Vision Mode
        [M] Toggle Foreground Mask
        [+] / [-] Adjust Mask Sensitivity
        [I] / [K] Adjust Brightness
        [F] Toggle FastMode
        """
        for idx, line in enumerate(help_text.strip().splitlines()):
            cv2.putText(display_frame, line.strip(), (10, 150 + idx * 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

    # Show main window with detections
    cv2.imshow("YOLOv8 Human Detection", display_frame)

    # Show or hide foreground mask window
    if show_mask:
        cv2.imshow("Foreground Mask", fg_mask)
    else:
        try:
            cv2.destroyWindow("Foreground Mask")
        except cv2.error:
            pass

    # Key input handling
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):  # Quit app
        break
    elif key == ord('n'):  # Cycle vision modes
        mode = (mode + 1) % 4
    elif key == ord('m'):  # Toggle foreground mask view
        show_mask = not show_mask
    elif key == ord('+') or key == ord('='):  # Increase mask sensitivity
        if sensitivity < 150:
            update_bg_subtractor(sensitivity + 5)
    elif key == ord('-'):  # Decrease mask sensitivity
        if sensitivity > 5:
            update_bg_subtractor(sensitivity - 5)
    elif key == ord('i'):  # Increase brightness factor (max 5.0)
        brightness_factor = min(brightness_factor + 0.1, 5.0)
        brightness_msg = f"Brightness: {brightness_factor:.1f}"
        brightness_msg_time = time.time()
    elif key == ord('k'):  # Decrease brightness factor (min 0.1)
        brightness_factor = max(brightness_factor - 0.1, 0.1)
        brightness_msg = f"Brightness: {brightness_factor:.1f}"
        brightness_msg_time = time.time()
    elif key == ord('f'):  # Toggle fast mode (frame skipping)
        frame_skip_enabled = not frame_skip_enabled
        fastmode_msg = f"FastMode: {'ON' if frame_skip_enabled else 'OFF'}"
        fastmode_msg_time = time.time()
    elif key == ord('h'):  # Toggle help overlay
        show_help = not show_help

# Cleanup on exit
stream.release()
cv2.destroyAllWindows()
log_file.close()
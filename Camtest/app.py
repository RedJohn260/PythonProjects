from flask import Flask, render_template, Response, request
import cv2
import threading

app = Flask(__name__)
cam = cv2.VideoCapture(0)
brightness = 1.0
running = True

def cleanup():
    print("Cleaning up...")
    cam.release()
    cv2.destroyAllWindows()

def gen_frames():
    global brightness
    while running:
        success, frame = cam.read()
        if not success:
            break
        frame = cv2.convertScaleAbs(frame, alpha=brightness, beta=0)
        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video')
def video():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/brightness', methods=['POST'])
def set_brightness():
    global brightness
    brightness = float(request.form['value'])
    return ('', 204)

@app.route('/screenshot')
def screenshot():
    ret, frame = cam.read()
    if ret:
        cv2.imwrite('screenshot.jpg', frame)
        return 'Saved as screenshot.jpg'
    return 'Failed', 500

def flask_thread():
    app.run(host='0.0.0.0', port=5000)

if __name__ == '__main__':
    threading.Thread(target=flask_thread, daemon=True).start()

    # OpenCV preview + q to quit
    try:
        while True:
            ret, frame = cam.read()
            if not ret:
                break
            frame = cv2.convertScaleAbs(frame, alpha=brightness, beta=0)
            cv2.imshow("Local Cam (Press q to quit)", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    except KeyboardInterrupt:
        pass
    finally:
        running = False
        cleanup()

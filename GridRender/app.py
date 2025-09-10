from flask import Flask, render_template, request, redirect, url_for
import json, os

app = Flask(__name__)
CONFIG_FILE = "config.json"

# Load config
def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"slots": 2, "urls": ["http://192.168.8.118:5001"] * 2}
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

# Save config
def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

config = load_config()

@app.route('/')
def index():
    return render_template('index.html', slots=config["slots"], urls=config["urls"])

@app.route('/config', methods=['GET', 'POST'])
def config_route():
    global config
    if request.method == 'POST':
        slots = int(request.form['slots'])
        urls = [request.form.get(f"url{i}", "http://192.168.8.118:5001") for i in range(slots)]
        config = {"slots": slots, "urls": urls}
        save_config(config)
        return redirect(url_for('index'))
    return render_template('config.html', slots=config["slots"], urls=config["urls"])

app.run(debug=True, port=5006, host='192.168.8.118')

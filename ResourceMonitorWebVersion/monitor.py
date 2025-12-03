import psutil
import time
import threading
from flask import Flask, render_template, jsonify

app = Flask(__name__)

# Disk/Net history
prev_disk_io = psutil.disk_io_counters(perdisk=True)
prev_net = psutil.net_io_counters()

lock = threading.Lock()

color_map = {
    'bright_cyan': 'cyan',
    'bright_green': 'lime',
    'bright_yellow': 'yellow',
    'bright_red': 'red'
}

def make_color(perc):
    if perc < 25: return "bright_cyan"
    elif perc < 50: return "bright_green"
    elif perc < 75: return "bright_yellow"
    else: return "bright_red"

def make_bar(perc, max_width, format='rich'):
    color = make_color(perc)
    if format == 'rich':
        filled = int(max_width * perc / 100)
        empty = max_width - filled
        return f"[{color}]{'░'*filled}[/][white]{'░'*empty}[/] {perc:>3.0f}%"
    elif format == 'html':
        color_css = color_map[color]
        # Fixed width for web
        return f'<div style="background-color: #333; width: 300px; height: 20px; display: inline-block;"><div style="background-color: {color_css}; width: {perc}%; height: 100%;"></div></div> {perc:.0f}%'

def get_cpu_power():
    # Just estimate: TDP × CPU load %
    tdp = 100.0  # Intel Celeron E1400 ≈ 65W TDP
    cpu_pct = psutil.cpu_percent(interval=None)
    est_w = round(tdp * (cpu_pct / 100.0), 2)
    return est_w, True

def get_system_power():
    # No direct sensors on this CPU
    return None

def make_cpu_rows(max_bar_width, format='rich'):
    with lock:
        cpu_percents = psutil.cpu_percent(percpu=True)
        cpu_freq = psutil.cpu_freq()

        rows = []
        # CPU Section
        if format == 'rich':
            rows.append(("[bold cyan]CPU[/bold cyan]", ""))
        else:
            rows.append(('<span style="font-weight: bold; color: cyan;">CPU</span>', ""))
        for i, perc in enumerate(cpu_percents):
            rows.append((f"Core {i}", make_bar(perc, max_bar_width, format)))
            rows.append(("", ""))
        if cpu_freq:
            rows.append(("Speed", f"{cpu_freq.current/1000:.2f} GHz"))
        rows.append(("", ""))

        # CPU Power
        cpu_watts, est = get_cpu_power()
        rows.append(("CPU Power", f"{cpu_watts:.1f} W" + (" (est)" if est else "")))

        # System Power
        sys_watts = get_system_power()
        if sys_watts is not None:
            rows.append(("System Power", f"{sys_watts:.1f} W"))
            if sys_watts > 0:
                rows.append(("CPU % of Total", f"{(cpu_watts/sys_watts*100):.1f}%"))
        else:
            rows.append(("System Power", "N/A"))
        rows.append(("", ""))

        return rows

def make_system_rows(max_bar_width, format='rich'):
    global prev_disk_io, prev_net
    with lock:
        ram = psutil.virtual_memory()
        curr_disk_io = psutil.disk_io_counters(perdisk=True)
        partitions = psutil.disk_partitions(all=False)
        if not partitions:
            partitions = [psutil._common.sdiskpart(device='/', mountpoint='/', fstype='', opts='') ]  # fallback to root

        curr_net = psutil.net_io_counters()
        net_sent_speed = (curr_net.bytes_sent - prev_net.bytes_sent) / 1024**2
        net_recv_speed = (curr_net.bytes_recv - prev_net.bytes_recv) / 1024**2

        rows = []
        # RAM Section
        if format == 'rich':
            rows.append(("[bold cyan]RAM[/bold cyan]", ""))
        else:
            rows.append(('<span style="font-weight: bold; color: cyan;">RAM</span>', ""))
        rows.append(("Usage", make_bar(ram.percent, max_bar_width, format)))
        rows.append(("", ""))
        rows.append(("Used", f"{ram.used / (1024**3):.2f} GB"))
        rows.append(("Free", f"{ram.available / (1024**3):.2f} GB"))
        rows.append(("", ""))

        # Disk Sections
        for p in partitions:
            if format == 'rich':
                rows.append(("[bold cyan]Disk " + p.mountpoint + "[/bold cyan]", ""))
            else:
                rows.append(('<span style="font-weight: bold; color: cyan;">Disk ' + p.mountpoint + '</span>', ""))
            try:
                usage = psutil.disk_usage(p.mountpoint)
                rows.append(("Usage", make_bar(usage.percent, max_bar_width, format)))
            except:
                rows.append(("Usage", "N/A"))
            rows.append(("", ""))

        # Network Section
        if format == 'rich':
            rows.append(("[bold cyan]Network[/bold cyan]", ""))
        else:
            rows.append(('<span style="font-weight: bold; color: cyan;">Network</span>', ""))
        rows.append(("Sent", f"{net_sent_speed:.2f} MB/s"))
        rows.append(("Recv", f"{net_recv_speed:.2f} MB/s"))

        prev_disk_io = curr_disk_io
        prev_net = curr_net

        return rows

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def data():
    cpu_rows = make_cpu_rows(max_bar_width=30, format='html')
    system_rows = make_system_rows(max_bar_width=30, format='html')
    return jsonify({'cpu_rows': cpu_rows, 'system_rows': system_rows})

if __name__ == '__main__':
    # Silence Flask/Werkzeug access logs
    import logging
    logging.getLogger('werkzeug').setLevel(logging.WARN)

    # Optional: also silence everything else if you really hate logs
    # logging.getLogger('werkzeug').disabled = True

    app.run(host='0.0.0.0', port=5000, debug=False)
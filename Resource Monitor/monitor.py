import psutil
import time
import win32com.client
from rich.live import Live
from rich.console import Console
from rich.table import Table as RichTable
from rich.padding import Padding
from shutil import get_terminal_size

# Disk/Net history
prev_disk = psutil.disk_io_counters()
prev_net = psutil.net_io_counters()

# Setup WMI
try:
    wmi = win32com.client.Dispatch("WbemScripting.SWbemLocator")
    w_cimv2 = wmi.ConnectServer(".", "root\\cimv2")
    w_wmi = wmi.ConnectServer(".", "root\\wmi")
except:
    w_cimv2, w_wmi = None, None


def make_color(perc):
    if perc < 25: return "bright_cyan"
    elif perc < 50: return "bright_green"
    elif perc < 75: return "bright_yellow"
    else: return "bright_red"


def make_bar(perc, max_width):
    filled = int(max_width * perc / 100)
    empty = max_width - filled
    return f"[{make_color(perc)}]{'░'*filled}[/][white]{'░'*empty}[/] {perc:>3.0f}%"


def get_cpu_power():
    # 1) Try explicit power sensors
    if w_cimv2:
        try:
            for cls in (
                "Win32_PerfFormattedData_Counters_ProcessorInformation",
                "Win32_PerfRawData_Counters_ProcessorInformation",
            ):
                try:
                    for item in getattr(w_cimv2, cls)():
                        if hasattr(item, "Power"):
                            val = getattr(item, "Power")
                            if val:
                                return float(val), False
                except:
                    pass
        except:
            pass

    # 2) Estimate using TDP × usage%
    tdp = None
    if w_cimv2:
        try:
            procs = w_cimv2.Win32_Processor()
            if procs:
                p = procs[0]
                for attr in ("ThermalDesignPower", "TDP", "MaxTDP"):
                    if hasattr(p, attr):
                        v = getattr(p, attr)
                        if v:
                            tdp = float(v)
                            break
        except:
            pass

    if tdp is None:
        tdp = 65.0  # fallback default

    cpu_pct = psutil.cpu_percent(interval=None)
    est_w = round(tdp * (cpu_pct / 100.0), 2)
    return est_w, True


def get_system_power():
    if not w_wmi:
        return None
    try:
        results = w_wmi.ExecQuery("SELECT * FROM BatteryStatus")
        for r in results:
            if hasattr(r, "DischargeRate"):
                val = r.DischargeRate
                if val:
                    return val / 1000.0  # mW → W
    except:
        pass
    return None


def make_table(max_bar_width, max_rows):
    global prev_disk, prev_net
    cpu_percents = psutil.cpu_percent(percpu=True)
    cpu_freq = psutil.cpu_freq()

    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    curr_disk = psutil.disk_io_counters()
    disk_read_speed = (curr_disk.read_bytes - prev_disk.read_bytes) / 1024**2
    disk_write_speed = (curr_disk.write_bytes - prev_disk.write_bytes) / 1024**2
    prev_disk = curr_disk

    curr_net = psutil.net_io_counters()
    net_sent_speed = (curr_net.bytes_sent - prev_net.bytes_sent) / 1024**2
    net_recv_speed = (curr_net.bytes_recv - prev_net.bytes_recv) / 1024**2
    prev_net = curr_net

    rows = []
    # CPU Section
    rows.append(("[bold cyan]CPU[/bold cyan]", ""))
    for i, perc in enumerate(cpu_percents):
        rows.append((f"Core {i}", make_bar(perc, max_bar_width)))
        rows.append(("", ""))
    rows.append(("Speed", f"{cpu_freq.current/1000:.2f} GHz"))
    rows.append(("", ""))

    # CPU Power
    cpu_watts, est = get_cpu_power()
    rows.append(("CPU Power", f"{cpu_watts:.1f} W" + (" (est)" if est else "")))

    # System Power
    sys_watts = get_system_power()
    if sys_watts is not None:
        rows.append(("System Power", f"{sys_watts:.1f} W"))
        # % CPU vs total
        if sys_watts > 0:
            rows.append(("CPU % of Total", f"{(cpu_watts/sys_watts*100):.1f}%"))
    else:
        rows.append(("System Power", "N/A"))
    rows.append(("", ""))

    # RAM Section
    rows.append(("[bold cyan]RAM[/bold cyan]", ""))
    rows.append(("Usage", make_bar(ram.percent, max_bar_width)))
    rows.append(("", ""))
    rows.append(("Used", f"{ram.used / (1024**3):.2f} GB"))
    rows.append(("Free", f"{ram.available / (1024**3):.2f} GB"))
    rows.append(("", ""))

    # Disk Section
    rows.append(("[bold cyan]Disk[/bold cyan]", ""))
    rows.append(("Usage", make_bar(disk.percent, max_bar_width)))
    rows.append(("", ""))
    rows.append(("Read", f"{disk_read_speed:.2f} MB/s"))
    rows.append(("Write", f"{disk_write_speed:.2f} MB/s"))
    rows.append(("", ""))

    # Network Section
    rows.append(("[bold cyan]Network[/bold cyan]", ""))
    rows.append(("Sent", f"{net_sent_speed:.2f} MB/s"))
    rows.append(("Recv", f"{net_recv_speed:.2f} MB/s"))

    if len(rows) > max_rows:
        rows = rows[:max_rows-1] + [("[bold red]...more rows[/bold red]", "")]

    return rows


console = Console()
with Live(console=console, refresh_per_second=0.5) as live:
    while True:
        size = get_terminal_size()
        max_bar_width = max(10, size.columns - 25)
        max_rows = size.lines - 5
        rich_table = RichTable(title="[bold cyan]PC Resource Monitor[/bold cyan]", border_style="cyan")
        rich_table.add_column("Resource", justify="left")
        rich_table.add_column("Usage", justify="left")
        for name, val in make_table(max_bar_width, max_rows):
            rich_table.add_row(Padding(name, (0,0,0,0)), Padding(val, (0,0,0,0)))
        live.update(rich_table)
        time.sleep(0.5)

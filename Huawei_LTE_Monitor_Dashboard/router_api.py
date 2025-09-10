import xml.etree.ElementTree as ET
from huawei_lte.router import B525Router
import atexit

IP = "192.168.8.1"
USERNAME = "admin"
PASSWORD = "samsung945"

router = B525Router(IP)
router.login(username=USERNAME, password=PASSWORD)

def get_router():
    router = B525Router(IP)
    return router

def clean_db(value):
    return float(value.lower().replace('dbm', '').replace('db', '').strip())
   
def router_logout():
    router.logout()

def get_router_signal():
    import xml.etree.ElementTree as ET
    raw = router.device.signal
    root = ET.fromstring(raw)

    def clean_db(value):
        if value is None:
            return None
        return float(value.lower().replace('dbm', '').replace('db', '').strip())

    data = {
        'rsrq': clean_db(root.findtext('rsrq')),
        'rsrp': clean_db(root.findtext('rsrp')),
        'current_band': root.findtext('band'),
        'dl_bandwidth': root.findtext('dlbandwidth'),
        'ul_bandwidth': root.findtext('ulbandwidth')
    }

    return data

def format_speed(bps):
    kbps = (bps * 8) / 1000  # Convert to kilobits/sec
    if kbps >= 1000:
        return f"{round(kbps / 1000, 2)} MBit/s"
    else:
        return f"{round(kbps, 1)} KBit/s"
    
def get_router_speeds():
    import xml.etree.ElementTree as ET
    raw = router.monitoring.traffic
    root = ET.fromstring(raw)

    download = int(root.findtext('CurrentDownloadRate') or 0)
    upload = int(root.findtext('CurrentUploadRate') or 0)

    return {
        'dl_speed': format_speed(download),
        'ul_speed': format_speed(upload)
    }
    
def get_network_info():
    raw = router.net.modelist2
    root = ET.fromstring(raw)

    mode = root.findtext('NetworkMode')

    bands = [b.text for b in root.findall('NetworkBands/Band')]
    lte_bands = [b.text for b in root.findall('LTEBands/Band')]

    return {
        'mode': mode,
        'network_bands': bands,
        'lte_bands': lte_bands
    }

def to_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return None

def get_sms_inbox():
    xml_data = {
        'PageIndex': 1,
        'ReadCount': 20,
        'BoxType': 1,
        'SortType': 0,
        'Ascending': 0,
        'UnreadPreferred': 0
    }
    resp = router.api('sms/sms-list', xml_data)
    root = ET.fromstring(resp)

    messages = []
    for msg in root.findall('.//Message'):
        
        index = msg.find('Index').text if msg.find('Index') is not None else ''
        phone = msg.find('Phone').text if msg.find('Phone') is not None else ''
        content = msg.find('Content').text if msg.find('Content') is not None else ''
        date = msg.find('Date').text if msg.find('Date') is not None else ''
        messages.append({
            'index': int(index) if index else None,
            'phone': phone,
            'content': content,
            'date': date,
        })
    return messages


def delete_sms(index):
    payload = {'Index': index}
    resp = router.api('sms/delete-sms', payload)
    return resp

def get_sim_number():
    import xml.etree.ElementTree as ET
    raw = router.device.info
    root = ET.fromstring(raw)
    sim_number = root.findtext("Msisdn")
    return sim_number

def seconds_to_hours(seconds):
    return int(seconds) / 3600

def get_device_info():
    import xml.etree.ElementTree as ET
    raw = router.device.info
    root = ET.fromstring(raw)

    data = {
        "device_name": root.findtext("DeviceName"),
        "serial_number": root.findtext("SerialNumber"),
        "imei": root.findtext("Imei"),
        "imsi": root.findtext("Imsi"),
        "iccid": root.findtext("Iccid"),
        "msisdn": root.findtext("Msisdn"),
        "hardver_version": root.findtext("HardwareVersion"),
        "software_version": root.findtext("SoftwareVersion"),
        "webui_version": root.findtext("WebUIVersion"),
        "mac_adress": root.findtext("MacAddress1"),
        "wan_ip_adress": root.findtext("WanIPAddress"),
        "wan_dns_address": root.findtext("wan_dns_address"),
        "product_family": root.findtext("ProductFamily"),
        "classify": root.findtext("Classify"),
        "supportmode": root.findtext("supportmode"),
        "workmode": root.findtext("workmode"),
        "submask": root.findtext("submask"),
        "mccmnc": root.findtext("Mccmnc"),
        "iniversion": root.findtext("iniversion"),
        "uptime": seconds_to_hours(root.findtext("uptime")),
        "imei_svn": root.findtext("ImeiSvn"),
        "wifi_mac_addr_wl0": root.findtext("WifiMacAddrWl0"),
        "wifi_mac_addr_wl1": root.findtext("WifiMacAddrWl1"),
        "spreadname_en": root.findtext("spreadname_en"),
    }
    print(data)
    return data

def get_notifications():
    raw = router.monitoring.notifications
    root = ET.fromstring(raw)
    unread_count = int(root.findtext('UnreadMessage') or 0)
    return unread_count

def clear_notifications():
    payload = {
            'PageIndex': 1,
            'ReadCount': 50,
            'BoxType': 1,
            'SortType': 0,
            'Ascending': 0,
            'UnreadPreferred': 1
        }
    resp = router.api('sms/sms-list', payload)
    root = ET.fromstring(resp)
    for msg in root.findall('.//Message'):
        idx = msg.findtext('Index')
        if idx:
            # mark as read
            router.api('sms/set-read', {'Index': int(idx), 'IsRead': 1})
            
def get_signal_strength():
    raw = router.device.signal_strength
    root = ET.fromstring(raw)
    return int(root.findtext('SignalStrength') or 0)

def set_antenna_type(val:int):
    request = f"<?xml version='1.0' encoding='UTF-8'?><request><antennasettype>{val}</antennasettype></request>"
    router.api('device/antenna_set_type', request)


atexit.register(lambda: router.logout())

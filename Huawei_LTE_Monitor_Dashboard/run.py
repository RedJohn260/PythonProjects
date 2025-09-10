import xml.dom.minidom
from huawei_lte.router import B525Router
import xml.etree.ElementTree as ET
import router_api

router = B525Router('192.168.8.1')
router.login('admin', 'pass')  # replace with your real password

xml_data = {
     'PageIndex': 1,
     'ReadCount': 20,
     'BoxType': 1,  # 1 = Inbox, 2 = Sent, 3 = Drafts
     'SortType': 0,
     'Ascending': 0,
     'UnreadPreferred': 0
}

request = '<?xml version="1.0" encoding="UTF-8"?><request><antennasettype>0</antennasettype></request>'
resp = router.api('device/antenna_set_type', request)
print(resp)

# Get raw XML of features
#raw_xml = router.voip.voice_settings
root = ET.fromstring(resp)
# Prettify and save
pretty = xml.dom.minidom.parseString(resp).toprettyxml()

with open("device_notifications.xml", "w", encoding="utf-8") as f:
    f.write(pretty)
router.logout()
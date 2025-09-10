import requests
import xml.etree.ElementTree as ET
import hashlib

BASE_URL = 'http://192.168.8.1'
SES_TOKEN_URL = BASE_URL + '/api/webserver/SesTokInfo'
LOGIN_URL = BASE_URL + '/api/user/login'
ANTENNA_URL = BASE_URL + '/api/device/antenna_settings'

session = requests.Session()

# Step 1: Get session token
resp = session.get(SES_TOKEN_URL)
root = ET.fromstring(resp.text)
session_id = root.find('SesInfo').text
token = root.find('TokInfo').text

# Step 2: Create hashed password
password = 'samsung945'  # change this
hashed_pw = hashlib.sha256((password + token).encode()).hexdigest().upper()

login_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<request>
  <Username>admin</Username>
  <Password>{hashed_pw}</Password>
  <password_type>4</password_type>
</request>"""

headers = {
    'Content-Type': 'text/xml',
    '__RequestVerificationToken': token,
    'Cookie': f'SesInfo={session_id}; __RequestVerificationToken={token}'
}

login_resp = session.post(LOGIN_URL, data=login_xml, headers=headers)
if login_resp.status_code != 200:
    print("Login failed")
    exit()

# Get new token from login response for next calls
new_token = login_resp.headers.get('__RequestVerificationToken')

# Step 3: Set antenna
antenna_xml = """<?xml version="1.0" encoding="UTF-8"?><request><antennasettype>1</antennasettype></request>"""

headers = {
    'Content-Type': 'text/xml',
    '__RequestVerificationToken': new_token,
    'Cookie': f'SessionID={session_id}; __RequestVerificationToken={new_token}'
}

antenna_resp = session.post(ANTENNA_URL, data=antenna_xml, headers=headers)

print("Antenna set response:")
print(antenna_resp.text)
from flask import Flask, render_template, jsonify, request
import router_api as router_api

app = Flask(__name__)

@app.route('/')
def dashboard():
    data = router_api.get_router_signal()
    sig = router_api.get_signal_strength()
    not_count = router_api.get_notifications()
    info = router_api.get_device_info()
    return render_template('dashboard.html', data=data, signal_strength=sig, not_count=not_count, info=info)

@app.route('/data')
def data():
    data = router_api.get_router_signal()
    return jsonify(data)

@app.route('/speed')
def speed():
    return jsonify(router_api.get_router_speeds())

@app.route('/system')
def system_page():
    net_info = router_api.get_network_info()
    not_count = router_api.get_notifications()
    sig = router_api.get_signal_strength()
    return render_template('system.html', net_info=net_info, not_count=not_count, signal_strength=sig)

@app.route('/system/netinfo')
def get_net_info():
    net_info = router_api.get_network_info()
    return jsonify(net_info)

@app.route('/system/<command>', methods=['POST'])
def system_command(command):
    router = router_api.get_router()
    router.login(username='admin', password='samsung945')

    try:
        if command == 'reboot':
            router.device.do_reboot()
            msg = 'Reboot command sent!'
        elif command == 'poweroff':
            router.device.do_poweroff()
            msg = 'Power off command sent!'
        else:
            msg = 'Unknown command'
    except Exception as e:
        msg = f'Error: {str(e)}'
    finally:
        router.logout()

    return jsonify({'message': msg})

@app.route('/system/applysettings', methods=['POST'])
def apply_network_settings():
    data = request.get_json()
    mode = data.get('mode')
    bands = data.get('bands', [])
    antenna = int(data.get('antenna', 3))  # default AUTO

    router = router_api.get_router()
    router.login(username='admin', password='samsung945')

    try:
        router.net.set_network_mode({'mode': mode})
        router.net.set_lte_band({'bands': bands})
        router_api.set_antenna_type(antenna)  # using router_api function to set antenna
        msg = f"Settings applied: Mode={mode}, Bands={', '.join(bands)}, Antenna={antenna}"
    except Exception as e:
        msg = f"Error applying settings: {str(e)}"
    finally:
        router.logout()

    return jsonify({'message': msg})

@app.route('/messages')
def sms_page():
    messages = router_api.get_sms_inbox()
    sim_number = router_api.get_sim_number()
    router_api.clear_notifications()
    sig = router_api.get_signal_strength()
    return render_template('messages.html', messages=messages, sim=sim_number, not_count=0, signal_strength=sig)

@app.route('/delete_sms/<int:index>', methods=['POST'])
def delete_sms(index):
    try:
        router_api.delete_sms(index)
        return jsonify({'message': f'Message {index} deleted.'})
    except Exception as e:
        return jsonify({'message': f'Error: {str(e)}'}), 500
    
@app.route('/delete-all-sms', methods=['POST'])
def delete_all_sms():
    messages = router_api.get_sms_inbox()
    for sms in messages:
        router_api.delete_sms(sms['index'])
    return jsonify({'message': 'All messages deleted'})

@app.route('/send_sms', methods=['POST'])
def send_sms():
    data = request.json
    phone = data.get('phone')
    message = data.get('message')

    router = router_api.get_router()
    router.login(username='admin', password='samsung945')

    xml_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
    <request>
    <Index>0</Index>
    <Phones>
        <Phone>+1234567890</Phone>
    </Phones>
    <Sca></Sca>
    <Content>Your message here</Content>
    <Length>16</Length>
    <Reserved>1</Reserved>
    <Date></Date>
    </request>"""

    try:
        resp = router.api('sms/send-sms', xml_payload)
        print(resp)
        msg = 'Message sent!' if resp else 'Failed to send message.'
    except Exception as e:
        msg = f'Error: {str(e)}'
    finally:
        router.logout()

    return jsonify({'message': msg})

@app.route('/info')
def device_page():
    info = router_api.get_device_info()
    not_count = router_api.get_notifications()
    sig = router_api.get_signal_strength()
    return render_template('info.html', info=info, not_count=not_count, signal_strength=sig)

@app.route('/api/notifications')
def api_notifications():
    count = router_api.get_notifications()
    return jsonify({'count': count})

@app.route('/api/signal-strength')
def api_signal_strength():
    strength = router_api.get_signal_strength()
    return jsonify({'strength': strength})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
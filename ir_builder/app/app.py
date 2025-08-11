import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, jsonify
import requests
import json
import os
import logging
import websocket
from eventlet import wsgi

# Configure basic logging for the application
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

# Log the application start
app.logger.info("Starting IR Builder Flask application...")

# Load the Home Assistant token and URL from environment variables
# This uses the SUPERVISOR_TOKEN which is automatically provided to add-ons.
HA_URL = os.environ.get('HA_URL', 'http://supervisor/core/api/')
HA_TOKEN = os.environ.get('SUPERVISOR_TOKEN')
BROADLINK_STORAGE_PATH = '/config/.storage/broadlink_remote_{mac}_codes.json'

# Log the token status for debugging
if HA_TOKEN:
    app.logger.info("SUPERVISOR_TOKEN is successfully loaded.")
else:
    app.logger.error("SUPERVISOR_TOKEN is not available. API calls will fail.")

# Create the headers dictionary for all Home Assistant API requests
# This must be done after confirming the token exists.
HEADERS = {
    'Authorization': f'Bearer {HA_TOKEN}',
    'Content-Type': 'application/json',
}

WS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIwMDU1YjMzNjI5NWY0OGFlOGU3NTRkNjg2MzAwOTM0YSIsImlhdCI6MTc1NDkzMjUwNCwiZXhwIjoyMDcwMjkyNTA0fQ.Ht05mvo_owQmzaJBgor26DxtZXjx5zDArLkTTB6Ei34"


def _get_device_registry_via_websocket():
    """
    Connects to the Home Assistant WebSocket API, retrieves the device registry,
    logs the raw response, and returns the registry data.
    """
    app.logger.info("Attempting to get device registry via WebSocket...")
    ha_ws_url = 'ws://supervisor/core/api/websocket'

    try:
        ws = websocket.create_connection(ha_ws_url)
        
        # 1. Wait for the initial 'auth_required' message from HA
        auth_required_response = json.loads(ws.recv())
        app.logger.info(f"Initial HA WebSocket message: {json.dumps(auth_required_response, indent=2)}")

        if auth_required_response.get('type') != 'auth_required':
            app.logger.error(f"Unexpected initial WebSocket response from Home Assistant.{json.dumps(auth_required_response, indent=2)}")
            return None

        # 2. Respond with the authentication payload
        auth_payload = {
            "type": "auth",
            "access_token": WS_TOKEN
        }
        ws.send(json.dumps(auth_payload))

        # 3. Wait for the 'auth_ok' message to confirm authentication
        auth_ok_response = json.loads(ws.recv())
        app.logger.info(f"HA WebSocket auth response: {json.dumps(auth_ok_response, indent=2)}")

        if auth_ok_response.get('type') != 'auth_ok':
            app.logger.error("WebSocket authentication failed.")
            return None
        
        app.logger.info("Successfully authenticated with Home Assistant WebSocket.")

        # 4. Send the command to get the device registry
        request_id = 1
        request_payload = {
            "id": request_id,
            "type": "config/device_registry/get"
        }
        ws.send(json.dumps(request_payload))

        # 5. Listen for the response
        while True:
            response = json.loads(ws.recv())
            app.logger.info(f"Received HA WebSocket message: {json.dumps(response, indent=2)}")

            if response.get('id') == request_id and response.get('type') == 'result':
                if response.get('success'):
                    app.logger.info("Successfully received device registry via WebSocket.")
                    return response.get('result')
                else:
                    app.logger.error(f"Failed to get device registry via WebSocket. Error: {response.get('error', {}).get('message')}")
                    return None
            
    except Exception as e:
        app.logger.error(f"WebSocket error: {e}")
        return None
    finally:
        if 'ws' in locals() and ws:
            ws.close()

def _get_mac_address_from_entity_id(entity_id):
    """
    Finds the MAC address for a given entity_id by querying the Home Assistant 
    entity and device registries.
    """
    app.logger.info(f"Attempting to find MAC address for {entity_id}...")
    try:
        # Step 1: Query the entity registry to get the device_id
        #entity_response = requests.get(f'{HA_URL}config/entity_registry', headers=HEADERS, timeout=10)
        #entity_response.raise_for_status()
        #entity_registry = entity_response.json()

        #app.logger.info(f"entity_registry response: {json.dumps(entity_registry, indent=4)}")
        
        device_id = None
        #for entity_entry in entity_registry:
        #    if entity_entry.get('entity_id') == entity_id:
        #        device_id = entity_entry.get('device_id')
        #        break

        #if not device_id:
        #    app.logger.warning(f"Could not find device_id for entity {entity_id} in entity registry.")
        #    return None

        # Step 2: Query the device registry using the found device_id to get the MAC address
        # *** Using WebSocket API instead of REST API as requested ***
        device_registry = _get_device_registry_via_websocket()
        if not device_registry:
            app.logger.error("Failed to retrieve device registry via WebSocket.")
            return None

        app.logger.info(f"device_registry response: {json.dumps(device_registry, indent=4)}")

        for device_entry in device_registry:
            if device_entry.get('id') == device_id:
                if 'connections' in device_entry:
                    for connection in device_entry['connections']:
                        if len(connection) == 2 and connection[0] == 'mac':
                            # The MAC address needs to be formatted for the storage file name.
                            return connection[1].replace(':', '').upper()

    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error fetching registries from Home Assistant: {e}")
    
    app.logger.warning(f"Could not find MAC address for entity {entity_id}.")
    return None

def _get_broadlink_file_path(mac_address):
    """
    Generates the expected file path for a Broadlink device's storage file.
    """
    return BROADLINK_STORAGE_PATH.format(mac=mac_address)

@app.route('/')
def index():
    """Renders the main page and fetches Broadlink remote devices from Home Assistant."""
    app.logger.info("Received request for the home page ('/').")
    
    # Check if the token exists before attempting any API calls
    if not HA_TOKEN:
        return "Error: Home Assistant token is not available.", 500

    try:
        app.logger.info("Making API call to fetch Home Assistant states...")
        response = requests.get(f'{HA_URL}states', headers=HEADERS, timeout=10)
        response.raise_for_status()  # This will raise an HTTPError for bad responses (4xx or 5xx)
        
        states = response.json()
        app.logger.info(f"Successfully fetched {len(states)} states from Home Assistant.")
        #app.logger.info(f"STATES JSON: {json.dumps(states, indent=4)}")

        # Filter the states to find only Broadlink remote devices
        broadlink_devices = [
            state for state in states 
            if state['entity_id'].startswith('remote.') and (state['attributes'].get('supported_features', 0) & 1) #and 'broadlink' in state['entity_id']
        ]
        enhanced_devices = []
        for device in broadlink_devices:
            mac_address = _get_mac_address_from_entity_id(device['entity_id'])
            if mac_address:
                # Assuming the device name is the friendly_name from the state
                device_name = device['attributes'].get('friendly_name', device['entity_id'])
                enhanced_devices.append({
                    'entity_id': device['entity_id'],
                    'name': device_name,
                    'mac': mac_address
                })
                
        app.logger.info(f"Found {len(broadlink_devices)} Broadlink remote devices.")
        app.logger.info(f"Found {len(enhanced_devices)} Broadlink remote devices with MAC addresses.")
        app.logger.info(f"Broadlink devices JSON: {json.dumps(broadlink_devices, indent=4)}")

        # Render the HTML template, passing the list of devices
        return render_template('index.html', devices=broadlink_devices)
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error connecting to Home Assistant API: {e}")
        return f"Error connecting to Home Assistant: {e}", 500
@app.route('/get_codes', methods=['POST'])
def get_codes():
    """
    Retrieves learned IR commands from the Broadlink device's .storage file.
    """
    entity_id = request.json.get('entity_id')
    app.logger.info(f"Received request to get learned codes for entity {entity_id}.")

    if not entity_id:
        return jsonify({'status': 'error', 'message': 'Missing entity_id.'}), 400

    mac_address = _get_mac_address_from_entity_id(entity_id)
    if not mac_address:
        return jsonify({'status': 'error', 'message': f'Could not find MAC address for {entity_id}.'}), 404

    file_path = _get_broadlink_file_path(mac_address)
    
    if not os.path.exists(file_path):
        app.logger.warning(f"Storage file not found for {entity_id} at {file_path}. Assuming no learned codes.")
        return jsonify({'status': 'success', 'devices': {}}), 200

    try:
        # Read the entire file
        with open(file_path, 'r') as f:
            data = json.load(f)
        app.logger.info(f"Successfully read and parsed codes for {entity_id}.")
        return jsonify({'status': 'success', 'devices': data.get('data', {}).get('devices', {})})
    except (IOError, json.JSONDecodeError) as e:
        app.logger.error(f"Error reading or parsing storage file at {file_path}: {e}")
        return jsonify({'status': 'error', 'message': 'Failed to read learned codes file.'}), 500

@app.route('/delete_command', methods=['POST'])
def delete_command():
    """
    Deletes a specific learned command by calling the Home Assistant remote.learn_command service
    with the 'delete_command' payload.
    """
    entity_id = request.json.get('entity_id')
    device_name = request.json.get('device')
    command_name = request.json.get('command')
    app.logger.info(f"Received request to delete command '{command_name}' for device '{device_name}' on entity {entity_id}.")

    if not all([entity_id, device_name, command_name]):
        return jsonify({'status': 'error', 'message': 'Missing required parameters (entity_id, device, command).'}), 400
    
    # Construct the payload to call the Home Assistant service
    data = {
        "entity_id": entity_id,
        "device": device_name,
        "command": command_name # This is the command to be deleted
    }

    try:
        # Call the remote.learn_command service via the HA API
        # The service internally handles the deletion based on the payload.
        response = requests.post(
            f'{HA_URL}services/remote/delete_command', 
            headers=HEADERS, 
            json=data,
            timeout=10
        )
        response.raise_for_status()

        app.logger.info(f"Successfully sent delete command request for '{command_name}' to Home Assistant.")
        return jsonify({'status': 'success', 'message': f"Command '{command_name}' deletion request sent to Home Assistant."})
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Failed to call service to delete command: {e}")
        return jsonify({'status': 'error', 'message': f'Failed to call service: {e}'}), 500

@app.route('/learn_mode', methods=['POST'])
def learn_mode():
    """Calls the Home Assistant service to put a specific device in learning mode."""
    entity_id = request.json.get('entity_id')
    device = request.json.get('device')
    command = request.json.get('command')
    app.logger.info(f"Received request to start learning mode for {entity_id} {command}.")

    if not entity_id or not command:
        return jsonify({'status': 'error', 'message': 'No entity_id provided.'}), 400

    data = {"entity_id": entity_id,
        "device": device,
        "command": command
    }

    # --- ADDED CODE FOR TRACING ---
    app.logger.info(f"Calling HA API: URL='{HA_URL}services/remote/learn_command'")
    app.logger.info(f"Headers: {HEADERS}")
    app.logger.info(f"Payload: {json.dumps(data)}")
    # -----------------------------
    
    try:
        # Call the `remote.learn_command` service via the HA API
        response = requests.post(
            f'{HA_URL}services/remote/learn_command', 
            headers=HEADERS, 
            json=data,
            timeout=10
        )
        response.raise_for_status()
        
        app.logger.info(f"Successfully activated learning mode for {entity_id}.")
        return jsonify({
            'status': 'success', 
            'message': f'Learning mode activated for {entity_id}. Press a button on your remote.'
        })
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Failed to call service for {entity_id}: {e}")
        return jsonify({'status': 'error', 'message': f'Failed to call service: {e}'}), 500

@app.route('/generate_yaml', methods=['POST'])
def generate_yaml():
    """Generates a YAML automation for a learned command."""
    device_id = request.json.get('device_id')
    command_name = request.json.get('command_name')
    app.logger.info(f"Received request to generate YAML for device {device_id} with command '{command_name}'.")

    if not all([device_id, command_name]):
        return jsonify({'status': 'error', 'message': 'Missing required parameters.'}), 400

    # A simple YAML template for the automation
    yaml_template = f"""
- id: 'generated_ir_command_{command_name}'
  alias: 'IR Command - {command_name.replace("_", " ").title()}'
  trigger:
    - platform: state
      entity_id: remote.{device_id.split('.')[1]}
      to: 'learning_command_complete'
  action:
    - service: remote.send_command
      data:
        entity_id: remote.{device_id.split('.')[1]}
        command:
          - '{command_name}'
    """
    
    app.logger.info("Successfully generated YAML template.")
    return jsonify({'status': 'success', 'yaml': yaml_template})

if __name__ == '__main__':
    # Patch standard library for non-blocking I/O
    #eventlet.monkey_patch()
    # Use eventlet's WSGI server to run the Flask app
    wsgi.server(eventlet.listen(('0.0.0.0', 8389)), app)
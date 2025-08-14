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

# Load the Home Assistant token from environment variables
HA_TOKEN = os.environ.get('SUPERVISOR_TOKEN')
BROADLINK_STORAGE_PATH = '/config/.storage/broadlink_remote_{mac}_codes'

# Log the token status for debugging
if HA_TOKEN:
    app.logger.info("SUPERVISOR_TOKEN is successfully loaded.")
else:
    app.logger.error("SUPERVISOR_TOKEN is not available. API calls will fail.")

# Create the headers dictionary for all Home Assistant API requests
HEADERS = {
    'Authorization': f'Bearer {HA_TOKEN}',
    'Content-Type': 'application/json',
}

def _get_all_states_via_rest():
    """
    Retrieves the states for all entities via the Home Assistant REST API.
    Returns a dictionary mapping entity IDs to their state objects.
    """
    app.logger.info("Attempting to get all entity states via REST API...")
    url = 'http://supervisor/core/api/states'
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        states = response.json()
        
        # Convert the list of state objects into a dictionary for easy lookup
        return {state['entity_id']: state for state in states}
    except requests.exceptions.RequestException as e:
        app.logger.error(f"REST API error fetching states: {e}")
        return {}

def _get_entity_registry_via_websocket():
    """
    Connects to the HA WebSocket API and retrieves the entity registry.
    """
    app.logger.info("Attempting to get entity registry via WebSocket...")
    ha_ws_url = 'ws://supervisor/core/api/websocket'
    
    try:
        ws = websocket.create_connection(ha_ws_url)
        
        auth_required_response = json.loads(ws.recv())
        if auth_required_response.get('type') != 'auth_required':
            app.logger.error("Unexpected initial WebSocket response.")
            return None

        auth_payload = {"type": "auth", "access_token": HA_TOKEN}
        ws.send(json.dumps(auth_payload))

        auth_ok_response = json.loads(ws.recv())
        if auth_ok_response.get('type') != 'auth_ok':
            app.logger.error("WebSocket authentication failed.")
            return None
        
        app.logger.info("Successfully authenticated with Home Assistant WebSocket.")

        request_id = 1
        request_payload = {"id": request_id, "type": "config/entity_registry/list"}
        ws.send(json.dumps(request_payload))

        while True:
            response = json.loads(ws.recv())
            if response.get('id') == request_id and response.get('type') == 'result':
                if response.get('success'):
                    app.logger.info("Successfully received entity registry via WebSocket.")
                    return response.get('result')
                else:
                    app.logger.error(f"Failed to get entity registry. Error: {response.get('error', {}).get('message')}")
                    return None
            
    except Exception as e:
        app.logger.error(f"WebSocket error for entity registry: {e}")
        return None
    finally:
        if 'ws' in locals() and ws:
            ws.close()

    """
    Connects to the HA WebSocket API and retrieves detailed information for a single entity.
    """
    app.logger.info(f"Attempting to get details for entity {entity_id} via WebSocket...")
    ha_ws_url = 'ws://supervisor/core/api/websocket'
    
    try:
        ws = websocket.create_connection(ha_ws_url)
        auth_required_response = json.loads(ws.recv())
        if auth_required_response.get('type') != 'auth_required':
            return None

        auth_payload = {"type": "auth", "access_token": HA_TOKEN}
        ws.send(json.dumps(auth_payload))

        auth_ok_response = json.loads(ws.recv())
        if auth_ok_response.get('type') != 'auth_ok':
            return None
        
        request_id = 1
        request_payload = {
            "id": request_id,
            "type": "config/entity_registry/get",
            "entity_id": entity_id
        }
        ws.send(json.dumps(request_payload))

        while True:
            response = json.loads(ws.recv())
            if response.get('id') == request_id and response.get('type') == 'result':
                if response.get('success'):
                    return response.get('result')
                else:
                    app.logger.error(f"Failed to get entity details for {entity_id}. Error: {response.get('error', {}).get('message')}")
                    return None
            
    except Exception as e:
        app.logger.error(f"WebSocket error for entity details: {e}")
        return None
    finally:
        if 'ws' in locals() and ws:
            ws.close()

def _get_broadlink_file_path(mac_address):
    """
    Generates the expected file path for a Broadlink device's storage file.
    """
    return BROADLINK_STORAGE_PATH.format(mac=mac_address)

@app.route('/')
def index():
    """
    Renders the main page by combining data from the WebSocket and REST API
    to find Broadlink remote devices with the correct supported features.
    """
    app.logger.info("Received request for the home page ('/').")
    
    if not HA_TOKEN:
        return "Error: Home Assistant token is not available.", 500

    # Step 1: Get the full entity registry list via WebSocket
    entity_list = _get_entity_registry_via_websocket()
    if not entity_list:
        return "Error: Could not retrieve entity registry from Home Assistant.", 500

    # Step 2: Get all entity states via REST API
    all_states = _get_all_states_via_rest()
    if not all_states:
        return "Error: Could not retrieve entity states from Home Assistant.", 500

    enhanced_devices = []
    # Step 3: Iterate through the WebSocket results and cross-reference with the REST API states
    for entity in entity_list:
        # Check if the entity is a remote and if its state information exists
        if entity['entity_id'].startswith('remote.') and entity['entity_id'] in all_states:
            state = all_states[entity['entity_id']]
            # Check the supported_features from the state data
            supported_features = state.get('attributes', {}).get('supported_features')
            
            if supported_features == 3:
                # If supported_features is 3, it's a remote that supports learning
                mac_address = entity.get('unique_id')
                
                enhanced_devices.append({
                    'entity_id': entity['entity_id'],
                    'name': entity.get('name', entity['entity_id']),
                    'mac': mac_address
                })
                app.logger.info(f"Found {json.dumps(entity)}")

    app.logger.info(f"Found {len(enhanced_devices)} Broadlink remote devices.")
    app.logger.info(f"Found {json.dumps(enhanced_devices)}")
    
    return render_template('index.html', devices=enhanced_devices)

@app.route('/get_codes', methods=['POST'])
def get_codes():
    """
    Retrieves learned IR commands from the Broadlink device's .storage file.
    """
    entity_id = request.json.get('entity_id')
    mac_address = request.json.get('mac')
    app.logger.info(f"Received request to get learned codes for entity {entity_id}.")

    if not mac_address:
        return jsonify({'status': 'error', 'message': 'Missing MAC address.'}), 400

    file_path = _get_broadlink_file_path(mac_address)
    
    if not os.path.exists(file_path):
        app.logger.warning(f"Storage file not found for {entity_id} at {file_path}. Assuming no learned codes.")
        return jsonify({'status': 'success', 'devices': {}}), 200

    try:
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
    
    data = {
        "entity_id": entity_id,
        "device": device_name,
        "command": command_name
    }

    try:
        response = requests.post(
            f'http://supervisor/core/api/services/remote/delete_command', 
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
    
    try:
        response = requests.post(
            f'http://supervisor/core/api/services/remote/learn_command', 
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
    entity_id = request.json.get('entity_id')
    command_name = request.json.get('command_name')
    app.logger.info(f"Received request to generate YAML for entity {entity_id} with command '{command_name}'.")

    if not all([entity_id, command_name]):
        return jsonify({'status': 'error', 'message': 'Missing required parameters.'}), 400

    yaml_template = f"""
- id: 'generated_ir_command_{command_name}'
  alias: 'IR Command - {command_name.replace("_", " ").title()}'
  trigger:
    - platform: state
      entity_id: {entity_id}
      to: 'learning_command_complete'
  action:
    - service: remote.send_command
      data:
        entity_id: {entity_id}
        command:
          - '{command_name}'
    """
    
    app.logger.info("Successfully generated YAML template.")
    return jsonify({'status': 'success', 'yaml': yaml_template})

if __name__ == '__main__':
    wsgi.server(eventlet.listen(('0.0.0.0', 8389)), app)
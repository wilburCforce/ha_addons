# app.py
from flask import Flask, render_template, request, jsonify
import requests
import json
import os

app = Flask(__name__)

# Load the Home Assistant token and URL from environment variables
# In a real add-on, these would be passed securely
HA_URL = os.environ.get('HA_URL', 'http://supervisor/core/api/')
#HA_TOKEN = os.environ.get('HA_TOKEN', 'YOUR_LONG_LIVED_ACCESS_TOKEN')
HA_TOKEN = os.environ.get('SUPERVISOR_TOKEN')
HEADERS = {
    'Authorization': f'Bearer {HA_TOKEN}',
    'Content-Type': 'application/json',
}

@app.route('/')
def index():
    """Renders the main page and fetches devices."""
    try:
        response = requests.get(f'{HA_URL}states', headers=HEADERS)
        response.raise_for_status()
        states = response.json()
        broadlink_devices = [
            state for state in states 
            if state['entity_id'].startswith('remote.') and 'broadlink' in state['entity_id']
        ]
        return render_template('index.html', devices=broadlink_devices)
    except requests.exceptions.RequestException as e:
        return f"Error connecting to Home Assistant: {e}", 500

@app.route('/learn_mode', methods=['POST'])
def learn_mode():
    """Calls the Home Assistant service to put a device in learning mode."""
    entity_id = request.json.get('entity_id')
    if not entity_id:
        return jsonify({'status': 'error', 'message': 'No entity_id provided.'}), 400

    data = {
        "entity_id": entity_id
    }
    try:
        # Assuming the service is remote.learn_command. Adjust if your Broadlink integration uses a different service.
        response = requests.post(f'{HA_URL}services/remote/learn_command', headers=HEADERS, json=data)
        response.raise_for_status()
        return jsonify({'status': 'success', 'message': f'Learning mode activated for {entity_id}. Press a button on your remote.'})
    except requests.exceptions.RequestException as e:
        return jsonify({'status': 'error', 'message': f'Failed to call service: {e}'}), 500

@app.route('/generate_yaml', methods=['POST'])
def generate_yaml():
    """Generates the YAML for a Home Assistant automation."""
    device_id = request.json.get('device_id')
    command_name = request.json.get('command_name')

    if not all([device_id, command_name]):
        return jsonify({'status': 'error', 'message': 'Missing required parameters.'}), 400

    # This is a basic template. You can make this more robust.
    yaml_template = f"""
- id: 'generated_ir_command_{command_name}'
  alias: 'IR Command - {command_name.replace("_", " ").title()}'
  trigger:
    - platform: state
      entity_id: remote.{device_id.split('.')[1]} # assuming remote.broadlink_device
      to: 'learning_command_complete' # The state change that indicates a learned command is ready
  action:
    - service: remote.send_command
      data:
        entity_id: remote.{device_id.split('.')[1]}
        command:
          - '{command_name}'
    """
    return jsonify({'status': 'success', 'yaml': yaml_template})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
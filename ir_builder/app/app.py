# app.py
from flask import Flask, render_template, request, jsonify
import requests
import json
import os
import logging

# Configure basic logging for the application
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

# Log the application start
app.logger.info("Starting IR Builder Flask application...")

# Load the Home Assistant token and URL from environment variables
# This uses the SUPERVISOR_TOKEN which is automatically provided to add-ons.
HA_URL = os.environ.get('HA_URL', 'http://supervisor/core/api/')
HA_TOKEN = os.environ.get('SUPERVISOR_TOKEN')

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

@app.route('/')
def index():
    """Renders the main page and fetches Broadlink remote devices from Home Assistant."""
    app.logger.info("Received request for the home page ('/').")
    
    # Check if the token exists before attempting any API calls
    if not HA_TOKEN:
        return "Error: Home Assistant token is not available.", 500

    try:
        # Make a GET request to the Home Assistant API to get all states
        app.logger.info("Making API call to fetch Home Assistant states...")
        response = requests.get(f'{HA_URL}states', headers=HEADERS, timeout=10)
        response.raise_for_status()  # This will raise an HTTPError for bad responses (4xx or 5xx)
        
        states = response.json()
        app.logger.info(f"Successfully fetched {len(states)} states from Home Assistant.")

        # Filter the states to find only Broadlink remote devices
        broadlink_devices = [
            state for state in states 
            if state['entity_id'].startswith('remote.') #and 'broadlink' in state['entity_id']
        ]
        app.logger.info(f"Found {len(broadlink_devices)} Broadlink remote devices.")
        app.logger.info(f"Broadlink devices JSON: {json.dumps(broadlink_devices, indent=4)}")

        # Render the HTML template, passing the list of devices
        return render_template('index.html', devices=broadlink_devices)
    except requests.exceptions.RequestException as e:
        # Log and return a user-friendly error message if the API call fails
        app.logger.error(f"Error connecting to Home Assistant API: {e}")
        return f"Error connecting to Home Assistant: {e}", 500

@app.route('/learn_mode', methods=['POST'])
def learn_mode():
    """Calls the Home Assistant service to put a specific device in learning mode."""
    entity_id = request.json.get('entity_id')
    app.logger.info(f"Received request to start learning mode for {entity_id}.")

    if not entity_id:
        return jsonify({'status': 'error', 'message': 'No entity_id provided.'}), 400

    data = {"entity_id": entity_id}
    
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
    # Ensure the Flask app runs on the correct host and port for Ingress
    app.run(host='0.0.0.0', port=8389, debug=True)
# app.py
from flask import Flask, render_template, request, jsonify
import requests
import json
import os

app = Flask(__name__)
app.logger.info("Flask app instance created.")

# Load the Home Assistant token and URL from environment variables
HA_URL = os.environ.get('HA_URL', 'http://supervisor/core/api/')
HA_TOKEN = os.environ.get('SUPERVISOR_TOKEN')

app.logger.info("Attempting to get HA_TOKEN from SUPERVISOR_TOKEN...")
if HA_TOKEN:
    app.logger.info(f"SUPERVISOR_TOKEN is set. Token length: {len(HA_TOKEN)}.")
    HEADERS = {
        'Authorization': f'Bearer {HA_TOKEN}',
        'Content-Type': 'application/json',
    }
    app.logger.info("HEADERS dictionary created successfully.")
else:
    app.logger.error("SUPERVISOR_TOKEN is not set. Add-on cannot access Home Assistant API.")
    HEADERS = {} # Fallback
    
app.logger.info("Defining Flask routes...")
@app.route('/')
def index():
    """Renders the main page and fetches devices."""
    app.logger.info("Route '/' called.")
    if not HA_TOKEN:
        return "Error: Home Assistant token is not available.", 500
    try:
        app.logger.info(f"Fetching states from: {HA_URL}states")
        response = requests.get(f'{HA_URL}states', headers=HEADERS)
        response.raise_for_status()
        states = response.json()
        app.logger.info(f"Successfully fetched {len(states)} states.")
        broadlink_devices = [
            state for state in states 
            if state['entity_id'].startswith('remote.') and 'broadlink' in state['entity_id']
        ]
        app.logger.info(f"Found {len(broadlink_devices)} Broadlink devices.")
        return render_template('index.html', devices=broadlink_devices)
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error connecting to Home Assistant: {e}")
        return f"Error connecting to Home Assistant: {e}", 500

@app.route('/learn_mode', methods=['POST'])
def learn_mode():
    """Calls the Home Assistant service to put a device in learning mode."""
    # ... (rest of your learn_mode function) ...
    pass

@app.route('/generate_yaml', methods=['POST'])
def generate_yaml():
    """Generates the YAML for a Home Assistant automation."""
    # ... (rest of your generate_yaml function) ...
    pass

if __name__ == '__main__':
    app.logger.info("Attempting to run Flask app...")
    app.run(host='0.0.0.0', port=8089, debug=True)
    app.logger.info("Flask app has started.")

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
            if state['entity_id'].startswith('remote.') and 'broadlink' in state['entity_id']
        ]
        app.logger.info(f"Found {len(broadlink_devices)} Broadlink remote devices.")

        # Render the HTML template, passing the list of devices
        return render_template('index.html', devices=broadlink_devices)
    except requests.exceptions.RequestException as e:
        # Log and return a user-friendly error message if the API call fails
        app.logger.error(f"Error connecting to Home Assistant API: {e}")
        return f"Error connecting to Home Assistant: {e}", 500



if __name__ == '__main__':
    # The app is now configured to run on port 8389.
    app.run(host='0.0.0.0', port=8389, debug=True)
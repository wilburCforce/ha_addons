import os
import requests
import json
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# Get the Home Assistant API token and URL from the environment
# The Home Assistant base image automatically exposes these
TOKEN = os.environ.get('SUPERVISOR_TOKEN')
HASS_URL = "http://supervisor/core/api"

app.logger.info(f"SUPERVISOR_TOKEN is set: {bool(TOKEN)}")
app.logger.info(f"Using token: {TOKEN[:5]}...")

@app.route('/')
def index():
    # Fetch all automations from the Home Assistant API
    headers = {
        'Authorization': f'Bearer {TOKEN}',
        'Content-Type': 'application/json'
    }
    response = requests.get(f'{HASS_URL}/states', headers=headers)
    response.raise_for_status()
    states = response.json()

    automations = []
    for state in states:
        if state['entity_id'].startswith('automation.'):
            # Fetch the full YAML for the automation
            # This is a bit more complex. You'd need to find a way to get the YAML from the automations.yaml file.
            # A simpler way for a proof-of-concept is to just get the state and attribute data.
            automations.append({
                'entity_id': state['entity_id'],
                'alias': state['attributes'].get('friendly_name', 'No Alias'),
                'raw_yaml': '...' # You would pull this from the file system, or a specific API endpoint.
            })

    return render_template('index.html', automations=automations)

@app.route('/submit', methods=['POST'])
def submit():
    selected_automations = request.form.getlist('selected_automations')
    data_to_submit = []

    for automation_id in selected_automations:
        user_description = request.form.get(f'description_{automation_id}')
        
        # In a real app, you would fetch the full YAML and friendly names here.
        
        data_to_submit.append({
            'entity_id': automation_id,
            'description': user_description,
            'yaml': '...', # The full YAML code
            'friendly_names': '...' # The mapped friendly names
        })
    
    # Send the data to your crowdsourcing server
    # response = requests.post("https://your-server.com/submit-data", json=data_to_submit)

    # Redirect back to the main page after submission
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8099)

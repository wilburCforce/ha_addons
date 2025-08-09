# app.py
from flask import Flask

# Log the application start
app = Flask(__name__)

@app.route('/')
def hello_world():
    """Renders a simple text response."""
    return "<h1>Hello, from IR Builder!</h1>"

if __name__ == '__main__':
    # Ensure the Flask app runs on the correct host and port for Ingress
    app.run(host='0.0.0.0', port=8089, debug=True)

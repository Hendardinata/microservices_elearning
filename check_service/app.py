import requests
import threading
import time
from flask import Flask, jsonify, g

app = Flask(__name__)

# Service URLs
SERVICE_URLS = {
    'user_service': 'http://127.0.0.1:5000/users',
    'kelas_service': 'http://127.0.0.1:5002/kelas',
    'jurusan_service': 'http://127.0.0.1:5003/jurusan',
    'materi_service': 'http://127.0.0.1:5004/materi',
    'hello_service': 'http://127.0.0.1:5001/hello'
}

# Store service availability status
service_status = {service: True for service in SERVICE_URLS.keys()}

def check_service_availability():
    global service_status
    for service, url in SERVICE_URLS.items():
        try:
            response = requests.get(url)
            response.raise_for_status()
            service_status[service] = True
        except requests.exceptions.RequestException:
            service_status[service] = False

    # Schedule the next check after a delay (e.g., 60 seconds)
    threading.Timer(60, check_service_availability).start()

# Start the service availability check
check_service_availability()

@app.route('/checking/site')
def service_check():
    unavailable_services = [service for service, available in service_status.items() if not available]
    if unavailable_services:
        error_message = 'Service(s) unavailable: ' + ', '.join(unavailable_services)
        g.service_error = error_message
        return jsonify({'error': error_message}), 503

@app.route('/')
def index():
    return 'All services are running!'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5008, debug=True)

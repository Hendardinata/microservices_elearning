from flask import Flask, request, redirect, render_template, session, make_response
from flask_cors import CORS
from flask_session import Session
from werkzeug.security import check_password_hash
from pymongo import MongoClient
import os
from zoneinfo import ZoneInfo
from redis import Redis
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

# Inisialisasi aplikasi Flask
app = Flask(__name__, template_folder='argon-dashboard/templates', static_folder='argon-dashboard/assets')

# Mengatur Random Secret Key
app.secret_key = 'your-consistent-secret-key'

# Mengatur CORS (Cross-Origin Resource Sharing)
CORS(app, supports_credentials=True)  # Mengatur agar cookies dapat dikirim lintas domain

HELLO_SERVICE_URL = os.getenv('HELLO_SERVICE_URL')

# Koneksi ke MongoDB
mongo_uri = os.getenv('MONGO_URI')
mongo_db_name = os.getenv('MONGO_DB_NAME')
client = MongoClient(mongo_uri)
db = client[mongo_db_name]
user_collection = db["users"]

# Konfigurasi Redis untuk session
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'auth_service_'
app.config['SESSION_REDIS'] = Redis(host='redis', port=6379)

# Inisialisasi session
server_session = Session(app)

def log_activity(username, status, ip_address):
    # Ambil zona waktu dari environment variable atau gunakan default
    timezone = os.getenv("TIMEZONE", "Asia/Makassar")  # Default ke Asia/Makassar jika tidak ada
    local_timezone = ZoneInfo(timezone)  # Menggunakan ZoneInfo

    # Membuat log aktivitas dengan timestamp yang sesuai dengan zona waktu lokal
    log = {
        "username": username,
        "status": status,
        "ip_address": ip_address,
        "timestamp": datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S")
    }

    # Simpan log ke dalam koleksi login_logs
    db.login_logs.insert_one(log)

# Rute untuk menampilkan halaman login
@app.route('/')
def index():
    return render_template('pages/login.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    
    print(f"Received username: {username}")
    user = user_collection.find_one({"username": username})
    if user:
        print(f"User found: {user}")
    else:
        print("User not found.")

    if user and check_password_hash(user['password'], password):
        session['user_id'] = str(user['_id'])
        session['username'] = str(user['username'])
        session['nama'] = str(user['nama'])
        session['role'] = str(user['role'])
        session['jurusan_id'] = user.get('jurusan_id')
        session['kelas_id'] = user.get('kelas_id')

        print("Login successful, session created:")
        print(session)
        
        # Log aktivitas login
        log_activity(username, 'success', request.remote_addr)

        print("Session contents before redirect:", dict(session))

        response = make_response(redirect(HELLO_SERVICE_URL))
        response.set_cookie('session', samesite='Lax', secure=False)
        return response
    else:
        error = "NISN/NIPN atau password salah"
        print(f"Login failed: {error}")
        return render_template('pages/login.html', error=error)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)

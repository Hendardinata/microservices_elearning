# from flask import Flask, request, redirect, render_template, session, make_response
# from flask_cors import CORS
# from flask_session import Session
# from werkzeug.security import check_password_hash
# from pymongo import MongoClient
# import os
# from zoneinfo import ZoneInfo
# from redis import Redis
# from dotenv import load_dotenv
# from datetime import datetime

# # Load environment variables
# load_dotenv()

# # Inisialisasi aplikasi Flask
# app = Flask(__name__, template_folder='argon-dashboard/templates', static_folder='argon-dashboard/assets')

# # Mengatur Random Secret Key
# app.secret_key = 'your-consistent-secret-key'

# # Mengatur CORS (Cross-Origin Resource Sharing)
# CORS(app, supports_credentials=True)  # Mengatur agar cookies dapat dikirim lintas domain

# HELLO_SERVICE_URL = os.getenv('HELLO_SERVICE_URL')

# # Koneksi ke MongoDB
# mongo_uri = os.getenv('MONGO_URI')
# mongo_db_name = os.getenv('MONGO_DB_NAME')
# client = MongoClient(mongo_uri)
# db = client[mongo_db_name]
# user_collection = db["users"]

# # Konfigurasi Redis untuk session
# app.config['SESSION_TYPE'] = 'redis'
# app.config['SESSION_PERMANENT'] = False
# app.config['SESSION_USE_SIGNER'] = True
# app.config['SESSION_KEY_PREFIX'] = 'auth_service_'
# app.config['SESSION_REDIS'] = Redis(host='redis', port=6379)

# # Inisialisasi session
# server_session = Session(app)

# def log_activity(username, status, ip_address):
#     # Ambil zona waktu dari environment variable atau gunakan default
#     timezone = os.getenv("TIMEZONE", "Asia/Makassar")  # Default ke Asia/Makassar jika tidak ada
#     local_timezone = ZoneInfo(timezone)  # Menggunakan ZoneInfo

#     # Membuat log aktivitas dengan timestamp yang sesuai dengan zona waktu lokal
#     log = {
#         "username": username,
#         "status": status,
#         "ip_address": ip_address,
#         "timestamp": datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S")
#     }

#     # Simpan log ke dalam koleksi login_logs
#     db.login_logs.insert_one(log)

# # Rute untuk menampilkan halaman login
# @app.route('/')
# def index():
#     return render_template('pages/login.html')

# @app.route('/login', methods=['POST'])
# def login():
#     username = request.form['username']
#     password = request.form['password']
    
#     print(f"Received username: {username}")
#     user = user_collection.find_one({"username": username})
#     if user:
#         print(f"User found: {user}")
#     else:
#         print("User not found.")

#     if user and check_password_hash(user['password'], password):
#         session['user_id'] = str(user['_id'])
#         session['username'] = str(user['username'])
#         session['nama'] = str(user['nama'])
#         session['role'] = str(user['role'])
#         session['jurusan_id'] = user.get('jurusan_id')
#         session['kelas_id'] = user.get('kelas_id')

#         print("Login successful, session created:")
#         print(session)
        
#         # Log aktivitas login
#         log_activity(username, 'success', request.remote_addr)

#         print("Session contents before redirect:", dict(session))

#         response = make_response(redirect(HELLO_SERVICE_URL))
#         response.set_cookie('session', samesite='Lax', secure=False)
#         return response
#     else:
#         error = "NISN/NIPN atau password salah"
#         print(f"Login failed: {error}")
#         return render_template('pages/login.html', error=error)


# if __name__ == '__main__':
#     app.run(host='0.0.0.0', port=8000, debug=True)


from flask import Flask, request, jsonify, render_template, redirect, make_response
from flask_cors import CORS
from pymongo import MongoClient
from werkzeug.security import check_password_hash
from dotenv import load_dotenv
import os
import jwt
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlencode

# Load environment variables dari .env
load_dotenv()

app = Flask(__name__, template_folder='argon-dashboard/templates', static_folder='argon-dashboard/assets')

# Enable CORS, support credentials jika butuh cookie (JWT biasanya di header, jadi ini optional)
CORS(app, supports_credentials=True)

# Konfigurasi MongoDB
mongo_uri = os.getenv('MONGO_URI')
mongo_db_name = os.getenv('MONGO_DB_NAME')
client = MongoClient(mongo_uri)
db = client[mongo_db_name]
user_collection = db["users"]

# JWT Secret Key dan Expiry dari environment variable
HELLO_SERVICE_URL = os.getenv('HELLO_SERVICE_URL')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'mysecretjwtkey')  # Ganti di .env
JWT_ALGORITHM = 'HS256'
JWT_EXP_DELTA_SECONDS = 3600  # Token berlaku 1 jam

# Zona waktu untuk log aktivitas
TIMEZONE = os.getenv("TIMEZONE", "Asia/Makassar")
local_timezone = ZoneInfo(TIMEZONE)

def log_activity(username, status, ip_address):
    log = {
        "username": username,
        "status": status,
        "ip_address": ip_address,
        "timestamp": datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S")
    }
    db.login_logs.insert_one(log)

@app.route('/')
def index():
    # Halaman login jika mau menggunakan form berbasis web
    return render_template('pages/login.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.json if request.is_json else request.form
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'message': 'Username dan password wajib diisi'}), 400

    user = user_collection.find_one({"username": username})
    if not user:
        log_activity(username, 'failed - user not found', request.remote_addr)
        return jsonify({'message': 'Username atau password salah'}), 401

    if not check_password_hash(user['password'], password):
        log_activity(username, 'failed - wrong password', request.remote_addr)
        return jsonify({'message': 'Username atau password salah'}), 401

    # Payload token JWT
    payload = {
        'user_id': str(user['_id']),
        'username': user['username'],
        'role': user.get('role', 'user'),
        'jurusan_id': user.get('jurusan_id'),
        'kelas_id': user.get('kelas_id'),
        'exp': datetime.utcnow() + timedelta(seconds=JWT_EXP_DELTA_SECONDS)
    }

    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    log_activity(username, 'success', request.remote_addr)

    # Buat response redirect
    resp = make_response(redirect(HELLO_SERVICE_URL))

    # Simpan token ke dalam cookie (HTTP-only biar aman)
    resp.set_cookie(
        'token', token,
        httponly=True,
        max_age=JWT_EXP_DELTA_SECONDS,
        samesite='Lax'  # atau 'Strict' untuk keamanan ekstra
    )

    return resp

@app.route('/protected', methods=['GET'])
def protected():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({'message': 'Authorization header missing'}), 401

    try:
        token = auth_header.split(" ")[1]  # Expect Bearer <token>
        decoded = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except (IndexError, jwt.ExpiredSignatureError, jwt.InvalidTokenError) as e:
        return jsonify({'message': f'Token tidak valid: {str(e)}'}), 401

    return jsonify({
        'message': 'Akses diterima',
        'user': {
            'user_id': decoded['user_id'],
            'username': decoded['username'],
            'role': decoded['role']
        }
    }), 200
    
    
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    user = user_collection.find_one({"username": username})
    if not user or not check_password_hash(user['password'], password):
        return jsonify({'message': 'Invalid credentials'}), 401

    payload = {
        'user_id': str(user['_id']),
        'username': user['username'],
        'role': user.get('role', 'user'),
        'exp': datetime.utcnow() + timedelta(seconds=JWT_EXP_DELTA_SECONDS)
    }

    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return jsonify({'token': token})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5006, debug=True)

from flask import Flask, request, jsonify, render_template, redirect, url_for, send_file, abort
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import jwt
import requests
from functools import wraps
from redis import Redis
import re

load_dotenv()

app = Flask(__name__)

# Mengatur direktori template dan static
app.template_folder = 'argon-dashboard'
# app.static_folder = 'argon-dashboard/assets'
app = Flask(__name__, template_folder='argon-dashboard/templates', static_folder='argon-dashboard/assets')

# Mengambil konfigurasi dari file .env
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'mysecretjwtkey')
KELAS_SERVICE_URL = os.getenv('KELAS_SERVICE_URL')
JURUSAN_SERVICE_URL = os.getenv('JURUSAN_SERVICE_URL')

redis_client = Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, decode_responses=True)

# Fungsi untuk menambahkan header Authorization
def verify_jwt(token):
    if redis_client.get(token) == "blacklisted":
        print("Token is blacklisted")
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        print("Token expired")
        return None
    except jwt.InvalidTokenError:
        print("Invalid token")
        return None
    
def jwt_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        else:
            return jsonify({'error': 'Unauthorized, token not found'}), 401

        user = verify_jwt(token)
        if not user:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        request.user = user
        return f(*args, **kwargs)
    return decorated_function

# Middleware untuk memeriksa token
@app.before_request
def check_token():
    if request.path.startswith('/static/uploads/users/'):
        return

    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
    else:
        abort(401)

    user = verify_jwt(token)
    if not user:
        abort(401)

    request.user = user


# Membuat koneksi ke MongoDB
mongo_uri = os.getenv('MONGO_URI')
mongo_db_name = os.getenv('MONGO_DB_NAME')
client = MongoClient(mongo_uri)
db = client[mongo_db_name]

# app.config['UPLOAD_FOLDER'] = 'static/uploads/users'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

ROLES = ["admin", "guru", "siswa"]

def is_unique(field, value):
    if db.users.find_one({field: value}):
        return False
    return True

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_password(password):
    return len(password) >= 8


@app.route('/users/insert', methods=['POST'])
def insert_users():
    foto = request.files.get('foto')
    
    # Validasi dan pemrosesan file foto
    if foto and foto.filename != '':
        if allowed_file(foto.filename):
            filename = secure_filename(foto.filename)
            file_path = os.path.join('static/uploads/users', filename)
            foto.save(file_path)
        else:
            return jsonify({'message': 'Invalid file type!'}), 400
    else:
        return jsonify({'message': 'No valid file uploaded!'}), 400

    # Ambil data dari form
    username = request.form.get('username')
    nama = request.form.get('nama')
    email = request.form.get('email')
    role = request.form.get('role')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    alamat = request.form.get('alamat')
    kota = request.form.get('kota')
    negara = request.form.get('negara')
    postal = request.form.get('postal')
    phone = request.form.get('phone')
    kelas_id = request.form.get('kelas_id')
    deskripsi_kelas = request.form.get('deskripsi_kelas')
    jurusan_id = request.form.get('jurusan_id')
    
    # Validasi input
    if not username or not nama or not email or not role or not password or not phone:
        return jsonify({'message': 'All required fields must be filled!'}), 400
    
    if role not in ROLES:
        return jsonify({'message': 'Invalid role!'}), 400
    
    if not is_unique('username', username):
        return jsonify({'message': 'Username already exists!'}), 400
    
    if not is_unique('email', email):
        return jsonify({'message': 'Email already exists!'}), 400
    
    if not is_unique('phone', phone):
        return jsonify({'message': 'Phone number already exists!'}), 400
    
    if not validate_password(password):
        return jsonify({'message': 'Password must be at least 8 characters long!'}), 400
    
    if password != confirm_password:
        return jsonify({'message': 'Passwords do not match!'}), 400

    # Verifikasi kelas jika kelas_id diisi
    if kelas_id:
        try:
            kelas_response = requests.get(f'{KELAS_SERVICE_URL}/{kelas_id}', headers={'Authorization': request.headers.get('Authorization')})
            if kelas_response.status_code != 200:
                return jsonify({'message': 'Kelas tidak ditemukan!'}), 404
            kelas_data = kelas_response.json()
        except requests.exceptions.RequestException as e:
            print("Error verifying kelas:", str(e))
            return jsonify({'message': str(e)}), 500
    else:
        kelas_data = None

    # Verifikasi jurusan jika jurusan_id diisi
    if jurusan_id:
        try:
            jurusan_response = requests.get(f'{JURUSAN_SERVICE_URL}/{jurusan_id}', headers={'Authorization': request.headers.get('Authorization')})
            if jurusan_response.status_code != 200:
                return jsonify({'message': 'Jurusan tidak ditemukan!'}), 404
            jurusan_data = jurusan_response.json()
        except requests.exceptions.RequestException as e:
            print("Error verifying jurusan:", str(e))
            return jsonify({'message': str(e)}), 500
    else:
        jurusan_data = None
    
    # Hash the password before saving to the database
    hashed_password = generate_password_hash(password)
    
    # Membuat dictionary user
    user = {
        'username': username,
        'nama':nama,
        'email': email,
        'role': role,
        'password': hashed_password,
        'alamat': alamat,
        'kota': kota,
        'negara': negara,
        'postal': postal,
        'phone': phone,
        'kelas_id': kelas_id if kelas_id else None,
        'deskripsi_kelas': deskripsi_kelas if deskripsi_kelas else None,
        'jurusan_id': jurusan_id if jurusan_id else None,
        'foto': file_path  # Menyimpan path foto setelah file diproses
    }
    
    # Insert the user into the database
    result = db.users.insert_one(user)
    user['_id'] = str(result.inserted_id)
    del user['password']  # Jangan kembalikan password dalam response
    
    return jsonify(user), 201

#Function Buat Menampilkan Seluruh User

@app.route('/users', methods=['GET'])
def get_users():
    users = list(db.users.find())
    for user in users:
        user['_id'] = str(user['_id'])
    return jsonify(users)

@app.route('/static/uploads/users/<path:filename>')
def get_user_foto(filename):
    try:
        file_path = os.path.join('static/uploads/users', filename)
        
        # Periksa apakah file ada
        if not os.path.exists(file_path):
            return jsonify({'message': 'File tidak ditemukan!'}), 404

        # Mengembalikan file sebagai respons
        return send_file(file_path)
    except Exception as e:
        # Menangani kesalahan server
        return jsonify({'message': 'Terjadi kesalahan pada server.', 'error': str(e)}), 500
    
@app.route('/users/update/<user_id>', methods=['POST'])
def update_users(user_id):
    # Cari user berdasarkan ID
    user = db.users.find_one({"_id": ObjectId(user_id)})  # Pastikan ini menggunakan 'db.users'
    if not user:
        return jsonify({"message": "User tidak ditemukan."}), 404

    # Ambil data dari form
    username = request.form.get('username')
    nama = request.form.get('nama')
    email = request.form.get('email')
    role = request.form.get('role')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    alamat = request.form.get('alamat')
    kota = request.form.get('kota')
    negara = request.form.get('negara')
    postal = request.form.get('postal')
    phone = request.form.get('phone')
    kelas_id = request.form.get('kelas_id')
    jurusan_id = request.form.get('jurusan_id')

    # Validasi dan pemrosesan file foto
    foto = request.files.get('foto')
    if foto and foto.filename != '':
        if allowed_file(foto.filename):
            filename = secure_filename(foto.filename)
            file_path = os.path.join('static/uploads/users', filename)
            foto.save(file_path)
            user['foto'] = file_path
        else:
            return jsonify({'message': 'Invalid file type!'}), 400

    # Validasi input
    if not username or not nama or not email or not role or not phone:
        return jsonify({'message': 'All required fields must be filled!'}), 400

    if role not in ROLES:
        return jsonify({'message': 'Invalid role!'}), 400

    if password:
        if not validate_password(password):
            return jsonify({'message': 'Password must be at least 8 characters long!'}), 400
        if password != confirm_password:
            return jsonify({'message': 'Passwords do not match!'}), 400
        user['password'] = generate_password_hash(password)

    # Update fields in the user document
    user.update({
        'username': username,
        'nama':nama,
        'email': email,
        'role': role,
        'alamat': alamat,
        'kota': kota,
        'negara': negara,
        'postal': postal,
        'phone': phone,
        'kelas_id': kelas_id,
        'jurusan_id': jurusan_id
    })

    # Simpan perubahan ke database
    db.users.update_one({"_id": ObjectId(user_id)}, {"$set": user})
    user['_id'] = str(user['_id'])

    return jsonify({"message": "User berhasil diperbarui."}), 200

@app.route('/users/<string:user_id>', methods=['GET'])
def get_users_by_id(user_id):
    try:
        user = db.users.find_one({'_id': ObjectId(user_id)})
        if user:
            user['_id'] = str(user['_id'])
            return jsonify(user)
        else:
            return jsonify({'message': 'User not found'}), 404
    except Exception as e:
        return jsonify({'message': str(e)}), 400
    
@app.route('/users/delete/<string:user_id>', methods=['DELETE'])
def delete_user(user_id):
    try:
        # Cari user berdasarkan ID
        user = db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify({"message": "User tidak ditemukan."}), 404
        
        # Hapus foto jika ada
        if 'foto' in user:
            file_path = user['foto']
            if os.path.exists(file_path):
                os.remove(file_path)

        # Hapus user dari database
        db.users.delete_one({"_id": ObjectId(user_id)})
        
        return jsonify({"message": "User berhasil dihapus."}), 200
    except Exception as e:
        return jsonify({'message': 'Terjadi kesalahan pada server.', 'error': str(e)}), 500
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

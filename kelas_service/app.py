from flask import Flask, request, jsonify, render_template, redirect, flash, abort
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv
import os
import requests
import jwt
from functools import wraps
from redis import Redis

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# Mengambil konfigurasi dari file .env
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'mysecretjwtkey')
mongo_uri = os.getenv('MONGO_URI')
mongo_db_name = os.getenv('MONGO_DB_NAME')
jurusan_service_url = os.getenv('JURUSAN_SERVICE_URL')

# Mengatur direktori template dan static
app.template_folder = 'argon-dashboard'
# app.static_folder = 'argon-dashboard/assets'
app = Flask(__name__, template_folder='argon-dashboard/templates', static_folder='argon-dashboard/assets')

redis_client = Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, decode_responses=True)

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

# Membuat koneksi ke MongoDB
client = MongoClient(mongo_uri)
db = client[mongo_db_name]

@app.route('/kelas', methods=['GET'])
def get_kelas():
    jurusan_id = request.args.get('jurusan_id')
    query = {}
    if jurusan_id:
        query['jurusan_id'] = jurusan_id
    kelas = list(db.kelas.find(query))
    for k in kelas:
        k['_id'] = str(k['_id'])
    return jsonify(kelas)

@app.route('/kelas/<string:kelas_id>', methods=['GET'])
def get_kelas_by_id(kelas_id):
    try:
        kelas = db.kelas.find_one({'_id': ObjectId(kelas_id)})
        if kelas:
            kelas['_id'] = str(kelas['_id'])
            return jsonify(kelas)
        else:
            return jsonify({'message': 'Kelas not found'}), 404
    except Exception as e:
        return jsonify({'message': str(e)}), 400

@app.route('/create', methods=['GET'])
def create():
    try:
        response = requests.get(f'{jurusan_service_url}/jurusan')
        response.raise_for_status()
        jurusan_list = response.json()
        return render_template('pages/create.html', jurusan_list=jurusan_list)
    except requests.exceptions.RequestException as e:
        return jsonify({'message': str(e)}), 500

@app.route('/kelas/insert', methods=['POST'])
def insert_kelas():
    data = request.json
    nama_kelas = data.get('nama_kelas')
    deskripsi_kelas = data.get('deskripsi_kelas')  # Single description text

    if not nama_kelas or not deskripsi_kelas:
        return jsonify({'message': 'Nama kelas dan deskripsi kelas harus diisi!'}), 400
    
    # Cek apakah nama kelas sudah ada
    existing_kelas = db.kelas.find_one({'nama_kelas': nama_kelas})
    
    if existing_kelas:
        # Jika kelas sudah ada, cek apakah deskripsi sudah ada dalam list
        if deskripsi_kelas in existing_kelas['deskripsi_kelas']:
            return jsonify({'message': 'Deskripsi kelas sudah ada dalam list.'}), 400
        try:
            # Tambahkan deskripsi baru ke list yang ada
            db.kelas.update_one(
                {'nama_kelas': nama_kelas},
                {'$push': {'deskripsi_kelas': deskripsi_kelas}}
            )
            return jsonify({'message': 'Deskripsi kelas berhasil ditambahkan.'}), 200
        except Exception as e:
            return jsonify({'message': str(e)}), 500
    else:
        # Jika kelas belum ada, buat entri baru
        kelas = {
            'nama_kelas': nama_kelas,
            'deskripsi_kelas': [deskripsi_kelas]  # Inisialisasi dengan list
        }
        try:
            result = db.kelas.insert_one(kelas)
            kelas['_id'] = str(result.inserted_id)
            return jsonify({'message': 'Kelas berhasil ditambahkan.'}), 201
        except Exception as e:
            return jsonify({'message': str(e)}), 500

@app.route('/kelas/update/<string:kelas_id>', methods=['PUT'])
def update_kelas(kelas_id):
    data = request.get_json()
    nama_kelas = data.get('nama_kelas')
    deskripsi_kelas = data.get('deskripsi_kelas')
    
    if not nama_kelas or not deskripsi_kelas:
        return jsonify({'message': 'Nama kelas dan deskripsi kelas harus diisi!'}), 400
    
    result = db.kelas.update_one({'_id': ObjectId(kelas_id)}, {'$set': {
        'nama_kelas': nama_kelas,
        'deskripsi_kelas': deskripsi_kelas
    }})
    
    if result.matched_count == 0:
        return jsonify({'message': 'Kelas tidak ditemukan!'}), 404
    
    kelas = db.kelas.find_one({'_id': ObjectId(kelas_id)})
    kelas['_id'] = str(kelas['_id'])
    
    return jsonify(kelas)

@app.route('/kelas/delete/<string:kelas_id>', methods=['DELETE'])
def delete_kelas(kelas_id):
    result = db.kelas.delete_one({'_id': ObjectId(kelas_id)})
    if result.deleted_count == 0:
        return jsonify({'message': 'Kelas tidak ditemukan'}), 404
    return '', 204

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)

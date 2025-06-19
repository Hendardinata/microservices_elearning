from flask import Flask, request, jsonify, render_template, abort, Response
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv
from flask_cors import CORS
import os
import jwt
from functools import wraps
from redis import Redis
from prometheus_flask_exporter import PrometheusMetrics
import prometheus_client

load_dotenv()

app = Flask(__name__)
metrics = PrometheusMetrics(app)
CORS(app)

# Mengambil konfigurasi dari file .env
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'mysecretjwtkey')
mongo_uri = os.getenv('MONGO_URI')
mongo_db_name = os.getenv('MONGO_DB_NAME')

redis_client = Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, decode_responses=True)

# API Token
# API_TOKEN = os.getenv('API_TOKEN')

# # Middleware untuk memeriksa token
# @app.before_request
# def check_token():
#     token = request.headers.get('Authorization')
#     if token != API_TOKEN:
#         abort(403)  # Forbidden

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

@app.route('/jurusan', methods=['GET'])
@jwt_required
def get_jurusan():
    jurusan = list(db.jurusan.find())
    for j in jurusan:
        j['_id'] = str(j['_id'])
    return jsonify(jurusan)

@app.route('/jurusan/<string:jurusan_id>', methods=['GET'])
def get_jurusan_by_id(jurusan_id):
    try:
        jurusan = db.jurusan.find_one({'_id': ObjectId(jurusan_id)})
        if jurusan:
            jurusan['_id'] = str(jurusan['_id'])
            return jsonify(jurusan)
        else:
            return jsonify({'message': 'Jurusan not found'}), 404
    except Exception as e:
        return jsonify({'message': str(e)}), 400

@app.route('/create', methods=['GET'])
def create():
    return render_template('pages/create.html')

@app.route('/jurusan/insert', methods=['POST'])
def insert_jurusan():
    data = request.get_json()
    print("Received data:", data)  # Debugging

    nama_jurusan = data.get('nama_jurusan')
    deskripsi_jurusan = data.get('deskripsi_jurusan')
    akreditasi_jurusan = data.get('akreditasi_jurusan')
    
    if not nama_jurusan or not deskripsi_jurusan or not akreditasi_jurusan:
        return jsonify({'message': 'Nama jurusan, deskripsi jurusan, dan akreditasi jurusan harus diisi!'}), 400
    
    jurusan = {
        'nama_jurusan': nama_jurusan,
        'deskripsi_jurusan': deskripsi_jurusan,
        'akreditasi_jurusan': akreditasi_jurusan
    }
    
    try:
        result = db.jurusan.insert_one(jurusan)
        jurusan['_id'] = str(result.inserted_id)
        return jsonify({'message': 'Jurusan berhasil ditambahkan.'}), 201
    except Exception as e:
        print("Error:", str(e))  # Debugging
        return jsonify({'message': 'Terjadi kesalahan pada server.'}), 500

@app.route('/jurusan/update/<string:jurusan_id>', methods=['PUT'])
def update_jurusan(jurusan_id):
    data = request.get_json()
    nama_jurusan = data.get('nama_jurusan')
    deskripsi_jurusan = data.get('deskripsi_jurusan')
    akreditasi_jurusan = data.get('akreditasi_jurusan')
    
    if not nama_jurusan or not deskripsi_jurusan or not akreditasi_jurusan:
        return jsonify({'message': 'Nama jurusan, deskripsi jurusan, dan akreditasi jurusan harus diisi!'}), 400
    
    result = db.jurusan.update_one({'_id': ObjectId(jurusan_id)}, {'$set': {
        'nama_jurusan': nama_jurusan,
        'deskripsi_jurusan': deskripsi_jurusan,
        'akreditasi_jurusan': akreditasi_jurusan
    }})
    
    if result.matched_count == 0:
        return jsonify({'message': 'Jurusan tidak ditemukan!'}), 404
    
    jurusan = db.jurusan.find_one({'_id': ObjectId(jurusan_id)})
    jurusan['_id'] = str(jurusan['_id'])
    
    return jsonify(jurusan)

@app.route('/jurusan/delete/<string:jurusan_id>', methods=['DELETE'])
def delete_jurusan(jurusan_id):
    result = db.jurusan.delete_one({'_id': ObjectId(jurusan_id)})
    if result.deleted_count == 0:
        return jsonify({'message': 'Jurusan tidak ditemukan'}), 404
    return '', 204

# Fallback jika metrics bawaan tidak muncul
@app.route('/metrics')
def metrics_manual():
    return Response(prometheus_client.generate_latest(), mimetype=prometheus_client.CONTENT_TYPE_LATEST)

if __name__ == '__main__':
    print("ROUTE YANG TERDAFTAR:")
    print(app.url_map)
    app.run(host='0.0.0.0', port=5004, debug=True)

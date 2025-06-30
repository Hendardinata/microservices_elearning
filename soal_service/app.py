from flask import Flask, request, jsonify, render_template, abort, Response
from flask_cors import CORS
from pymongo import MongoClient
from dotenv import load_dotenv
from bson import ObjectId
from bson.errors import InvalidId
import requests
import os
from functools import wraps
from redis import Redis
import jwt
from prometheus_flask_exporter import PrometheusMetrics
import prometheus_client

load_dotenv()

app = Flask(__name__)
metrics = PrometheusMetrics(app)
CORS(app)

# Mengambil konfigurasi dari file .env
USER_SERVICE_URL = os.getenv('USER_SERVICE_URL')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')

# Konfigurasi MongoDB
mongo_uri = os.getenv('MONGO_URI')
mongo_db_name = os.getenv('MONGO_DB_NAME')
client = MongoClient(mongo_uri)
db = client[mongo_db_name]
soal_collection = db["soal"]
jawaban_collection = db["jawaban"]

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

@app.route('/create', methods=['POST'])
def create():
    data = request.json
    user_id = data.get('user_id')  # Ambil user_id dari data yang dikirim
    
    # Ambil data soal sebagai array
    soal_list = data.get('soal')
    if not isinstance(soal_list, list):
        return jsonify({"message": "Invalid data format"}), 400

    # Persiapkan data untuk disimpan
    processed_data = {}
    for index, soal in enumerate(soal_list):
        key = f"question_{index+1}"
        processed_data[key] = soal

    # Tambahkan data kelas, jurusan, materi, dan user_id ke processed_data
    processed_data['kelas_id'] = data.get('kelas_id')
    processed_data['jurusan_id'] = data.get('jurusan_id')
    processed_data['materi_id'] = data.get('materi_id')
    processed_data['user_id'] = user_id  # Tambahkan user_id
    
    try:
        soal_collection.insert_one(processed_data)
        return jsonify({"message": "Soal created successfully"}), 201
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@app.route('/update/<soal_id>', methods=['PUT'])
def update(soal_id):
    data = request.json
    print("Received data:", data)  # Debugging untuk melihat request

    # Validasi panjang soal_id sebelum dikonversi ke ObjectId
    if len(soal_id) != 24:
        return jsonify({"error": "Invalid soal_id format. Must be 24-character hexadecimal"}), 400

    try:
        soal_id = ObjectId(soal_id)  # Konversi ID ke ObjectId MongoDB
    except Exception:
        return jsonify({"error": "Invalid soal_id format"}), 400

    # Pastikan data soal dikirim dalam format list
    if 'soal' not in data or not isinstance(data['soal'], dict):
        return jsonify({"message": "Invalid data format, 'soal' harus berupa dictionary"}), 400

    # Pastikan kelas_id, jurusan_id, materi_id ada
    if not all(key in data for key in ['kelas_id', 'jurusan_id', 'materi_id']):
        return jsonify({"message": "kelas_id, jurusan_id, dan materi_id wajib ada"}), 400

    # Proses data soal menjadi format yang sesuai
    updated_data = data['soal']
    updated_data['kelas_id'] = data.get('kelas_id')
    updated_data['jurusan_id'] = data.get('jurusan_id')
    updated_data['materi_id'] = data.get('materi_id')

    # Jika ada user_id, tambahkan juga
    if 'user_id' in data:
        updated_data['user_id'] = data['user_id']

    try:
        existing_data = soal_collection.find_one({"_id": soal_id})
        if not existing_data:
            return jsonify({"message": "Soal not found"}), 404

        soal_collection.update_one({"_id": soal_id}, {"$set": updated_data})
        return jsonify({"message": "Soal updated successfully"}), 200

    except Exception as e:
        print(f"Error updating soal: {e}")  # Debugging
        return jsonify({"message": str(e)}), 500

@app.route('/soal', methods=['GET'])
def get_all_soals():
    try:
        # Debugging log untuk memeriksa apakah endpoint dipanggil
        print("Endpoint /soal dipanggil")

        # Ambil semua soal dari database
        soals = list(soal_collection.find())

        # Konversi ObjectId menjadi string
        for soal in soals:
            soal['_id'] = str(soal['_id'])

        print(f"Found soals: {soals}")  # Debugging log

        return jsonify(soals), 200
    except Exception as e:
        print(f"Error occurred: {str(e)}")  # Cetak pesan kesalahan
        return jsonify({"error": str(e)}), 500

@app.route('/soal/<soal_id>', methods=['GET'])
def get_soal_by_id(soal_id):
    try:
        # Cari soal berdasarkan ID
        soal = soal_collection.find_one({"_id": ObjectId(soal_id)})
        if not soal:
            return jsonify({"message": "Soal tidak ditemukan"}), 404

        # Konversi ObjectId menjadi string
        soal['_id'] = str(soal['_id'])
        return jsonify(soal), 200
    except Exception as e:
        print(f"Error occurred: {str(e)}")  # Cetak pesan kesalahan
        return jsonify({"error": str(e)}), 500

@app.route('/cek-jawaban/<soal_id>/<user_id>', methods=['GET'])
def cek_jawaban(soal_id, user_id):
    jawaban = jawaban_collection.find_one({"soal_id": soal_id, "user_id": user_id})
    already_answered = bool(jawaban)
    return jsonify({"already_answered": already_answered}), 200


@app.route('/jawaban', methods=['POST'])
def submit_jawaban():
    data = request.json
    jawaban_collection.insert_one(data)
    return jsonify({"message": "Jawaban submitted successfully"}), 201


# KODE BARU DITAMBAH
@app.route('/jawaban/<soal_id>', methods=['GET'])
def get_jawaban_by_soal_id(soal_id):
    try:
        # Ambil token dari header permintaan
        auth_header = request.headers.get('Authorization')
        headers = {'Authorization': auth_header} if auth_header else {}

        # Cari jawaban berdasarkan soal_id
        jawabans = list(jawaban_collection.find({"soal_id": soal_id}))

        # Cari soal berdasarkan soal_id
        soal = soal_collection.find_one({"_id": ObjectId(soal_id)})
        if not soal:
            return jsonify({"error": "Soal tidak ditemukan."}), 404

        for jawaban in jawabans:
            jawaban['_id'] = str(jawaban['_id'])

            user_response = requests.get(f"{USER_SERVICE_URL}/{jawaban['user_id']}", headers=headers)
            user_response.raise_for_status()
            user = user_response.json()

            jawaban['nama'] = user.get('nama', 'User tidak ditemukan')
            jawaban['username'] = user.get('username', 'Username tidak ditemukan')

        soal['_id'] = str(soal['_id'])
        return jsonify({"jawabans": jawabans, "soal": soal}), 200

    except requests.exceptions.RequestException as e:
        print(f"Error occurred: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/jawaban', methods=['GET'])
def get_jawaban_by_user_id():
    user_id = request.args.get('user_id')
    jawabans = list(jawaban_collection.find({"user_id": user_id}))
    for jawaban in jawabans:
        jawaban['_id'] = str(jawaban['_id'])
    return jsonify(jawabans), 200


@app.route('/koreksi-jawaban/<jawaban_id>', methods=['POST'])
def koreksi_jawaban(jawaban_id):

    data = request.json
    try:
        # Cari jawaban berdasarkan ID
        jawaban = jawaban_collection.find_one({"_id": ObjectId(jawaban_id)})
        if not jawaban:
            return jsonify({"message": "Jawaban tidak ditemukan"}), 404

        # Update jawaban dengan nilai dan feedback
        jawaban_collection.update_one(
            {"_id": ObjectId(jawaban_id)},
            {"$set": {"nilai": data.get("nilai"), "feedback": data.get("feedback")}}
        )

        return jsonify({"message": "Koreksi berhasil disimpan."}), 200
    except Exception as e:
        print(f"Error occurred: {str(e)}")  # Cetak pesan kesalahan
        return jsonify({"error": str(e)}), 500
    
@app.route('/soal/<soal_id>', methods=['DELETE'])
def delete_soal(soal_id):
    try:
        # Cari soal berdasarkan ID
        soal = soal_collection.find_one({"_id": ObjectId(soal_id)})
        if not soal:
            return jsonify({"message": "Soal tidak ditemukan"}), 404

        # Hapus soal dari database
        soal_collection.delete_one({"_id": ObjectId(soal_id)})

        # Hapus jawaban yang terkait dengan soal ini
        jawaban_collection.delete_many({"soal_id": soal_id})

        return jsonify({"message": "Soal berhasil dihapus."}), 200
    except Exception as e:
        print(f"Error occurred: {str(e)}")  # Cetak pesan kesalahan
        return jsonify({"error": str(e)}), 500
    
# Fallback jika metrics bawaan tidak muncul
@app.route('/metrics')
def metrics_manual():
    return Response(prometheus_client.generate_latest(), mimetype=prometheus_client.CONTENT_TYPE_LATEST)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005, debug=True)

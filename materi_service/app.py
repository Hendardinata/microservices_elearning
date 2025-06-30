from flask import Flask, request, jsonify, render_template, redirect,  send_from_directory, abort, Response
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import os
import jwt
import requests
import logging
from functools import wraps
from redis import Redis
from prometheus_flask_exporter import PrometheusMetrics
import prometheus_client

load_dotenv()

app = Flask(__name__)
metrics = PrometheusMetrics(app)

# Mengambil konfigurasi dari file .env
mongo_uri = os.getenv('MONGO_URI')
mongo_db_name = os.getenv('MONGO_DB_NAME')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
KELAS_SERVICE_URL = os.getenv('KELAS_SERVICE_URL')
JURUSAN_SERVICE_URL = os.getenv('JURUSAN_SERVICE_URL')

# API Token
API_TOKEN = os.getenv('API_TOKEN')

redis_client = Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, decode_responses=True)

# Fungsi untuk menambahkan header Authorization
# def get_headers():
#     return {
#         'Authorization': API_TOKEN
#     }

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
# @app.before_request
# def check_token():
#     token = request.headers.get('Authorization')
#     if token != API_TOKEN:
#         abort(403)  # Forbidden

# Membuat koneksi ke MongoDB
client = MongoClient(mongo_uri)
db = client[mongo_db_name]

# Definisikan path untuk folder upload
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads', 'pdf')


# Pastikan folder ada
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

ALLOWED_EXTENSIONS = {'pdf'}

# Cek apakah ekstensi file diizinkan
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Mengatur direktori template dan static
app.template_folder = 'argon-dashboard'
# app.static_folder = 'argon-dashboard/assets'
app = Flask(__name__, template_folder='argon-dashboard/templates', static_folder='argon-dashboard/assets')

@app.route('/materi', methods=['GET'])
def get_materi():
    kelas_id = request.args.get('kelas_id')
    query = {}
    if kelas_id:
        query['kelas_id'] = kelas_id
    materi = list(db.materi.find(query))
    for m in materi:
        m['_id'] = str(m['_id'])
    return jsonify(materi)

@app.route('/materi/<string:materi_id>', methods=['GET'])
def get_materi_by_id(materi_id):
    try:
        materi = db.materi.find_one({'_id': ObjectId(materi_id)})
        if materi:
            materi['_id'] = str(materi['_id'])
            return jsonify(materi)
        else:
            return jsonify({'message': 'Materi not found'}), 404
    except Exception as e:
        return jsonify({'message': str(e)}), 400

@app.route('/create', methods=['GET'])
def create():
    try:
        # Get data from kelas_service
        kelas_response = requests.get(f'{KELAS_SERVICE_URL}/kelas', headers={'Authorization': request.headers.get('Authorization')})
        kelas_response.raise_for_status()
        kelas_list = kelas_response.json()

        # Get data from jurusan_service
        jurusan_response = requests.get(f'{JURUSAN_SERVICE_URL}/jurusan', headers={'Authorization': request.headers.get('Authorization')})
        jurusan_response.raise_for_status()
        jurusan_list = jurusan_response.json()

        return render_template('pages/create.html', kelas_list=kelas_list, jurusan_list=jurusan_list)
    except requests.exceptions.RequestException as e:
        return jsonify({'message': str(e)}), 500


@app.route('/materi/insert', methods=['POST'])
def insert_materi():
    
    # Logging untuk debug
    logging.debug(f'UPLOAD_FOLDER from config: {app.config.get("UPLOAD_FOLDER")}')
    
    data = request.form
    nama_materi = data.get('nama_materi')
    deskripsi_materi = data.get('deskripsi_materi')
    kelas_id = data.get('kelas_id')
    jurusan_id = data.get('jurusan_id')
    deskripsi_kelas = data.get('deskripsi_kelas')

    if not nama_materi or not deskripsi_materi or not kelas_id or not jurusan_id or not deskripsi_kelas:
        return jsonify({'message': 'Semua field harus diisi!'}), 400

    try:
        kelas_response = requests.get(f'{KELAS_SERVICE_URL}/kelas/{kelas_id}', headers={'Authorization': request.headers.get('Authorization')})
        if kelas_response.status_code != 200:
            return jsonify({'message': 'Kelas tidak ditemukan!'}), 404
        kelas_data = kelas_response.json()
    except requests.exceptions.RequestException as e:
        print("Error verifying kelas:", str(e))
        return jsonify({'message': str(e)}), 500

    try:
        jurusan_response = requests.get(f'{JURUSAN_SERVICE_URL}/jurusan/{jurusan_id}', headers={'Authorization': request.headers.get('Authorization')})
        if jurusan_response.status_code != 200:
            return jsonify({'message': 'Jurusan tidak ditemukan!'}), 404
    except requests.exceptions.RequestException as e:
        print("Error verifying jurusan:", str(e))
        return jsonify({'message': str(e)}), 500

    if deskripsi_kelas not in kelas_data['deskripsi_kelas']:
        return jsonify({'message': 'Deskripsi kelas tidak valid!'}), 400

    files = request.files.getlist('pdf_files')
    pdf_file_paths = []

    print("Received files:", files)

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join('static/uploads/pdf', filename)
            file.save(file_path)
            pdf_file_paths.append(file_path)
        else:
            print("Invalid file:", file)
            return jsonify({'message': 'File tidak valid!'}), 400

    materi = {
        'nama_materi': nama_materi,
        'deskripsi_materi': deskripsi_materi,
        'kelas_id': kelas_id,
        'deskripsi_kelas': deskripsi_kelas,
        'jurusan_id': jurusan_id,
        'pdf_files': pdf_file_paths
    }

    result = db.materi.insert_one(materi)
    materi['_id'] = str(result.inserted_id)

    return jsonify({"message": "Materi berhasil ditambahkan.", "materi": materi}), 201

@app.route('/check_upload_folder', methods=['GET'])
def check_upload_folder():
    return jsonify({'UPLOAD_FOLDER': app.config.get('UPLOAD_FOLDER')}), 200

@app.route('/materi/update/<materi_id>', methods=['POST'])
def update_materi(materi_id):
    data = request.form
    nama_materi = data.get('nama_materi')
    deskripsi_materi = data.get('deskripsi_materi')
    kelas_id = data.get('kelas_id')
    jurusan_id = data.get('jurusan_id')
    deskripsi_kelas = data.get('deskripsi_kelas')

    if not nama_materi or not deskripsi_materi or not kelas_id or not jurusan_id or not deskripsi_kelas:
        return jsonify({'message': 'Semua field harus diisi!'}), 400

    # Validasi kelas
    try:
        kelas_response = requests.get(f'{KELAS_SERVICE_URL}/kelas/{kelas_id}', headers={'Authorization': request.headers.get('Authorization')})
        if kelas_response.status_code != 200:
            return jsonify({'message': 'Kelas tidak ditemukan!'}), 404
        kelas_data = kelas_response.json()
    except requests.exceptions.RequestException as e:
        return jsonify({'message': str(e)}), 500

    # Validasi jurusan
    try:
        jurusan_response = requests.get(f'{JURUSAN_SERVICE_URL}/jurusan/{jurusan_id}', headers={'Authorization': request.headers.get('Authorization')})
        if jurusan_response.status_code != 200:
            return jsonify({'message': 'Jurusan tidak ditemukan!'}), 404
    except requests.exceptions.RequestException as e:
        return jsonify({'message': str(e)}), 500

    if deskripsi_kelas not in kelas_data['deskripsi_kelas']:
        return jsonify({'message': 'Deskripsi kelas tidak valid!'}), 400

    # Ambil file baru
    files = request.files.getlist('pdf_files')
    pdf_file_paths = []

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join('static/uploads/pdf', filename)
            file.save(file_path)
            pdf_file_paths.append(file_path)
        elif file.filename != '':
            return jsonify({'message': 'File tidak valid!'}), 400

    # Ambil data materi lama untuk menyimpan file lama
    existing_materi = db.materi.find_one({'_id': ObjectId(materi_id)})
    if not existing_materi:
        return jsonify({'message': 'Materi tidak ditemukan!'}), 404

    existing_files = existing_materi.get('pdf_files', [])
    combined_files = existing_files + pdf_file_paths if pdf_file_paths else existing_files

    # Buat data untuk diupdate
    update_data = {
        'nama_materi': nama_materi,
        'deskripsi_materi': deskripsi_materi,
        'kelas_id': kelas_id,
        'deskripsi_kelas': deskripsi_kelas,
        'jurusan_id': jurusan_id,
        'pdf_files': combined_files
    }

    result = db.materi.update_one({'_id': ObjectId(materi_id)}, {'$set': update_data})

    if result.matched_count == 0:
        return jsonify({'message': 'Materi tidak ditemukan!'}), 404

    return jsonify({"message": "Materi berhasil diperbarui."}), 200

# Route to serve PDF files
@app.route('/openpdf/pdf/<filename>')
def openpdf_file(filename):
    return send_from_directory('static/uploads/pdf', filename)

@app.route('/uploads/pdf/<filename>')
def uploaded_file(filename):
    # Path to the uploads folder
    uploads = os.path.join(app.root_path, 'static/uploads/pdf')
    
    # Ensure the file is safe to serve
    try:
        return send_from_directory(directory=uploads, path=filename, as_attachment=True)
    except FileNotFoundError:
        abort(404)

@app.route('/materi/delete/<m_id>', methods=['DELETE'])
def delete_materi(m_id):
    try:
        result = db.materi.delete_one({'_id': ObjectId(m_id)})
        if result.deleted_count == 1:
            return jsonify({'message': 'Materi berhasil dihapus.'}), 204
        else:
            return jsonify({'message': 'Materi tidak ditemukan.'}), 404
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    
# Fallback jika metrics bawaan tidak muncul
@app.route('/metrics')
def metrics_manual():
    return Response(prometheus_client.generate_latest(), mimetype=prometheus_client.CONTENT_TYPE_LATEST)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=True)

from flask import Flask, render_template, jsonify, redirect, request, url_for, Response, session
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from functools import wraps
from flask_cors import CORS
from dotenv import load_dotenv
from flask import make_response
from fpdf import FPDF
from flask_session import Session
import requests
import os
import jwt
from redis import Redis
from prometheus_flask_exporter import PrometheusMetrics
import prometheus_client

load_dotenv()

# Inisialisasi aplikasi Flask
app = Flask(__name__)
metrics = PrometheusMetrics(app)

# Mengatur direktori template dan static
app.template_folder = 'argon-dashboard'

# Mengatur app.static_folder 
app = Flask(__name__, template_folder='argon-dashboard/templates', static_folder='argon-dashboard/assets')

# Mengatur Random Secret Key
app.secret_key = 'your-consistent-secret-key'

# Mengatur CORS ( Cross )
CORS(app, supports_credentials=True)

# URL untuk ambil semua DATA.
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
AUTH_SERVICE_URL = os.getenv('AUTH_SERVICE_URL')
USER_SERVICE_URL = os.getenv('USER_SERVICE_URL')
KELAS_SERVICE_URL = os.getenv('KELAS_SERVICE_URL')
MATERI_SERVICE_URL = os.getenv('MATERI_SERVICE_URL')
JURUSAN_SERVICE_URL = os.getenv('JURUSAN_SERVICE_URL')
SOAL_SERVICE_URL = os.getenv('SOAL_SERVICE_URL')
MATERI_SERVICE_URL_PDF = os.getenv('MATERI_SERVICE_URL_PDF')
# API Token
API_TOKEN = os.getenv('API_TOKEN')

JWT_EXP_DELTA_SECONDS = 3600
redis_client = Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, decode_responses=True)

# Konfigurasi MongoDB
mongo_uri = os.getenv('MONGO_URI')
mongo_db_name = os.getenv('MONGO_DB_NAME')
client = MongoClient(mongo_uri)
db = client[mongo_db_name]
login_logs_collection = db["login_logs"]

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


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        token = None

        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        elif request.args.get('token'):
            token = request.args.get('token')
        else:
            # Ambil dari cookie
            token = request.cookies.get('token')

        if not token:
            return redirect(AUTH_SERVICE_URL)
        
        user_payload = verify_jwt(token)
        if not user_payload:
            return redirect(AUTH_SERVICE_URL)

        # Simpan payload user di context request, jika perlu
        request.user = user_payload
        request.user['token'] = token
        return f(*args, **kwargs)
    return decorated_function

# Rute untuk menampilkan index
@app.route('/')
@login_required
def index():
    try:
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        print(f"[DEBUG] Authorization headers: {headers}")

        # Ambil data semua pengguna
        print("[DEBUG] Mengirim request ke USER_SERVICE_URL...")
        user_response = requests.get(f"{USER_SERVICE_URL}", headers=headers)
        print(f"[DEBUG] Status code user_response: {user_response.status_code}")
        print(f"[DEBUG] Body user_response: {user_response.text}")

        if user_response.status_code == 200:
            all_users = user_response.json()
            print(f"[DEBUG] all_users length: {len(all_users)}")
            total_siswa = sum(1 for user in all_users if user.get('role') == 'siswa')
            total_guru = sum(1 for user in all_users if user.get('role') == 'guru')
            print(f"[DEBUG] total_siswa: {total_siswa}, total_guru: {total_guru}")
        else:
            total_siswa = 0
            total_guru = 0
            print("[DEBUG] Gagal mengambil data user, set total siswa dan guru = 0")

        # Ambil data total materi
        print("[DEBUG] Mengirim request ke MATERI_SERVICE_URL...")
        materi_response = requests.get(f"{MATERI_SERVICE_URL}", headers=headers)
        print(f"[DEBUG] Status code materi_response: {materi_response.status_code}")
        print(f"[DEBUG] Body materi_response: {materi_response.text}")
        
        total_materi = len(materi_response.json()) if materi_response.status_code == 200 else 0
        print(f"[DEBUG] total_materi: {total_materi}")

        # Ambil 10 log aktivitas login terbaru
        print("[DEBUG] Mengambil 10 login logs terbaru dari MongoDB...")
        login_logs = list(login_logs_collection.find().sort("timestamp", -1).limit(10))
        print(f"[DEBUG] Jumlah login_logs: {len(login_logs)}")

        # Cek apakah user memiliki role admin
        user_data = getattr(request, "user", None)
        is_admin = user_data.get("role") == "admin" if user_data else False
        print(f"[DEBUG] User role: {user_data.get('role') if user_data else 'None'}, is_admin: {is_admin}")

        return render_template(
            'pages/index.html',
            total_siswa=total_siswa,
            total_guru=total_guru,
            total_materi=total_materi,
            login_logs=login_logs,
            is_admin=is_admin,
            user=user_data 
        )
    except Exception as e:
        print(f"[ERROR] Error while loading dashboard: {e}")
        return render_template('pages/index.html', error_message="Error loading dashboard data.")


# Rute untuk Logout
@app.route('/logout')
@login_required
def logout():
    token = request.user.get('token')  # token dari context
    if token:
        # Simpan ke Redis blacklist dengan TTL sesuai waktu kedaluwarsa
        redis_client.setex(token, JWT_EXP_DELTA_SECONDS, 'blacklisted')
    
    response = make_response(redirect(AUTH_SERVICE_URL))
    # Hapus cookie token dengan meng-set cookie token kosong dan expired
    response.set_cookie('token', '', expires=0, httponly=True, samesite='Lax')
    return response # URL login dari auth_service

#-------------ROUTE UNTUK USER ----------------
#-----ROUTE UNTUK TAMBAH DATA USER------------

# Rute untuk Create User
@app.route('/create-user')
@login_required
def create_user():
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    # Get data from kelas_service
    headers = {'Authorization': f"Bearer {request.user['token']}"}
    
    kelas_response = requests.get(KELAS_SERVICE_URL, headers=headers)
    kelas_response.raise_for_status()
    kelas_list = kelas_response.json()

    # Get data from jurusan_service
    jurusan_response = requests.get(JURUSAN_SERVICE_URL, headers=headers)
    jurusan_response.raise_for_status()
    jurusan_list = jurusan_response.json()

    page_name = "User"
    return render_template('pages/create-user.html', kelas_list=kelas_list, jurusan_list=jurusan_list, page_name=page_name)

# Rute untuk Melakukan Deliveri ke user_service
@app.route('/proxy/user/insert', methods=['POST'])
@login_required
def proxy_insert_user():
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    data = request.form.to_dict(flat=True)
    foto = request.files.get('foto')
    
    if foto:
        files_payload = {'foto': (foto.filename, foto.read(), foto.content_type)}
    else:
        files_payload = {}
    
    try:
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        response = requests.post(f'{USER_SERVICE_URL}/insert', data=data, files=files_payload, headers=headers)
        if response.status_code == 201:
            return jsonify({"message": "User berhasil ditambahkan.", "redirect_url": url_for('users')}), 201
        else:
            return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"message": "Terjadi kesalahan pada server."}), 500
    
@app.route('/users')
@login_required
def users():
    try:
        # Ambil token dari request.user (hasil dari @login_required)
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        print(f"[DEBUG] Authorization header: {headers}")

        # Mengambil data pengguna dari user_service
        response = requests.get(USER_SERVICE_URL, headers=headers)
        response.raise_for_status()
        users = response.json()
        print(f"[DEBUG] Total users fetched: {len(users)}")

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] user_service error: {e}")
        error_message = 'Layanan user_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
        return render_template('pages/users.html', error_message=error_message, page_name="User")

    try:
        # Mengambil data kelas dari kelas_service
        kelas_response = requests.get(KELAS_SERVICE_URL, headers=headers)
        kelas_response.raise_for_status()
        kelas_list = kelas_response.json()
        print(f"[DEBUG] Total kelas fetched: {len(kelas_list)}")

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] kelas_service error: {e}")
        error_message = 'Layanan kelas_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
        return render_template('pages/users.html', error_message=error_message, page_name="User")

    try:
        # Mengambil data jurusan dari jurusan_service
        jurusan_response = requests.get(JURUSAN_SERVICE_URL, headers=headers)
        jurusan_response.raise_for_status()
        jurusan_list = jurusan_response.json()
        print(f"[DEBUG] Total jurusan fetched: {len(jurusan_list)}")

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] jurusan_service error: {e}")
        error_message = 'Layanan jurusan_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
        return render_template('pages/users.html', error_message=error_message, page_name="User")

    # Buat kamus untuk pencarian nama kelas dan jurusan
    kelas_dict = {kelas['_id']: kelas['nama_kelas'] for kelas in kelas_list}
    jurusan_dict = {jurusan['_id']: jurusan['nama_jurusan'] for jurusan in jurusan_list}

    # Tambahkan nama kelas dan jurusan ke user
    for user in users:
        user['nama_kelas'] = kelas_dict.get(user.get('kelas_id'), '-')
        user['nama_jurusan'] = jurusan_dict.get(user.get('jurusan_id'), '-')

        # URL foto
        if 'foto' in user and user['foto']:
            user['foto_url'] = f'http://127.0.0.1:5000/{user.get("foto")}'
        else:
            user['foto_url'] = url_for('static', filename='default-avatar.png')

        print(f"[DEBUG] User data: {user['username']}, kelas: {user['nama_kelas']}, jurusan: {user['nama_jurusan']}")

    # Filter data jika user login sebagai guru/siswa
    if request.user['role'] in ['guru', 'siswa']:
        users = [user for user in users if user['username'] == request.user['username']]

    return render_template('pages/users.html', users=users, user=request.user, page_name="User")


# Rute utuk Edit user
@app.route('/edit-user/<string:user_id>')
@login_required
def edit_user(user_id):
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin', 'guru', 'siswa']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    try:
        
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        # Ambil data user dari user_service
        user_response = requests.get(f'{USER_SERVICE_URL}/{user_id}', headers=headers)
        user_response.raise_for_status()
        user = user_response.json()

        # Ambil data jurusan dan kelas
        jurusan_response = requests.get(JURUSAN_SERVICE_URL, headers=headers)
        kelas_response = requests.get(KELAS_SERVICE_URL, headers=headers)
        jurusan_response.raise_for_status()
        kelas_response.raise_for_status()
        jurusan_list = jurusan_response.json()
        kelas_list = kelas_response.json()
        
        # Membuat URL foto yang merujuk ke proxy di hello_service
        if 'foto' in user and user['foto']:
            # user['foto_url'] = url_for('proxy_foto', filename=user['foto'].split('/')[-1])
            user['foto_url'] = f'http://127.0.0.1:5000/{user.get("foto")}'
        else:
            user['foto_url'] = url_for('static', filename='default-avatar.png')

        return render_template('pages/edit-user.html', user=user, jurusan_list=jurusan_list, kelas_list=kelas_list, page_name="User")
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500

# Rute untuk Melakukan Deliveri update ke user_service
@app.route('/proxy/user/update/<user_id>', methods=['POST'])
@login_required
def proxy_update_user(user_id):
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin', 'guru', 'siswa']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    data = request.form.to_dict(flat=True)
    foto = request.files.get('foto')
    
    files_payload = {}
    if foto:
        files_payload['foto'] = (foto.filename, foto.read(), foto.content_type)

    try:
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        response = requests.post(f'{USER_SERVICE_URL}/update/{user_id}', data=data, files=files_payload, headers=headers)
        if response.status_code == 200:
            return jsonify({"message": "User berhasil diperbarui.", "redirect_url": url_for('users')}), 200
        else:
            return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({"message": "Terjadi kesalahan pada server."}), 500
    
# Rute untuk Menghapus Pengguna di hello_service
@app.route('/proxy/user/delete/<string:user_id>', methods=['DELETE'])
@login_required
def proxy_delete_user(user_id):
    # Memeriksa apakah pengguna memiliki role 'admin'
    if request.user['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))

    try:
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        response = requests.delete(f'{USER_SERVICE_URL}/delete/{user_id}', headers=headers)
        if response.status_code == 200:
            return jsonify({"message": "User berhasil dihapus."}), 200
        else:
            return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({"message": "Terjadi kesalahan pada server."}), 500
    

#-------------ROUTE UNTUK JURUSAN----------------
#-----ROUTE UNTUK TAMBAH DATA JURUSAN------------
@app.route('/create-jurusan')
@login_required
def create_jurusan():
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    headers = {'Authorization': f"Bearer {request.user['token']}"}
    
    return render_template('pages/create-jurusan.html', page_name="Jurusan", headers=headers)

@app.route('/proxy/jurusan/insert', methods=['POST'])
@login_required
def proxy_insert():
    data = request.json  # Mendapatkan data dari permintaan
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))

    try:
        
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        response = requests.post(f'{JURUSAN_SERVICE_URL}/insert', json=data, headers=headers)
        print("Response from backend:", response.status_code, response.json())  # Debugging
        if response.status_code == 201:  # Status kode 201 untuk sukses insert
            return jsonify({"message": "Jurusan berhasil ditambahkan.", "redirect_url": url_for('jurusan')}), 201
        else:
            return jsonify(response.json()), response.status_code
    except Exception as e:
        print("Error:", str(e))  # Debugging
        return jsonify({"message": "Terjadi kesalahan pada server."}), 500
    
#-----ROUTE UNTUK EDIT DATA JURUSAN------------
@app.route('/edit-jurusan/<string:jurusan_id>')
@login_required
def edit_jurusan(jurusan_id):
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    headers = {'Authorization': f"Bearer {request.user['token']}"}
    
    jurusan = requests.get(f'{JURUSAN_SERVICE_URL}/{jurusan_id}', headers=headers).json()
    
    return render_template('pages/edit-jurusan.html', jurusan=jurusan, page_name="Jurusan")
    
@app.route('/proxy/jurusan/update/<string:jurusan_id>', methods=['PUT'])
@login_required
def proxy_update(jurusan_id):
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    data = request.get_json()  # Mendapatkan data dari permintaan
    print("Received data:", data)  # Debugging

    try:
        
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        response = requests.put(f'{JURUSAN_SERVICE_URL}/update/{jurusan_id}', json=data, headers=headers)
        print("Response from backend:", response.status_code, response.json())  # Debugging
        if response.status_code == 200:  # Status kode 200 untuk sukses update
            return jsonify({"message": "Jurusan berhasil diupdate.", "redirect_url": url_for('jurusan')}), 200
        else:
            return jsonify(response.json()), response.status_code
    except Exception as e:
        print("Error:", str(e))  # Debugging
        return jsonify({"message": "Terjadi kesalahan pada server."}), 500
    
#-----ROUTE UNTUK MENAMPILKAN DATA JURUSAN------------
@app.route('/jurusan')
@login_required
def jurusan():
    
    try:
        headers = {'Authorization': f"Bearer {request.user['token']}"}  # Ambil token dari user context

        response = requests.get(JURUSAN_SERVICE_URL, headers=headers)
        response.raise_for_status()
        jurusan = response.json()
        
        return render_template('pages/jurusan.html', jurusan=jurusan, page_name="Jurusan")
    except requests.exceptions.ConnectionError:
        # Jika terjadi kesalahan koneksi, tampilkan pesan error ramah
        error_message = "Layanan jurusan_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan."
        return render_template('pages/jurusan.html', error_message=error_message, jurusan=[], page_name="Jurusan")
    
#-----ROUTE UNTUK MENGHAPUS DATA JURUSAN------------
@app.route('/proxy/delete/<jurusan_id>', methods=['DELETE'])
@login_required
def proxy_delete(jurusan_id):
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    headers = {'Authorization': f"Bearer {request.user['token']}"}
    
    response = requests.delete(f'{JURUSAN_SERVICE_URL}/delete/{jurusan_id}', headers=headers)
    if response.status_code == 204:
        return jsonify({"message": "Jurusan berhasil dihapus."}), 200
    else:
        return jsonify(response.json()), response.status_code

#-------------ROUTE UNTUK KELAS----------------
#-----ROUTE UNTUK TAMBAH DATA KELAs--------------
@app.route('/create-kelas')
@login_required
def create_kelas():
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    headers = {'Authorization': f"Bearer {request.user['token']}"}
    
    return render_template('pages/create-kelas.html', headers=headers ,page_name="Kelas")

@app.route('/proxy/kelas/insert', methods=['POST'])
@login_required
def proxy_insert_kelas():
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    data = request.json  # Mendapatkan data dari permintaan
    print("Received data:", data)  # Debugging

    try:
        
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        response = requests.post(f'{KELAS_SERVICE_URL}/insert', json=data, headers=headers)
        print("Response from backend:", response.status_code, response.json())  # Debugging
        if response.status_code == 201 or response.status_code == 200:  # Status kode 201 atau 200 untuk sukses insert/update
            return jsonify({"message": "Kelas berhasil ditambahkan.", "redirect_url": url_for('kelas')}), 201
        else:
            return jsonify(response.json()), response.status_code
    except Exception as e:
        print("Error:", str(e))  # Debugging
        return jsonify({"message": "Terjadi kesalahan pada server."}), 500
    
@app.route('/edit-kelas/<string:kelas_id>')
@login_required
def edit_kelas(kelas_id):
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    headers = {'Authorization': f"Bearer {request.user['token']}"}

    kelas = requests.get(f'{KELAS_SERVICE_URL}/{kelas_id}', headers=headers).json()

    return render_template('pages/edit-kelas.html', kelas=kelas, page_name="Kelas")

@app.route('/proxy/kelas/update/<string:kelas_id>', methods=['PUT'])
@login_required
def proxy_update_kelas(kelas_id):
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    data = request.get_json()  # Mendapatkan data dari permintaan
    print("Received data:", data)  # Debugging

    try:
        
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        response = requests.put(f'{KELAS_SERVICE_URL}/update/{kelas_id}', json=data, headers=headers)
        print("Response from backend:", response.status_code, response.json())  # Debugging
        if response.status_code == 200:  # Status kode 200 untuk sukses update
            return jsonify({"message": "Kelas berhasil diupdate.", "redirect_url": url_for('kelas')}), 200
        else:
            return jsonify(response.json()), response.status_code
    except Exception as e:
        print("Error:", str(e))  # Debugging
        return jsonify({"message": "Terjadi kesalahan pada server."}), 500
    
@app.route('/kelas')
@login_required
def kelas():
    try:
        
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        response = requests.get(KELAS_SERVICE_URL, headers=headers)
        response.raise_for_status()
        kelas = response.json()

        return render_template('pages/kelas.html', kelas=kelas, page_name="Kelas")

    except requests.exceptions.RequestException as e:
        # Custom error handling
        error_message = 'Layanan kelas_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
        return render_template('pages/kelas.html', error_message=error_message, page_name="Kelas")


@app.route('/proxy/kelas/delete/<kelas_id>', methods=['DELETE'])
@login_required
def proxy_delete_kelas(kelas_id):
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    headers = {'Authorization': f"Bearer {request.user['token']}"}
    
    response = requests.delete(f'{KELAS_SERVICE_URL}/delete/{kelas_id}', headers=headers)
    if response.status_code == 204:
        return jsonify({"message": "Kelas berhasil dihapus."}), 200
    else:
        return jsonify(response.json()), response.status_code
    
#-------------ROUTE UNTUK MATERI----------------
#-----ROUTE UNTUK TAMBAH DATA MATERI--------------
    
@app.route('/create-materi')
@login_required
def create_materi():
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin','guru']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    headers = {'Authorization': f"Bearer {request.user['token']}"}
    
    # Get data from kelas_service
    kelas_response = requests.get(KELAS_SERVICE_URL, headers=headers)
    kelas_response.raise_for_status()
    kelas_list = kelas_response.json()

    # Get data from jurusan_service
    jurusan_response = requests.get(JURUSAN_SERVICE_URL, headers=headers)
    jurusan_response.raise_for_status()
    jurusan_list = jurusan_response.json()

    return render_template('pages/create-materi.html',user=request.user, kelas_list=kelas_list, jurusan_list=jurusan_list, page_name="Materi")
    
@app.route('/proxy/materi/insert', methods=['POST'])
@login_required
def proxy_insert_materi():
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    data = request.form.to_dict(flat=True)
    files = request.files.getlist('pdf_files')
    
    files_payload = [('pdf_files', (file.filename, file.read(), file.content_type)) for file in files]
    
    try:
        
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        response = requests.post(f'{MATERI_SERVICE_URL}/insert', data=data, files=files_payload, headers=headers)
        print("Response from backend:", response.status_code, response.json())
        if response.status_code == 201 or response.status_code == 200:
            return jsonify({"message": "Materi berhasil ditambahkan.", "redirect_url": url_for('materi')}), 201
        else:
            return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException as e:
        print("Error:", str(e))
        return jsonify({"message": "Terjadi kesalahan pada server."}), 500


@app.route('/edit-materi/<string:m_id>')
@login_required
def edit_materi(m_id):

    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin','guru']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    try:
        
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        # Ambil data materi dari materi_service
        materi_response = requests.get(f'{MATERI_SERVICE_URL}/{m_id}')
        materi_response.raise_for_status()
        materi = materi_response.json()

        # Ambil data jurusan dan kelas dari jurusan_service dan kelas_service
        jurusan_response = requests.get(JURUSAN_SERVICE_URL, headers=headers)
        kelas_response = requests.get(KELAS_SERVICE_URL, headers=headers)
        jurusan_response.raise_for_status()
        kelas_response.raise_for_status()
        jurusan_list = jurusan_response.json()
        kelas_list = kelas_response.json()

        return render_template('pages/edit-materi.html',user=request.user, materi=materi, jurusan_list=jurusan_list, kelas_list=kelas_list, page_name="Materi")
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500

@app.route('/proxy/materi/update/<materi_id>', methods=['POST'])
@login_required
def proxy_update_materi(materi_id):
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin','guru']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    data = request.form.to_dict(flat=True)
    files = request.files.getlist('pdf_files')

    files_payload = [('pdf_files', (file.filename, file.read(), file.content_type)) for file in files]

    try:
        
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        response = requests.post(f'{MATERI_SERVICE_URL}/update/{materi_id}', data=data, files=files_payload)
        if response.status_code == 200:
            return jsonify({"message": "Materi berhasil diperbarui.", "redirect_url": url_for('materi')}), 200
        else:
            return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({"message": "Terjadi kesalahan pada server."}), 500

@app.route('/proxy/materi/delete/<string:m_id>', methods=['DELETE'])
@login_required
def proxy_delete_materi(m_id):
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin','guru']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    try:
        
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        response = requests.delete(f'{MATERI_SERVICE_URL}/delete/{m_id}')
        if response.status_code == 204:
            return jsonify({"message": "Materi berhasil dihapus."}), 200
        else:
            return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({"message": "Terjadi kesalahan pada server."}), 500

@app.route('/materi')
@login_required
def materi():
    headers = {'Authorization': f"Bearer {request.user['token']}"}

    try:
        # Get data from materi_service
        materi_response = requests.get(MATERI_SERVICE_URL)
        materi_response.raise_for_status()
        materi = materi_response.json()

    except requests.exceptions.RequestException:
        error_message = 'Layanan materi_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
        return render_template('pages/materi.html', error_message=error_message, page_name="Materi")

    try:
        # Get data from kelas_service
        kelas_response = requests.get(KELAS_SERVICE_URL, headers=headers)
        kelas_response.raise_for_status()
        kelas_list = kelas_response.json()

    except requests.exceptions.RequestException:
        error_message = 'Layanan kelas_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
        return render_template('pages/materi.html', error_message=error_message, page_name="Materi")

    try:
        # Get data from jurusan_service
        jurusan_response = requests.get(JURUSAN_SERVICE_URL, headers=headers)
        jurusan_response.raise_for_status()
        jurusan_list = jurusan_response.json()

    except requests.exceptions.RequestException:
        error_message = 'Layanan jurusan_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
        return render_template('pages/materi.html', error_message=error_message, page_name="Materi")

    # Buat dict untuk lookup
    kelas_dict = {kelas['_id']: kelas['nama_kelas'] for kelas in kelas_list}
    jurusan_dict = {jurusan['_id']: jurusan['nama_jurusan'] for jurusan in jurusan_list}

    # Filter materi berdasarkan peran
    user_role = request.user.get('role')
    jurusan_id = request.user.get('jurusan_id')
    kelas_id = request.user.get('kelas_id')

    if user_role == 'siswa':
        materi = [m for m in materi if m['jurusan_id'] == jurusan_id and m['kelas_id'] == kelas_id]
    elif user_role == 'guru':
        materi = [m for m in materi if m['jurusan_id'] == jurusan_id]
    # admin bisa melihat semua materi, jadi tidak difilter

    for m in materi:
        m['nama_kelas'] = kelas_dict.get(m['kelas_id'], 'Kelas tidak ditemukan')
        m['nama_jurusan'] = jurusan_dict.get(m['jurusan_id'], 'Jurusan tidak ditemukan')

        # Pastikan pdf_files berupa list
        if 'pdf_files' not in m or not isinstance(m['pdf_files'], list):
            m['pdf_files'] = []

    return render_template('pages/materi.html', user=request.user, materi=materi, page_name="Materi")
    
@app.route('/detail-materi/<string:m_id>')
@login_required
def detail_materi(m_id):
    try:
        
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        # Get data from materi_service
        materi_response = requests.get(f'{MATERI_SERVICE_URL}/{m_id}')
        materi_response.raise_for_status()
        materi = materi_response.json()

        # Get data from kelas_service
        kelas_response = requests.get(KELAS_SERVICE_URL, headers=headers)
        kelas_response.raise_for_status()
        kelas_list = kelas_response.json()

        # Get data from jurusan_service
        jurusan_response = requests.get(JURUSAN_SERVICE_URL, headers=headers)
        jurusan_response.raise_for_status()
        jurusan_list = jurusan_response.json()

        # Create dictionaries for fast lookup
        kelas_dict = {kelas['_id']: kelas['nama_kelas'] for kelas in kelas_list}
        jurusan_dict = {jurusan['_id']: jurusan['nama_jurusan'] for jurusan in jurusan_list}

        materi['nama_kelas'] = kelas_dict.get(materi['kelas_id'], 'Kelas tidak ditemukan')
        materi['nama_jurusan'] = jurusan_dict.get(materi['jurusan_id'], 'Jurusan tidak ditemukan')

        # Ensure pdf_files is a list
        if 'pdf_files' not in materi or not isinstance(materi['pdf_files'], list):
            materi['pdf_files'] = []

        return render_template('pages/detail-materi.html', materi=materi, page_name="Materi")
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500

@app.route('/openpdf/<filename>')
@login_required
def proxy_openpdf(filename):
    try:
        
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        # Request ke service PDF untuk dibuka secara inline
        materi_service_url = f"{MATERI_SERVICE_URL_PDF}/openpdf/pdf/{filename}"
        response = requests.get(materi_service_url, stream=True)

        if response.status_code == 200:
            return Response(
                response.iter_content(chunk_size=1024),
                content_type=response.headers.get('Content-Type', 'application/pdf'),
                headers={
                    "Content-Disposition": f"inline; filename={filename}"
                }
            )
        else:
            return f"Gagal membuka PDF. Status code: {response.status_code}", 404

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to materi_service: {e}")
        return "Terjadi kesalahan saat mengakses PDF", 500
    
@app.route('/uploads/<filename>')
@login_required
def proxy_downloadpdf(filename):
    try:
        
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        # Request ke service PDF untuk diunduh
        materi_service_url = f"{MATERI_SERVICE_URL_PDF}/uploads/pdf/{filename}"
        response = requests.get(materi_service_url, stream=True)

        if response.status_code == 200:
            return Response(
                response.iter_content(chunk_size=1024),
                content_type=response.headers.get('Content-Type', 'application/pdf'),
                headers={
                    "Content-Disposition": f"attachment; filename={filename}"
                }
            )
        else:
            return f"Gagal mengunduh PDF. Status code: {response.status_code}", 404

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to materi_service: {e}")
        return "Terjadi kesalahan saat mengakses PDF", 500

@app.route('/create-soal')
@login_required
def create_soal():
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin','guru']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    try:
        
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        # Ambil data jurusan
        jurusan_response = requests.get(f"{JURUSAN_SERVICE_URL}", headers=headers)
        jurusan_list = jurusan_response.json()

        # Ambil data kelas
        kelas_response = requests.get(f"{KELAS_SERVICE_URL}", headers=headers)
        kelas_list = kelas_response.json()
        
        # Ambil data Materi
        materi_response = requests.get(f"{MATERI_SERVICE_URL}", headers=headers)
        materi_list = materi_response.json()

        return render_template('pages/create-soal.html', jurusans=jurusan_list, kelass=kelas_list, materis=materi_list,  page_name="Soal")
    except Exception as e:
        return render_template('pages/create-soal.html', error="Gagal mengambil data kelas dan jurusan.")

@app.route('/proxy/soal/insert', methods=['POST'])
@login_required
def proxy_insert_soal():
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin', 'guru']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))

    try:
        data = request.get_json()
        data['user_id'] = request.user.get('user_id')  # gunakan data user dari token, bukan session

        headers = {'Authorization': f"Bearer {request.user['token']}"}

        response = requests.post(f'{SOAL_SERVICE_URL}/create', json=data, headers=headers)
        response.raise_for_status()

        return jsonify({"message": "Soal berhasil ditambahkan.", "redirect_url": url_for('soal')}), 201

    except requests.exceptions.RequestException as e:
        return jsonify({"message": f"Gagal menghubungi SOAL_SERVICE: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"message": f"Terjadi kesalahan pada server: {str(e)}"}), 500

    
@app.route('/edit-soal/<string:soal_id>')
@login_required
def edit_soal(soal_id):

    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin','guru']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    try:
        
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        # Ambil data materi dari materi_service
        soal_response = requests.get(f'{SOAL_SERVICE_URL}/soal/{soal_id}', headers=headers)
        soal_response.raise_for_status()
        soal = soal_response.json()

        # Ambil data jurusan dan kelas dari jurusan_service dan kelas_service
        jurusan_response = requests.get(JURUSAN_SERVICE_URL, headers=headers)
        kelas_response = requests.get(KELAS_SERVICE_URL, headers=headers)
        materi_response = requests.get(MATERI_SERVICE_URL, headers=headers)
        jurusan_response.raise_for_status()
        kelas_response.raise_for_status()
        materi_response.raise_for_status()
        jurusan_list = jurusan_response.json()
        kelas_list = kelas_response.json()
        materi_list = materi_response.json()

        return render_template('pages/edit-soal.html', soal=soal, jurusan_list=jurusan_list, kelas_list=kelas_list, materi_list=materi_list, page_name="Soal")
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500

@app.route('/proxy/soal/update/<string:soal_id>', methods=['POST'])
@login_required
def proxy_update_soal(soal_id):
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))

    data = request.get_json()

    if not data:
        return jsonify({"message": "Data tidak valid."}), 400

    # Pastikan soal_id valid (24 karakter)
    if len(soal_id) != 24:
        return jsonify({"message": "Invalid soal_id format. Must be 24-character hexadecimal"}), 400

    # Menambahkan data kelas_id, jurusan_id, materi_id jika belum ada
    if not all(key in data for key in ['kelas_id', 'jurusan_id', 'materi_id']):
        return jsonify({"message": "Data harus menyertakan kelas_id, jurusan_id, dan materi_id"}), 400

    try:
        
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        response = requests.put(f'{SOAL_SERVICE_URL}/update/{soal_id}', json=data, headers=headers)
        response.raise_for_status()

        if response.status_code == 200:
            return jsonify({"message": "Soal berhasil diperbarui.", "redirect_url": url_for('soal')}), 200
        else:
            return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException as e:
        print(f"Error updating soal: {e}")  # Debugging di server
        return jsonify({"message": "Terjadi kesalahan pada server."}), 500


@app.route('/soal')
@login_required
def soal():
    headers = {'Authorization': f"Bearer {request.user['token']}"}

    try:
        soal_response = requests.get(f"{SOAL_SERVICE_URL}/soal", headers=headers)
        soal_response.raise_for_status()
        soals = soal_response.json()
    except requests.exceptions.RequestException:
        return render_template('pages/soal.html', error_message='Layanan soal_service tidak dapat dihubungi.', page_name="Soal")

    try:
        kelas_response = requests.get(KELAS_SERVICE_URL, headers=headers)
        kelas_response.raise_for_status()
        kelas_list = kelas_response.json()
    except requests.exceptions.RequestException:
        return render_template('pages/soal.html', error_message='Layanan kelas_service tidak dapat dihubungi.', page_name="Soal")

    try:
        jurusan_response = requests.get(JURUSAN_SERVICE_URL, headers=headers)
        jurusan_response.raise_for_status()
        jurusan_list = jurusan_response.json()
    except requests.exceptions.RequestException:
        return render_template('pages/soal.html', error_message='Layanan jurusan_service tidak dapat dihubungi.', page_name="Soal")

    try:
        materi_response = requests.get(MATERI_SERVICE_URL, headers=headers)
        materi_response.raise_for_status()
        materi_list = materi_response.json()
    except requests.exceptions.RequestException:
        return render_template('pages/soal.html', error_message='Layanan materi_service tidak dapat dihubungi.', page_name="Soal")

    kelas_dict = {kelas['_id']: kelas['nama_kelas'] for kelas in kelas_list}
    jurusan_dict = {jurusan['_id']: jurusan['nama_jurusan'] for jurusan in jurusan_list}
    materi_dict = {materi['_id']: materi['nama_materi'] for materi in materi_list}

    if request.user.get('role') == 'siswa':
        soals = [
            s for s in soals
            if s.get('jurusan_id') == request.user['jurusan_id'] and s.get('kelas_id') == request.user['kelas_id']
        ]

        try:
            jawaban_response = requests.get(
                f"{SOAL_SERVICE_URL}/jawaban?user_id={request.user['user_id']}",
                headers=headers
            )
            jawaban_response.raise_for_status()
            jawaban_list = jawaban_response.json()
        except requests.exceptions.RequestException:
            return render_template('pages/soal.html', error_message='Layanan jawaban soal_service tidak dapat dihubungi.', page_name="Soal")

        for s in soals:
            jawaban = next((j for j in jawaban_list if j['soal_id'] == s['_id']), None)
            s['nilai'] = jawaban.get('nilai') if jawaban else None

    elif request.user.get('role') == 'guru':
        soals = [
            s for s in soals
            if s.get('jurusan_id') == request.user['jurusan_id'] and s.get('user_id') == request.user['user_id']
        ]

    for s in soals:
        s['nama_kelas'] = kelas_dict.get(s['kelas_id'], 'Kelas tidak ditemukan')
        s['nama_jurusan'] = jurusan_dict.get(s['jurusan_id'], 'Jurusan tidak ditemukan')
        s['nama_materi'] = materi_dict.get(s.get('materi_id'), 'Materi tidak ditemukan')
        s['questions'] = [value for key, value in s.items() if key.startswith('question_')]

    return render_template('pages/soal.html', user=request.user, soals=soals, page_name="Soal")

@app.route('/delete-soal/<soal_id>', methods=['DELETE'])
@login_required
def delete_soal(soal_id):
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    try:
        
        headers = {'Authorization': f"Bearer {request.user['token']}"}

        response = requests.delete(f"{SOAL_SERVICE_URL}/soal/{soal_id}", headers=headers)
        if response.status_code == 200:
            return jsonify({"message": "Soal berhasil dihapus."}), 200
        else:
            return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({"message": str(e)}), 500

@app.route('/jawab-soal/<soal_id>')
@login_required
def jawab_soal(soal_id):
    try:
        
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        # Dapatkan data soal berdasarkan ID
        soal_response = requests.get(f"{SOAL_SERVICE_URL}/soal/{soal_id}", headers=headers)
        soal_response.raise_for_status()
        soal = soal_response.json()

        # Periksa apakah siswa sudah menjawab soal melalui API
        user_id = request.user.get('user_id')
        jawaban_response = requests.get(f"{SOAL_SERVICE_URL}/cek-jawaban/{soal_id}/{user_id}", headers=headers)
        jawaban_response.raise_for_status()
        jawaban_data = jawaban_response.json()
        already_answered = jawaban_data.get('already_answered', False)

        questions = [value for key, value in soal.items() if key.startswith('question_')]

        # Render halaman dengan informasi apakah sudah menjawab atau belum
        return render_template('pages/answer-soal.html', soal_id=soal_id, questions=questions, already_answered=already_answered,  page_name="Jawab Soal")
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500

@app.route('/submit-jawaban', methods=['POST'])
@login_required
def submit_jawaban():
    data = request.form.to_dict()
    data['user_id'] = request.user['user_id']  # Ambil user_id langsung dari request.user

    try:
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        response = requests.post(f"{SOAL_SERVICE_URL}/jawaban", json=data, headers=headers)
        response.raise_for_status()
        return jsonify({"message": "Jawaban berhasil dikirim."}), 201
    except requests.exceptions.RequestException as e:
        return jsonify({'message': str(e)}), 500


# KODE BARU DITAMBAH
@app.route('/koreksi-jawaban/<soal_id>')
@login_required
def koreksi_jawaban(soal_id):
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if request.user['role'] not in ['admin','guru']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    try:
        headers = {'Authorization': f"Bearer {request.user['token']}"}
        
        # Dapatkan semua jawaban dan soal untuk soal tertentu
        response = requests.get(f"{SOAL_SERVICE_URL}/jawaban/{soal_id}", headers=headers)
        response.raise_for_status()
        data = response.json()
        jawabans = data.get('jawabans', [])
        soal = data.get('soal', {})

        # Periksa apakah semua jawaban sudah dikoreksi
        all_corrected = all(jawaban.get('nilai') is not None for jawaban in jawabans)

        return render_template(
            'pages/koreksi-jawaban.html',
            jawabans=jawabans,
            soal=soal,
            soal_id=soal_id,
            all_corrected=all_corrected,
            page_name="Jawaban"
        )
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500


@app.route('/submit-koreksi/<jawaban_id>', methods=['POST'])
@login_required
def submit_koreksi(jawaban_id):
    data = request.form.to_dict()
    try:
        # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
        if request.user['role'] not in ['admin','guru']:
            alert_message = "Anda tidak memiliki akses ke halaman ini."
            session['alert_message'] = alert_message
            return redirect(url_for('index'))

        headers = {'Authorization': f"Bearer {request.user['token']}"}

        response = requests.post(f"{SOAL_SERVICE_URL}/koreksi-jawaban/{jawaban_id}", json=data, headers=headers)
        response.raise_for_status()
        return jsonify({"message": "Koreksi berhasil dikirim."}), 200
    except requests.exceptions.RequestException as e:
        return jsonify({'message': str(e)}), 500
    
@app.route('/download-rekap/<soal_id>')
@login_required
def download_rekap(soal_id):
    try:
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
        if request.user['role'] not in ['admin','guru']:
            alert_message = "Anda tidak memiliki akses ke halaman ini."
            session['alert_message'] = alert_message
            return redirect(url_for('index'))

        headers = {'Authorization': f"Bearer {request.user['token']}"}

        # Dapatkan semua jawaban untuk soal tertentu
        response = requests.get(f"{SOAL_SERVICE_URL}/jawaban/{soal_id}", headers=headers)
        response.raise_for_status()
        data = response.json()
        jawabans = data.get('jawabans', [])

        # Periksa apakah semua jawaban sudah dikoreksi
        if not all(j.get('nilai') is not None for j in jawabans):
            return jsonify({"message": "Belum semua jawaban dikoreksi."}), 400

        # Buat PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)

        # Tambahkan judul
        pdf.cell(200, 10, txt="Rekap Nilai", ln=True, align='C')

        # Tambahkan tabel
        pdf.cell(40, 10, txt="NIS", border=1)
        pdf.cell(80, 10, txt="Nama", border=1)
        pdf.cell(40, 10, txt="Nilai", border=1)
        pdf.ln()

        # Tambahkan data dari jawaban
        for jawaban in jawabans:
            pdf.cell(40, 10, txt=jawaban.get('username', ''), border=1)  # Ganti 'nim' dengan 'username'
            pdf.cell(80, 10, txt=jawaban.get('nama', ''), border=1)
            pdf.cell(40, 10, txt=str(jawaban.get('nilai', '')), border=1)
            pdf.ln()

        # Buat respons PDF
        response = make_response(pdf.output(dest='S').encode('latin1'))
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename=rekap_nilai.pdf'
        return response

    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500


@app.route('/profile')
def profile():
    return render_template('pages/profile.html')

@app.context_processor
def inject_user():
    return dict(user=getattr(request, "user", None))

# Fallback jika metrics bawaan tidak muncul
@app.route('/metrics')
def metrics_manual():
    return Response(prometheus_client.generate_latest(), mimetype=prometheus_client.CONTENT_TYPE_LATEST)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)

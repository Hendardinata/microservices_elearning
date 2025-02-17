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
from redis import Redis

load_dotenv()

# Inisialisasi aplikasi Flask
app = Flask(__name__)

# Mengatur direktori template dan static
app.template_folder = 'argon-dashboard'

# Mengatur app.static_folder 
app = Flask(__name__, template_folder='argon-dashboard/templates', static_folder='argon-dashboard/assets')

# Mengatur Random Secret Key
app.secret_key = 'your-consistent-secret-key'

# Mengatur CORS ( Cross )
CORS(app, supports_credentials=True)

# URL untuk ambil semua DATA.

USER_SERVICE_URL = os.getenv('USER_SERVICE_URL')
KELAS_SERVICE_URL = os.getenv('KELAS_SERVICE_URL')
MATERI_SERVICE_URL = os.getenv('MATERI_SERVICE_URL')
JURUSAN_SERVICE_URL = os.getenv('JURUSAN_SERVICE_URL')
SOAL_SERVICE_URL = os.getenv('SOAL_SERVICE_URL')
# API Token
API_TOKEN = os.getenv('API_TOKEN')

# Konfigurasi MongoDB
mongo_uri = os.getenv('MONGO_URI')
mongo_db_name = os.getenv('MONGO_DB_NAME')
client = MongoClient(mongo_uri)
db = client[mongo_db_name]
login_logs_collection = db["login_logs"]

# Konfigurasi Redis untuk session
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'auth_service_'  # Harus sama dengan di auth_service
app.config['SESSION_REDIS'] = Redis(host='redis', port=6379)

# Inisialisasi session
server_session = Session(app)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        print(f"Checking login status, user_id: {user_id}")
        if not user_id:
            print("User not logged in, redirecting to login page.")
            return redirect('http://localhost:8000/')  # URL login dari auth_service
        print("User is logged in, proceeding to requested page.")
        return f(*args, **kwargs)
    return decorated_function

# Fungsi untuk menambahkan header Authorization
def get_headers():
    return {
        'Authorization': API_TOKEN,
    }

# Rute untuk menampilkan index
@app.route('/')
@login_required
def index():
    try:
        # Ambil data semua pengguna (hanya satu permintaan API)
        user_response = requests.get(f"{USER_SERVICE_URL}", headers=get_headers())
        if user_response.status_code == 200:
            all_users = user_response.json()
            total_siswa = sum(1 for user in all_users if user.get('role') == 'siswa')
            total_guru = sum(1 for user in all_users if user.get('role') == 'guru')
        else:
            total_siswa = 0
            total_guru = 0

        # Ambil data total materi
        materi_response = requests.get(f"{MATERI_SERVICE_URL}", headers=get_headers())
        total_materi = len(materi_response.json()) if materi_response.status_code == 200 else 0

        # Ambil 10 log aktivitas login terbaru
        login_logs = list(login_logs_collection.find().sort("timestamp", -1).limit(10))

        # Cek apakah user memiliki role admin
        user_data = session.get("user_data")
        is_admin = user_data.get("role") == "admin" if user_data else False

        # Render halaman dashboard
        return render_template(
            'pages/index.html',
            total_siswa=total_siswa,
            total_guru=total_guru,
            total_materi=total_materi,
            login_logs=login_logs,
            is_admin=is_admin
        )
    except Exception as e:
        print(f"Error while loading dashboard: {e}")
        return render_template('pages/index.html', error_message="Error loading dashboard data.")


# Rute untuk Logout
@app.route('/logout')
@login_required
def logout():
    session.clear()
    return redirect('http://localhost:8000/')  # URL login dari auth_service

#-------------ROUTE UNTUK USER ----------------
#-----ROUTE UNTUK TAMBAH DATA USER------------

# Rute untuk Create User
@app.route('/create-user')
@login_required
def create_user():
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if session['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        # Menyimpan pesan ke dalam session agar bisa diakses setelah redirect
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    # Get data from kelas_service
    kelas_response = requests.get(KELAS_SERVICE_URL, headers=get_headers())
    kelas_response.raise_for_status()
    kelas_list = kelas_response.json()

    # Get data from jurusan_service
    jurusan_response = requests.get(JURUSAN_SERVICE_URL, headers=get_headers())
    jurusan_response.raise_for_status()
    jurusan_list = jurusan_response.json()

    page_name = "User"
    return render_template('pages/create-user.html', kelas_list=kelas_list, jurusan_list=jurusan_list, page_name=page_name)

# Rute untuk Melakukan Deliveri ke user_service
@app.route('/proxy/user/insert', methods=['POST'])
@login_required
def proxy_insert_user():
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if session['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        # Menyimpan pesan ke dalam session agar bisa diakses setelah redirect
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    data = request.form.to_dict(flat=True)
    foto = request.files.get('foto')
    
    if foto:
        files_payload = {'foto': (foto.filename, foto.read(), foto.content_type)}
    else:
        files_payload = {}
    
    try:
        response = requests.post(f'{USER_SERVICE_URL}/insert', data=data, files=files_payload, headers=get_headers())
        if response.status_code == 201:
            return jsonify({"message": "User berhasil ditambahkan.", "redirect_url": url_for('users')}), 201
        else:
            return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"message": "Terjadi kesalahan pada server."}), 500
    
# Rute untuk Menampilkan Seluruh data di User_Service
@app.route('/users')
@login_required
def users():
    try:
        # Mengambil data pengguna dari user_service
        response = requests.get(USER_SERVICE_URL, headers=get_headers())
        response.raise_for_status()
        users = response.json()

    except requests.exceptions.RequestException as e:
        error_message = 'Layanan user_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
        return render_template('pages/users.html', error_message=error_message, page_name="User")

    try:
        # Mengambil data kelas dari kelas_service
        kelas_response = requests.get(KELAS_SERVICE_URL, headers=get_headers())
        kelas_response.raise_for_status()
        kelas_list = kelas_response.json()

    except requests.exceptions.RequestException as e:
        error_message = 'Layanan kelas_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
        return render_template('pages/users.html', error_message=error_message, page_name="User")

    try:
        # Mengambil data jurusan dari jurusan_service
        jurusan_response = requests.get(JURUSAN_SERVICE_URL, headers=get_headers())
        jurusan_response.raise_for_status()
        jurusan_list = jurusan_response.json()

    except requests.exceptions.RequestException as e:
        error_message = 'Layanan jurusan_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
        return render_template('pages/users.html', error_message=error_message, page_name="User")

    # Membuat dictionary untuk pencarian cepat nama kelas dan jurusan
    kelas_dict = {kelas['_id']: kelas['nama_kelas'] for kelas in kelas_list}
    jurusan_dict = {jurusan['_id']: jurusan['nama_jurusan'] for jurusan in jurusan_list}

    # Menambahkan data kelas dan jurusan ke setiap user
    for user in users:
        user['nama_kelas'] = kelas_dict.get(user['kelas_id'], '-')
        user['nama_jurusan'] = jurusan_dict.get(user['jurusan_id'], '-')

        # Membuat URL foto yang merujuk ke proxy di hello_service
        if 'foto' in user and user['foto']:
            user['foto_url'] = f'http://127.0.0.1:5000/{user.get("foto")}'
            print(user)
        else:
            user['foto_url'] = url_for('static', filename='default-avatar.png')

    # Filter pengguna berdasarkan session login
    if session['role'] in ['guru', 'siswa']:
        users = [user for user in users if user['username'] == session['username']]

    page_name = "User"
    return render_template('pages/users.html', users=users, page_name=page_name)

# Rute utuk Edit user
@app.route('/edit-user/<string:user_id>')
@login_required
def edit_user(user_id):
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if session['role'] not in ['admin', 'guru','siswa']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        # Menyimpan pesan ke dalam session agar bisa diakses setelah redirect
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    try:
        # Ambil data user dari user_service
        user_response = requests.get(f'{USER_SERVICE_URL}/{user_id}', headers=get_headers())
        user_response.raise_for_status()
        user = user_response.json()

        # Ambil data jurusan dan kelas
        jurusan_response = requests.get(JURUSAN_SERVICE_URL, headers=get_headers())
        kelas_response = requests.get(KELAS_SERVICE_URL, headers=get_headers())
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

        page_name = "User"
        return render_template('pages/edit-user.html', user=user, jurusan_list=jurusan_list, kelas_list=kelas_list, page_name=page_name)
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500

# Rute untuk Melakukan Deliveri update ke user_service
@app.route('/proxy/user/update/<user_id>', methods=['POST'])
@login_required
def proxy_update_user(user_id):
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if session['role'] not in ['admin', 'guru','siswa']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        # Menyimpan pesan ke dalam session agar bisa diakses setelah redirect
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    data = request.form.to_dict(flat=True)
    foto = request.files.get('foto')
    
    files_payload = {}
    if foto:
        files_payload['foto'] = (foto.filename, foto.read(), foto.content_type)

    try:
        response = requests.post(f'{USER_SERVICE_URL}/update/{user_id}', data=data, files=files_payload, headers=get_headers())
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
    if session['role'] not in ['admin']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        session['alert_message'] = alert_message
        return redirect(url_for('index'))

    try:
        response = requests.delete(f'{USER_SERVICE_URL}/delete/{user_id}', headers=get_headers())
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
    page_name = "Jurusan"
    return render_template('pages/create-jurusan.html', page_name=page_name)

@app.route('/proxy/jurusan/insert', methods=['POST'])
@login_required
def proxy_insert():
    data = request.json  # Mendapatkan data dari permintaan
    print("Received data:", data)  # Debugging

    try:
        response = requests.post(f'{JURUSAN_SERVICE_URL}/insert', json=data, headers=get_headers())
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
    jurusan = requests.get(f'{JURUSAN_SERVICE_URL}/{jurusan_id}', headers=get_headers()).json()
    page_name = "Jurusan"
    return render_template('pages/edit-jurusan.html', jurusan=jurusan, page_name=page_name)
    
@app.route('/proxy/jurusan/update/<string:jurusan_id>', methods=['PUT'])
@login_required
def proxy_update(jurusan_id):
    data = request.get_json()  # Mendapatkan data dari permintaan
    print("Received data:", data)  # Debugging

    try:
        response = requests.put(f'{JURUSAN_SERVICE_URL}/update/{jurusan_id}', json=data, headers=get_headers())
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
        response = requests.get(JURUSAN_SERVICE_URL, headers=get_headers())
        response.raise_for_status()
        jurusan = response.json()
        
        page_name = "Jurusan"
        return render_template('pages/jurusan.html', jurusan=jurusan, page_name=page_name)
    except requests.exceptions.ConnectionError:
        # Jika terjadi kesalahan koneksi, tampilkan pesan error ramah
        error_message = "Layanan jurusan_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan."
        return render_template('pages/jurusan.html', error_message=error_message, jurusan=[], page_name="Jurusan")
    
#-----ROUTE UNTUK MENGHAPUS DATA JURUSAN------------
@app.route('/proxy/delete/<jurusan_id>', methods=['DELETE'])
@login_required
def proxy_delete(jurusan_id):
    response = requests.delete(f'{JURUSAN_SERVICE_URL}/delete/{jurusan_id}', headers=get_headers())
    if response.status_code == 204:
        return jsonify({"message": "Jurusan berhasil dihapus."}), 200
    else:
        return jsonify(response.json()), response.status_code


#-------------ROUTE UNTUK JURUSAN----------------
#-----ROUTE UNTUK TAMBAH DATA KELAs--------------
@app.route('/create-kelas')
@login_required
def create_kelas():
    page_name = "Kelas"
    return render_template('pages/create-kelas.html', page_name=page_name)

@app.route('/proxy/kelas/insert', methods=['POST'])
@login_required
def proxy_insert_kelas():
    data = request.json  # Mendapatkan data dari permintaan
    print("Received data:", data)  # Debugging

    try:
        response = requests.post(f'{KELAS_SERVICE_URL}/insert', json=data, headers=get_headers())
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
    kelas = requests.get(f'{KELAS_SERVICE_URL}/{kelas_id}', headers=get_headers()).json()
    page_name = "Kelas"
    return render_template('pages/edit-kelas.html', kelas=kelas, page_name=page_name)

@app.route('/proxy/kelas/update/<string:kelas_id>', methods=['PUT'])
@login_required
def proxy_update_kelas(kelas_id):
    data = request.get_json()  # Mendapatkan data dari permintaan
    print("Received data:", data)  # Debugging

    try:
        response = requests.put(f'{KELAS_SERVICE_URL}/update/{kelas_id}', json=data, headers=get_headers())
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
        response = requests.get(KELAS_SERVICE_URL, headers=get_headers())
        response.raise_for_status()
        kelas = response.json()

        page_name = "Kelas"
        return render_template('pages/kelas.html', kelas=kelas, page_name=page_name)

    except requests.exceptions.RequestException as e:
        # Custom error handling
        error_message = 'Layanan kelas_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
        return render_template('pages/kelas.html', error_message=error_message, page_name="Kelas")


@app.route('/proxy/kelas/delete/<kelas_id>', methods=['DELETE'])
@login_required
def proxy_delete_kelas(kelas_id):
    response = requests.delete(f'{KELAS_SERVICE_URL}/delete/{kelas_id}', headers=get_headers())
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
    if session['role'] not in ['admin', 'guru']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        # Menyimpan pesan ke dalam session agar bisa diakses setelah redirect
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    # Get data from kelas_service
    kelas_response = requests.get(KELAS_SERVICE_URL, headers=get_headers())
    kelas_response.raise_for_status()
    kelas_list = kelas_response.json()

    # Get data from jurusan_service
    jurusan_response = requests.get(JURUSAN_SERVICE_URL, headers=get_headers())
    jurusan_response.raise_for_status()
    jurusan_list = jurusan_response.json()

    page_name = "Materi"
    return render_template('pages/create-materi.html', kelas_list=kelas_list, jurusan_list=jurusan_list, page_name=page_name)
    
@app.route('/proxy/materi/insert', methods=['POST'])
@login_required
def proxy_insert_materi():
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if session['role'] not in ['admin', 'guru']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        # Menyimpan pesan ke dalam session agar bisa diakses setelah redirect
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    data = request.form.to_dict(flat=True)
    files = request.files.getlist('pdf_files')
    
    files_payload = [('pdf_files', (file.filename, file.read(), file.content_type)) for file in files]
    
    try:
        response = requests.post(f'{MATERI_SERVICE_URL}/insert', data=data, files=files_payload, headers=get_headers())
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
    if session['role'] not in ['admin', 'guru']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        # Menyimpan pesan ke dalam session agar bisa diakses setelah redirect
        session['alert_message'] = alert_message
        return redirect(url_for('index'))

    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if session['role'] not in ['admin', 'guru']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        # Menyimpan pesan ke dalam session agar bisa diakses setelah redirect
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    try:
        # Ambil data materi dari materi_service
        materi_response = requests.get(f'{MATERI_SERVICE_URL}/{m_id}')
        materi_response.raise_for_status()
        materi = materi_response.json()

        # Ambil data jurusan dan kelas dari jurusan_service dan kelas_service
        jurusan_response = requests.get(JURUSAN_SERVICE_URL, headers=get_headers())
        kelas_response = requests.get(KELAS_SERVICE_URL, headers=get_headers())
        jurusan_response.raise_for_status()
        kelas_response.raise_for_status()
        jurusan_list = jurusan_response.json()
        kelas_list = kelas_response.json()

        page_name = "Materi"
        return render_template('pages/edit-materi.html', materi=materi, jurusan_list=jurusan_list, kelas_list=kelas_list, page_name=page_name)
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500

@app.route('/proxy/materi/update/<materi_id>', methods=['POST'])
@login_required
def proxy_update_materi(materi_id):
    
    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if session['role'] not in ['admin', 'guru']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        # Menyimpan pesan ke dalam session agar bisa diakses setelah redirect
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    data = request.form.to_dict(flat=True)
    files = request.files.getlist('pdf_files')

    files_payload = [('pdf_files', (file.filename, file.read(), file.content_type)) for file in files]

    try:
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
    if session['role'] not in ['admin', 'guru']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        # Menyimpan pesan ke dalam session agar bisa diakses setelah redirect
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    try:
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
    try:
        # Get data from materi_service
        materi_response = requests.get(MATERI_SERVICE_URL)
        materi_response.raise_for_status()
        materi = materi_response.json()

    except requests.exceptions.RequestException as e:
        error_message = 'Layanan materi_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
        return render_template('pages/materi.html', error_message=error_message, page_name="Materi")

    try:
        # Get data from kelas_service
        kelas_response = requests.get(KELAS_SERVICE_URL, headers=get_headers())
        kelas_response.raise_for_status()
        kelas_list = kelas_response.json()

    except requests.exceptions.RequestException as e:
        error_message = 'Layanan kelas_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
        return render_template('pages/materi.html', error_message=error_message, page_name="Materi")

    try:
        # Get data from jurusan_service
        jurusan_response = requests.get(JURUSAN_SERVICE_URL, headers=get_headers())
        jurusan_response.raise_for_status()
        jurusan_list = jurusan_response.json()

    except requests.exceptions.RequestException as e:
        error_message = 'Layanan jurusan_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
        return render_template('pages/materi.html', error_message=error_message, page_name="Materi")

    # Create dictionaries for fast lookup
    kelas_dict = {kelas['_id']: kelas['nama_kelas'] for kelas in kelas_list}
    jurusan_dict = {jurusan['_id']: jurusan['nama_jurusan'] for jurusan in jurusan_list}

    # Filter materi untuk siswa
    if session['role'] == 'siswa':
        jurusan_id = session.get('jurusan_id')
        kelas_id = session.get('kelas_id')
        materi = [m for m in materi if m['jurusan_id'] == jurusan_id and m['kelas_id'] == kelas_id]
    elif session['role'] == 'guru':
        jurusan_id = session.get('jurusan_id')
        materi = [m for m in materi if m['jurusan_id'] == jurusan_id]

    for m in materi:
        m['nama_kelas'] = kelas_dict.get(m['kelas_id'], 'Kelas tidak ditemukan')
        m['nama_jurusan'] = jurusan_dict.get(m['jurusan_id'], 'Jurusan tidak ditemukan')

        # Ensure pdf_files is a list
        if 'pdf_files' not in m or not isinstance(m['pdf_files'], list):
            m['pdf_files'] = []

    page_name = "Materi"
    return render_template('pages/materi.html', materi=materi, page_name=page_name)
    
@app.route('/detail-materi/<string:m_id>')
@login_required
def detail_materi(m_id):
    try:
        # Get data from materi_service
        materi_response = requests.get(f'{MATERI_SERVICE_URL}/{m_id}')
        materi_response.raise_for_status()
        materi = materi_response.json()

        # Get data from kelas_service
        kelas_response = requests.get(KELAS_SERVICE_URL, headers=get_headers())
        kelas_response.raise_for_status()
        kelas_list = kelas_response.json()

        # Get data from jurusan_service
        jurusan_response = requests.get(JURUSAN_SERVICE_URL, headers=get_headers())
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

        page_name = "Materi"
        return render_template('pages/detail-materi.html', materi=materi, page_name=page_name)
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500
    

@app.route('/create-soal')
@login_required
def create_soal():
    try:
        # Ambil data jurusan
        jurusan_response = requests.get(f"{JURUSAN_SERVICE_URL}", headers=get_headers())
        jurusan_list = jurusan_response.json()

        # Ambil data kelas
        kelas_response = requests.get(f"{KELAS_SERVICE_URL}", headers=get_headers())
        kelas_list = kelas_response.json()
        
        # Ambil data Materi
        materi_response = requests.get(f"{MATERI_SERVICE_URL}", headers=get_headers())
        materi_list = materi_response.json()

        page_name = "Soal"
        return render_template('pages/create-soal.html', jurusans=jurusan_list, kelass=kelas_list, materis=materi_list,  page_name=page_name)
    except Exception as e:
        return render_template('pages/create-soal.html', error="Gagal mengambil data kelas dan jurusan.")

@app.route('/proxy/soal/insert', methods=['POST'])
@login_required
def proxy_insert_soal():
    data = request.get_json()
    data['user_id'] = session.get('user_id')
    try:
        response = requests.post(f'{SOAL_SERVICE_URL}/create', json=data, headers=get_headers())
        if response.status_code == 201:
            return jsonify({"message": "Soal berhasil ditambahkan.", "redirect_url": url_for('soal')}), 201
        else:
            return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"message": "Terjadi kesalahan pada server."}), 500
    
@app.route('/edit-soal/<string:soal_id>')
@login_required
def edit_soal(soal_id):

    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if session['role'] not in ['admin', 'guru']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        # Menyimpan pesan ke dalam session agar bisa diakses setelah redirect
        session['alert_message'] = alert_message
        return redirect(url_for('index'))

    # Memeriksa apakah pengguna memiliki role 'admin' atau 'guru'
    if session['role'] not in ['admin', 'guru']:
        alert_message = "Anda tidak memiliki akses ke halaman ini."
        # Menyimpan pesan ke dalam session agar bisa diakses setelah redirect
        session['alert_message'] = alert_message
        return redirect(url_for('index'))
    
    try:
        # Ambil data materi dari materi_service
        soal_response = requests.get(f'{SOAL_SERVICE_URL}/soal/{soal_id}', headers=get_headers())
        soal_response.raise_for_status()
        soal = soal_response.json()

        # Ambil data jurusan dan kelas dari jurusan_service dan kelas_service
        jurusan_response = requests.get(JURUSAN_SERVICE_URL, headers=get_headers())
        kelas_response = requests.get(KELAS_SERVICE_URL, headers=get_headers())
        materi_response = requests.get(MATERI_SERVICE_URL, headers=get_headers())
        jurusan_response.raise_for_status()
        kelas_response.raise_for_status()
        materi_response.raise_for_status()
        jurusan_list = jurusan_response.json()
        kelas_list = kelas_response.json()
        materi_list = materi_response.json()

        page_name = "Soal"
        return render_template('pages/edit-soal.html', soal=soal, jurusan_list=jurusan_list, kelas_list=kelas_list, materi_list=materi_list, page_name=page_name)
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500

@app.route('/proxy/soal/update/<string:soal_id>', methods=['POST'])
@login_required
def proxy_update_soal(soal_id):
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
        response = requests.put(
            f'{SOAL_SERVICE_URL}/update/{soal_id}',
            json=data,
            headers=get_headers()
        )
        response.raise_for_status()  # Menangani error HTTP

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
    try:
        # Dapatkan data dari soal_service
        soal_response = requests.get(f"{SOAL_SERVICE_URL}/soal", headers=get_headers())
        soal_response.raise_for_status()
        soals = soal_response.json()

    except requests.exceptions.RequestException as e:
        error_message = 'Layanan soal_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
        return render_template('pages/soal.html', error_message=error_message, page_name="Soal")

    try:
        # Dapatkan data dari kelas_service
        kelas_response = requests.get(KELAS_SERVICE_URL, headers=get_headers())
        kelas_response.raise_for_status()
        kelas_list = kelas_response.json()

    except requests.exceptions.RequestException as e:
        error_message = 'Layanan kelas_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
        return render_template('pages/soal.html', error_message=error_message, page_name="Soal")

    try:
        # Dapatkan data dari jurusan_service
        jurusan_response = requests.get(JURUSAN_SERVICE_URL, headers=get_headers())
        jurusan_response.raise_for_status()
        jurusan_list = jurusan_response.json()

    except requests.exceptions.RequestException as e:
        error_message = 'Layanan jurusan_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
        return render_template('pages/soal.html', error_message=error_message, page_name="Soal")
        
    try:
        # Dapatkan data dari materi_service
        materi_response = requests.get(MATERI_SERVICE_URL, headers=get_headers())
        materi_response.raise_for_status()
        materi_list = materi_response.json()

    except requests.exceptions.RequestException as e:
        error_message = 'Layanan materi_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
        return render_template('pages/soal.html', error_message=error_message, page_name="Soal")

    # Buat kamus (dictionary) untuk pencarian cepat
    kelas_dict = {kelas['_id']: kelas['nama_kelas'] for kelas in kelas_list}
    jurusan_dict = {jurusan['_id']: jurusan['nama_jurusan'] for jurusan in jurusan_list}
    materi_dict = {materi['_id']: materi['nama_materi'] for materi in materi_list}

    # Filter soal berdasarkan role
    jurusan_id = session.get('jurusan_id')

    if session['role'] == 'siswa':
        kelas_id = session.get('kelas_id')
        soals = [s for s in soals if s.get('jurusan_id') == jurusan_id and s.get('kelas_id') == kelas_id]

        # Ambil jawaban siswa dari soal_service
        try:
            jawaban_response = requests.get(f"{SOAL_SERVICE_URL}/jawaban?user_id={session['user_id']}", headers=get_headers())
            jawaban_response.raise_for_status()
            jawaban_list = jawaban_response.json()
        except requests.exceptions.RequestException as e:
            error_message = 'Layanan jawaban soal_service tidak dapat dihubungi. Pastikan layanan tersebut sudah berjalan.'
            return render_template('pages/soal.html', error_message=error_message, page_name="Soal")

        # Tambahkan nilai ke dalam soals
        for s in soals:
            jawaban = next((j for j in jawaban_list if j['soal_id'] == s['_id']), None)
            if jawaban:
                s['nilai'] = jawaban.get('nilai', None)
            else:
                s['nilai'] = None

    elif session['role'] == 'guru':
        # Dapatkan user_id dari session
        user_id = session['user_id']
        soals = [s for s in soals if s.get('jurusan_id') == jurusan_id and s.get('user_id') == user_id]

    for s in soals:
        s['nama_kelas'] = kelas_dict.get(s['kelas_id'], 'Kelas tidak ditemukan')
        s['nama_jurusan'] = jurusan_dict.get(s['jurusan_id'], 'Jurusan tidak ditemukan')
        s['nama_materi'] = materi_dict.get(s.get('materi_id'), 'Materi tidak ditemukan')

        # Konversi soal menjadi list (tanpa key-value pair)
        s['questions'] = [value for key, value in s.items() if key.startswith('question_')]

    page_name = "Soal"
    return render_template('pages/soal.html', soals=soals, page_name=page_name)

@app.route('/delete-soal/<soal_id>', methods=['DELETE'])
@login_required
def delete_soal(soal_id):
    try:
        # Hanya guru dan admin yang bisa menghapus soal
        if session['role'] not in ['guru', 'admin']:
            return jsonify({"message": "Akses ditolak."}), 403

        response = requests.delete(f"{SOAL_SERVICE_URL}/soal/{soal_id}", headers=get_headers())
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
        # Dapatkan data soal berdasarkan ID
        soal_response = requests.get(f"{SOAL_SERVICE_URL}/soal/{soal_id}", headers=get_headers())
        soal_response.raise_for_status()
        soal = soal_response.json()

        # Periksa apakah siswa sudah menjawab soal melalui API
        user_id = session.get('user_id')
        jawaban_response = requests.get(f"{SOAL_SERVICE_URL}/cek-jawaban/{soal_id}/{user_id}", headers=get_headers())
        jawaban_response.raise_for_status()
        jawaban_data = jawaban_response.json()
        already_answered = jawaban_data.get('already_answered', False)

        questions = [value for key, value in soal.items() if key.startswith('question_')]

        # Render halaman dengan informasi apakah sudah menjawab atau belum
        page_name = "Soal"
        return render_template('pages/answer-soal.html', soal_id=soal_id, questions=questions, already_answered=already_answered,  page_name=page_name)
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500



@app.route('/submit-jawaban', methods=['POST'])
@login_required
def submit_jawaban():
    data = request.form.to_dict()
    data['user_id'] = session.get('user_id')  # Tambahkan ID pengguna jika diperlukan
    try:
        response = requests.post(f"{SOAL_SERVICE_URL}/jawaban", json=data, headers=get_headers())
        response.raise_for_status()
        return jsonify({"message": "Jawaban berhasil dikirim."}), 201
    except requests.exceptions.RequestException as e:
        return jsonify({'message': str(e)}), 500

# KODE BARU DITAMBAH
@app.route('/koreksi-jawaban/<soal_id>')
@login_required
def koreksi_jawaban(soal_id):
    try:
        # Hanya guru dan admin yang bisa mengakses halaman ini
        if session['role'] not in ['guru', 'admin']:
            return jsonify({"message": "Akses ditolak."}), 403

        # Dapatkan semua jawaban dan soal untuk soal tertentu
        response = requests.get(f"{SOAL_SERVICE_URL}/jawaban/{soal_id}", headers=get_headers())
        response.raise_for_status()
        data = response.json()
        jawabans = data.get('jawabans', [])
        soal = data.get('soal', {})

        # Periksa apakah semua jawaban sudah dikoreksi
        all_corrected = all(jawaban.get('nilai') is not None for jawaban in jawabans)

        page_name = "Soal"
        return render_template(
            'pages/koreksi-jawaban.html',
            jawabans=jawabans,
            soal=soal,
            soal_id=soal_id,
            all_corrected=all_corrected,
            page_name=page_name
        )
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500


@app.route('/submit-koreksi/<jawaban_id>', methods=['POST'])
@login_required
def submit_koreksi(jawaban_id):
    data = request.form.to_dict()
    try:
        # Hanya guru dan admin yang bisa mengirim koreksi
        if session['role'] not in ['guru', 'admin']:
            return jsonify({"message": "Akses ditolak."}), 403

        response = requests.post(f"{SOAL_SERVICE_URL}/koreksi-jawaban/{jawaban_id}", json=data, headers=get_headers())
        response.raise_for_status()
        return jsonify({"message": "Koreksi berhasil dikirim."}), 200
    except requests.exceptions.RequestException as e:
        return jsonify({'message': str(e)}), 500
    
@app.route('/download-rekap/<soal_id>')
@login_required
def download_rekap(soal_id):
    try:
        # Hanya guru dan admin yang bisa mengakses halaman ini
        if session['role'] not in ['guru', 'admin']:
            return jsonify({"message": "Akses ditolak."}), 403

        # Dapatkan semua jawaban untuk soal tertentu
        response = requests.get(f"{SOAL_SERVICE_URL}/jawaban/{soal_id}", headers=get_headers())
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)

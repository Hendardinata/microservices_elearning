from flask import Flask, request, redirect, render_template, session, make_response
from flask_cors import CORS
from flask_session import Session
from werkzeug.security import check_password_hash
from pymongo import MongoClient
import os
from redis import Redis
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Inisialisasi aplikasi Flask
app = Flask(__name__, template_folder='argon-dashboard/templates', static_folder='argon-dashboard/assets')

# Mengatur Random Secret Key
app.secret_key = 'your-consistent-secret-key'

# Mengatur CORS (Cross-Origin Resource Sharing)
CORS(app, supports_credentials=True)  # Mengatur agar cookies dapat dikirim lintas domain

@app.route('/')
def index():
    return render_template('pages/landing-page.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)

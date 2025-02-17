import unittest
import requests
import time

class TestServiceResponseTime(unittest.TestCase):

    def test_auth_service_login(self):
        url = "http://localhost:8000/login"
        data = {
            'username': 'test_user',
            'password': 'test_password'
        }
        start_time = time.time()
        response = requests.post(url, data=data)
        response_time = time.time() - start_time
        print(f"Auth Service Login Response Time: {response_time:.4f} seconds")
        self.assertLess(response_time, 4, "Auth service login response time is too slow")
        self.assertEqual(response.status_code, 200, "Login failed or service not available")
    
    def test_hello_service_index(self):
        url = "http://localhost:5001/"
        start_time = time.time()
        response = requests.get(url)
        response_time = time.time() - start_time
        print(f"Hello Service Index Response Time: {response_time:.4f} seconds")
        self.assertLess(response_time, 5, "Hello service index response time is too slow")
        self.assertEqual(response.status_code, 200, "Failed to load index page or service not available")

    def test_user_service(self):
        url = "http://localhost:5000/users"  # Ganti dengan URL endpoint user_service
        start_time = time.time()
        response = requests.get(url)
        response_time = time.time() - start_time
        print(f"User Service Response Time: {response_time:.4f} seconds")
        self.assertLess(response_time, 5, "User service response time is too slow")
        self.assertEqual(response.status_code, 200, "Failed to load user service or service not available")

    def test_jurusan_service(self):
        url = "http://localhost:5004/jurusan"  # Ganti dengan URL endpoint jurusan_service
        start_time = time.time()
        response = requests.get(url)
        response_time = time.time() - start_time
        print(f"Jurusan Service Response Time: {response_time:.4f} seconds")
        self.assertLess(response_time, 5, "Jurusan service response time is too slow")
        self.assertEqual(response.status_code, 200, "Failed to load jurusan service or service not available")

    def test_kelas_service(self):
        url = "http://localhost:5002/kelas"  # Ganti dengan URL endpoint kelas_service
        start_time = time.time()
        response = requests.get(url)
        response_time = time.time() - start_time
        print(f"Kelas Service Response Time: {response_time:.4f} seconds")
        self.assertLess(response_time, 5, "Kelas service response time is too slow")
        self.assertEqual(response.status_code, 200, "Failed to load kelas service or service not available")

    def test_materi_service(self):
        url = "http://localhost:5003/materi"  # Ganti dengan URL endpoint materi_service
        start_time = time.time()
        response = requests.get(url)
        response_time = time.time() - start_time
        print(f"Materi Service Response Time: {response_time:.4f} seconds")
        self.assertLess(response_time, 5, "Materi service response time is too slow")
        self.assertEqual(response.status_code, 200, "Failed to load materi service or service not available")

    def test_soal_service(self):
        url = "http://localhost:5005/soal"  # Ganti dengan URL endpoint soal_service
        start_time = time.time()
        response = requests.get(url)
        response_time = time.time() - start_time
        print(f"Soal Service Response Time: {response_time:.4f} seconds")
        self.assertLess(response_time, 5, "Soal service response time is too slow")
        self.assertEqual(response.status_code, 200, "Failed to load soal service or service not available")

if __name__ == '__main__':
    unittest.main()

import http from 'k6/http';
import { check, sleep } from 'k6';

export let options = {
    scenarios: {
        load_test: {
            executor: 'constant-vus', // Load Testing
            vus: 20, // 20 Virtual Users
            duration: '30s',
        },
        stress_test: {
            executor: 'ramping-vus', // Stress Testing
            startVUs: 10,
            stages: [
                { duration: '10s', target: 50 }, // Naik ke 50 VUs dalam 10 detik
                { duration: '20s', target: 100 }, // Naik ke 100 VUs dalam 20 detik
                { duration: '20s', target: 150 }, // Naik ke 150 VUs dalam 20 detik
                { duration: '10s', target: 0 }, // Turun ke 0 VUs dalam 10 detik
            ],
        },
        soak_test: {
            executor: 'constant-vus', // Soak Testing
            vus: 10, // 10 Virtual Users
            duration: '5m', // Tes dalam 5 menit
        },
        spike_test: {
            executor: 'ramping-vus',
            startVUs: 10,
            stages: [
                { duration: '10s', target: 100 }, // Lonjakan ke 100 VUs dalam 10 detik
                { duration: '10s', target: 20 }, // Turun lagi ke 10 VUs dalam 10 detik
            ],
        },
        breakpoint_test: {
            executor: 'ramping-vus',
            startVUs: 1,
            stages: [
                { duration: '5s', target: 20 },
                { duration: '5s', target: 50 },
                { duration: '5s', target: 100 },
                { duration: '5s', target: 200 },
                { duration: '5s', target: 350 }, // Cari titik kegagalan API
                { duration: '5s', target: 0 },
            ],
        },
    },
};

export default function () {
    let url = 'http://host.docker.internal:5005/soal'; // Sesuaikan jika tidak pakai Docker
    let params = {
        headers: {
            'Authorization': 'sma_11_api_token',
        },
    };

    let res = http.get(url, params);

    check(res, {
        'status 200': (r) => r.status === 200,
        'response contains users': (r) => r.json().length > 0,
    });

    console.log(`Response status: ${res.status}, Body: ${res.body}`);

    sleep(1); // Simulasi jeda antar request
}

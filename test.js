// import http from 'k6/http';
// import { check, sleep } from 'k6';

// export let options = {
//     scenarios: {
//         load_test: {
//             executor: 'constant-vus', // Load Testing
//             vus: 20, // 20 Virtual Users
//             duration: '30s',
//         },
//         stress_test: {
//             executor: 'ramping-vus', // Stress Testing
//             startVUs: 10,
//             stages: [
//                 { duration: '10s', target: 50 }, // Naik ke 50 VUs dalam 10 detik
//                 { duration: '20s', target: 100 }, // Naik ke 100 VUs dalam 20 detik
//                 { duration: '20s', target: 150 }, // Naik ke 150 VUs dalam 20 detik
//                 { duration: '10s', target: 0 }, // Turun ke 0 VUs dalam 10 detik
//             ],
//         },
//         soak_test: {
//             executor: 'constant-vus', // Soak Testing
//             vus: 10, // 10 Virtual Users
//             duration: '5m', // Tes dalam 5 menit
//         },
//         spike_test: {
//             executor: 'ramping-vus',
//             startVUs: 10,
//             stages: [
//                 { duration: '10s', target: 100 }, // Lonjakan ke 100 VUs dalam 10 detik
//                 { duration: '10s', target: 20 }, // Turun lagi ke 10 VUs dalam 10 detik
//             ],
//         },
//         breakpoint_test: {
//             executor: 'ramping-vus',
//             startVUs: 1,
//             stages: [
//                 { duration: '5s', target: 20 },
//                 { duration: '5s', target: 50 },
//                 { duration: '5s', target: 100 },
//                 { duration: '5s', target: 200 },
//                 { duration: '5s', target: 350 }, // Cari titik kegagalan API
//                 { duration: '5s', target: 0 },
//             ],
//         },
//     },
// };

// export default function () {
//     let url = 'http://host.docker.internal:5005/soal'; // Sesuaikan jika tidak pakai Docker
//     let params = {
//         headers: {
//             'Authorization': 'sma_11_api_token',
//         },
//     };

//     let res = http.get(url, params);

//     check(res, {
//         'status 200': (r) => r.status === 200,
//         'response contains users': (r) => r.json().length > 0,
//     });

//     console.log(`Response status: ${res.status}, Body: ${res.body}`);

//     sleep(1); // Simulasi jeda antar request
// }


//CREATE USERS
// import http from 'k6/http';
// import { check } from 'k6';

// export let options = {
//     vus: 5,
//     duration: '5s',
// };

// export default function () {
//     let url = 'http://host.docker.internal:5005/create';

//     let payload = JSON.stringify({
//         soal: [
//             `Soal Test ${__VU}-${__ITER} - 1`,
//             `Soal Test ${__VU}-${__ITER} - 2`,
//             `Soal Test ${__VU}-${__ITER} - 3`
//         ],
//         kelas_id: "66a61c44b70cba3c548221db",
//         jurusan_id: "66a5d2c830a7ff62681cc61c",
//         materi_id: "679e3e1a1561e5f88508e110",
//         user_id: "66bba38a37b011ff78baec22",
//     });

//     let params = {
//         headers: {
//             'Authorization': 'sma_11_api_token', // Pastikan token valid
//             'Content-Type': 'application/json', // Pastikan dikirim sebagai JSON
//         },
//     };

//     console.log(`Sending payload: ${payload}`); // Debugging

//     let res = http.post(url, payload, params);

//     check(res, {
//         'status 201': (r) => r.status === 201,
//         'status 400 (Bad Request)': (r) => r.status === 400,
//     });

//     console.log(`Response status: ${res.status}, Body: ${res.body}`);
// }


import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = 'http://host.docker.internal:5006';
const API_TARGET = 'http://host.docker.internal:5004/jurusan';

// ==== PILIH SKENARIO YANG AKTIF DENGAN UNCOMMENT ====
export let options = {
    scenarios: {
        // --- Load Test ---
        load_test: {
            executor: 'constant-vus',
            vus: 20,
            duration: '60s',
        },

        // --- Stress Test ---
        // stress_test: {
        //     executor: 'ramping-vus',
        //     startVUs: 10,
        //     stages: [
        //         { duration: '10s', target: 50 },
        //         { duration: '20s', target: 100 },
        //         { duration: '20s', target: 150 },
        //         { duration: '10s', target: 0 },
        //     ],
        // },

        // --- Soak Test ---
        // soak_test: {
        //     executor: 'constant-vus',
        //     vus: 10,
        //     duration: '5m',
        // },

        // --- Spike Test ---
        // spike_test: {
        //     executor: 'ramping-vus',
        //     startVUs: 10,
        //     stages: [
        //         { duration: '10s', target: 100 },
        //         { duration: '10s', target: 20 },
        //     ],
        // },

        // --- Breakpoint Test ---
        // breakpoint_test: {
        //     executor: 'ramping-vus',
        //     startVUs: 1,
        //     stages: [
        //         { duration: '5s', target: 20 },
        //         { duration: '5s', target: 50 },
        //         { duration: '5s', target: 100 },
        //         { duration: '5s', target: 200 },
        //         { duration: '5s', target: 350 },
        //         { duration: '5s', target: 0 },
        //     ],
        // },
    },
};

// === Setup: Login untuk ambil token ===
export function setup() {
    const loginPayload = JSON.stringify({
        username: 'admin',      // Ganti sesuai dengan user yang valid
        password: '12qwaszx',   // Ganti sesuai password
    });

    const loginHeaders = {
        'Content-Type': 'application/json',
    };

    const loginRes = http.post(`${BASE_URL}/api/login`, loginPayload, {
        headers: loginHeaders,
    });

    check(loginRes, {
        'login sukses': (res) => res.status === 200,
        'token diterima': (res) => res.json('token') !== undefined,
    });

    const token = loginRes.json('token');
    return { token };
}

// === Function Utama: Kirim request dengan token ===
export default function (data) {
    const token = data.token;

    const headers = {
        'Authorization': `Bearer ${token}`,
    };

    const res = http.get(API_TARGET, { headers });

    check(res, {
        'status 200': (r) => r.status === 200,
        'body tidak kosong': (r) => r.body && r.body.length > 0,
    });

    sleep(1);
}



import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 15,
  duration: '5m',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<800'],
  },
};

const BASE = __ENV.BASE_URL || 'http://127.0.0.1:8000';

export default function () {
  const res1 = http.get(`${BASE}/api/health`);
  check(res1, { 'health 200': r => r.status === 200 });

  const me = http.get(`${BASE}/api/users/me`, { headers: { Authorization: 'Bearer test' }});
  check(me, { 'me ok': r => r.status === 200 || r.status === 401 });

  // Status poll sim for step 5
  const st = http.get(`${BASE}/api/episodes/status?id=fake`);
  check(st, { 'status ok-ish': r => [200, 404, 401].includes(r.status) });

  sleep(0.5);
}

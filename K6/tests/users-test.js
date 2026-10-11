/**
 * ============================================================================
 * USERS / CAPACITY TEST
 * ============================================================================
 *
 * МЕТА:
 * Визначити максимальну кількість одночасних користувачів, яку витримує API,
 * та зібрати метрики продуктивності для звіту.
 *
 * ДВА РЕЖИМИ:
 *
 * 1. Східчастий (за замовчуванням):
 *    k6 run users-test.js
 *    Профіль: 10 → 25 → 50 → 100 → 200 → 500 → 1000 VU за 8 хвилин.
 *    Показує динаміку деградації. Використовується для пошуку межі.
 *
 * 2. Фіксований:
 *    k6 run -e VUS=200 -e DURATION=2m users-test.js
 *    Тримає N VU протягом M хвилин. Використовується для чистих метрик
 *    на конкретному рівні навантаження.
 *
 * КОЖНА ІТЕРАЦІЯ:
 *   1. POST   /api/travel-plans          → 201 Created
 *   2. GET    /api/travel-plans          → 200 OK
 *   3. GET    /api/travel-plans/{id}     → 200 OK
 *   4. PUT    /api/travel-plans/{id}     → 200 OK (успішне оновлення)
 *   5. PUT    /api/travel-plans/{id}     → 409 Conflict (optimistic locking)
 *   6. DELETE /api/travel-plans/{id}     → 204 No Content
 *   7. GET    /api/travel-plans/{id}     → 404 Not Found (перевірка видалення)
 *
 * МЕТРИКИ:
 *   - http_req_duration (p50, p90, p95, p99)
 *   - http_req_failed (error rate)
 *   - http_reqs (throughput)
 *   - read_duration / write_duration (окремо)
 *   - conflict_count (409 від optimistic locking)
 *   - success_rate (успішні перевірки)
 *
 * ============================================================================
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';

// ──────────────────────── Кастомні метрики ────────────────────────

const readDuration = new Trend('read_duration', true);
const writeDuration = new Trend('write_duration', true);
const successRate = new Rate('success_rate');
const conflictCount = new Counter('conflict_count');

// ──────────────────────── Конфігурація ────────────────────────

const BASE = __ENV.API_URL || 'http://localhost:8000';
const JSON_HEADERS = { 'Content-Type': 'application/json' };

// Якщо VUS передано через -e VUS=200, використовуємо фіксований режим.
// Інакше — східчастий.
const FIXED_VUS = __ENV.VUS ? Number(__ENV.VUS) : null;
const FIXED_DURATION = __ENV.DURATION || '2m';

const fixedThresholds = {
    'http_req_duration': ['p(99)<5000'],
    'http_req_failed': ['rate<0.5'],        // м'яко — бо ми шукаємо межу
};

const stagedThresholds = {
    'http_req_duration': ['p(99)<5000'],
    'http_req_failed': ['rate<0.5'],
};

export const options = FIXED_VUS
    ? {
        // ──── Режим 1: Фіксоване навантаження ────
        vus: FIXED_VUS,
        duration: FIXED_DURATION,
        thresholds: fixedThresholds,
        userAgent: 'K6-UsersTest-Fixed/1.0',
    }
    : {
        // ──── Режим 2: Східчастий профіль ────
        scenarios: {
            capacity_search: {
                executor: 'ramping-vus',
                startVUs: 0,
                stages: [
                    { duration: '30s', target: 10 },
                    { duration: '1m',  target: 10 },
                    { duration: '1m',  target: 25 },
                    { duration: '1m',  target: 50 },
                    { duration: '1m',  target: 100 },
                    { duration: '1m',  target: 200 },
                    { duration: '1m',  target: 500 },
                    { duration: '1m',  target: 1000 },
                    { duration: '30s', target: 0 },
                ],
                gracefulRampDown: '30s',
                gracefulStop: '10s',
            },
        },
        thresholds: stagedThresholds,
        userAgent: 'K6-UsersTest-Staged/1.0',
    };

// ──────────────────────── Основна функція ────────────────────────

export default function () {
    // ── 1. Створити план (POST) ──
    const createRes = http.post(
        `${BASE}/api/travel-plans`,
        JSON.stringify({
            title: `Capacity Test ${__VU}-${__ITER}`,
            budget: 1000,
            currency: 'EUR',
        }),
        { headers: JSON_HEADERS, tags: { type: 'write', name: 'create_plan' } }
    );

    const createOk = check(createRes, {
        'create 201': (r) => r.status === 201,
    });
    writeDuration.add(createRes.timings.duration);
    successRate.add(createOk);

    if (createRes.status !== 201) {
        sleep(0.5);
        return;
    }

    const planId = createRes.json('id');
    const version = createRes.json('version');

    // ── 2. Список планів (GET) ──
    const listRes = http.get(`${BASE}/api/travel-plans?limit=10`, {
        tags: { type: 'read', name: 'list_plans' },
    });
    const listOk = check(listRes, {
        'list 200': (r) => r.status === 200,
    });
    readDuration.add(listRes.timings.duration);
    successRate.add(listOk);

    // ── 3. Отримати конкретний план (GET) ──
    const getRes = http.get(`${BASE}/api/travel-plans/${planId}`, {
        tags: { type: 'read', name: 'get_plan' },
    });
    const getOk = check(getRes, {
        'get 200': (r) => r.status === 200,
    });
    readDuration.add(getRes.timings.duration);
    successRate.add(getOk);

    // ── 4. Успішне оновлення (PUT) ──
    const updateRes = http.put(
        `${BASE}/api/travel-plans/${planId}`,
        JSON.stringify({ version: version, budget: 2000 }),
        { headers: JSON_HEADERS, tags: { type: 'write', name: 'update_plan' } }
    );
    const updateOk = check(updateRes, {
        'update 200': (r) => r.status === 200,
    });
    writeDuration.add(updateRes.timings.duration);
    successRate.add(updateOk);

    // ── 5. Конфлікт версій (PUT зі старою version → 409) ──
    const conflictRes = http.put(
        `${BASE}/api/travel-plans/${planId}`,
        JSON.stringify({ version: version, budget: 3000 }),
        { headers: JSON_HEADERS, tags: { type: 'write', name: 'conflict_put' } }
    );
    if (conflictRes.status === 409) {
        conflictCount.add(1);
    }
    check(conflictRes, {
        'conflict 409': (r) => r.status === 409,
    });

    // ── 6. Видалити план (DELETE) ──
    const deleteRes = http.del(
        `${BASE}/api/travel-plans/${planId}`,
        null,
        { tags: { type: 'write', name: 'delete_plan' } }
    );
    check(deleteRes, {
        'delete 204': (r) => r.status === 204,
    });

    // ── 7. Перевірити, що план видалено (GET → 404) ──
    const verifyRes = http.get(`${BASE}/api/travel-plans/${planId}`, {
        tags: { type: 'read', name: 'verify_deleted' },
    });
    check(verifyRes, {
        'verify deleted 404': (r) => r.status === 404,
    });

    // Пауза між ітераціями
    sleep(0.5);
}

// ──────────────────────── Setup & Teardown ────────────────────────

export function setup() {
    console.log('='.repeat(80));
    if (FIXED_VUS) {
        console.log(`USERS TEST — фіксоване навантаження ${FIXED_VUS} VU, ${FIXED_DURATION}`);
    } else {
        console.log('USERS TEST — східчастий профіль 10 → 1000 VU за 8 хвилин');
    }
    console.log(`Target API: ${BASE}`);
    console.log('='.repeat(80));
}

export function teardown() {
    console.log('='.repeat(80));
    console.log('USERS TEST completed');
    console.log('='.repeat(80));
}
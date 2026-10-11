/**
 * ============================================================================
 * STRESS TEST — пошук точки відмови і перевірка відновлення
 * ============================================================================
 *
 * МЕТА:
 *   1. Знайти точку деградації (коли checks < 95%)
 *   2. Знайти точку відмови / breaking point (коли checks < 50%)
 *   3. Перевірити, чи відновлюється система після зниження навантаження
 *
 * ПРОФІЛЬ:
 *   Фаза 1 — Ramp-up:     0 → 500 VU за 2 хв
 *   Фаза 2 — Stress:      500 → 1000 VU за 2 хв
 *   Фаза 3 — Hold peak:   1000 VU протягом 3 хв
 *   Фаза 4 — Recovery:    1000 → 10 VU за 30 сек
 *   Фаза 5 — Verify:      10 VU протягом 1 хв (перевірка відновлення)
 *
 * РЕЗУЛЬТАТ:
 *   - Графік деградації по VU
 *   - Точка breaking point
 *   - Метрики фази recovery — чи працює API після стресу
 *
 * ============================================================================
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate, Counter, Gauge } from 'k6/metrics';

// ──── Кастомні метрики ────

const readDuration = new Trend('read_duration', true);
const writeDuration = new Trend('write_duration', true);
const successRate = new Rate('success_rate');
const conflictCount = new Counter('conflict_count');

// Метрики для фаз (щоб окремо бачити recovery)
const recoverySuccessRate = new Rate('recovery_success_rate');
const recoveryDuration = new Trend('recovery_duration', true);
const phaseGauge = new Gauge('current_phase');

// ──── Конфігурація ────

const BASE = __ENV.API_URL || 'http://localhost:8000';
const JSON_HEADERS = { 'Content-Type': 'application/json' };

export const options = {
    scenarios: {
        stress: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                // Фаза 1: ramp-up до 500 VU
                { duration: '1m', target: 100 },
                { duration: '1m', target: 500 },

                // Фаза 2: стрес — до 1000 VU
                { duration: '1m', target: 750 },
                { duration: '1m', target: 1000 },

                // Фаза 3: тримаємо пік
                { duration: '3m', target: 1000 },

                // Фаза 4: різкий спад для перевірки recovery
                { duration: '30s', target: 10 },

                // Фаза 5: тримаємо 10 VU — перевірка відновлення
                { duration: '1m', target: 10 },
            ],
            gracefulRampDown: '10s',
            gracefulStop: '30s',
        },
    },

    thresholds: {
        // Ми НЕ очікуємо, що тест пройде — мета знайти межу.
        // Але фіксуємо recovery-метрики.
        'recovery_success_rate': ['rate>0.95'],   // відновлення має бути успішним
        'http_req_duration': ['p(99)<10000'],     // м'яко
    },
};

// ──── Основна функція ────

export default function () {
    // ── 1. Створити план (POST) ──
    const createRes = http.post(
        `${BASE}/api/travel-plans`,
        JSON.stringify({
            title: `Stress Test ${__VU}-${__ITER}`,
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

    // Фаза recovery: якщо ми на низькому VU — записуємо окремо
    if (__VU <= 10) {
        recoverySuccessRate.add(createOk);
        recoveryDuration.add(createRes.timings.duration);
    }

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
    check(listRes, { 'list 200': (r) => r.status === 200 });
    readDuration.add(listRes.timings.duration);

    // ── 3. Отримати конкретний план (GET) ──
    const getRes = http.get(`${BASE}/api/travel-plans/${planId}`, {
        tags: { type: 'read', name: 'get_plan' },
    });
    check(getRes, { 'get 200': (r) => r.status === 200 });
    readDuration.add(getRes.timings.duration);

    // ── 4. Успішне оновлення (PUT) ──
    const updateRes = http.put(
        `${BASE}/api/travel-plans/${planId}`,
        JSON.stringify({ version: version, budget: 2000 }),
        { headers: JSON_HEADERS, tags: { type: 'write', name: 'update_plan' } }
    );
    check(updateRes, { 'update 200': (r) => r.status === 200 });
    writeDuration.add(updateRes.timings.duration);

    // ── 5. Конфлікт версій (PUT старої version → 409) ──
    const conflictRes = http.put(
        `${BASE}/api/travel-plans/${planId}`,
        JSON.stringify({ version: version, budget: 3000 }),
        { headers: JSON_HEADERS, tags: { type: 'write', name: 'conflict_put' } }
    );
    if (conflictRes.status === 409) {
        conflictCount.add(1);
    }

    // ── 6. Видалити план (DELETE) ──
    const deleteRes = http.del(
        `${BASE}/api/travel-plans/${planId}`,
        null,
        { tags: { type: 'write', name: 'delete_plan' } }
    );
    check(deleteRes, { 'delete 204': (r) => r.status === 204 });

    // ── 7. Перевірити видалення (GET → 404) ──
    const verifyRes = http.get(`${BASE}/api/travel-plans/${planId}`, {
        tags: { type: 'read', name: 'verify_deleted' },
    });
    check(verifyRes, { 'verify deleted 404': (r) => r.status === 404 });

    sleep(0.5);
}

// ──── Setup & Teardown ────

export function setup() {
    console.log('='.repeat(80));
    console.log('STRESS TEST — пошук точки відмови і перевірка відновлення');
    console.log('='.repeat(80));
    console.log('Фаза 1 (1m):   0 → 100 VU');
    console.log('Фаза 2 (1m):   100 → 500 VU');
    console.log('Фаза 3 (1m):   500 → 750 VU');
    console.log('Фаза 4 (1m):   750 → 1000 VU');
    console.log('Фаза 5 (3m):   Тримаємо 1000 VU (stress)');
    console.log('Фаза 6 (30s):  1000 → 10 VU (спад)');
    console.log('Фаза 7 (1m):   Тримаємо 10 VU (recovery)');
    console.log('='.repeat(80));
}

export function teardown() {
    console.log('='.repeat(80));
    console.log('STRESS TEST completed');
    console.log('='.repeat(80));
}
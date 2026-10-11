/**
 * ============================================================================
 * SPIKE TEST — раптові сплески навантаження
 * ============================================================================
 *
 * МЕТА:
 *   1. Перевірити, як система реагує на раптовий сплеск навантаження
 *   2. Визначити, чи втрачаються запити під час сплеску
 *   3. Виміряти час відновлення після сплеску
 *
 * ПРОФІЛЬ:
 *   Фаза 1 — Baseline:  10 VU протягом 30 сек
 *   Фаза 2 — Ramp-up:   10 → 1000 VU за 10 сек (різко!)
 *   Фаза 3 — Spike:     1000 VU протягом 30 сек
 *   Фаза 4 — Drop:      1000 → 10 VU за 5 сек
 *   Фаза 5 — Recovery:  10 VU протягом 60 сек
 *
 * ОСОБЛИВОСТІ:
 *   - Окремі метрики для baseline, spike, recovery
 *   - Підрахунок "втрачених" запитів (timeouts, connection refused)
 *   - Метрика часу відновлення (коли повертається до baseline)
 *
 * ============================================================================
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';

// ──── Кастомні метрики ────

// Загальні
const readDuration = new Trend('read_duration', true);
const writeDuration = new Trend('write_duration', true);
const conflictCount = new Counter('conflict_count');

// Фазові (для розрізнення baseline / spike / recovery)
const baselineDuration = new Trend('baseline_duration', true);
const baselineSuccess = new Rate('baseline_success');

const spikeDuration = new Trend('spike_duration', true);
const spikeSuccess = new Rate('spike_success');

const recoveryDuration = new Trend('recovery_duration', true);
const recoverySuccess = new Rate('recovery_success');

// Втрачені запити (timeouts, conn refused, 5xx)
const lostRequests = new Counter('lost_requests');

// ──── Конфігурація ────

const BASE = __ENV.API_URL || 'http://localhost:8000';
const JSON_HEADERS = { 'Content-Type': 'application/json' };

// Час початку тесту — для визначення фази
const START_TIME = Date.now();

// Фази в секундах від початку
const PHASES = {
    BASELINE_END: 30,       // 0-30 сек — baseline
    RAMP_END: 40,           // 30-40 сек — ramp-up
    SPIKE_END: 70,          // 40-70 сек — spike
    DROP_END: 75,           // 70-75 сек — drop
    RECOVERY_END: 135,      // 75-135 сек — recovery
};

function getCurrentPhase() {
    const elapsed = (Date.now() - START_TIME) / 1000;
    if (elapsed < PHASES.BASELINE_END) return 'baseline';
    if (elapsed < PHASES.RAMP_END) return 'ramp';
    if (elapsed < PHASES.SPIKE_END) return 'spike';
    if (elapsed < PHASES.DROP_END) return 'drop';
    if (elapsed < PHASES.RECOVERY_END) return 'recovery';
    return 'after';
}

export const options = {
    scenarios: {
        spike: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                // 1. Baseline
                { duration: '5s',  target: 10 },
                { duration: '25s', target: 10 },

                // 2. RAMP-UP — різкий стрибок (10 сек)
                { duration: '10s', target: 1000 },

                // 3. SPIKE — тримаємо пік
                { duration: '30s', target: 1000 },

                // 4. DROP — різкий спад (5 сек)
                { duration: '5s',  target: 10 },

                // 5. RECOVERY — перевірка відновлення (60 сек)
                { duration: '60s', target: 10 },
            ],
            gracefulRampDown: '5s',
            gracefulStop: '10s',
        },
    },

    thresholds: {
        // Spike очікувано деградує — м'яко
        'http_req_duration': ['p(99)<10000'],

        // Але recovery має бути успішним
        'recovery_success': ['rate>0.90'],

        // Baseline має бути ідеальним
        'baseline_success': ['rate>0.99'],
    },
};

// ──── Основна функція ────

export default function () {
    const phase = getCurrentPhase();

    // ── 1. POST create ──
    const createRes = http.post(
        `${BASE}/api/travel-plans`,
        JSON.stringify({
            title: `Spike Test ${__VU}-${__ITER}`,
            budget: 1000,
            currency: 'EUR',
        }),
        { headers: JSON_HEADERS, tags: { type: 'write', name: 'create_plan', phase: phase } }
    );

    const createOk = check(createRes, {
        'create 201': (r) => r.status === 201,
    });

    // Записуємо в фазові метрики
    writeDuration.add(createRes.timings.duration);
    recordPhaseMetric(phase, createRes.timings.duration, createOk);

    // Трекінг втрачених запитів
    if (createRes.status === 0 || createRes.status >= 500) {
        lostRequests.add(1);
    }

    if (createRes.status !== 201) {
        sleep(0.3);
        return;
    }

    const planId = createRes.json('id');
    const version = createRes.json('version');

    // ── 2. GET list ──
    const listRes = http.get(`${BASE}/api/travel-plans?limit=10`, {
        tags: { type: 'read', name: 'list_plans', phase: phase },
    });
    check(listRes, { 'list 200': (r) => r.status === 200 });
    readDuration.add(listRes.timings.duration);

    // ── 3. GET by id ──
    const getRes = http.get(`${BASE}/api/travel-plans/${planId}`, {
        tags: { type: 'read', name: 'get_plan', phase: phase },
    });
    check(getRes, { 'get 200': (r) => r.status === 200 });

    // ── 4. PUT update ──
    const updateRes = http.put(
        `${BASE}/api/travel-plans/${planId}`,
        JSON.stringify({ version: version, budget: 2000 }),
        { headers: JSON_HEADERS, tags: { type: 'write', name: 'update_plan', phase: phase } }
    );
    check(updateRes, { 'update 200': (r) => r.status === 200 });

    // ── 5. PUT conflict (409) ──
    const conflictRes = http.put(
        `${BASE}/api/travel-plans/${planId}`,
        JSON.stringify({ version: version, budget: 3000 }),
        { headers: JSON_HEADERS, tags: { type: 'write', name: 'conflict_put', phase: phase } }
    );
    if (conflictRes.status === 409) {
        conflictCount.add(1);
    }

    // ── 6. DELETE ──
    const deleteRes = http.del(
        `${BASE}/api/travel-plans/${planId}`,
        null,
        { tags: { type: 'write', name: 'delete_plan', phase: phase } }
    );
    check(deleteRes, { 'delete 204': (r) => r.status === 204 });

    // ── 7. GET verify (404) ──
    const verifyRes = http.get(`${BASE}/api/travel-plans/${planId}`, {
        tags: { type: 'read', name: 'verify_deleted', phase: phase },
    });
    check(verifyRes, { 'verify deleted 404': (r) => r.status === 404 });

    // Пауза
    sleep(0.3);
}

// ──── Запис у фазові метрики ────

function recordPhaseMetric(phase, duration, success) {
    switch (phase) {
        case 'baseline':
            baselineDuration.add(duration);
            baselineSuccess.add(success);
            break;
        case 'spike':
            spikeDuration.add(duration);
            spikeSuccess.add(success);
            break;
        case 'recovery':
            recoveryDuration.add(duration);
            recoverySuccess.add(success);
            break;
    }
}

// ──── Setup & Teardown ────

export function setup() {
    console.log('='.repeat(80));
    console.log('SPIKE TEST — раптові сплески навантаження');
    console.log('='.repeat(80));
    console.log('Фаза 1 (30s):  Baseline, 10 VU');
    console.log('Фаза 2 (10s):  Ramp-up  10 → 1000 VU (різкий стрибок)');
    console.log('Фаза 3 (30s):  SPIKE, 1000 VU (тримаємо пік)');
    console.log('Фаза 4 (5s):   DROP   1000 → 10 VU');
    console.log('Фаза 5 (60s):  RECOVERY, 10 VU (перевірка відновлення)');
    console.log('='.repeat(80));
    console.log('Загальна тривалість: ~2 хв 15 сек');
    console.log('='.repeat(80));
}

export function teardown() {
    console.log('='.repeat(80));
    console.log('SPIKE TEST completed');
    console.log('='.repeat(80));
}
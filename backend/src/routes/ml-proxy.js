import express, { Router } from 'express';

const READ_TIMEOUT_MS = 10_000;
// Node's fetch gives up waiting for response headers after 300 s; stay just under it.
const AGENT_TIMEOUT_MS = 280_000;
const BONUS_QUERY = ['agent', 'year'];
const KV_QUERY = ['agent', 'quarter'];
const KV_SCENARIO_QUERY = [...KV_QUERY, 'extra_kasko', 'extra_priority', 'prolonged', 'due'];

/** GET path → allowed query keys. Anything else never reaches the ML service. */
const READ_PATHS = {
  '/plans': BONUS_QUERY,
  '/bonuses': BONUS_QUERY,
  '/model': [],
  '/config': [],
  '/forecast': BONUS_QUERY,
  '/bonus/scenarios': BONUS_QUERY,
  '/bonus/forecast': BONUS_QUERY,
  '/kv/options': [],
  '/kv/rules': [],
  '/kv/cabinet': KV_QUERY,
  '/kv/recommendations': ['agent'],
};
const POST_PATHS = {
  '/kv/simulate': READ_TIMEOUT_MS,
  '/agents/review': AGENT_TIMEOUT_MS,
  '/agents/kv-review': AGENT_TIMEOUT_MS,
  '/agents/ask': AGENT_TIMEOUT_MS,
};

/** FastAPI returns {detail: string | validation[]}; normalize to the backend's {success, error} envelope. */
function errorText(body, status) {
  if (typeof body?.detail === 'string') return body.detail;
  if (Array.isArray(body?.detail)) return 'Некорректные параметры запроса';
  return `ML-сервис ответил ошибкой ${status}`;
}

async function call(res, url, init, timeoutMs) {
  try {
    return await fetch(url, { ...init, signal: AbortSignal.timeout(timeoutMs) });
  } catch (err) {
    const timedOut = err?.name === 'TimeoutError';
    res.status(timedOut ? 504 : 503).json({
      success: false,
      error: timedOut
        ? 'ML-сервис не ответил вовремя'
        : 'ML-сервис недоступен — запустите его: ml/.venv/bin/uvicorn metrixs_ml.api:app --app-dir ml --port 8000',
    });
    return null;
  }
}

async function forwardJson(res, url, init, timeoutMs) {
  const response = await call(res, url, init, timeoutMs);
  if (!response) return;
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    res.status(response.status).json({ success: false, error: errorText(body, response.status) });
    return;
  }
  res.json(body);
}

/** Excel export: stream bytes and the download headers through unchanged. */
async function forwardFile(res, url) {
  const response = await call(res, url, { method: 'GET' }, READ_TIMEOUT_MS);
  if (!response) return;
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    res.status(response.status).json({ success: false, error: errorText(body, response.status) });
    return;
  }
  res.set('content-type', response.headers.get('content-type') ?? 'application/octet-stream');
  const disposition = response.headers.get('content-disposition');
  if (disposition) res.set('content-disposition', disposition);
  res.send(Buffer.from(await response.arrayBuffer()));
}

function withQuery(baseUrl, path, query, keys) {
  const url = new URL(path, baseUrl);
  for (const key of keys) {
    if (typeof query[key] === 'string' && query[key]) url.searchParams.set(key, query[key]);
  }
  return url;
}

/** Proxies a fixed allow-list of ML-service endpoints; arbitrary paths and query keys never reach it. */
export function createMlProxy(baseUrl) {
  const router = Router();
  router.use(express.json({ limit: '10kb' }));

  for (const [path, keys] of Object.entries(READ_PATHS)) {
    router.get(path, (req, res, next) => {
      forwardJson(res, withQuery(baseUrl, path, req.query, keys), { method: 'GET' }, READ_TIMEOUT_MS).catch(next);
    });
  }

  router.get('/kv/export', (req, res, next) => {
    forwardFile(res, withQuery(baseUrl, '/kv/export', req.query, KV_SCENARIO_QUERY)).catch(next);
  });

  for (const [path, timeout] of Object.entries(POST_PATHS)) {
    router.post(path, (req, res, next) => {
      const init = { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(req.body ?? {}) };
      forwardJson(res, new URL(path, baseUrl), init, timeout).catch(next);
    });
  }

  return router;
}

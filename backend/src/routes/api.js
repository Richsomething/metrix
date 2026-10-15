import { Router } from 'express';
import { buildDashboard, buildFilterOptions } from '../services/aggregations.js';

const FILTER_KEYS = ['group', 'branch', 'agent', 'line', 'year'];
const OPTION_KEY = { group: 'groups', branch: 'branches', agent: 'agents', line: 'lines', year: 'years' };

/** Keeps only known filter values so arbitrary query input never reaches the aggregations. */
function parseFilters(query, options) {
  return FILTER_KEYS.reduce((filters, key) => {
    const raw = typeof query[key] === 'string' ? query[key] : '';
    if (!raw) return filters;
    if (!options[OPTION_KEY[key]].includes(raw)) {
      throw Object.assign(new Error(`Неизвестное значение фильтра «${key}»`), { status: 400 });
    }
    return { ...filters, [key]: raw };
  }, {});
}

export function createApiRouter(dataset) {
  const router = Router();
  const options = buildFilterOptions(dataset);

  router.get('/health', (_req, res) => res.json({ success: true, data: { status: 'ok' } }));

  router.get('/filters', (_req, res) => res.json({ success: true, data: options }));

  router.get('/dashboard', (req, res) => {
    const filters = parseFilters(req.query, options);
    res.json({ success: true, data: buildDashboard(dataset, filters) });
  });

  return router;
}

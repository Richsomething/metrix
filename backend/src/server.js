import express from 'express';
import cors from 'cors';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadDataset } from './data/excel-loader.js';
import { createApiRouter } from './routes/api.js';
import { createMlProxy } from './routes/ml-proxy.js';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const PORT = Number(process.env.PORT ?? 3000);
const DATA_FILE = process.env.DATA_FILE ?? path.join(ROOT, 'data', 'data.xlsx');
const CORS_ORIGIN = process.env.CORS_ORIGIN ?? 'http://localhost:4200';
const ML_URL = process.env.ML_URL ?? 'http://127.0.0.1:8000';

async function main() {
  const dataset = await loadDataset(DATA_FILE);
  console.info(
    `Загружено: сборы ${dataset.collections.length}, пролонгации ${dataset.prolongations.length}, агенты ${dataset.agents.length}`,
  );

  const app = express();
  app.use(cors({ origin: CORS_ORIGIN }));
  // API-only server: a browser opening the root goes to the dashboard instead of «Cannot GET /».
  app.get('/', (_req, res) => res.redirect(CORS_ORIGIN));
  app.use('/api/ml', createMlProxy(ML_URL));
  app.use('/api', createApiRouter(dataset));

  app.use((err, _req, res, _next) => {
    const status = err.status ?? 500;
    if (status >= 500) console.error(err);
    res.status(status).json({ success: false, error: status >= 500 ? 'Внутренняя ошибка сервера' : err.message });
  });

  app.listen(PORT, () => console.info(`API: http://localhost:${PORT}/api`));
}

main().catch((err) => {
  console.error('Не удалось запустить сервер:', err);
  process.exit(1);
});

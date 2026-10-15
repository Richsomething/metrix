import { readFile } from 'node:fs/promises';
import * as XLSX from 'xlsx';

const EXCEL_EPOCH_MS = Date.UTC(1899, 11, 30);
const MS_PER_DAY = 86_400_000;

const SHEETS = {
  branchGroups: 'группа филиала',
  agents: 'дата 1 АД агента',
  collections: 'сборы',
  prolongations: 'пролонг',
};

function toDate(value) {
  if (value instanceof Date) return value;
  if (typeof value === 'number') return new Date(EXCEL_EPOCH_MS + value * MS_PER_DAY);
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }
  return null;
}

function toNumber(value) {
  if (typeof value === 'number') return value;
  const parsed = Number(String(value ?? '').replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : 0;
}

function toText(value) {
  return value === null || value === undefined ? '' : String(value).trim();
}

/**
 * Reads a sheet into objects keyed by header. The header is the first non-empty row
 * («пролонг» starts on row 2); columns stop at the first blank header, which drops
 * the stale pivot table placed to the right of the data.
 */
function readSheet(workbook, name) {
  const sheet = workbook.Sheets[name];
  if (!sheet) throw new Error(`Лист «${name}» не найден в файле`);

  const allRows = XLSX.utils.sheet_to_json(sheet, { header: 1, raw: true, defval: null });
  const headerIndex = allRows.findIndex((row) => row.some((cell) => toText(cell)));
  const headerRow = allRows[headerIndex] ?? [];
  const dataRows = allRows.slice(headerIndex + 1);
  const firstBlank = headerRow.findIndex((h) => !toText(h));
  const headers = headerRow.slice(0, firstBlank === -1 ? headerRow.length : firstBlank).map(toText);

  return dataRows.map((row) => Object.fromEntries(headers.map((header, i) => [header, row[i] ?? null])));
}

export async function loadDataset(filePath) {
  const workbook = XLSX.read(await readFile(filePath), { type: 'buffer', dense: true });

  const branchGroups = new Map(
    readSheet(workbook, SHEETS.branchGroups).map((r) => [toText(r['Филиал']), toText(r['группа'])]),
  );
  const groupOf = (branch) => branchGroups.get(branch) ?? 'Без группы';

  const agents = readSheet(workbook, SHEETS.agents)
    .filter((r) => r['AGENTISN'])
    .map((r) => ({
      id: toText(r['AGENTISN']),
      name: toText(r['Агент']),
      firstContractDate: toDate(r['Дата 1 АД']),
    }));

  const collections = readSheet(workbook, SHEETS.collections)
    .filter((r) => r['Договор'])
    .map((r) => {
      const branch = toText(r['Филиал']);
      return {
        period: toDate(r['Отч период']),
        signedAt: toDate(r['Дата заключения']),
        line: toText(r['Линия бизнеса']),
        contract: toText(r['Договор']),
        product: toText(r['Продукт']),
        branch,
        group: groupOf(branch),
        agentId: toText(r['AGENTISN']),
        agent: toText(r['Агент']),
        partner: toText(r['Партнер']),
        amount: toNumber(r['Сумма сборов']),
      };
    });

  const prolongations = readSheet(workbook, SHEETS.prolongations)
    .filter((r) => r['Договор к пролонгации'])
    .map((r) => {
      const branch = toText(r['Филиал']);
      return {
        branch,
        group: groupOf(branch),
        startAt: toDate(r['Дата начала']),
        endAt: toDate(r['Дата окончания']),
        agentId: toText(r['Агент ISN']),
        agent: toText(r['Агент']),
        partner: toText(r['Партнер']),
        product: toText(r['Продукт страхования']),
        line: toText(r['Линия бизнеса']),
        contract: toText(r['Договор к пролонгации']),
        prolongedContract: toText(r['Пролонгация']),
      };
    });

  return { agents, collections, prolongations };
}

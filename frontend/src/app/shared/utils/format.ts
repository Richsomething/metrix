const MILLION = 1_000_000;
const THOUSAND = 1_000;

const integer = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });
const oneDecimal = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 });

/** Compact money: 20 084 843 → «20,1 млн». */
export function formatCompact(value: number): string {
  const abs = Math.abs(value);
  if (abs >= MILLION) return `${oneDecimal.format(value / MILLION)} млн`;
  if (abs >= THOUSAND) return `${oneDecimal.format(value / THOUSAND)} тыс`;
  return integer.format(value);
}

/** Full integer with thousands separators: 20084843.61 → «20 084 844». */
export function formatInteger(value: number): string {
  return integer.format(value);
}

const twoDecimals = new Intl.NumberFormat('ru-RU', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const significant = new Intl.NumberFormat('ru-RU', { maximumSignificantDigits: 3 });

/** Money that may be tiny (bonuses): compact from a thousand up, kopecks below. */
export function formatMoney(value: number): string {
  return Math.abs(value) >= THOUSAND ? formatCompact(value) : twoDecimals.format(value);
}

/** Percent with 3 significant digits, so 0.0000134 % stays visible instead of rounding to 0. */
export function formatPercent(value: number): string {
  return `${significant.format(value)} %`;
}

export function formatYears(value: number): string {
  return `${oneDecimal.format(value)} г.`;
}

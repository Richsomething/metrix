import { ChartTokens } from '../../../core/services/theme.service';
import { NamedValue } from '../../../core/models/dashboard.model';
import { ChartView } from '../../../shared/components/chart-card/chart-card.component';
import { formatInteger } from '../../../shared/utils/format';
import { horizontalBars, timeColumns } from './base';

const COUNT = { format: formatInteger, tableFormat: formatInteger, valueLabel: 'Договоров' };

export const prolongByMonthChart = (items: NamedValue[], t: ChartTokens): ChartView =>
  timeColumns(items, t, { ...COUNT, nameLabel: 'Месяц окончания' });

export const prolongByAgentChart = (items: NamedValue[], t: ChartTokens): ChartView =>
  horizontalBars(items, t, { ...COUNT, nameLabel: 'Агент' });

export const prolongByProductChart = (items: NamedValue[], t: ChartTokens): ChartView =>
  horizontalBars(items, t, { ...COUNT, nameLabel: 'Продукт' });

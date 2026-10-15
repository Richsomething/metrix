export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

export interface NamedValue {
  name: string;
  value: number;
}

export interface FilterOptions {
  groups: string[];
  branches: string[];
  agents: string[];
  lines: string[];
  years: string[];
}

export interface DashboardFilters {
  group: string;
  branch: string;
  agent: string;
  line: string;
  year: string;
}

export type FilterKey = keyof DashboardFilters;

export const EMPTY_FILTERS: DashboardFilters = {
  group: '',
  branch: '',
  agent: '',
  line: '',
  year: '',
};

export interface Kpi {
  total: number;
  refunds: number;
  contracts: number;
  avgPerContract: number;
  prolongationsDue: number;
}

export interface SeriesMatrix {
  quarters: string[];
  series: { name: string; values: number[] }[];
}

export interface Heatmap {
  quarters: string[];
  agents: string[];
  /** [quarterIndex, agentIndex, value] */
  values: [number, number, number][];
}

export interface AgentTenure extends NamedValue {
  years: number;
}

export interface DashboardData {
  kpi: Kpi;
  byQuarter: NamedValue[];
  byQuarterLine: SeriesMatrix;
  byAgent: NamedValue[];
  byBranch: NamedValue[];
  byGroup: NamedValue[];
  topProducts: NamedValue[];
  agentQuarterHeatmap: Heatmap;
  agentTenure: AgentTenure[];
  prolongByMonth: NamedValue[];
  prolongByAgent: NamedValue[];
  prolongByProduct: NamedValue[];
}

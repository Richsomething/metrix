import { Analysis, AuditVerdict, ModelUse, MotivationLetter, ToolCall } from './bonus.model';

/**
 * Agency reward (АВ) cabinet — a separate mechanism from the overperformance bonus.
 * Rate per line = base + Доп.АВ1 (dynamics) + Доп.АВ2 (penetration) + Доп.АВ3 (prolongation). Shapes mirror the ML API.
 */

export type KvScenario = 'base' | 'cautious' | 'optimistic';
export type KvQuarterKind = 'fact' | 'nowcast' | 'forecast';
export type KvComponentKey = 'kaskoBase' | 'd1' | 'd2' | 'd3';

/** [upper bound (exclusive, null = no bound), value] */
export type KvBand = [number | null, number];

export interface KvOptions {
  agents: string[];
  quarters: string[];
  currentQuarter: string;
  asOf: string;
  source: string;
  currentQuarterHasData: boolean;
}

export interface KvRuleInfo {
  id: string;
  status: 'demo' | 'approved';
  title: string;
  source: string;
  validFrom: string;
  validTo: string | null;
}

export interface KvLineRate {
  line: string;
  title: string;
  base: number | null;
  d1: number;
  d2: number;
  d3: number;
  total: number | null;
  capped: boolean;
  note: string | null;
}

export interface KvProlongation {
  due: number;
  prolonged: number | null;
  rate: number | null;
  dueEstimated: boolean;
  missing: string | null;
}

export interface KvMetrics {
  dvs: number;
  dvsPrevious: number;
  priority: number;
  dynamics: number;
  dynamicsBase: number;
  dynamicsFloorApplied: boolean;
  penetration: number | null;
  prolongation: KvProlongation;
}

export interface KvComponents {
  kaskoBase: {
    rate: number | null;
    newcomer: boolean;
    group: string | null;
    scaleGroup: string | null;
    scaleIndex: number | null;
    scale: KvBand[] | null;
  };
  d1: { value: number; bandIndex: number; bands: KvBand[] };
  d2: { value: number; above: number; bonus: number };
  d3: { value: number; atLeast: number; bonus: number };
}

export interface KvRate {
  quarter: string;
  reporting: string;
  previous: string;
  rule: KvRuleInfo;
  basis: { quarter: string; kind: KvQuarterKind; kindTitle: string }[];
  status: 'fact' | 'forecast';
  statusTitle: string;
  metrics: KvMetrics;
  components: KvComponents;
  rates: KvLineRate[];
  amountsReporting: Record<string, number>;
}

export interface KvIncomeLine {
  line: string;
  title: string;
  base: number;
  rate: number;
  kv: number;
  zeroBase: boolean;
}

export interface KvIncome {
  quarter: string;
  scenario: KvScenario;
  scenarioTitle: string;
  kind: KvQuarterKind;
  kindTitle: string;
  lines: KvIncomeLine[];
  unrated: { line: string; title: string; amount: number }[];
  base: number;
  kv: number;
  effectiveRate: number | null;
  effectiveRateNote: string;
}

export interface KvEffects {
  salesEffect: number;
  salesEffectNote: string;
  rateEffect: number;
  rateEffectNote: string;
  total: number;
}

export interface KvContracts {
  kasko: { avgCheck: number | null; contracts: number | null };
  priority: { avgCheck: number | null; contracts: number | null };
  note: string;
}

export interface KvPlanStep {
  component: KvComponentKey;
  title: string;
  target: string;
  from: number | null;
  to: number;
  needs: {
    dvs?: number;
    priority?: number;
    prolonged?: number;
    due?: number;
    dueEstimated?: boolean;
  };
  gain: Record<string, number>;
  blocked?: string;
  salesNote?: string | null;
}

export interface KvPlanOption {
  key: string;
  title: string;
  kasko: number;
  priority: number;
  prolonged: number | null;
  contracts: KvContracts;
  rates: KvLineRate[];
  components: Record<KvComponentKey, number | null>;
  gain: Record<string, number>;
  effects: KvEffects;
}

export interface KvPlan {
  available: boolean;
  reason?: string;
  quarter?: string;
  salesQuarter?: string;
  steps?: KvPlanStep[];
  options?: KvPlanOption[];
  note?: string;
}

export interface KvAgentInfo {
  branch: string;
  group: string | null;
  firstAd: string | null;
  newcomer: boolean;
}

export interface KvCabinet {
  agent: string;
  agentInfo: KvAgentInfo;
  quarter: string;
  nextQuarter: string;
  asOf: string;
  source: string;
  currentRate: KvRate;
  nextRate: KvRate;
  nextRateByScenario: Record<KvScenario, { line: string; total: number | null }[]>;
  income: { current: Record<KvScenario, KvIncome>; next: Record<KvScenario, KvIncome> };
  scenarioNote: string;
  plan: KvPlan;
  assumptions: string[];
}

export interface KvAdditions {
  extra_kasko: number;
  extra_priority: number;
  prolonged: number | null;
  due: number | null;
}

export interface KvRateBrief {
  quarter: string;
  rates: KvLineRate[];
  components: Record<KvComponentKey, number | null>;
  metrics: KvMetrics;
  status: string;
}

export interface KvSimulation {
  agent: string;
  quarter: string;
  nextQuarter: string;
  baseline: { nextRate: KvRateBrief; incomeCurrent: KvIncome; incomeNext: KvIncome };
  scenario: { nextRate: KvRateBrief; incomeCurrent: KvIncome; incomeNext: KvIncome };
  contracts: KvContracts;
  effects: KvEffects;
}

export interface KvReviewReport {
  agent: string;
  quarter: string;
  analysis: Analysis;
  letter: MotivationLetter;
  audit: AuditVerdict;
  revisions: number;
  tool_calls: ToolCall[];
  models: ModelUse[];
}

/** Main page: what to prolong from the КАСКО portfolio and what to sell, for the open quarter. */
export interface KvPortfolioContract {
  contract: string;
  endAt: string;
  expired: boolean;
}

export interface KvPortfolioGroup {
  line: string;
  title: string;
  product: string;
  count: number;
  contracts: KvPortfolioContract[];
}

export interface KvSellRow {
  line: string;
  title: string;
  priority: boolean;
  rate: number;
  kvPerUnit: number;
  planAmount: number;
  avgCheck: number | null;
  planContracts: number | null;
  products: { product: string; amount: number; contracts: number }[];
}

export interface KvRecommendations {
  agent: string;
  quarter: string;
  nextQuarter: string;
  asOf: string;
  income: { current: number; next: number; currentBase: number; nextBase: number };
  rates: {
    line: string;
    title: string;
    base: number | null;
    current: number;
    next: number | null;
    nextWithPlan: number | null;
    cappedWithPlan: boolean;
    addedWithPlan: number | null;
    collections: number;
    /** Contracts behind each rate: quarter T's rate comes from the sales of T−1. */
    contracts: { current: number; next: number; nextWithPlan: number };
  }[];
  portfolio: {
    lines: string[] | null;
    due: number;
    needed: number;
    atLeast: number;
    bonus: number;
    expired: number;
    gain: Record<string, number>;
    effects: KvEffects | null;
    groups: KvPortfolioGroup[];
  };
  sell: {
    unit: number;
    total: number;
    kasko: number;
    priority: number;
    mix: string | null;
    perRenewal: number | null;
    effects: KvEffects | null;
    componentsAfter: Record<KvComponentKey, number | null> | null;
    rows: KvSellRow[];
  };
  planEffect: KvEffects | null;
  planComponents: {
    before: Record<KvComponentKey, number | null>;
    after: Record<KvComponentKey, number | null> | null;
  };
  steps: KvPlanStep[];
  notes: string[];
}

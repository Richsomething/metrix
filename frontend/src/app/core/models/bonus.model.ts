export interface Contribution {
  key: string;
  label: string;
  value: number;
}

export interface PlanBonus {
  amount: number;
  overperformance: number;
  capped: boolean;
  refundPenalized: boolean;
}

/** `completed`: quarter ended, fact known, bonus calculated. `forecast`: next quarter — plan only. */
export type PlanKind = 'completed' | 'forecast';

export interface PlanRow {
  agent: string;
  quarter: string;
  kind: PlanKind;
  /** Model output: «рекомендуемый план на основе прогноза». */
  recommendedPlan: number;
  /** Management-approved plan — absent in the export. */
  approvedPlan: number | null;
  bonusBasis: 'recommended_plan' | null;
  fact: number | null;
  refundShare: number | null;
  completion: number | null;
  bonus: PlanBonus | null;
  contributions: Contribution[];
}

export interface BonusSummary {
  agent: string;
  bonus: number;
  recommendedPlan: number;
  fact: number;
  quarters: number;
  completion: number;
}

export interface ModelScore {
  name: string;
  title: string;
  wape: number;
  mape: number;
  bias: number;
  quarters: number;
}

export interface ModelMetrics {
  trainedAt: string;
  datasetNote: string;
  asOf: string;
  lastCompletedQuarter: string;
  futureRowsExcluded: number;
  chosen: string;
  scores: ModelScore[];
  plannedQuarters: string[];
  forecastQuarter: string | null;
  agents: string[];
}

export interface ForecastInfo {
  quarter: string | null;
  rows: { agent: string; recommendedPlan: number; contributions: Contribution[] }[];
  totalRecommendedPlan: number;
  limitation: string;
}

export interface BonusConfig {
  rate: number;
  threshold: number;
  cap_per_quarter: number;
  max_refund_share: number;
  refund_penalty: number;
}

export interface BonusScenario {
  key: string;
  title: string;
  fact: number;
  refundShare: number;
  completion: number;
  overperformance: number;
  amount: number;
  capped: boolean;
  refundPenalized: boolean;
}

export interface ScenarioSet {
  demo: true;
  agent: string;
  quarter: string;
  plan: number;
  planSource: string;
  config: BonusConfig;
  scenarios: BonusScenario[];
}

export interface BonusCurvePoint {
  fact: number;
  bonus: number;
  bonus_high_refunds: number;
}

/** Next-quarter bonus outlook for one employee: bonus as a function of collections. */
export interface BonusForecast {
  agent: string;
  quarter: string;
  forecastCollections: number;
  forecastBonus: number;
  threshold: number;
  capReachedAt: number | null;
  lastFact: number | null;
  lastQuarter: string | null;
  config: BonusConfig;
  curve: BonusCurvePoint[];
  note: string;
}

export interface BonusFilters {
  agent: string;
  year: string;
}

export interface Analysis {
  summary: string;
  strengths: string[];
  risks: string[];
  plan_drivers: string[];
}

export interface MotivationLetter {
  title: string;
  body: string;
  next_steps: string[];
}

export interface AuditVerdict {
  approved: boolean;
  issues: string[];
}

export interface ToolCall {
  role: string;
  name: string;
  input: Record<string, unknown>;
}

export interface ModelUse {
  role: string;
  model: string;
  fallback_reason: string | null;
}

/** Deterministic bonus calculation for a completed quarter — never produced by the LLM. */
export interface ReviewBonus {
  recommendedPlan: number;
  fact: number;
  completionPct: number;
  bonusThreshold: number;
  overperformance: number;
  amount: number;
  capped: boolean;
  refundPenalized: boolean;
  basis: string;
}

export interface ReviewReport {
  agent: string;
  quarter: string;
  bonus: ReviewBonus;
  analysis: Analysis;
  letter: MotivationLetter;
  audit: AuditVerdict;
  revisions: number;
  tool_calls: ToolCall[];
  models: ModelUse[];
}

export interface AskReport {
  answer: string;
  tool_calls: ToolCall[];
  models: ModelUse[];
}

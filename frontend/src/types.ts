export interface ChainEntry {
  font: string;
  verdict: "hit" | "miss";
  covered: string[];
  missing: string[];
}

export type Severity = "error" | "warning" | "info";

export interface Diagnostic {
  code: string;
  severity: Severity;
  message: string;
  fix: string | null;
}

export type ClusterStatus = "ok" | "partial" | "missing";

export interface ClusterResult {
  index: number;
  text: string;
  start: number;
  end: number;
  codepoints: string[];
  names: string[];
  categories: string[];
  status: ClusterStatus;
  resolvedFont: string | null;
  bestPartialFont: string | null;
  chain: ChainEntry[];
  diagnostics: Diagnostic[];
}

export interface Summary {
  total: number;
  ok: number;
  partial: number;
  missing: number;
  errors: number;
  warnings: number;
}

export interface DiagnoseResponse {
  clusters: ClusterResult[];
  globalDiagnostics: Diagnostic[];
  summary: Summary;
  effectiveOrder: string[];
  segmenter: string;
}

export interface Defaults {
  sampleText: string;
  manifest: unknown;
  priority: string[];
}

export interface ValidateResponse {
  ok: boolean;
  errors: string[];
  fontCount: number;
  codepointCount: number;
  priority: string[];
}

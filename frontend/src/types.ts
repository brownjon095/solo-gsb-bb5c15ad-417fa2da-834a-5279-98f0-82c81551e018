export interface CodepointInfo {
  cp: string;
  value: number;
  char: string;
  name: string;
  block: string | null;
  category: string;
  ccc: number;
  role:
    | "base"
    | "combining-mark"
    | "variation-selector"
    | "join-control"
    | "emoji-modifier"
    | "regional-indicator"
    | "combining-enclosing-keycap"
    | "sequence-member";
}

export interface ChainStep {
  font: string;
  viaAlias?: string | null;
  covered: number[];
  missing: number[];
  default?: boolean;
}

export interface PerCodepointChain {
  index: number;
  chosen: string | null;
  chain: ChainStep[];
}

export interface Issue {
  kind:
    | "missing_glyph"
    | "combining_split"
    | "fragmented_cluster"
    | "zwj_sequence_broken"
    | "alias_cycle"
    | "dangling_font"
    | "duplicate_priority";
  at?: string;
  cp?: string;
  char?: string;
  block?: string | null;
  cpIndex?: number;
  chain?: string[];
  cycle?: string[];
  groups?: { font: string; cpIndexes: number[] }[];
  message: string;
}

export interface Suggestion {
  id: string;
  severity: "error" | "warning" | "info";
  title: string;
  problem: string;
  fix: string;
  snippet?: string;
  copyable: boolean;
}

export interface ClusterRecord {
  index: number;
  text: string;
  kind: string;
  start: number;
  end: number;
  codepoints: CodepointInfo[];
  chosenFont: string | null;
  usedDefault: boolean;
  status: "ok" | "missing" | "split" | "default";
  tags: string[];
  issues: Issue[];
  fallbackChain: ChainStep[];
  perCodepoint?: PerCodepointChain[];
  fragmented?: boolean;
}

export interface FontSummary {
  name: string;
  coverageSize: number;
  intervalCount: number;
  aliasFor: string | null;
}

export interface DiagnoseResponse {
  text: string;
  summary: {
    clusterCount: number;
    codepointCount: number;
    missingCount: number;
    splitCount: number;
    defaultedCount: number;
    issueCount: number;
    mode: "cluster" | "codepoint";
    effectiveOrder: string[];
  };
  manifest: {
    order: string[];
    default: string | null;
    warnings: string[];
    fontCount: number;
    fonts: FontSummary[];
  };
  issues: Issue[];
  suggestions: Suggestion[];
  clusters: ClusterRecord[];
}

export interface ValidationResponse {
  valid: boolean;
  error?: { kind: string; message: string; line?: number; column?: number };
  warnings?: string[];
  fontCount?: number;
  order?: string[];
  effectiveOrder?: string[];
  issues?: Issue[];
  fonts?: FontSummary[];
}

export type SettingsResponse = {
  auth_enabled: boolean;
  broker: string;
  paper_trading: boolean;
  db_path: string;
  results_dir: string;
  provider_keys: Record<string, { configured: boolean }>;
  watchlist: string[];
  risk_limits: Record<string, number>;
  scheduler: Record<string, string>;
};

export type RunStatus =
  | "queued"
  | "running"
  | "waiting_approval"
  | "completed"
  | "failed"
  | "cancel_requested"
  | "cancelled"
  | "stale";

export type Run = {
  id: string;
  ticker: string;
  analysis_date: string;
  asset_type: string;
  status: RunStatus;
  config: Record<string, unknown>;
  error?: string | null;
  result?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

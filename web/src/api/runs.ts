import { http } from './client';

export type RunStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
export type AssetType = 'stock' | 'crypto';
export type AnalystKey = 'market' | 'social' | 'news' | 'fundamentals';

export type CreateRunInput = {
  ticker: string;
  trade_date: string;
  asset_type: AssetType;
  analysts: AnalystKey[];
};

export type RunSummary = {
  run_id: string;
  status: RunStatus;
  ticker: string;
  trade_date: string;
  asset_type: AssetType;
  analysts: AnalystKey[];
  current_step: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
};

export type RunResult = {
  run_id: string;
  status: RunStatus;
  decision: string | null;
  reports: Record<string, unknown>;
  final_state: Record<string, unknown>;
  created_at: string;
};

export const runsApi = {
  async create(input: CreateRunInput): Promise<{ run_id: string; status: RunStatus }> {
    const { data } = await http.post('/runs', input);
    return data;
  },
  async get(runId: string): Promise<RunSummary> {
    const { data } = await http.get<RunSummary>(`/runs/${runId}`);
    return data;
  },
  async result(runId: string): Promise<RunResult> {
    const { data } = await http.get<RunResult>(`/runs/${runId}/result`);
    return data;
  },
  async cancel(runId: string): Promise<{ run_id: string; status: RunStatus }> {
    const { data } = await http.post(`/runs/${runId}/cancel`);
    return data;
  },
};

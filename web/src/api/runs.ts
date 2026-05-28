import { apiUrl, http } from './client';

export type RunStatus = 'queued' | 'dispatching' | 'running' | 'cancelling' | 'succeeded' | 'failed' | 'cancelled';
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
  queue_position: number | null;
};

export type RunResult = {
  run_id: string;
  status: RunStatus;
  decision: string | null;
  reports: Record<string, unknown>;
  reports_i18n: Record<string, Record<string, unknown>> | null;
  final_state: Record<string, unknown>;
  created_at: string;
};

export type RunArtifact = {
  artifact_id: string;
  kind: string;
  content_type: string | null;
  size_bytes: number;
  created_at: string;
};

export type CreateRunResponse = {
  run_id: string;
  status: RunStatus;
  queue_position: number | null;
};

export const runsApi = {
  async create(input: CreateRunInput): Promise<CreateRunResponse> {
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
  async artifacts(runId: string): Promise<RunArtifact[]> {
    const { data } = await http.get<RunArtifact[]>(`/runs/${runId}/artifacts`);
    return data;
  },
  artifactUrl(runId: string, artifactId: string): string {
    return apiUrl(`/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}`);
  },
};

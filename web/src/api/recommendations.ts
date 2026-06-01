import { http } from './client';
import { getLang } from '@/i18n';

export type RecommendationSource = 'watchlist' | 'model_expansion';
export type RecommendationItemStatus = 'recommended' | 'analysis_queued' | 'analysis_failed' | 'ignored';
export type RecommendationBatchStatus = 'succeeded' | 'failed';
export type RunStatus =
  | 'queued'
  | 'dispatching'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled';

export type RecommendationItem = {
  item_id: string;
  ticker: string;
  source: RecommendationSource;
  priority: number;
  reason: string;
  risk: string;
  status: RecommendationItemStatus;
  run_id: string | null;
  run_status: RunStatus | null;
  error: string | null;
};

export type RecommendationBatch = {
  batch_id: string;
  status: RecommendationBatchStatus;
  created_at: string;
  items: RecommendationItem[];
};

export type RecommendationBatchSummary = {
  batch_id: string;
  status: RecommendationBatchStatus;
  created_at: string;
  item_count: number;
};

export type Watchlist = {
  tickers: string[];
  updated_at: string | null;
};

export type AnalyzeRecommendationsResponse = {
  created: { item_id: string; ticker: string; run_id: string }[];
  failed: { item_id: string; ticker?: string | null; detail: string }[];
};

export const recommendationsApi = {
  async watchlist(): Promise<Watchlist> {
    const { data } = await http.get<Watchlist>('/recommendations/watchlist');
    return data;
  },
  async saveWatchlist(tickers: string[]): Promise<Watchlist> {
    const { data } = await http.put<Watchlist>('/recommendations/watchlist', { tickers });
    return data;
  },
  async generate(): Promise<RecommendationBatch> {
    // Pass the UI language so reason/risk come back in the user's language.
    const { data } = await http.post<RecommendationBatch>('/recommendations/generate', {
      language: getLang(),
    });
    return data;
  },
  async batches(): Promise<RecommendationBatchSummary[]> {
    const { data } = await http.get<RecommendationBatchSummary[]>('/recommendations/batches');
    return data;
  },
  async batch(batchId: string): Promise<RecommendationBatch> {
    const { data } = await http.get<RecommendationBatch>(`/recommendations/batches/${encodeURIComponent(batchId)}`);
    return data;
  },
  async analyze(batchId: string, itemIds: string[]): Promise<AnalyzeRecommendationsResponse> {
    const { data } = await http.post<AnalyzeRecommendationsResponse>(
      `/recommendations/batches/${encodeURIComponent(batchId)}/analyze`,
      { item_ids: itemIds },
    );
    return data;
  },
};

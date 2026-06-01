import { http } from './client';

export type BrokerStatus = {
  broker: string;
  connected: boolean;
  gateway_online: boolean;
  brokerage_session: boolean;
  account_id: string | null;
  paper: boolean;
  last_refresh_at: string | null;
  last_error: string | null;
};

export type BrokerAccount = {
  cash: number;
  portfolio_value: number;
  buying_power: number;
  equity: number;
};

export type BrokerPosition = {
  ticker: string;
  qty: number;
  avg_entry_price: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  side: string;
};

export type BrokerOrder = {
  broker_order_id: string;
  account_id: string | null;
  ticker: string;
  side: string;
  order_type: string;
  quantity: number;
  status: string;
  filled_qty: number;
  filled_avg_price: number | null;
  limit_price: number | null;
  approval_id: string | null;
  submitted_at: string | null;
  updated_at: string | null;
};

export type TradeApproval = {
  approval_id: string;
  run_id: string | null;
  ticker: string;
  side: string;
  order_type: string;
  quantity: number;
  limit_price: number | null;
  time_in_force: string;
  estimated_price: number | null;
  estimated_value: number | null;
  whatif_init_margin: number | null;
  whatif_commission: number | null;
  risk_verdict: Record<string, unknown> | null;
  agent_reasoning: string | null;
  status: string;
  requested_by_user_id: string;
  approved_by_user_id: string | null;
  submitted_order_id: string | null;
  error: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type ApproveResult = {
  approval_id: string;
  status: string;
  order_id: string | null;
  detail: string;
};

export type PreviewResult = {
  init_margin: number | null;
  maint_margin: number | null;
  commission: number | null;
  equity_with_loan: number | null;
  warning: string | null;
};

export type EquityPoint = {
  date: string;
  total_value: number;
  cash: number;
  invested_value: number;
  daily_pnl: number;
  daily_pnl_pct: number;
  open_positions: number;
};

export type PerformanceData = {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_realized_pnl: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number | null;
  sharpe_ratio: number;
  max_drawdown: number;
  current_equity: number;
  starting_equity: number;
  total_return_pct: number;
  equity_curve: EquityPoint[];
};

export type TradeRow = {
  ticker: string;
  side: string;
  qty: number;
  price: number;
  total_value: number;
  signal: string;
  order_id: string;
  trade_date: string | null;
  timestamp: string | null;
};

export type ClosedRow = {
  ticker: string;
  entry_price: number;
  exit_price: number;
  qty: number;
  realized_pnl: number;
  realized_pnl_pct: number;
  entry_date: string | null;
  exit_date: string | null;
  holding_days: number;
};

export type TradesData = { trades: TradeRow[]; closed: ClosedRow[] };

export type SnapshotPayload = {
  account_id: string;
  broker?: string;
  cash: number;
  invested_value: number;
  total_value: number;
  open_positions: number;
};

export type WebullConnectionStatus = {
  connected: boolean;
  status: 'connected' | 'expired' | 'revoked' | 'not_connected' | string;
  account_id: string | null;
  region: string | null;
  scope: string | null;
  token_expires_at: string | null;
  auth_type: 'oauth' | 'api_key' | string | null;
};

export type WebullApiKeyPayload = {
  app_key: string;
  app_secret: string;
  account_id?: string;
  region?: string;
};

export type OrderPayload = {
  ticker: string;
  qty: number;
  side: 'buy' | 'sell';
  order_type?: 'market' | 'limit';
  limit_price?: number;
  time_in_force?: string;
};

export const brokerApi = {
  async status(): Promise<BrokerStatus> {
    return (await http.get<BrokerStatus>('/broker/status')).data;
  },
  async account(): Promise<BrokerAccount> {
    return (await http.get<BrokerAccount>('/broker/account')).data;
  },
  async positions(): Promise<BrokerPosition[]> {
    return (await http.get<BrokerPosition[]>('/broker/positions')).data;
  },
  async orders(): Promise<BrokerOrder[]> {
    return (await http.get<BrokerOrder[]>('/broker/orders')).data;
  },
  async approvals(status?: string): Promise<TradeApproval[]> {
    return (await http.get<TradeApproval[]>('/broker/approvals', { params: status ? { status } : undefined })).data;
  },
  async createProposal(run_id: string): Promise<TradeApproval> {
    return (await http.post<TradeApproval>('/broker/approvals', { run_id })).data;
  },
  // Desktop local-execution bridge (server builds the proposal from a local
  // account snapshot; the order is placed locally and reported back).
  async createLocalProposal(payload: {
    run_id: string;
    account: BrokerAccount;
    positions: BrokerPosition[];
    price: number;
  }): Promise<TradeApproval> {
    return (await http.post<TradeApproval>('/broker/local/proposals', payload)).data;
  },
  async recordExecuted(
    approvalId: string,
    payload: {
      broker_order_id: string;
      status: string;
      filled_qty?: number;
      filled_avg_price?: number | null;
      limit_price?: number | null;
      account_id?: string;
    },
  ): Promise<ApproveResult> {
    return (await http.post<ApproveResult>(`/broker/approvals/${approvalId}/executed`, payload)).data;
  },
  async approve(approvalId: string): Promise<ApproveResult> {
    return (await http.post<ApproveResult>(`/broker/approvals/${approvalId}/approve`)).data;
  },
  async reject(approvalId: string): Promise<TradeApproval> {
    return (await http.post<TradeApproval>(`/broker/approvals/${approvalId}/reject`)).data;
  },
  async cancel(orderId: string): Promise<{ cancelled: boolean }> {
    return (await http.post<{ cancelled: boolean }>(`/broker/orders/${orderId}/cancel`)).data;
  },
  async refresh(): Promise<BrokerStatus> {
    return (await http.post<BrokerStatus>('/broker/refresh')).data;
  },
  async previewOrder(payload: OrderPayload): Promise<PreviewResult> {
    return (await http.post<PreviewResult>('/broker/orders/preview', payload)).data;
  },
  async placeOrder(payload: OrderPayload): Promise<BrokerOrder> {
    return (await http.post<BrokerOrder>('/broker/orders', payload)).data;
  },
  // Portfolio analytics — server-side, scoped to (user, account, broker).
  async performance(accountId: string, broker = 'ibkr'): Promise<PerformanceData> {
    return (await http.get<PerformanceData>('/broker/performance', { params: { account_id: accountId, broker } })).data;
  },
  async trades(accountId: string, broker = 'ibkr'): Promise<TradesData> {
    return (await http.get<TradesData>('/broker/trades', { params: { account_id: accountId, broker } })).data;
  },
  async pushSnapshot(payload: SnapshotPayload): Promise<void> {
    await http.post('/broker/snapshot', payload);
  },
  // Mirror a manually-placed order (no approval) to the server order list.
  async recordManualOrder(payload: {
    broker_order_id: string;
    account_id: string;
    ticker: string;
    side: string;
    order_type: string;
    quantity: number;
    status: string;
    filled_qty?: number;
    filled_avg_price?: number | null;
    limit_price?: number | null;
  }): Promise<BrokerOrder> {
    return (await http.post<BrokerOrder>('/broker/orders/manual', payload)).data;
  },
  // Webull Connect API (cloud broker, per-user OAuth). The platform holds each
  // user's tokens server-side; the browser only starts / inspects the link.
  webull: {
    async status(): Promise<WebullConnectionStatus> {
      return (await http.get<WebullConnectionStatus>('/broker/oauth/webull/status')).data;
    },
    async authorizeUrl(): Promise<string> {
      return (await http.get<{ authorize_url: string }>('/broker/oauth/webull/authorize')).data
        .authorize_url;
    },
    async connectApiKey(payload: WebullApiKeyPayload): Promise<WebullConnectionStatus> {
      return (await http.post<WebullConnectionStatus>('/broker/oauth/webull/api-key', payload)).data;
    },
    async refresh(): Promise<WebullConnectionStatus> {
      return (await http.post<WebullConnectionStatus>('/broker/oauth/webull/refresh')).data;
    },
    async disconnect(): Promise<WebullConnectionStatus> {
      return (await http.post<WebullConnectionStatus>('/broker/oauth/webull/disconnect')).data;
    },
  },
};

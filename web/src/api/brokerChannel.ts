// Pluggable "live broker" channel. The same broker pages drive either:
//   • localBrokerClient  — Electron desktop → main-process IPC → Python sidecar
//                          → local TWS / IB Gateway (this machine)
//   • serverBrokerClient — browser/server → existing /broker/* (Redis connector,
//                          future cloud brokers like Webull)
// The approval/proposal workflow stays on the server (see broker.ts); only the
// live status/account/positions/orders + connect controls are channel-switched.

import {
  brokerApi,
  type BrokerAccount,
  type BrokerOrder,
  type BrokerPosition,
  type BrokerStatus,
  type PreviewResult,
} from './broker';

export type ConnectOpts = {
  broker?: string;
  host: string;
  port: number;
  client_id: number;
  market_data_type: number;
  account_id?: string;
  paper: boolean;
};

export type OrderReq = {
  ticker: string;
  qty: number;
  side: 'buy' | 'sell';
  order_type?: 'market' | 'limit';
  limit_price?: number;
  time_in_force?: string;
};

// A discovered IBKR endpoint (one running TWS / IB Gateway socket). `paper` is a
// hint from the conventional port; the real paper/live is confirmed on connect.
export type BrokerCandidate = {
  host: string;
  port: number;
  kind: 'tws' | 'gateway' | string;
  paper: boolean;
};

export type BrokerKind = 'local' | 'server';

export interface BrokerLiveChannel {
  kind: BrokerKind;
  /** Whether this channel exposes an interactive connect flow (local only). */
  supportsConnect: boolean;
  status(): Promise<BrokerStatus>;
  // Local-only: scan well-known IBKR ports for one-click connect (undefined on server).
  discover?(host?: string): Promise<{ candidates: BrokerCandidate[] }>;
  account(accountId?: string): Promise<BrokerAccount>;
  positions(accountId?: string): Promise<BrokerPosition[]>;
  orders(): Promise<BrokerOrder[]>;
  connect(opts: ConnectOpts): Promise<BrokerStatus>;
  disconnect(): Promise<void>;
  refresh(): Promise<BrokerStatus>;
  // Local-only: order placement against the local TWS (undefined on server).
  quote?(ticker: string): Promise<{ ticker: string; price: number }>;
  preview?(req: OrderReq): Promise<PreviewResult>;
  execute?(req: OrderReq): Promise<BrokerOrder>;
  cancel?(orderId: string): Promise<{ cancelled: boolean }>;
}

// Server channel: connection is managed server-side; connect just re-probes.
const serverChannel: BrokerLiveChannel = {
  kind: 'server',
  supportsConnect: false,
  status: () => brokerApi.status(),
  account: (accountId) => brokerApi.account(accountId ? { account_id: accountId } : undefined),
  positions: (accountId) => brokerApi.positions(accountId ? { account_id: accountId } : undefined),
  orders: () => brokerApi.orders(),
  connect: () => brokerApi.refresh(),
  disconnect: async () => {},
  refresh: () => brokerApi.refresh(),
};

function localChannel(): BrokerLiveChannel {
  const d = window.desktop!;
  return {
    kind: 'local',
    supportsConnect: true,
    status: () => d.broker.status(),
    discover: (host) => d.broker.discover(host),
    account: (accountId) => d.broker.account(accountId),
    positions: (accountId) => d.broker.positions(accountId),
    orders: () => d.broker.orders(),
    connect: (opts) => d.broker.connect(opts),
    disconnect: async () => {
      await d.broker.disconnect();
    },
    refresh: () => d.broker.status(),
    quote: (ticker) => d.broker.quote(ticker),
    preview: (req) => d.broker.preview(req),
    execute: (req) => d.broker.execute(req),
    cancel: (orderId) => d.broker.cancel(orderId),
  };
}

export function isDesktop(): boolean {
  return Boolean(window.desktop?.isDesktop && window.desktop.broker);
}

export function getBrokerChannel(): BrokerLiveChannel {
  return isDesktop() ? localChannel() : serverChannel;
}

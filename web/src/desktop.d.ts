// Surface exposed by web/electron/preload.cjs. Optional: undefined in the
// plain browser build, present when running inside the Electron desktop shell.
// Broker calls are mediated by the main process (token never reaches here).
import type {
  BrokerAccount,
  BrokerOrder,
  BrokerPosition,
  BrokerStatus,
  PreviewResult,
} from '@/api/broker';
import type { BrokerCandidate, ConnectOpts, OrderReq } from '@/api/brokerChannel';

export {};

declare global {
  interface Window {
    desktop?: {
      isDesktop: boolean;
      platform: string;
      broker: {
        ready(): Promise<{ ready: boolean; lastError: string | null }>;
        status(): Promise<BrokerStatus>;
        discover(host?: string): Promise<{ candidates: BrokerCandidate[] }>;
        connect(opts: ConnectOpts): Promise<BrokerStatus>;
        disconnect(): Promise<{ ok: boolean } | void>;
        account(): Promise<BrokerAccount>;
        positions(): Promise<BrokerPosition[]>;
        orders(): Promise<BrokerOrder[]>;
        quote(ticker: string): Promise<{ ticker: string; price: number }>;
        preview(req: OrderReq): Promise<PreviewResult>;
        execute(req: OrderReq): Promise<BrokerOrder>;
        cancel(orderId: string): Promise<{ cancelled: boolean }>;
      };
    };
  }
}

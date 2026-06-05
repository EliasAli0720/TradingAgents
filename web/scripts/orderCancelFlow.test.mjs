import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function loadBrokerReadiness() {
  const source = readFileSync(new URL('../src/api/brokerReadiness.ts', import.meta.url), 'utf8');
  const js = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  const mod = { exports: {} };
  vm.runInNewContext(js, { module: mod, exports: mod.exports });
  return mod.exports;
}

function loadOrderCancelFlow({ brokerApi, channel }) {
  const source = readFileSync(new URL('../src/api/orderCancelFlow.ts', import.meta.url), 'utf8');
  const js = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  const mod = { exports: {} };
  const require = (id) => {
    if (id === './broker') return { brokerApi };
    if (id === './brokerChannel') return { getBrokerChannel: () => channel };
    if (id === './brokerReadiness') return loadBrokerReadiness();
    throw new Error(`unexpected import: ${id}`);
  };
  vm.runInNewContext(js, { module: mod, exports: mod.exports, require });
  return mod.exports;
}

const order = {
  broker_order_id: 'local-order-1',
  account_id: 'DULOCAL',
  ticker: 'AAPL',
  side: 'buy',
  order_type: 'limit',
  quantity: 1,
  status: 'pending',
  filled_qty: 0,
  filled_avg_price: null,
  limit_price: 120,
  approval_id: null,
  submitted_at: null,
  updated_at: null,
};

{
  const calls = [];
  const brokerApi = {
    status: async () => ({
      broker: 'ibkr',
      connected: false,
      gateway_online: false,
      brokerage_session: false,
      account_id: null,
    }),
    cancel: async (orderId) => {
      calls.push(['server-cancel', orderId]);
      return { cancelled: true };
    },
    updateOrderStatus: async (orderId, payload) => {
      calls.push(['server-status', orderId, payload.status]);
      return { ...order, status: payload.status };
    },
  };
  const channel = {
    kind: 'local',
    status: async () => ({
      broker: 'ibkr',
      connected: true,
      brokerage_session: true,
      account_id: 'DULOCAL',
    }),
    cancel: async (orderId) => {
      calls.push(['local-cancel', orderId]);
      return { cancelled: true };
    },
  };
  const { cancelOrder } = loadOrderCancelFlow({ brokerApi, channel });
  assert.deepEqual(await cancelOrder(order), { cancelled: true });
  assert.deepEqual(calls, [
    ['local-cancel', 'local-order-1'],
    ['server-status', 'local-order-1', 'cancelled'],
  ]);
}

{
  const calls = [];
  const brokerApi = {
    status: async () => ({
      broker: 'webull',
      connected: true,
      brokerage_session: true,
      account_id: 'DUWEBULL',
    }),
    cancel: async (orderId) => {
      calls.push(['server-cancel', orderId]);
      return { cancelled: true };
    },
    updateOrderStatus: async () => {
      calls.push(['server-status']);
      return order;
    },
  };
  const channel = {
    kind: 'local',
    cancel: async (orderId) => {
      calls.push(['local-cancel', orderId]);
      return { cancelled: true };
    },
  };
  const { cancelOrder } = loadOrderCancelFlow({ brokerApi, channel });
  assert.deepEqual(await cancelOrder(order), { cancelled: true });
  assert.deepEqual(calls, [['server-cancel', 'local-order-1']]);
}

{
  const calls = [];
  const brokerApi = {
    status: async () => ({
      broker: 'webull',
      connected: true,
      brokerage_session: true,
      account_id: 'DUWEBULL',
    }),
    cancel: async (orderId) => {
      calls.push(['server-cancel', orderId]);
      return { cancelled: true };
    },
    updateOrderStatus: async (orderId, payload) => {
      calls.push(['server-status', orderId, payload.status]);
      return { ...order, status: payload.status };
    },
  };
  const channel = {
    kind: 'local',
    status: async () => ({
      broker: 'ibkr',
      connected: true,
      brokerage_session: true,
      account_id: 'DULOCAL',
    }),
    cancel: async (orderId) => {
      calls.push(['local-cancel', orderId]);
      return { cancelled: true };
    },
  };
  const { cancelOrder } = loadOrderCancelFlow({ brokerApi, channel });
  assert.deepEqual(await cancelOrder(order, { source: 'local' }), { cancelled: true });
  assert.deepEqual(calls, [
    ['local-cancel', 'local-order-1'],
    ['server-status', 'local-order-1', 'cancelled'],
  ]);
}

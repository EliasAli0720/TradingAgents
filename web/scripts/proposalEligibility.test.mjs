import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = readFileSync(new URL('../src/routes/analysis/proposalEligibility.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
  },
}).outputText;

const mod = { exports: {} };
vm.runInNewContext(js, { module: mod, exports: mod.exports });
const { normalizeProposalSignal, proposalEligibility, proposalButtonLabelKey } = mod.exports;

assert.equal(
  proposalEligibility({ canOperate: true, runStatus: 'succeeded', decision: 'Hold' }).state,
  'no_action',
);
assert.equal(
  proposalEligibility({ canOperate: true, runStatus: 'succeeded', decision: 'BUY' }).state,
  'actionable',
);
assert.equal(normalizeProposalSignal('**Rating**: Buy\n\nEnter gradually.'), 'BUY');
assert.equal(
  proposalEligibility({
    canOperate: true,
    runStatus: 'succeeded',
    decision: '**Rating**: Buy\n\nEnter gradually.',
  }).state,
  'actionable',
);
assert.equal(
  proposalEligibility({ canOperate: true, runStatus: 'succeeded', decision: null }).state,
  'waiting',
);
assert.equal(
  proposalEligibility({ canOperate: false, runStatus: 'succeeded', decision: 'BUY' }).state,
  'hidden',
);
assert.equal(
  proposalEligibility({
    canOperate: true,
    runStatus: 'succeeded',
    decision: 'BUY',
    brokerStatusLoading: true,
  }).state,
  'waiting',
);
assert.equal(
  proposalEligibility({
    canOperate: true,
    runStatus: 'succeeded',
    decision: 'BUY',
    hasUsableBrokerAccount: false,
  }).state,
  'connect_account',
);
assert.equal(proposalButtonLabelKey(false), 'broker.proposal.generate');
assert.equal(proposalButtonLabelKey(true), 'broker.proposal.generating');

function loadTradeFlow({ brokerApi, channel }) {
  const tradeFlowSource = readFileSync(new URL('../src/api/tradeFlow.ts', import.meta.url), 'utf8');
  const tradeFlowJs = ts.transpileModule(tradeFlowSource, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  const tradeFlowMod = { exports: {} };
  const require = (id) => {
    if (id === './broker') return { brokerApi };
    if (id === './brokerChannel') return { getBrokerChannel: () => channel };
    if (id === './brokerReadiness') {
      return loadBrokerReadiness();
    }
    throw new Error(`unexpected import: ${id}`);
  };
  vm.runInNewContext(tradeFlowJs, { module: tradeFlowMod, exports: tradeFlowMod.exports, require });
  return tradeFlowMod.exports;
}

function loadBrokerReadiness() {
  const readinessSource = readFileSync(new URL('../src/api/brokerReadiness.ts', import.meta.url), 'utf8');
  const readinessJs = ts.transpileModule(readinessSource, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  const readinessMod = { exports: {} };
  vm.runInNewContext(readinessJs, { module: readinessMod, exports: readinessMod.exports });
  return readinessMod.exports;
}

const connectedWebull = {
  broker: 'webull',
  connected: true,
  gateway_online: true,
  brokerage_session: true,
  account_id: 'DUWEBULL',
  paper: true,
  last_refresh_at: null,
  last_error: null,
};

{
  const calls = [];
  const brokerApi = {
    status: async () => connectedWebull,
    createProposal: async (runId) => {
      calls.push(['server', runId]);
      return { approval_id: 'server-proposal' };
    },
    createLocalProposal: async () => {
      calls.push(['local']);
      return { approval_id: 'local-proposal' };
    },
  };
  const channel = {
    kind: 'local',
    status: async () => ({ connected: true, brokerage_session: true, account_id: 'DULOCAL' }),
    account: async () => ({ cash: 100, portfolio_value: 100, buying_power: 100, equity: 100 }),
    positions: async () => [],
    quote: async () => {
      calls.push(['quote']);
      return { ticker: 'AAPL', price: 200 };
    },
  };
  const { createProposal } = loadTradeFlow({ brokerApi, channel });
  const proposal = await createProposal('run-webull', 'AAPL');
  assert.equal(proposal.approval_id, 'server-proposal');
  assert.deepEqual(calls, [['server', 'run-webull']]);
}

{
  const calls = [];
  const brokerApi = {
    status: async () => ({
      broker: 'ibkr',
      connected: false,
      gateway_online: false,
      brokerage_session: false,
      account_id: null,
      paper: true,
      last_refresh_at: null,
      last_error: 'connector not running',
    }),
    createProposal: async () => {
      calls.push(['server']);
      return { approval_id: 'server-proposal' };
    },
    createLocalProposal: async (payload) => {
      calls.push(['local', payload.price]);
      return { approval_id: 'local-proposal' };
    },
  };
  const channel = {
    kind: 'local',
    status: async () => ({
      broker: 'ibkr',
      connected: true,
      gateway_online: true,
      brokerage_session: true,
      account_id: 'DULOCAL',
      paper: true,
      last_refresh_at: null,
      last_error: null,
    }),
    account: async () => ({ cash: 100, portfolio_value: 100, buying_power: 100, equity: 100 }),
    positions: async () => [],
    quote: async () => ({ ticker: 'AAPL', price: 200 }),
  };
  const { createProposal } = loadTradeFlow({ brokerApi, channel });
  const proposal = await createProposal('run-local', 'AAPL');
  assert.equal(proposal.approval_id, 'local-proposal');
  assert.deepEqual(calls, [['local', 200]]);
}

{
  const brokerApi = {
    status: async () => ({
      broker: 'ibkr',
      connected: false,
      gateway_online: false,
      brokerage_session: false,
      account_id: null,
      paper: true,
      last_refresh_at: null,
      last_error: 'connector not running',
    }),
    createProposal: async () => ({ approval_id: 'server-proposal' }),
    createLocalProposal: async () => ({ approval_id: 'local-proposal' }),
  };
  const channel = {
    kind: 'server',
    status: brokerApi.status,
  };
  const { createProposal } = loadTradeFlow({ brokerApi, channel });
  await assert.rejects(
    () => createProposal('run-none', 'AAPL'),
    (err) => err?.detail === 'broker_not_connected',
  );
}

{
  const calls = [];
  const brokerApi = {
    status: async () => ({
      broker: 'ibkr',
      connected: false,
      gateway_online: false,
      brokerage_session: false,
      account_id: null,
      paper: true,
      last_refresh_at: null,
      last_error: 'connector not running',
    }),
    createProposal: async () => {
      calls.push(['server']);
      return { approval_id: 'server-proposal' };
    },
    createLocalProposal: async (payload) => {
      calls.push(['local', payload.price]);
      return { approval_id: 'local-proposal' };
    },
  };
  const channel = {
    kind: 'local',
    status: async () => ({
      broker: 'ibkr',
      connected: true,
      gateway_online: true,
      brokerage_session: true,
      account_id: 'DULOCAL',
      paper: true,
      last_refresh_at: null,
      last_error: null,
    }),
    account: async () => ({ cash: 100, portfolio_value: 100, buying_power: 100, equity: 100 }),
    positions: async () => [{ ticker: 'MSFT', qty: 2, current_price: 422.06 }],
    quote: async () => {
      throw { status: 502, detail: "No price available for 'MSFT' from IBKR" };
    },
  };
  const { createProposal } = loadTradeFlow({ brokerApi, channel });
  const proposal = await createProposal('run-local-held', 'msft');
  assert.equal(proposal.approval_id, 'local-proposal');
  assert.deepEqual(calls, [['local', 422.06]]);
}

{
  const calls = [];
  const brokerApi = {
    status: async () => connectedWebull,
    approve: async (approvalId) => {
      calls.push(['server-approve', approvalId]);
      return { approval_id: approvalId, status: 'submitted', order_id: 'webull-order' };
    },
    recordExecuted: async () => {
      calls.push(['record-local']);
    },
  };
  const channel = {
    kind: 'local',
    status: async () => ({ connected: true, brokerage_session: true, account_id: 'DULOCAL' }),
    execute: async () => {
      calls.push(['local-execute']);
      return { broker_order_id: 'local-order', status: 'submitted' };
    },
  };
  const { approveProposal } = loadTradeFlow({ brokerApi, channel });
  await approveProposal({
    approval_id: 'approval-webull',
    ticker: 'AAPL',
    quantity: 1,
    side: 'buy',
    order_type: 'market',
    limit_price: null,
    time_in_force: 'day',
  });
  assert.deepEqual(calls, [['server-approve', 'approval-webull']]);
}

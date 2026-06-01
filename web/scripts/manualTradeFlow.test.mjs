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

const source = readFileSync(new URL('../src/api/manualTradeFlow.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
  },
}).outputText;
const mod = { exports: {} };
const require = (id) => {
  if (id === './brokerReadiness') return loadBrokerReadiness();
  throw new Error(`unexpected import: ${id}`);
};
vm.runInNewContext(js, { module: mod, exports: mod.exports, require });

const { manualTradeRoute } = mod.exports;

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

const connectedLocal = {
  broker: 'ibkr',
  connected: true,
  gateway_online: true,
  brokerage_session: true,
  account_id: 'DULOCAL',
  paper: true,
  last_refresh_at: null,
  last_error: null,
};

assert.equal(
  manualTradeRoute({
    desktop: true,
    serverStatus: connectedWebull,
    localStatus: connectedLocal,
    localCanExecute: true,
  }),
  'server',
);

assert.equal(
  manualTradeRoute({
    desktop: true,
    serverStatus: { ...connectedLocal, connected: false, account_id: null },
    localStatus: connectedLocal,
    localCanExecute: true,
  }),
  'local',
);

assert.equal(
  manualTradeRoute({
    desktop: true,
    serverStatusLoading: true,
    localStatus: connectedLocal,
    localCanExecute: true,
  }),
  null,
);

assert.equal(
  manualTradeRoute({
    desktop: false,
    serverStatus: connectedWebull,
  }),
  'server',
);

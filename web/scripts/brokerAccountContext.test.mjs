import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = readFileSync(new URL('../src/api/brokerAccountContext.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
  },
}).outputText;
const mod = { exports: {} };
vm.runInNewContext(js, { module: mod, exports: mod.exports });

const { brokerAccountOptions, defaultBrokerAccountKey, resolveBrokerAccountKey } = mod.exports;

const webull = {
  broker: 'webull',
  connected: true,
  brokerage_session: true,
  account_id: 'DUWEBULL',
  accounts: ['DUWEBULL'],
};

const localIbkr = {
  broker: 'ibkr',
  connected: true,
  brokerage_session: true,
  account_id: 'DULOCAL',
  accounts: ['DULOCAL'],
};

{
  const options = brokerAccountOptions({
    serverStatus: webull,
    localStatus: localIbkr,
    includeLocal: true,
  });
  assert.equal(
    JSON.stringify(options.map((option) => [option.key, option.source, option.broker, option.account_id])),
    JSON.stringify([
      ['server:webull:DUWEBULL', 'server', 'webull', 'DUWEBULL'],
      ['local:ibkr:DULOCAL', 'local', 'ibkr', 'DULOCAL'],
    ]),
  );
  assert.equal(defaultBrokerAccountKey(options), 'server:webull:DUWEBULL');
  assert.equal(resolveBrokerAccountKey(options, 'local:ibkr:DULOCAL'), 'local:ibkr:DULOCAL');
  assert.equal(resolveBrokerAccountKey(options, 'missing'), 'server:webull:DUWEBULL');
}

{
  const options = brokerAccountOptions({
    serverStatus: { ...webull, connected: false, account_id: null },
    localStatus: localIbkr,
    includeLocal: true,
  });
  assert.equal(JSON.stringify(options.map((option) => option.key)), JSON.stringify(['local:ibkr:DULOCAL']));
  assert.equal(defaultBrokerAccountKey(options), 'local:ibkr:DULOCAL');
}

{
  const options = brokerAccountOptions({
    serverStatus: {
      ...webull,
      account_id: 'DUWEB1',
      accounts: ['DUWEB1', 'DUWEB2'],
    },
    localStatus: {
      ...localIbkr,
      account_id: 'DUIB1',
      accounts: ['DUIB1', 'DUIB2'],
    },
    includeLocal: true,
  });
  assert.equal(
    JSON.stringify(options.map((option) => [option.key, option.source, option.broker, option.account_id])),
    JSON.stringify([
      ['server:webull:DUWEB1', 'server', 'webull', 'DUWEB1'],
      ['server:webull:DUWEB2', 'server', 'webull', 'DUWEB2'],
      ['local:ibkr:DUIB1', 'local', 'ibkr', 'DUIB1'],
      ['local:ibkr:DUIB2', 'local', 'ibkr', 'DUIB2'],
    ]),
  );
  assert.equal(resolveBrokerAccountKey(options, 'local:ibkr:DUIB2'), 'local:ibkr:DUIB2');
}

{
  const options = brokerAccountOptions({
    serverStatus: {
      ...webull,
      account_id: 'DUWEB1',
      accounts: ['DUWEB1', '', 'DUWEB1', 'DUWEB2'],
    },
    localStatus: null,
    includeLocal: true,
  });
  assert.equal(
    JSON.stringify(options.map((option) => option.key)),
    JSON.stringify(['server:webull:DUWEB1', 'server:webull:DUWEB2']),
  );
}

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = readFileSync(new URL('../src/api/proposalReport.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
  },
}).outputText;
const mod = { exports: {} };
vm.runInNewContext(js, { module: mod, exports: mod.exports });

const { proposalReportRows, proposalReportSummary } = mod.exports;

const approval = {
  ticker: 'AAPL',
  side: 'buy',
  quantity: 25,
  estimated_price: 200,
  estimated_value: 5000,
  agent_reasoning: 'Fallback reasoning',
  proposal_report: {
    summary: 'BUY AAPL 25 shares at estimated 200.00 (value 5000.00).',
    signal: {
      raw: '**Rating**: Buy',
      normalized: 'BUY',
      action: 'buy',
      reason: 'Strong buy - allocating full position',
    },
    sizing: {
      basis: 'cash',
      basis_amount: 100000,
      allocation_fraction: 0.05,
      target_value: 5000,
      estimated_price: 200,
      computed_quantity: 25,
      final_quantity: 25,
      estimated_value: 5000,
    },
    risk: {
      approved: true,
      reason: 'within risk limits',
      adjusted_qty: null,
    },
    agent_reasoning: 'Portfolio manager recommends accumulation.',
  },
};

assert.equal(
  proposalReportSummary(approval),
  'BUY AAPL 25 shares at estimated 200.00 (value 5000.00).',
);

assert.equal(
  JSON.stringify(proposalReportRows(approval).map((row) => [row.labelKey, row.value])),
  JSON.stringify([
    ['broker.proposal_report.signal', 'BUY (raw: **Rating**: Buy)'],
    ['broker.proposal_report.sizing', 'cash 100000.00 x 5.00% / 200.00 = 25.00 -> 25 shares'],
    ['broker.proposal_report.estimated_value', '5000.00'],
    ['broker.proposal_report.risk', 'approved - within risk limits'],
    ['broker.proposal_report.reasoning', 'Portfolio manager recommends accumulation.'],
  ]),
);

assert.equal(
  proposalReportSummary({ ...approval, proposal_report: null }),
  'BUY AAPL 25 @ 200.00',
);

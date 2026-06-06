'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const { resolveAppFile } = require('./app-protocol.cjs');

function makeDist() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ta-app-protocol-'));
  const dist = path.join(root, 'dist');
  fs.mkdirSync(path.join(dist, 'assets'), { recursive: true });
  fs.writeFileSync(path.join(dist, 'index.html'), '<html></html>');
  fs.writeFileSync(path.join(dist, 'assets', 'index.js'), 'console.log("ok");');
  fs.writeFileSync(path.join(root, 'secret.json'), '{"secret":true}');
  return { root, dist };
}

test('resolveAppFile serves existing files under dist', () => {
  const { dist } = makeDist();
  const resolved = resolveAppFile(dist, 'app://local/assets/index.js');
  assert.equal(resolved.filePath, path.join(dist, 'assets', 'index.js'));
  assert.equal(resolved.contentType, 'text/javascript');
});

test('resolveAppFile falls back to index.html for SPA routes', () => {
  const { dist } = makeDist();
  const resolved = resolveAppFile(dist, 'app://local/analysis/run_123');
  assert.equal(resolved.filePath, path.join(dist, 'index.html'));
  assert.equal(resolved.contentType, 'text/html');
});

test('resolveAppFile rejects encoded traversal outside dist', () => {
  const { dist } = makeDist();
  const resolved = resolveAppFile(dist, 'app://local/%2e%2e/secret.json');
  assert.equal(resolved, null);
});

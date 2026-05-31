'use strict';

// Spawns and supervises the Python broker sidecar (run_sidecar.py) on a free
// loopback port with a per-session token. The token never leaves the main
// process: the renderer reaches the sidecar only through the IPC handlers in
// main.cjs, so there is no CORS / Private-Network-Access surface and no token
// in renderer-reachable JS.

const { app } = require('electron');
const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const crypto = require('node:crypto');
const net = require('node:net');

const REPO_ROOT = path.join(__dirname, '..', '..');

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

function resolvePython() {
  if (process.env.SIDECAR_PYTHON) return process.env.SIDECAR_PYTHON;
  // Dev: the project venv. Packaging (P4) swaps this for the PyInstaller binary.
  const venv = path.join(REPO_ROOT, '.venv', 'bin', 'python3');
  return fs.existsSync(venv) ? venv : 'python3';
}

class Sidecar {
  constructor() {
    this.port = null;
    this.token = null;
    this.proc = null;
    this.ready = false;
    this.lastError = null;
  }

  get baseUrl() {
    return this.port ? `http://127.0.0.1:${this.port}` : null;
  }

  async start() {
    if (this.proc) return;
    this.port = await freePort();
    this.token = crypto.randomBytes(24).toString('hex');
    const cliArgs = ['--host', '127.0.0.1', '--port', String(this.port), '--token', this.token];

    let command;
    let args;
    let cwd;
    if (app.isPackaged) {
      // Packaged: spawn the bundled PyInstaller binary from extraResources.
      const bin = process.platform === 'win32' ? 'sidecar.exe' : 'sidecar';
      command = path.join(process.resourcesPath, 'sidecar', bin);
      args = cliArgs;
      cwd = path.dirname(command);
    } else {
      // Dev: run from source with the project venv.
      command = resolvePython();
      args = [process.env.SIDECAR_ENTRY || path.join(REPO_ROOT, 'run_sidecar.py'), ...cliArgs];
      cwd = REPO_ROOT;
    }

    this.proc = spawn(command, args, {
      cwd,
      env: { ...process.env, SIDECAR_TOKEN: this.token, PYTHONUNBUFFERED: '1' },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    const log = (d) => process.stdout.write(`[sidecar] ${d}`);
    this.proc.stdout.on('data', log);
    this.proc.stderr.on('data', log);
    this.proc.on('exit', (code) => {
      this.ready = false;
      this.proc = null;
      if (code) this.lastError = `sidecar exited with code ${code}`;
    });

    await this._waitReady();
  }

  async _waitReady(timeoutMs = 45000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      try {
        const r = await fetch(`${this.baseUrl}/ping`);
        if (r.ok) {
          this.ready = true;
          this.lastError = null;
          return;
        }
      } catch {
        /* not up yet */
      }
      await new Promise((res) => setTimeout(res, 300));
    }
    throw new Error('sidecar did not become ready in time');
  }

  // Mediated HTTP call to the sidecar with the bearer token attached.
  async call(method, pathname, body) {
    if (!this.baseUrl) throw new Error('sidecar not started');
    const r = await fetch(`${this.baseUrl}${pathname}`, {
      method,
      headers: { authorization: `Bearer ${this.token}`, 'content-type': 'application/json' },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    const text = await r.text();
    const data = text ? JSON.parse(text) : null;
    if (!r.ok) {
      const err = new Error((data && data.detail) || `sidecar HTTP ${r.status}`);
      err.status = r.status;
      throw err;
    }
    return data;
  }

  stop() {
    if (this.proc && !this.proc.killed) {
      try {
        this.proc.kill();
      } catch {
        /* ignore */
      }
    }
    this.proc = null;
    this.ready = false;
  }
}

module.exports = { Sidecar };

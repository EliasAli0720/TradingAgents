'use strict';

// Electron main process — P1 shell. Loads the existing React SPA unchanged:
//   dev  -> the Vite dev server (HMR + /api proxy to the FastAPI server)
//   prod -> the built dist/ served over a custom `app://` scheme so the SPA
//           can keep absolute asset paths and BrowserRouter routing without
//           any change to web/src/router.tsx.
// No broker/sidecar logic yet — that arrives in P2.

const { app, BrowserWindow, protocol, shell, ipcMain } = require('electron');
const path = require('node:path');
const { registerAppProtocol } = require('./app-protocol.cjs');
const { Sidecar } = require('./sidecar.cjs');

const sidecar = new Sidecar();

const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL || '';
const isDev = Boolean(DEV_SERVER_URL);
const DIST_DIR = path.join(__dirname, '..', 'dist');

// Privileged custom scheme must be declared before app `ready`.
protocol.registerSchemesAsPrivileged([
  {
    scheme: 'app',
    privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true },
  },
]);

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    title: 'TradingAgents',
    backgroundColor: '#0a0a0a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  // Keep external links out of the app window — open them in the OS browser.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://localhost') || url.startsWith('app://')) {
      return { action: 'allow' };
    }
    shell.openExternal(url);
    return { action: 'deny' };
  });

  if (isDev) {
    win.loadURL(DEV_SERVER_URL);
    win.webContents.openDevTools({ mode: 'detach' });
  } else {
    win.loadURL('app://local/');
  }
}

// Broker IPC — the renderer's localBrokerClient calls these; the main process
// holds the sidecar URL + token and makes the actual HTTP calls. Errors reject
// the invoke() promise with the sidecar's detail message.
function withAccount(pathname, accountId) {
  if (!accountId) return pathname;
  return `${pathname}?account_id=${encodeURIComponent(accountId)}`;
}

function registerBrokerIpc() {
  ipcMain.handle('broker:ready', () => ({ ready: sidecar.ready, lastError: sidecar.lastError }));
  ipcMain.handle('broker:status', () => sidecar.call('GET', '/health'));
  ipcMain.handle('broker:discover', (_e, host) =>
    sidecar.call('POST', '/discover', { host: host || '127.0.0.1' }),
  );
  ipcMain.handle('broker:connect', (_e, opts) => sidecar.call('POST', '/connect', opts ?? {}));
  ipcMain.handle('broker:disconnect', () => sidecar.call('POST', '/disconnect'));
  ipcMain.handle('broker:account', (_e, accountId) => sidecar.call('GET', withAccount('/account', accountId)));
  ipcMain.handle('broker:positions', (_e, accountId) => sidecar.call('GET', withAccount('/positions', accountId)));
  ipcMain.handle('broker:orders', () => sidecar.call('GET', '/orders'));
  ipcMain.handle('broker:quote', (_e, ticker) => sidecar.call('POST', '/quote', { ticker }));
  ipcMain.handle('broker:preview', (_e, req) => sidecar.call('POST', '/preview', req));
  ipcMain.handle('broker:execute', (_e, req) => sidecar.call('POST', '/execute', req));
  ipcMain.handle('broker:cancel', (_e, orderId) =>
    sidecar.call('POST', `/orders/${encodeURIComponent(orderId)}/cancel`),
  );
}

app.whenReady().then(() => {
  if (!isDev) registerAppProtocol(protocol, DIST_DIR);
  registerBrokerIpc();
  createWindow();
  // Start the sidecar in the background — the window loads immediately and the
  // renderer's connection store polls broker:status / broker:ready for state.
  sidecar.start().catch((err) => {
    sidecar.lastError = String(err && err.message ? err.message : err);
    console.error('[sidecar] start failed:', sidecar.lastError);
  });
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('before-quit', () => sidecar.stop());

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

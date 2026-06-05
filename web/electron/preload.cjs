'use strict';

// Bridge for the renderer. `broker.*` calls are mediated by the main process
// (see main.cjs IPC handlers), so the sidecar token is never exposed here.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('desktop', {
  isDesktop: true,
  platform: process.platform,
  broker: {
    ready: () => ipcRenderer.invoke('broker:ready'),
    status: () => ipcRenderer.invoke('broker:status'),
    discover: (host) => ipcRenderer.invoke('broker:discover', host),
    connect: (opts) => ipcRenderer.invoke('broker:connect', opts),
    disconnect: () => ipcRenderer.invoke('broker:disconnect'),
    account: (accountId) => ipcRenderer.invoke('broker:account', accountId),
    positions: (accountId) => ipcRenderer.invoke('broker:positions', accountId),
    orders: () => ipcRenderer.invoke('broker:orders'),
    quote: (ticker) => ipcRenderer.invoke('broker:quote', ticker),
    preview: (req) => ipcRenderer.invoke('broker:preview', req),
    execute: (req) => ipcRenderer.invoke('broker:execute', req),
    cancel: (orderId) => ipcRenderer.invoke('broker:cancel', orderId),
  },
});

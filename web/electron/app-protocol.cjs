'use strict';

const fs = require('node:fs');
const path = require('node:path');

const MIME = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.mjs': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.map': 'application/json',
};

function isWithin(root, filePath) {
  const resolvedRoot = path.resolve(root);
  const resolvedFile = path.resolve(filePath);
  const rootWithSep = resolvedRoot.endsWith(path.sep) ? resolvedRoot : `${resolvedRoot}${path.sep}`;
  return resolvedFile === resolvedRoot || resolvedFile.startsWith(rootWithSep);
}

function rawPathname(requestUrl) {
  const match = requestUrl.match(/^[a-zA-Z][a-zA-Z\d+.-]*:\/\/[^/?#]*([^?#]*)/);
  return match ? match[1] || '/' : '/';
}

function resolveAppFile(distDir, requestUrl, existsSync = fs.existsSync) {
  const root = path.resolve(distDir);
  let decoded;
  try {
    decoded = decodeURIComponent(rawPathname(requestUrl));
  } catch {
    return null;
  }
  const relativePath = decoded.replace(/^\/+/, '');
  const candidate = path.resolve(root, relativePath);

  if (!isWithin(root, candidate)) {
    return null;
  }

  let filePath = candidate;
  if (!path.extname(relativePath) || !existsSync(filePath)) {
    filePath = path.join(root, 'index.html');
  }

  if (!isWithin(root, filePath)) {
    return null;
  }

  return {
    filePath,
    contentType: MIME[path.extname(filePath)] || 'application/octet-stream',
  };
}

function registerAppProtocol(protocol, distDir) {
  protocol.handle('app', async (request) => {
    const resolved = resolveAppFile(distDir, request.url);
    if (resolved === null) {
      return new Response('Not found', { status: 404 });
    }

    try {
      const data = await fs.promises.readFile(resolved.filePath);
      return new Response(data, { headers: { 'content-type': resolved.contentType } });
    } catch {
      return new Response('Not found', { status: 404 });
    }
  });
}

module.exports = { MIME, resolveAppFile, registerAppProtocol };

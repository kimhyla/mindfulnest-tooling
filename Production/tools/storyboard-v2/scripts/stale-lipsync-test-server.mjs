#!/usr/bin/env node
// Tiny static-file server used ONLY by playwright.stale-lipsync.config.ts.
//
// Listens on http://localhost:5599. Serves:
//   /                       → dist/index.html (the built v59 bundle)
//   /api/health             → 200 {ok:true}
//   any other /api/* path   → 404 (Playwright page.route mocks intercept
//                                 the real endpoints; un-mocked calls
//                                 should surface as visible 404s, not
//                                 silently proxy to a live server)
//   /asset/* /api/beat/audio/* → 404 (route mocks supply bytes)
//
// Self-contained — no Express/Vite/production_server dependency. Keeps the
// stale-lipsync RED/GREEN harness independent from Kim's live dev server
// on port 5111.

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname_here = path.dirname(__filename);
const distDir = path.resolve(__dirname_here, '..', 'dist');
const indexPath = path.join(distDir, 'index.html');

if (!fs.existsSync(indexPath)) {
  console.error(`[stale-lipsync-test-server] FATAL: dist/index.html missing at ${indexPath}. Run \`npm run build\` first.`);
  process.exit(1);
}

const PORT = 5599;

const server = http.createServer((req, res) => {
  const url = req.url || '/';

  if (url === '/api/health' || url.startsWith('/api/health?')) {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ ok: true, server: 'stale-lipsync-test-server' }));
    return;
  }

  if (url === '/' || url.startsWith('/?') || url === '/index.html') {
    const body = fs.readFileSync(indexPath);
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
    res.end(body);
    return;
  }

  // Default 404 — page.route mocks should intercept real endpoint calls
  // before they reach this server.
  res.writeHead(404, { 'content-type': 'text/plain' });
  res.end(`not found: ${url}`);
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[stale-lipsync-test-server] listening on http://localhost:${PORT}`);
});

// Graceful shutdown so Playwright's webServer teardown doesn't leave the
// process orphaned across test runs.
for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    console.log(`[stale-lipsync-test-server] ${sig} received — closing`);
    server.close(() => process.exit(0));
    // Force-exit if close stalls.
    setTimeout(() => process.exit(1), 2000).unref();
  });
}

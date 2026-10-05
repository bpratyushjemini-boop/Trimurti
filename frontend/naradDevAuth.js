/**
 * NARAD local development auth for the Vite /api proxy (Node-side only — never bundled).
 *
 * Why the proxy and not the browser:
 *   - VITE_* variables are inlined into the client bundle, which would leak the key into
 *     JavaScript shipped to the browser (and into `dist/`).
 *   - <img src="/api/...">, <audio>, and EventSource requests cannot attach custom headers,
 *     so a browser-side fetch interceptor would not cover them.
 * Injecting `Authorization: Bearer <NARAD_API_KEY>` on the dev-server proxy covers every
 * /api request in one place, and the key never leaves the developer's machine.
 *
 * Key resolution mirrors backend/app/core/config.py exactly: start from the process
 * environment, then backend/.env, backend/.venv/.env, and the project-root .env are applied
 * in order, each overriding the previous value (python-dotenv `override=True`). So the
 * proxy always sends the same key the local backend enforces. backend/.env is canonical.
 *
 * Safety:
 *   - The key value is never logged; only its source file is reported.
 *   - Auth is only injected for requests originating from loopback, so running
 *     `vite --host` does not turn the dev server into an authenticated gateway for the LAN.
 *   - A client-supplied Authorization / X-Narad-Key header is never overwritten.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const FRONTEND_DIR = path.dirname(fileURLToPath(import.meta.url));
const NARAD_DIR = path.resolve(FRONTEND_DIR, '..');
const BACKEND_DIR = path.join(NARAD_DIR, 'backend');

export const BACKEND_ENV_FILES = [
  path.join(BACKEND_DIR, '.env'),
  path.join(BACKEND_DIR, '.venv', '.env'),
  path.join(NARAD_DIR, '.env'),
];

const KEY_NAME = 'NARAD_API_KEY';

/** Return the value of `name` in a dotenv file, or undefined if the file/key is absent. */
export function readDotenvValue(file, name) {
  let text;
  try {
    text = fs.readFileSync(file, 'utf8');
  } catch {
    return undefined;
  }
  let found;
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const m = line.match(/^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
    if (!m || m[1] !== name) continue;
    let value = m[2];
    const quote = value[0];
    if ((quote === '"' || quote === "'") && value.indexOf(quote, 1) > 0) {
      value = value.slice(1, value.indexOf(quote, 1));
    } else {
      value = value.replace(/\s+#.*$/, '').trim();
    }
    found = value; // last occurrence wins, like python-dotenv
  }
  return found;
}

/** Resolve the local NARAD API key. Returns { key, source } — never log `key`. */
export function resolveNaradApiKey({ env = process.env, files = BACKEND_ENV_FILES } = {}) {
  let key = (env[KEY_NAME] || '').trim();
  let source = key ? 'process environment' : null;
  for (const file of files) {
    const value = readDotenvValue(file, KEY_NAME);
    if (value !== undefined) {
      key = value.trim();
      source = path.relative(NARAD_DIR, file);
    }
  }
  return { key, source: key ? source : null };
}

export function isLoopbackAddress(addr) {
  if (!addr) return false;
  return addr === '::1' || addr.startsWith('127.') || addr.startsWith('::ffff:127.');
}

/** Attach Bearer auth to an outgoing proxy request when appropriate. Exported for tests. */
export function attachNaradAuth(proxyReq, req, resolve = resolveNaradApiKey) {
  const headers = req.headers || {};
  if (headers.authorization || headers['x-narad-key']) return false;
  if (!isLoopbackAddress(req.socket?.remoteAddress)) return false;
  const { key } = resolve();
  if (!key) return false;
  proxyReq.setHeader('Authorization', `Bearer ${key}`);
  return true;
}

/** Build a Vite proxy entry that authenticates /api requests against the local backend. */
export function naradAuthProxy(target) {
  return {
    target,
    changeOrigin: true,
    secure: false,
    configure(proxy) {
      // Key is re-resolved per request so edits to backend/.env apply without restarting Vite.
      proxy.on('proxyReq', (proxyReq, req) => attachNaradAuth(proxyReq, req));
    },
  };
}

/** Vite plugin that reports (without revealing) where the dev auth key comes from. */
export function naradAuthStatusPlugin() {
  const report = (logger) => {
    const { source } = resolveNaradApiKey();
    if (source) {
      logger.info(`[narad-auth] /api proxy authenticating with NARAD_API_KEY from ${source} (value hidden)`);
    } else {
      logger.warn('[narad-auth] NARAD_API_KEY not found in backend/.env or environment; /api requests are forwarded unauthenticated');
    }
  };
  return {
    name: 'narad-dev-auth-status',
    apply: 'serve',
    configureServer(server) {
      report(server.config.logger);
    },
    configurePreviewServer(server) {
      report(server.config.logger);
    },
  };
}

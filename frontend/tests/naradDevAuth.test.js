// Run: npm run test:auth   (uses Node's built-in test runner; no extra deps)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import {
  readDotenvValue,
  resolveNaradApiKey,
  isLoopbackAddress,
  attachNaradAuth,
} from '../naradDevAuth.js';

const FAKE = 'unit-test-fake-key';

function tmpEnv(contents) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'narad-auth-'));
  const file = path.join(dir, '.env');
  fs.writeFileSync(file, contents);
  return file;
}

function fakeProxyReq() {
  const headers = {};
  return { headers, setHeader: (k, v) => { headers[k.toLowerCase()] = v; } };
}

test('readDotenvValue parses plain, quoted, exported and commented values', () => {
  const f = tmpEnv([
    '# comment',
    'OTHER=1',
    `NARAD_API_KEY=${FAKE}  # trailing comment`,
  ].join('\n'));
  assert.equal(readDotenvValue(f, 'NARAD_API_KEY'), FAKE);
  assert.equal(readDotenvValue(tmpEnv(`export NARAD_API_KEY="${FAKE}"`), 'NARAD_API_KEY'), FAKE);
  assert.equal(readDotenvValue(tmpEnv(`NARAD_API_KEY='${FAKE}'`), 'NARAD_API_KEY'), FAKE);
  assert.equal(readDotenvValue(tmpEnv('GROQ_API_KEY=x'), 'NARAD_API_KEY'), undefined);
  assert.equal(readDotenvValue('/nonexistent/.env', 'NARAD_API_KEY'), undefined);
});

test('resolveNaradApiKey mirrors backend precedence: later .env files override env', () => {
  const a = tmpEnv(`NARAD_API_KEY=from-a`);
  const b = tmpEnv(`NARAD_API_KEY=from-b`);
  const none = tmpEnv('GROQ_API_KEY=x');
  assert.equal(resolveNaradApiKey({ env: { NARAD_API_KEY: 'from-env' }, files: [none] }).key, 'from-env');
  assert.equal(resolveNaradApiKey({ env: { NARAD_API_KEY: 'from-env' }, files: [a] }).key, 'from-a');
  assert.equal(resolveNaradApiKey({ env: {}, files: [a, b] }).key, 'from-b');
  const empty = resolveNaradApiKey({ env: {}, files: [none] });
  assert.equal(empty.key, '');
  assert.equal(empty.source, null);
});

test('isLoopbackAddress', () => {
  for (const a of ['127.0.0.1', '::1', '::ffff:127.0.0.1', '127.0.1.1']) assert.ok(isLoopbackAddress(a), a);
  for (const a of ['192.168.1.20', '10.0.0.5', '::ffff:192.168.1.2', '', undefined]) assert.ok(!isLoopbackAddress(a), String(a));
});

test('attachNaradAuth injects Bearer for loopback requests only', () => {
  const resolve = () => ({ key: FAKE, source: 'test' });

  const local = fakeProxyReq();
  assert.equal(attachNaradAuth(local, { headers: {}, socket: { remoteAddress: '127.0.0.1' } }, resolve), true);
  assert.equal(local.headers.authorization, `Bearer ${FAKE}`);

  const lan = fakeProxyReq();
  assert.equal(attachNaradAuth(lan, { headers: {}, socket: { remoteAddress: '192.168.1.20' } }, resolve), false);
  assert.equal(lan.headers.authorization, undefined);
});

test('attachNaradAuth never overwrites client-supplied credentials and skips when no key', () => {
  const resolve = () => ({ key: FAKE, source: 'test' });
  const sock = { remoteAddress: '127.0.0.1' };

  const withBearer = fakeProxyReq();
  assert.equal(attachNaradAuth(withBearer, { headers: { authorization: 'Bearer client' }, socket: sock }, resolve), false);
  assert.equal(withBearer.headers.authorization, undefined);

  const withXKey = fakeProxyReq();
  assert.equal(attachNaradAuth(withXKey, { headers: { 'x-narad-key': 'client' }, socket: sock }, resolve), false);

  const noKey = fakeProxyReq();
  assert.equal(attachNaradAuth(noKey, { headers: {}, socket: sock }, () => ({ key: '', source: null })), false);
  assert.equal(noKey.headers.authorization, undefined);
});

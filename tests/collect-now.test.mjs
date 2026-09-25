import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import handler from '../netlify/functions/collect-now.mjs';

const endpoint = 'https://radar-licita-tinet.netlify.app/.netlify/functions/collect-now';
const originalFetch = global.fetch;
const originalEnv = {
  VITE_SUPABASE_PUBLISHABLE_KEY: process.env.VITE_SUPABASE_PUBLISHABLE_KEY,
  RADAR_SUPABASE_PUBLISHABLE_KEY: process.env.RADAR_SUPABASE_PUBLISHABLE_KEY,
  RADAR_GITHUB_DISPATCH_TOKEN: process.env.RADAR_GITHUB_DISPATCH_TOKEN,
};

function request(method = 'POST', origin = 'https://radar-licita-tinet.netlify.app', token = 'valid.jwt.token') {
  return new Request(endpoint, {
    method,
    headers: { Origin: origin, Authorization: `Bearer ${token}` },
  });
}

beforeEach(() => {
  process.env.VITE_SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_test';
  process.env.RADAR_GITHUB_DISPATCH_TOKEN = 'github_pat_test';
});

afterEach(() => {
  global.fetch = originalFetch;
  for (const [key, value] of Object.entries(originalEnv)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
});

test('rejects GET and requests from another origin before contacting other services', async () => {
  global.fetch = () => { throw new Error('Should not fetch'); };
  assert.equal((await handler(request('GET'))).status, 405);
  assert.equal((await handler(request('POST', 'https://evil.example'))).status, 403);
});

test('requires a bearer session', async () => {
  global.fetch = () => { throw new Error('Should not fetch'); };
  const response = await handler(new Request(endpoint, {
    method: 'POST', headers: { Origin: 'https://radar-licita-tinet.netlify.app' },
  }));
  assert.equal(response.status, 401);
});

test('does not let Diego or another panel member start a collection', async () => {
  const calls = [];
  global.fetch = async (url) => {
    calls.push(url);
    return Response.json({ email: 'diegosmfranca@hotmail.com' });
  };
  assert.equal((await handler(request())).status, 403);
  assert.equal(calls.length, 1);
});

test('checks owner against the live database allowlist', async () => {
  const calls = [];
  global.fetch = async (url) => {
    calls.push(url);
    return calls.length === 1
      ? Response.json({ email: 'bi@tinettecnologia.com.br' })
      : Response.json(false);
  };
  assert.equal((await handler(request())).status, 403);
  assert.equal(calls.length, 2);
});

test('dispatches the existing GitHub workflow for the authorized owner', async () => {
  const calls = [];
  global.fetch = async (url, options) => {
    calls.push({ url, options });
    if (calls.length === 1) return Response.json({ email: 'bi@tinettecnologia.com.br' });
    if (calls.length === 2) return Response.json(true);
    return new Response(null, { status: 204 });
  };
  const response = await handler(request());
  assert.equal(response.status, 202);
  assert.match((await response.json()).message, /Coleta solicitada/);
  assert.match(calls[2].url, /radar-sync\.yml\/dispatches$/);
  assert.deepEqual(JSON.parse(calls[2].options.body), { ref: 'main' });
  assert.equal(calls[2].options.headers.Authorization, 'Bearer github_pat_test');
});

test('reports missing GitHub configuration without dispatching', async () => {
  delete process.env.RADAR_GITHUB_DISPATCH_TOKEN;
  let calls = 0;
  global.fetch = async () => {
    calls += 1;
    return calls === 1
      ? Response.json({ email: 'bi@tinettecnologia.com.br' })
      : Response.json(true);
  };
  assert.equal((await handler(request())).status, 503);
  assert.equal(calls, 2);
});

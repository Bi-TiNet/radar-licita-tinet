const SUPABASE_URL = 'https://bcjrwgnmwajvbidhnzuk.supabase.co';
const COLLECTOR_EMAILS = new Set([
  'bi@tinettecnologia.com.br',
  'diegosmfranca@hotmail.com',
]);
const SITE_ORIGIN = 'https://radar-licita-tinet.netlify.app';
const WORKFLOW_URL = 'https://api.github.com/repos/Bi-TiNet/radar-licita-tinet/actions/workflows/radar-sync.yml/dispatches';

function json(status, body) {
  return Response.json(body, {
    status,
    headers: { 'Cache-Control': 'no-store' },
  });
}

async function verifiedCollector(jwt, publishableKey) {
  const headers = { apikey: publishableKey, Authorization: `Bearer ${jwt}` };
  const userResponse = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
    headers,
    signal: AbortSignal.timeout(15000),
  });
  if (!userResponse.ok) return false;
  const user = await userResponse.json();
  if (!COLLECTOR_EMAILS.has(user.email?.toLowerCase())) return false;

  // Keep the database allowlist authoritative if this account is ever revoked.
  const accessResponse = await fetch(`${SUPABASE_URL}/rest/v1/rpc/radar_is_authorized`, {
    method: 'POST',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: '{}',
    signal: AbortSignal.timeout(15000),
  });
  return accessResponse.ok && (await accessResponse.json()) === true;
}

export default async function handler(request) {
  if (request.method !== 'POST') return json(405, { error: 'Método não permitido.' });
  if (request.headers.get('origin') !== SITE_ORIGIN) {
    return json(403, { error: 'Origem não autorizada.' });
  }

  const match = /^Bearer ([A-Za-z0-9._~-]+)$/.exec(request.headers.get('authorization') || '');
  if (!match) return json(401, { error: 'Entre novamente para iniciar a coleta.' });

  const publishableKey = process.env.VITE_SUPABASE_PUBLISHABLE_KEY || process.env.RADAR_SUPABASE_PUBLISHABLE_KEY;
  if (!publishableKey) return json(503, { error: 'Autenticação da coleta não configurada no servidor.' });

  try {
    if (!(await verifiedCollector(match[1], publishableKey))) {
      return json(403, { error: 'Sua conta não pode iniciar coletas.' });
    }

    const githubToken = process.env.RADAR_GITHUB_DISPATCH_TOKEN;
    if (!githubToken) {
      return json(503, { error: 'Coleta manual ainda não configurada no servidor.' });
    }

    const response = await fetch(WORKFLOW_URL, {
      method: 'POST',
      headers: {
        Accept: 'application/vnd.github+json',
        Authorization: `Bearer ${githubToken}`,
        'Content-Type': 'application/json',
        'X-GitHub-Api-Version': '2026-03-10',
      },
      body: JSON.stringify({ ref: 'main' }),
      signal: AbortSignal.timeout(15000),
    });
    if (!response.ok) {
      const error = response.status === 401 || response.status === 403
        ? 'O GitHub recusou a credencial de coleta. Verifique a permissão Actions: escrita.'
        : 'O GitHub não conseguiu iniciar a coleta agora. Tente novamente mais tarde.';
      return json(502, { error });
    }
    return json(202, { message: 'Coleta solicitada. Acompanhe o resultado na aba Coletas.' });
  } catch {
    return json(502, { error: 'Não foi possível iniciar a coleta. Tente novamente.' });
  }
}

const BASE = '';
const TOKEN_KEY = 'sentinel_token';

export function getToken() {
  try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(token) {
  try { sessionStorage.setItem(TOKEN_KEY, token); } catch { /* storage unavailable */ }
}
export function clearToken() {
  try { sessionStorage.removeItem(TOKEN_KEY); } catch { /* storage unavailable */ }
}

async function request(method, path, body, { skipAuth = false } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token && !skipAuth) headers.Authorization = `Bearer ${token}`;
  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${BASE}${path}`, opts);
  if (res.status === 401 && !skipAuth) {
    clearToken();
    window.dispatchEvent(new Event('sentinel-auth-expired'));
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  health: () => request('GET', '/health'),
  login: async (username, password) => {
    const data = await request('POST', '/auth/login', { username, password }, { skipAuth: true });
    setToken(data.access_token);
    return data;
  },
  // trailing slash avoids FastAPI's 307 redirect, which would drop the Authorization header
  getIncidents: (params) => request('GET', `/incidents/${params ? '?' + new URLSearchParams(params) : ''}`),
  getIncident:  (id)     => request('GET', `/incidents/${id}`),
  postActivity: (data)   => request('POST', '/events/activity', data),
};

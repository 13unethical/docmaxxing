/* CSRF token for same-origin state-changing requests. The token comes from
   <meta name="csrf-token">, is kept in memory only and is never sent to other origins.
   Rotated tokens (login, logout) arrive in the X-CSRF-Token response header. */
(function (global) {
  'use strict';

  if (global.DMCsrf) return;

  const HEADER = 'X-CSRF-Token';
  const FIELD = 'csrf_token';
  const SAFE = new Set(['GET', 'HEAD', 'OPTIONS', 'TRACE']);
  const meta = document.querySelector('meta[name="csrf-token"]');
  let token = meta ? meta.getAttribute('content') || '' : '';
  const nativeFetch = global.fetch.bind(global);

  function setToken(value) {
    if (!value || value === token) return;
    token = value;
    if (meta) meta.setAttribute('content', value);
  }

  function sameOrigin(url) {
    try {
      return new URL(url, global.location.href).origin === global.location.origin;
    } catch (_) {
      return false;
    }
  }

  async function refresh() {
    const res = await nativeFetch('/api/csrf-token', { credentials: 'same-origin', cache: 'no-store' });
    const data = await res.json().catch(() => ({}));
    setToken(data.csrf_token || res.headers.get(HEADER) || '');
    return token;
  }

  function withToken(input, init) {
    const opts = Object.assign({}, init || {});
    const headers = new Headers(opts.headers || (input instanceof Request ? input.headers : undefined));
    headers.set(HEADER, token);
    opts.headers = headers;
    return opts;
  }

  async function isCsrfRejection(res) {
    if (res.status !== 403) return false;
    const data = await res.clone().json().catch(() => null);
    return !!(data && data.error === 'CSRF_FAILED');
  }

  global.fetch = async function (input, init) {
    const url = input instanceof Request ? input.url : String(input);
    const method = String((init && init.method) || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    if (!sameOrigin(url)) return nativeFetch(input, init);
    if (SAFE.has(method)) {
      const res = await nativeFetch(input, init);
      setToken(res.headers.get(HEADER));
      return res;
    }
    if (!token) await refresh().catch(() => '');
    let res = await nativeFetch(input, withToken(input, init));
    setToken(res.headers.get(HEADER));
    const body = init && init.body;
    const streamed = typeof ReadableStream !== 'undefined' && body instanceof ReadableStream;
    const replayable = !(input instanceof Request) && !streamed;
    if (replayable && (await isCsrfRejection(res))) {
      // Rejected before the handler ran (token rotated in another tab), so one retry is safe.
      await refresh();
      res = await nativeFetch(input, withToken(input, init));
      setToken(res.headers.get(HEADER));
    }
    return res;
  };

  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if ((form.getAttribute('method') || 'get').toUpperCase() !== 'POST') return;
    if (!sameOrigin(form.getAttribute('action') || global.location.href)) return;
    let input = form.querySelector(`input[name="${FIELD}"]`);
    if (!input) {
      input = document.createElement('input');
      input.type = 'hidden';
      input.name = FIELD;
      form.appendChild(input);
    }
    if (token) input.value = token;
  }, true);

  global.DMCsrf = { token: () => token, refresh, header: HEADER };
})(window);

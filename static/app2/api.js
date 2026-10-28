/* DocMaxxing app — thin client for the Flask JSON API. Every call resolves with the
   parsed payload or rejects with an Error carrying { code, status, data }. */
(function (global) {
  'use strict';

  class ApiError extends Error {
    constructor(message, { code = '', status = 0, data = null } = {}) {
      super(message);
      this.code = code;
      this.status = status;
      this.data = data;
    }
  }

  const CODE_RE = /^[A-Z][A-Z0-9_]+$/;

  async function request(method, url, { json, form, timeoutMs } = {}) {
    const init = { method, credentials: 'same-origin', headers: { Accept: 'application/json' } };
    if (json !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(json);
    } else if (form) {
      init.body = form;
    }
    let timer = null;
    if (timeoutMs) {
      const ctl = new AbortController();
      init.signal = ctl.signal;
      timer = setTimeout(() => ctl.abort(), timeoutMs);
    }
    let res;
    try {
      res = await fetch(url, init);
    } catch (err) {
      throw new ApiError('Network error. Check your connection and try again.', { code: 'NETWORK' });
    } finally {
      if (timer) clearTimeout(timer);
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.success === false) {
      const raw = data.error || '';
      const code = CODE_RE.test(raw) ? raw : (res.status === 402 ? 'INSUFFICIENT_COINS' : '');
      const message = data.message || (code ? '' : raw) || `Request failed (HTTP ${res.status})`;
      throw new ApiError(message, { code, status: res.status, data });
    }
    return data;
  }

  const isCyrillic = (text) => {
    const letters = text.match(/\p{L}/gu) || [];
    if (!letters.length) return false;
    const cyr = letters.filter(ch => /\p{Script=Cyrillic}/u.test(ch)).length;
    return cyr / letters.length > 0.5;
  };

  async function fingerprint() {
    try { return global.DMDeviceFingerprint ? await global.DMDeviceFingerprint() : ''; } catch { return ''; }
  }

  function referralCode() {
    try {
      const params = new URLSearchParams(global.location.search);
      return params.get('ref') || params.get('referral_code') || sessionStorage.getItem('dm_pending_ref') || '';
    } catch { return ''; }
  }

  const api = {
    ApiError,

    login: (email, password) => request('POST', '/api/auth/login', { json: { email, password } }),
    async register({ email, password, passwordConfirm, name }) {
      const body = { email, password, password_confirm: passwordConfirm, name: name || '', next: '/app' };
      const ref = referralCode();
      if (ref) body.referral_code = ref;
      const fp = await fingerprint();
      if (fp) body.device_fingerprint = fp;
      return request('POST', '/api/auth/register', { json: body });
    },
    logout: () => request('POST', '/api/auth/logout', { json: {} }),

    balance: () => request('GET', '/api/economy/balance'),
    transactions: (limit = 50) => request('GET', `/api/economy/transactions?limit=${limit}`),

    async extractText(file) {
      if (/\.txt$/i.test(file.name) || (file.type || '').startsWith('text/')) return file.text();
      const form = new FormData();
      form.append('file', file);
      const data = await request('POST', '/api/extract-document', { form });
      return String(data.text || '');
    },

    humanize(text, source = 'standalone') {
      const url = isCyrillic(text) ? '/api/browser/providers/ru/humanize' : '/api/browser/providers/stealthwriter/humanize';
      return request('POST', url, { json: { text, source } });
    },

    editor: {
      detect: (text) => request('POST', '/api/workspace/detect', { json: { text }, timeoutMs: 180000 }),
      citeSearch: (query, style) => request('POST', '/api/workspace/citations/search', { json: { query, style, limit: 6 }, timeoutMs: 60000 }),
      citeUse: (action, doi) => request('POST', '/api/workspace/citations/use', { json: { action, doi: doi || '' } }),
      async export(title, html) {
        const res = await fetch('/api/workspace/export', {
          method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ title, html }),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          const raw = data.error || '';
          throw new ApiError(CODE_RE.test(raw) ? (data.message || '') : (raw || `Export failed (HTTP ${res.status})`),
            { code: CODE_RE.test(raw) ? raw : '', status: res.status, data });
        }
        const name = (res.headers.get('Content-Disposition') || '').match(/filename\*?=(?:UTF-8'')?"?([^";]+)/i);
        return { blob: await res.blob(), name: name ? decodeURIComponent(name[1]) : 'document.docx' };
      },
    },

    turnitin: {
      list: () => request('GET', '/api/turnitin/reports'),
      get: (id) => request('GET', `/api/turnitin/submissions/${encodeURIComponent(id)}`),
      remove: (id) => request('DELETE', `/api/turnitin/submissions/${encodeURIComponent(id)}`),
      highlights: (id) => request('POST', `/api/turnitin/submissions/${encodeURIComponent(id)}/highlights`),
      check(file) {
        const form = new FormData();
        form.append('file', file);
        form.append('exclude_bibliography', '0');
        form.append('exclude_quotes', '0');
        return request('POST', '/api/turnitin/check', { form });
      },
      reportUrl: (id, kind) => `/api/turnitin/submissions/${encodeURIComponent(id)}/report/${kind}`,
    },

    format: {
      run({ file, text, style, overrides }) {
        const form = new FormData();
        if (file) form.append('file', file);
        else form.append('pasted_text', text || '');
        form.append('format_style', style);
        form.append('overrides', JSON.stringify(overrides || {}));
        return request('POST', '/api/format-v2', { form, timeoutMs: 300000 });
      },
      parseBrief(text, style) {
        const form = new FormData();
        form.append('requirements_text', text);
        form.append('format_style', style);
        return request('POST', '/api/extract-requirements-v2', { form, timeoutMs: 120000 });
      },
      async download(documentId) {
        const res = await fetch(`/api/format-v2/download/${encodeURIComponent(documentId)}`, { credentials: 'same-origin' });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new ApiError(data.error || `Download failed (HTTP ${res.status})`, { status: res.status, data });
        }
        return res.blob();
      },
    },

    format: {
      run({ file, text, style, overrides }) {
        const form = new FormData();
        if (file) form.append('file', file);
        else form.append('pasted_text', text || '');
        form.append('format_style', style);
        form.append('overrides', JSON.stringify(overrides || {}));
        return request('POST', '/api/format-v2', { form, timeoutMs: 180000 });
      },
      parseBrief(text, style) {
        const form = new FormData();
        form.append('requirements_text', text);
        form.append('format_style', style);
        return request('POST', '/api/extract-requirements-v2', { form, timeoutMs: 90000 });
      },
      async download(id) {
        const res = await fetch(`/api/format-v2/download/${encodeURIComponent(id)}`, { credentials: 'same-origin' });
        if (!res.ok) throw new ApiError('This file has expired. Format the document again.', { status: res.status });
        return res.blob();
      },
    },

    review: {
      requirements({ text, file }) {
        const form = new FormData();
        if (text) form.append('requirements_text', text);
        if (file) form.append('file', file);
        return request('POST', '/api/extract-requirements', { form, timeoutMs: 90000 });
      },
      check({ file, text, docType, requirements, parsed }) {
        const form = new FormData();
        if (file) form.append('file', file);
        else form.append('pasted_text', text || '');
        form.append('document_type', docType || 'other');
        form.append('requirements', requirements || '');
        if (parsed) form.append('parsed_requirements', JSON.stringify(parsed));
        return request('POST', '/api/check-document', { form, timeoutMs: 180000 });
      },
    },

    assignment: (() => {
      const base = (id) => `/api/assignment/projects/${encodeURIComponent(id)}`;
      // Pipeline steps call the LLM and can run for several minutes (gunicorn timeout is 600 s).
      const LONG = 600000;
      return {
        upload({ files, note }) {
          const form = new FormData();
          files.forEach((f, i) => form.append(i === 0 ? 'assignment_brief' : 'additional_files', f, f.name));
          if (note) form.append('note', note);
          form.append('priority', 'standard');
          return request('POST', '/api/assignment/projects/upload', { form, timeoutMs: 120000 });
        },
        get: (id) => request('GET', base(id)),
        analyze: (id) => request('POST', `${base(id)}/analyze-requirements`, { json: {}, timeoutMs: LONG }),
        price: (id) => request('POST', `${base(id)}/pricing`, { json: { priority: 'standard' } }),
        brief: (id, fields) => request('POST', `${base(id)}/brief`, { json: fields }),
        confirm: (id) => request('POST', `${base(id)}/confirm-payment`, { json: {} }),
        step: (id, path, body) => request('POST', base(id) + path, { json: body || {}, timeoutMs: LONG }),
        revise: (id, message) => request('POST', `${base(id)}/revision-chat`, { json: { message }, timeoutMs: LONG }),
        revisions: (id) => request('GET', `${base(id)}/revision-chat`),
        refund: (id) => request('POST', `${base(id)}/refund-failed`, { json: {} }),
        downloadUrl: (id) => `${base(id)}/download`,
      };
    })(),

    presentation: {
      extract(file) {
        const form = new FormData();
        form.append('file', file, file.name);
        return request('POST', '/api/presentation/extract', { form, timeoutMs: 120000 });
      },
      // Web research + writing + photos can take a few minutes.
      generate: (body) => request('POST', '/api/presentation/generate', { json: body, timeoutMs: 600000 }),
      async export(deck) {
        const res = await fetch('/api/presentation/export', {
          method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ deck }),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new ApiError(data.error || `Download failed (HTTP ${res.status})`, { status: res.status, data });
        }
        const name = (res.headers.get('Content-Disposition') || '').match(/filename\*?=(?:UTF-8'')?"?([^";]+)/i);
        return { blob: await res.blob(), name: name ? decodeURIComponent(name[1]) : 'presentation.pptx' };
      },
    },

    account: {
      profile: (name) => request('POST', '/api/account/profile', { json: { name } }),
      password: (current, next, confirm) => request('POST', '/api/account/password',
        { json: { current_password: current, new_password: next, confirm_password: confirm } }),
      avatar(file) {
        const form = new FormData();
        form.append('avatar', file);
        return request('POST', '/api/upload_avatar', { form });
      },
    },
    feedback: (message) => request('POST', '/api/feedback', { json: { message } }),
    contact: (body) => request('POST', '/api/contact', { json: body }),

    checkout: (what) => request('POST', '/api/payments/create', { json: { ...what, return_to: 'app' } }),
    billing: () => request('GET', '/api/billing'),

    veil: {
      unlock: () => request('POST', '/api/veil/unlock', { json: {} }),
      emailLink: () => request('POST', '/api/veil/email-link', { json: {} }),
    },

    admin: (() => {
      const P = '/api/admin/panel';
      const qs = (params) => {
        const q = new URLSearchParams();
        Object.entries(params || {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') q.set(k, v); });
        const s = q.toString();
        return s ? '?' + s : '';
      };
      return {
        overview: () => request('GET', `${P}/overview`),
        users: (params) => request('GET', `${P}/users${qs(params)}`),
        user: (id) => request('GET', `${P}/users/${id}`),
        usersCsvUrl: `${P}/users.csv`,
        credits: (id, delta, reason) => request('POST', `${P}/users/${id}/credits`, { json: { delta, reason } }),
        block: (id, blocked, removeBonus) =>
          request('POST', `${P}/users/${id}/block`, { json: { blocked, remove_bonus: !!removeBonus } }),
        blockMany: (ids) => request('POST', `${P}/users/block`, { json: { ids, remove_bonus: true } }),
        flag: (id, flag) => request('POST', `${P}/users/${id}/flag`, { json: { flag } }),
        clear: (id, cleared) => request('POST', `${P}/users/${id}/clear`, { json: { cleared } }),
        activity: (params) => request('GET', `${P}/activity${qs(params)}`),
        setAdmin: (id, isAdmin) => request('PATCH', `/api/admin/users/${id}/admin`, { json: { is_admin: isAdmin } }),
        deleteUser: (id) => request('POST', `/api/admin/users/${id}/delete`, { json: {} }),
        dailyStats: () => request('GET', '/api/admin/daily-stats'),
        siteSettings: (patch) => request('PATCH', '/api/admin/site-settings', { json: patch }),
        preflight: (browser) => request('GET', '/api/admin/pipeline-preflight' + (browser ? '?browser=1' : ''),
          { timeoutMs: browser ? 45000 : 15000 }),
        datasetStats: () => request('GET', '/api/admin/dataset-stats'),
      };
    })(),

    referral: {
      me: () => request('GET', '/api/referral/me'),
      convert: (amountUsd) => request('POST', '/api/referral/convert', { json: { amount_usd: amountUsd } }),
      withdraw: (amountUsd, walletDetails) =>
        request('POST', '/api/referral/withdraw', { json: { amount_usd: amountUsd, wallet_details: walletDetails } }),
    },
  };

  global.DMX = global.DMX || {};
  global.DMX.api = api;
})(window);

/* Landing-page humanizer widget. No dependencies; the page is complete without it. */
(function () {
  'use strict';

  var form = document.querySelector('[data-lp-tool]');
  if (!form || !window.fetch) return;

  var lang = form.getAttribute('data-lang') === 'ru' ? 'ru' : 'en';
  var endpoint = form.getAttribute('data-endpoint');
  var maxWords = parseInt(form.getAttribute('data-max-words'), 10) || 0;
  var hardMax = parseInt(form.getAttribute('data-hard-max-words'), 10) || 0;
  var signupUrl = form.getAttribute('data-signup-url') || '/register';
  var enPage = form.getAttribute('data-en-page') || '/humanizer';
  var blockCyrillic = form.getAttribute('data-block-cyrillic') === '1';

  var input = form.querySelector('#lp-input');
  var output = form.querySelector('#lp-output');
  var count = form.querySelector('#lp-count');
  var runBtn = form.querySelector('#lp-run');
  var copyBtn = form.querySelector('#lp-copy');
  var msg = form.querySelector('#lp-msg');

  var T = {
    en: {
      words: 'words', run: 'Humanize', running: 'Humanizing…', copy: 'Copy', copied: 'Copied',
      empty: 'Paste some text first.',
      tooLong: function (n) { return 'Free runs take up to ' + n + ' words. Create a free account for longer texts and more runs.'; },
      limit: 'You have used today’s free runs. Create a free account to get more — it takes a minute.',
      signup: 'Create a free account', rate: 'Too many requests. Wait a minute and try again.',
      retry: 'The humanizer could not finish this time. Nothing was counted — please try again.',
      network: 'Network error. Check your connection and try again.',
      hardMax: function (n) { return 'Texts up to ' + n + ' words can be humanized at once. Split it into parts.'; },
      englishOnly: 'The humanizer works with English text for now. Paste an English draft and try again.'
    },
    ru: {
      words: 'слов', run: 'Очеловечить текст', running: 'Обрабатываем…', copy: 'Копировать', copied: 'Скопировано',
      empty: 'Сначала вставьте текст.',
      tooLong: function (n) { return 'Бесплатно — до ' + n + ' слов за раз. Создайте бесплатный аккаунт, чтобы обрабатывать тексты длиннее.'; },
      limit: 'Бесплатные запуски на сегодня закончились. Создайте бесплатный аккаунт — это займёт минуту.',
      signup: 'Создать аккаунт бесплатно', rate: 'Слишком много запросов. Подождите минуту и попробуйте снова.',
      retry: 'Не получилось обработать текст. Запуск не засчитан — попробуйте ещё раз.',
      network: 'Ошибка сети. Проверьте подключение и попробуйте снова.',
      hardMax: function (n) { return 'За раз можно обработать до ' + n + ' слов. Разделите текст на части.'; },
      cyrillic: 'Русскоязычный движок пока в разработке, поэтому русский текст мы не отправляем. Сейчас хуманайзер работает с английскими текстами — вставьте английский текст или откройте ',
      enLink: 'англоязычную версию'
    }
  }[lang];

  var fmt = function (n) { return lang === 'ru' ? String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0') : n.toLocaleString('en-US'); };
  var countWords = function (text) { var m = text.match(/\S+/g); return m ? m.length : 0; };
  var isCyrillic = function (text) {
    var letters = text.match(/[A-Za-z\u0400-\u04FF]/g) || [];
    if (!letters.length) return false;
    var cyr = letters.filter(function (ch) { return /[\u0400-\u04FF]/.test(ch); }).length;
    return cyr / letters.length > 0.3;
  };

  function track(name, data) {
    try { if (window.umami && typeof window.umami.track === 'function') window.umami.track(name, data); } catch (e) { /* analytics is optional */ }
  }

  function showMessage(text, kind, opts) {
    opts = opts || {};
    msg.textContent = '';
    msg.className = 'lp-tool-msg' + (kind ? ' is-' + kind : '');
    var p = document.createElement('p');
    p.style.margin = '0';
    p.textContent = text;
    if (opts.link) {
      var a = document.createElement('a');
      a.href = opts.link.href;
      a.textContent = opts.link.text;
      p.appendChild(a);
      p.appendChild(document.createTextNode('.'));
    }
    msg.appendChild(p);
    if (opts.signup) {
      var btn = document.createElement('a');
      btn.className = 'lp-btn lp-btn-primary';
      btn.href = signupUrl;
      btn.textContent = T.signup;
      btn.setAttribute('data-umami-event', 'landing_signup_click');
      btn.setAttribute('data-umami-event-place', 'tool_' + opts.signup);
      msg.appendChild(btn);
    }
    msg.hidden = false;
  }

  function hideMessage() { msg.hidden = true; msg.textContent = ''; }

  function updateCount() {
    var words = countWords(input.value);
    count.textContent = fmt(words) + ' / ' + fmt(maxWords) + ' ' + T.words;
    count.classList.toggle('is-over', maxWords > 0 && words > maxWords);
    return words;
  }

  function setBusy(busy) {
    runBtn.disabled = busy;
    runBtn.textContent = busy ? T.running : T.run;
    form.setAttribute('aria-busy', busy ? 'true' : 'false');
  }

  input.addEventListener('input', updateCount);
  input.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); form.requestSubmit ? form.requestSubmit() : run(); }
  });

  copyBtn.addEventListener('click', function () {
    var text = output.textContent || '';
    if (!text) return;
    var done = function () {
      copyBtn.textContent = T.copied;
      setTimeout(function () { copyBtn.textContent = T.copy; }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fallback);
    } else {
      fallback();
    }
    function fallback() {
      var range = document.createRange();
      range.selectNodeContents(output);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      try { document.execCommand('copy'); done(); } catch (e) { /* user can copy the selection */ }
    }
  });

  form.addEventListener('submit', function (e) { e.preventDefault(); run(); });

  function run() {
    hideMessage();
    var text = input.value.trim();
    var words = updateCount();
    if (!text) { showMessage(T.empty, 'error'); input.focus(); return; }
    if (blockCyrillic && isCyrillic(text)) {
      showMessage(T.cyrillic, 'cta', { link: { href: enPage, text: T.enLink } });
      track('landing_humanize_run', { lang: lang, outcome: 'ru_unavailable', words: words });
      return;
    }
    if (hardMax && words > hardMax) { showMessage(T.hardMax(fmt(hardMax)), 'error'); return; }
    if (maxWords && words > maxWords) {
      showMessage(T.tooLong(fmt(maxWords)), 'cta', { signup: 'too_long' });
      track('landing_humanize_run', { lang: lang, outcome: 'too_long', words: words });
      return;
    }

    setBusy(true);
    output.textContent = '';
    copyBtn.disabled = true;
    fetch(endpoint, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ text: text, source: 'landing' })
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) { return { res: res, data: data }; });
    }).then(function (r) {
      var data = r.data || {};
      if (r.res.ok && data.success !== false && data.humanized_text) {
        output.textContent = String(data.humanized_text).trim();
        copyBtn.disabled = false;
        track('landing_humanize_run', { lang: lang, outcome: 'ok', words: words });
        return;
      }
      var code = data.error || '';
      if (code === 'REGISTER_REQUIRED' || code === 'FREE_LIMIT_REACHED' || code === 'AUTH_REQUIRED') {
        showMessage(T.limit, 'cta', { signup: 'limit' });
      } else if (code === 'FREE_WORD_LIMIT') {
        showMessage(T.tooLong(fmt(data.max_words || maxWords)), 'cta', { signup: 'too_long' });
      } else if (code === 'TOO_MANY_WORDS') {
        showMessage(T.hardMax(fmt(data.max_words || hardMax)), 'error');
      } else if (code === 'FREE_ENGLISH_ONLY') {
        if (lang === 'ru') showMessage(T.cyrillic, 'cta', { link: { href: enPage, text: T.enLink } });
        else showMessage(T.englishOnly, 'error');
      } else if (r.res.status === 429 || code === 'RATE_LIMITED') {
        showMessage(T.rate, 'error');
      } else {
        showMessage(T.retry, 'error');
      }
      track('landing_humanize_run', { lang: lang, outcome: code || ('http_' + r.res.status), words: words });
    }).catch(function () {
      showMessage(T.network, 'error');
      track('landing_humanize_run', { lang: lang, outcome: 'network', words: words });
    }).then(function () { setBusy(false); });
  }

  updateCount();
})();

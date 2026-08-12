/* ============================================================
   DocMaxxing — переключение темы
   Файл: static/js/theme.js  (подключать в конце <body>)

   ВАЖНО: отдельно, в <head> base.html, ПЕРВЫМ скриптом,
   вставить сниппет из THEME_HEAD_SNIPPET (см. низ файла).
   Без него будет вспышка светлой темы при загрузке.
   ============================================================ */

(function () {
  'use strict';

  var STORAGE_KEY = 'dm-theme';
  var root = document.documentElement;

  function systemTheme() {
    return window.matchMedia &&
           window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function stored() {
    try { return localStorage.getItem(STORAGE_KEY); } catch (e) { return null; }
  }

  function apply(theme, animate) {
    if (animate) {
      root.classList.add('theme-switching');
      window.setTimeout(function () {
        root.classList.remove('theme-switching');
      }, 60);
    }
    root.setAttribute('data-theme', theme);
    root.style.colorScheme = theme;

    document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
      btn.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
    });
  }

  function set(theme) {
    try { localStorage.setItem(STORAGE_KEY, theme); } catch (e) {}
    apply(theme, true);
  }

  // Текущее значение уже проставлено сниппетом в <head>.
  // Здесь только вешаем обработчики и следим за системной темой.
  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('[data-theme-toggle]');
    if (!btn) return;
    set(root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
  });

  if (window.matchMedia) {
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    var onChange = function () {
      if (!stored()) apply(systemTheme(), true);  // выбор пользователя приоритетнее
    };
    if (mq.addEventListener) mq.addEventListener('change', onChange);
    else if (mq.addListener) mq.addListener(onChange);
  }

  // Наружу — на случай, если тему надо переключить из другого кода
  window.dmTheme = {
    get: function () { return root.getAttribute('data-theme'); },
    set: set,
    reset: function () {
      try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
      apply(systemTheme(), true);
    }
  };
})();


/* ============================================================
   THEME_HEAD_SNIPPET
   Скопировать ЭТО в <head> base.html первым скриптом,
   до всех <link rel="stylesheet">:

<script>
(function(){try{
  var t=localStorage.getItem('dm-theme');
  if(!t){t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}
  document.documentElement.setAttribute('data-theme',t);
  document.documentElement.style.colorScheme=t;
}catch(e){document.documentElement.setAttribute('data-theme','light');}})();
</script>

   ============================================================ */

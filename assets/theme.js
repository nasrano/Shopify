(function () {
  'use strict';

  var scroller = document.getElementById('privat-scroller');
  var backdrop = document.getElementById('privat-backdrop');
  var app = document.getElementById('privat-app');
  var toastEl = document.getElementById('privat-toast');
  var toastTimer = null;

  /* ---------------- overlays ---------------- */
  function drawers() {
    return app.querySelectorAll('[data-drawer]');
  }

  var CLOSE_MS = 260;
  function closeAll() {
    var any = false;
    drawers().forEach(function (d) {
      if (d.classList.contains('is-open') && !d.classList.contains('is-closing')) {
        any = true;
        d.classList.add('is-closing');
        setTimeout(function () { d.classList.remove('is-open', 'is-closing'); }, CLOSE_MS);
      }
    });
    if (any) {
      backdrop.classList.add('is-closing');
      setTimeout(function () { backdrop.classList.remove('is-open', 'is-closing'); }, CLOSE_MS);
    } else {
      backdrop.classList.remove('is-open');
    }
    if (scroller) scroller.classList.remove('no-scroll');
    syncNavActive(null);
  }

  function open(name, opener) {
    drawers().forEach(function (d) {
      d.classList.remove('is-closing');
      d.classList.toggle('is-open', d.getAttribute('data-drawer') === name);
    });
    backdrop.classList.remove('is-closing');
    backdrop.classList.add('is-open');
    if (scroller) scroller.classList.add('no-scroll');
    syncNavActive(name);
    if (name === 'search') {
      var input = document.getElementById('privat-search-input');
      if (input) setTimeout(function () { input.focus({ preventScroll: true }); }, 50);
    }
    if (name === 'cart') renderCart();
    if (name === 'favs') renderFavorites();
    if (name === 'cats') {
      catStack.length = 0;
      catStack.push('root');
      var target = opener && opener.getAttribute('data-cat-target');
      if (target && document.querySelector('[data-cat-panel="' + target + '"]')) catStack.push(target);
      catShow();
    }
  }

  function defaultNav() {
    var p = window.location.pathname;
    if (p === '/' || p === '') return 'home';
    if (p.indexOf('/collections') === 0 || p.indexOf('/products') === 0) return 'shop';
    if (p.indexOf('/search') === 0) return 'search';
    if (p.indexOf('/account') === 0) return 'acc';
    return null;
  }

  function syncNavActive(overlayName) {
    var current = overlayName === null ? defaultNav() : overlayName;
    app.querySelectorAll('.privat-nav__btn').forEach(function (b) {
      var target = b.getAttribute('data-nav-active-for');
      b.classList.toggle('is-active', target !== null && target === current);
    });
  }

  /* ---------------- categories: 3-level drill panels ---------------- */
  var catStack = ['root'];
  function catShow() {
    document.querySelectorAll('[data-cat-panel]').forEach(function (p) {
      var id = p.getAttribute('data-cat-panel');
      p.classList.toggle('is-active', id === catStack[catStack.length - 1]);
      p.classList.toggle('is-left', id !== catStack[catStack.length - 1] && catStack.indexOf(id) > -1);
    });
  }
  document.addEventListener('click', function (e) {
    var drill = e.target.closest('[data-cat-drill]');
    if (drill) { catStack.push(drill.getAttribute('data-cat-drill')); catShow(); return; }
    var back = e.target.closest('[data-cat-back]');
    if (back) {
      if (catStack.length > 1) catStack.pop();
      catShow();
    }
  });

  document.addEventListener('click', function (e) {
    var opener = e.target.closest('[data-open]');
    if (opener) {
      e.preventDefault();
      open(opener.getAttribute('data-open'), opener);
      return;
    }
    var closer = e.target.closest('[data-close]');
    if (closer) {
      e.preventDefault();
      closeAll();
      return;
    }
    if (e.target === backdrop) closeAll();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeAll();
  });

  document.addEventListener('click', function (e) {
    var homeLink = e.target.closest('[data-go-home]');
    if (homeLink && window.location.pathname.replace(/\/$/, '') === '') {
      e.preventDefault();
      closeAll();
      if (scroller) scroller.scrollTo({ top: 0, behavior: 'smooth' });
    } else if (homeLink) {
      closeAll();
    }
  });

  syncNavActive(null);

  /* ---------------- theme (light/dark) toggle ---------------- */
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-theme-toggle]');
    if (!t) return;
    var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    if (isDark) {
      document.documentElement.removeAttribute('data-theme');
      try { localStorage.setItem('privat-theme', 'light'); } catch (err) {}
    } else {
      document.documentElement.setAttribute('data-theme', 'dark');
      try { localStorage.setItem('privat-theme', 'dark'); } catch (err) {}
    }
  });

  /* ---------------- toast ---------------- */
  function toast(msg) {
    if (!toastEl) return;
    clearTimeout(toastTimer);
    toastEl.textContent = msg;
    toastEl.classList.add('is-open');
    toastTimer = setTimeout(function () { toastEl.classList.remove('is-open'); }, 1800);
  }

  /* ---------------- scroll reveal + hero parallax ---------------- */
  function setupReveals() {
    if (!scroller) return;
    var els = scroller.querySelectorAll('[data-reveal]');
    if (!els.length) return;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          io.unobserve(entry.target);
        }
      });
    }, { root: scroller, threshold: 0.12 });
    els.forEach(function (el) {
      var r = el.getBoundingClientRect();
      var inView = r.top < scroller.clientHeight * 0.9;
      el.classList.add('privat-reveal');
      if (!inView) io.observe(el); else el.classList.add('is-visible');
    });
  }

  function setupParallax() {
    if (!scroller) return;
    var heroImg = document.getElementById('privat-hero-img');
    var heroTag = document.getElementById('privat-hero-tag');
    if (!heroImg && !heroTag) return;
    scroller.addEventListener('scroll', function () {
      var y = scroller.scrollTop;
      if (heroImg) heroImg.style.transform = 'translateY(' + (y * 0.3) + 'px)';
      if (heroTag) {
        heroTag.style.opacity = String(Math.max(0, 1 - y / 340));
        heroTag.style.transform = 'translateY(' + (y * 0.12) + 'px)';
      }
    }, { passive: true });
  }

  /* ---------------- cart (Shopify Ajax API) ---------------- */
  var moneyFormat = (window.Shopify && Shopify.money_format) || '{{amount}}';
  function formatMoney(cents) {
    var m = moneyFormat.match(/\{\{\s*(\w+)\s*\}\}/);
    var token = m ? m[1] : 'amount';
    var noDecimals = token.indexOf('no_decimals') > -1;
    var comma = token.indexOf('comma_separator') > -1;
    var thousands = comma ? '.' : ' ';
    var decimal = comma ? ',' : '.';
    var num = cents / 100;
    var parts = (noDecimals ? String(Math.round(num)) : num.toFixed(2)).split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, thousands);
    var value = parts.join(decimal);
    if (!noDecimals) value = value.replace(decimal + '00', '');
    return moneyFormat.replace(/\{\{\s*\w+\s*\}\}/, value);
  }

  var lastCartCount = null;
  /* уменьшенное превью для Ajax-картинок корзины (полноразмер грузится долго) */
  function thumbUrl(u) {
    if (!u) return u;
    return u + (u.indexOf('?') > -1 ? '&' : '?') + 'width=240';
  }

  function cartBadge(count) {
    var badge = document.getElementById('privat-cart-badge');
    if (badge) {
      badge.textContent = String(count);
      badge.hidden = count <= 0;
      if (lastCartCount !== null && count > lastCartCount) {
        badge.style.animation = 'none';
        void badge.offsetWidth;
        badge.style.animation = 'dcBadge .4s ease';
      }
    }
    lastCartCount = count;
    var menuCount = document.getElementById('privat-menu-cart-count');
    if (menuCount) menuCount.textContent = String(count);
  }

  /* ---------------- заявка + gclid (атрибуция Google Ads) ---------------- */
  function storeGclid() {
    try {
      var m = location.search.match(/[?&]gclid=([^&]+)/);
      if (m) localStorage.setItem('privat-gclid', JSON.stringify({ v: decodeURIComponent(m[1]), t: Date.now() }));
    } catch (e) {}
  }
  function getGclid() {
    try {
      var s = JSON.parse(localStorage.getItem('privat-gclid') || 'null');
      if (s && s.v && (Date.now() - s.t) < 90 * 24 * 3600 * 1000) return s.v;
    } catch (e) {}
    return '';
  }
  function newOrderCode() {
    return String(Date.now()).slice(-6);
  }
  /* формат сообщения заказа: портал продавца детектит «заявка XXXXXX» */
  function buildWaOrderMsg(code, items, total) {
    var lines = ['Здравствуйте! Я хочу оформить заказ (заявка ' + code + '):', ''];
    items.forEach(function (it, n) {
      lines.push((n + 1) + ') ' + it.title + (it.sku ? ' (код ' + it.sku + ')' : '') + ' х ' + it.qty + ' = ' + formatMoney(it.sum));
    });
    lines.push('', 'Общая сумма: ' + formatMoney(total));
    return lines.join('\n');
  }
  function trackWaOrder(code, total) {
    try {
      var log = JSON.parse(localStorage.getItem('privat-wa-orders') || '[]');
      log.push({ code: code, gclid: getGclid(), total: total, ts: new Date().toISOString() });
      localStorage.setItem('privat-wa-orders', JSON.stringify(log.slice(-50)));
    } catch (e) {}
    /* маячок на портал продавца: связка «код заявки ↔ gclid» для офлайн-конверсий.
       text/plain — простой запрос без CORS-preflight, ответ не важен */
    try {
      var portal = window.__privatPortal;
      if (portal && getGclid()) {
        var payload = JSON.stringify({ code: code, gclid: getGclid(), total: total,
          currency: (window.Shopify && Shopify.currency && Shopify.currency.active) || 'KGS' });
        var url = portal.replace(/\/$/, '') + '/api/ref';
        if (navigator.sendBeacon) navigator.sendBeacon(url, new Blob([payload], { type: 'text/plain' }));
        else fetch(url, { method: 'POST', body: payload, keepalive: true, headers: { 'Content-Type': 'text/plain' } });
      }
    } catch (e) {}
    try {
      window.dataLayer = window.dataLayer || [];
      window.dataLayer.push({
        event: 'wa_order_click',
        order_code: code,
        value: total / 100,
        currency: (window.Shopify && Shopify.currency && Shopify.currency.active) || 'KGS',
        gclid: getGclid()
      });
    } catch (e) {}
  }
  document.addEventListener('click', function (e) {
    var a = e.target.closest('[data-wa-checkout],[data-wa-buy]');
    if (!a) return;
    var code = a.getAttribute('data-order-code');
    if (code) trackWaOrder(code, parseInt(a.getAttribute('data-order-total') || '0', 10));
  });

  function syncWaCheckout(cart) {
    var btn = document.getElementById('privat-cart-checkout');
    if (!btn || !btn.hasAttribute('data-wa-checkout')) return;
    var code = newOrderCode();
    var items = cart.items.map(function (i) {
      return { title: i.product_title, sku: i.sku, qty: i.quantity, sum: (i.final_line_price != null ? i.final_line_price : i.price * i.quantity) };
    });
    btn.href = 'https://wa.me/' + btn.getAttribute('data-wa-phone') + '?text=' + encodeURIComponent(buildWaOrderMsg(code, items, cart.total_price));
    btn.setAttribute('data-order-code', code);
    btn.setAttribute('data-order-total', String(cart.total_price));
  }

  function renderCart(cartData) {
    var body = document.getElementById('privat-cart-body');
    var empty = document.getElementById('privat-cart-empty');
    var summary = document.getElementById('privat-cart-summary');
    var totalEl = document.getElementById('privat-cart-total');
    if (!body) return;

    function paint(cart) {
      cartBadge(cart.item_count);
      syncWaCheckout(cart);
      if (!cart.items.length) {
        body.innerHTML = '';
        body.style.display = 'none';
        if (summary) summary.style.display = 'none';
        if (empty) empty.style.display = 'flex';
        return;
      }
      if (empty) empty.style.display = 'none';
      body.style.display = 'flex';
      if (summary) summary.style.display = 'flex';
      body.innerHTML = cart.items.map(function (item) {
        var img = item.image ? 'background-image:url(' + thumbUrl(item.image) + ')' : '';
        return '' +
          '<div class="privat-line-item" data-line-key="' + item.key + '">' +
            '<div class="privat-line-item__thumb" style="' + img + '"></div>' +
            '<div class="privat-line-item__body">' +
              '<div class="privat-line-item__name privat-fav-row__name">' + item.product_title + '</div>' +
              (item.sku ? '<div class="privat-line-item__code">Код: ' + item.sku + '</div>' : '') +
              '<div class="privat-line-item__price">' + formatMoney(item.line_price) + '</div>' +
              '<div class="privat-line-item__qty">' +
                '<button class="privat-qty-btn" data-cart-dec="' + item.key + '" aria-label="Меньше">−</button>' +
                '<span class="privat-qty-val">' + item.quantity + '</span>' +
                '<button class="privat-qty-btn" data-cart-inc="' + item.key + '" aria-label="Больше">+</button>' +
                '<button class="privat-line-item__remove" data-cart-remove="' + item.key + '">убрать</button>' +
              '</div>' +
            '</div>' +
          '</div>';
      }).join('');
      if (totalEl) totalEl.textContent = formatMoney(cart.total_price);
    }

    if (cartData) { paint(cartData); return; }
    fetch('/cart.js').then(function (r) { return r.json(); }).then(paint);
  }

  document.addEventListener('click', function (e) {
    var add = e.target.closest('[data-add-to-cart]');
    if (add) {
      e.preventDefault();
      var id = add.getAttribute('data-variant-id');
      if (!id) return;
      add.disabled = true;
      fetch('/cart/add.js', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ id: id, quantity: 1 })
      }).then(function (r) { return r.json(); }).then(function () {
        toast('Добавлено в корзину');
        return fetch('/cart.js');
      }).then(function (r) { return r.json(); }).then(function (cart) {
        renderCart(cart);
      }).finally(function () { add.disabled = false; });
      return;
    }

    var inc = e.target.closest('[data-cart-inc]');
    var dec = e.target.closest('[data-cart-dec]');
    var rem = e.target.closest('[data-cart-remove]');
    if (inc || dec || rem) {
      e.preventDefault();
      var key = (inc || dec || rem).getAttribute(inc ? 'data-cart-inc' : dec ? 'data-cart-dec' : 'data-cart-remove');
      fetch('/cart.js').then(function (r) { return r.json(); }).then(function (cart) {
        var line = cart.items.find(function (i) { return i.key === key; });
        var qty = rem ? 0 : (line ? line.quantity + (inc ? 1 : -1) : 0);
        return fetch('/cart/change.js', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({ id: key, quantity: Math.max(0, qty) })
        });
      }).then(function (r) { return r.json(); }).then(function (cart) {
        renderCart(cart);
      });
    }
  });

  /* ---------------- favorites (localStorage) ---------------- */
  var FAV_KEY = 'privat-favorites';
  function getFavs() {
    try { return JSON.parse(localStorage.getItem(FAV_KEY) || '{}'); } catch (e) { return {}; }
  }
  function setFavs(favs) {
    try { localStorage.setItem(FAV_KEY, JSON.stringify(favs)); } catch (e) {}
  }
  function favCount() { return Object.keys(getFavs()).length; }

  function syncFavButtons() {
    var favs = getFavs();
    document.querySelectorAll('[data-fav-toggle]').forEach(function (btn) {
      var id = btn.getAttribute('data-product-id');
      btn.classList.toggle('is-active', !!favs[id]);
    });
    var badge = document.getElementById('privat-favs-badge');
    if (badge) {
      var c = favCount();
      badge.textContent = String(c);
      badge.hidden = c <= 0;
    }
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-fav-toggle]');
    if (!btn) return;
    e.preventDefault();
    var id = btn.getAttribute('data-product-id');
    var favs = getFavs();
    if (favs[id]) {
      delete favs[id];
    } else {
      favs[id] = {
        title: btn.getAttribute('data-product-title') || '',
        price: btn.getAttribute('data-product-price') || '',
        image: btn.getAttribute('data-product-image') || '',
        url: btn.getAttribute('data-product-url') || '#',
        sku: btn.getAttribute('data-product-sku') || '',
        variantId: btn.getAttribute('data-variant-id') || ''
      };
    }
    setFavs(favs);
    syncFavButtons();
    if (document.querySelector('[data-drawer="favs"]').classList.contains('is-open')) renderFavorites();
  });

  /* старые записи избранного не содержат SKU — дотягиваем его по Ajax один раз */
  function enrichFavSkus() {
    var favs = getFavs();
    var pending = Object.keys(favs).filter(function (id) {
      return !favs[id].sku && !favs[id].skuChecked && favs[id].url;
    });
    if (!pending.length) return;
    Promise.all(pending.map(function (id) {
      var m = (favs[id].url || '').match(/\/products\/([^\/?#]+)/);
      favs[id].skuChecked = true;
      if (!m) return null;
      return fetch('/products/' + m[1] + '.js')
        .then(function (r) { return r.json(); })
        .then(function (p) {
          var v = (p.variants || []).find(function (v) { return String(v.id) === String(favs[id].variantId); }) || (p.variants || [])[0];
          if (v && v.sku) favs[id].sku = v.sku;
        }).catch(function () {});
    })).then(function () {
      setFavs(favs);
      renderFavorites(true);
    });
  }

  function renderFavorites(skipEnrich) {
    var body = document.getElementById('privat-favs-body');
    var empty = document.getElementById('privat-favs-empty');
    if (!body) return;
    if (!skipEnrich) enrichFavSkus();
    var favs = getFavs();
    var ids = Object.keys(favs);
    if (!ids.length) {
      body.innerHTML = '';
      if (empty) empty.style.display = 'flex';
      return;
    }
    if (empty) empty.style.display = 'none';
    body.innerHTML = ids.map(function (id) {
      var f = favs[id];
      var img = f.image ? 'background-image:url(' + f.image + ')' : '';
      return '' +
        '<div class="privat-line-item privat-line-item--fav">' +
          '<a href="' + f.url + '" class="privat-line-item__thumb" style="' + img + '"></a>' +
          '<div class="privat-line-item__body">' +
            '<a href="' + f.url + '" class="privat-line-item__name privat-fav-row__name" style="color:inherit;text-decoration:none">' + f.title + '</a>' +
            (f.sku ? '<div class="privat-line-item__code">Код: ' + f.sku + '</div>' : '') +
            '<div class="privat-line-item__price">' + f.price + '</div>' +
            '<div class="privat-line-item__qty">' +
              (f.variantId ? '<button class="privat-fav-row__add" data-add-to-cart data-variant-id="' + f.variantId + '">В корзину</button>' : '') +
            '</div>' +
          '</div>' +
          '<button class="privat-fav-row__heart is-active" data-fav-toggle data-product-id="' + id + '" data-product-title="' + f.title + '" data-product-price="' + f.price + '" data-product-image="' + f.image + '" data-product-url="' + f.url + '" data-product-sku="' + (f.sku || '') + '" data-variant-id="' + f.variantId + '" aria-label="Убрать из избранного">' +
            '<svg width="18" height="18" viewBox="0 0 22 22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M11 18.6C6.7 15.3 3.8 12.6 3.8 9.6c0-2.2 1.7-3.9 3.9-3.9 1.3 0 2.5.6 3.3 1.7.8-1.1 2-1.7 3.3-1.7 2.2 0 3.9 1.7 3.9 3.9 0 3-2.9 5.7-7.2 9Z"/></svg>' +
          '</button>' +
        '</div>';
    }).join('');
  }

  /* ---------------- account: switch login <-> register views ---------------- */
  document.addEventListener('click', function (e) {
    var sw = e.target.closest('[data-acc-show]');
    if (!sw) return;
    var drawer = document.querySelector('[data-drawer="acc"]');
    if (!drawer) return;
    e.preventDefault();
    var name = sw.getAttribute('data-acc-show');
    drawer.querySelectorAll('[data-acc-view]').forEach(function (v) {
      v.style.display = v.getAttribute('data-acc-view') === name ? '' : 'none';
    });
    var title = drawer.querySelector('.privat-sheet__title');
    if (title) title.textContent = name === 'register' ? 'Регистрация' : 'Вход';
  });

  /* ---------------- search (predictive) ---------------- */
  document.addEventListener('click', function (e) {
    var fill = e.target.closest('[data-search-fill]');
    if (!fill) return;
    var input = document.getElementById('privat-search-input');
    if (!input) return;
    input.value = fill.getAttribute('data-search-fill');
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.focus({ preventScroll: true });
  });

  var searchTimer = null;
  document.addEventListener('input', function (e) {
    if (e.target.id !== 'privat-search-input') return;
    var q = e.target.value.trim();
    var idle = document.getElementById('privat-search-idle');
    var results = document.getElementById('privat-search-results');
    if (!results) return;
    clearTimeout(searchTimer);
    if (!q) {
      results.innerHTML = '';
      if (idle) idle.style.display = 'block';
      return;
    }
    if (idle) idle.style.display = 'none';
    searchTimer = setTimeout(function () {
      /* unavailable_products=show — иначе Shopify прячет товары, лежащие только на «Складе»:
         эта локация не выполняет онлайн-заказы, поэтому они считаются недоступными.
         Каталог их показывает, и поиск должен вести себя так же — товар есть, просто не в зале. */
      fetch('/search/suggest.json?q=' + encodeURIComponent(q) + '&resources[type]=product&resources[limit]=10&resources[options][unavailable_products]=show&resources[options][fields]=title,product_type,tag,variants.sku')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var products = (data.resources && data.resources.results && data.resources.results.products) || [];
          results.innerHTML = products.map(function (p) {
            var imgUrl = p.featured_image ? (p.featured_image.url || p.featured_image) : (p.image || '');
            var img = imgUrl ? 'background-image:url(' + imgUrl + ')' : '';
            var variantId = p.variant_id || (p.variants && p.variants[0] && p.variants[0].id) || '';
            // у товара с вариантами класть в корзину наугад нельзя — ведём выбирать
            var many = p.variants && p.variants.length > 1;
            return '' +
              '<div class="privat-search__row">' +
                '<a href="' + p.url + '" class="privat-line-item__thumb" style="width:46px;height:46px;min-height:46px;' + img + '"></a>' +
                '<div class="privat-search__row-body">' +
                  '<a href="' + p.url + '" class="privat-search__row-name" style="color:inherit;text-decoration:none">' + p.title + '</a>' +
                  '<div class="privat-search__row-price">' + p.price + '</div>' +
                '</div>' +
                (many
                  ? '<a class="privat-search__row-add" href="' + p.url + '">Выбрать</a>'
                  : (variantId ? '<button class="privat-search__row-add" data-add-to-cart data-variant-id="' + variantId + '">В корзину</button>' : '')) +
              '</div>';
          }).join('') || '<div class="privat-search__idle">Ничего не найдено</div>';
        });
    }, 220);
  });

  /* ---------------- product page ---------------- */
  (function () {
    var jsonEl = document.getElementById('privat-pp-json');
    if (!jsonEl) return;
    var product;
    try { product = JSON.parse(jsonEl.textContent); } catch (e) { return; }
    if (!product || !product.variants || !product.variants.length) return;

    var qtyEl = document.getElementById('privat-pp-qty');
    var addBtn = document.getElementById('privat-pp-add');
    var swatches = [].slice.call(document.querySelectorAll('[data-opt-value]'));
    var labels = [].slice.call(document.querySelectorAll('[data-opt-label]'));
    var qty = 1;
    var curId = addBtn ? addBtn.getAttribute('data-variant-id') : '';

    function variantById(id) {
      for (var i = 0; i < product.variants.length; i++) {
        if (String(product.variants[i].id) === String(id)) return product.variants[i];
      }
      return null;
    }
    function currentVariant() {
      return variantById(curId) || product.variants[0];
    }

    /* Клик по плитке меняет один параметр, остальные оставляем как есть. Если
       такой комбинации нет (у товара с двумя параметрами не все пары существуют) —
       берём любой вариант с выбранным значением, лучше доступный. */
    function pickVariant(oi, val) {
      var want = (currentVariant().options || []).slice();
      want[oi] = val;
      var exact = null, loose = null;
      for (var i = 0; i < product.variants.length; i++) {
        var v = product.variants[i];
        if (v.options[oi] !== val) continue;
        if (!loose || (!loose.available && v.available)) loose = v;
        var same = true;
        for (var k = 0; k < want.length; k++) {
          if (v.options[k] !== want[k]) { same = false; break; }
        }
        if (same) exact = v;
      }
      return exact || loose;
    }

    function paintSwatches(v) {
      swatches.forEach(function (sw) {
        var on = v.options[+sw.getAttribute('data-opt-index')] === sw.getAttribute('data-value');
        sw.classList.toggle('is-active', on);
        sw.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      labels.forEach(function (el) {
        el.textContent = v.options[+el.getAttribute('data-opt-label')] || '';
      });
    }

    /* галерея живёт в своём модуле ниже — просим её показать фото варианта */
    function showVariantPhoto(v, instant) {
      document.dispatchEvent(new CustomEvent('privat:variant', { detail: { id: v.id, instant: instant } }));
    }

    /* ...и наоборот: пролистали фото до другого цвета — выбор едет за ним, иначе
       покупатель смотрит на зелёную и кладёт в корзину синюю */
    document.addEventListener('privat:frame', function (e) {
      var ids = (e.detail && e.detail.ids) || [];
      if (ids.indexOf(String(curId)) >= 0) return;
      var v = variantById(ids[0]);
      if (!v) return;
      curId = String(v.id);
      sync();
    });

    function sync() {
      var v = currentVariant();
      if (qtyEl) qtyEl.textContent = String(qty);
      var priceEl = document.getElementById('privat-pp-price');
      var oldEl = document.getElementById('privat-pp-old');
      var skuEl = document.getElementById('privat-pp-sku');
      var stockEl = document.getElementById('privat-pp-stock');
      var badgeEl = document.getElementById('privat-pp-badge');
      var totalEl = document.getElementById('privat-pp-total');
      var buyNow = document.getElementById('privat-pp-buynow');
      var onSale = v.compare_at_price && v.compare_at_price > v.price;
      if (priceEl) priceEl.textContent = formatMoney(v.price);
      if (oldEl) {
        oldEl.textContent = onSale ? formatMoney(v.compare_at_price) : '';
        oldEl.hidden = !onSale;
      }
      if (badgeEl) {
        badgeEl.hidden = !onSale;
        if (onSale) badgeEl.textContent = '−' + Math.round((1 - v.price / v.compare_at_price) * 100) + '%';
      }
      if (skuEl && v.sku) skuEl.textContent = v.sku;
      if (stockEl) stockEl.textContent = v.available ? 'В наличии' : 'Нет в наличии';
      if (addBtn) {
        addBtn.disabled = !v.available;
        addBtn.setAttribute('data-variant-id', String(v.id));
        var addLabel = addBtn.querySelector('[data-add-label]');
        if (addLabel) addLabel.textContent = v.available ? 'В корзину' : 'Нет в наличии';
      }
      paintSwatches(v);
      // сердечко на фото запоминает именно выбранный вариант
      var fav = document.querySelector('.privat-pp__photo [data-fav-toggle]');
      if (fav) {
        fav.setAttribute('data-variant-id', String(v.id));
        fav.setAttribute('data-product-price', formatMoney(v.price));
        fav.setAttribute('data-product-sku', v.sku || '');
      }
      if (totalEl) totalEl.textContent = formatMoney(v.price * qty);
      if (buyNow) {
        var orderCode = newOrderCode();
        var itemTitle = buyNow.getAttribute('data-product-title') +
          (product.variants.length > 1 ? ', ' + v.title : '');
        var itemSum = v.price * qty;
        buyNow.href = 'https://wa.me/' + buyNow.getAttribute('data-wa-phone') + '?text=' +
          encodeURIComponent(buildWaOrderMsg(orderCode, [{ title: itemTitle, sku: v.sku, qty: qty, sum: itemSum }], itemSum));
        buyNow.setAttribute('data-order-code', orderCode);
        buyNow.setAttribute('data-order-total', String(itemSum));
      }
    }

    function flyToCart() {
      var photo = document.getElementById('privat-pp-photo');
      var cart = document.querySelector('.privat-header [data-open="cart"]');
      if (!photo || !cart || !app) return;
      var dot = document.createElement('div');
      if (!dot.animate) return;
      var size = 64;
      var pr = photo.getBoundingClientRect(), cr = cart.getBoundingClientRect(), rr = app.getBoundingClientRect();
      var startX = pr.left + pr.width / 2 - rr.left - size / 2;
      var startY = pr.top + pr.height / 2 - rr.top - size / 2;
      var endX = cr.left + cr.width / 2 - rr.left - size / 2;
      var endY = cr.top + cr.height / 2 - rr.top - size / 2;
      dot.className = 'privat-fly-dot';
      dot.style.width = size + 'px';
      dot.style.height = size + 'px';
      dot.style.left = startX + 'px';
      dot.style.top = startY + 'px';
      var photoImg = visibleGalImg() || document.getElementById('privat-pp-photo-img');
      if (photoImg && photoImg.src) dot.style.backgroundImage = 'url(' + photoImg.src + ')';
      var bgColor = photo.getAttribute('data-photo-bg');
      if (bgColor) dot.style.backgroundColor = bgColor;
      app.appendChild(dot);
      var anim = dot.animate([
        { transform: 'translate(0,0) scale(1)', opacity: 1 },
        { transform: 'translate(' + (endX - startX) * 0.55 + 'px,' + ((endY - startY) - 90) + 'px) scale(.55)', opacity: 0.95, offset: 0.6 },
        { transform: 'translate(' + (endX - startX) + 'px,' + (endY - startY) + 'px) scale(.15)', opacity: 0.4 }
      ], { duration: 650, easing: 'cubic-bezier(.3,.7,.4,1)' });
      anim.onfinish = function () { dot.remove(); };
    }

    document.addEventListener('click', function (e) {
      if (e.target.closest('[data-pp-qty-inc]')) { qty = Math.min(99, qty + 1); sync(); return; }
      if (e.target.closest('[data-pp-qty-dec]')) { qty = Math.max(1, qty - 1); sync(); return; }
      var sw = e.target.closest('[data-opt-value]');
      if (sw) {
        var v = pickVariant(+sw.getAttribute('data-opt-index'), sw.getAttribute('data-value'));
        if (!v) return;
        curId = String(v.id);
        sync();
        showVariantPhoto(v);
      }
    });

    if (addBtn) addBtn.addEventListener('click', function () {
      var v = currentVariant();
      if (!v || !v.available) return;
      addBtn.disabled = true;
      fetch('/cart/add.js', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ id: v.id, quantity: qty })
      }).then(function (r) { return r.json(); }).then(function () {
        flyToCart();
        toast('Добавлено: ' + product.title);
        return fetch('/cart.js');
      }).then(function (r) { return r.json(); }).then(function (cart) {
        renderCart(cart);
      }).finally(function () { addBtn.disabled = !currentVariant().available; });
    });

    sync();
    // сразу открываемся на фото выбранного варианта: если первый цвет распродан,
    // Shopify выберет следующий, а галерея всё равно начнётся с первого кадра.
    // Ждём тика — галерея подписывается на событие ниже по файлу.
    setTimeout(function () { showVariantPhoto(currentVariant(), true); }, 0);
  })();

  /* ---------------- галерея товара: стрелки + свайп ----------------
     Свайп достаётся бесплатно: кадры лежат в горизонтальном скроллере
     со снапом, палец листает их родным скроллом с инерцией. Стрелки и
     миниатюры просто прокручивают этот же скроллер на нужный кадр. */
  function galTrack() { return document.querySelector('[data-gal-track]'); }

  /* Плавная прокрутка по горизонтали с подстраховкой: там, где плавный режим
     не работает (headless-браузеры, старые движки), кадр всё равно встаёт на
     место — иначе стрелка выглядела бы сломанной. */
  function scrollX(el, left) {
    var from = el.scrollLeft;
    if (left === from) return;
    if (el.scrollTo) el.scrollTo({ left: left, behavior: 'smooth' });
    else el.scrollLeft = left;
    setTimeout(function () { if (el.scrollLeft === from) el.scrollLeft = left; }, 120);
  }

  /* фото, которое сейчас на экране (для полёта в корзину) */
  function visibleGalImg() {
    var gal = galTrack();
    if (!gal || !gal.clientWidth) return null;
    var imgs = gal.querySelectorAll('.privat-pp__media');
    return imgs[Math.round(gal.scrollLeft / gal.clientWidth)] || imgs[0] || null;
  }

  (function () {
    var gal = galTrack();
    if (!gal) return;
    var slides = gal.querySelectorAll('.privat-gal__slide');
    if (slides.length < 2) return;
    var prev = document.querySelector('[data-gal-prev]');
    var next = document.querySelector('[data-gal-next]');
    var thumbs = [].slice.call(document.querySelectorAll('[data-thumb]'));
    var cur = 0;

    function index() {
      return gal.clientWidth ? Math.round(gal.scrollLeft / gal.clientWidth) : cur;
    }
    /* состояние стрелок и миниатюр — отдельно от скролла: после свайпа его
       приносит событие scroll, после клика мы знаем кадр заранее */
    function showFrame(i) {
      cur = i;
      if (prev) prev.disabled = i <= 0;
      if (next) next.disabled = i >= slides.length - 1;
      thumbs.forEach(function (t, n) { t.classList.toggle('is-active', n === i); });
      var active = thumbs[i];
      var box = active && active.parentNode;
      // миниатюру подтягиваем руками (scrollIntoView увёл бы всю страницу) и
      // только если она вышла за край — иначе ряд дёргается на ровном месте
      if (box && box.clientWidth > active.offsetWidth) {
        var left = active.offsetLeft - box.scrollLeft;
        if (left < 0 || left + active.offsetWidth > box.clientWidth) {
          scrollX(box, Math.max(0, active.offsetLeft - (box.clientWidth - active.offsetWidth) / 2));
        }
      }
    }
    /* какие варианты живут на этом кадре — чтобы выбор ехал за фото */
    function emitFrame(i) {
      var ids = (slides[i].getAttribute('data-variant-ids') || '').split(',').filter(Boolean);
      if (ids.length) document.dispatchEvent(new CustomEvent('privat:frame', { detail: { ids: ids } }));
    }
    function go(i, silent) {
      i = Math.max(0, Math.min(slides.length - 1, i));
      showFrame(i);
      scrollX(gal, i * gal.clientWidth);
      if (!silent) emitFrame(i);
    }
    /* поставить кадр без анимации (открытие страницы). На первом тике ширина
       кадра ещё может быть нулевой — тогда повторяем, пока разложится. */
    function placeFrame(i) {
      showFrame(i);
      var put = function () {
        if (!gal.clientWidth) return false;
        gal.scrollLeft = i * gal.clientWidth;
        return true;
      };
      if (put()) return;
      var tries = 0;
      var again = function () { if (!put() && ++tries < 30) requestAnimationFrame(again); };
      requestAnimationFrame(again);
      window.addEventListener('load', put, { once: true });
    }

    if (prev) prev.addEventListener('click', function () { go(cur - 1); });
    if (next) next.addEventListener('click', function () { go(cur + 1); });
    document.addEventListener('click', function (e) {
      var t = e.target.closest('[data-thumb]');
      if (!t) return;
      var i = thumbs.indexOf(t);
      if (i >= 0) go(i);
    });

    var ticking = false;
    gal.addEventListener('scroll', function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () { ticking = false; showFrame(index()); emitFrame(index()); });
    }, { passive: true });
    // поворот экрана меняет ширину кадра — возвращаем текущее фото на место
    window.addEventListener('resize', function () { gal.scrollLeft = cur * gal.clientWidth; }, { passive: true });

    /* выбрали цвет — листаем на фото этого варианта (у слайда есть data-variant-ids).
       silent: обратно событие не шлём, чтобы не гонять выбор по кругу */
    document.addEventListener('privat:variant', function (e) {
      var id = String((e.detail && e.detail.id) || '');
      var own = -1, general = -1;
      for (var i = 0; i < slides.length; i++) {
        var ids = slides[i].getAttribute('data-variant-ids') || '';
        if (own < 0 && ids.split(',').indexOf(id) >= 0) own = i;
        if (general < 0 && !ids) general = i;
      }
      // У цвета может не быть своего фото (в Odoo не сняли) — тогда общее.
      // Без этого выбор «назад» на такой цвет оставлял фото соседнего.
      var to = own >= 0 ? own : general;
      if (to < 0) return;
      if (e.detail.instant) placeFrame(to);
      else go(to, true);
    });
    showFrame(0);
  })();

  /* ---------------- ленты со стрелками (категории) ---------------- */
  (function () {
    function setup(rail) {
      var strip = rail.querySelector('[data-rail-track]');
      var prev = rail.querySelector('[data-rail-prev]');
      var next = rail.querySelector('[data-rail-next]');
      if (!strip || !prev || !next) return;

      function step() { return Math.max(140, Math.round(strip.clientWidth * 0.8)); }
      function by(delta) {
        var max = strip.scrollWidth - strip.clientWidth;
        scrollX(strip, Math.max(0, Math.min(max, strip.scrollLeft + delta)));
        setTimeout(sync, 400);
      }
      // стрелку прячем там, где листать уже некуда (и обе — если лента влезла целиком)
      function sync() {
        var max = strip.scrollWidth - strip.clientWidth;
        prev.hidden = strip.scrollLeft <= 4;
        next.hidden = strip.scrollLeft >= max - 4;
      }

      prev.addEventListener('click', function () { by(-step()); });
      next.addEventListener('click', function () { by(step()); });
      var ticking = false;
      strip.addEventListener('scroll', function () {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(function () { ticking = false; sync(); });
      }, { passive: true });
      window.addEventListener('resize', sync, { passive: true });
      sync();
    }
    document.querySelectorAll('[data-rail]').forEach(setup);
  })();

  /* ---------------- collection: автоподгрузка при скролле ---------------- */
  (function () {
    var loading = false;

    function doLoadMore(btn, onDone) {
      var url = btn && btn.getAttribute('data-next-url');
      if (!url || loading) { if (onDone) onDone(); return; }
      loading = true;
      var wrap = document.getElementById('privat-loadmore');
      var spin = wrap && wrap.querySelector('.privat-loadmore__spin');
      if (spin) spin.hidden = false;
      if (btn.disabled !== undefined) btn.disabled = true;
      fetch(url).then(function (r) { return r.text(); }).then(function (html) {
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var grid = document.getElementById('privat-coll-grid');
        var newGrid = doc.getElementById('privat-coll-grid');
        if (grid && newGrid) {
          while (newGrid.firstElementChild) grid.appendChild(newGrid.firstElementChild);
        }
        var shownEl = document.querySelector('[data-shown-count]');
        if (shownEl && grid) shownEl.textContent = String(grid.querySelectorAll('.privat-card').length);
        var nextBtn = doc.querySelector('[data-load-more]');
        if (nextBtn && nextBtn.getAttribute('data-next-url')) {
          btn.setAttribute('data-next-url', nextBtn.getAttribute('data-next-url'));
          if (btn.disabled !== undefined) btn.disabled = false;
        } else if (wrap) {
          wrap.remove();           // страниц больше нет
        }
        syncFavButtons();
        loading = false;
        if (spin) spin.hidden = true;
        if (onDone) onDone();
      }).catch(function () {
        loading = false;
        if (spin) spin.hidden = true;
        if (btn.disabled !== undefined) btn.disabled = false;
        if (onDone) onDone();
      });
    }

    // Фолбэк: ручной клик (если IntersectionObserver недоступен — кнопка видна)
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-load-more]');
      if (!btn) return;
      e.preventDefault();
      doLoadMore(btn);
    });

    // Автоподгрузка: как только «хвост» списка подходит к экрану — тянем следующую страницу
    function nearViewport(el, margin) {
      var r = el.getBoundingClientRect();
      var vh = window.innerHeight || document.documentElement.clientHeight;
      return r.top <= vh + margin && r.bottom >= -margin;
    }
    function checkAndLoad() {
      var wrap = document.getElementById('privat-loadmore');
      if (!wrap || loading) return;
      var btn = wrap.querySelector('[data-load-more]');
      if (!btn || !btn.getAttribute('data-next-url')) return;
      if (!nearViewport(wrap, 600)) return;
      doLoadMore(btn, checkAndLoad);   // после подгрузки проверяем снова — цепочка для коротких страниц
    }
    function initAuto() {
      var wrap = document.getElementById('privat-loadmore');
      if (!wrap) return;
      wrap.classList.add('is-auto');   // авто-режим: прячем кнопку (CSS), спиннер при загрузке
      // Основной механизм — IntersectionObserver
      if ('IntersectionObserver' in window) {
        var io = new IntersectionObserver(function (entries) {
          for (var i = 0; i < entries.length; i++) if (entries[i].isIntersecting) { checkAndLoad(); break; }
        }, { rootMargin: '600px 0px' });
        io.observe(wrap);
      }
      // Подстраховка обычным скроллом (тема скроллит внутри #privat-scroller;
      // capture ловит scroll с любого контейнера, даже если IO не сработал)
      var ticking = false;
      function onScroll() {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(function () { ticking = false; checkAndLoad(); });
      }
      document.addEventListener('scroll', onScroll, { passive: true, capture: true });
      window.addEventListener('resize', onScroll, { passive: true });
      checkAndLoad();  // короткая первая страница — сразу дотягиваем
    }
    if (document.readyState !== 'loading') initAuto();
    else document.addEventListener('DOMContentLoaded', initAuto);
  })();

  /* ---------------- init ---------------- */
  document.addEventListener('DOMContentLoaded', function () {
    storeGclid();
    setupReveals();
    setupParallax();
    syncFavButtons();
    var cartDataEl = document.getElementById('privat-cart-data');
    if (cartDataEl) {
      try { cartBadge(JSON.parse(cartDataEl.textContent).item_count); } catch (e) {}
    }
  });
})();

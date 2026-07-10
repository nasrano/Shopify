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

  function closeAll() {
    drawers().forEach(function (d) { d.classList.remove('is-open'); });
    backdrop.classList.remove('is-open');
    if (scroller) scroller.classList.remove('no-scroll');
    syncNavActive(null);
  }

  function open(name) {
    drawers().forEach(function (d) {
      d.classList.toggle('is-open', d.getAttribute('data-drawer') === name);
    });
    backdrop.classList.add('is-open');
    if (scroller) scroller.classList.add('no-scroll');
    syncNavActive(name);
    if (name === 'search') {
      var input = document.getElementById('privat-search-input');
      if (input) setTimeout(function () { input.focus({ preventScroll: true }); }, 50);
    }
    if (name === 'cart') renderCart();
    if (name === 'favs') renderFavorites();
  }

  function syncNavActive(overlayName) {
    app.querySelectorAll('.privat-nav__btn').forEach(function (b) {
      var target = b.getAttribute('data-nav-active-for');
      b.classList.toggle('is-active', target === overlayName || (overlayName === null && target === 'home'));
    });
  }

  document.addEventListener('click', function (e) {
    var opener = e.target.closest('[data-open]');
    if (opener) {
      e.preventDefault();
      open(opener.getAttribute('data-open'));
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
    var value = (cents / 100).toFixed(2).replace('.00', '');
    var withSpaces = value.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
    return moneyFormat.replace(/\{\{\s*amount\s*\}\}/, withSpaces).replace('{{amount_no_decimals}}', withSpaces);
  }

  function cartBadge(count) {
    var badge = document.getElementById('privat-cart-badge');
    if (badge) {
      badge.textContent = String(count);
      badge.hidden = count <= 0;
    }
    var menuCount = document.getElementById('privat-menu-cart-count');
    if (menuCount) menuCount.textContent = String(count);
  }

  function renderCart(cartData) {
    var body = document.getElementById('privat-cart-body');
    var empty = document.getElementById('privat-cart-empty');
    var summary = document.getElementById('privat-cart-summary');
    var totalEl = document.getElementById('privat-cart-total');
    if (!body) return;

    function paint(cart) {
      cartBadge(cart.item_count);
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
        var img = item.image ? 'background-image:url(' + item.image + ')' : '';
        return '' +
          '<div class="privat-line-item" data-line-key="' + item.key + '">' +
            '<div class="privat-line-item__thumb" style="' + img + '"></div>' +
            '<div class="privat-line-item__body">' +
              '<div class="privat-line-item__name">' + item.product_title + '</div>' +
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
      var on = !!favs[id];
      btn.classList.toggle('is-active', on);
      btn.textContent = on ? '♥' : '♡';
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
        variantId: btn.getAttribute('data-variant-id') || ''
      };
    }
    setFavs(favs);
    syncFavButtons();
    if (document.querySelector('[data-drawer="favs"]').classList.contains('is-open')) renderFavorites();
  });

  function renderFavorites() {
    var body = document.getElementById('privat-favs-body');
    var empty = document.getElementById('privat-favs-empty');
    if (!body) return;
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
        '<div class="privat-fav-row">' +
          '<a href="' + f.url + '" class="privat-line-item__thumb privat-line-item__thumb--sm" style="' + img + '"></a>' +
          '<div class="privat-fav-row__body">' +
            '<a href="' + f.url + '" class="privat-fav-row__name" style="color:inherit;text-decoration:none">' + f.title + '</a>' +
            '<div class="privat-fav-row__price">' + f.price + '</div>' +
          '</div>' +
          (f.variantId ? '<button class="privat-fav-row__add" data-add-to-cart data-variant-id="' + f.variantId + '">В корзину</button>' : '') +
          '<button class="privat-fav-row__heart" data-fav-toggle data-product-id="' + id + '" data-product-title="' + f.title + '" data-product-price="' + f.price + '" data-product-image="' + f.image + '" data-product-url="' + f.url + '" data-variant-id="' + f.variantId + '">♥</button>' +
        '</div>';
    }).join('');
  }

  /* ---------------- search (predictive) ---------------- */
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
      fetch('/search/suggest.json?q=' + encodeURIComponent(q) + '&resources[type]=product&resources[limit]=10&resources[options][fields]=title,product_type,tag')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var products = (data.resources && data.resources.results && data.resources.results.products) || [];
          results.innerHTML = products.map(function (p) {
            var imgUrl = p.featured_image ? (p.featured_image.url || p.featured_image) : (p.image || '');
            var img = imgUrl ? 'background-image:url(' + imgUrl + ')' : '';
            var variantId = p.variant_id || (p.variants && p.variants[0] && p.variants[0].id) || '';
            return '' +
              '<div class="privat-search__row">' +
                '<a href="' + p.url + '" class="privat-line-item__thumb" style="width:46px;height:46px;' + img + '"></a>' +
                '<div class="privat-search__row-body">' +
                  '<a href="' + p.url + '" class="privat-search__row-name" style="color:inherit;text-decoration:none">' + p.title + '</a>' +
                  '<div class="privat-search__row-price">' + p.price + '</div>' +
                '</div>' +
                (variantId ? '<button class="privat-search__row-add" data-add-to-cart data-variant-id="' + variantId + '">В корзину</button>' : '') +
              '</div>';
          }).join('') || '<div class="privat-search__idle">Ничего не найдено</div>';
        });
    }, 220);
  });

  /* ---------------- init ---------------- */
  document.addEventListener('DOMContentLoaded', function () {
    setupReveals();
    setupParallax();
    syncFavButtons();
    var cartDataEl = document.getElementById('privat-cart-data');
    if (cartDataEl) {
      try { cartBadge(JSON.parse(cartDataEl.textContent).item_count); } catch (e) {}
    }
  });
})();

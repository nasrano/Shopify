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

  function open(name) {
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
    if (name === 'cats') { catStack.length = 0; catStack.push('root'); catShow(); }
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

  function syncWaCheckout(cart) {
    var btn = document.getElementById('privat-cart-checkout');
    if (!btn || !btn.hasAttribute('data-wa-checkout')) return;
    var msg = 'Здравствуйте! Я хочу заказать: ' + cart.items.map(function (i) {
      return i.product_title + ' — ' + i.quantity + ' шт × ' + formatMoney(i.price);
    }).join('; ') + '. Итого ' + formatMoney(cart.total_price);
    btn.href = 'https://wa.me/' + btn.getAttribute('data-wa-phone') + '?text=' + encodeURIComponent(msg);
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
            (f.sku ? '<div class="privat-fav-row__code">Код: ' + f.sku + '</div>' : '') +
            '<div class="privat-fav-row__price">' + f.price + '</div>' +
          '</div>' +
          '<div class="privat-fav-row__actions">' +
            (f.variantId ? '<button class="privat-fav-row__add" data-add-to-cart data-variant-id="' + f.variantId + '">В корзину</button>' : '') +
            '<button class="privat-fav-row__heart is-active" data-fav-toggle data-product-id="' + id + '" data-product-title="' + f.title + '" data-product-price="' + f.price + '" data-product-image="' + f.image + '" data-product-url="' + f.url + '" data-product-sku="' + (f.sku || '') + '" data-variant-id="' + f.variantId + '" aria-label="Убрать из избранного">' +
              '<svg width="17" height="17" viewBox="0 0 22 22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M11 18.6C6.7 15.3 3.8 12.6 3.8 9.6c0-2.2 1.7-3.9 3.9-3.9 1.3 0 2.5.6 3.3 1.7.8-1.1 2-1.7 3.3-1.7 2.2 0 3.9 1.7 3.9 3.9 0 3-2.9 5.7-7.2 9Z"/></svg>' +
            '</button>' +
          '</div>' +
        '</div>';
    }).join('');
  }

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

  /* ---------------- product page ---------------- */
  (function () {
    var jsonEl = document.getElementById('privat-pp-json');
    if (!jsonEl) return;
    var product;
    try { product = JSON.parse(jsonEl.textContent); } catch (e) { return; }
    if (!product || !product.variants || !product.variants.length) return;

    var select = document.getElementById('privat-pp-variant');
    var qtyEl = document.getElementById('privat-pp-qty');
    var addBtn = document.getElementById('privat-pp-add');
    var qty = 1;

    function variantById(id) {
      for (var i = 0; i < product.variants.length; i++) {
        if (String(product.variants[i].id) === String(id)) return product.variants[i];
      }
      return null;
    }
    function currentVariant() {
      if (select) return variantById(select.value) || product.variants[0];
      return variantById(addBtn && addBtn.getAttribute('data-variant-id')) || product.variants[0];
    }

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
      }
      if (totalEl) totalEl.textContent = formatMoney(v.price * qty);
      if (buyNow) {
        var msg = 'Здравствуйте! Я хочу заказать ' + buyNow.getAttribute('data-product-title') +
          (v.sku ? ', код ' + v.sku : '') +
          (select ? ' (' + v.title + ')' : '') +
          ', ' + qty + ' шт × ' + formatMoney(v.price) +
          ', итого ' + formatMoney(v.price * qty);
        buyNow.href = 'https://wa.me/' + buyNow.getAttribute('data-wa-phone') + '?text=' + encodeURIComponent(msg);
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
      if (photo.style.backgroundImage) dot.style.backgroundImage = photo.style.backgroundImage;
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
      var thumb = e.target.closest('[data-thumb]');
      if (thumb) {
        var photo = document.getElementById('privat-pp-photo');
        if (photo) photo.style.backgroundImage = 'url(' + thumb.getAttribute('data-image-url') + ')';
        document.querySelectorAll('[data-thumb]').forEach(function (t) {
          t.classList.toggle('is-active', t === thumb);
        });
      }
    });

    if (select) select.addEventListener('change', sync);

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
  })();

  /* ---------------- collection: load more ---------------- */
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-load-more]');
    if (!btn) return;
    e.preventDefault();
    var url = btn.getAttribute('data-next-url');
    if (!url || btn.disabled) return;
    btn.disabled = true;
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
        btn.disabled = false;
      } else {
        btn.remove();
      }
      syncFavButtons();
    }).catch(function () { btn.disabled = false; });
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

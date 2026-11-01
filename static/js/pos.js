(function () {
  "use strict";
  function start() {
    var app = document.getElementById("posApp");
    if (!app || app.dataset.initialized === "yes") return;
    app.dataset.initialized = "yes";
    var products = new Map();
    var cart = new Map();
    var busy = false;
    var sequence = 0;
    var noticeTimer;
    function byId(id) { return document.getElementById(id); }
    function element(tag, className, text) {
      var node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined) node.textContent = String(text);
      return node;
    }
    function money(value) {
      return Number(value).toLocaleString("ru-RU", { maximumFractionDigits: 2 }) + " ₽";
    }
    function notify(text) {
      byId("notice").textContent = text;
      byId("notice").hidden = false;
      clearTimeout(noticeTimer);
      noticeTimer = setTimeout(function () { byId("notice").hidden = true; }, 10000);
    }
    async function readJSON(response) {
      if (response.redirected && response.url.indexOf("login") !== -1) {
        throw new Error("Сессия истекла. Войдите в систему заново.");
      }
      if ((response.headers.get("content-type") || "").indexOf("application/json") === -1) {
        throw new Error("Сервер вернул не JSON: HTTP " + response.status + ". Проверьте терминал Django.");
      }
      var data = await response.json();
      if (!response.ok) throw new Error(data.error || "Ошибка HTTP " + response.status);
      return data;
    }
    async function loadProducts() {
      var current = ++sequence;
      byId("catalogStatus").textContent = "Загрузка товаров…";
      byId("retryCatalog").hidden = true;
      try {
        var response = await fetch(app.dataset.catalogUrl + "?q=" + encodeURIComponent(byId("search").value), {
          credentials: "same-origin", cache: "no-store"
        });
        var data = await readJSON(response);
        if (current !== sequence) return;
        if (!Array.isArray(data.products)) throw new Error("API не вернул список products.");
        var container = byId("products");
        container.replaceChildren();
        data.products.forEach(function (p) {
          p.stock = Number(p.stock);
          p.min_stock = Number(p.min_stock || 0);
          products.set(p.id, p);
          var button = element("button", "product-card");
          button.type = "button";
          button.disabled = p.stock <= 0;
          var picture = element("div", "product-image");
          if (p.image) {
            var image = element("img");
            image.src = p.image;
            image.alt = p.name;
            image.onerror = function () { picture.replaceChildren(); picture.textContent = "📦"; };
            picture.append(image);
          } else { picture.textContent = "📦"; }
          button.append(picture, element("div", "product-name", p.name),
            element("div", "product-price", money(p.price)),
            element("div", "product-stock", "В наличии: " + p.stock + " шт."));
          if (p.stock <= p.min_stock) button.append(element("small", "low-stock", "Низкий остаток"));
          button.addEventListener("click", function () { change(p.id, 1); });
          container.append(button);
        });
        byId("catalogStatus").textContent = data.products.length
          ? "Товаров: " + data.products.length
          : "Нет товаров по запросу. Проверьте поиск и флаг «Активен».";
        renderCart();
      } catch (error) {
        if (current !== sequence) return;
        byId("catalogStatus").textContent = error.message;
        byId("retryCatalog").hidden = false;
      }
    }
    function change(id, delta) {
      if (busy) return;
      var p = products.get(id);
      var quantity = (cart.get(id) || 0) + delta;
      if (quantity > p.stock) {
        notify("«" + p.name + "»: доступно " + p.stock + " шт.");
        return;
      }
      if (quantity <= 0) cart.delete(id); else cart.set(id, quantity);
      renderCart();
      if (delta > 0 && p.stock - quantity <= p.min_stock) {
        notify("Низкий остаток «" + p.name + "»: после продажи останется " + (p.stock - quantity) + " шт.");
      }
    }
    function renderCart() {
      byId("cart").replaceChildren();
      var total = 0;
      cart.forEach(function (quantity, id) {
        var p = products.get(id);
        if (!p) return;
        total += Number(p.price) * quantity;
        var row = element("div", "cart-line");
        var left = element("div", "cart-line-name");
        left.append(element("b", "", p.name), element("small", "", money(p.price) + " × " + quantity));
        var right = element("div", "cart-line-controls");
        var controls = element("div", "qty");
        var minus = element("button", "", "−");
        var plus = element("button", "", "+");
        minus.type = plus.type = "button";
        minus.disabled = busy;
        plus.disabled = busy || quantity >= p.stock;
        minus.addEventListener("click", function () { change(id, -1); });
        plus.addEventListener("click", function () { change(id, 1); });
        controls.append(minus, element("span", "", quantity), plus);
        right.append(element("b", "", money(Number(p.price) * quantity)), controls);
        row.append(left, right);
        byId("cart").append(row);
      });
      if (!cart.size) byId("cart").append(element("p", "empty-cart", "Чек пустой"));
      byId("total").textContent = money(total);
      app.querySelectorAll("[data-payment]").forEach(function (button) {
        button.disabled = busy || !cart.size;
      });
      byId("clearCart").disabled = busy;
    }
    async function checkout(payment) {
      if (busy || !cart.size) return;
      busy = true;
      renderCart();
      try {
        var token = app.querySelector("[name=csrfmiddlewaretoken]").value;
        var rows = Array.from(cart, function (entry) { return { id: entry[0], qty: entry[1] }; });
        var response = await fetch(app.dataset.checkoutUrl, {
          method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRFToken": token },
          body: JSON.stringify({ payment: payment, items: rows })
        });
        var data = await readJSON(response);
        cart.clear();
        renderCart();
        var text = "Чек №" + data.sale_id + " проведён: " + money(data.total);
        if (Array.isArray(data.warnings) && data.warnings.length) {
          text += "\n" + data.warnings.join("\n");
        }
        notify(text);
        await loadProducts();
      } catch (error) {
        notify(error.message + " При сетевом сбое проверьте чеки перед повторной оплатой.");
      } finally {
        busy = false;
        renderCart();
      }
    }
    byId("searchForm").addEventListener("submit", function (event) { event.preventDefault(); loadProducts(); });
    byId("retryCatalog").addEventListener("click", loadProducts);
    byId("clearCart").addEventListener("click", function () { if (!busy) { cart.clear(); renderCart(); } });
    app.querySelectorAll("[data-payment]").forEach(function (button) {
      button.addEventListener("click", function () { checkout(button.dataset.payment); });
    });
    renderCart();
    loadProducts();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();

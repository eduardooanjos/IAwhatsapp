const els = {
  form: document.getElementById("productForm"),
  formTitle: document.getElementById("formTitle"),
  productId: document.getElementById("productId"),
  name: document.getElementById("name"),
  sku: document.getElementById("sku"),
  category: document.getElementById("category"),
  price: document.getElementById("price"),
  stock: document.getElementById("stock"),
  description: document.getElementById("description"),
  active: document.getElementById("active"),
  cancelEditBtn: document.getElementById("cancelEditBtn"),
  searchInput: document.getElementById("searchInput"),
  reloadBtn: document.getElementById("reloadBtn"),
  productsList: document.getElementById("productsList"),
  statusText: document.getElementById("statusText"),
};

const state = {
  products: [],
  searchTimer: null,
};

function setStatus(msg, isError = false) {
  els.statusText.textContent = msg || "";
  els.statusText.classList.toggle("error", !!isError);
}

function escapeHtml(v) {
  return String(v || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function apiGet(url) {
  const r = await fetch(url);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `GET ${url} falhou`);
  return data;
}

async function apiRequest(url, method, body) {
  const r = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `${method} ${url} falhou`);
  return data;
}

function clearForm() {
  els.formTitle.textContent = "Novo produto";
  els.productId.value = "";
  els.name.value = "";
  els.sku.value = "";
  els.category.value = "";
  els.price.value = "0";
  els.stock.value = "0";
  els.description.value = "";
  els.active.checked = true;
}

function getFormPayload() {
  return {
    name: (els.name.value || "").trim(),
    sku: (els.sku.value || "").trim(),
    category: (els.category.value || "").trim(),
    price: Number(els.price.value || 0),
    stock: Number(els.stock.value || 0),
    description: (els.description.value || "").trim(),
    active: !!els.active.checked,
  };
}

function fillForm(product) {
  els.formTitle.textContent = `Editando produto #${product.id}`;
  els.productId.value = String(product.id);
  els.name.value = product.name || "";
  els.sku.value = product.sku || "";
  els.category.value = product.category || "";
  els.price.value = String(product.price || 0);
  els.stock.value = String(product.stock || 0);
  els.description.value = product.description || "";
  els.active.checked = !!product.active;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderProducts() {
  if (!state.products.length) {
    els.productsList.innerHTML = `<div class="wa-empty-list">Nenhum produto cadastrado.</div>`;
    return;
  }

  els.productsList.innerHTML = state.products
    .map(
      (p) => `
      <article class="product-item">
        <div class="product-main">
          <div class="product-title">${escapeHtml(p.name)}</div>
          <div class="product-meta">
            SKU: ${escapeHtml(p.sku || "-")} | Categoria: ${escapeHtml(p.category || "-")}
          </div>
          <div class="product-meta">
            Preco: R$ ${Number(p.price || 0).toFixed(2)} | Estoque: ${Number(p.stock || 0)}
            | ${p.active ? "Ativo" : "Inativo"}
          </div>
          <div class="product-desc">${escapeHtml(p.description || "")}</div>
        </div>
        <div class="product-actions">
          <button data-edit="${p.id}" class="products-btn-secondary" type="button">Editar</button>
          <button data-delete="${p.id}" class="products-btn-danger" type="button">Excluir</button>
        </div>
      </article>
    `
    )
    .join("");

  els.productsList.querySelectorAll("[data-edit]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = Number(btn.getAttribute("data-edit"));
      const product = state.products.find((x) => Number(x.id) === id);
      if (product) fillForm(product);
    });
  });

  els.productsList.querySelectorAll("[data-delete]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = Number(btn.getAttribute("data-delete"));
      if (!confirm("Tem certeza que deseja excluir este produto?")) return;
      try {
        await apiRequest(`/api/products/${id}`, "DELETE");
        setStatus("Produto excluido com sucesso.");
        await loadProducts();
      } catch (err) {
        setStatus(err.message || "Falha ao excluir produto.", true);
      }
    });
  });
}

async function loadProducts() {
  const q = encodeURIComponent((els.searchInput.value || "").trim());
  const data = await apiGet(`/api/products?q=${q}`);
  state.products = data.products || [];
  renderProducts();
}

async function saveProduct(e) {
  e.preventDefault();
  const payload = getFormPayload();
  if (!payload.name) {
    setStatus("Informe o nome do produto.", true);
    return;
  }

  try {
    const id = Number(els.productId.value || 0);
    if (id) {
      await apiRequest(`/api/products/${id}`, "PUT", payload);
      setStatus("Produto atualizado com sucesso.");
    } else {
      await apiRequest("/api/products", "POST", payload);
      setStatus("Produto cadastrado com sucesso.");
    }
    clearForm();
    await loadProducts();
  } catch (err) {
    setStatus(err.message || "Falha ao salvar produto.", true);
  }
}

function wire() {
  els.form.addEventListener("submit", saveProduct);
  els.cancelEditBtn.addEventListener("click", () => {
    clearForm();
    setStatus("");
  });
  els.reloadBtn.addEventListener("click", async () => {
    try {
      await loadProducts();
      setStatus("Lista atualizada.");
    } catch (err) {
      setStatus(err.message || "Falha ao atualizar lista.", true);
    }
  });
  els.searchInput.addEventListener("input", () => {
    if (state.searchTimer) clearTimeout(state.searchTimer);
    state.searchTimer = setTimeout(async () => {
      try {
        await loadProducts();
      } catch (err) {
        setStatus(err.message || "Falha ao buscar produtos.", true);
      }
    }, 250);
  });
}

(async function init() {
  clearForm();
  wire();
  try {
    await loadProducts();
  } catch (err) {
    setStatus(err.message || "Falha ao carregar produtos.", true);
  }
})();

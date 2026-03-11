const els = {
  form: document.getElementById("responseForm"),
  formTitle: document.getElementById("formTitle"),
  responseId: document.getElementById("responseId"),
  question: document.getElementById("question"),
  answer: document.getElementById("answer"),
  tags: document.getElementById("tags"),
  active: document.getElementById("active"),
  cancelEditBtn: document.getElementById("cancelEditBtn"),
  searchInput: document.getElementById("searchInput"),
  reloadBtn: document.getElementById("reloadBtn"),
  responsesList: document.getElementById("responsesList"),
  statusText: document.getElementById("statusText"),
};

const state = {
  responses: [],
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
  els.formTitle.textContent = "Nova resposta";
  els.responseId.value = "";
  els.question.value = "";
  els.answer.value = "";
  els.tags.value = "";
  els.active.checked = true;
}

function getFormPayload() {
  return {
    question: (els.question.value || "").trim(),
    answer: (els.answer.value || "").trim(),
    tags: String(els.tags.value || "")
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean),
    active: !!els.active.checked,
  };
}

function fillForm(item) {
  els.formTitle.textContent = `Editando resposta #${item.id}`;
  els.responseId.value = String(item.id);
  els.question.value = item.question || "";
  els.answer.value = item.answer || "";
  els.tags.value = Array.isArray(item.tags) ? item.tags.join(", ") : "";
  els.active.checked = !!item.active;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderResponses() {
  if (!state.responses.length) {
    els.responsesList.innerHTML = `<div class="wa-empty-list">Nenhuma resposta cadastrada.</div>`;
    return;
  }

  els.responsesList.innerHTML = state.responses
    .map(
      (r) => `
      <article class="response-item">
        <div class="response-main">
          <div class="response-title">${escapeHtml(r.question)}</div>
          <div class="response-meta">
            Tags: ${escapeHtml(Array.isArray(r.tags) && r.tags.length ? r.tags.join(", ") : "-")}
            | ${r.active ? "Ativa" : "Inativa"}
          </div>
          <div class="response-answer">${escapeHtml(r.answer || "")}</div>
        </div>
        <div class="response-actions">
          <button data-edit="${r.id}" class="responses-btn-secondary" type="button">Editar</button>
          <button data-delete="${r.id}" class="responses-btn-danger" type="button">Excluir</button>
        </div>
      </article>
    `
    )
    .join("");

  els.responsesList.querySelectorAll("[data-edit]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = Number(btn.getAttribute("data-edit"));
      const item = state.responses.find((x) => Number(x.id) === id);
      if (item) fillForm(item);
    });
  });

  els.responsesList.querySelectorAll("[data-delete]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = Number(btn.getAttribute("data-delete"));
      if (!confirm("Tem certeza que deseja excluir esta resposta?")) return;
      try {
        await apiRequest(`/api/responses/${id}`, "DELETE");
        setStatus("Resposta excluida com sucesso.");
        await loadResponses();
      } catch (err) {
        setStatus(err.message || "Falha ao excluir resposta.", true);
      }
    });
  });
}

async function loadResponses() {
  const q = encodeURIComponent((els.searchInput.value || "").trim());
  const data = await apiGet(`/api/responses?q=${q}`);
  state.responses = data.responses || [];
  renderResponses();
}

async function saveResponse(e) {
  e.preventDefault();
  const payload = getFormPayload();
  if (!payload.question) {
    setStatus("Informe a pergunta.", true);
    return;
  }
  if (!payload.answer) {
    setStatus("Informe a resposta.", true);
    return;
  }

  try {
    const id = Number(els.responseId.value || 0);
    if (id) {
      await apiRequest(`/api/responses/${id}`, "PUT", payload);
      setStatus("Resposta atualizada com sucesso.");
    } else {
      await apiRequest("/api/responses", "POST", payload);
      setStatus("Resposta cadastrada com sucesso.");
    }
    clearForm();
    await loadResponses();
  } catch (err) {
    setStatus(err.message || "Falha ao salvar resposta.", true);
  }
}

function wire() {
  els.form.addEventListener("submit", saveResponse);
  els.cancelEditBtn.addEventListener("click", () => {
    clearForm();
    setStatus("");
  });
  els.reloadBtn.addEventListener("click", async () => {
    try {
      await loadResponses();
      setStatus("Lista atualizada.");
    } catch (err) {
      setStatus(err.message || "Falha ao atualizar lista.", true);
    }
  });
  els.searchInput.addEventListener("input", () => {
    if (state.searchTimer) clearTimeout(state.searchTimer);
    state.searchTimer = setTimeout(async () => {
      try {
        await loadResponses();
      } catch (err) {
        setStatus(err.message || "Falha ao buscar respostas.", true);
      }
    }, 250);
  });
}

(async function init() {
  clearForm();
  wire();
  try {
    await loadResponses();
  } catch (err) {
    setStatus(err.message || "Falha ao carregar respostas.", true);
  }
})();

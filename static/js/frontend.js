const els = {
  chatList: document.getElementById("chatList"),
  chatCount: document.getElementById("chatCount"),
  searchInput: document.getElementById("searchInput"),
  refreshBtn: document.getElementById("refreshBtn"),

  activeTitle: document.getElementById("activeTitle"),
  activeMeta: document.getElementById("activeMeta"),
  toggleAiBtn: document.getElementById("toggleAiBtn"),
  clearBtn: document.getElementById("clearBtn"),

  messages: document.getElementById("messages"),
  composerInput: document.getElementById("composerInput"),
  sendBtn: document.getElementById("sendBtn"),
  composerHint: document.getElementById("composerHint"),

  sysPrompt: document.getElementById("sysPrompt"),
  saveSysBtn: document.getElementById("saveSysBtn"),
  reloadSysBtn: document.getElementById("reloadSysBtn"),

  autoRefresh: document.getElementById("autoRefresh"),
  showSystemInDebug: document.getElementById("showSystemInDebug"),

  modal: document.getElementById("modal"),
  modalTitle: document.getElementById("modalTitle"),
  modalBody: document.getElementById("modalBody"),
  modalClose: document.getElementById("modalClose"),

    // Produtos
  prodCount: document.getElementById("prodCount"),
  prodList: document.getElementById("prodList"),
  prodSearch: document.getElementById("prodSearch"),
  prodRefreshBtn: document.getElementById("prodRefreshBtn"),
  prodOnlyActive: document.getElementById("prodOnlyActive"),
  newProdBtn: document.getElementById("newProdBtn"),
};

let LAST_CHAT = null;

let STATE = {
  chats: [],
  active: null,  // {numero, ai_enabled, last_preview, updated_at}
  history: [],
  autoTimer: null,
  showDebug: false,
  products: [],
};

function isNearBottom(el, thresholdPx = 30){
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
  return distance <= thresholdPx;
}

function keepScrollIfNotNearBottom(el, wasNearBottom){
  if(wasNearBottom){
    el.scrollTop = el.scrollHeight;
  }
}


function fmtTime(ts){
  if(!ts) return "—";
  try{
    const d = new Date(ts * 1000);
    return d.toLocaleString("pt-BR");
  } catch { return "—"; }
}

async function apiGet(url){
  const r = await fetch(url);
  if(!r.ok) throw new Error("GET " + url + " failed");
  return await r.json();
}
async function apiPost(url, body){
  const r = await fetch(url, {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(body || {})
  });
  if(!r.ok) {
    const t = await r.text().catch(()=> "");
    throw new Error("POST " + url + " failed: " + t);
  }
  return await r.json().catch(()=> ({}));
}

function setTabs(){
  document.querySelectorAll(".tab").forEach(btn=>{
    btn.addEventListener("click", ()=>{
      document.querySelectorAll(".tab").forEach(b=>b.classList.remove("active"));
      document.querySelectorAll(".tabpane").forEach(p=>p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(btn.dataset.tab).classList.add("active");
    });
  });
}

function openModal(title, html){
  els.modalTitle.textContent = title;
  els.modalBody.innerHTML = html;
  els.modal.classList.remove("hidden");
}
function closeModal(){
  els.modal.classList.add("hidden");
  els.modalBody.innerHTML = "";
}
els.modalClose.addEventListener("click", closeModal);
els.modal.addEventListener("click", (e)=>{
  if(e.target === els.modal) closeModal();
});

function renderChatList(){
  const q = (els.searchInput.value || "").trim();
  const filtered = q ? STATE.chats.filter(c => (c.numero || "").includes(q)) : STATE.chats;

  els.chatCount.textContent = String(filtered.length);
  els.chatList.innerHTML = "";

  filtered.forEach(c=>{
    const div = document.createElement("div");
    div.className = "chatitem" + (STATE.active && STATE.active.numero === c.numero ? " active" : "");
    const badge = c.ai_enabled ? `<span class="badge ok">IA ON</span>` : `<span class="badge off">IA OFF</span>`;
    div.innerHTML = `
      <div class="chat-left">
        <div class="chatnum">${c.numero}</div>
        <div class="chatsub">${escapeHtml(c.last_preview || "—")}</div>
      </div>
      ${badge}
    `;
    div.addEventListener("click", ()=> selectChat(c.numero));
    els.chatList.appendChild(div);
  });
}

function escapeHtml(s){
  return (s||"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
}

function renderHeader(){
  if(!STATE.active){
    els.activeTitle.textContent = "Selecione um chat";
    els.activeMeta.textContent = "—";
    els.toggleAiBtn.textContent = "IA: —";
    els.toggleAiBtn.disabled = true;
    els.clearBtn.disabled = true;
    els.composerInput.disabled = true;
    els.sendBtn.disabled = true;
    return;
  }
  els.activeTitle.textContent = STATE.active.numero;
  els.activeMeta.textContent = `Atualizado: ${fmtTime(STATE.active.updated_at)} | Último: ${STATE.active.last_preview || "—"}`;
  els.toggleAiBtn.disabled = false;
  els.clearBtn.disabled = false;

  const on = !!STATE.active.ai_enabled;
  els.toggleAiBtn.textContent = on ? "IA: ON (clique p/ OFF)" : "IA: OFF (clique p/ ON)";
  els.toggleAiBtn.classList.toggle("warn", on);
  els.toggleAiBtn.classList.toggle("ghost", !on);

  // envio manual só quando IA OFF
  els.composerInput.disabled = on;
  els.sendBtn.disabled = on;
  els.composerHint.innerHTML = on
    ? "IA está <b>habilitada</b>. Para envio manual, desligue a IA neste chat."
    : "IA está <b>desabilitada</b>. Envie mensagens manualmente por aqui.";
}
function renderMessages(){
  const activeNumero = STATE.active?.numero || null;

  // entrou em outro chat? vai pro final
  const chatChanged = (activeNumero && LAST_CHAT !== activeNumero);
  if(chatChanged) LAST_CHAT = activeNumero;

  // só considera "near bottom" se não trocou de chat
  const wasNearBottom = chatChanged ? true : isNearBottom(els.messages, 30);

  if(!STATE.active){
    els.messages.classList.add("empty");
    els.messages.innerHTML = `
      <div class="emptyState">
        <div class="emoji">💬</div>
        <div>Escolha um chat na esquerda pra ver o histórico.</div>
      </div>
    `;
    return;
  }

  els.messages.classList.remove("empty");
  els.messages.innerHTML = "";

  const items = STATE.history || [];
  if(items.length === 0){
    els.messages.classList.add("empty");
    els.messages.innerHTML = `
      <div class="emptyState">
        <div class="emoji">🗂️</div>
        <div>Sem histórico ainda.</div>
      </div>
    `;
    return;
  }

  const frag = document.createDocumentFragment();

  items.forEach(it=>{
    const role = it.role === "user" ? "user" : "assistant";
    const wrap = document.createElement("div");
    wrap.className = "msg " + role;

    const b = document.createElement("div");
    b.className = "bubble";
    b.innerHTML = `
      ${escapeHtml(it.text || "")}
      <div class="bmeta">${role === "user" ? "Cliente" : "IA"} · ${fmtTime(it.ts)}</div>
    `;

    wrap.appendChild(b);
    frag.appendChild(wrap);
  });

  els.messages.appendChild(frag);

  // aplica scroll depois do DOM estar pronto
  requestAnimationFrame(() => {
    keepScrollIfNotNearBottom(els.messages, wasNearBottom);
  });
}


async function loadChats(){
  const data = await apiGet("/api/chats");
  STATE.chats = data.chats || [];
  renderChatList();

  // se ativo ainda existe, atualiza header
  if(STATE.active){
    const updated = STATE.chats.find(c=>c.numero === STATE.active.numero);
    if(updated){
      STATE.active = updated;
      renderHeader();
    }
  }
}

async function selectChat(numero){
  const c = STATE.chats.find(x=>x.numero === numero) || await apiGet("/api/chat/" + numero);
  STATE.active = c;
  renderHeader();

  const data = await apiGet("/api/chat/" + numero);
  STATE.history = data.history || [];
  // opcional: mostrar debug de contexto (mini janela)
  if(STATE.showDebug){
    openModal("Debug do chat " + numero, `<pre style="white-space:pre-wrap; font-family: var(--mono); color: #cfe0ff;">${escapeHtml(data.debug_context || "")}</pre>`);
  }
  renderMessages();
  renderChatList();
}

async function toggleAI(){
  if(!STATE.active) return;
  const numero = STATE.active.numero;
  const data = await apiPost(`/api/chat/${numero}/toggle`, {});
  // refresh local
  STATE.active.ai_enabled = data.ai_enabled;
  renderHeader();
  await loadChats();
}

async function sendManual(){
  if(!STATE.active) return;
  const numero = STATE.active.numero;
  const text = (els.composerInput.value || "").trim();
  if(!text) return;

  els.sendBtn.disabled = true;
  try{
    await apiPost(`/api/chat/${numero}/send`, { text });
    els.composerInput.value = "";
    await selectChat(numero);
  } finally{
    renderHeader();
    els.sendBtn.disabled = false;
  }
}

async function clearHistory(){
  if(!STATE.active) return;
  const numero = STATE.active.numero;
  openModal("Limpar histórico?", `
    <div style="color:var(--muted); margin-bottom:12px;">
      Isso apaga <code>hist:${numero}</code> no Redis (não afeta WhatsApp).
    </div>
    <div style="display:flex; gap:10px; justify-content:flex-end;">
      <button class="btn ghost" id="mCancel">Cancelar</button>
      <button class="btn danger" id="mOk">Apagar</button>
    </div>
  `);
  document.getElementById("mCancel").onclick = closeModal;
  document.getElementById("mOk").onclick = async ()=>{
    await apiPost(`/api/chat/${numero}/clear`, {});
    closeModal();
    await loadChats();
    await selectChat(numero);
  };
}

async function loadSysPrompt(){
  const data = await apiGet("/api/config");
  els.sysPrompt.value = data.sys_prompt || "";
}

async function saveSysPrompt(){
  const v = (els.sysPrompt.value || "").trim();
  await apiPost("/api/config", { sys_prompt: v });
  openModal("Salvo", `<div style="color:var(--muted);">cfg:sys atualizado no Redis.</div>`);
}

function setAutoRefresh(){
  if(STATE.autoTimer) clearInterval(STATE.autoTimer);
  if(els.autoRefresh.checked){
    STATE.autoTimer = setInterval(async ()=>{
      try{
        await loadChats();
        if(STATE.active){
          const numero = STATE.active.numero;
          const data = await apiGet("/api/chat/" + numero);
          STATE.history = data.history || [];
          renderMessages();
        }
      } catch {}
    }, 3000);
  }
}

function wire(){
  els.refreshBtn.addEventListener("click", async ()=>{
    await loadChats();
    if(STATE.active) await selectChat(STATE.active.numero);
  });
  els.searchInput.addEventListener("input", renderChatList);

  els.toggleAiBtn.addEventListener("click", toggleAI);
  els.sendBtn.addEventListener("click", sendManual);
  els.composerInput.addEventListener("keydown", (e)=>{
    if((e.ctrlKey || e.metaKey) && e.key === "Enter") sendManual();
  });

  els.clearBtn.addEventListener("click", clearHistory);

  els.reloadSysBtn.addEventListener("click", loadSysPrompt);
  els.saveSysBtn.addEventListener("click", saveSysPrompt);

  els.autoRefresh.addEventListener("change", setAutoRefresh);
  els.showSystemInDebug.addEventListener("change", ()=>{
    STATE.showDebug = els.showSystemInDebug.checked;
  });

  // Produtos
  els.prodRefreshBtn.addEventListener("click", loadProducts);
  els.prodSearch.addEventListener("input", ()=>{
    // debounce simples
    clearTimeout(window.__prodT);
    window.__prodT = setTimeout(loadProducts, 250);
  });
  els.prodOnlyActive.addEventListener("change", loadProducts);
  els.newProdBtn.addEventListener("click", ()=> openProductModal("create"));


  setTabs();
}

async function loadProducts(){
  const q = (els.prodSearch.value || "").trim();
  const active = els.prodOnlyActive.checked ? "1" : "0";
  const data = await apiGet(`/api/products?q=${encodeURIComponent(q)}&active=${active}`);
  STATE.products = data.items || [];
  renderProducts();
}

function money(v){
  try{ return Number(v).toFixed(2); } catch { return String(v); }
}

function renderProducts(){
  const items = STATE.products || [];
  els.prodCount.textContent = String(items.length);
  els.prodList.innerHTML = "";

  if(items.length === 0){
    els.prodList.innerHTML = `<div class="card" style="color:var(--muted);">Nenhum produto encontrado.</div>`;
    return;
  }

  items.forEach(p=>{
    const div = document.createElement("div");
    div.className = "proditem";

    const badge = p.active ? `<span class="badge ok">Ativo</span>` : `<span class="badge off">Inativo</span>`;

    div.innerHTML = `
      <div class="prod-left">
        <div class="prod-name">${escapeHtml(p.name || "")}</div>
        <div class="prod-sku">SKU: ${escapeHtml(p.sku || "")} · ${badge}</div>
        <div class="prod-meta">
          <span>Preço: R$ ${money(p.price)}</span>
          <span>Estoque: ${p.stock}</span>
        </div>
      </div>
      <div class="pbtns">
        <button class="btn ghost smallbtn" data-act="stock" data-id="${p.id}">Estoque</button>
        <button class="btn ghost smallbtn" data-act="edit" data-id="${p.id}">Editar</button>
        <button class="btn warn smallbtn" data-act="toggle" data-id="${p.id}">
          ${p.active ? "Desativar" : "Ativar"}
        </button>
      </div>
    `;

    div.querySelectorAll("button").forEach(btn=>{
      btn.addEventListener("click", ()=> handleProdAction(btn.dataset.act, Number(btn.dataset.id)));
    });

    els.prodList.appendChild(div);
  });
}

function productById(id){
  return (STATE.products || []).find(x => Number(x.id) === Number(id));
}

function openProductModal(mode, product){
  const isEdit = mode === "edit";
  const p = product || { sku:"", name:"", price:0, stock:0, active:true };

  openModal(isEdit ? "Editar produto" : "Novo produto", `
    <div class="card" style="margin:0;">
      <div class="card-title">${isEdit ? "Atualize os campos" : "Preencha os campos"}</div>

      <label class="hint">SKU</label>
      <input id="mSku" value="${escapeHtml(p.sku)}" ${isEdit ? "disabled" : ""} style="width:100%; padding:10px 12px; border-radius:12px; border:1px solid var(--line); background:#07101e; color:var(--text); outline:none;"/>

      <div style="height:10px;"></div>

      <label class="hint">Nome</label>
      <input id="mName" value="${escapeHtml(p.name)}" style="width:100%; padding:10px 12px; border-radius:12px; border:1px solid var(--line); background:#07101e; color:var(--text); outline:none;"/>

      <div style="height:10px;"></div>

      <div style="display:flex; gap:10px;">
        <div style="flex:1;">
          <label class="hint">Preço</label>
          <input id="mPrice" type="number" step="0.01" value="${Number(p.price || 0)}"
            style="width:100%; padding:10px 12px; border-radius:12px; border:1px solid var(--line); background:#07101e; color:var(--text); outline:none;"/>
        </div>
        <div style="flex:1;">
          <label class="hint">Estoque</label>
          <input id="mStock" type="number" step="1" value="${Number(p.stock || 0)}"
            style="width:100%; padding:10px 12px; border-radius:12px; border:1px solid var(--line); background:#07101e; color:var(--text); outline:none;"/>
        </div>
      </div>

      <label class="chk" style="margin:12px 0 0;">
        <input id="mActive" type="checkbox" ${p.active ? "checked" : ""}/>
        <span>Ativo</span>
      </label>

      <div class="row" style="justify-content:flex-end;">
        <button class="btn ghost" id="mCancel">Cancelar</button>
        <button class="btn" id="mSave">${isEdit ? "Salvar" : "Cadastrar"}</button>
      </div>
    </div>
  `);

  document.getElementById("mCancel").onclick = closeModal;
  document.getElementById("mSave").onclick = async ()=>{
    const sku = (document.getElementById("mSku").value || "").trim();
    const name = (document.getElementById("mName").value || "").trim();
    const price = Number(document.getElementById("mPrice").value || 0);
    const stock = parseInt(document.getElementById("mStock").value || "0", 10);
    const active = document.getElementById("mActive").checked;

    if(!sku || !name){
      openModal("Erro", `<div style="color:var(--muted);">SKU e Nome são obrigatórios.</div>`);
      return;
    }

    try{
      if(isEdit){
        await apiPost(`/api/products/${p.id}/update`, { name, price, stock, active });
      } else {
        await apiPost(`/api/products/create`, { sku, name, price, stock, active });
      }
      closeModal();
      await loadProducts();
    } catch(e){
      openModal("Erro", `<div style="color:var(--muted);">${escapeHtml(String(e.message || e))}</div>`);
    }
  };
}

function openStockModal(product){
  const p = product;
  openModal("Ajustar estoque", `
    <div class="card" style="margin:0;">
      <div class="card-title">${escapeHtml(p.name)} <span style="color:var(--muted); font-weight:600;">(SKU: ${escapeHtml(p.sku)})</span></div>
      <div class="hint">Estoque atual: <b>${p.stock}</b></div>

      <div style="display:flex; gap:10px; margin-top:10px;">
        <button class="btn ghost" id="mDec">-1</button>
        <input id="mNewStock" type="number" value="${p.stock}"
          style="flex:1; padding:10px 12px; border-radius:12px; border:1px solid var(--line); background:#07101e; color:var(--text); outline:none;"/>
        <button class="btn ghost" id="mInc">+1</button>
      </div>

      <div class="row" style="justify-content:flex-end;">
        <button class="btn ghost" id="mCancel">Cancelar</button>
        <button class="btn" id="mSave">Salvar</button>
      </div>
    </div>
  `);

  const inp = document.getElementById("mNewStock");
  document.getElementById("mDec").onclick = ()=> inp.value = String(Number(inp.value||0) - 1);
  document.getElementById("mInc").onclick = ()=> inp.value = String(Number(inp.value||0) + 1);

  document.getElementById("mCancel").onclick = closeModal;
  document.getElementById("mSave").onclick = async ()=>{
    const stock = parseInt(inp.value || "0", 10);
    await apiPost(`/api/products/${p.id}/stock`, { stock });
    closeModal();
    await loadProducts();
  };
}

async function handleProdAction(action, id){
  const p = productById(id);
  if(!p) return;

  if(action === "edit"){
    openProductModal("edit", p);
    return;
  }
  if(action === "stock"){
    openStockModal(p);
    return;
  }
  if(action === "toggle"){
    await apiPost(`/api/products/${id}/toggle`, {});
    await loadProducts();
    return;
  }
}


(async function init(){
  wire();
  await loadSysPrompt();
  await loadChats();
  await loadProducts();  // NOVO
  setAutoRefresh();
})();


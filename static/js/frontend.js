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
};

let STATE = {
  chats: [],
  active: null,  // {numero, ai_enabled, last_preview, updated_at}
  history: [],
  autoTimer: null,
  showDebug: false,
};

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
    els.messages.appendChild(wrap);
  });

  els.messages.scrollTop = els.messages.scrollHeight;
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

  setTabs();
}

(async function init(){
  wire();
  await loadSysPrompt();
  await loadChats();
  setAutoRefresh();
})();

const els = {
  chatList: document.getElementById("chatList"),
  messages: document.getElementById("messages"),
  composer: document.getElementById("composer"),
  composerInput: document.getElementById("composerInput"),
  activeName: document.getElementById("activeContactName"),
  activeAvatar: document.getElementById("activeContactAvatar"),
  aiToggleBtn: document.getElementById("aiToggleBtn"),
  newContactBtn: document.getElementById("newContactBtn"),
  deleteContactBtn: document.getElementById("deleteContactBtn"),
  inlineContactNameInput: document.getElementById("inlineContactNameInput"),
};

const state = {
  chats: [],
  active: null,
  history: [],
  pollTimer: null,
  lastChatNumero: null,
  isEditingContact: false,
};

function isNearBottom(el, thresholdPx = 40) {
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
  return distance <= thresholdPx;
}

function escapeHtml(v) {
  return String(v || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function firstLetter(v) {
  const s = String(v || "").trim();
  return s ? s[0].toUpperCase() : "?";
}

function fmtTime(ts) {
  if (!ts) return "";
  try {
    return new Date(Number(ts) * 1000).toLocaleString("pt-BR");
  } catch {
    return "";
  }
}

async function apiGet(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`GET ${url} falhou`);
  return await r.json();
}

async function apiPost(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `POST ${url} falhou`);
  return data;
}

async function apiDelete(url) {
  const r = await fetch(url, { method: "DELETE" });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `DELETE ${url} falhou`);
  return data;
}

function renderChats() {
  els.chatList.innerHTML = "";

  if (!state.chats.length) {
    els.chatList.innerHTML = `
      <div class="wa-empty-list">Nenhuma conversa ainda.</div>
    `;
    return;
  }

  state.chats.forEach((chat) => {
    const displayName = chat.display_name || chat.contact_name || chat.numero;
    const div = document.createElement("div");
    div.className = "wa-chat" + (state.active?.numero === chat.numero ? " active" : "");
    div.innerHTML = `
      <div class="wa-chat-avatar">${firstLetter(displayName)}</div>
      <div class="wa-chat-info">
        <div class="wa-chat-name">${escapeHtml(displayName)}</div>
        <div class="wa-chat-lastmsg">${escapeHtml(chat.numero)}</div>
        <div class="wa-chat-lastmsg">${escapeHtml(chat.last_preview || "Sem mensagens")}</div>
      </div>
      <span class="wa-ai-pill ${chat.ai_enabled ? "on" : "off"}">${chat.ai_enabled ? "IA ON" : "IA OFF"}</span>
    `;
    div.addEventListener("click", () => selectChat(chat.numero));
    els.chatList.appendChild(div);
  });
}

function renderHeader() {
  if (!state.active) {
    els.activeName.textContent = "Selecione uma conversa";
    els.activeAvatar.textContent = "?";
    els.aiToggleBtn.disabled = true;
    els.aiToggleBtn.textContent = "IA: -";
    els.newContactBtn.disabled = true;
    els.newContactBtn.textContent = "+";
    els.deleteContactBtn.classList.add("wa-hidden");
    els.deleteContactBtn.disabled = true;
    els.inlineContactNameInput.classList.remove("visible");
    state.isEditingContact = false;
    return;
  }

  const hasSavedContact = !!(state.active.contact_name || "").trim();
  const headerName = hasSavedContact ? state.active.contact_name : state.active.numero;
  els.activeName.textContent = headerName;
  els.activeAvatar.textContent = firstLetter(state.active.contact_name || state.active.numero);
  els.aiToggleBtn.disabled = false;
  els.aiToggleBtn.textContent = state.active.ai_enabled ? "IA: ON" : "IA: OFF";
  els.aiToggleBtn.classList.toggle("off", !state.active.ai_enabled);
  els.newContactBtn.disabled = false;

  if (state.isEditingContact) {
    els.inlineContactNameInput.classList.add("visible");
    els.newContactBtn.textContent = "✅";
    els.deleteContactBtn.classList.toggle("wa-hidden", !hasSavedContact);
    els.deleteContactBtn.disabled = !hasSavedContact;
  } else {
    els.inlineContactNameInput.classList.remove("visible");
    els.newContactBtn.textContent = hasSavedContact ? "📝" : "+";
    els.deleteContactBtn.classList.add("wa-hidden");
    els.deleteContactBtn.disabled = true;
  }
}

function renderMessages() {
  const currentChat = state.active?.numero || null;
  const chatChanged = currentChat && state.lastChatNumero !== currentChat;
  if (chatChanged) state.lastChatNumero = currentChat;
  const shouldAutoScroll = chatChanged ? true : isNearBottom(els.messages);

  els.messages.innerHTML = "";

  if (!state.active) {
    els.messages.innerHTML = `
      <div class="wa-empty-chat">Escolha um chat na coluna esquerda.</div>
    `;
    return;
  }

  if (!state.history.length) {
    els.messages.innerHTML = `
      <div class="wa-empty-chat">Sem histórico ainda.</div>
    `;
    return;
  }

  state.history.forEach((msg) => {
    const mine = msg.role !== "user";
    const isAudioTranscript = !mine && String(msg.text || "").startsWith("[Audio] ");
    const cleanText = isAudioTranscript ? String(msg.text).slice(8) : String(msg.text || "");
    const wrap = document.createElement("div");
    wrap.className = `wa-msg ${mine ? "wa-msg-assistant" : "wa-msg-user"}`;
    wrap.innerHTML = `
      <div class="wa-bubble">
        ${isAudioTranscript ? '<div class="wa-audio-flag">Audio transcrito</div>' : ""}
        ${escapeHtml(cleanText)}
        <div class="wa-meta">${mine ? "Atendimento" : "Cliente"} ${fmtTime(msg.ts)}</div>
      </div>
    `;
    els.messages.appendChild(wrap);
  });

  if (shouldAutoScroll) {
    els.messages.scrollTop = els.messages.scrollHeight;
  }
}

async function loadChats() {
  const data = await apiGet("/api/chats");
  state.chats = data.chats || [];

  if (state.active) {
    const found = state.chats.find((c) => c.numero === state.active.numero);
    if (found) state.active = found;
  }

  if (!state.active && state.chats.length) {
    state.active = state.chats[0];
    await loadActiveHistory();
  }

  renderChats();
  renderHeader();
}

async function loadActiveHistory() {
  if (!state.active) return;
  const data = await apiGet(`/api/chat/${encodeURIComponent(state.active.numero)}`);
  state.active = {
    numero: data.numero,
    contact_name: data.contact_name || "",
    display_name: data.display_name || data.contact_name || data.numero,
    ai_enabled: !!data.ai_enabled,
    updated_at: data.updated_at,
    last_preview: data.last_preview || "",
  };
  state.history = data.history || [];
  renderHeader();
  renderMessages();
  renderChats();
}

async function selectChat(numero) {
  state.active = state.chats.find((c) => c.numero === numero) || { numero };
  await loadActiveHistory();
}

async function sendMessage() {
  if (!state.active) return;
  const text = (els.composerInput.value || "").trim();
  if (!text) return;

  await apiPost(`/api/chat/${encodeURIComponent(state.active.numero)}/send`, { text });
  els.composerInput.value = "";
  await loadChats();
  await loadActiveHistory();
}

async function toggleAi() {
  if (!state.active) return;
  await apiPost(`/api/chat/${encodeURIComponent(state.active.numero)}/toggle`, {});
  await loadChats();
  await loadActiveHistory();
}

function setContactEditor(open) {
  state.isEditingContact = open;
  if (open && state.active) {
    els.inlineContactNameInput.value = state.active.contact_name || "";
    els.inlineContactNameInput.classList.add("visible");
    els.inlineContactNameInput.focus();
    els.inlineContactNameInput.select();
  }
  if (!open) {
    els.inlineContactNameInput.classList.remove("visible");
  }
  renderHeader();
}

async function saveInlineContact() {
  if (!state.active) return;
  const name = (els.inlineContactNameInput.value || "").trim();
  const phone = (state.active.numero || "").trim();
  if (!name || !phone) {
    alert("Informe o nome do contato.");
    return;
  }
  await apiPost("/api/contacts", { name, phone });
  setContactEditor(false);
  await loadChats();
  if (state.active?.numero) await loadActiveHistory();
}

async function deleteInlineContact() {
  if (!state.active?.numero) return;
  await apiDelete(`/api/contacts/${encodeURIComponent(state.active.numero)}`);
  setContactEditor(false);
  await loadChats();
  await loadActiveHistory();
}

function wire() {
  els.composer.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await sendMessage();
    } catch (err) {
      alert(err.message || "Erro ao enviar");
    }
  });

  els.aiToggleBtn.addEventListener("click", async () => {
    try {
      await toggleAi();
    } catch (err) {
      alert(err.message || "Erro ao alternar IA");
    }
  });

  els.newContactBtn.addEventListener("click", async () => {
    if (!state.active) return;
    if (!state.isEditingContact) {
      setContactEditor(true);
      return;
    }
    try {
      await saveInlineContact();
    } catch (err) {
      alert(err.message || "Erro ao salvar contato");
    }
  });

  els.deleteContactBtn.addEventListener("click", async () => {
    if (!state.active?.contact_name) return;
    const ok = confirm(`Excluir o contato "${state.active.contact_name}"?`);
    if (!ok) return;
    try {
      await deleteInlineContact();
    } catch (err) {
      alert(err.message || "Erro ao excluir contato");
    }
  });

  els.inlineContactNameInput.addEventListener("keydown", async (e) => {
    if (e.key === "Escape") {
      setContactEditor(false);
      return;
    }
    if (e.key !== "Enter") return;
    e.preventDefault();
    try {
      await saveInlineContact();
    } catch (err) {
      alert(err.message || "Erro ao salvar contato");
    }
  });
}

function startPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async () => {
    try {
      await loadChats();
      if (state.active) await loadActiveHistory();
    } catch {
      // polling silencioso
    }
  }, 1000);
}

(async function init() {
  wire();
  await loadChats();
  renderMessages();
  startPolling();
})();

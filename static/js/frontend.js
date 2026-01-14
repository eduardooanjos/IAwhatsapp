let chatAtual = null;

// caches anti-flicker
let chatsCacheKey = "";
let chatsStatusCache = {};        // { numero: enabled }
let lastCountByChat = {};         // { numero: int } quantidade de "mensagens" renderizadas
let isRefreshing = false;

// =====================
// HELPERS
// =====================
function appendMsg(box, msg) {
  if (msg.cliente) {
    const c = document.createElement("div");
    c.className = "msg cliente";
    c.textContent = msg.cliente;
    box.appendChild(c);
  }
  if (msg.ia) {
    const i = document.createElement("div");
    i.className = "msg ia";
    i.textContent = msg.ia;
    box.appendChild(i);
  }
}

function nearBottom(el, px = 140) {
  return (el.scrollHeight - (el.scrollTop + el.clientHeight)) < px;
}

// =====================
// LOAD CHATS (sem flicker)
// =====================
async function carregarChats() {
  const res = await fetch("/api/chats");
  const chats = await res.json();

  const key = chats.join("|");
  if (key === chatsCacheKey) {
    // lista não mudou: apenas atualiza o "active" visual sem recriar tudo
    const items = document.querySelectorAll("#lista li.chat");
    items.forEach(li => {
      const numero = li.getAttribute("data-numero");
      li.classList.toggle("active", numero === chatAtual);
    });
    return;
  }

  chatsCacheKey = key;

  const lista = document.getElementById("lista");
  lista.innerHTML = "";

  // quando a lista muda, buscamos status e desenhamos
  for (const numero of chats) {
    const stRes = await fetch(`/api/chat_status/${numero}`);
    const st = await stRes.json(); // { enabled: true/false }
    chatsStatusCache[numero] = !!st.enabled;

    const li = document.createElement("li");
    li.className = "chat" + (chatAtual === numero ? " active" : "");
    li.setAttribute("data-numero", numero);

    const left = document.createElement("div");
    left.className = "chat-left";

    const title = document.createElement("div");
    title.textContent = numero;

    const pill = document.createElement("div");
    pill.className = "pill " + (st.enabled ? "on" : "off");
    pill.textContent = st.enabled ? "IA ativa" : "IA desativada";

    left.appendChild(title);
    left.appendChild(pill);

    const btn = document.createElement("button");
    btn.className = "secondary";
    btn.textContent = st.enabled ? "Desativar" : "Ativar";

    btn.onclick = async (ev) => {
      ev.stopPropagation();

      const novo = !chatsStatusCache[numero];
      await fetch(`/api/chat_status/${numero}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: novo })
      });

      chatsStatusCache[numero] = novo;

      // atualiza pill e botão sem recriar a lista toda
      pill.className = "pill " + (novo ? "on" : "off");
      pill.textContent = novo ? "IA ativa" : "IA desativada";
      btn.textContent = novo ? "Desativar" : "Ativar";

      // se for chat atual, atualiza o toggle do topo
      if (chatAtual === numero) {
        await carregarStatusChat(numero, /*useCache*/ true);
      }
    };

    li.onclick = () => abrirChat(numero);

    li.appendChild(left);
    li.appendChild(btn);
    lista.appendChild(li);
  }
}

// =====================
// CHAT STATUS (toggle IA) — sem flicker
// =====================
async function carregarStatusChat(numero, useCache = false) {
  let enabled;

  if (useCache && (numero in chatsStatusCache)) {
    enabled = chatsStatusCache[numero];
  } else {
    const res = await fetch(`/api/chat_status/${numero}`);
    const st = await res.json();
    enabled = !!st.enabled;
    chatsStatusCache[numero] = enabled;
  }

  const toggle = document.getElementById("toggleIa");
  const label = document.getElementById("toggleLabel");

  toggle.disabled = false;
  toggle.checked = enabled;

  label.textContent = enabled ? "IA ativa" : "IA desativada";
  label.className = "pill " + (enabled ? "on" : "off");
}

async function toggleIaChat() {
  if (!chatAtual) return;

  const toggle = document.getElementById("toggleIa");
  const enabled = toggle.checked;

  await fetch(`/api/chat_status/${chatAtual}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled })
  });

  chatsStatusCache[chatAtual] = enabled;
  await carregarStatusChat(chatAtual, true);
}

// =====================
// OPEN CHAT (render inicial, sem piscar depois)
// =====================
async function abrirChat(numero) {
  chatAtual = numero;

  document.getElementById("titulo").textContent = `Chat ${numero}`;
  document.getElementById("btnLimpar").disabled = false;

  await carregarStatusChat(numero);

  const res = await fetch(`/api/historico/${numero}`);
  const mensagens = await res.json();

  const box = document.getElementById("msgs");
  box.innerHTML = "";

  mensagens.forEach(msg => appendMsg(box, msg));

  box.scrollTop = box.scrollHeight;
  lastCountByChat[numero] = mensagens.length;

  // atualiza visual active sem recriar lista
  const items = document.querySelectorAll("#lista li.chat");
  items.forEach(li => {
    const n = li.getAttribute("data-numero");
    li.classList.toggle("active", n === chatAtual);
  });
}

// =====================
// UPDATE CHAT (só adiciona novas mensagens)
// =====================
async function atualizarChatSeMudou() {
  if (!chatAtual) return;

  const res = await fetch(`/api/historico/${chatAtual}`);
  const mensagens = await res.json();

  const prevCount = lastCountByChat[chatAtual] ?? 0;
  if (mensagens.length === prevCount) return; // nada novo

  const box = document.getElementById("msgs");
  const shouldScroll = nearBottom(box);

  const novas = mensagens.slice(prevCount);
  novas.forEach(msg => appendMsg(box, msg));

  lastCountByChat[chatAtual] = mensagens.length;

  if (shouldScroll) box.scrollTop = box.scrollHeight;
}

// =====================
// CLEAR CHAT
// =====================
async function limpar() {
  if (!chatAtual) return;

  await fetch(`/api/clear/${chatAtual}`, { method: "POST" });

  // limpa caches do chat
  delete lastCountByChat[chatAtual];
  delete chatsStatusCache[chatAtual];

  chatAtual = null;

  document.getElementById("msgs").innerHTML = "";
  document.getElementById("titulo").textContent = "Selecione um chat";
  document.getElementById("btnLimpar").disabled = true;

  const toggle = document.getElementById("toggleIa");
  const label = document.getElementById("toggleLabel");
  toggle.disabled = true;
  toggle.checked = true;
  label.textContent = "IA ativa";
  label.className = "pill on";

  // força redesenhar lista (já que removemos chat)
  chatsCacheKey = "";
  await carregarChats();
}

// =====================
// CONFIG (UI)
// =====================
async function carregarConfig() {
  const res = await fetch("/api/config");
  const cfg = await res.json();

  document.getElementById("cfg_sys").value = cfg.sys || "";
  document.getElementById("cfg_kb").value = cfg.kb_text || "";
  document.getElementById("cfg_sinais").value = cfg.sinais_text || "";
  document.getElementById("cfg_mem_prompt").value = cfg.mem_prompt || "";
  document.getElementById("cfg_out_rules").value = cfg.out_rules || "";

  const st = document.getElementById("statusSave");
  if (st) st.textContent = "";
}

async function salvarConfig() {
  const payload = {
    sys: document.getElementById("cfg_sys").value,
    kb_text: document.getElementById("cfg_kb").value,
    sinais_text: document.getElementById("cfg_sinais").value,
    mem_prompt: document.getElementById("cfg_mem_prompt").value,
    out_rules: document.getElementById("cfg_out_rules").value
  };

  const res = await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  const data = await res.json();
  const st = document.getElementById("statusSave");
  if (st) st.textContent = data.ok ? "✅ Salvo!" : "❌ Erro ao salvar";
}

carregarConfig();

// =====================
// (opcional) compatibilidade com /api/instrucoes antigo
// =====================
async function salvarInstrucao() { await salvarConfig(); }
async function carregarInstrucao() { await carregarConfig(); }

// =====================
// AUTO REFRESH (sem flicker)
// =====================
setInterval(async () => {
  if (isRefreshing) return;
  isRefreshing = true;

  try {
    await carregarChats();         // só redesenha se mudou
    await atualizarChatSeMudou();  // só adiciona novas mensagens
  } finally {
    isRefreshing = false;
  }
}, 2000);

// =====================
// INIT
// =====================
carregarChats();

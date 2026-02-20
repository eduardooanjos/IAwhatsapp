const els = {
  saveBtn: document.getElementById("saveBtn"),
  statusText: document.getElementById("statusText"),
  modelName: document.getElementById("modelName"),
  responseDelaySeconds: document.getElementById("responseDelaySeconds"),
  timezone: document.getElementById("timezone"),
  businessHoursPolicy: document.getElementById("businessHoursPolicy"),
  outsideHoursMessage: document.getElementById("outsideHoursMessage"),
  handoffContact: document.getElementById("handoffContact"),
  systemPrompt: document.getElementById("systemPrompt"),
  rules: document.getElementById("rules"),
  blockedTopics: document.getElementById("blockedTopics"),
  storeName: document.getElementById("storeName"),
  storeCnpj: document.getElementById("storeCnpj"),
  storeAddress: document.getElementById("storeAddress"),
  storeHours: document.getElementById("storeHours"),
  storePhone: document.getElementById("storePhone"),
  storeWhatsapp: document.getElementById("storeWhatsapp"),
  storeEmail: document.getElementById("storeEmail"),
  storeInstagram: document.getElementById("storeInstagram"),
  storeSite: document.getElementById("storeSite"),
  storeDelivery: document.getElementById("storeDelivery"),
  storePickup: document.getElementById("storePickup"),
  storePayments: document.getElementById("storePayments"),
  storeReturnsPolicy: document.getElementById("storeReturnsPolicy"),
};

function linesToList(value) {
  return String(value || "")
    .split("\n")
    .map((v) => v.trim())
    .filter(Boolean);
}

function listToLines(values) {
  return Array.isArray(values) ? values.join("\n") : "";
}

function setStatus(msg, isError = false) {
  els.statusText.textContent = msg;
  els.statusText.classList.toggle("error", isError);
}

async function apiGet(url) {
  const r = await fetch(url);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `GET ${url} falhou`);
  return data;
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

function fillForm(config) {
  const store = config.store || {};
  const ai = config.ai_settings || {};

  els.modelName.value = ((config.model || {}).name || "").trim();
  els.responseDelaySeconds.value = Number(ai.response_delay_seconds || 0);
  els.timezone.value = ai.timezone || "";
  els.businessHoursPolicy.value = ai.business_hours_policy || "";
  els.outsideHoursMessage.value = ai.outside_hours_message || "";
  els.handoffContact.value = ai.handoff_contact || "";
  els.systemPrompt.value = config.system_prompt || "";
  els.rules.value = listToLines(config.rules);
  els.blockedTopics.value = listToLines(ai.blocked_topics);

  els.storeName.value = store.name || "";
  els.storeCnpj.value = store.cnpj || "";
  els.storeAddress.value = store.address || "";
  els.storeHours.value = store.hours || "";
  els.storePhone.value = store.contact_phone || "";
  els.storeWhatsapp.value = store.contact_whatsapp || "";
  els.storeEmail.value = store.contact_email || "";
  els.storeInstagram.value = store.instagram || "";
  els.storeSite.value = store.site || "";
  els.storeDelivery.value = store.delivery || "";
  els.storePickup.value = store.pickup || "";
  els.storePayments.value = store.payments || "";
  els.storeReturnsPolicy.value = store.returns_policy || "";
}

function collectForm() {
  const responseDelay = Number(els.responseDelaySeconds.value || 0);
  const safeDelay = Number.isFinite(responseDelay)
    ? Math.max(0, Math.min(120, Math.floor(responseDelay)))
    : 0;

  return {
    model: {
      name: (els.modelName.value || "").trim(),
    },
    system_prompt: els.systemPrompt.value || "",
    rules: linesToList(els.rules.value),
    ai_settings: {
      response_delay_seconds: safeDelay,
      timezone: (els.timezone.value || "").trim(),
      business_hours_policy: (els.businessHoursPolicy.value || "").trim(),
      outside_hours_message: (els.outsideHoursMessage.value || "").trim(),
      handoff_contact: (els.handoffContact.value || "").trim(),
      blocked_topics: linesToList(els.blockedTopics.value),
    },
    store: {
      name: (els.storeName.value || "").trim(),
      cnpj: (els.storeCnpj.value || "").trim(),
      address: (els.storeAddress.value || "").trim(),
      hours: (els.storeHours.value || "").trim(),
      contact_phone: (els.storePhone.value || "").trim(),
      contact_whatsapp: (els.storeWhatsapp.value || "").trim(),
      contact_email: (els.storeEmail.value || "").trim(),
      instagram: (els.storeInstagram.value || "").trim(),
      site: (els.storeSite.value || "").trim(),
      delivery: (els.storeDelivery.value || "").trim(),
      pickup: (els.storePickup.value || "").trim(),
      payments: (els.storePayments.value || "").trim(),
      returns_policy: (els.storeReturnsPolicy.value || "").trim(),
    },
  };
}

async function loadConfig() {
  setStatus("Carregando configuracoes...");
  const data = await apiGet("/api/config/full");
  fillForm(data.config || {});
  setStatus("Configuracoes carregadas.");
}

async function saveConfig() {
  els.saveBtn.disabled = true;
  setStatus("Salvando configuracoes...");
  try {
    const config = collectForm();
    await apiPost("/api/config/full", { config });
    setStatus("Configuracoes salvas com sucesso.");
  } catch (err) {
    setStatus(err.message || "Falha ao salvar configuracoes.", true);
  } finally {
    els.saveBtn.disabled = false;
  }
}

function wire() {
  els.saveBtn.addEventListener("click", saveConfig);
}

(async function init() {
  wire();
  try {
    await loadConfig();
  } catch (err) {
    setStatus(err.message || "Falha ao carregar configuracoes.", true);
  }
})();

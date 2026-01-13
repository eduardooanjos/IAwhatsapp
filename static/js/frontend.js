let chatAtual = null;

// =====================
// LOAD CHATS
// =====================
async function carregarChats() {
    const res = await fetch("/api/chats");
    const chats = await res.json();

    const lista = document.getElementById("lista"); // ✔ ID correto
    lista.innerHTML = "";

    chats.forEach(numero => {
        const li = document.createElement("li");
        li.textContent = numero;
        li.onclick = () => abrirChat(numero);
        lista.appendChild(li);
    });
}

// =====================
// OPEN CHAT
// =====================
async function abrirChat(numero) {
    chatAtual = numero;

    document.getElementById("titulo").textContent = `Chat ${numero}`;

    const res = await fetch(`/api/historico/${numero}`);
    const mensagens = await res.json();

    const box = document.getElementById("msgs"); // ✔ ID correto
    box.innerHTML = "";

    mensagens.forEach(msg => {
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
    });

    box.scrollTop = box.scrollHeight;
}

// =====================
// CLEAR CHAT
// =====================
async function limpar() { // ✔ nome correto
    if (!chatAtual) return;

    await fetch(`/api/clear/${chatAtual}`, { method: "POST" });

    chatAtual = null;
    document.getElementById("msgs").innerHTML = "";
    document.getElementById("titulo").textContent = "Selecione um chat";
    carregarChats();
}

// =====================
// INTRUÇÕES
// =====================

async function salvarInstrucao() {
    const texto = document.getElementById("instrucao").value;

    await fetch("/api/instrucoes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ texto })
    });

    alert("Instruções salvas");
}

async function carregarInstrucao() {
    const res = await fetch("/api/instrucoes");
    const data = await res.json();

    document.getElementById("instrucao").value = data.texto || "";
}

carregarInstrucao();


// =====================
// AUTO REFRESH
// =====================
setInterval(() => {
    if (chatAtual) abrirChat(chatAtual);
    carregarChats();
}, 2000);

// =====================
// INIT
// =====================
carregarChats();

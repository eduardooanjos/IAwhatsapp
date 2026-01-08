let chatAtual = null;

function carregarChats() {
    fetch("/api/chats")
        .then(r => r.json())
        .then(chats => {
            const lista = document.getElementById("lista");
            lista.innerHTML = "";

            chats.forEach(n => {
                const li = document.createElement("li");
                li.innerText = n;
                li.onclick = () => carregarHistorico(n);
                lista.appendChild(li);
            });
        });
}

function carregarHistorico(numero) {
    chatAtual = numero;
    document.getElementById("titulo").innerText = "Chat: " + numero;
    atualizarHistorico();
}

function atualizarHistorico() {
    if (!chatAtual) return;

    fetch("/api/historico/" + chatAtual)
        .then(r => r.json())
        .then(msgs => {
            const div = document.getElementById("msgs");
            div.innerHTML = "";

            msgs.forEach(m => {
                const c = document.createElement("div");
                c.className = "msg cliente";
                c.innerText = "Cliente: " + m.cliente;

                const i = document.createElement("div");
                i.className = "msg ia";
                i.innerText = "IA: " + m.ia;

                div.appendChild(c);
                div.appendChild(i);
            });

            div.scrollTop = div.scrollHeight;
        });
}

// 🔁 atualiza automaticamente
setInterval(() => {
    carregarChats();
    atualizarHistorico();
}, 1500);

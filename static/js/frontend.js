let chatAtual = null;

function carregarChats() {
    fetch("/api/chats")
        .then(res => res.json())
        .then(chats => {
            const lista = document.getElementById("lista");
            lista.innerHTML = "";

            chats.forEach(numero => {
                const li = document.createElement("li");
                li.textContent = numero;
                li.onclick = () => carregarHistorico(numero);
                lista.appendChild(li);
            });
        });
}

function carregarHistorico(numero) {
    chatAtual = numero;
    document.getElementById("titulo").innerText = "Chat: " + numero;

    fetch("/api/historico/" + numero)
        .then(res => res.json())
        .then(msgs => {
            const div = document.getElementById("msgs");
            div.innerHTML = "";

            msgs.forEach(m => {
                if (m.cliente) {
                    const c = document.createElement("div");
                    c.className = "msg cliente";
                    c.innerText = "Cliente: " + m.cliente;
                    div.appendChild(c);
                }

                if (m.ia) {
                    const i = document.createElement("div");
                    i.className = "msg ia";
                    i.innerText = "IA: " + m.ia;
                    div.appendChild(i);
                }
            });

            div.scrollTop = div.scrollHeight;
        });
}

function limpar() {
    if (!chatAtual) return;

    fetch("/api/clear/" + chatAtual, { method: "POST" })
        .then(() => {
            document.getElementById("msgs").innerHTML = "";
            document.getElementById("titulo").innerText = "Selecione um chat";
            chatAtual = null;
            carregarChats();
        });
}

carregarChats();
setInterval(carregarChats, 5000);
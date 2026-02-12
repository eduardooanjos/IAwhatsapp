🤖 WhatsApp AI Assistant (Evolution + Gemini + Redis)

Sistema de atendimento automatizado via WhatsApp, utilizando:

📲 Evolution API (integração WhatsApp)

🧠 Google Gemini API (IA)

🗄 Redis (memória + debounce inteligente)

🐍 Flask (Webhook server)

O sistema aguarda 2 minutos após a última mensagem do cliente antes de responder, permitindo que o usuário envie várias mensagens seguidas e a IA responda de forma consolidada.

📌 Arquitetura
Cliente WhatsApp
        ↓
Evolution API
        ↓
Webhook (Flask)
        ↓
Redis (Buffer + Debounce + Histórico)
        ↓
Gemini API (IA)
        ↓
Evolution API (sendText)
        ↓
Cliente

🧠 Como Funciona
🔹 1. Recebimento

O webhook recebe eventos messages.upsert.

🔹 2. Buffer Inteligente

Cada mensagem:

É armazenada no Redis

Reagenda o tempo de resposta para agora + 120 segundos

🔹 3. Debounce

Se o cliente parar de enviar mensagens por 2 minutos:

Todas as mensagens acumuladas são unificadas

A IA gera uma única resposta

A resposta é enviada

📁 Estrutura do Projeto
.
├── webhook.py        # Servidor Flask + Orquestração
├── ai_service.py     # Lógica da IA (Gemini)
├── sender.py         # Envio via Evolution API
├── parser.py         # Extração de número e texto
├── memory.py         # Histórico Redis
├── buffer.py         # Debounce de 2 minutos
├── .env
└── README.md

⚙️ Variáveis de Ambiente
🔹 .env
# Evolution
AUTHENTICATION_API_KEY=
EVOLUTION_API=http://localhost:8080/message/sendText/secundario

# Webhook
WEBHOOK_ENABLED=true

# Redis
CACHE_REDIS_ENABLED=true
CACHE_REDIS_URI=redis://localhost:6379/6
CACHE_REDIS_PREFIX_KEY=evolution

# Gemini
GEMINI_MODEL=gemini-3-flash-preview


⚠ A GEMINI_API_KEY deve estar configurada nas variáveis do sistema Windows.

🐳 Redis (Docker)

Rodando via container:

docker run -d \
  --name redis \
  -p 6379:6379 \
  redis:7

▶️ Executar o Projeto

Instale dependências:

pip install flask redis python-dotenv google-genai requests


Execute:

python webhook.py


Servidor disponível em:

http://localhost:5000/webhook

🧩 Fluxo do Debounce
Exemplo real:

Cliente envia:

Oi
Tudo bem?
Queria saber preço


Sistema:

Armazena tudo

Espera 2 minutos

Envia uma única resposta contextualizada

🛡 Controle de Duplicidade

A Evolution pode reenviar eventos múltiplas vezes.
O sistema:

Usa message.key.id

Armazena em Redis com TTL

Ignora mensagens duplicadas

👨‍💻 Autor

Eduardo Henrique
Engenharia de Computação – UTFPR
Foco em IA, backend e sistemas distribuídos.

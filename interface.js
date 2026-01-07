import express from "express";
import { createClient } from "redis";

const app = express();
app.use(express.json());

// Redis
const redis = createClient({
  url: "redis://localhost:6379"
});

redis.connect();

// ========================
// LISTAR CHATS ATIVOS
// ========================
app.get("/api/chats", async (req, res) => {
  const chats = await redis.sMembers("chats_ativos");
  res.json(chats);
});

// ========================
// HISTÓRICO DE UM CHAT
// ========================
app.get("/api/historico/:numero", async (req, res) => {
  const { numero } = req.params;

  const msgIds = await redis.lRange(numero, 0, -1);

  const mensagens = [];
  for (const id of msgIds) {
    const msg = await redis.hGetAll(`msg:${id}`);
    mensagens.push(msg);
  }

  res.json(mensagens);
});

// ========================
app.listen(3000, () => {
  console.log("Servidor rodando em http://localhost:3000");
});

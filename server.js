const express = require("express");
const http = require("http");
const path = require("path");
const { Server } = require("socket.io");

const app = express();
const server = http.createServer(app);
const io = new Server(server);

const PORT = process.env.PORT || 3000;

app.use("/static", express.static(path.join(__dirname, "static")));
app.use(express.static(path.join(__dirname, "public")));

const ROLE_CONFIG = {
  scholar: {
    name: "學霸",
    counts: { delete2: 3, reset: 1, occupy: 0, freeze: 0, bomb: 0 },
    seesAllTypes: false
  },
  landlord: {
    name: "霸道地主",
    counts: { delete2: 0, reset: 1, occupy: 1, freeze: 0, bomb: 0 },
    seesAllTypes: false
  },
  prophet: {
    name: "先知",
    counts: { delete2: 0, reset: 1, occupy: 0, freeze: 0, bomb: 0 },
    seesAllTypes: true
  },
  timeMaster: {
    name: "時間大師",
    counts: { delete2: 0, reset: 1, occupy: 0, freeze: 1, bomb: 0 },
    seesAllTypes: false
  },
  bombMan: {
    name: "炸彈怪客",
    counts: { delete2: 0, reset: 1, occupy: 0, freeze: 0, bomb: 1 },
    seesAllTypes: false
  }
};

const QUESTIONS = {
  normal: [
    { type: "國文", q: "「望梅止渴」主要是在形容什麼？", options: ["真正解渴", "以想像安慰自己", "梅子很好吃", "口渴不能忍"], answer: 1, explain: "是用想像來暫時安慰自己。" },
    { type: "數學", q: "15 + 27 = ?", options: ["40", "41", "42", "43"], answer: 2, explain: "15 + 27 = 42。" },
    { type: "地理", q: "台灣的首都是哪裡？", options: ["台中", "高雄", "台北", "台南"], answer: 2, explain: "台灣首都為台北。" },
    { type: "科學", q: "地球繞著哪一個天體運行？", options: ["月亮", "火星", "太陽", "木星"], answer: 2, explain: "地球繞太陽公轉。" }
  ],
  hard: [
    { type: "歷史", q: "鄭成功主要驅逐哪一個國家的勢力，收復台灣？", options: ["英國", "西班牙", "葡萄牙", "荷蘭"], answer: 3, explain: "鄭成功驅逐荷蘭勢力。" },
    { type: "科學", q: "水的化學式為何？", options: ["CO2", "H2O", "O2", "NaCl"], answer: 1, explain: "水的化學式是 H2O。" },
    { type: "地理", q: "世界上面積最大的海洋是？", options: ["大西洋", "印度洋", "太平洋", "北冰洋"], answer: 2, explain: "太平洋最大。" }
  ],
  super: [
    { type: "數學", q: "三角形兩角為 35 度與 65 度，第三角為？", options: ["70 度", "75 度", "80 度", "90 度"], answer: 2, explain: "180 - 35 - 65 = 80。" },
    { type: "邏輯", q: "所有 A 都是 B，所有 B 都是 C，則何者正確？", options: ["所有 C 都是 A", "所有 A 都是 C", "A 和 C 無關", "所有 B 都是 A"], answer: 1, explain: "由傳遞性可知所有 A 都是 C。" },
    { type: "歷史", q: "清朝最後一位皇帝是？", options: ["康熙", "乾隆", "溥儀", "道光"], answer: 2, explain: "最後一位皇帝是溥儀。" }
  ]
};
QUESTIONS.mix = [...QUESTIONS.normal, ...QUESTIONS.hard, ...QUESTIONS.super];

const rooms = new Map();

function nowText() {
  const d = new Date();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `[${hh}:${mm}]`;
}

function addLog(room, msg) {
  room.logs.push(`${nowText()} ${msg}`);
  room.logs = room.logs.slice(-80);
}

function createBoard(size) {
  const types = ["國文", "數學", "歷史", "地理", "科學", "邏輯"];
  return Array.from({ length: size * size }, (_, index) => ({
    index,
    type: types[index % types.length],
    owner: null,
    status: "normal"
  }));
}

function getStartPositions(playerCount, size) {
  const positions = [0, size - 1, size * (size - 1), size * size - 1];
  return positions.slice(0, playerCount);
}

function getNeighbors(index, size) {
  const row = Math.floor(index / size);
  const col = index % size;
  const result = [];
  if (row > 0) result.push(index - size);
  if (row < size - 1) result.push(index + size);
  if (col > 0) result.push(index - 1);
  if (col < size - 1) result.push(index + 1);
  return result;
}

function getMovableIndexes(room, player) {
  if (!player || player.ended) return [];
  return getNeighbors(player.position, room.mapSize).filter((i) => {
    const tile = room.board[i];
    if (!tile) return false;
    if (tile.status === "blocked") return false;
    if (tile.owner && tile.owner !== player.id) return false;
    if (tile.owner === player.id) return false;
    return true;
  });
}

function recomputeScores(room) {
  room.players.forEach((p) => { p.score = 0; });
  room.board.forEach((tile) => {
    if (tile.owner) {
      const p = room.players.find((x) => x.id === tile.owner);
      if (p) p.score += 1;
    }
  });
}

function updateEndedPlayers(room) {
  for (const player of room.players) {
    if (player.ended) {
      player.status = "已結束";
      continue;
    }
    if (player.frozenUntil && Date.now() < player.frozenUntil) {
      player.status = "凍結中";
      continue;
    }
    const movable = getMovableIndexes(room, player);
    if (movable.length === 0) {
      player.ended = true;
      player.status = "已結束";
      addLog(room, `${player.nickname} 已無法移動，結束遊戲`);
    } else {
      player.status = "進行中";
    }
  }
}

function maybeFinishGame(room) {
  updateEndedPlayers(room);
  if (!room.finished && room.started && room.players.every((p) => p.ended)) {
    room.finished = true;
    recomputeScores(room);
    addLog(room, "全部玩家已結束，進行最終結算");
  }
}

function getQuestionForTile(room, tileIndex) {
  const tile = room.board[tileIndex];
  const pool = QUESTIONS[room.mode] || QUESTIONS.mix;
  const sameType = pool.filter((q) => q.type === tile.type);
  const source = sameType.length ? sameType : pool;
  return JSON.parse(JSON.stringify(source[Math.floor(Math.random() * source.length)]));
}

function publicStateForSocket(room, socketId) {
  const self = room.players.find((p) => p.socketId === socketId) || null;
  const board = room.board.map((tile) => ({
    ...tile,
    visibleType: self?.seesAllTypes ? tile.type : "?"
  }));

  return {
    roomNo: room.roomNo,
    mapSize: room.mapSize,
    playerLimit: room.playerLimit,
    mode: room.mode,
    started: room.started,
    finished: room.finished,
    board,
    players: room.players.map((p) => ({
      id: p.id,
      nickname: p.nickname,
      roleId: p.roleId,
      roleName: p.roleName,
      position: p.position,
      score: p.score,
      status: p.status,
      ended: p.ended,
      isSelf: p.socketId === socketId,
      counts: p.socketId === socketId ? p.counts : undefined
    })),
    logs: room.logs
  };
}

function emitRoom(room) {
  for (const player of room.players) {
    io.to(player.socketId).emit("room_state", publicStateForSocket(room, player.socketId));
  }
}

function createRoom(roomNo, mapSize, playerLimit, mode) {
  return {
    roomNo,
    mapSize,
    playerLimit,
    mode,
    started: false,
    finished: false,
    board: createBoard(mapSize),
    players: [],
    logs: []
  };
}

function joinRoom(socket, payload) {
  const roomNo = String(payload.roomNo || "").trim();
  const nickname = String(payload.nickname || "").trim() || "玩家";
  const roleId = payload.roleId;
  const mapSize = Number(payload.mapSize || 5);
  const playerLimit = Number(payload.playerLimit || 2);
  const mode = payload.mode || "mix";

  if (!ROLE_CONFIG[roleId]) {
    socket.emit("join_error", "角色不存在");
    return;
  }

  let room = rooms.get(roomNo);
  if (!room) {
    room = createRoom(roomNo, mapSize, playerLimit, mode);
    rooms.set(roomNo, room);
  }

  if (room.started) {
    socket.emit("join_error", "遊戲已開始，無法加入");
    return;
  }

  if (room.players.length >= room.playerLimit) {
    socket.emit("join_error", "房間已滿");
    return;
  }

  if (room.players.some((p) => p.roleId === roleId)) {
    socket.emit("join_error", "這個角色已被選走");
    return;
  }

  const playerId = `p${room.players.length + 1}`;
  const role = ROLE_CONFIG[roleId];

  room.players.push({
    id: playerId,
    socketId: socket.id,
    nickname,
    roleId,
    roleName: role.name,
    position: -1,
    score: 0,
    status: "等待中",
    ended: false,
    counts: JSON.parse(JSON.stringify(role.counts)),
    seesAllTypes: role.seesAllTypes,
    frozenUntil: 0,
    pendingQuestion: null,
    pendingTileIndex: null,
    pendingExpireAt: 0
  });

  socket.join(roomNo);
  socket.data.roomNo = roomNo;
  socket.data.playerId = playerId;

  addLog(room, `${nickname} 加入房間，角色：${role.name}`);

  if (room.players.length === room.playerLimit) {
    const starts = getStartPositions(room.playerLimit, room.mapSize);
    room.players.forEach((p, idx) => {
      p.position = starts[idx];
      p.status = "進行中";
      const tile = room.board[p.position];
      tile.owner = p.id;
      tile.status = "owned";
    });
    recomputeScores(room);
    room.started = true;
    addLog(room, "人數到齊，遊戲開始");
    updateEndedPlayers(room);
  }

  emitRoom(room);
}

function startQuestion(socket, tileIndex) {
  const room = rooms.get(socket.data.roomNo);
  if (!room || !room.started || room.finished) return;

  const player = room.players.find((p) => p.id === socket.data.playerId);
  if (!player || player.ended) return;

  const movable = getMovableIndexes(room, player);
  if (!movable.includes(tileIndex)) {
    socket.emit("action_error", "只能選上下左右鄰近且可走的格子");
    return;
  }

  player.pendingTileIndex = tileIndex;
  player.pendingQuestion = getQuestionForTile(room, tileIndex);
  player.pendingExpireAt = Date.now() + 15000;

  socket.emit("question_started", {
    tileIndex,
    question: player.pendingQuestion,
    expireAt: player.pendingExpireAt
  });

  addLog(room, `${player.nickname} 開始挑戰格子 #${tileIndex + 1}`);
  emitRoom(room);
}

function answerQuestion(socket, optionIndex) {
  const room = rooms.get(socket.data.roomNo);
  if (!room || room.finished) return;

  const player = room.players.find((p) => p.id === socket.data.playerId);
  if (!player || player.ended || !player.pendingQuestion) return;

  const tileIndex = player.pendingTileIndex;
  const tile = room.board[tileIndex];
  const question = player.pendingQuestion;

  const timeout = Date.now() > player.pendingExpireAt;
  const correct = !timeout && Number(optionIndex) === Number(question.answer);

  if (correct) {
    tile.status = "owned";
    tile.owner = player.id;
    player.position = tileIndex;
    addLog(room, `${player.nickname} 答對，占領格子 #${tileIndex + 1}`);
  } else {
    tile.status = "blocked";
    tile.owner = null;
    addLog(room, `${player.nickname} 答錯，格子 #${tileIndex + 1} 變灰`);
  }

  player.pendingQuestion = null;
  player.pendingTileIndex = null;
  player.pendingExpireAt = 0;

  recomputeScores(room);
  maybeFinishGame(room);

  socket.emit("question_result", {
    correct,
    timeout,
    answer: question.answer,
    explain: question.explain,
    tileIndex
  });

  emitRoom(room);
}

function disconnectRoom(socket) {
  const roomNo = socket.data.roomNo;
  const playerId = socket.data.playerId;
  if (!roomNo || !playerId) return;

  const room = rooms.get(roomNo);
  if (!room) return;

  const player = room.players.find((p) => p.id === playerId);
  if (!player) return;

  addLog(room, `${player.nickname} 離線`);

  if (!room.started) {
    room.players = room.players.filter((p) => p.id !== playerId);
    if (room.players.length === 0) {
      rooms.delete(roomNo);
      return;
    }
  } else {
    player.ended = true;
    player.status = "離線";
    maybeFinishGame(room);
  }

  emitRoom(room);
}

io.on("connection", (socket) => {
  socket.on("join_room", (payload) => joinRoom(socket, payload));
  socket.on("start_question", ({ tileIndex }) => startQuestion(socket, Number(tileIndex)));
  socket.on("answer_question", ({ optionIndex }) => answerQuestion(socket, Number(optionIndex)));
  socket.on("disconnect", () => disconnectRoom(socket));
});

app.get("*", (_req, res) => {
  res.sendFile(path.join(__dirname, "public", "index.html"));
});

server.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
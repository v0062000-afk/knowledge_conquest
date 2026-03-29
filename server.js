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
  room.logs = room.logs.slice(-120);
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
  if (player.frozenUntil && Date.now() < player.frozenUntil) return [];
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
  if (!room.finished && room.started && room.players.length >= 2 && room.players.every((p) => p.ended)) {
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

function getRoomPlayer(socket) {
  const room = rooms.get(socket.data.roomNo);
  if (!room) return { room: null, player: null };
  const player = room.players.find((p) => p.id === socket.data.playerId);
  return { room, player };
}

function serializeRoomFor(socketId, room) {
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
    ownerId: room.ownerId,
    countdownEndsAt: room.countdownEndsAt || null,
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
      ready: !!p.ready,
      isSelf: p.socketId === socketId,
      counts: p.socketId === socketId ? p.counts : undefined,
      frozenUntil: p.socketId === socketId ? p.frozenUntil : undefined
    })),
    logs: room.logs
  };
}

function emitRoom(room) {
  for (const p of room.players) {
    io.to(p.socketId).emit("room_state", serializeRoomFor(p.socketId, room));
  }
}

function cancelCountdown(room, reason = "") {
  if (room.countdownTimer) {
    clearTimeout(room.countdownTimer);
    room.countdownTimer = null;
  }
  room.countdownEndsAt = null;
  if (reason) addLog(room, reason);
}

function maybeStartCountdown(room) {
  if (room.started || room.finished) return;
  if (room.players.length < 2) {
    cancelCountdown(room);
    return;
  }

  const allReady = room.players.every((p) => p.ready);
  if (!allReady) {
    cancelCountdown(room);
    return;
  }

  if (room.countdownTimer) return;

  room.countdownEndsAt = Date.now() + 5000;
  addLog(room, "全部玩家已準備，5 秒後開始");
  room.countdownTimer = setTimeout(() => {
    room.countdownTimer = null;
    room.countdownEndsAt = null;
    startGame(room);
  }, 5000);
}

function startGame(room) {
  room.started = true;
  room.finished = false;
  room.board = createBoard(room.mapSize);

  const starts = getStartPositions(room.players.length, room.mapSize);
  room.players.forEach((p, idx) => {
    p.position = starts[idx];
    p.score = 0;
    p.status = "進行中";
    p.ended = false;
    p.frozenUntil = 0;
    p.pendingQuestion = null;
    p.pendingTileIndex = null;
    p.pendingExpireAt = 0;
    p.removedOptions = [];

    const tile = room.board[p.position];
    tile.owner = p.id;
    tile.status = "owned";
  });

  recomputeScores(room);
  updateEndedPlayers(room);
  addLog(room, "遊戲正式開始");
  emitRoom(room);
}

function createRoom(roomNo, mapSize, playerLimit, mode) {
  return {
    roomNo,
    mapSize,
    playerLimit,
    mode,
    started: false,
    finished: false,
    ownerId: null,
    board: createBoard(mapSize),
    players: [],
    logs: [],
    countdownTimer: null,
    countdownEndsAt: null
  };
}

function joinRoom(socket, payload) {
  const roomNo = String(payload.roomNo || "").trim();
  const nickname = String(payload.nickname || "").trim() || "玩家";
  const roleId = payload.roleId;
  const mapSize = Number(payload.mapSize || 5);
  const playerLimit = Number(payload.playerLimit || 2);
  const mode = payload.mode || "mix";

  if (!roomNo) {
    socket.emit("join_error", "請輸入房號");
    return;
  }

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

  const player = {
    id: playerId,
    socketId: socket.id,
    nickname,
    roleId,
    roleName: role.name,
    position: -1,
    score: 0,
    status: "等待中",
    ended: false,
    ready: false,
    counts: JSON.parse(JSON.stringify(role.counts)),
    seesAllTypes: role.seesAllTypes,
    frozenUntil: 0,
    pendingQuestion: null,
    pendingTileIndex: null,
    pendingExpireAt: 0,
    removedOptions: []
  };

  room.players.push(player);
  if (!room.ownerId) room.ownerId = player.id;

  socket.join(roomNo);
  socket.data.roomNo = roomNo;
  socket.data.playerId = playerId;

  addLog(room, `${nickname} 加入房間，角色：${role.name}${room.ownerId === player.id ? "（房主）" : ""}`);

  cancelCountdown(room, "");
  emitRoom(room);
}

function toggleReady(socket) {
  const { room, player } = getRoomPlayer(socket);
  if (!room || !player || room.started) return;

  player.ready = !player.ready;
  addLog(room, `${player.nickname}${player.ready ? " 已準備" : " 取消準備"}`);

  maybeStartCountdown(room);
  emitRoom(room);
}

function startQuestion(socket, tileIndex) {
  const { room, player } = getRoomPlayer(socket);
  if (!room || !player || !room.started || room.finished) return;
  if (player.ended) return;

  if (player.frozenUntil && Date.now() < player.frozenUntil) {
    socket.emit("action_error", "你目前被凍結中");
    return;
  }

  const movable = getMovableIndexes(room, player);
  if (!movable.includes(tileIndex)) {
    socket.emit("action_error", "只能選上下左右鄰近且可走的格子");
    return;
  }

  player.pendingTileIndex = tileIndex;
  player.pendingQuestion = getQuestionForTile(room, tileIndex);
  player.pendingExpireAt = Date.now() + 15000;
  player.removedOptions = [];

  socket.emit("question_started", {
    tileIndex,
    question: player.pendingQuestion,
    expireAt: player.pendingExpireAt,
    removedOptions: []
  });

  addLog(room, `${player.nickname} 開始挑戰格子 #${tileIndex + 1}`);
  emitRoom(room);
}

function answerQuestion(socket, optionIndex) {
  const { room, player } = getRoomPlayer(socket);
  if (!room || !player || room.finished) return;
  if (!player.pendingQuestion || player.ended) return;

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
  player.removedOptions = [];

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

function useSkill(socket, payload) {
  const { room, player } = getRoomPlayer(socket);
  if (!room || !player || !room.started || room.finished) return;
  if (player.ended) return;

  const skill = payload.skill;
  const targetTileIndex = Number(payload.targetTileIndex);

  if (skill === "delete2") {
    if (player.counts.delete2 <= 0) {
      return socket.emit("action_error", "刪2次數不足");
    }
    if (!player.pendingQuestion) {
      return socket.emit("action_error", "請先開始答題");
    }

    const wrong = player.pendingQuestion.options
      .map((_, i) => i)
      .filter((i) => i !== player.pendingQuestion.answer);

    const removed = wrong.sort(() => Math.random() - 0.5).slice(0, 2);
    player.removedOptions = removed;
    player.counts.delete2 -= 1;

    socket.emit("question_options_removed", { removedOptions: removed });
    addLog(room, `${player.nickname} 使用技能：刪2選項`);
    emitRoom(room);
    return;
  }

  if (skill === "occupy") {
    if (player.counts.occupy <= 0) {
      return socket.emit("action_error", "霸佔次數不足");
    }
    const movable = getMovableIndexes(room, player);
    if (!movable.includes(targetTileIndex)) {
      return socket.emit("action_error", "只能霸佔鄰近可走格子");
    }

    const tile = room.board[targetTileIndex];
    tile.status = "owned";
    tile.owner = player.id;
    player.position = targetTileIndex;
    player.counts.occupy -= 1;

    recomputeScores(room);
    maybeFinishGame(room);
    addLog(room, `${player.nickname} 使用技能：霸佔格子 #${targetTileIndex + 1}`);
    emitRoom(room);
    return;
  }

  if (skill === "bomb") {
    if (player.counts.bomb <= 0) {
      return socket.emit("action_error", "炸彈次數不足");
    }

    if (Number.isNaN(targetTileIndex) || targetTileIndex < 0 || targetTileIndex >= room.board.length) {
      return socket.emit("action_error", "炸彈目標格子無效");
    }

    const occupiedByPlayer = room.players.some((p) => !p.ended && p.position === targetTileIndex);
    if (occupiedByPlayer) {
      return socket.emit("action_error", "不能炸目前有玩家站著的格子");
    }

    const tile = room.board[targetTileIndex];
    tile.status = "blocked";
    tile.owner = null;
    player.counts.bomb -= 1;

    recomputeScores(room);
    maybeFinishGame(room);
    addLog(room, `${player.nickname} 使用技能：炸彈，格子 #${targetTileIndex + 1} 變灰`);
    emitRoom(room);
    return;
  }

  if (skill === "reset") {
    if (player.counts.reset <= 0) {
      return socket.emit("action_error", "重置次數不足");
    }

    if (Number.isNaN(targetTileIndex) || targetTileIndex < 0 || targetTileIndex >= room.board.length) {
      return socket.emit("action_error", "重置目標格子無效");
    }

    const neighborIndexes = getNeighbors(player.position, room.mapSize);
    if (!neighborIndexes.includes(targetTileIndex)) {
      return socket.emit("action_error", "只能重置鄰近的灰色格子");
    }

    const tile = room.board[targetTileIndex];
    if (!tile || tile.status !== "blocked") {
      return socket.emit("action_error", "只能重置鄰近的灰色格子");
    }

    tile.status = "normal";
    tile.owner = null;
    player.counts.reset -= 1;

    recomputeScores(room);
    addLog(room, `${player.nickname} 使用技能：重置灰格 #${targetTileIndex + 1}`);
    emitRoom(room);
    return;
  }

  if (skill === "freeze") {
    if (player.counts.freeze <= 0) {
      return socket.emit("action_error", "凍結次數不足");
    }

    const targets = room.players.filter((p) => p.id !== player.id && !p.ended);
    if (targets.length === 0) {
      return socket.emit("action_error", "目前沒有可凍結的其他玩家");
    }

    const freezeUntil = Date.now() + 5000;
    targets.forEach((target) => {
      target.frozenUntil = freezeUntil;
      target.status = "凍結中";
    });

    player.counts.freeze -= 1;
    addLog(room, `${player.nickname} 使用技能：凍結全部其他玩家 5 秒`);
    emitRoom(room);
    return;
  }
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
    if (room.ownerId === playerId && room.players.length > 0) {
      room.ownerId = room.players[0].id;
      addLog(room, `${room.players[0].nickname} 成為新房主`);
    }
    cancelCountdown(room, "");
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
  socket.on("toggle_ready", () => toggleReady(socket));
  socket.on("start_question", ({ tileIndex }) => startQuestion(socket, Number(tileIndex)));
  socket.on("answer_question", ({ optionIndex }) => answerQuestion(socket, Number(optionIndex)));
  socket.on("use_skill", (payload) => useSkill(socket, payload));
  socket.on("disconnect", () => disconnectRoom(socket));
});

app.get("*", (_req, res) => {
  res.sendFile(path.join(__dirname, "public", "index.html"));
});

server.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

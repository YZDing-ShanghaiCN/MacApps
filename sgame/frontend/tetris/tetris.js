(() => {
  "use strict";

  /* ---------- 常量与配置 ---------- */

  const COLS = 10;
  const ROWS = 20;
  const TILE = 30;
  const BASE_INTERVAL = 800;
  const MIN_INTERVAL = 90;
  const INTERVAL_DECAY = 0.86;
  const DAS_DELAY_MS = 170;
  const DAS_REPEAT_MS = 45;
  const HOLD_REPEAT_MS = 90;
  const CLEAR_FLASH_MS = 220;
  const SCORES = [0, 100, 300, 500, 800];
  const RANK_LIMIT = 10;

  const LS = {
    rank: (mode) => "sgame-tetris-rank-" + mode,
    stats: "sgame-tetris-stats",
    name: "sgame-tetris-name",
    sound: "sgame-tetris-sound",
  };

  const MODES = {
    casual: { label: "休闲", icon: "🌱", startLevel: 1, desc: "从第 1 关开始 · 轻松上手" },
    classic: { label: "经典", icon: "⚡", startLevel: 5, desc: "从第 5 关开始 · 标准速度" },
    expert: { label: "高手", icon: "🔥", startLevel: 10, desc: "从第 10 关开始 · 极速挑战" },
  };

  const SHAPE_BASE = {
    I: ["....", "XXXX", "....", "...."],
    O: ["XX", "XX"],
    T: [".X.", "XXX", "..."],
    S: [".XX", "XX.", "..."],
    Z: ["XX.", ".XX", "..."],
    J: ["X..", "XXX", "..."],
    L: ["..X", "XXX", "..."],
  };

  const COLORS = {
    I: "#00e5e5",
    O: "#f0d000",
    T: "#b14ce8",
    S: "#3ddc5e",
    Z: "#f04a4a",
    J: "#4a7df0",
    L: "#f09a3d",
  };

  function rotateCW(matrix) {
    const n = matrix.length;
    const out = matrix.map((row) => Array.from(row));
    for (let r = 0; r < n; r += 1) {
      for (let c = 0; c < n; c += 1) {
        out[c][n - 1 - r] = matrix[r][c];
      }
    }
    return out;
  }

  const ROTS = {};
  for (const name of Object.keys(SHAPE_BASE)) {
    const states = [SHAPE_BASE[name]];
    let cur = SHAPE_BASE[name];
    for (let i = 0; i < 3; i += 1) {
      cur = rotateCW(cur);
      states.push(cur);
    }
    ROTS[name] = states;
  }

  /* ---------- DOM ---------- */

  const $ = (id) => document.getElementById(id);

  const views = {
    menu: $("menu-view"),
    mode: $("mode-view"),
    game: $("game-view"),
    ranking: $("ranking-view"),
  };
  const rulesDialog = $("rules-dialog");

  const canvas = $("game");
  const ctx = canvas.getContext("2d");
  canvas.width = COLS * TILE;
  canvas.height = ROWS * TILE;

  const holdCanvas = $("hold-panel");
  const holdCtx = holdCanvas.getContext("2d");
  const nextCanvas = $("next-panel");
  const nextCtx = nextCanvas.getContext("2d");
  const canvasWrap = $("canvas-wrap");

  const scoreEl = $("score");
  const bestEl = $("best");
  const levelEl = $("level");
  const linesEl = $("lines");
  const modeLabelEl = $("mode-label");

  const overlayEl = $("overlay");
  const overlayTitleEl = $("overlay-title");
  const overlayDetailEl = $("overlay-detail");
  const overlayNoteEl = $("overlay-note");
  const recordEntryEl = $("record-entry");
  const nameInputEl = $("name-input");
  const overlayPrimaryEl = $("btn-overlay-primary");
  const overlaySecondaryEl = $("btn-overlay-secondary");
  const overlayTertiaryEl = $("btn-overlay-tertiary");

  const statGamesEl = $("stat-games");
  const statBestEl = $("stat-best");
  const statLinesEl = $("stat-lines");

  const rankingListEl = $("ranking-list");
  const rankingEmptyEl = $("ranking-empty");

  /* ---------- 状态 ---------- */

  let board = Array.from({ length: ROWS }, () => new Array(COLS).fill(null));
  let active = null;
  let holdShape = null;
  let canHold = true;
  let nextQueue = [];
  let bag = [];
  let score = 0;
  let lines = 0;
  let level = 1;
  let startLevel = 1;
  let mode = "casual";
  let fallTimer = 0;
  let fallInterval = BASE_INTERVAL;
  let dropScore = 0;
  // idle | ready | playing | paused | clearing | over
  let state = "idle";
  let clearingRows = null;
  let clearTimer = 0;
  let popups = [];

  let stats = Object.assign(
    { games: 0, lines: 0, best: { casual: 0, classic: 0, expert: 0 } },
    loadJSON(LS.stats, {})
  );
  stats.best = Object.assign({ casual: 0, classic: 0, expert: 0 }, stats.best || {});
  let soundOn = localStorage.getItem(LS.sound) !== "0";
  let savedName = localStorage.getItem(LS.name) || "";
  let rankTab = "casual";
  let currentGameBest = 0;

  /* ---------- 本地存储 ---------- */

  function loadJSON(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (err) {
      return fallback;
    }
  }

  function saveJSON(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (err) {
      /* 存储不可用时静默忽略 */
    }
  }

  function loadRank(modeKey) {
    const list = loadJSON(LS.rank(modeKey), []);
    return Array.isArray(list) ? list : [];
  }

  function saveRank(modeKey, list) {
    saveJSON(LS.rank(modeKey), list);
  }

  function saveStats() {
    saveJSON(LS.stats, stats);
  }

  function qualifies(modeKey, value) {
    if (value <= 0) {
      return false;
    }
    const list = loadRank(modeKey);
    if (list.length < RANK_LIMIT) {
      return true;
    }
    return value > list[list.length - 1].score;
  }

  function addRank(modeKey, entry) {
    const list = loadRank(modeKey);
    list.push(entry);
    list.sort((a, b) => b.score - a.score);
    saveRank(modeKey, list.slice(0, RANK_LIMIT));
  }

  /* ---------- 音效 ---------- */

  let audioCtx = null;

  function ensureCtx() {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) {
      return null;
    }
    if (!audioCtx) {
      audioCtx = new AC();
    }
    if (audioCtx.state === "suspended") {
      audioCtx.resume();
    }
    return audioCtx;
  }

  function tone(freq, dur, opts) {
    if (!soundOn) {
      return;
    }
    const ac = ensureCtx();
    if (!ac) {
      return;
    }
    const o = opts || {};
    const t0 = ac.currentTime + (o.delay || 0);
    const osc = ac.createOscillator();
    const gain = ac.createGain();
    osc.type = o.type || "square";
    osc.frequency.setValueAtTime(freq, t0);
    if (o.end) {
      osc.frequency.exponentialRampToValueAtTime(Math.max(o.end, 1), t0 + dur);
    }
    gain.gain.setValueAtTime(o.vol || 0.05, t0);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(gain);
    gain.connect(ac.destination);
    osc.start(t0);
    osc.stop(t0 + dur + 0.03);
  }

  const SFX = {
    move() {
      tone(220, 0.03, { vol: 0.025 });
    },
    rotate() {
      tone(330, 0.05, { vol: 0.035 });
    },
    soft() {
      tone(200, 0.03, { end: 150, vol: 0.02 });
    },
    hard() {
      tone(130, 0.1, { end: 45, vol: 0.06 });
    },
    lock() {
      tone(160, 0.04, { vol: 0.035 });
    },
    hold() {
      tone(280, 0.07, { end: 420, vol: 0.035 });
    },
    clear(n) {
      const notes = [523.25, 659.25, 783.99];
      for (let i = 0; i < n; i += 1) {
        tone(notes[i], 0.09, { type: "triangle", vol: 0.06, delay: i * 0.07 });
      }
    },
    tetris() {
      [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => {
        tone(f, 0.16, { type: "square", vol: 0.05, delay: i * 0.06 });
      });
    },
    levelup() {
      [392, 523.25, 659.25].forEach((f, i) => {
        tone(f, 0.1, { type: "triangle", vol: 0.05, delay: 0.15 + i * 0.08 });
      });
    },
    over() {
      [392, 311, 247, 165].forEach((f, i) => {
        tone(f, 0.22, { type: "sawtooth", vol: 0.04, delay: i * 0.18 });
      });
    },
    record() {
      [523.25, 659.25, 783.99, 1046.5, 1318.5].forEach((f, i) => {
        tone(f, 0.12, { type: "triangle", vol: 0.05, delay: i * 0.09 });
      });
    },
  };

  function updateSoundButtons() {
    $("btn-sound-menu").textContent = soundOn ? "🔊 音效：开" : "🔇 音效：关";
    $("btn-sound-menu").setAttribute("aria-pressed", String(soundOn));
    $("btn-sound-game").textContent = soundOn ? "🔊" : "🔇";
    $("btn-sound-game").setAttribute("aria-pressed", String(soundOn));
  }

  function toggleSound() {
    soundOn = !soundOn;
    localStorage.setItem(LS.sound, soundOn ? "1" : "0");
    updateSoundButtons();
    if (soundOn) {
      ensureCtx();
      SFX.rotate();
    }
  }

  /* ---------- 核心逻辑 ---------- */

  function nextFromBag() {
    if (bag.length === 0) {
      bag = Object.keys(SHAPE_BASE);
      for (let i = bag.length - 1; i > 0; i -= 1) {
        const j = Math.floor(Math.random() * (i + 1));
        const tmp = bag[i];
        bag[i] = bag[j];
        bag[j] = tmp;
      }
    }
    return bag.pop();
  }

  function collides(shape, rot, row, col) {
    const m = ROTS[shape][rot];
    for (let r = 0; r < m.length; r += 1) {
      for (let c = 0; c < m.length; c += 1) {
        if (m[r][c] !== "X") {
          continue;
        }
        const x = col + c;
        const y = row + r;
        if (x < 0 || x >= COLS || y >= ROWS) {
          return true;
        }
        if (y >= 0 && board[y][x]) {
          return true;
        }
      }
    }
    return false;
  }

  function spawn() {
    const shape = nextQueue.shift();
    nextQueue.push(nextFromBag());
    active = {
      shape,
      rot: 0,
      row: -1,
      col: Math.floor((COLS - ROTS[shape][0].length) / 2),
    };
    dropScore = 0;
    renderNext();
    if (collides(active.shape, active.rot, active.row, active.col)) {
      gameOver();
    }
  }

  function dropRow(piece) {
    let row = piece.row;
    while (!collides(piece.shape, piece.rot, row + 1, piece.col)) {
      row += 1;
    }
    return row;
  }

  function moveLeft() {
    if (state !== "playing" || !active) {
      return;
    }
    if (!collides(active.shape, active.rot, active.row, active.col - 1)) {
      active.col -= 1;
      SFX.move();
    }
  }

  function moveRight() {
    if (state !== "playing" || !active) {
      return;
    }
    if (!collides(active.shape, active.rot, active.row, active.col + 1)) {
      active.col += 1;
      SFX.move();
    }
  }

  function rotatePiece(dir) {
    if (state !== "playing" || !active) {
      return;
    }
    const nextRot = (active.rot + dir + 4) % 4;
    const kicks = [0, -1, 1, -2, 2];
    for (const dx of kicks) {
      if (!collides(active.shape, nextRot, active.row, active.col + dx)) {
        active.rot = nextRot;
        active.col += dx;
        SFX.rotate();
        return;
      }
    }
  }

  function holdPiece() {
    if (state !== "playing" || !active || !canHold) {
      return;
    }
    canHold = false;
    const cur = active.shape;
    if (holdShape === null) {
      holdShape = cur;
      spawn();
    } else {
      const swapped = holdShape;
      holdShape = cur;
      active.shape = swapped;
      active.rot = 0;
      active.row = -1;
      active.col = Math.floor((COLS - ROTS[swapped][0].length) / 2);
      dropScore = 0;
      if (collides(active.shape, active.rot, active.row, active.col)) {
        gameOver();
      }
    }
    SFX.hold();
    renderHold();
  }

  function softDropStep(byUser) {
    if (state !== "playing" || !active) {
      return;
    }
    if (!collides(active.shape, active.rot, active.row + 1, active.col)) {
      active.row += 1;
      if (byUser) {
        dropScore += 1;
        SFX.soft();
      }
    } else {
      lockPiece();
    }
  }

  function hardDrop() {
    if (state !== "playing" || !active) {
      return;
    }
    const target = dropRow(active);
    dropScore += (target - active.row) * 2;
    active.row = target;
    SFX.hard();
    shake();
    lockPiece();
  }

  function lockPiece() {
    const m = ROTS[active.shape][active.rot];
    for (let r = 0; r < m.length; r += 1) {
      for (let c = 0; c < m.length; c += 1) {
        if (m[r][c] !== "X") {
          continue;
        }
        const y = active.row + r;
        const x = active.col + c;
        if (y < 0 || y >= ROWS || x < 0 || x >= COLS) {
          continue;
        }
        board[y][x] = COLORS[active.shape];
      }
    }
    score += dropScore;
    active = null;
    canHold = true;
    SFX.lock();
    renderHold();
    updateHud();

    const full = [];
    for (let r = 0; r < ROWS; r += 1) {
      if (board[r].every((cell) => cell !== null)) {
        full.push(r);
      }
    }
    if (full.length > 0) {
      state = "clearing";
      clearingRows = full;
      clearTimer = CLEAR_FLASH_MS;
      shake();
    } else {
      spawn();
    }
  }

  function finishClear() {
    const n = clearingRows.length;
    const topRow = Math.min.apply(null, clearingRows);
    for (const r of clearingRows.slice().sort((a, b) => b - a)) {
      board.splice(r, 1);
    }
    for (let i = 0; i < n; i += 1) {
      board.unshift(new Array(COLS).fill(null));
    }
    const gained = SCORES[n] * level;
    score += gained;
    lines += n;
    const newLevel = startLevel + Math.floor(lines / 10);
    const levelUp = newLevel > level;
    level = newLevel;
    fallInterval = Math.max(MIN_INTERVAL, BASE_INTERVAL * Math.pow(INTERVAL_DECAY, level - 1));
    addPopup(n === 4 ? "TETRIS!" : "+" + gained, topRow, n === 4);
    if (n === 4) {
      SFX.tetris();
    } else {
      SFX.clear(n);
    }
    if (levelUp) {
      SFX.levelup();
      addPopup("关卡 +1", Math.max(topRow - 1, 0), false);
    }
    clearingRows = null;
    state = "playing";
    spawn();
    updateHud();
  }

  function gameOver() {
    state = "over";
    SFX.over();
    stats.games += 1;
    stats.lines += lines;
    const prevBest = stats.best[mode] || 0;
    const isRecord = score > prevBest;
    if (isRecord) {
      stats.best[mode] = score;
      saveStats();
      SFX.record();
    } else {
      saveStats();
    }
    currentGameBest = Math.max(prevBest, score);
    overlayTitleEl.textContent = "GAME OVER";
    overlayDetailEl.textContent = "得分 " + score + " · 关卡 " + level + " · 消行 " + lines;
    overlayNoteEl.textContent = isRecord ? "🎉 新纪录！" : "";
    overlayNoteEl.hidden = !isRecord;
    const inRank = qualifies(mode, score);
    if (inRank) {
      nameInputEl.value = savedName;
      recordEntryEl.hidden = false;
    } else {
      recordEntryEl.hidden = true;
    }
    overlayPrimaryEl.textContent = "↻ 再来一局";
    overlayPrimaryEl.onclick = () => newGame(mode);
    overlaySecondaryEl.textContent = "← 返回菜单";
    overlaySecondaryEl.onclick = leaveToMenu;
    overlayTertiaryEl.hidden = true;
    overlayEl.hidden = false;
    updateHud();
    updateMenuStats();
  }

  function saveCurrentRecord() {
    const name = nameInputEl.value.trim() || "匿名玩家";
    savedName = nameInputEl.value.trim();
    localStorage.setItem(LS.name, savedName);
    addRank(mode, {
      name,
      score,
      level,
      lines,
      ts: Date.now(),
    });
    recordEntryEl.hidden = true;
    overlayNoteEl.textContent = "✅ 成绩已保存到排行榜";
    overlayNoteEl.hidden = false;
    overlaySecondaryEl.textContent = "🏆 查看排行榜";
    overlaySecondaryEl.onclick = () => {
      rankTab = mode;
      syncRankTabs();
      showView("ranking");
    };
  }

  function newGame(modeKey) {
    mode = modeKey;
    startLevel = MODES[modeKey].startLevel;
    board = Array.from({ length: ROWS }, () => new Array(COLS).fill(null));
    score = 0;
    lines = 0;
    level = startLevel;
    fallInterval = Math.max(MIN_INTERVAL, BASE_INTERVAL * Math.pow(INTERVAL_DECAY, level - 1));
    fallTimer = 0;
    dropScore = 0;
    bag = [];
    holdShape = null;
    canHold = true;
    nextQueue = [];
    while (nextQueue.length < 3) {
      nextQueue.push(nextFromBag());
    }
    active = null;
    clearingRows = null;
    clearTimer = 0;
    popups = [];
    currentGameBest = stats.best[mode] || 0;
    spawn();
    state = "ready";
    modeLabelEl.textContent = MODES[modeKey].icon + " " + MODES[modeKey].label + " · 第 " + startLevel + " 关";
    overlayTitleEl.textContent = "准备好了吗？";
    overlayDetailEl.textContent = MODES[modeKey].label + "模式 · 从第 " + startLevel + " 关开始";
    overlayNoteEl.hidden = true;
    recordEntryEl.hidden = true;
    overlayPrimaryEl.textContent = "▶ 开始游戏";
    overlayPrimaryEl.onclick = () => {
      state = "playing";
      overlayEl.hidden = true;
      SFX.rotate();
    };
    overlaySecondaryEl.textContent = "← 返回菜单";
    overlaySecondaryEl.onclick = leaveToMenu;
    overlayTertiaryEl.hidden = true;
    overlayEl.hidden = false;
    updateHud();
    renderHold();
    renderNext();
  }

  function pauseGame() {
    if (state !== "playing") {
      return;
    }
    state = "paused";
    overlayTitleEl.textContent = "已暂停";
    overlayDetailEl.textContent = "得分 " + score + " · 关卡 " + level;
    overlayNoteEl.hidden = true;
    recordEntryEl.hidden = true;
    overlayPrimaryEl.textContent = "▶ 继续游戏";
    overlayPrimaryEl.onclick = () => {
      state = "playing";
      overlayEl.hidden = true;
    };
    overlaySecondaryEl.textContent = "↻ 重新开始";
    overlaySecondaryEl.onclick = () => newGame(mode);
    overlayTertiaryEl.hidden = false;
    overlayTertiaryEl.textContent = "← 返回菜单";
    overlayTertiaryEl.onclick = leaveToMenu;
    overlayEl.hidden = false;
    releaseAllKeys();
  }

  function resumeGame() {
    if (state !== "paused") {
      return;
    }
    state = "playing";
    overlayEl.hidden = true;
  }

  function togglePause() {
    if (state === "playing") {
      pauseGame();
    } else if (state === "paused") {
      resumeGame();
    }
  }

  function leaveToMenu() {
    if (state !== "idle" && state !== "over") {
      const ok = window.confirm("确定退出当前对局吗？本局进度将丢失。");
      if (!ok) {
        return;
      }
    }
    state = "idle";
    active = null;
    showView("menu");
  }

  function updateHud() {
    scoreEl.textContent = String(score);
    bestEl.textContent = String(Math.max(score, currentGameBest));
    levelEl.textContent = String(level);
    linesEl.textContent = String(lines);
  }

  function updateMenuStats() {
    statGamesEl.textContent = String(stats.games);
    statLinesEl.textContent = String(stats.lines);
    statBestEl.textContent = String(overallBest());
  }

  function overallBest() {
    let best = 0;
    for (const key of Object.keys(MODES)) {
      best = Math.max(best, stats.best[key] || 0);
      const list = loadRank(key);
      if (list.length > 0) {
        best = Math.max(best, list[0].score);
      }
    }
    return best;
  }

  function renderModeBests() {
    const cells = document.querySelectorAll(".mode-best");
    for (const cell of cells) {
      const key = cell.getAttribute("data-best");
      const value = stats.best[key] || 0;
      cell.textContent = value > 0 ? "最佳：" + value : "最佳：暂无";
    }
  }

  function addPopup(text, row, big) {
    popups.push({
      text,
      x: (COLS * TILE) / 2,
      y: (row + 1) * TILE,
      big: !!big,
      t: 0,
      life: 1000,
    });
  }

  function shake() {
    canvasWrap.classList.remove("shake");
    void canvasWrap.offsetWidth;
    canvasWrap.classList.add("shake");
  }

  /* ---------- 视图切换 ---------- */

  function showView(name) {
    for (const key of Object.keys(views)) {
      views[key].hidden = key !== name;
    }
    if (name === "menu") {
      updateMenuStats();
    } else if (name === "mode") {
      renderModeBests();
    } else if (name === "ranking") {
      renderRanking();
    }
  }

  /* ---------- 排行榜渲染 ---------- */

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (ch) => {
      const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
      return map[ch];
    });
  }

  function pad2(n) {
    return n < 10 ? "0" + n : String(n);
  }

  function formatDate(ts) {
    const d = new Date(ts);
    return d.getMonth() + 1 + "/" + d.getDate() + " " + pad2(d.getHours()) + ":" + pad2(d.getMinutes());
  }

  function renderRanking() {
    const list = loadRank(rankTab);
    rankingListEl.innerHTML = "";
    rankingEmptyEl.hidden = list.length > 0;
    const medals = ["🥇", "🥈", "🥉"];
    list.forEach((entry, i) => {
      const li = document.createElement("li");
      li.className = i < 3 ? "rank-item top-" + (i + 1) : "rank-item";
      li.innerHTML =
        '<span class="rank-no">' + (medals[i] || String(i + 1)) + "</span>" +
        '<span class="rank-name">' + escapeHtml(entry.name) + "</span>" +
        '<span class="rank-sub">第 ' + entry.level + " 关 · " + entry.lines + " 行 · " + formatDate(entry.ts) + "</span>" +
        '<strong class="rank-score value-accent">' + entry.score + "</strong>";
      rankingListEl.appendChild(li);
    });
  }

  /* ---------- 渲染 ---------- */

  function drawCell(target, x, y, size, color) {
    target.fillStyle = color;
    target.fillRect(x + 1, y + 1, size - 2, size - 2);
    target.fillStyle = "rgba(255, 255, 255, 0.28)";
    target.fillRect(x + 1, y + 1, size - 2, 4);
    target.fillStyle = "rgba(0, 0, 0, 0.25)";
    target.fillRect(x + 1, y + size - 4, size - 2, 3);
  }

  function drawGhostCell(target, x, y, size, color) {
    target.save();
    target.globalAlpha = 0.22;
    target.fillStyle = color;
    target.fillRect(x + 2, y + 2, size - 4, size - 4);
    target.restore();
    target.strokeStyle = color;
    target.lineWidth = 1.5;
    target.strokeRect(x + 2.5, y + 2.5, size - 5, size - 5);
  }

  function render() {
    ctx.fillStyle = "#05060f";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let c = 1; c < COLS; c += 1) {
      ctx.moveTo(c * TILE, 0);
      ctx.lineTo(c * TILE, canvas.height);
    }
    for (let r = 1; r < ROWS; r += 1) {
      ctx.moveTo(0, r * TILE);
      ctx.lineTo(canvas.width, r * TILE);
    }
    ctx.stroke();

    const flash = clearingRows ? 1 - clearTimer / CLEAR_FLASH_MS : 0;
    for (let r = 0; r < ROWS; r += 1) {
      for (let c = 0; c < COLS; c += 1) {
        if (!board[r][c]) {
          continue;
        }
        if (clearingRows && clearingRows.indexOf(r) !== -1) {
          drawCell(ctx, c * TILE, r * TILE, TILE, "rgba(255,255,255," + Math.min(flash, 1) + ")");
        } else {
          drawCell(ctx, c * TILE, r * TILE, TILE, board[r][c]);
        }
      }
    }

    if (active && state !== "clearing") {
      const ghostRow = dropRow(active);
      const m = ROTS[active.shape][active.rot];
      const color = COLORS[active.shape];
      for (let r = 0; r < m.length; r += 1) {
        for (let c = 0; c < m.length; c += 1) {
          if (m[r][c] !== "X") {
            continue;
          }
          const y = ghostRow + r;
          if (y >= 0) {
            drawGhostCell(ctx, (active.col + c) * TILE, y * TILE, TILE, color);
          }
        }
      }
      for (let r = 0; r < m.length; r += 1) {
        for (let c = 0; c < m.length; c += 1) {
          if (m[r][c] !== "X") {
            continue;
          }
          const y = active.row + r;
          if (y < 0) {
            continue;
          }
          drawCell(ctx, (active.col + c) * TILE, y * TILE, TILE, color);
        }
      }
    }

    for (const p of popups) {
      ctx.save();
      ctx.globalAlpha = Math.max(1 - p.t / p.life, 0);
      ctx.font = "700 " + (p.big ? 26 : 18) + "px 'Segoe UI', system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.fillStyle = p.big ? "#ffcc00" : "#eceaf4";
      ctx.shadowColor = "rgba(0, 0, 0, 0.6)";
      ctx.shadowBlur = 6;
      ctx.fillText(p.text, p.x, p.y - p.t * 0.045);
      ctx.restore();
    }
  }

  function renderCenteredPiece(target, shape, cell, boxW, boxH, dimmed) {
    const m = ROTS[shape][0];
    const ox = (boxW - m.length * cell) / 2;
    const oy = (boxH - m.length * cell) / 2;
    target.save();
    if (dimmed) {
      target.globalAlpha = 0.3;
    }
    for (let r = 0; r < m.length; r += 1) {
      for (let c = 0; c < m.length; c += 1) {
        if (m[r][c] !== "X") {
          continue;
        }
        drawCell(target, ox + c * cell, oy + r * cell, cell, COLORS[shape]);
      }
    }
    target.restore();
  }

  function renderHold() {
    holdCtx.fillStyle = "#05060f";
    holdCtx.fillRect(0, 0, holdCanvas.width, holdCanvas.height);
    if (holdShape) {
      renderCenteredPiece(holdCtx, holdShape, 24, holdCanvas.width, holdCanvas.height, !canHold);
    }
  }

  function renderNext() {
    nextCtx.fillStyle = "#05060f";
    nextCtx.fillRect(0, 0, nextCanvas.width, nextCanvas.height);
    const slotH = nextCanvas.height / 3;
    const cell = 18;
    for (let i = 0; i < 3; i += 1) {
      const shape = nextQueue[i];
      if (!shape) {
        continue;
      }
      nextCtx.save();
      nextCtx.translate(0, i * slotH);
      renderCenteredPiece(nextCtx, shape, cell, nextCanvas.width, slotH, false);
      nextCtx.restore();
    }
  }

  /* ---------- 主循环 ---------- */

  function tick(dt) {
    if (state === "clearing") {
      clearTimer -= dt * 1000;
      if (clearTimer <= 0) {
        finishClear();
      }
      return;
    }
    if (state !== "playing" || !active) {
      return;
    }
    fallTimer += dt * 1000;
    while (fallTimer >= fallInterval && state === "playing") {
      fallTimer -= fallInterval;
      softDropStep(false);
    }
  }

  let lastTime = null;
  function frame(now) {
    requestAnimationFrame(frame);
    const dt = Math.min(lastTime === null ? 0 : (now - lastTime) / 1000, 0.05);
    lastTime = now;
    tick(dt);
    for (const p of popups) {
      p.t += dt * 1000;
    }
    popups = popups.filter((p) => p.t < p.life);
    render();
  }

  /* ---------- 输入 ---------- */

  const KEY_ACTIONS = {
    ArrowLeft: { action: moveLeft, repeat: true },
    KeyA: { action: moveLeft, repeat: true },
    ArrowRight: { action: moveRight, repeat: true },
    KeyD: { action: moveRight, repeat: true },
    ArrowDown: { action: () => softDropStep(true), repeat: true },
    KeyS: { action: () => softDropStep(true), repeat: true },
  };

  const dasTimers = {};

  function pressKey(code) {
    const entry = KEY_ACTIONS[code];
    if (!entry || state !== "playing" || dasTimers[code]) {
      return;
    }
    entry.action();
    if (entry.repeat) {
      const holder = {};
      holder.timer = setTimeout(() => {
        holder.timer = null;
        holder.interval = setInterval(() => entry.action(), DAS_REPEAT_MS);
      }, DAS_DELAY_MS);
      dasTimers[code] = holder;
    }
  }

  function releaseKey(code) {
    const holder = dasTimers[code];
    if (!holder) {
      return;
    }
    if (holder.timer) {
      clearTimeout(holder.timer);
    }
    if (holder.interval) {
      clearInterval(holder.interval);
    }
    delete dasTimers[code];
  }

  function releaseAllKeys() {
    for (const code of Object.keys(dasTimers)) {
      releaseKey(code);
    }
  }

  document.addEventListener("keydown", (event) => {
    const target = event.target;
    if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) {
      if (event.code === "Enter" && target === nameInputEl && !recordEntryEl.hidden) {
        event.preventDefault();
        saveCurrentRecord();
      }
      return;
    }

    if (KEY_ACTIONS[event.code]) {
      event.preventDefault();
      pressKey(event.code);
      return;
    }

    if (state === "playing" || state === "ready" || state === "over") {
      if (event.code === "ArrowUp" || event.code === "KeyW" || event.code === "KeyX") {
        event.preventDefault();
        rotatePiece(1);
        return;
      }
      if (event.code === "KeyZ") {
        event.preventDefault();
        rotatePiece(-1);
        return;
      }
      if (event.code === "Space") {
        event.preventDefault();
        hardDrop();
        return;
      }
      if (event.code === "KeyC" || event.code === "ShiftLeft" || event.code === "ShiftRight") {
        event.preventDefault();
        holdPiece();
        return;
      }
      if (event.code === "KeyR") {
        event.preventDefault();
        if (state !== "ready") {
          newGame(mode);
        }
        return;
      }
    }

    if (event.code === "KeyP" || event.code === "Escape") {
      if (!rulesDialog.hidden) {
        rulesDialog.hidden = true;
        return;
      }
      event.preventDefault();
      togglePause();
      return;
    }

    if (event.code === "KeyM") {
      event.preventDefault();
      toggleSound();
    }
  });

  document.addEventListener("keyup", (event) => {
    if (KEY_ACTIONS[event.code]) {
      event.preventDefault();
      releaseKey(event.code);
    }
  });

  window.addEventListener("blur", releaseAllKeys);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && state === "playing") {
      pauseGame();
    }
  });

  canvas.addEventListener("mousedown", (event) => {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    rotatePiece(1);
  });
  canvas.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    rotatePiece(-1);
  });

  function bindHold(button, action) {
    let timer = null;
    const stop = () => {
      if (timer !== null) {
        clearInterval(timer);
        timer = null;
      }
    };
    button.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      stop();
      if (state === "playing") {
        action();
      }
      timer = setInterval(() => {
        if (state === "playing") {
          action();
        }
      }, HOLD_REPEAT_MS);
    });
    button.addEventListener("pointerup", stop);
    button.addEventListener("pointerleave", stop);
    button.addEventListener("pointercancel", stop);
  }

  bindHold($("btn-left"), moveLeft);
  bindHold($("btn-right"), moveRight);
  bindHold($("btn-down"), () => softDropStep(true));
  $("btn-rotate").addEventListener("pointerdown", (event) => {
    event.preventDefault();
    rotatePiece(1);
  });
  $("btn-hold").addEventListener("pointerdown", (event) => {
    event.preventDefault();
    holdPiece();
  });
  $("btn-drop").addEventListener("pointerdown", (event) => {
    event.preventDefault();
    hardDrop();
  });

  /* ---------- 按钮事件 ---------- */

  function bindClick(id, handler) {
    $(id).addEventListener("click", (event) => {
      event.currentTarget.blur();
      handler();
    });
  }

  bindClick("btn-start", () => showView("mode"));
  bindClick("btn-ranking", () => showView("ranking"));
  bindClick("btn-rules", () => {
    rulesDialog.hidden = false;
  });
  bindClick("btn-close-rules", () => {
    rulesDialog.hidden = true;
  });
  bindClick("btn-sound-menu", toggleSound);
  bindClick("btn-sound-game", toggleSound);
  bindClick("btn-back-mode", () => showView("menu"));
  bindClick("btn-back-ranking", () => showView("menu"));
  bindClick("btn-to-menu", leaveToMenu);
  bindClick("btn-pause", togglePause);
  bindClick("btn-restart", () => {
    if (state !== "idle") {
      newGame(mode);
    }
  });
  bindClick("btn-save-record", saveCurrentRecord);

  const modeCards = document.querySelectorAll(".mode-card");
  for (const card of modeCards) {
    card.addEventListener("click", () => {
      newGame(card.getAttribute("data-mode"));
      showView("game");
    });
  }

  const rankTabs = document.querySelectorAll(".ranking-tab");
  for (const tab of rankTabs) {
    tab.addEventListener("click", () => {
      rankTab = tab.getAttribute("data-tab");
      syncRankTabs();
      renderRanking();
    });
  }

  function syncRankTabs() {
    for (const tab of rankTabs) {
      const selected = tab.getAttribute("data-tab") === rankTab;
      tab.classList.toggle("selected", selected);
      tab.setAttribute("aria-selected", String(selected));
    }
  }

  /* ---------- 启动 ---------- */

  updateSoundButtons();
  showView("menu");
  requestAnimationFrame(frame);

  /* 仅当 URL 带 ?debug=1 时暴露内部状态，供自动化测试使用 */
  if (window.location.search.indexOf("debug=1") !== -1) {
    window.__tetrisDebug = {
      state: () => state,
      active: () => active,
      hold: () => holdShape,
      canHold: () => canHold,
      next: () => nextQueue.slice(),
      board: () => board.map((row) => row.slice()),
      score: () => score,
      lines: () => lines,
      level: () => level,
      mode: () => mode,
      popups: () => popups.map((p) => Object.assign({}, p)),
    };
  }
})();

(() => {
  "use strict";

  const SIZE = 4;
  const BEST_KEY = "sgame-2048-best";
  const STATS_KEY = "sgame-2048-stats";
  const HISTORY_KEY = "sgame-2048-history";
  const HISTORY_LIMIT = 20;
  const WIN_VALUE = 2048;
  const SWIPE_THRESHOLD = 24;

  const DIRS = {
    up: { dr: -1, dc: 0 },
    down: { dr: 1, dc: 0 },
    left: { dr: 0, dc: -1 },
    right: { dr: 0, dc: 1 },
  };

  const KEY_DIRS = {
    ArrowUp: "up",
    ArrowDown: "down",
    ArrowLeft: "left",
    ArrowRight: "right",
    w: "up",
    W: "up",
    s: "down",
    S: "down",
    a: "left",
    A: "left",
    d: "right",
    D: "right",
  };

  const TEXT = {
    winTitle: "你赢了 · YOU WIN!",
    winDetail: (score) => `你合成 2048！得分 ${score}。You made 2048! Score ${score}.`,
    loseTitle: "游戏结束 · GAME OVER",
    loseDetail: (score) => `没有可移动的格子了。得分 ${score}。No moves left. Score ${score}.`,
  };

  const views = {
    menu: document.getElementById("menu-view"),
    game: document.getElementById("game-view"),
    records: document.getElementById("records-view"),
  };
  const boardEl = document.getElementById("board");
  const tileLayerEl = document.getElementById("tile-layer");
  const scoreEl = document.getElementById("score");
  const bestEl = document.getElementById("best");
  const maxTileEl = document.getElementById("max-tile");
  const overlayEl = document.getElementById("overlay");
  const overlayTitleEl = document.getElementById("overlay-title");
  const overlayDetailEl = document.getElementById("overlay-detail");
  const overlayRecordEl = document.getElementById("overlay-record");
  const overlayContinueButton = document.getElementById("overlay-continue");
  const overlayRestartButton = document.getElementById("overlay-restart");
  const newGameButton = document.getElementById("new-game-button");
  const pauseOverlayEl = document.getElementById("pause-overlay");
  const pauseDetailEl = document.getElementById("pause-detail");
  const rulesModal = document.getElementById("rules-modal");
  const historyListEl = document.getElementById("history-list");
  const historyEmptyEl = document.getElementById("history-empty");

  let tiles = [];
  let nextId = 1;
  let score = 0;
  let best = 0;
  let won = false;
  let over = false;
  let keepPlaying = false;
  let moves = 0;
  let maxTile = 0;
  let paused = false;
  let gameStartBest = 0;
  let gameRecorded = false;

  const tileEls = new Map();

  function loadBest() {
    const value = Number(localStorage.getItem(BEST_KEY));
    return Number.isFinite(value) && value > 0 ? value : 0;
  }

  function saveBest() {
    if (score > best) {
      best = score;
      localStorage.setItem(BEST_KEY, String(best));
    }
  }

  function loadStats() {
    try {
      const value = JSON.parse(localStorage.getItem(STATS_KEY));
      return value && typeof value.games === "number"
        ? { games: value.games, wins: value.wins || 0, maxTile: value.maxTile || 0 }
        : { games: 0, wins: 0, maxTile: 0 };
    } catch {
      return { games: 0, wins: 0, maxTile: 0 };
    }
  }

  function saveStats(stats) {
    localStorage.setItem(STATS_KEY, JSON.stringify(stats));
  }

  function loadHistory() {
    try {
      const value = JSON.parse(localStorage.getItem(HISTORY_KEY));
      return Array.isArray(value) ? value : [];
    } catch {
      return [];
    }
  }

  function saveHistory(entries) {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(entries));
  }

  function formatDate(ts) {
    const date = new Date(ts);
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  function gameEnded() {
    return over || (won && !keepPlaying);
  }

  function emptyCells() {
    const occupied = new Set(tiles.map((tile) => tile.row * SIZE + tile.col));
    const cells = [];
    for (let row = 0; row < SIZE; row++) {
      for (let col = 0; col < SIZE; col++) {
        if (!occupied.has(row * SIZE + col)) {
          cells.push({ row, col });
        }
      }
    }
    return cells;
  }

  function spawnTile() {
    const cells = emptyCells();
    if (cells.length === 0) {
      return;
    }
    const cell = cells[Math.floor(Math.random() * cells.length)];
    tiles.push({
      id: nextId++,
      value: Math.random() < 0.9 ? 2 : 4,
      row: cell.row,
      col: cell.col,
      merged: false,
      isNew: true,
    });
  }

  function slide(dir) {
    const { dr, dc } = DIRS[dir];
    const horizontal = dc !== 0;
    const reverse = dc > 0 || dr > 0;
    let changed = false;
    const next = [];

    for (const tile of tiles) {
      tile.merged = false;
    }

    for (let line = 0; line < SIZE; line++) {
      const lineTiles = tiles
        .filter((tile) => (horizontal ? tile.row === line : tile.col === line))
        .sort((a, b) => {
          const pa = horizontal ? a.col : a.row;
          const pb = horizontal ? b.col : b.row;
          return reverse ? pb - pa : pa - pb;
        });

      const result = [];
      for (const tile of lineTiles) {
        const last = result[result.length - 1];
        if (last && last.value === tile.value && !last.merged) {
          last.value *= 2;
          last.merged = true;
          score += last.value;
          changed = true;
        } else {
          result.push(tile);
        }
      }

      result.forEach((tile, index) => {
        const pos = reverse ? SIZE - 1 - index : index;
        const newRow = horizontal ? line : pos;
        const newCol = horizontal ? pos : line;
        if (tile.row !== newRow || tile.col !== newCol) {
          changed = true;
        }
        tile.row = newRow;
        tile.col = newCol;
      });

      next.push(...result);
    }

    tiles = next;
    return changed;
  }

  function hasMoves() {
    if (tiles.length < SIZE * SIZE) {
      return true;
    }
    const byCell = new Map();
    for (const tile of tiles) {
      byCell.set(tile.row * SIZE + tile.col, tile.value);
    }
    for (const [key, value] of byCell) {
      const row = Math.floor(key / SIZE);
      const col = key % SIZE;
      if (col + 1 < SIZE && byCell.get(key + 1) === value) {
        return true;
      }
      if (row + 1 < SIZE && byCell.get(key + SIZE) === value) {
        return true;
      }
    }
    return false;
  }

  function move(dir) {
    if (over || (won && !keepPlaying)) {
      return;
    }
    if (!slide(dir)) {
      return;
    }
    moves += 1;
    spawnTile();
    saveBest();
    if (!won && tiles.some((tile) => tile.value >= WIN_VALUE)) {
      won = true;
      recordResult("win");
      showOverlay("win");
    } else if (!hasMoves()) {
      over = true;
      recordResult("lose");
      showOverlay("lose");
    }
    render();
  }

  function render() {
    scoreEl.textContent = score;
    bestEl.textContent = best;

    let currentMax = 0;
    const seen = new Set();
    for (const tile of tiles) {
      seen.add(tile.id);
      if (tile.value > currentMax) {
        currentMax = tile.value;
      }
      let el = tileEls.get(tile.id);
      if (!el) {
        el = document.createElement("div");
        tileLayerEl.appendChild(el);
        tileEls.set(tile.id, el);
      }
      const valueClass = tile.value <= WIN_VALUE ? `v-${tile.value}` : "v-super";
      if (tile.merged) {
        el.classList.remove("pop");
        void el.offsetWidth; // restart the pop animation when it fires twice in a row
        el.className = `tile ${valueClass} pop`;
      } else if (tile.isNew) {
        el.className = `tile ${valueClass} new`;
      } else {
        el.className = `tile ${valueClass}`;
      }
      el.textContent = tile.value;
      el.style.transform =
        `translate(` +
        `calc(var(--gap) + ${tile.col} * (var(--tile-size) + var(--gap))), ` +
        `calc(var(--gap) + ${tile.row} * (var(--tile-size) + var(--gap))))`;
      tile.merged = false;
      tile.isNew = false;
    }

    for (const [id, el] of tileEls) {
      if (!seen.has(id)) {
        el.remove();
        tileEls.delete(id);
      }
    }

    maxTile = currentMax;
    maxTileEl.textContent = currentMax > 0 ? String(currentMax) : "--";
  }

  function showOverlay(type) {
    overlayTitleEl.textContent = type === "win" ? TEXT.winTitle : TEXT.loseTitle;
    overlayDetailEl.textContent =
      type === "win" ? TEXT.winDetail(score) : TEXT.loseDetail(score);
    overlayContinueButton.hidden = type !== "win";
    overlayRecordEl.hidden = !(score > gameStartBest);
    overlayEl.hidden = false;
  }

  function hideOverlay() {
    overlayEl.hidden = true;
  }

  function recordResult(result) {
    if (gameRecorded) {
      return;
    }
    gameRecorded = true;
    const stats = loadStats();
    stats.games += 1;
    if (result === "win") {
      stats.wins += 1;
    }
    if (maxTile > stats.maxTile) {
      stats.maxTile = maxTile;
    }
    saveStats(stats);

    const history = loadHistory();
    history.unshift({ result, score, maxTile, moves, date: Date.now() });
    saveHistory(history.slice(0, HISTORY_LIMIT));
  }

  function newGame() {
    tiles = [];
    score = 0;
    won = false;
    over = false;
    keepPlaying = false;
    moves = 0;
    maxTile = 0;
    paused = false;
    gameStartBest = best;
    gameRecorded = false;
    hideOverlay();
    pauseOverlayEl.hidden = true;
    for (const el of tileEls.values()) {
      el.remove();
    }
    tileEls.clear();
    spawnTile();
    spawnTile();
    render();
  }

  function gameInProgress() {
    return score > 0 && !gameEnded();
  }

  function confirmNewGame() {
    if (gameInProgress() && !window.confirm("确定开始新游戏吗？当前进度将丢失。")) {
      return;
    }
    newGame();
  }

  function leaveGame() {
    if (gameInProgress() && !window.confirm("返回菜单将丢失当前进度，确定吗？")) {
      return;
    }
    pauseOverlayEl.hidden = true;
    hideOverlay();
    showView("menu");
  }

  function pauseGame() {
    if (paused || gameEnded()) {
      return;
    }
    paused = true;
    pauseDetailEl.textContent = `得分 ${score} · 最大方块 ${maxTile > 0 ? maxTile : "--"}`;
    pauseOverlayEl.hidden = false;
  }

  function resumeGame() {
    if (!paused) {
      return;
    }
    paused = false;
    pauseOverlayEl.hidden = true;
  }

  function showView(id) {
    for (const [key, element] of Object.entries(views)) {
      element.hidden = key !== id;
    }
    if (id === "menu") {
      renderMenuStats();
    } else if (id === "records") {
      renderRecords();
    }
  }

  function renderMenuStats() {
    const stats = loadStats();
    document.getElementById("stat-games").textContent = String(stats.games);
    document.getElementById("stat-best").textContent = String(loadBest());
    document.getElementById("stat-max-tile").textContent =
      stats.maxTile > 0 ? String(stats.maxTile) : "--";
    document.getElementById("stat-wins").textContent = String(stats.wins);
  }

  function renderRecords() {
    const stats = loadStats();
    document.getElementById("rec-games").textContent = String(stats.games);
    document.getElementById("rec-wins").textContent = String(stats.wins);
    document.getElementById("rec-best").textContent = String(loadBest());
    document.getElementById("rec-max-tile").textContent =
      stats.maxTile > 0 ? String(stats.maxTile) : "--";

    historyListEl.innerHTML = "";
    const history = loadHistory();
    for (const entry of history) {
      const item = document.createElement("li");
      item.className = "history-item";

      const badge = document.createElement("span");
      badge.className =
        `history-result ${entry.result === "win" ? "result-win" : "result-lose"}`;
      badge.textContent = entry.result === "win" ? "胜利" : "失败";

      const entryScore = document.createElement("span");
      entryScore.className = "history-score";
      entryScore.textContent = `得分 ${entry.score}`;

      const meta = document.createElement("span");
      meta.className = "history-meta";
      meta.textContent = `最大 ${entry.maxTile} · ${entry.moves} 步`;

      const date = document.createElement("span");
      date.className = "history-date";
      date.textContent = formatDate(entry.date);

      item.append(badge, entryScore, meta, date);
      historyListEl.appendChild(item);
    }
    historyEmptyEl.hidden = history.length > 0;
  }

  function openRules() {
    rulesModal.hidden = false;
  }

  function closeRules() {
    rulesModal.hidden = true;
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (!rulesModal.hidden) {
        closeRules();
        return;
      }
      if (!views.game.hidden) {
        if (paused) {
          resumeGame();
        } else {
          pauseGame();
        }
      }
      return;
    }
    const dir = KEY_DIRS[event.key];
    if (!dir || views.game.hidden || paused) {
      return;
    }
    event.preventDefault();
    move(dir);
  });

  let touchStart = null;
  boardEl.addEventListener(
    "touchstart",
    (event) => {
      event.preventDefault();
      const touch = event.touches[0];
      touchStart = { x: touch.clientX, y: touch.clientY };
    },
    { passive: false },
  );

  boardEl.addEventListener(
    "touchmove",
    (event) => {
      event.preventDefault();
      if (touchStart === null || views.game.hidden || paused) {
        return;
      }
      const touch = event.touches[0];
      const dx = touch.clientX - touchStart.x;
      const dy = touch.clientY - touchStart.y;
      if (Math.abs(dx) < SWIPE_THRESHOLD && Math.abs(dy) < SWIPE_THRESHOLD) {
        return;
      }
      if (Math.abs(dx) > Math.abs(dy)) {
        move(dx > 0 ? "right" : "left");
      } else {
        move(dy > 0 ? "down" : "up");
      }
      touchStart = { x: touch.clientX, y: touch.clientY };
    },
    { passive: false },
  );

  boardEl.addEventListener("touchend", () => {
    touchStart = null;
  });

  document.getElementById("btn-start").addEventListener("click", () => {
    newGame();
    showView("game");
  });
  document.getElementById("btn-menu").addEventListener("click", leaveGame);
  document.getElementById("btn-pause").addEventListener("click", () => {
    if (paused) {
      resumeGame();
    } else {
      pauseGame();
    }
  });
  document.getElementById("btn-resume").addEventListener("click", resumeGame);
  document.getElementById("btn-pause-new").addEventListener("click", confirmNewGame);
  document.getElementById("btn-pause-menu").addEventListener("click", leaveGame);
  document.getElementById("btn-rules").addEventListener("click", openRules);
  document.getElementById("btn-close-rules").addEventListener("click", closeRules);
  document.getElementById("btn-records").addEventListener("click", () => showView("records"));
  document.getElementById("btn-back-menu").addEventListener("click", () => showView("menu"));
  document.getElementById("btn-clear-history").addEventListener("click", () => {
    if (window.confirm("确定清空最近记录吗？最高分与统计将保留。")) {
      saveHistory([]);
      renderRecords();
    }
  });

  newGameButton.addEventListener("click", confirmNewGame);
  overlayRestartButton.addEventListener("click", newGame);
  document.getElementById("overlay-menu").addEventListener("click", () => showView("menu"));
  overlayContinueButton.addEventListener("click", () => {
    keepPlaying = true;
    hideOverlay();
  });

  rulesModal.addEventListener("click", (event) => {
    if (event.target === rulesModal) {
      closeRules();
    }
  });

  /* Boot */
  best = loadBest();
  newGame();
  showView("menu");
})();

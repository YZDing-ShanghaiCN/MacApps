(() => {
  "use strict";

  const DIFFICULTIES = {
    beginner: { rows: 9, cols: 9, mines: 10 },
    intermediate: { rows: 16, cols: 16, mines: 40 },
    expert: { rows: 16, cols: 30, mines: 99 },
  };
  const MAX_TIME = 999;
  const LONG_PRESS_MS = 400;
  const RECORDS_LIMIT = 10;
  const STATS_KEY = "sgame-ms-stats";

  /* DOM */

  const boardEl = document.getElementById("board");
  const mineCounterEl = document.getElementById("mine-counter");
  const timerEl = document.getElementById("timer");
  const bestDisplayEl = document.getElementById("best-display");
  const flagModeButton = document.getElementById("flag-mode-button");
  const resultOverlay = document.getElementById("result-overlay");
  const resultTitleEl = document.getElementById("result-title");
  const resultDetailEl = document.getElementById("result-detail");
  const rulesDialog = document.getElementById("rules-dialog");
  const rankingListEl = document.getElementById("ranking-list");
  const rankingEmptyEl = document.getElementById("ranking-empty");
  const views = Array.from(document.querySelectorAll(".ms-view"));

  /* Storage */

  function recordsKey(difficultyKey) {
    return `sgame-ms-records-${difficultyKey}`;
  }

  function loadRecords(difficultyKey) {
    try {
      const value = JSON.parse(localStorage.getItem(recordsKey(difficultyKey)));
      if (Array.isArray(value)) {
        return value.filter((rec) => typeof rec.time === "number");
      }
    } catch (err) {
      /* corrupted entry: fall through */
    }
    return [];
  }

  function saveRecords(difficultyKey, records) {
    localStorage.setItem(recordsKey(difficultyKey), JSON.stringify(records));
  }

  function bestOf(difficultyKey) {
    const records = loadRecords(difficultyKey);
    return records.length > 0 ? records[0].time : null;
  }

  function loadStats() {
    const fallback = {
      beginner: { games: 0, wins: 0 },
      intermediate: { games: 0, wins: 0 },
      expert: { games: 0, wins: 0 },
    };
    try {
      const value = JSON.parse(localStorage.getItem(STATS_KEY));
      if (value && typeof value === "object") {
        for (const key of Object.keys(fallback)) {
          const entry = value[key];
          if (entry && typeof entry.games === "number" && typeof entry.wins === "number") {
            fallback[key] = { games: entry.games, wins: entry.wins };
          }
        }
      }
    } catch (err) {
      /* corrupted entry: use fallback */
    }
    return fallback;
  }

  function saveStats(stats) {
    localStorage.setItem(STATS_KEY, JSON.stringify(stats));
  }

  /* Views */

  function showView(id) {
    for (const view of views) {
      view.hidden = view.id !== id;
    }
  }

  function updateMenuStats() {
    const stats = loadStats();
    let games = 0;
    let wins = 0;
    for (const key of Object.keys(DIFFICULTIES)) {
      games += stats[key].games;
      wins += stats[key].wins;
    }
    document.getElementById("stat-games").textContent = String(games);
    document.getElementById("stat-wins").textContent = String(wins);
    document.getElementById("stat-rate").textContent =
      games > 0 ? `${Math.round((wins / games) * 100)}%` : "—";
  }

  function updateDifficultyBests() {
    for (const key of Object.keys(DIFFICULTIES)) {
      const best = bestOf(key);
      const el = document.querySelector(`[data-best="${key}"]`);
      el.textContent = best === null ? "最佳：暂无" : `最佳：${best} 秒`;
    }
  }

  function renderRanking(difficultyKey) {
    const records = loadRecords(difficultyKey);
    rankingListEl.innerHTML = "";
    rankingEmptyEl.hidden = records.length > 0;
    const medals = ["🥇", "🥈", "🥉"];
    records.slice(0, RECORDS_LIMIT).forEach((rec, i) => {
      const item = document.createElement("li");
      item.className = "ranking-item";
      const rank = document.createElement("span");
      rank.className = "ranking-rank";
      rank.textContent = medals[i] || `${i + 1}.`;
      const time = document.createElement("span");
      time.className = "ranking-time";
      time.textContent = `${rec.time} 秒`;
      const date = document.createElement("span");
      date.className = "ranking-date";
      date.textContent = rec.date || "";
      item.append(rank, time, date);
      rankingListEl.appendChild(item);
    });
  }

  function updateBestDisplay() {
    const best = bestOf(difficultyKey);
    bestDisplayEl.textContent = best === null ? "—" : `${best} 秒`;
  }

  /* Game state */

  let difficultyKey = "beginner";
  let rows = 0;
  let cols = 0;
  let mineTotal = 0;
  let cells = [];
  let cellButtons = [];
  let minesPlaced = false;
  let gameOver = false;
  let revealedCount = 0;
  let flagCount = 0;
  let seconds = 0;
  let timerId = null;
  let flagMode = false;
  let suppressClick = false;
  let longPressTimer = null;

  function indexOf(row, col) {
    return row * cols + col;
  }

  function neighborsOf(index) {
    const row = Math.floor(index / cols);
    const col = index % cols;
    const result = [];
    for (let dr = -1; dr <= 1; dr += 1) {
      for (let dc = -1; dc <= 1; dc += 1) {
        if (dr === 0 && dc === 0) {
          continue;
        }
        const nr = row + dr;
        const nc = col + dc;
        if (nr >= 0 && nr < rows && nc >= 0 && nc < cols) {
          result.push(indexOf(nr, nc));
        }
      }
    }
    return result;
  }

  function shuffle(values) {
    for (let i = values.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [values[i], values[j]] = [values[j], values[i]];
    }
    return values;
  }

  function startTimer() {
    if (timerId !== null) {
      return;
    }
    timerId = setInterval(() => {
      seconds = Math.min(seconds + 1, MAX_TIME);
      timerEl.textContent = String(seconds);
    }, 1000);
  }

  function stopTimer() {
    if (timerId !== null) {
      clearInterval(timerId);
      timerId = null;
    }
  }

  function updateMineCounter() {
    mineCounterEl.textContent = String(mineTotal - flagCount);
  }

  function placeMines(safeIndex) {
    const forbidden = new Set([safeIndex, ...neighborsOf(safeIndex)]);
    const candidates = [];
    for (let i = 0; i < cells.length; i += 1) {
      if (!forbidden.has(i)) {
        candidates.push(i);
      }
    }
    // Fall back to excluding only the clicked cell if the 3x3 exclusion
    // ever leaves too few candidates.
    if (candidates.length < mineTotal) {
      candidates.length = 0;
      for (let i = 0; i < cells.length; i += 1) {
        if (i !== safeIndex) {
          candidates.push(i);
        }
      }
    }
    shuffle(candidates);
    for (const index of candidates.slice(0, mineTotal)) {
      cells[index].mine = true;
    }
    for (let i = 0; i < cells.length; i += 1) {
      cells[i].adjacent = neighborsOf(i).filter((n) => cells[n].mine).length;
    }
    minesPlaced = true;
  }

  function renderCell(index) {
    const cell = cells[index];
    const button = cellButtons[index];
    button.className = "ms-cell";
    button.textContent = "";
    if (cell.revealed) {
      button.classList.add("revealed");
      if (cell.mine) {
        button.classList.add("mine");
        button.textContent = "💣";
      } else if (cell.adjacent > 0) {
        button.classList.add(`num-${cell.adjacent}`);
        button.textContent = String(cell.adjacent);
      }
    } else if (cell.flagged) {
      button.classList.add("flagged");
      button.textContent = "🚩";
    }
  }

  function reveal(index) {
    const cell = cells[index];
    if (cell.revealed || cell.flagged) {
      return;
    }
    cell.revealed = true;
    revealedCount += 1;
    renderCell(index);
    if (cell.adjacent === 0 && !cell.mine) {
      for (const neighbor of neighborsOf(index)) {
        reveal(neighbor);
      }
    }
  }

  function toggleFlag(index) {
    const cell = cells[index];
    if (cell.revealed || gameOver) {
      return;
    }
    cell.flagged = !cell.flagged;
    flagCount += cell.flagged ? 1 : -1;
    renderCell(index);
    updateMineCounter();
  }

  function chord(index) {
    const cell = cells[index];
    const neighbors = neighborsOf(index);
    const flagged = neighbors.filter((n) => cells[n].flagged).length;
    if (flagged !== cell.adjacent) {
      return;
    }
    for (const neighbor of neighbors) {
      if (!cells[neighbor].flagged && !cells[neighbor].revealed) {
        if (cells[neighbor].mine) {
          reveal(neighbor);
          lose(neighbor);
          return;
        }
        reveal(neighbor);
      }
    }
    checkWin();
  }

  function revealAllMines(explodedIndex) {
    for (let i = 0; i < cells.length; i += 1) {
      const cell = cells[i];
      if (cell.mine && !cell.flagged) {
        cell.revealed = true;
        renderCell(i);
      } else if (!cell.mine && cell.flagged) {
        cellButtons[i].classList.add("wrong-flag");
        cellButtons[i].textContent = "💣";
      }
    }
    if (explodedIndex !== null) {
      cellButtons[explodedIndex].classList.add("exploded");
    }
  }

  function showResult(title, detail) {
    resultTitleEl.textContent = title;
    resultDetailEl.textContent = detail;
    resultOverlay.hidden = false;
  }

  function lose(explodedIndex) {
    gameOver = true;
    stopTimer();
    revealAllMines(explodedIndex);
    const stats = loadStats();
    stats[difficultyKey].games += 1;
    saveStats(stats);
    const best = bestOf(difficultyKey);
    showResult(
      "💥 踩到地雷了",
      `用时 ${seconds} 秒 · 最佳 ${best === null ? "暂无" : `${best} 秒`}`,
    );
  }

  function checkWin() {
    if (revealedCount !== rows * cols - mineTotal) {
      return;
    }
    gameOver = true;
    stopTimer();
    for (let i = 0; i < cells.length; i += 1) {
      if (cells[i].mine && !cells[i].flagged) {
        cells[i].flagged = true;
        flagCount += 1;
        renderCell(i);
      }
    }
    updateMineCounter();
    const stats = loadStats();
    stats[difficultyKey].games += 1;
    stats[difficultyKey].wins += 1;
    saveStats(stats);
    const records = loadRecords(difficultyKey);
    const isNewBest = records.length === 0 || seconds < records[0].time;
    records.push({ time: seconds, date: new Date().toISOString().slice(0, 10) });
    records.sort((a, b) => a.time - b.time);
    saveRecords(difficultyKey, records.slice(0, RECORDS_LIMIT));
    const best = isNewBest ? seconds : records[0].time;
    showResult(
      "🎉 胜利！",
      `用时 ${seconds} 秒${isNewBest ? " · 新纪录！" : ""} · 最佳 ${best} 秒`,
    );
  }

  function handleActivate(index) {
    if (gameOver) {
      return;
    }
    const cell = cells[index];
    if (flagMode && !cell.revealed) {
      toggleFlag(index);
      return;
    }
    if (!minesPlaced) {
      placeMines(index);
      startTimer();
    }
    if (cell.revealed) {
      chord(index);
      return;
    }
    if (cell.flagged) {
      return;
    }
    if (cell.mine) {
      reveal(index);
      lose(index);
      return;
    }
    reveal(index);
    checkWin();
  }

  function buildBoard() {
    stopTimer();
    const difficulty = DIFFICULTIES[difficultyKey];
    rows = difficulty.rows;
    cols = difficulty.cols;
    mineTotal = difficulty.mines;
    minesPlaced = false;
    gameOver = false;
    revealedCount = 0;
    flagCount = 0;
    seconds = 0;
    timerEl.textContent = "0";
    resultOverlay.hidden = true;
    updateMineCounter();
    updateBestDisplay();

    cells = Array.from({ length: rows * cols }, () => ({
      mine: false,
      revealed: false,
      flagged: false,
      adjacent: 0,
    }));

    boardEl.innerHTML = "";
    boardEl.style.gridTemplateColumns = `repeat(${cols}, var(--ms-cell-size))`;
    cellButtons = [];
    for (let i = 0; i < cells.length; i += 1) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "ms-cell";
      button.dataset.index = String(i);
      boardEl.appendChild(button);
      cellButtons.push(button);
    }
  }

  function startGame(key) {
    difficultyKey = key;
    buildBoard();
    showView("game-view");
  }

  function backToMenu() {
    stopTimer();
    resultOverlay.hidden = true;
    updateMenuStats();
    showView("menu-view");
  }

  /* Input: board */

  boardEl.addEventListener("click", (event) => {
    const button = event.target.closest(".ms-cell");
    if (!button) {
      return;
    }
    if (suppressClick) {
      suppressClick = false;
      return;
    }
    handleActivate(Number(button.dataset.index));
  });

  boardEl.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    const button = event.target.closest(".ms-cell");
    if (button) {
      toggleFlag(Number(button.dataset.index));
    }
  });

  boardEl.addEventListener("touchstart", (event) => {
    const button = event.target.closest(".ms-cell");
    if (!button) {
      return;
    }
    const index = Number(button.dataset.index);
    longPressTimer = setTimeout(() => {
      longPressTimer = null;
      suppressClick = true;
      toggleFlag(index);
      if (navigator.vibrate) {
        navigator.vibrate(30);
      }
    }, LONG_PRESS_MS);
  });

  const cancelLongPress = () => {
    if (longPressTimer !== null) {
      clearTimeout(longPressTimer);
      longPressTimer = null;
    }
  };
  boardEl.addEventListener("touchmove", cancelLongPress);
  boardEl.addEventListener("touchend", cancelLongPress);
  boardEl.addEventListener("touchcancel", cancelLongPress);

  /* Input: navigation */

  document.getElementById("btn-start").addEventListener("click", () => {
    updateDifficultyBests();
    showView("difficulty-view");
  });

  document.getElementById("btn-ranking").addEventListener("click", () => {
    const activeTab = document.querySelector(".ranking-tab.selected");
    renderRanking(activeTab ? activeTab.dataset.tab : "beginner");
    showView("ranking-view");
  });

  document.getElementById("btn-rules").addEventListener("click", () => {
    rulesDialog.hidden = false;
  });

  document.getElementById("btn-close-rules").addEventListener("click", () => {
    rulesDialog.hidden = true;
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !rulesDialog.hidden) {
      rulesDialog.hidden = true;
    }
  });

  document.getElementById("btn-back-from-difficulty").addEventListener("click", backToMenu);
  document.getElementById("btn-back-from-ranking").addEventListener("click", backToMenu);
  document.getElementById("btn-to-menu").addEventListener("click", backToMenu);
  document.getElementById("btn-overlay-menu").addEventListener("click", backToMenu);
  document.getElementById("btn-restart").addEventListener("click", buildBoard);
  document.getElementById("btn-again").addEventListener("click", buildBoard);

  for (const card of document.querySelectorAll(".diff-card")) {
    card.addEventListener("click", () => {
      startGame(card.dataset.diff);
    });
  }

  for (const tab of document.querySelectorAll(".ranking-tab")) {
    tab.addEventListener("click", () => {
      for (const other of document.querySelectorAll(".ranking-tab")) {
        const selected = other === tab;
        other.classList.toggle("selected", selected);
        other.setAttribute("aria-selected", String(selected));
      }
      renderRanking(tab.dataset.tab);
    });
  }

  flagModeButton.addEventListener("click", () => {
    flagMode = !flagMode;
    flagModeButton.classList.toggle("selected", flagMode);
    flagModeButton.setAttribute("aria-pressed", String(flagMode));
  });

  /* Boot */

  updateMenuStats();
  buildBoard();
})();

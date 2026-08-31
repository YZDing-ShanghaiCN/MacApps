(() => {
  "use strict";

  const MODES = { 3: 9, 4: 16, 5: 25 };
  const MODE_KEY = "sgame-schulte-mode";
  const BEST_KEY_PREFIX = "sgame-schulte-best-";
  const LEGACY_BEST_KEY = "sgame-schulte-best";
  const STATS_KEY = "sgame-schulte-stats";
  const HISTORY_KEY = "sgame-schulte-history";
  const HISTORY_LIMIT = 20;

  const views = {
    menu: document.getElementById("menu-view"),
    game: document.getElementById("game-view"),
    records: document.getElementById("records-view"),
  };
  const grid = document.getElementById("grid");
  const timerEl = document.getElementById("timer");
  const nextEl = document.getElementById("next-number");
  const mistakesEl = document.getElementById("mistakes");
  const bestEl = document.getElementById("best");
  const modeLabelEl = document.getElementById("mode-label");
  const progressBarEl = document.getElementById("progress-bar");
  const pauseOverlay = document.getElementById("pause-overlay");
  const pauseDetailEl = document.getElementById("pause-detail");
  const resultOverlay = document.getElementById("result-overlay");
  const resultDetailEl = document.getElementById("result-detail");
  const resultRecordEl = document.getElementById("result-record");
  const rulesModal = document.getElementById("rules-modal");
  const historyListEl = document.getElementById("history-list");
  const historyEmptyEl = document.getElementById("history-empty");
  const startButtons = {
    3: document.getElementById("start-3"),
    4: document.getElementById("start-4"),
    5: document.getElementById("start-5"),
  };

  let size = loadMode();
  let next = 1;
  let mistakes = 0;
  let startTime = null;
  let finished = false;
  let paused = false;
  let pauseAt = null;
  let pausedTotal = 0;
  let rafId = null;

  function loadMode() {
    const value = Number(localStorage.getItem(MODE_KEY));
    return MODES[value] ? value : 5;
  }

  function bestKey() {
    return BEST_KEY_PREFIX + size;
  }

  function loadBestFor(mode) {
    let value = Number(localStorage.getItem(BEST_KEY_PREFIX + mode));
    if (!(Number.isFinite(value) && value > 0) && mode === 5) {
      // Fall back to the key used before per-mode best times existed.
      value = Number(localStorage.getItem(LEGACY_BEST_KEY));
    }
    return Number.isFinite(value) && value > 0 ? value : null;
  }

  function loadBest() {
    return loadBestFor(size);
  }

  function formatTime(ms) {
    return (ms / 1000).toFixed(1) + "s";
  }

  function formatBest(mode) {
    const best = loadBestFor(mode);
    return best === null ? "--" : formatTime(best);
  }

  function formatDate(ts) {
    const date = new Date(ts);
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  function loadStats() {
    try {
      const value = JSON.parse(localStorage.getItem(STATS_KEY));
      return value && typeof value.games === "number" ? value : { games: 0 };
    } catch {
      return { games: 0 };
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

  function renderBest() {
    bestEl.textContent = formatBest(size);
  }

  function renderStartButtons() {
    for (const [key, button] of Object.entries(startButtons)) {
      button.classList.toggle("selected", Number(key) === size);
    }
  }

  function renderMenuStats() {
    document.getElementById("stat-games").textContent = String(loadStats().games);
    document.getElementById("stat-best-3").textContent = formatBest(3);
    document.getElementById("stat-best-4").textContent = formatBest(4);
    document.getElementById("stat-best-5").textContent = formatBest(5);
    renderStartButtons();
  }

  function renderRecords() {
    document.getElementById("rec-best-3").textContent = formatBest(3);
    document.getElementById("rec-best-4").textContent = formatBest(4);
    document.getElementById("rec-best-5").textContent = formatBest(5);

    historyListEl.innerHTML = "";
    const history = loadHistory();
    for (const entry of history) {
      const item = document.createElement("li");
      item.className = "history-item";

      const mode = document.createElement("span");
      mode.className = "history-mode";
      mode.textContent = `${entry.size}×${entry.size}`;

      const time = document.createElement("span");
      time.className = "history-time";
      time.textContent = formatTime(entry.ms);

      const entryMistakes = document.createElement("span");
      entryMistakes.className = "history-mistakes";
      entryMistakes.textContent = `错误 ${entry.mistakes}`;

      const date = document.createElement("span");
      date.className = "history-date";
      date.textContent = formatDate(entry.date);

      item.append(mode, time, entryMistakes, date);
      historyListEl.appendChild(item);
    }
    historyEmptyEl.hidden = history.length > 0;
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

  function shuffle(values) {
    for (let i = values.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [values[i], values[j]] = [values[j], values[i]];
    }
    return values;
  }

  function elapsedMs() {
    if (startTime === null) {
      return 0;
    }
    let elapsed = performance.now() - startTime - pausedTotal;
    if (paused && pauseAt !== null) {
      elapsed -= performance.now() - pauseAt;
    }
    return elapsed;
  }

  function tick() {
    if (startTime !== null && !finished && !paused) {
      timerEl.textContent = formatTime(elapsedMs());
      rafId = requestAnimationFrame(tick);
    } else {
      rafId = null;
    }
  }

  function handleClick(button, value) {
    if (finished || paused || button.classList.contains("done")) {
      return;
    }
    if (startTime === null) {
      startTime = performance.now();
      rafId = requestAnimationFrame(tick);
    }
    if (value === next) {
      button.classList.add("done");
      next += 1;
      nextEl.textContent = next <= MODES[size] ? String(next) : "--";
      progressBarEl.style.width = `${((next - 1) / MODES[size]) * 100}%`;
      if (next > MODES[size]) {
        finish();
      }
    } else {
      mistakes += 1;
      mistakesEl.textContent = String(mistakes);
      button.classList.remove("wrong");
      // Force a reflow so re-adding the class restarts the shake animation.
      void button.offsetWidth;
      button.classList.add("wrong");
    }
  }

  function finish() {
    finished = true;
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    const elapsed = elapsedMs();
    timerEl.textContent = formatTime(elapsed);
    const best = loadBest();
    const isNewRecord = best === null || elapsed < best;
    if (isNewRecord) {
      localStorage.setItem(bestKey(), String(elapsed));
    }

    const stats = loadStats();
    stats.games += 1;
    saveStats(stats);

    const history = loadHistory();
    history.unshift({ size, ms: elapsed, mistakes, date: Date.now() });
    saveHistory(history.slice(0, HISTORY_LIMIT));

    resultDetailEl.textContent = `模式 ${size}×${size} · 用时 ${formatTime(elapsed)} · 错误 ${mistakes} 次`;
    resultRecordEl.hidden = !isNewRecord;
    resultOverlay.hidden = false;
    renderBest();
  }

  function newGame() {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    next = 1;
    mistakes = 0;
    startTime = null;
    finished = false;
    paused = false;
    pauseAt = null;
    pausedTotal = 0;
    timerEl.textContent = "0.0s";
    nextEl.textContent = "1";
    mistakesEl.textContent = "0";
    modeLabelEl.textContent = `${size}×${size}`;
    progressBarEl.style.width = "0%";
    pauseOverlay.hidden = true;
    resultOverlay.hidden = true;
    renderBest();

    grid.innerHTML = "";
    grid.style.gridTemplateColumns = `repeat(${size}, minmax(0, 1fr))`;
    const values = shuffle(Array.from({ length: MODES[size] }, (_, i) => i + 1));
    for (const value of values) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "schulte-cell";
      button.textContent = String(value);
      button.addEventListener("click", () => handleClick(button, value));
      grid.appendChild(button);
    }
  }

  function startGame(nextSize) {
    if (!MODES[nextSize]) {
      return;
    }
    size = nextSize;
    localStorage.setItem(MODE_KEY, String(size));
    newGame();
    showView("game");
  }

  function backToMenu() {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    pauseOverlay.hidden = true;
    resultOverlay.hidden = true;
    showView("menu");
  }

  function pauseGame() {
    if (paused || finished || startTime === null) {
      return;
    }
    paused = true;
    pauseAt = performance.now();
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    pauseDetailEl.textContent = `当前用时 ${formatTime(elapsedMs())}`;
    pauseOverlay.hidden = false;
  }

  function resumeGame() {
    if (!paused) {
      return;
    }
    paused = false;
    pausedTotal += performance.now() - pauseAt;
    pauseAt = null;
    pauseOverlay.hidden = true;
    rafId = requestAnimationFrame(tick);
  }

  function openRules() {
    rulesModal.hidden = false;
  }

  function closeRules() {
    rulesModal.hidden = true;
  }

  for (const [key, button] of Object.entries(startButtons)) {
    button.addEventListener("click", () => startGame(Number(key)));
  }
  document.getElementById("btn-rules").addEventListener("click", openRules);
  document.getElementById("btn-close-rules").addEventListener("click", closeRules);
  document.getElementById("btn-records").addEventListener("click", () => showView("records"));
  document.getElementById("btn-back-menu").addEventListener("click", () => showView("menu"));
  document.getElementById("btn-menu").addEventListener("click", backToMenu);
  document.getElementById("btn-restart").addEventListener("click", newGame);
  document.getElementById("btn-pause").addEventListener("click", () => {
    if (paused) {
      resumeGame();
    } else {
      pauseGame();
    }
  });
  document.getElementById("btn-resume").addEventListener("click", resumeGame);
  document.getElementById("btn-pause-restart").addEventListener("click", newGame);
  document.getElementById("btn-pause-menu").addEventListener("click", backToMenu);
  document.getElementById("btn-again").addEventListener("click", newGame);
  document.getElementById("btn-result-menu").addEventListener("click", backToMenu);
  document.getElementById("btn-clear-history").addEventListener("click", () => {
    if (window.confirm("确定清空最近记录吗？各模式最佳成绩将保留。")) {
      saveHistory([]);
      renderRecords();
    }
  });

  rulesModal.addEventListener("click", (event) => {
    if (event.target === rulesModal) {
      closeRules();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
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
  });

  newGame();
  showView("menu");
})();

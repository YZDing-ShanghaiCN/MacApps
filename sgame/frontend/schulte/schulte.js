(() => {
  "use strict";

  const MODES = { 3: 9, 4: 16, 5: 25 };
  const MODE_KEY = "sgame-schulte-mode";
  const BEST_KEY_PREFIX = "sgame-schulte-best-";
  const LEGACY_BEST_KEY = "sgame-schulte-best";

  const grid = document.getElementById("grid");
  const timerEl = document.getElementById("timer");
  const nextEl = document.getElementById("next-number");
  const mistakesEl = document.getElementById("mistakes");
  const bestEl = document.getElementById("best");
  const resultEl = document.getElementById("result");
  const restartButton = document.getElementById("restart-button");
  const modeButtons = {
    3: document.getElementById("mode-3"),
    4: document.getElementById("mode-4"),
    5: document.getElementById("mode-5"),
  };

  let size = loadMode();
  let next = 1;
  let mistakes = 0;
  let startTime = null;
  let finished = false;
  let rafId = null;

  function loadMode() {
    const value = Number(localStorage.getItem(MODE_KEY));
    return MODES[value] ? value : 5;
  }

  function bestKey() {
    return BEST_KEY_PREFIX + size;
  }

  function loadBest() {
    let value = Number(localStorage.getItem(bestKey()));
    if (!(Number.isFinite(value) && value > 0) && size === 5) {
      // Fall back to the key used before per-mode best times existed.
      value = Number(localStorage.getItem(LEGACY_BEST_KEY));
    }
    return Number.isFinite(value) && value > 0 ? value : null;
  }

  function formatTime(ms) {
    return (ms / 1000).toFixed(1) + "s";
  }

  function renderBest() {
    const best = loadBest();
    bestEl.textContent = best === null ? "--" : formatTime(best);
  }

  function renderModeButtons() {
    for (const [key, button] of Object.entries(modeButtons)) {
      button.classList.toggle("selected", Number(key) === size);
    }
  }

  function shuffle(values) {
    for (let i = values.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [values[i], values[j]] = [values[j], values[i]];
    }
    return values;
  }

  function tick() {
    if (startTime !== null && !finished) {
      timerEl.textContent = formatTime(performance.now() - startTime);
      rafId = requestAnimationFrame(tick);
    }
  }

  function handleClick(button, value) {
    if (finished || button.classList.contains("done")) {
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
    const elapsed = performance.now() - startTime;
    timerEl.textContent = formatTime(elapsed);
    const best = loadBest();
    const isNewRecord = best === null || elapsed < best;
    if (isNewRecord) {
      localStorage.setItem(bestKey(), String(elapsed));
    }
    resultEl.textContent =
      `完成！用时 ${formatTime(elapsed)}，错误 ${mistakes} 次。` +
      (isNewRecord ? "新纪录！" : "");
    resultEl.hidden = false;
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
    timerEl.textContent = "0.0s";
    nextEl.textContent = "1";
    mistakesEl.textContent = "0";
    resultEl.hidden = true;
    renderBest();
    renderModeButtons();

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

  function selectMode(nextSize) {
    if (!MODES[nextSize]) {
      return;
    }
    size = nextSize;
    localStorage.setItem(MODE_KEY, String(size));
    newGame();
  }

  for (const [key, button] of Object.entries(modeButtons)) {
    button.addEventListener("click", () => selectMode(Number(key)));
  }
  restartButton.addEventListener("click", newGame);
  newGame();
})();

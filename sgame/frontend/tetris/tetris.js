(() => {
  "use strict";

  const COLS = 10;
  const ROWS = 20;
  const TILE = 30;
  const BEST_KEY = "sgame-tetris-highscore";
  const BASE_INTERVAL = 800;
  const MIN_INTERVAL = 100;
  const INTERVAL_DECAY = 0.85;
  const SOFT_DROP_INTERVAL = 40;
  const SCORES = [0, 100, 300, 500, 800];
  const HOLD_REPEAT_MS = 90;

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

  const canvas = document.getElementById("game");
  const ctx = canvas.getContext("2d");
  canvas.width = COLS * TILE;
  canvas.height = ROWS * TILE;

  const nextCanvas = document.getElementById("next-panel");
  const nextCtx = nextCanvas.getContext("2d");

  const scoreEl = document.getElementById("score");
  const bestEl = document.getElementById("best");
  const levelEl = document.getElementById("level");
  const overlayEl = document.getElementById("overlay");
  const overlayTitleEl = document.getElementById("overlay-title");
  const overlayDetailEl = document.getElementById("overlay-detail");
  const overlayButton = document.getElementById("overlay-button");

  let board = Array.from({ length: ROWS }, () => new Array(COLS).fill(null));
  let active = null;
  let nextShape = null;
  let bag = [];
  let score = 0;
  let best = loadBest();
  let lines = 0;
  let level = 1;
  let fallTimer = 0;
  let fallInterval = BASE_INTERVAL;
  let softDrop = false;
  let state = "attract";

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
    active = {
      shape: nextShape,
      rot: 0,
      row: -1,
      col: Math.floor((COLS - ROTS[nextShape][0].length) / 2),
    };
    nextShape = nextFromBag();
    if (collides(active.shape, active.rot, active.row, active.col)) {
      gameOver();
    }
  }

  function moveLeft() {
    if (active && !collides(active.shape, active.rot, active.row, active.col - 1)) {
      active.col -= 1;
    }
  }

  function moveRight() {
    if (active && !collides(active.shape, active.rot, active.row, active.col + 1)) {
      active.col += 1;
    }
  }

  function rotatePiece() {
    if (!active) {
      return;
    }
    const nextRot = (active.rot + 1) % 4;
    const kicks = [0, -1, 1, -2, 2];
    for (const dx of kicks) {
      if (!collides(active.shape, nextRot, active.row, active.col + dx)) {
        active.rot = nextRot;
        active.col += dx;
        return;
      }
    }
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
    clearLines();
    active = null;
    spawn();
  }

  function clearLines() {
    const full = [];
    for (let r = 0; r < ROWS; r += 1) {
      if (board[r].every((cell) => cell !== null)) {
        full.push(r);
      }
    }
    if (full.length === 0) {
      return;
    }
    const n = full.length;
    for (const r of full.reverse()) {
      board.splice(r, 1);
    }
    for (let i = 0; i < n; i += 1) {
      board.unshift(new Array(COLS).fill(null));
    }
    lines += n;
    level = Math.floor(lines / 10) + 1;
    fallInterval = Math.max(MIN_INTERVAL, BASE_INTERVAL * Math.pow(INTERVAL_DECAY, level - 1));
    score += SCORES[n] * level;
    saveBest();
    updateHud();
  }

  function softDropStep() {
    if (!active) {
      return;
    }
    if (!collides(active.shape, active.rot, active.row + 1, active.col)) {
      active.row += 1;
    } else {
      lockPiece();
    }
  }

  function gameOver() {
    state = "over";
    saveBest();
    overlayTitleEl.textContent = "GAME OVER";
    overlayDetailEl.textContent = `得分 ${score} · 最高分 ${best}`;
    overlayButton.textContent = "再来一局";
    overlayEl.hidden = false;
    updateHud();
  }

  function newGame() {
    board = Array.from({ length: ROWS }, () => new Array(COLS).fill(null));
    score = 0;
    lines = 0;
    level = 1;
    fallInterval = BASE_INTERVAL;
    fallTimer = 0;
    softDrop = false;
    bag = [];
    active = null;
    nextShape = nextFromBag();
    spawn();
    state = "playing";
    overlayEl.hidden = true;
    updateHud();
  }

  function updateHud() {
    scoreEl.textContent = String(score);
    bestEl.textContent = String(best);
    levelEl.textContent = String(level);
  }

  function tick(dt) {
    if (state !== "playing" || !active) {
      return;
    }
    fallTimer += dt * 1000;
    const interval = softDrop ? SOFT_DROP_INTERVAL : fallInterval;
    while (fallTimer >= interval && state === "playing") {
      fallTimer -= interval;
      softDropStep();
    }
  }

  function drawCell(target, x, y, size, color) {
    target.fillStyle = color;
    target.fillRect(x + 1, y + 1, size - 2, size - 2);
    target.fillStyle = "rgba(255, 255, 255, 0.25)";
    target.fillRect(x + 1, y + 1, size - 2, 4);
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

    for (let r = 0; r < ROWS; r += 1) {
      for (let c = 0; c < COLS; c += 1) {
        if (board[r][c]) {
          drawCell(ctx, c * TILE, r * TILE, TILE, board[r][c]);
        }
      }
    }

    if (active) {
      const m = ROTS[active.shape][active.rot];
      const color = COLORS[active.shape];
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

    renderNext();
  }

  function renderNext() {
    nextCtx.fillStyle = "#05060f";
    nextCtx.fillRect(0, 0, nextCanvas.width, nextCanvas.height);
    if (!nextShape) {
      return;
    }
    const m = ROTS[nextShape][0];
    const cell = 24;
    const ox = (nextCanvas.width - m.length * cell) / 2;
    const oy = (nextCanvas.height - m.length * cell) / 2;
    for (let r = 0; r < m.length; r += 1) {
      for (let c = 0; c < m.length; c += 1) {
        if (m[r][c] !== "X") {
          continue;
        }
        drawCell(nextCtx, ox + c * cell, oy + r * cell, cell, COLORS[nextShape]);
      }
    }
  }

  /* Input */

  document.addEventListener("keydown", (event) => {
    if (event.code === "KeyA") {
      event.preventDefault();
      moveLeft();
      return;
    }
    if (event.code === "KeyD") {
      event.preventDefault();
      moveRight();
      return;
    }
    if (event.code === "ShiftLeft" || event.code === "ShiftRight") {
      event.preventDefault();
      softDrop = true;
    }
  });

  document.addEventListener("keyup", (event) => {
    if (event.code === "ShiftLeft" || event.code === "ShiftRight") {
      softDrop = false;
    }
  });

  canvas.addEventListener("mousedown", (event) => {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    if (state === "playing") {
      rotatePiece();
    }
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

  bindHold(document.getElementById("btn-left"), moveLeft);
  bindHold(document.getElementById("btn-right"), moveRight);
  bindHold(document.getElementById("btn-drop"), softDropStep);
  document.getElementById("btn-rotate").addEventListener("pointerdown", (event) => {
    event.preventDefault();
    if (state === "playing") {
      rotatePiece();
    }
  });

  overlayButton.addEventListener("click", () => {
    newGame();
  });

  /* Boot */

  overlayTitleEl.textContent = "俄罗斯方块";
  overlayDetailEl.textContent = "A / D 移动 · 鼠标左键旋转 · 按住 Shift 加速";
  overlayButton.textContent = "开始游戏";
  updateHud();

  let lastTime = null;
  function frame(now) {
    requestAnimationFrame(frame);
    const dt = Math.min(lastTime === null ? 0 : (now - lastTime) / 1000, 0.05);
    lastTime = now;
    tick(dt);
    render();
  }
  requestAnimationFrame(frame);
})();

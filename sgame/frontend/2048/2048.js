(() => {
  "use strict";

  const SIZE = 4;
  const BEST_KEY = "sgame-2048-best";
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

  const boardEl = document.getElementById("board");
  const tileLayerEl = document.getElementById("tile-layer");
  const scoreEl = document.getElementById("score");
  const bestEl = document.getElementById("best");
  const overlayEl = document.getElementById("overlay");
  const overlayTitleEl = document.getElementById("overlay-title");
  const overlayDetailEl = document.getElementById("overlay-detail");
  const overlayContinueButton = document.getElementById("overlay-continue");
  const overlayRestartButton = document.getElementById("overlay-restart");
  const newGameButton = document.getElementById("new-game-button");

  let tiles = [];
  let nextId = 1;
  let score = 0;
  let best = 0;
  let won = false;
  let over = false;
  let keepPlaying = false;

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
    spawnTile();
    saveBest();
    if (!won && tiles.some((tile) => tile.value >= WIN_VALUE)) {
      won = true;
      showOverlay("win");
    } else if (!hasMoves()) {
      over = true;
      showOverlay("lose");
    }
    render();
  }

  function render() {
    scoreEl.textContent = score;
    bestEl.textContent = best;

    const seen = new Set();
    for (const tile of tiles) {
      seen.add(tile.id);
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
  }

  function showOverlay(type) {
    overlayTitleEl.textContent = type === "win" ? TEXT.winTitle : TEXT.loseTitle;
    overlayDetailEl.textContent =
      type === "win" ? TEXT.winDetail(score) : TEXT.loseDetail(score);
    overlayContinueButton.hidden = type !== "win";
    overlayEl.hidden = false;
  }

  function hideOverlay() {
    overlayEl.hidden = true;
  }

  function newGame() {
    tiles = [];
    score = 0;
    won = false;
    over = false;
    keepPlaying = false;
    hideOverlay();
    for (const el of tileEls.values()) {
      el.remove();
    }
    tileEls.clear();
    spawnTile();
    spawnTile();
    render();
  }

  document.addEventListener("keydown", (event) => {
    const dir = KEY_DIRS[event.key];
    if (!dir) {
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
      if (touchStart === null) {
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

  newGameButton.addEventListener("click", newGame);
  overlayRestartButton.addEventListener("click", newGame);
  overlayContinueButton.addEventListener("click", () => {
    keepPlaying = true;
    hideOverlay();
  });

  /* Boot */
  best = loadBest();
  newGame();
})();

(() => {
  "use strict";

  const DIFFICULTIES = {
    beginner: { rows: 9, cols: 9, mines: 10 },
    intermediate: { rows: 16, cols: 16, mines: 40 },
    expert: { rows: 16, cols: 30, mines: 99 },
  };
  const MAX_TIME = 999;
  const LONG_PRESS_MS = 400;

  const boardEl = document.getElementById("board");
  const mineCounterEl = document.getElementById("mine-counter");
  const timerEl = document.getElementById("timer");
  const faceButton = document.getElementById("face-button");
  const flagModeButton = document.getElementById("flag-mode-button");
  const messageEl = document.getElementById("message");
  const difficultyButtons = {
    beginner: document.getElementById("difficulty-beginner"),
    intermediate: document.getElementById("difficulty-intermediate"),
    expert: document.getElementById("difficulty-expert"),
  };

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

  function lose(explodedIndex) {
    gameOver = true;
    stopTimer();
    revealAllMines(explodedIndex);
    faceButton.textContent = "😵";
    messageEl.textContent = "踩到地雷了！点击笑脸再来一局。";
    messageEl.className = "message lose";
  }

  function checkWin() {
    if (revealedCount === rows * cols - mineTotal) {
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
      faceButton.textContent = "😎";
      messageEl.textContent = `胜利！用时 ${seconds} 秒。`;
      messageEl.className = "message win";
    }
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
    faceButton.textContent = "🙂";
    messageEl.textContent = "";
    messageEl.className = "message";
    updateMineCounter();

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

  faceButton.addEventListener("click", buildBoard);

  flagModeButton.addEventListener("click", () => {
    flagMode = !flagMode;
    flagModeButton.classList.toggle("selected", flagMode);
    flagModeButton.setAttribute("aria-pressed", String(flagMode));
  });

  for (const [key, button] of Object.entries(difficultyButtons)) {
    button.addEventListener("click", () => {
      if (difficultyKey === key) {
        buildBoard();
        return;
      }
      difficultyKey = key;
      for (const [otherKey, otherButton] of Object.entries(difficultyButtons)) {
        otherButton.classList.toggle("selected", otherKey === key);
      }
      buildBoard();
    });
  }

  buildBoard();
})();

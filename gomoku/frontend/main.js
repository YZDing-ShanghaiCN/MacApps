const boardElement = document.querySelector("#board");
const statusElement = document.querySelector("#status");
const messageElement = document.querySelector("#message");
const resetButton = document.querySelector("#reset-button");
const undoButton = document.querySelector("#undo-button");

let currentState = null;

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || "Request failed.");
  }

  return data;
}

function setMessage(text) {
  messageElement.textContent = text || "";
}

function playerLabel(playerName) {
  if (playerName === "Black") {
    return "黑棋";
  }

  if (playerName === "White") {
    return "白棋";
  }

  return "";
}

function friendlyErrorMessage(message) {
  if (message.includes("already occupied")) {
    return "这个位置已经有棋子了";
  }

  if (message.includes("outside the board")) {
    return "落子位置不在棋盘内";
  }

  if (message.includes("game is over")) {
    return "游戏已经结束，请重新开始";
  }

  if (message.includes("row and col")) {
    return "落子位置无效";
  }

  return message || "操作失败，请重试";
}

function updateStatus(state) {
  if (state.winner_name) {
    statusElement.textContent = `${playerLabel(state.winner_name)}胜`;
    return;
  }

  if (state.game_over) {
    statusElement.textContent = "平局";
    return;
  }

  statusElement.textContent = `当前：${playerLabel(state.current_player_name)}`;
}

function renderBoard(state) {
  boardElement.innerHTML = "";

  state.board.forEach((row, rowIndex) => {
    row.forEach((cell, colIndex) => {
      const isLastMove =
        state.last_move &&
        state.last_move.row === rowIndex &&
        state.last_move.col === colIndex;
      const button = document.createElement("button");
      button.type = "button";
      button.className = isLastMove ? "cell last-move" : "cell";
      button.dataset.row = rowIndex;
      button.dataset.col = colIndex;
      button.disabled = state.game_over || cell !== 0;
      button.setAttribute("aria-label", `Row ${rowIndex + 1}, column ${colIndex + 1}`);

      if (cell !== 0) {
        const stone = document.createElement("span");
        stone.className = cell === 1 ? "stone black" : "stone white";
        button.appendChild(stone);
      }

      boardElement.appendChild(button);
    });
  });
}

function render(state) {
  currentState = state;
  updateStatus(state);
  renderBoard(state);
}

async function loadState() {
  try {
    const state = await requestJson("/api/state");
    render(state);
    setMessage("");
  } catch (error) {
    setMessage(friendlyErrorMessage(error.message));
  }
}

async function playMove(row, col) {
  try {
    const state = await requestJson("/api/move", {
      method: "POST",
      body: JSON.stringify({ row, col }),
    });
    render(state);
    setMessage("");
  } catch (error) {
    setMessage(friendlyErrorMessage(error.message));
  }
}

boardElement.addEventListener("click", (event) => {
  const cell = event.target.closest(".cell");
  if (!cell || !boardElement.contains(cell) || !currentState) {
    return;
  }

  if (currentState.game_over || cell.disabled) {
    return;
  }

  playMove(Number(cell.dataset.row), Number(cell.dataset.col));
});

resetButton.addEventListener("click", async () => {
  try {
    const state = await requestJson("/api/reset", { method: "POST" });
    render(state);
    setMessage("");
  } catch (error) {
    setMessage(friendlyErrorMessage(error.message));
  }
});

undoButton.addEventListener("click", async () => {
  try {
    const state = await requestJson("/api/undo", { method: "POST" });
    render(state);
    setMessage("");
  } catch (error) {
    setMessage(friendlyErrorMessage(error.message));
  }
});

loadState();

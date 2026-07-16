const boardElement = document.querySelector("#board");
const modeStatusElement = document.querySelector("#mode-status");
const statusElement = document.querySelector("#status");
const timerElement = document.querySelector("#timer");
const messageElement = document.querySelector("#message");
const modeLocalButton = document.querySelector("#mode-local-button");
const modeAiButton = document.querySelector("#mode-ai-button");
const difficultyActionsElement = document.querySelector("#difficulty-actions");
const difficultySimpleButton = document.querySelector("#difficulty-simple-button");
const difficultyNormalButton = document.querySelector("#difficulty-normal-button");
const difficultyHardButton = document.querySelector("#difficulty-hard-button");
const createRoomButton = document.querySelector("#create-room-button");
const startButton = document.querySelector("#start-button");
const resetButton = document.querySelector("#reset-button");
const undoButton = document.querySelector("#undo-button");
const resultDialog = document.querySelector("#game-result-dialog");
const resultTitleElement = document.querySelector("#result-title");
const resultSummaryElement = document.querySelector("#result-summary");
const resultPrimaryButton = document.querySelector("#result-primary-button");
const resultSecondaryButton = document.querySelector("#result-secondary-button");
const resultCloseButton = document.querySelector("#result-close-button");

let currentState = null;
let stateReceivedAt = 0;
let requestInFlight = false;
let displayedResultKey = null;

const MODE_LABELS = {
  local_2p: "双人对战",
  vs_ai: "人机对战",
};

const STAR_POINTS_BY_SIZE = {
  15: new Set([
    "3,3", "3,7", "3,11",
    "7,3", "7,7", "7,11",
    "11,3", "11,7", "11,11",
  ]),
};

async function requestJson(url, options = {}) {
  const headers = {
    ...(options.headers || {}),
  };

  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(url, {
    ...options,
    headers: {
      ...headers,
    },
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

function modeLabel(mode) {
  return MODE_LABELS[mode] || "未知模式";
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

  if (message.includes("Mode must be")) {
    return "模式无效";
  }

  if (message.includes("difficulty must be")) {
    return "AI 难度无效";
  }

  if (message.includes("currently thinking")) {
    return "AI 正在思考，请稍候";
  }

  return message || "操作失败，请重试";
}

function updateMode(state) {
  const mode = state.mode || "local_2p";
  modeStatusElement.textContent = `模式：${modeLabel(mode)}`;
  modeLocalButton.setAttribute("aria-pressed", String(mode === "local_2p"));
  modeAiButton.setAttribute("aria-pressed", String(mode === "vs_ai"));
  const aiMode = mode === "vs_ai";
  const difficulty = state.ai_difficulty || "simple";
  const busy = requestInFlight || state.ai_thinking;
  difficultyActionsElement.hidden = !aiMode;
  difficultySimpleButton.disabled = !aiMode || busy;
  difficultySimpleButton.setAttribute(
    "aria-pressed",
    String(aiMode && difficulty === "simple"),
  );
  difficultyNormalButton.disabled = !aiMode || busy;
  difficultyNormalButton.setAttribute(
    "aria-pressed",
    String(aiMode && difficulty === "normal"),
  );
  difficultyHardButton.disabled = true;
  startButton.disabled = busy || state.timer_running || state.game_over;
}

function updateStatus(state) {
  if (state.ai_thinking) {
    statusElement.textContent = "普通 AI 思考中…";
    return;
  }
  if (state.winner_name) {
    statusElement.textContent = `${playerLabel(state.winner_name)}胜`;
    return;
  }

  if (state.game_over) {
    statusElement.textContent = "平局";
    return;
  }

  if (!state.timer_running) {
    statusElement.textContent = "准备中，请点击开始对局";
    return;
  }

  statusElement.textContent = `当前：${playerLabel(state.current_player_name)}`;
}

function formatDuration(seconds) {
  const totalSeconds = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(totalSeconds / 60);
  const remainder = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function displayedTime(state, color) {
  let elapsed = Number(state.time_spent?.[color] || 0);
  const activeColor = state.current_player === 1 ? "black" : "white";
  if (state.timer_running && !state.game_over && color === activeColor) {
    elapsed += (Date.now() - stateReceivedAt) / 1000;
  }
  return elapsed;
}

function updateTimer(state) {
  timerElement.textContent = [
    `黑棋 ${formatDuration(displayedTime(state, "black"))}`,
    `白棋 ${formatDuration(displayedTime(state, "white"))}`,
  ].join("　");
}

function renderBoard(state) {
  const boardSize = state.size || state.board.length;
  const starPoints = STAR_POINTS_BY_SIZE[boardSize] || new Set();
  boardElement.style.setProperty("--board-size", String(boardSize));
  boardElement.style.setProperty("--board-span", String(Math.max(boardSize - 1, 1)));
  boardElement.setAttribute("aria-label", `${boardSize}×${boardSize} 五子棋棋盘`);
  boardElement.innerHTML = "";
  const winningCells = new Set(
    (state.winning_line || []).map(({ row, col }) => `${row},${col}`),
  );

  state.board.forEach((row, rowIndex) => {
    row.forEach((cell, colIndex) => {
      const isLastMove =
        state.last_move &&
        state.last_move.row === rowIndex &&
        state.last_move.col === colIndex;
      const button = document.createElement("button");
      button.type = "button";
      button.className = [
        "cell",
        starPoints.has(`${rowIndex},${colIndex}`) ? "star-point" : "",
        isLastMove ? "last-move" : "",
        winningCells.has(`${rowIndex},${colIndex}`) ? "winning-cell" : "",
        cell === 0 && state.timer_running && !state.game_over && !requestInFlight && !state.ai_thinking
          ? (state.current_player === 1 ? "preview-black" : "preview-white")
          : "",
      ].filter(Boolean).join(" ");
      button.dataset.row = rowIndex;
      button.dataset.col = colIndex;
      button.style.setProperty("--row-index", String(rowIndex));
      button.style.setProperty("--col-index", String(colIndex));
      button.disabled = requestInFlight || state.ai_thinking || state.game_over || !state.timer_running || cell !== 0;
      button.setAttribute("aria-label", `第 ${rowIndex + 1} 行，第 ${colIndex + 1} 列`);

      if (cell !== 0) {
        const stone = document.createElement("span");
        stone.className = cell === 1 ? "stone black" : "stone white";
        button.appendChild(stone);
      }

      boardElement.appendChild(button);
    });
  });
}

function resultKey(state) {
  return `${state.move_count}:${state.winner_name || "draw"}`;
}

function updateResultDialog(state) {
  if (!state.game_over) {
    displayedResultKey = null;
    return;
  }

  resultTitleElement.textContent = state.winner_name
    ? `${playerLabel(state.winner_name)}胜`
    : "平局";
  resultSummaryElement.textContent = [
    `黑棋累计 ${formatDuration(state.time_spent?.black || 0)}`,
    `白棋累计 ${formatDuration(state.time_spent?.white || 0)}`,
  ].join("　");

  const key = resultKey(state);
  if (displayedResultKey !== key) {
    displayedResultKey = key;
    if (!resultDialog.open) {
      resultDialog.showModal();
    }
  }
}

function render(state) {
  currentState = state;
  stateReceivedAt = Date.now();
  updateMode(state);
  updateStatus(state);
  updateTimer(state);
  renderBoard(state);
  updateResultDialog(state);
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
  if (requestInFlight) {
    return;
  }

  requestInFlight = true;
  render(currentState);
  if (currentState.mode === "vs_ai") {
    setMessage(`${currentState.ai_difficulty === "normal" ? "普通" : "简单"} AI 思考中…`);
  }
  try {
    const state = await requestJson("/api/move", {
      method: "POST",
      body: JSON.stringify({ row, col }),
    });
    render(state);
    setMessage("");
  } catch (error) {
    setMessage(friendlyErrorMessage(error.message));
  } finally {
    requestInFlight = false;
    if (currentState) {
      render(currentState);
    }
  }
}

async function startGame() {
  if (requestInFlight) {
    return;
  }

  requestInFlight = true;
  try {
    const state = await requestJson("/api/start", { method: "POST" });
    render(state);
    setMessage("");
  } catch (error) {
    setMessage(friendlyErrorMessage(error.message));
  } finally {
    requestInFlight = false;
  }
}

async function createPrivateRoom() {
  if (requestInFlight) {
    return;
  }

  requestInFlight = true;
  try {
    const room = await requestJson("/api/rooms", { method: "POST" });
    const invitationRecord = JSON.stringify({
      inviteUrl: room.invite_url,
      savedAt: Date.now(),
    });
    sessionStorage.setItem(
      `gomoku.room.${room.room_id}.invite_url`,
      invitationRecord,
    );
    localStorage.setItem(`gomoku.room.${room.room_id}.invite_url`, invitationRecord);
    window.location.assign(room.owner_url);
  } catch (error) {
    setMessage(friendlyErrorMessage(error.message));
  } finally {
    requestInFlight = false;
  }
}

async function resetGame() {
  const state = await requestJson("/api/reset", { method: "POST" });
  render(state);
  setMessage("");
}

boardElement.addEventListener("click", (event) => {
  const cell = event.target.closest(".cell");
  if (!cell || !boardElement.contains(cell) || !currentState) {
    return;
  }

  if (requestInFlight || currentState.game_over || cell.disabled) {
    return;
  }

  playMove(Number(cell.dataset.row), Number(cell.dataset.col));
});

async function changeMode(mode) {
  if (requestInFlight) {
    return;
  }
  requestInFlight = true;
  try {
    const state = await requestJson("/api/mode", {
      method: "POST",
      body: JSON.stringify({ mode }),
    });
    render(state);
    setMessage("");
  } catch (error) {
    setMessage(friendlyErrorMessage(error.message));
  } finally {
    requestInFlight = false;
    if (currentState) {
      render(currentState);
    }
  }
}

async function changeDifficulty(difficulty) {
  if (requestInFlight) {
    return;
  }
  requestInFlight = true;
  try {
    const state = await requestJson("/api/difficulty", {
      method: "POST",
      body: JSON.stringify({ difficulty }),
    });
    render(state);
    setMessage(`当前 AI 难度：${difficulty === "normal" ? "普通" : "简单"}`);
  } catch (error) {
    setMessage(friendlyErrorMessage(error.message));
  } finally {
    requestInFlight = false;
    if (currentState) {
      render(currentState);
    }
  }
}

modeLocalButton.addEventListener("click", () => {
  changeMode("local_2p");
});

modeAiButton.addEventListener("click", () => {
  changeMode("vs_ai");
});

difficultySimpleButton.addEventListener("click", () => {
  changeDifficulty("simple");
});

difficultyNormalButton.addEventListener("click", () => {
  changeDifficulty("normal");
});

createRoomButton.addEventListener("click", () => {
  createPrivateRoom();
});

startButton.addEventListener("click", () => {
  startGame();
});

resetButton.addEventListener("click", async () => {
  if (!window.confirm("确定要重新开始吗？当前棋局和累计用时将被清空。")) {
    return;
  }
  try {
    await resetGame();
  } catch (error) {
    setMessage(friendlyErrorMessage(error.message));
  }
});

resultPrimaryButton.addEventListener("click", async () => {
  try {
    await resetGame();
    resultDialog.close();
  } catch (error) {
    setMessage(friendlyErrorMessage(error.message));
  }
});

resultSecondaryButton.addEventListener("click", () => {
  resultDialog.close();
});

resultCloseButton.addEventListener("click", () => {
  resultDialog.close();
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
window.setInterval(() => {
  if (currentState) {
    updateTimer(currentState);
  }
}, 250);

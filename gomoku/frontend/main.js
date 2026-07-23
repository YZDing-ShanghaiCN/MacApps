const boardElement = document.querySelector("#board");
const modeStatusElement = document.querySelector("#mode-status");
const statusElement = document.querySelector("#status");
const timerElement = document.querySelector("#timer");
const blackPlayerCard = document.querySelector("#black-player-card");
const whitePlayerCard = document.querySelector("#white-player-card");
const blackRoleElement = document.querySelector("#black-role");
const whiteRoleElement = document.querySelector("#white-role");
const blackStateElement = document.querySelector("#black-state");
const whiteStateElement = document.querySelector("#white-state");
const blackTimeElement = document.querySelector("#black-time");
const whiteTimeElement = document.querySelector("#white-time");
const messageElement = document.querySelector("#message");
const modeLocalButton = document.querySelector("#mode-local-button");
const modeAiButton = document.querySelector("#mode-ai-button");
const difficultyActionsElement = document.querySelector("#difficulty-actions");
const difficultySimpleButton = document.querySelector("#difficulty-simple-button");
const difficultyNormalButton = document.querySelector("#difficulty-normal-button");
const difficultyHardButton = document.querySelector("#difficulty-hard-button");
const colorActionsElement = document.querySelector("#color-actions");
const colorBlackButton = document.querySelector("#color-black-button");
const colorWhiteButton = document.querySelector("#color-white-button");
const colorRandomButton = document.querySelector("#color-random-button");
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
const aiDebugPanel = document.querySelector("#ai-debug-panel");
const aiDebugSummaryElement = document.querySelector("#ai-debug-summary");
const aiDebugCandidatesElement = document.querySelector("#ai-debug-candidates");
const copyDebugButton = document.querySelector("#copy-debug-button");
const downloadDebugButton = document.querySelector("#download-debug-button");

let currentState = null;
let stateReceivedAt = 0;
let requestInFlight = false;
let aiPollInFlight = false;
let displayedResultKey = null;

const LOCAL_SESSION_STORAGE_KEY = "gomoku.local.session_id";
let localSessionId = sessionStorage.getItem(LOCAL_SESSION_STORAGE_KEY);
if (!localSessionId) {
  localSessionId = globalThis.crypto?.randomUUID?.() ||
    `local_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  sessionStorage.setItem(LOCAL_SESSION_STORAGE_KEY, localSessionId);
}

const MODE_LABELS = {
  local_2p: "双人对战",
  vs_ai: "人机对战",
};

const DIFFICULTY_LABELS = {
  simple: "简单",
  normal: "普通",
  hard: "困难",
};

const DECISION_LABELS = {
  not_searched: "尚未决策",
  no_legal_move: "无合法落点",
  immediate_win: "立即获胜",
  immediate_block: "阻挡对手立即获胜",
  vcf_forced_win: "连续冲四获胜",
  defensive_vcf: "化解连续冲四",
  iterative_deepening: "迭代加深搜索",
  legal_fallback: "合法落点兜底",
  nearby_fallback: "邻域落点兜底",
  empty_board_center: "空棋盘中心",
  grow_isolated_own_stone: "延伸己方孤子",
  block_isolated_opponent_stone: "贴近对方孤子",
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
    "X-Gomoku-Session": localSessionId,
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

  if (message.includes("Human color must be")) {
    return "棋色选择无效";
  }

  if (message.includes("currently thinking")) {
    return "AI 正在思考，请稍候";
  }

  return message || "操作失败，请重试";
}

function updateMode(state) {
  const mode = state.mode || "local_2p";
  const resolvedColor = state.human_player === 1
    ? " · 你执黑"
    : (state.human_player === 2 ? " · 你执白" : "");
  modeStatusElement.textContent = `模式：${modeLabel(mode)}${resolvedColor}`;
  modeLocalButton.setAttribute("aria-pressed", String(mode === "local_2p"));
  modeAiButton.setAttribute("aria-pressed", String(mode === "vs_ai"));
  const aiMode = mode === "vs_ai";
  const difficulty = state.ai_difficulty || "simple";
  const busy = requestInFlight || state.ai_thinking;
  difficultyActionsElement.hidden = !aiMode;
  colorActionsElement.hidden = !aiMode;
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
  const humanColor = state.human_color_choice || "black";
  for (const [button, color] of [
    [colorBlackButton, "black"],
    [colorWhiteButton, "white"],
    [colorRandomButton, "random"],
  ]) {
    button.disabled = !aiMode || busy;
    button.setAttribute("aria-pressed", String(aiMode && humanColor === color));
  }
  startButton.disabled = busy || state.timer_running || state.game_over;
}

function updateStatus(state) {
  if (state.ai_thinking) {
    const difficulty = DIFFICULTY_LABELS[state.ai_difficulty] || "AI";
    statusElement.textContent = `${difficulty} AI 思考中…`;
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
  const blackTime = formatDuration(displayedTime(state, "black"));
  const whiteTime = formatDuration(displayedTime(state, "white"));
  blackTimeElement.textContent = blackTime;
  whiteTimeElement.textContent = whiteTime;
  timerElement.textContent = `黑棋 ${blackTime}　白棋 ${whiteTime}`;
}

function updatePlayerCards(state) {
  const aiMode = state.mode === "vs_ai";
  const difficulty = DIFFICULTY_LABELS[state.ai_difficulty] || "AI";
  if (aiMode) {
    blackRoleElement.textContent = state.ai_player === 1 ? `${difficulty} AI` : "你";
    whiteRoleElement.textContent = state.ai_player === 2 ? `${difficulty} AI` : "你";
  } else {
    blackRoleElement.textContent = "玩家一";
    whiteRoleElement.textContent = "玩家二";
  }

  for (const [card, stateElement, player] of [
    [blackPlayerCard, blackStateElement, 1],
    [whitePlayerCard, whiteStateElement, 2],
  ]) {
    const active = state.timer_running && !state.game_over && state.current_player === player;
    const winner = state.game_over && state.winner === player;
    const thinking = state.ai_thinking && state.ai_player === player;
    card.classList.toggle("is-active", active);
    card.classList.toggle("is-winner", winner);
    card.classList.toggle("is-thinking", thinking);
    card.setAttribute("aria-current", active ? "true" : "false");

    if (winner) {
      stateElement.textContent = "胜方";
    } else if (thinking) {
      stateElement.textContent = "思考中…";
    } else if (state.game_over) {
      stateElement.textContent = "本局结束";
    } else if (!state.timer_running) {
      stateElement.textContent = "等待开始";
    } else if (active) {
      stateElement.textContent = "行棋中";
    } else {
      stateElement.textContent = "等待对方";
    }
  }
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
        cell === 0 && state.timer_running && !state.game_over && !requestInFlight && !state.ai_thinking && state.current_player !== state.ai_player
          ? (state.current_player === 1 ? "preview-black" : "preview-white")
          : "",
      ].filter(Boolean).join(" ");
      button.dataset.row = rowIndex;
      button.dataset.col = colIndex;
      button.style.setProperty("--row-index", String(rowIndex));
      button.style.setProperty("--col-index", String(colIndex));
      button.disabled = requestInFlight || state.ai_thinking || state.game_over || !state.timer_running || cell !== 0 || state.current_player === state.ai_player;
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

function updateAiDebug(state) {
  const visible = state.mode === "vs_ai";
  aiDebugPanel.hidden = !visible;
  if (!visible) {
    return;
  }
  const stats = state.ai_search_stats;
  const decision = state.ai_decision;
  if (!stats) {
    aiDebugSummaryElement.textContent = [
      "简单 AI：规则策略",
      `原因 ${DECISION_LABELS[decision?.reason] || decision?.reason || "尚未决策"}`,
    ].join("　");
  } else {
    aiDebugSummaryElement.textContent = [
      `深度 ${stats.completed_depth}`,
      `节点 ${stats.nodes}`,
      `静态延伸 ${stats.quiescence_nodes}`,
      `耗时 ${Number(stats.elapsed_ms || 0).toFixed(1)}ms`,
      `VCF ${stats.vcf_found ? "进攻命中" : (stats.defensive_vcf_detected ? "防守命中" : "未命中")}`,
      stats.timed_out ? "达到预算" : "完整结束",
      `原因 ${DECISION_LABELS[decision?.reason] || decision?.reason || "尚未决策"}`,
    ].join("　");
  }
  const candidates = decision?.candidates || [];
  aiDebugCandidatesElement.innerHTML = "";
  if (!candidates.length) {
    const item = document.createElement("li");
    item.textContent = "完成一次 AI 落子后显示候选";
    aiDebugCandidatesElement.appendChild(item);
    return;
  }
  candidates.slice(0, 3).forEach((candidate, index) => {
    const item = document.createElement("li");
    const move = candidate.move || [];
    item.textContent = `#${index + 1}　(${Number(move[0]) + 1}, ${Number(move[1]) + 1})　评分 ${candidate.score}`;
    aiDebugCandidatesElement.appendChild(item);
  });
}

function render(state) {
  currentState = state;
  stateReceivedAt = Date.now();
  updateMode(state);
  updateStatus(state);
  updateTimer(state);
  updatePlayerCards(state);
  renderBoard(state);
  updateResultDialog(state);
  updateAiDebug(state);
}

async function loadDebugPosition() {
  return requestJson("/api/debug-position");
}

async function copyDebugPosition() {
  try {
    const snapshot = await loadDebugPosition();
    const text = JSON.stringify(snapshot, null, 2);
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      const copied = document.execCommand("copy");
      textarea.remove();
      if (!copied) {
        throw new Error("浏览器不允许复制，请使用下载 JSON");
      }
    }
    setMessage("问题局面已复制，可直接发送用于复现");
  } catch (error) {
    setMessage(friendlyErrorMessage(error.message));
  }
}

async function downloadDebugPosition() {
  try {
    const snapshot = await loadDebugPosition();
    const blob = new Blob([JSON.stringify(snapshot, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `gomoku-position-${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(url);
    setMessage("问题局面 JSON 已生成");
  } catch (error) {
    setMessage(friendlyErrorMessage(error.message));
  }
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

async function pollAiState() {
  if (aiPollInFlight || !currentState?.ai_thinking) {
    return;
  }
  aiPollInFlight = true;
  try {
    const wasThinking = currentState.ai_thinking;
    const state = await requestJson("/api/state");
    render(state);
    if (wasThinking && !state.ai_thinking) {
      setMessage(state.ai_error ? friendlyErrorMessage(state.ai_error) : "");
    }
  } catch (error) {
    setMessage(friendlyErrorMessage(error.message));
  } finally {
    aiPollInFlight = false;
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
    if (currentState) {
      render(currentState);
    }
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

function confirmStateReset(actionLabel) {
  if (!currentState || currentState.move_count === 0) {
    return true;
  }
  return window.confirm(`${actionLabel}会清空当前棋局和累计用时，确定继续吗？`);
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
  if (currentState?.mode === mode || !confirmStateReset("切换对战模式")) {
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
  if (currentState?.ai_difficulty === difficulty || !confirmStateReset("切换 AI 难度")) {
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

async function changeHumanColor(humanColor) {
  if (requestInFlight) {
    return;
  }
  if (currentState?.human_color_choice === humanColor || !confirmStateReset("切换棋色")) {
    return;
  }
  requestInFlight = true;
  try {
    const state = await requestJson("/api/ai-color", {
      method: "POST",
      body: JSON.stringify({ human_color: humanColor }),
    });
    render(state);
    const resolved = state.human_player === 1 ? "黑棋" : "白棋";
    setMessage(`本局你执${resolved}`);
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

colorBlackButton.addEventListener("click", () => {
  changeHumanColor("black");
});

colorWhiteButton.addEventListener("click", () => {
  changeHumanColor("white");
});

colorRandomButton.addEventListener("click", () => {
  changeHumanColor("random");
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

copyDebugButton.addEventListener("click", copyDebugPosition);
downloadDebugButton.addEventListener("click", downloadDebugPosition);

loadState();
window.setInterval(() => {
  if (currentState) {
    updateTimer(currentState);
    pollAiState();
  }
}, 250);

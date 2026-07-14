const boardElement = document.querySelector("#board");
const roomStatusElement = document.querySelector("#room-status");
const statusElement = document.querySelector("#status");
const timerElement = document.querySelector("#timer");
const messageElement = document.querySelector("#message");
const lobbyPanel = document.querySelector("#lobby-panel");
const gamePanel = document.querySelector("#game-panel");
const participantStatusElement = document.querySelector("#participant-status");
const configurationSummaryElement = document.querySelector("#configuration-summary");
const guestSettingsElement = document.querySelector("#guest-settings");
const ownerConfirmationElement = document.querySelector("#owner-confirmation");
const submitConfigurationButton = document.querySelector("#submit-configuration-button");
const acceptConfigurationButton = document.querySelector("#accept-configuration-button");
const shareInviteButton = document.querySelector("#share-invite-button");
const reconnectButton = document.querySelector("#reconnect-button");
const copyInviteButton = document.querySelector("#copy-invite-button");
const undoButton = document.querySelector("#undo-button");
const rematchButton = document.querySelector("#rematch-button");
const inviteDialog = document.querySelector("#invite-dialog");
const inviteCloseButton = document.querySelector("#invite-close-button");
const inviteSavedButton = document.querySelector("#invite-saved-button");
const inviteQrImage = document.querySelector("#invite-qr-image");
const inviteLinkPreview = document.querySelector("#invite-link-preview");
const resultDialog = document.querySelector("#game-result-dialog");
const resultTitleElement = document.querySelector("#result-title");
const resultSummaryElement = document.querySelector("#result-summary");
const resultPrimaryButton = document.querySelector("#result-primary-button");
const resultSecondaryButton = document.querySelector("#result-secondary-button");
const resultCloseButton = document.querySelector("#result-close-button");
const guestColorButtons = document.querySelectorAll("[data-guest-color]");
const firstPlayerButtons = document.querySelectorAll("[data-first-player]");

const roomId = window.location.pathname.split("/").filter(Boolean).at(-1);
const roomStorageKey = `gomoku.room.${roomId}.token`;
const inviteStorageKey = `gomoku.room.${roomId}.invite_url`;
const tokenFromUrl = new URLSearchParams(window.location.hash.slice(1)).get("token");

let token = tokenFromUrl || sessionStorage.getItem(roomStorageKey);
let socket = null;
let currentState = null;
let stateReceivedAt = 0;
let selectedGuestColor = "black";
let selectedFirstPlayer = "black";
let reconnectTimer = null;
let inviteQrObjectUrl = null;
let invitePrompted = false;
let displayedResultKey = null;

if (tokenFromUrl) {
  sessionStorage.setItem(roomStorageKey, tokenFromUrl);
  window.history.replaceState({}, "", window.location.pathname);
}

function storedInviteUrl() {
  const stored = localStorage.getItem(inviteStorageKey) || sessionStorage.getItem(inviteStorageKey);
  if (!stored) {
    return null;
  }
  try {
    const record = JSON.parse(stored);
    return typeof record.inviteUrl === "string" ? record.inviteUrl : null;
  } catch {
    return stored;
  }
}

function setMessage(message) {
  messageElement.textContent = message || "";
}

function colorLabel(player) {
  return player === 1 ? "黑棋" : "白棋";
}

function roleLabel(role) {
  return role === "owner" ? "房主" : "受邀者";
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

function configurationText(configuration) {
  if (!configuration) {
    return "尚未确定棋色与先手。";
  }
  return [
    `受邀者执${colorLabel(configuration.guest_player)}`,
    `${colorLabel(configuration.first_player)}先手`,
  ].join("，");
}

function updateLobby(state) {
  const { phase, participants, configuration, you } = state;
  participantStatusElement.textContent = [
    `房主：${participants.owner_connected ? "已连接" : "未连接"}`,
    `受邀者：${participants.guest_connected ? "已连接" : "等待加入"}`,
  ].join("　");
  configurationSummaryElement.textContent = configurationText(configuration);
  guestSettingsElement.hidden = you.role !== "guest" || ["playing", "finished"].includes(phase);
  ownerConfirmationElement.hidden = !(
    you.role === "owner" && phase === "waiting_for_owner_confirmation"
  );
  submitConfigurationButton.disabled = phase !== "waiting_for_configuration" && phase !== "waiting_for_owner_confirmation";
  acceptConfigurationButton.disabled = phase !== "waiting_for_owner_confirmation" || !(
    participants.owner_connected && participants.guest_connected
  );

  if (phase === "waiting_for_guest") {
    statusElement.textContent = "等待好友通过邀请链接加入";
  } else if (phase === "waiting_for_configuration") {
    statusElement.textContent = you.role === "guest" ? "请选择棋色和先手" : "等待受邀者选择棋色和先手";
  } else if (phase === "waiting_for_owner_confirmation") {
    statusElement.textContent = you.role === "owner" ? "请确认设置并开始" : "等待房主确认并开始";
  }
}

function updateGameStatus(state) {
  if (state.paused_for_disconnect) {
    statusElement.textContent = "对方暂时断线，计时已暂停";
    return;
  }
  if (state.winner) {
    statusElement.textContent = `${colorLabel(state.winner)}胜`;
    return;
  }
  if (state.game_over) {
    statusElement.textContent = "平局";
    return;
  }
  statusElement.textContent = state.you.player === state.current_player ? "轮到你落子" : "等待对方落子";
}

function updateConnectionState(state) {
  const bothPlayersConnected = state.participants.owner_connected && state.participants.guest_connected;
  if (state.paused_for_disconnect) {
    roomStatusElement.dataset.connectionState = "paused";
  } else if (bothPlayersConnected) {
    roomStatusElement.dataset.connectionState = "online";
  } else {
    roomStatusElement.dataset.connectionState = "waiting";
  }
}

function renderBoard(state) {
  boardElement.innerHTML = "";
  const winningCells = new Set(
    (state.winning_line || []).map(({ row, col }) => `${row},${col}`),
  );
  const canMove = state.phase === "playing" &&
    !state.paused_for_disconnect &&
    state.you.player === state.current_player;

  state.board.forEach((row, rowIndex) => {
    row.forEach((cell, colIndex) => {
      const button = document.createElement("button");
      const isLastMove = state.move_history.length > 0 &&
        state.move_history.at(-1).row === rowIndex &&
        state.move_history.at(-1).col === colIndex;
      button.type = "button";
      button.className = [
        "cell",
        isLastMove ? "last-move" : "",
        winningCells.has(`${rowIndex},${colIndex}`) ? "winning-cell" : "",
        canMove ? (state.current_player === 1 ? "preview-black" : "preview-white") : "",
      ].filter(Boolean).join(" ");
      button.dataset.row = rowIndex;
      button.dataset.col = colIndex;
      button.disabled = !canMove || cell !== 0;
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
  return `${state.move_history.length}:${state.winner || "draw"}`;
}

function updateResultDialog(state) {
  if (state.phase !== "finished") {
    displayedResultKey = null;
    if (resultDialog.open) {
      resultDialog.close();
    }
    return;
  }

  resultTitleElement.textContent = state.winner ? `${colorLabel(state.winner)}胜` : "平局";
  resultSummaryElement.textContent = [
    `黑棋累计 ${formatDuration(state.time_spent?.black || 0)}`,
    `白棋累计 ${formatDuration(state.time_spent?.white || 0)}`,
  ].join("　");
  resultPrimaryButton.textContent = rematchButton.textContent;
  resultPrimaryButton.disabled = rematchButton.disabled;

  const key = resultKey(state);
  if (displayedResultKey !== key) {
    displayedResultKey = key;
    if (!resultDialog.open) {
      resultDialog.showModal();
    }
  }
}

function updateActionButtons(state) {
  const { you, undo_requested_by: undoRequestedBy, rematch_requested_by: rematchRequestedBy } = state;
  const bothPlayersConnected = state.participants.owner_connected && state.participants.guest_connected;
  undoButton.hidden = state.phase !== "playing";
  if (undoRequestedBy === null) {
    undoButton.textContent = "请求悔棋";
    undoButton.disabled = state.move_history.length === 0 || !bothPlayersConnected;
  } else if (undoRequestedBy === you.role) {
    undoButton.textContent = "等待对方确认悔棋";
    undoButton.disabled = true;
  } else {
    undoButton.textContent = "接受悔棋";
    undoButton.disabled = !bothPlayersConnected;
  }

  rematchButton.hidden = state.phase !== "finished";
  if (rematchRequestedBy === null) {
    rematchButton.textContent = "请求再来一局";
    rematchButton.disabled = !bothPlayersConnected;
  } else if (rematchRequestedBy === you.role) {
    rematchButton.textContent = "等待对方确认再来一局";
    rematchButton.disabled = true;
  } else {
    rematchButton.textContent = "接受再来一局";
    rematchButton.disabled = !bothPlayersConnected;
  }
}

function render(state) {
  currentState = state;
  stateReceivedAt = Date.now();
  roomStatusElement.textContent = `房间已连接 · 你是${roleLabel(state.you.role)}`;
  updateConnectionState(state);
  shareInviteButton.hidden = state.you.role !== "owner";
  updateTimer(state);
  updateLobby(state);
  const isGameVisible = state.phase === "playing" || state.phase === "finished";
  lobbyPanel.hidden = isGameVisible;
  gamePanel.hidden = !isGameVisible;
  if (isGameVisible) {
    updateGameStatus(state);
    renderBoard(state);
    updateActionButtons(state);
  }
  updateResultDialog(state);

  if (state.configuration && state.you.role === "guest") {
    selectedGuestColor = state.configuration.guest_player === 1 ? "black" : "white";
    selectedFirstPlayer = state.configuration.first_player === 1 ? "black" : "white";
    updateSelectionButtons();
  }

  if (state.you.role === "owner" && !invitePrompted && storedInviteUrl()) {
    invitePrompted = true;
    window.setTimeout(openInviteDialog, 0);
  }
}

function updateSelectionButtons() {
  guestColorButtons.forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.guestColor === selectedGuestColor));
  });
  firstPlayerButtons.forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.firstPlayer === selectedFirstPlayer));
  });
}

function send(message) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    setMessage("连接已断开，正在重连。");
    return;
  }
  socket.send(JSON.stringify(message));
}

async function openInviteDialog() {
  const inviteUrl = storedInviteUrl();
  if (!inviteUrl) {
    setMessage("未找到邀请链接。请在创建房间时保存链接。" );
    return;
  }

  inviteLinkPreview.textContent = inviteUrl;
  inviteQrImage.removeAttribute("src");
  inviteQrImage.alt = "正在生成邀请二维码";
  if (!inviteDialog.open) {
    inviteDialog.showModal();
  }

  try {
    const response = await fetch("/api/room-invite-qr", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ invite_url: inviteUrl }),
    });
    const data = await response.text();
    if (!response.ok) {
      throw new Error(data ? JSON.parse(data).error : "二维码生成失败。" );
    }
    if (inviteQrObjectUrl) {
      URL.revokeObjectURL(inviteQrObjectUrl);
    }
    inviteQrObjectUrl = URL.createObjectURL(new Blob([data], { type: "image/svg+xml" }));
    inviteQrImage.src = inviteQrObjectUrl;
    inviteQrImage.alt = "私人房间邀请二维码";
  } catch (error) {
    inviteQrImage.alt = "二维码生成失败";
    setMessage(error.message || "二维码生成失败，请复制邀请链接发送。" );
  }
}

function connect() {
  if (!token) {
    roomStatusElement.textContent = "邀请链接无效或已失效";
    roomStatusElement.dataset.connectionState = "invalid";
    return;
  }
  if (socket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(socket.readyState)) {
    return;
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const url = new URL(`/ws/rooms/${encodeURIComponent(roomId)}`, `${protocol}://${window.location.host}`);
  roomStatusElement.dataset.connectionState = "reconnecting";
  socket = new WebSocket(url);

  socket.addEventListener("open", () => {
    setMessage("");
    roomStatusElement.textContent = "房间已连接";
    reconnectButton.hidden = true;
    socket.send(JSON.stringify({ type: "authenticate", token }));
  });
  socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "state") {
      render(payload.state);
    } else if (payload.type === "error") {
      setMessage(payload.error);
    }
  });
  socket.addEventListener("close", (event) => {
    if (event.code === 1008) {
      roomStatusElement.textContent = "邀请链接无效或已失效";
      roomStatusElement.dataset.connectionState = "invalid";
      return;
    }
    if (event.code === 4001) {
      roomStatusElement.textContent = "该席位已在另一设备打开";
      roomStatusElement.dataset.connectionState = "other-device";
      return;
    }
    roomStatusElement.textContent = "连接断开，正在重连...";
    roomStatusElement.dataset.connectionState = "reconnecting";
    reconnectButton.hidden = false;
    window.clearTimeout(reconnectTimer);
    reconnectTimer = window.setTimeout(connect, 1500);
  });
}

boardElement.addEventListener("click", (event) => {
  const cell = event.target.closest(".cell");
  if (!cell || cell.disabled) {
    return;
  }
  send({
    type: "move",
    row: Number(cell.dataset.row),
    col: Number(cell.dataset.col),
  });
});

guestColorButtons.forEach((button) => {
  button.addEventListener("click", () => {
    selectedGuestColor = button.dataset.guestColor;
    updateSelectionButtons();
  });
});

firstPlayerButtons.forEach((button) => {
  button.addEventListener("click", () => {
    selectedFirstPlayer = button.dataset.firstPlayer;
    updateSelectionButtons();
  });
});

submitConfigurationButton.addEventListener("click", () => {
  send({
    type: "configure",
    color: selectedGuestColor,
    first_player: selectedFirstPlayer,
  });
});

acceptConfigurationButton.addEventListener("click", () => {
  send({ type: "accept_configuration" });
});

undoButton.addEventListener("click", () => {
  if (currentState?.undo_requested_by && currentState.undo_requested_by !== currentState.you.role) {
    send({ type: "accept_undo" });
  } else {
    send({ type: "request_undo" });
  }
});

function requestRematch() {
  if (currentState?.rematch_requested_by && currentState.rematch_requested_by !== currentState.you.role) {
    send({ type: "accept_rematch" });
  } else {
    send({ type: "request_rematch" });
  }
}

rematchButton.addEventListener("click", requestRematch);

shareInviteButton.addEventListener("click", () => {
  openInviteDialog();
});

copyInviteButton.addEventListener("click", async () => {
  const inviteUrl = storedInviteUrl();
  if (!inviteUrl) {
    setMessage("未找到邀请链接。请在创建房间时保存链接。" );
    return;
  }
  try {
    await navigator.clipboard.writeText(inviteUrl);
    setMessage("邀请链接已复制，可以发送给好友。");
  } catch {
    window.prompt("复制邀请链接", inviteUrl);
  }
});

inviteCloseButton.addEventListener("click", () => {
  inviteDialog.close();
});

inviteSavedButton.addEventListener("click", () => {
  inviteDialog.close();
  setMessage("邀请链接已保存在本机浏览器中。请勿公开转发。" );
});

reconnectButton.addEventListener("click", () => {
  window.clearTimeout(reconnectTimer);
  reconnectTimer = null;
  connect();
});

resultPrimaryButton.addEventListener("click", requestRematch);

resultSecondaryButton.addEventListener("click", () => {
  window.location.assign("/");
});

resultCloseButton.addEventListener("click", () => {
  resultDialog.close();
});

window.setInterval(() => {
  if (currentState) {
    updateTimer(currentState);
  }
}, 250);

updateSelectionButtons();
connect();

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

function updateStatus(state) {
  if (state.winner_name) {
    statusElement.textContent = `${state.winner_name} wins`;
    return;
  }

  if (state.game_over) {
    statusElement.textContent = "Draw";
    return;
  }

  statusElement.textContent = `Turn: ${state.current_player_name}`;
}

function renderBoard(state) {
  boardElement.innerHTML = "";

  state.board.forEach((row, rowIndex) => {
    row.forEach((cell, colIndex) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "cell";
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
    setMessage(error.message);
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
    setMessage(error.message);
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
    setMessage(error.message);
  }
});

undoButton.addEventListener("click", async () => {
  try {
    const state = await requestJson("/api/undo", { method: "POST" });
    render(state);
    setMessage("");
  } catch (error) {
    setMessage(error.message);
  }
});

loadState();

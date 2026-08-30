(() => {
  "use strict";

  /* ---- Levels and tuning ---- */

  const L1_MAZE = [
    "#############",
    "#...........#",
    "#o##.###.##o#",
    "#...........#",
    "#.##.....##.#",
    "#.#..#-#..#.#",
    "#....#G#....#",
    "#....###....#",
    "#...........#",
    "#.##.....##.#",
    "#...........#",
    "#...........#",
    "#############",
  ];

  const L2_MAZE = [
    "###############",
    "#.............#",
    "#o##..###..##o#",
    "#.............#",
    "#.##..###..##.#",
    "#.##.......##.#",
    "#.##.##-##.##.#",
    "#.##..#GG#....#",
    "#....####.....#",
    "#.##.......##.#",
    "#.............#",
    "#.##..###..##.#",
    "#o##..###..##o#",
    "#.............#",
    "###############",
  ];

  const L3_MAZE = [
    "###################",
    "#........#........#",
    "#o##.###.#.###.##o#",
    "#.................#",
    "#.##.#.#####.#.##.#",
    "#....#...#...#....#",
    "####.###.#.###.####",
    "####.#.......#.####",
    "####.#.##-##.#.####",
    "       #GGG#       ",
    "####.#.#####.#.####",
    "####.#.......#.####",
    "####.###.#.###.####",
    "#........#........#",
    "#o##.###.#.###.##o#",
    "#.................#",
    "#.##.#.#####.#.##.#",
    "#....#...#...#....#",
    "#.######.#.######.#",
    "#o...............o#",
    "###################",
  ];

  const L4_MAZE = [
    "#########################",
    "#.......................#",
    "#o##.###.##.#.##.###.##o#",
    "#.......................#",
    "#.##......#.#.#......##.#",
    "#.....#.....#.....#.....#",
    "#.#####.#####.#####.#####",
    "#.....#.....#.....#.....#",
    "#.......................#",
    "#.......................#",
    "#.########.#--##.######.#",
    "#..........#GGG#........#",
    "#..........#####........#",
    "#.##.##.....#.....##.##.#",
    "#.##.##.###.#.###.##.##.#",
    "#.......................#",
    "#.#####.#####.#####.#####",
    "#.......................#",
    "#.##.##.###.#.###.##.##.#",
    "#.##.##.....#.....##.##.#",
    "#o##.###.##.#.##.###.##o#",
    "#.......................#",
    "#########################",
  ];

  const TILE = 24;
  const HIGH_SCORE_KEY = "sgame-pacman-highscore";
  const PROGRESS_KEY = "sgame-pacman-progress";
  const RECORDS_KEY = "sgame-pacman-timed-records";
  const FRIGHT_DURATION = 6.5;

  const PACMAN_SPEED = 6.5;
  const GHOST_SPEED = 4.9;
  const FRIGHT_SPEED = 3.8;
  const EYES_SPEED = 11;
  const READY_DURATION = 2.2;
  const DEATH_DURATION = 1.3;
  const CLEAR_DURATION = 2.0;
  const TIMED_DEATH_PENALTY = 3;
  const MODE_SCHEDULE = [
    [9, "scatter"],
    [20, "chase"],
    [7, "scatter"],
    [20, "chase"],
    [5, "scatter"],
    [Infinity, "chase"],
  ];

  const DIRS = {
    none: { x: 0, y: 0 },
    up: { x: 0, y: -1 },
    down: { x: 0, y: 1 },
    left: { x: -1, y: 0 },
    right: { x: 1, y: 0 },
  };
  const DIR_ORDER = [DIRS.up, DIRS.left, DIRS.down, DIRS.right];

  const ALL_GHOSTS = {
    blinky: { name: "blinky", color: "#ff0000" },
    pinky: { name: "pinky", color: "#ffb8ff" },
    inky: { name: "inky", color: "#00ffff" },
    clyde: { name: "clyde", color: "#ffb852" },
  };

  const LEVELS = [
    {
      maze: L1_MAZE,
      house: { houseRow: 6, doorRow: 5, exitRow: 4, doorCol: 6 },
      pacmanStart: { row: 9, col: 6 },
      ghosts: [
        { name: "blinky", corner: { row: 1, col: 11 }, start: { row: 4, col: 6 } },
        { name: "pinky", corner: { row: 1, col: 1 }, start: { row: 6, col: 6 } },
      ],
      releaseTimes: { pinky: 3.5 },
    },
    {
      maze: L2_MAZE,
      house: { houseRow: 7, doorRow: 6, exitRow: 5, doorCol: 7 },
      pacmanStart: { row: 9, col: 7 },
      ghosts: [
        { name: "blinky", corner: { row: 1, col: 13 }, start: { row: 5, col: 7 } },
        { name: "pinky", corner: { row: 1, col: 1 }, start: { row: 7, col: 7 } },
        { name: "inky", corner: { row: 13, col: 1 }, start: { row: 7, col: 8 } },
      ],
      releaseTimes: { pinky: 3.5, inky: 7 },
    },
    {
      maze: L3_MAZE,
      house: { houseRow: 9, doorRow: 8, exitRow: 7, doorCol: 9 },
      pacmanStart: { row: 15, col: 9 },
      ghosts: [
        { name: "blinky", corner: { row: 1, col: 17 }, start: { row: 7, col: 9 } },
        { name: "pinky", corner: { row: 1, col: 1 }, start: { row: 9, col: 8 } },
        { name: "inky", corner: { row: 19, col: 1 }, start: { row: 9, col: 9 } },
        { name: "clyde", corner: { row: 19, col: 17 }, start: { row: 9, col: 10 } },
      ],
      releaseTimes: { pinky: 3.5, inky: 7, clyde: 11 },
    },
    {
      maze: L4_MAZE,
      house: { houseRow: 11, doorRow: 10, exitRow: 9, doorCol: 12 },
      pacmanStart: { row: 17, col: 12 },
      ghosts: [
        { name: "blinky", corner: { row: 1, col: 23 }, start: { row: 9, col: 12 } },
        { name: "pinky", corner: { row: 1, col: 1 }, start: { row: 11, col: 12 } },
        { name: "inky", corner: { row: 21, col: 1 }, start: { row: 11, col: 13 } },
        { name: "clyde", corner: { row: 21, col: 23 }, start: { row: 11, col: 14 } },
      ],
      releaseTimes: { pinky: 3.5, inky: 7, clyde: 11 },
    },
  ];

  /* ---- DOM ---- */

  const canvas = document.getElementById("game");
  const ctx = canvas.getContext("2d");

  const views = Array.from(document.querySelectorAll(".pm-view"));
  const gameView = document.getElementById("game-view");
  const levelCardsEl = document.getElementById("level-cards");
  const rankingListEl = document.getElementById("ranking-list");
  const rankingEmptyEl = document.getElementById("ranking-empty");
  const rulesDialog = document.getElementById("rules-dialog");
  const gameHintEl = document.getElementById("game-hint");

  const scoreEl = document.getElementById("score");
  const highScoreEl = document.getElementById("high-score");
  const levelEl = document.getElementById("level");
  const livesEl = document.getElementById("lives");
  const livesItem = document.getElementById("lives-item");
  const timeItem = document.getElementById("time-item");
  const timerEl = document.getElementById("timer");
  const pauseButton = document.getElementById("btn-pause");

  const overlayEl = document.getElementById("overlay");
  const overlayTitleEl = document.getElementById("overlay-title");
  const overlayDetailEl = document.getElementById("overlay-detail");
  const overlayPrimary = document.getElementById("overlay-primary");
  const overlaySecondary = document.getElementById("overlay-secondary");

  /* ---- Storage ---- */

  function loadHighScore() {
    const value = Number(localStorage.getItem(HIGH_SCORE_KEY));
    return Number.isFinite(value) && value > 0 ? value : 0;
  }

  function loadProgress() {
    const fallback = { cleared: [false, false, false, false], bestScores: [0, 0, 0, 0] };
    try {
      const value = JSON.parse(localStorage.getItem(PROGRESS_KEY));
      if (value && typeof value === "object" && Array.isArray(value.cleared) && Array.isArray(value.bestScores)) {
        for (let i = 0; i < LEVELS.length; i += 1) {
          fallback.cleared[i] = value.cleared[i] === true;
          if (typeof value.bestScores[i] === "number") {
            fallback.bestScores[i] = value.bestScores[i];
          }
        }
      }
    } catch (err) {
      /* corrupted entry: fall through */
    }
    return fallback;
  }

  function saveProgress() {
    localStorage.setItem(PROGRESS_KEY, JSON.stringify(progress));
  }

  function loadRecords() {
    try {
      const value = JSON.parse(localStorage.getItem(RECORDS_KEY));
      if (Array.isArray(value)) {
        return value
          .filter((rec) => rec && typeof rec.time === "number" && rec.time > 0)
          .sort((a, b) => a.time - b.time)
          .slice(0, 10);
      }
    } catch (err) {
      /* corrupted entry: fall through */
    }
    return [];
  }

  function saveRecords(records) {
    localStorage.setItem(RECORDS_KEY, JSON.stringify(records));
  }

  function addTimedRecord(time) {
    const entry = {
      time,
      date: new Date().toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }),
    };
    const records = loadRecords();
    records.push(entry);
    records.sort((a, b) => a.time - b.time);
    const rank = records.indexOf(entry);
    saveRecords(records.slice(0, 10));
    return rank < 10 ? rank : null;
  }

  function formatTime(total) {
    const minutes = Math.floor(total / 60);
    const seconds = total - minutes * 60;
    const secText = seconds.toFixed(1).padStart(4, "0");
    return minutes > 0 ? `${minutes}:${secText}` : `${secText} 秒`;
  }

  /* ---- Views ---- */

  function showView(id) {
    for (const view of views) {
      view.hidden = view.id !== id;
    }
    if (id === "menu-view") {
      updateMenuStats();
    } else if (id === "levels-view") {
      renderLevelCards();
    } else if (id === "ranking-view") {
      renderRanking();
    }
  }

  function updateMenuStats() {
    const clearedCount = progress.cleared.filter(Boolean).length;
    document.getElementById("stat-progress").textContent = `${clearedCount}/${LEVELS.length}`;
    document.getElementById("stat-highscore").textContent = String(highScore);
    const records = loadRecords();
    document.getElementById("stat-best-time").textContent =
      records.length > 0 ? formatTime(records[0].time) : "—";
  }

  function isUnlocked(levelNumber) {
    return levelNumber === 1 || progress.cleared[levelNumber - 2] === true;
  }

  function renderLevelCards() {
    levelCardsEl.innerHTML = "";
    LEVELS.forEach((cfg, i) => {
      const n = i + 1;
      const locked = !isUnlocked(n);
      const cleared = progress.cleared[i];
      const card = document.createElement("button");
      card.type = "button";
      card.className = "level-card";
      if (locked) {
        card.classList.add("locked");
      }
      if (cleared) {
        card.classList.add("cleared");
      }
      card.disabled = locked;
      const icon = document.createElement("span");
      icon.className = "level-icon";
      icon.textContent = locked ? "🔒" : cleared ? "★" : String(n);
      const name = document.createElement("span");
      name.className = "level-name";
      name.textContent = `第 ${n} 关`;
      const spec = document.createElement("span");
      spec.className = "level-spec";
      spec.textContent = `${cfg.maze[0].length}×${cfg.maze.length} · ${cfg.ghosts.length} 只幽灵`;
      const status = document.createElement("span");
      status.className = "level-status";
      if (locked) {
        status.textContent = `未解锁 · 先通关第 ${n - 1} 关`;
      } else if (cleared) {
        status.textContent = `已通关 · 最佳 ${progress.bestScores[i]} 分`;
      } else {
        status.textContent = n === 1 ? "开始挑战" : "未挑战";
      }
      card.append(icon, name, spec, status);
      card.addEventListener("click", () => startCampaign(n));
      levelCardsEl.appendChild(card);
    });
  }

  function renderRanking() {
    const records = loadRecords();
    rankingListEl.innerHTML = "";
    rankingEmptyEl.hidden = records.length > 0;
    const medals = ["🥇", "🥈", "🥉"];
    records.forEach((rec, i) => {
      const item = document.createElement("li");
      item.className = "ranking-item";
      const rank = document.createElement("span");
      rank.className = "ranking-rank";
      rank.textContent = medals[i] || `${i + 1}.`;
      const time = document.createElement("span");
      time.className = "ranking-time";
      time.textContent = formatTime(rec.time);
      const date = document.createElement("span");
      date.className = "ranking-date";
      date.textContent = rec.date || "";
      item.append(rank, time, date);
      rankingListEl.appendChild(item);
    });
  }

  /* ---- Game state ---- */

  let dots = [];
  let dotsRemaining = 0;
  let score = 0;
  let highScore = loadHighScore();
  let lives = 3;
  let level = 1;
  let activeLevel = 0;
  let ROWS = 0;
  let COLS = 0;
  let eyesField = null;
  let state = "idle";
  let readyTimer = 0;
  let deathTimer = 0;
  let clearTimer = 0;
  let frightTimer = 0;
  let ghostCombo = 0;
  let levelClock = 0;
  let lifeClock = 0;
  let pacman = null;
  let ghosts = [];
  let pendingDir = DIRS.none;
  let lastDirAngle = Math.PI;
  const releaseOverrides = new WeakMap();

  let mode = null;
  let progress = loadProgress();
  let paused = false;
  let overlayKind = null;
  let levelStartScore = 0;
  let runTime = 0;
  let penalty = 0;
  let deathPenaltyNote = false;

  /* ---- Maze helpers ---- */

  function wrapCol(col) {
    return ((col % COLS) + COLS) % COLS;
  }

  function tileChar(col, row) {
    if (row < 0 || row >= ROWS) {
      return "#";
    }
    return LEVELS[activeLevel].maze[row][wrapCol(col)];
  }

  function isWall(col, row, allowDoor) {
    const ch = tileChar(col, row);
    if (ch === "#") {
      return true;
    }
    if (ch === "-") {
      return !allowDoor;
    }
    return false;
  }

  function levelSpeedMul() {
    return 1;
  }

  function currentMode() {
    let remaining = levelClock;
    for (const [duration, modeName] of MODE_SCHEDULE) {
      if (remaining < duration) {
        return modeName;
      }
      remaining -= duration;
    }
    return "chase";
  }

  function makeEntity(row, col) {
    return { row, col, targetRow: row, targetCol: col, progress: 1, dir: DIRS.none, speed: 0 };
  }

  function startMove(ent, dir) {
    ent.dir = dir;
    ent.targetRow = ent.row + dir.y;
    ent.targetCol = wrapCol(ent.col + dir.x);
    ent.progress = Math.max(ent.progress - 1, 0);
  }

  function advance(ent, dt) {
    if (ent.progress >= 1) {
      return true;
    }
    ent.progress += ent.speed * dt;
    if (ent.progress >= 1) {
      ent.row = ent.targetRow;
      ent.col = ent.targetCol;
      return true;
    }
    return false;
  }

  function entityPos(ent) {
    const t = Math.min(ent.progress, 1);
    let dc = ent.targetCol - ent.col;
    if (dc > 1) {
      dc -= COLS;
    } else if (dc < -1) {
      dc += COLS;
    }
    return {
      x: ent.col + dc * t + 0.5,
      y: ent.row + (ent.targetRow - ent.row) * t + 0.5,
    };
  }

  function computeDistanceField(targetRow, targetCol) {
    const dist = new Array(ROWS * COLS).fill(Infinity);
    const queue = [[targetCol, targetRow]];
    dist[targetRow * COLS + targetCol] = 0;
    while (queue.length > 0) {
      const [col, row] = queue.shift();
      const base = dist[row * COLS + col];
      for (const dir of DIR_ORDER) {
        const nc = wrapCol(col + dir.x);
        const nr = row + dir.y;
        if (isWall(nc, nr, true)) {
          continue;
        }
        const ni = nr * COLS + nc;
        if (dist[ni] === Infinity) {
          dist[ni] = base + 1;
          queue.push([nc, nr]);
        }
      }
    }
    return dist;
  }

  function loadLevel(idx) {
    activeLevel = idx;
    const cfg = LEVELS[idx];
    ROWS = cfg.maze.length;
    COLS = cfg.maze[0].length;
    canvas.width = COLS * TILE;
    canvas.height = ROWS * TILE;
    wallCanvas.width = canvas.width;
    wallCanvas.height = canvas.height;
    renderWallLayer();
    eyesField = computeDistanceField(cfg.house.houseRow, cfg.house.doorCol);
  }

  function resetDots() {
    dots = [];
    dotsRemaining = 0;
    for (let row = 0; row < ROWS; row += 1) {
      const line = [];
      for (let col = 0; col < COLS; col += 1) {
        const ch = LEVELS[activeLevel].maze[row][col];
        if (ch === ".") {
          line.push(1);
          dotsRemaining += 1;
        } else if (ch === "o") {
          line.push(2);
          dotsRemaining += 1;
        } else {
          line.push(0);
        }
      }
      dots.push(line);
    }
  }

  function resetPositions() {
    const cfg = LEVELS[activeLevel];
    pacman = makeEntity(cfg.pacmanStart.row, cfg.pacmanStart.col);
    pacman.dir = DIRS.left;
    lastDirAngle = Math.PI;
    pendingDir = DIRS.none;
    ghosts = cfg.ghosts.map((def) => ({
      ...ALL_GHOSTS[def.name],
      corner: def.corner,
      start: def.start,
      row: def.start.row,
      col: def.start.col,
      targetRow: def.start.row,
      targetCol: def.start.col,
      progress: 1,
      dir: DIRS.none,
      speed: GHOST_SPEED,
      state: def.name === "blinky" ? "active" : "house",
      housePhase: Math.random() * Math.PI * 2,
      leavePhase: 0,
      fx: def.start.col + 0.5,
      fy: def.start.row + 0.5,
    }));
    frightTimer = 0;
    ghostCombo = 0;
    lifeClock = 0;
  }

  /* ---- Game flow ---- */

  function hideOverlay() {
    overlayKind = null;
    overlayEl.hidden = true;
  }

  function showOverlay(kind, title, detail, primaryLabel, secondaryLabel) {
    overlayKind = kind;
    overlayTitleEl.textContent = title;
    overlayDetailEl.textContent = detail;
    overlayPrimary.textContent = primaryLabel;
    overlayPrimary.hidden = false;
    overlaySecondary.textContent = secondaryLabel || "";
    overlaySecondary.hidden = !secondaryLabel;
    overlayEl.hidden = false;
  }

  function updateGameHint() {
    gameHintEl.textContent =
      mode === "timed"
        ? "计时模式：连续打通 4 关，用时计入排行榜。撞到幽灵不扣命，每次 +3 秒惩罚；方向键 / WASD 移动，Esc 暂停。"
        : "闯关模式：吃完所有豆子过关，通关解锁下一关。3 条命，能量豆可以反击幽灵；方向键 / WASD 移动，Esc 暂停。";
  }

  function startLevel() {
    levelStartScore = score;
    resetDots();
    resetPositions();
    eatAt(pacman.row, pacman.col);
    levelClock = 0;
    state = "ready";
    readyTimer = READY_DURATION;
    deathPenaltyNote = false;
    updateHud();
  }

  function startCampaign(levelNumber) {
    mode = "campaign";
    score = 0;
    lives = 3;
    level = levelNumber;
    clearPause();
    hideOverlay();
    loadLevel(levelNumber - 1);
    showView("game-view");
    updateGameHint();
    startLevel();
  }

  function startTimed() {
    mode = "timed";
    score = 0;
    lives = 3;
    level = 1;
    runTime = 0;
    penalty = 0;
    clearPause();
    hideOverlay();
    loadLevel(0);
    showView("game-view");
    updateGameHint();
    startLevel();
  }

  function restartLevel() {
    if (mode !== "campaign") {
      startTimed();
      return;
    }
    score = levelStartScore;
    lives = 3;
    clearPause();
    hideOverlay();
    loadLevel(level - 1);
    startLevel();
  }

  function exitToMenu() {
    mode = null;
    state = "idle";
    clearPause();
    hideOverlay();
    showView("menu-view");
  }

  function goToLevels() {
    mode = "campaign";
    state = "idle";
    clearPause();
    hideOverlay();
    showView("levels-view");
  }

  function primaryAction() {
    switch (overlayKind) {
      case "paused":
        setPaused(false);
        break;
      case "gameover":
        restartLevel();
        break;
      case "levelclear":
        afterLevelClear();
        break;
      case "victory":
        if (mode === "campaign") {
          startCampaign(1);
        } else {
          startTimed();
        }
        break;
      default:
        break;
    }
  }

  function secondaryAction() {
    switch (overlayKind) {
      case "paused":
        exitToMenu();
        break;
      case "gameover":
      case "levelclear":
        goToLevels();
        break;
      case "victory":
        if (mode === "campaign") {
          goToLevels();
        } else {
          exitToMenu();
        }
        break;
      default:
        break;
    }
  }

  function setPaused(value) {
    if (value === paused) {
      return;
    }
    if (value && state !== "ready" && state !== "playing") {
      return;
    }
    paused = value;
    pauseButton.textContent = paused ? "▶ 继续" : "⏸ 暂停";
    if (paused) {
      showOverlay("paused", "已暂停", "按 Esc / P 或点击继续", "▶ 继续", "🏠 返回菜单");
    } else {
      hideOverlay();
    }
  }

  function clearPause() {
    paused = false;
    pauseButton.textContent = "⏸ 暂停";
  }

  function togglePause() {
    setPaused(!paused);
  }

  function addScore(points) {
    score += points;
    if (score > highScore) {
      highScore = score;
      localStorage.setItem(HIGH_SCORE_KEY, String(highScore));
    }
    updateHud();
  }

  function updateHud() {
    scoreEl.textContent = String(score);
    highScoreEl.textContent = String(highScore);
    levelEl.textContent = String(level);
    const isTimed = mode === "timed";
    livesItem.hidden = isTimed;
    timeItem.hidden = !isTimed;
    if (isTimed) {
      timerEl.textContent = formatTime(runTime + penalty);
    }
    livesEl.innerHTML = "";
    for (let i = 0; i < lives; i += 1) {
      const icon = document.createElement("span");
      icon.className = "life-icon";
      livesEl.appendChild(icon);
    }
  }

  function eatAt(row, col) {
    const kind = dots[row][col];
    if (kind === 0) {
      return;
    }
    dots[row][col] = 0;
    dotsRemaining -= 1;
    if (kind === 1) {
      addScore(10);
    } else {
      addScore(50);
      frightTimer = FRIGHT_DURATION;
      ghostCombo = 0;
    }
    if (dotsRemaining === 0) {
      state = "levelclear";
      clearTimer = CLEAR_DURATION;
      if (mode === "campaign") {
        const idx = level - 1;
        progress.cleared[idx] = true;
        progress.bestScores[idx] = Math.max(progress.bestScores[idx], score);
        saveProgress();
        const last = level >= LEVELS.length;
        showOverlay(
          "levelclear",
          "本关完成!",
          `得分 ${score} · 最高分 ${highScore}`,
          last ? "🏆 通关!" : "▶ 下一关",
          "🗺️ 返回选关",
        );
      }
    }
  }

  function isFrightened(ghost) {
    return frightTimer > 0 && ghost.state !== "eyes";
  }

  function pacmanTileAhead(distance) {
    const pos = entityPos(pacman);
    const dir = pacman.dir === DIRS.none ? DIRS.left : pacman.dir;
    return {
      row: Math.round(pos.y - 0.5 + dir.y * distance),
      col: wrapCol(Math.round(pos.x - 0.5 + dir.x * distance)),
    };
  }

  function ghostTarget(ghost) {
    if (currentMode() === "scatter") {
      return ghost.corner;
    }
    const pos = entityPos(pacman);
    const pacTile = { row: Math.round(pos.y - 0.5), col: Math.round(pos.x - 0.5) };
    switch (ghost.name) {
      case "blinky":
        return pacTile;
      case "pinky":
        return pacmanTileAhead(4);
      case "inky":
        return pacmanTileAhead(2);
      case "clyde": {
        const distSq = (ghost.row - pacTile.row) ** 2 + (ghost.col - pacTile.col) ** 2;
        return distSq > 64 ? pacTile : ghost.corner;
      }
      default:
        return pacTile;
    }
  }

  function decideGhostDirection(ghost) {
    const allowDoor = ghost.state === "eyes";
    const opposite = { x: -ghost.dir.x, y: -ghost.dir.y };
    const options = DIR_ORDER.filter((dir) => {
      if (ghost.dir !== DIRS.none && dir.x === opposite.x && dir.y === opposite.y) {
        return false;
      }
      return !isWall(ghost.col + dir.x, ghost.row + dir.y, allowDoor);
    });
    if (options.length === 0) {
      startMove(ghost, opposite);
      return;
    }
    let chosen = options[0];
    if (ghost.state === "eyes") {
      let bestDist = Infinity;
      for (const dir of options) {
        const dist = eyesField[(ghost.row + dir.y) * COLS + wrapCol(ghost.col + dir.x)];
        if (dist < bestDist) {
          bestDist = dist;
          chosen = dir;
        }
      }
    } else if (isFrightened(ghost)) {
      chosen = options[Math.floor(Math.random() * options.length)];
    } else {
      const target = ghostTarget(ghost);
      let bestDist = Infinity;
      for (const dir of options) {
        const nr = ghost.row + dir.y;
        const nc = wrapCol(ghost.col + dir.x);
        const distSq = (nr - target.row) ** 2 + (nc - target.col) ** 2;
        if (distSq < bestDist) {
          bestDist = distSq;
          chosen = dir;
        }
      }
    }
    startMove(ghost, chosen);
  }

  function updateLeaving(ghost, dt) {
    const cfg = LEVELS[activeLevel];
    const speed = GHOST_SPEED * levelSpeedMul();
    if (ghost.leavePhase === 0) {
      const targetX = cfg.house.doorCol + 0.5;
      const step = speed * dt;
      if (Math.abs(ghost.fx - targetX) <= step) {
        ghost.fx = targetX;
        ghost.leavePhase = 1;
      } else {
        ghost.fx += Math.sign(targetX - ghost.fx) * step;
      }
      return;
    }
    const targetY = cfg.house.exitRow + 0.5;
    const step = speed * dt;
    if (ghost.fy - targetY <= step) {
      ghost.fy = targetY;
      ghost.state = "active";
      ghost.row = cfg.house.exitRow;
      ghost.col = cfg.house.doorCol;
      ghost.targetRow = cfg.house.exitRow;
      ghost.targetCol = cfg.house.doorCol;
      ghost.progress = 1;
      ghost.dir = DIRS.none;
    } else {
      ghost.fy -= step;
    }
  }

  function ghostSpeed(ghost) {
    if (ghost.state === "eyes") {
      return EYES_SPEED;
    }
    if (isFrightened(ghost)) {
      return FRIGHT_SPEED;
    }
    return GHOST_SPEED;
  }

  function updateGhost(ghost, dt) {
    const cfg = LEVELS[activeLevel];
    if (ghost.state === "house") {
      ghost.housePhase += dt * 3;
      const override = releaseOverrides.get(ghost);
      let releaseAt = override !== undefined ? override : cfg.releaseTimes[ghost.name];
      if (releaseAt === undefined) {
        releaseAt = 0;
      }
      if (lifeClock >= releaseAt) {
        ghost.state = "leaving";
        ghost.leavePhase = 0;
        ghost.fx = ghost.col + 0.5;
        ghost.fy = cfg.house.houseRow + 0.5;
      }
      return;
    }
    if (ghost.state === "leaving") {
      updateLeaving(ghost, dt);
      return;
    }
    ghost.speed = ghostSpeed(ghost);
    const arrived = advance(ghost, dt * levelSpeedMul());
    if (!arrived) {
      return;
    }
    if (ghost.state === "eyes" && ghost.row === cfg.house.houseRow && ghost.col === cfg.house.doorCol) {
      ghost.state = "house";
      ghost.row = cfg.house.houseRow;
      ghost.col = cfg.house.doorCol;
      ghost.targetRow = cfg.house.houseRow;
      ghost.targetCol = cfg.house.doorCol;
      ghost.fx = cfg.house.doorCol + 0.5;
      ghost.fy = cfg.house.houseRow + 0.5;
      ghost.progress = 1;
      releaseOverrides.set(ghost, lifeClock + 1.5);
      return;
    }
    decideGhostDirection(ghost);
  }

  function updatePacman(dt) {
    if (pacman.progress < 1 && pendingDir !== DIRS.none
      && pendingDir.x === -pacman.dir.x && pendingDir.y === -pacman.dir.y) {
      const row = pacman.row;
      const col = pacman.col;
      pacman.row = pacman.targetRow;
      pacman.col = pacman.targetCol;
      pacman.targetRow = row;
      pacman.targetCol = col;
      pacman.progress = 1 - pacman.progress;
      pacman.dir = pendingDir;
    }
    pacman.speed = PACMAN_SPEED;
    const arrived = advance(pacman, dt * levelSpeedMul());
    if (!arrived) {
      return;
    }
    eatAt(pacman.row, pacman.col);
    if (state !== "playing") {
      return;
    }
    const candidates = [];
    if (pendingDir !== DIRS.none) {
      candidates.push(pendingDir);
    }
    if (pacman.dir !== DIRS.none && !candidates.includes(pacman.dir)) {
      candidates.push(pacman.dir);
    }
    for (const dir of candidates) {
      if (!isWall(pacman.col + dir.x, pacman.row + dir.y, false)) {
        startMove(pacman, dir);
        return;
      }
    }
    pacman.dir = DIRS.none;
    pacman.progress = 1;
  }

  function checkCollisions() {
    const pos = entityPos(pacman);
    for (const ghost of ghosts) {
      if (ghost.state === "house" || ghost.state === "leaving") {
        continue;
      }
      const gpos = entityPos(ghost);
      const distSq = (gpos.x - pos.x) ** 2 + (gpos.y - pos.y) ** 2;
      if (distSq > 0.25) {
        continue;
      }
      if (ghost.state === "eyes") {
        continue;
      }
      if (isFrightened(ghost)) {
        ghost.state = "eyes";
        addScore(200 * 2 ** ghostCombo);
        ghostCombo = Math.min(ghostCombo + 1, 3);
      } else {
        state = "dying";
        deathTimer = DEATH_DURATION;
        return;
      }
    }
  }

  function afterDeath() {
    if (mode === "timed") {
      penalty += TIMED_DEATH_PENALTY;
      deathPenaltyNote = true;
      resetPositions();
      eatAt(pacman.row, pacman.col);
      state = "ready";
      readyTimer = READY_DURATION;
      updateHud();
      return;
    }
    lives -= 1;
    updateHud();
    if (lives <= 0) {
      state = "idle";
      showOverlay(
        "gameover",
        "游戏结束",
        `得分 ${score} · 最高分 ${highScore} · 止步第 ${level} 关`,
        "↻ 重新挑战本关",
        "🗺️ 返回选关",
      );
      return;
    }
    resetPositions();
    eatAt(pacman.row, pacman.col);
    state = "ready";
    readyTimer = READY_DURATION;
  }

  function afterLevelClear() {
    if (level >= LEVELS.length) {
      state = "idle";
      if (mode === "timed") {
        const finalTime = runTime + penalty;
        const rank = addTimedRecord(finalTime);
        if (rank === 0) {
          showOverlay("victory", "新纪录!", `用时 ${formatTime(finalTime)} · 恭喜登顶排行榜`, "⏱️ 再来一次", "🏠 返回菜单");
        } else if (rank === null) {
          showOverlay("victory", "通关成功!", `用时 ${formatTime(finalTime)} · 未进前十，再接再厉`, "⏱️ 再来一次", "🏠 返回菜单");
        } else {
          showOverlay("victory", "通关成功!", `用时 ${formatTime(finalTime)} · 排行榜第 ${rank + 1} 名`, "⏱️ 再来一次", "🏠 返回菜单");
        }
      } else {
        showOverlay("victory", "恭喜通关!", `得分 ${score} · 最高分 ${highScore} · 4 关全部完成`, "🎮 再来一局", "🗺️ 返回选关");
      }
      return;
    }
    level += 1;
    hideOverlay();
    loadLevel(level - 1);
    startLevel();
  }

  function update(dt) {
    if (paused) {
      return;
    }
    if (mode === "timed" && state !== "idle") {
      runTime += dt;
      timerEl.textContent = formatTime(runTime + penalty);
    }
    if (state === "ready") {
      readyTimer -= dt;
      if (readyTimer <= 0) {
        state = "playing";
        deathPenaltyNote = false;
      }
      return;
    }
    if (state === "dying") {
      deathTimer -= dt;
      if (deathTimer <= 0) {
        afterDeath();
      }
      return;
    }
    if (state === "levelclear") {
      if (mode === "timed") {
        clearTimer -= dt;
        if (clearTimer <= 0) {
          afterLevelClear();
        }
      }
      return;
    }
    if (state !== "playing") {
      return;
    }
    levelClock += dt;
    lifeClock += dt;
    if (frightTimer > 0) {
      frightTimer -= dt;
    }
    updatePacman(dt);
    if (state !== "playing") {
      return;
    }
    for (const ghost of ghosts) {
      updateGhost(ghost, dt);
    }
    checkCollisions();
  }

  /* ---- Rendering ---- */

  const wallCanvas = document.createElement("canvas");
  wallCanvas.width = canvas.width;
  wallCanvas.height = canvas.height;

  function renderWallLayer() {
    const maze = LEVELS[activeLevel].maze;
    const wctx = wallCanvas.getContext("2d");
    wctx.fillStyle = "#05060f";
    wctx.fillRect(0, 0, wallCanvas.width, wallCanvas.height);
    const inset = 5;
    for (let row = 0; row < ROWS; row += 1) {
      for (let col = 0; col < COLS; col += 1) {
        if (maze[row][col] !== "#") {
          continue;
        }
        const x = col * TILE;
        const y = row * TILE;
        wctx.fillStyle = "#101433";
        wctx.fillRect(x, y, TILE, TILE);
        wctx.strokeStyle = "#3d5afe";
        wctx.lineWidth = 2.5;
        wctx.lineCap = "round";
        const open = (dc, dr) => tileChar(col + dc, row + dr) !== "#";
        wctx.beginPath();
        if (open(0, -1)) {
          wctx.moveTo(x + inset, y + inset);
          wctx.lineTo(x + TILE - inset, y + inset);
        }
        if (open(0, 1)) {
          wctx.moveTo(x + inset, y + TILE - inset);
          wctx.lineTo(x + TILE - inset, y + TILE - inset);
        }
        if (open(-1, 0)) {
          wctx.moveTo(x + inset, y + inset);
          wctx.lineTo(x + inset, y + TILE - inset);
        }
        if (open(1, 0)) {
          wctx.moveTo(x + TILE - inset, y + inset);
          wctx.lineTo(x + TILE - inset, y + TILE - inset);
        }
        wctx.stroke();
      }
    }
    for (let row = 0; row < ROWS; row += 1) {
      for (let col = 0; col < COLS; col += 1) {
        if (maze[row][col] !== "-") {
          continue;
        }
        const x = col * TILE;
        const y = row * TILE;
        wctx.strokeStyle = "#ffb8de";
        wctx.lineWidth = 3.5;
        wctx.beginPath();
        wctx.moveTo(x + 3, y + TILE / 2);
        wctx.lineTo(x + TILE - 3, y + TILE / 2);
        wctx.stroke();
      }
    }
  }

  function drawDots(t) {
    ctx.fillStyle = "#ffcf9e";
    for (let row = 0; row < ROWS; row += 1) {
      for (let col = 0; col < COLS; col += 1) {
        const kind = dots[row][col];
        if (kind === 0) {
          continue;
        }
        const x = col * TILE + TILE / 2;
        const y = row * TILE + TILE / 2;
        if (kind === 1) {
          ctx.beginPath();
          ctx.arc(x, y, 3, 0, Math.PI * 2);
          ctx.fill();
        } else {
          const radius = 6.5 * (0.8 + 0.2 * Math.sin(t * 8));
          ctx.beginPath();
          ctx.arc(x, y, radius, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
  }

  function drawPacman(t, x, y) {
    const r = TILE * 0.48;
    let mouth;
    if (state === "dying") {
      const k = Math.min(1, 1 - deathTimer / DEATH_DURATION);
      mouth = Math.PI * k;
    } else {
      mouth = (0.09 + 0.24 * Math.abs(Math.sin(t * 10))) * Math.PI;
    }
    if (pacman.dir !== DIRS.none) {
      lastDirAngle = Math.atan2(pacman.dir.y, pacman.dir.x);
    }
    ctx.fillStyle = "#ffcc00";
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.arc(x, y, r, lastDirAngle + mouth, lastDirAngle - mouth);
    ctx.closePath();
    ctx.fill();
  }

  function ghostPixelPos(ghost) {
    if (ghost.state === "house") {
      return {
        x: ghost.fx * TILE,
        y: (ghost.fy + Math.sin(ghost.housePhase) * 0.22) * TILE,
      };
    }
    if (ghost.state === "leaving") {
      return { x: ghost.fx * TILE, y: ghost.fy * TILE };
    }
    const pos = entityPos(ghost);
    return { x: pos.x * TILE, y: pos.y * TILE };
  }

  function drawGhost(ghost, t, x, y) {
    const r = TILE * 0.46;
    const eyesOnly = ghost.state === "eyes";
    const frightened = isFrightened(ghost);
    const flashing = frightened && frightTimer < 2 && Math.floor(t * 6) % 2 === 0;

    if (!eyesOnly) {
      ctx.fillStyle = frightened ? (flashing ? "#f8f8ff" : "#2121de") : ghost.color;
      ctx.beginPath();
      ctx.arc(x, y - r * 0.15, r, Math.PI, 0);
      ctx.lineTo(x + r, y + r * 0.75);
      const waves = 3;
      const width = (r * 2) / waves;
      for (let i = 0; i < waves; i += 1) {
        const edge = x + r - width * i;
        ctx.quadraticCurveTo(
          edge - width / 2,
          y + r * (0.75 + 0.35 * ((Math.floor(t * 8) + i) % 2 === 0 ? 1 : 0.4)),
          edge - width,
          y + r * 0.75,
        );
      }
      ctx.closePath();
      ctx.fill();
    }

    const eyeDx = ghost.dir.x * r * 0.16;
    const eyeDy = ghost.dir.y * r * 0.16;
    if (frightened && !eyesOnly) {
      ctx.fillStyle = flashing ? "#ff3b3b" : "#ffd8c2";
      ctx.beginPath();
      ctx.arc(x - r * 0.35, y - r * 0.2, r * 0.14, 0, Math.PI * 2);
      ctx.arc(x + r * 0.35, y - r * 0.2, r * 0.14, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = ctx.fillStyle;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x - r * 0.5, y + r * 0.35);
      for (let i = 0; i < 4; i += 1) {
        ctx.lineTo(x - r * 0.5 + r * 0.25 * (i + 0.5), y + r * (i % 2 === 0 ? 0.2 : 0.4));
      }
      ctx.stroke();
    } else {
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.ellipse(x - r * 0.32, y - r * 0.2, r * 0.26, r * 0.32, 0, 0, Math.PI * 2);
      ctx.ellipse(x + r * 0.32, y - r * 0.2, r * 0.26, r * 0.32, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "#1b2ca0";
      ctx.beginPath();
      ctx.arc(x - r * 0.32 + eyeDx, y - r * 0.2 + eyeDy, r * 0.14, 0, Math.PI * 2);
      ctx.arc(x + r * 0.32 + eyeDx, y - r * 0.2 + eyeDy, r * 0.14, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function drawWithWrap(drawFn, x) {
    drawFn(x);
    if (x < TILE) {
      drawFn(x + COLS * TILE);
    } else if (x > (COLS - 1) * TILE) {
      drawFn(x - COLS * TILE);
    }
  }

  function drawCenterText(text, y, color, size) {
    ctx.fillStyle = color;
    ctx.font = `bold ${size}px "Segoe UI", sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, canvas.width / 2, y);
  }

  function draw(t) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(wallCanvas, 0, 0);
    if (state === "levelclear" && Math.floor(clearTimer * 4) % 2 === 0) {
      ctx.fillStyle = "rgba(255, 255, 255, 0.18)";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    } else {
      drawDots(t);
    }

    if (state !== "dying") {
      for (const ghost of ghosts) {
        const pos = ghostPixelPos(ghost);
        drawWithWrap((x) => drawGhost(ghost, t, x, pos.y), pos.x);
      }
    }

    const ppos = entityPos(pacman);
    const py = ppos.y * TILE;
    drawWithWrap((x) => drawPacman(t, x, py), ppos.x * TILE);

    if (state === "ready") {
      drawCenterText(
        deathPenaltyNote ? `时间惩罚 +${TIMED_DEATH_PENALTY} 秒` : "READY!",
        canvas.height * 0.62,
        "#ffcc00",
        18,
      );
    } else if (state === "levelclear" && mode === "timed") {
      drawCenterText(`第 ${level} 关完成!`, canvas.height / 2, "#ffcc00", 22);
    }
  }

  /* ---- Input ---- */

  const KEY_DIRS = {
    ArrowUp: DIRS.up,
    ArrowDown: DIRS.down,
    ArrowLeft: DIRS.left,
    ArrowRight: DIRS.right,
    KeyW: DIRS.up,
    KeyS: DIRS.down,
    KeyA: DIRS.left,
    KeyD: DIRS.right,
  };

  document.addEventListener("keydown", (event) => {
    if (!rulesDialog.hidden) {
      if (event.code === "Escape" || event.code === "Enter" || event.code === "Space") {
        event.preventDefault();
        rulesDialog.hidden = true;
      }
      return;
    }
    if (gameView.hidden) {
      return;
    }
    if (event.code === "Escape" || event.code === "KeyP") {
      event.preventDefault();
      togglePause();
      return;
    }
    if (event.code === "Space" || event.code === "Enter") {
      if (paused || overlayKind !== null) {
        event.preventDefault();
        primaryAction();
      }
      return;
    }
    const dir = KEY_DIRS[event.code];
    if (!dir) {
      return;
    }
    event.preventDefault();
    pendingDir = dir;
  });

  let touchStart = null;
  canvas.addEventListener("touchstart", (event) => {
    event.preventDefault();
    const touch = event.touches[0];
    touchStart = { x: touch.clientX, y: touch.clientY };
  }, { passive: false });

  canvas.addEventListener("touchmove", (event) => {
    event.preventDefault();
    if (touchStart === null) {
      return;
    }
    const touch = event.touches[0];
    const dx = touch.clientX - touchStart.x;
    const dy = touch.clientY - touchStart.y;
    if (Math.abs(dx) < 24 && Math.abs(dy) < 24) {
      return;
    }
    if (Math.abs(dx) > Math.abs(dy)) {
      pendingDir = dx > 0 ? DIRS.right : DIRS.left;
    } else {
      pendingDir = dy > 0 ? DIRS.down : DIRS.up;
    }
    touchStart = { x: touch.clientX, y: touch.clientY };
  }, { passive: false });

  canvas.addEventListener("touchend", () => {
    touchStart = null;
  });

  /* ---- Buttons ---- */

  document.getElementById("btn-campaign").addEventListener("click", () => showView("levels-view"));
  document.getElementById("btn-timed").addEventListener("click", startTimed);
  document.getElementById("btn-ranking").addEventListener("click", () => showView("ranking-view"));
  document.getElementById("btn-rules").addEventListener("click", () => {
    rulesDialog.hidden = false;
  });
  document.getElementById("btn-close-rules").addEventListener("click", () => {
    rulesDialog.hidden = true;
  });
  document.getElementById("btn-back-to-menu").addEventListener("click", () => showView("menu-view"));
  document.getElementById("btn-back-from-ranking").addEventListener("click", () => showView("menu-view"));
  document.getElementById("btn-exit").addEventListener("click", exitToMenu);
  document.getElementById("btn-restart").addEventListener("click", restartLevel);
  pauseButton.addEventListener("click", togglePause);
  overlayPrimary.addEventListener("click", primaryAction);
  overlaySecondary.addEventListener("click", secondaryAction);

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      setPaused(true);
    }
  });

  /* ---- Boot ---- */

  loadLevel(0);
  resetDots();
  resetPositions();
  updateHud();
  updateGameHint();
  showView("menu-view");

  let lastTime = null;
  function frame(now) {
    requestAnimationFrame(frame);
    const dt = Math.min(lastTime === null ? 0 : (now - lastTime) / 1000, 0.05);
    lastTime = now;
    if (!gameView.hidden) {
      update(dt);
      draw(now / 1000);
    }
  }
  requestAnimationFrame(frame);
})();

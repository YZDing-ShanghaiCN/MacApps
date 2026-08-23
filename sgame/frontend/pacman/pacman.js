(() => {
  "use strict";

  const MAZE = [
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

  const ROWS = MAZE.length;
  const COLS = MAZE[0].length;
  const TILE = 24;
  const HIGH_SCORE_KEY = "sgame-pacman-highscore";

  const HOUSE_ROW = 9;
  const DOOR_ROW = 8;
  const EXIT_ROW = 7;
  const DOOR_COL = 9;
  const PACMAN_START = { row: 11, col: 9 };

  const PACMAN_SPEED = 6.5;
  const GHOST_SPEED = 6.0;
  const FRIGHT_SPEED = 3.8;
  const EYES_SPEED = 11;
  const READY_DURATION = 1.6;
  const DEATH_DURATION = 1.3;
  const CLEAR_DURATION = 2.0;
  const RELEASE_TIMES = { pinky: 1, inky: 4, clyde: 7 };
  const MODE_SCHEDULE = [
    [7, "scatter"],
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

  const GHOST_DEFS = [
    { name: "blinky", color: "#ff0000", corner: { row: 1, col: 17 }, start: { row: EXIT_ROW, col: DOOR_COL } },
    { name: "pinky", color: "#ffb8ff", corner: { row: 1, col: 1 }, start: { row: HOUSE_ROW, col: 8 } },
    { name: "inky", color: "#00ffff", corner: { row: 19, col: 1 }, start: { row: HOUSE_ROW, col: 9 } },
    { name: "clyde", color: "#ffb852", corner: { row: 19, col: 17 }, start: { row: HOUSE_ROW, col: 10 } },
  ];

  const canvas = document.getElementById("game");
  const ctx = canvas.getContext("2d");
  canvas.width = COLS * TILE;
  canvas.height = ROWS * TILE;

  const scoreEl = document.getElementById("score");
  const highScoreEl = document.getElementById("high-score");
  const levelEl = document.getElementById("level");
  const livesEl = document.getElementById("lives");
  const overlayEl = document.getElementById("overlay");
  const overlayDetailEl = document.getElementById("overlay-detail");
  const overlayButton = document.getElementById("overlay-button");

  let dots = [];
  let dotsRemaining = 0;
  let score = 0;
  let highScore = loadHighScore();
  let lives = 3;
  let level = 1;
  let state = "attract";
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

  function loadHighScore() {
    const value = Number(localStorage.getItem(HIGH_SCORE_KEY));
    return Number.isFinite(value) && value > 0 ? value : 0;
  }

  function wrapCol(col) {
    return ((col % COLS) + COLS) % COLS;
  }

  function tileChar(col, row) {
    if (row < 0 || row >= ROWS) {
      return "#";
    }
    return MAZE[row][wrapCol(col)];
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
    return 1 + Math.min(level - 1, 8) * 0.04;
  }

  function currentMode() {
    let remaining = levelClock;
    for (const [duration, mode] of MODE_SCHEDULE) {
      if (remaining < duration) {
        return mode;
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

  const eyesField = computeDistanceField(HOUSE_ROW, DOOR_COL);

  function resetDots() {
    dots = [];
    dotsRemaining = 0;
    for (let row = 0; row < ROWS; row += 1) {
      const line = [];
      for (let col = 0; col < COLS; col += 1) {
        const ch = MAZE[row][col];
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
    pacman = makeEntity(PACMAN_START.row, PACMAN_START.col);
    pacman.dir = DIRS.left;
    lastDirAngle = Math.PI;
    pendingDir = DIRS.none;
    ghosts = GHOST_DEFS.map((def) => ({
      ...def,
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

  function startLevel() {
    resetDots();
    resetPositions();
    eatAt(pacman.row, pacman.col);
    levelClock = 0;
    state = "ready";
    readyTimer = READY_DURATION;
    updateHud();
  }

  function newGame() {
    score = 0;
    lives = 3;
    level = 1;
    overlayEl.hidden = true;
    startLevel();
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
      frightTimer = Math.max(6.5 - (level - 1) * 0.5, 2.5);
      ghostCombo = 0;
    }
    if (dotsRemaining === 0) {
      state = "levelclear";
      clearTimer = CLEAR_DURATION;
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
    const speed = GHOST_SPEED * levelSpeedMul();
    if (ghost.leavePhase === 0) {
      const targetX = DOOR_COL + 0.5;
      const step = speed * dt;
      if (Math.abs(ghost.fx - targetX) <= step) {
        ghost.fx = targetX;
        ghost.leavePhase = 1;
      } else {
        ghost.fx += Math.sign(targetX - ghost.fx) * step;
      }
      return;
    }
    const targetY = EXIT_ROW + 0.5;
    const step = speed * dt;
    if (ghost.fy - targetY <= step) {
      ghost.fy = targetY;
      ghost.state = "active";
      ghost.row = EXIT_ROW;
      ghost.col = DOOR_COL;
      ghost.targetRow = EXIT_ROW;
      ghost.targetCol = DOOR_COL;
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
    if (ghost.state === "house") {
      ghost.housePhase += dt * 3;
      const releaseAt = releaseOverrides.get(ghost) ?? RELEASE_TIMES[ghost.name] ?? 0;
      if (lifeClock >= releaseAt) {
        ghost.state = "leaving";
        ghost.leavePhase = 0;
        ghost.fx = ghost.col + 0.5;
        ghost.fy = HOUSE_ROW + 0.5;
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
    if (ghost.state === "eyes" && ghost.row === HOUSE_ROW && ghost.col === DOOR_COL) {
      ghost.state = "house";
      ghost.row = HOUSE_ROW;
      ghost.col = DOOR_COL;
      ghost.targetRow = HOUSE_ROW;
      ghost.targetCol = DOOR_COL;
      ghost.fx = DOOR_COL + 0.5;
      ghost.fy = HOUSE_ROW + 0.5;
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
      if (distSq > 0.36) {
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
    lives -= 1;
    if (lives <= 0) {
      state = "gameover";
      overlayDetailEl.textContent = `得分 ${score} · 最高分 ${highScore} · 关卡 ${level}`;
      overlayEl.hidden = false;
      updateHud();
      return;
    }
    resetPositions();
    eatAt(pacman.row, pacman.col);
    state = "ready";
    readyTimer = READY_DURATION;
    updateHud();
  }

  function afterLevelClear() {
    level += 1;
    startLevel();
  }

  function update(dt) {
    if (state === "ready") {
      readyTimer -= dt;
      if (readyTimer <= 0) {
        state = "playing";
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
      clearTimer -= dt;
      if (clearTimer <= 0) {
        afterLevelClear();
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

  /* Rendering */

  const wallCanvas = document.createElement("canvas");
  wallCanvas.width = canvas.width;
  wallCanvas.height = canvas.height;

  function renderWallLayer() {
    const wctx = wallCanvas.getContext("2d");
    wctx.fillStyle = "#05060f";
    wctx.fillRect(0, 0, wallCanvas.width, wallCanvas.height);
    const inset = 5;
    for (let row = 0; row < ROWS; row += 1) {
      for (let col = 0; col < COLS; col += 1) {
        if (MAZE[row][col] !== "#") {
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
        if (MAZE[row][col] !== "-") {
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

    if (state === "attract") {
      drawCenterText("PAC-MAN", canvas.height / 2 - 30, "#ffcc00", 34);
      drawCenterText("按方向键开始", canvas.height / 2 + 12, "#eceaf4", 18);
      return;
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
      drawCenterText("READY!", 13 * TILE + TILE / 2, "#ffcc00", 18);
    }
  }

  /* Input */

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
    if (event.code === "Space" || event.code === "Enter") {
      if (state === "gameover" || state === "attract") {
        newGame();
        event.preventDefault();
      }
      return;
    }
    const dir = KEY_DIRS[event.code];
    if (!dir) {
      return;
    }
    event.preventDefault();
    if (state === "attract") {
      newGame();
      pendingDir = dir;
      return;
    }
    if (state === "gameover") {
      return;
    }
    pendingDir = dir;
  });

  let touchStart = null;
  canvas.addEventListener("touchstart", (event) => {
    event.preventDefault();
    const touch = event.touches[0];
    touchStart = { x: touch.clientX, y: touch.clientY };
    if (state === "attract" || state === "gameover") {
      newGame();
    }
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

  overlayButton.addEventListener("click", () => {
    newGame();
  });

  /* Boot */

  renderWallLayer();
  resetDots();
  resetPositions();
  updateHud();

  let lastTime = null;
  function frame(now) {
    requestAnimationFrame(frame);
    const dt = Math.min(lastTime === null ? 0 : (now - lastTime) / 1000, 0.05);
    lastTime = now;
    update(dt);
    draw(now / 1000);
  }
  requestAnimationFrame(frame);
})();

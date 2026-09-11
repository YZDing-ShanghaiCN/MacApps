(() => {
  "use strict";

  const TARGET = 24;
  const EPS = 1e-6;
  const SOLVE_EPS = 1e-9;
  const MAX_INPUT_LEN = 120;
  const MAX_RETRIES = 5000;
  const FALLBACK_DEAL = [3, 3, 8, 8]; // 8/(3-8/3)=24

  const menuView = document.getElementById("menu-view");
  const gameView = document.getElementById("game-view");
  const modeLabel = document.getElementById("mode-label");
  const numberCards = Array.from(document.querySelectorAll(".number-card"));
  const exprInput = document.getElementById("expr-input");
  const feedback = document.getElementById("feedback");
  const btnVerify = document.getElementById("btn-verify");
  const btnNewDeal = document.getElementById("btn-new-deal");
  const btnBackMenu = document.getElementById("btn-back-menu");
  const btnStartEasy = document.getElementById("start-easy");
  const btnStartHard = document.getElementById("start-hard");

  let mode = "easy";
  let dealt = [];

  function randInt(min, max) {
    return min + Math.floor(Math.random() * (max - min + 1));
  }

  function isSolvable(nums) {
    if (nums.length === 1) {
      return Math.abs(nums[0] - TARGET) < SOLVE_EPS;
    }
    for (let i = 0; i < nums.length; i += 1) {
      for (let j = i + 1; j < nums.length; j += 1) {
        const rest = [];
        for (let k = 0; k < nums.length; k += 1) {
          if (k !== i && k !== j) {
            rest.push(nums[k]);
          }
        }
        const a = nums[i];
        const b = nums[j];
        const candidates = [a + b, a * b, a - b, b - a];
        if (b !== 0) {
          candidates.push(a / b);
        }
        if (a !== 0) {
          candidates.push(b / a);
        }
        for (const c of candidates) {
          if (isSolvable(rest.concat(c))) {
            return true;
          }
        }
      }
    }
    return false;
  }

  function deal() {
    const max = mode === "easy" ? 13 : 99;
    for (let attempt = 0; attempt < MAX_RETRIES; attempt += 1) {
      const nums = [randInt(1, max), randInt(1, max), randInt(1, max), randInt(1, max)];
      if (isSolvable(nums)) {
        dealt = nums;
        renderCards();
        return;
      }
    }
    dealt = FALLBACK_DEAL.slice();
    renderCards();
  }

  function renderCards() {
    numberCards.forEach((card, index) => {
      card.textContent = dealt[index];
    });
  }

  function showFeedback(message, kind) {
    feedback.textContent = message;
    feedback.className = kind ? `feedback ${kind}` : "feedback";
  }

  function showView(view) {
    menuView.hidden = view !== menuView;
    gameView.hidden = view !== gameView;
  }

  function startGame(newMode) {
    mode = newMode;
    modeLabel.textContent = mode === "easy" ? "简单 · 1–13" : "困难 · 1–99";
    exprInput.value = "";
    showFeedback("", null);
    deal();
    showView(gameView);
    exprInput.focus();
  }

  // ---- expression parsing (hand-written, no eval) ----

  function tokenize(input) {
    const tokens = [];
    let i = 0;
    while (i < input.length) {
      const ch = input[i];
      if (ch === " " || ch === "\t" || ch === "\n") {
        i += 1;
        continue;
      }
      if (ch >= "0" && ch <= "9") {
        let j = i;
        while (j < input.length && input[j] >= "0" && input[j] <= "9") {
          j += 1;
        }
        tokens.push({ type: "num", value: parseInt(input.slice(i, j), 10) });
        i = j;
        continue;
      }
      if (ch === "+" || ch === "-" || ch === "*" || ch === "/" || ch === "(" || ch === ")") {
        tokens.push({ type: "op", value: ch });
        i += 1;
        continue;
      }
      throw new Error(`无法识别的字符「${ch}」：只支持数字、+ - * / 和括号`);
    }
    return tokens;
  }

  function parseExpression(tokens) {
    let pos = 0;
    const used = [];

    function parseExpr() {
      let value = parseTerm();
      while (
        tokens[pos] &&
        tokens[pos].type === "op" &&
        (tokens[pos].value === "+" || tokens[pos].value === "-")
      ) {
        const op = tokens[pos].value;
        pos += 1;
        const rhs = parseTerm();
        value = op === "+" ? value + rhs : value - rhs;
      }
      return value;
    }

    function parseTerm() {
      let value = parseFactor();
      while (
        tokens[pos] &&
        tokens[pos].type === "op" &&
        (tokens[pos].value === "*" || tokens[pos].value === "/")
      ) {
        const op = tokens[pos].value;
        pos += 1;
        const rhs = parseFactor();
        if (op === "*") {
          value *= rhs;
        } else {
          if (rhs === 0) {
            throw new Error("除以零了");
          }
          value /= rhs;
        }
      }
      return value;
    }

    function parseFactor() {
      const tok = tokens[pos];
      if (!tok) {
        throw new Error("算式不完整");
      }
      if (tok.type === "num") {
        pos += 1;
        used.push(tok.value);
        return tok.value;
      }
      if (tok.value === "(") {
        pos += 1;
        const value = parseExpr();
        const close = tokens[pos];
        if (!close || close.value !== ")") {
          throw new Error("缺少右括号 )");
        }
        pos += 1;
        return value;
      }
      if (tok.value === ")") {
        throw new Error("括号不匹配：多余的右括号");
      }
      if (tok.value === "-" || tok.value === "+") {
        throw new Error("不支持正负号，数字只能以正数形式使用");
      }
      throw new Error("此处应为数字或左括号");
    }

    const value = parseExpr();
    if (pos !== tokens.length) {
      throw new Error("算式无法解析，请检查括号和运算符");
    }
    return { value, used };
  }

  function sameMultiset(a, b) {
    if (a.length !== b.length) {
      return false;
    }
    const sortedA = a.slice().sort((x, y) => x - y);
    const sortedB = b.slice().sort((x, y) => x - y);
    return sortedA.every((v, i) => v === sortedB[i]);
  }

  function formatNumber(v) {
    return String(Math.round(v * 1e6) / 1e6);
  }

  function onVerify() {
    const raw = exprInput.value;
    if (raw.trim() === "") {
      showFeedback("请输入算式", "error");
      return;
    }
    if (raw.length > MAX_INPUT_LEN) {
      showFeedback("算式太长了", "error");
      return;
    }
    let parsed;
    try {
      parsed = parseExpression(tokenize(raw));
    } catch (err) {
      showFeedback(err.message, "error");
      return;
    }
    if (!sameMultiset(parsed.used, dealt)) {
      showFeedback("必须且只能用给出的 4 个数字，每个恰好使用一次", "error");
      return;
    }
    if (Math.abs(parsed.value - TARGET) < EPS) {
      showFeedback("正确！这个算式等于 24", "ok");
    } else {
      showFeedback(`结果是 ${formatNumber(parsed.value)}，不等于 24，再试试`, "error");
    }
  }

  // ---- events ----

  btnStartEasy.addEventListener("click", () => startGame("easy"));
  btnStartHard.addEventListener("click", () => startGame("hard"));
  btnVerify.addEventListener("click", onVerify);
  exprInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      onVerify();
    }
  });
  btnNewDeal.addEventListener("click", () => {
    exprInput.value = "";
    showFeedback("", null);
    deal();
    exprInput.focus();
  });
  btnBackMenu.addEventListener("click", () => {
    showView(menuView);
  });

  showView(menuView);
})();

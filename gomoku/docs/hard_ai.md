# HardAI 技术说明

HardAI 是“困难”难度的独立 AI：战术证明引擎（VCF/VCT/强制防守）+ 确定性蒙特卡洛树搜索（MCTS）兜底。它不是更深的 NormalAI，与 SimpleAI/NormalAI 的实现完全分离，配置集中在 `src/gomoku/ai/hard_ai_config.py`（`HardAIConfig`，不可变 dataclass，默认每步 800ms 总预算、20ms 安全余量）。

## 决策流水线

`HardAI.choose_move` 与 NormalAI 保持相同的同步调用约定（含 `cancel_event`），按以下顺序决策，任一阶段命中即返回：

| 阶段 | 决策原因 | 时间预算（默认） | 说明 |
|---|---|---|---|
| 1. 己方一步获胜 | `immediate_win` | 瞬时 | 扫描一步成五的所有点，取最靠中心的 |
| 2. VCF | `vcf_forced_win` | 可用时间 × 0.25 | 仅使用四的连续冲四证明 |
| 3. VCT | `vct_forced_win` | 可用时间 × 0.45 | 四 + 活三/跳三的连续做杀证明 |
| 4. 阻挡对手一步获胜 | `immediate_block` | 瞬时 | 对手成五点中最靠中心的一个 |
| 5. 战术防守 | `tactical_defense` | 剩余时间 × 0.5 | 先找对手强制胜链，再逐点验证防守（找链与验证各占一半） |
| 6. MCTS 兜底 | `mcts_fallback` | 全部剩余时间 | PUCT 蒙特卡洛树搜索，战术点作为优先落点 |

未用完的阶段预算会滚入后续阶段。整个流水线共享一个绝对时限：战术搜索在每个搜索节点与每个候选/应对探测点检查截止时间与取消事件，MCTS 在每次模拟之前及策略/价值评估循环内部检查，因此该时限是真实生效的截止时间而非目标值。超时、取消或任何意外异常都返回合法的“最靠中心”兜底落点（`timeout_fallback` / `error_fallback`），**HardAI 对外绝不抛异常**。

所有战术阶段（VCF/VCT/战术防守）始终运行（各阶段预算为 0 时自然跳过）；不存在会漏掉战术局面的预检捷径。

## 战术引擎（threat_search.py）

### VCF 与 VCT 的区别

- **VCF**（Victory by Continuous Fours）：攻方每步都必须产生立即威胁——成五、冲四或双四。防守方只要存在任意一个被验证必胜的应对，该攻方落点即被否定；所有应对都败才宣布 FOUND，并输出结构化证明链（`attacker_moves`、一条规范防守线 `forced_defenses`、最终成五点 `winning_points`）。
- **VCT**（Victory by Continuous Threats）：与 VCF 相同的 AND/OR 树，但攻方威胁扩展为四 + 活三/跳三。VCT 之前先跑 VCF；`mode="auto"` 先切 VCF，再对攻方步数 2..`vct_max_depth` 迭代加深。

防守方应对**枚举而非假设**，分三类：

1. 攻方所造四/三棋型的全部 `key_empties` 阻挡点（不设上限）；
2. 防守方的一步成五点（硬反驳）；
3. 防守方的反四点（在已有棋子半径 1 邻域内扫描）。

三类应对**全量枚举、绝不截断**：FOUND 意味着每一个相关应对（阻挡、反胜、反四）都已被逐一验证必败；若枚举在时限内无法完成，结果只能是 TIMEOUT（不确定），绝不会带着未验证的应对宣布 FOUND。

关键不对称：**反四不能反驳四，但能反驳三**。攻方冲四后防守方只剩阻挡点，堵住即死；而面对三的威胁，防守方可以造自己的四——攻方若应，则失去先手；若不应，防守方成五。因此 VCT 只有在防守方全盘没有反四资源时才能从三的威胁中得证。

### 超时语义与置换表

- `TIMEOUT` 与 `NOT_FOUND` 严格区分：TIMEOUT 表示“未能证明”，**绝不**输出落子或证据链；NOT_FOUND 才是已验证的“无强制胜”。
- 深度感知置换表（键为 `(哈希, 攻方, 模式, 剩余深度)`，容量 `threat_transposition_capacity`）：FOUND 命中要求存储深度 ≤ 当前剩余深度（证明仍然成立）；NOT_FOUND 命中要求存储深度 ≥ 当前剩余深度（否定仍然成立）；TIMEOUT 从不入表。
- 超时检查在每个搜索节点入口以及每个候选/应对枚举循环内进行（含 `_counter_cells`、`_defense_candidates`、威胁扫描），配合绝对时限与 `cancel_event`；任何阶段超时都立即停止。

### 强制防守（find_forced_defense）

候选 = 对手强制胜链上的空点（按链序）+ 链上各点切比雪夫距离 ≤1 的干扰空点，**全量枚举、不设上限**。每个候选都会落子后用 `find_forcing_win` 验证：对手仍有强制胜 → 失败；已验证无强制胜 → 采纳；验证超时 → 跳过（**绝不盲选未经验证的链首**，也绝不返回未经完整验证的候选）。返回第一个被验证安全的落点；若枚举中途超时，整体结果为 TIMEOUT 而非 FOUND。

## MCTS 兜底（mcts.py + policy_value.py）

- **无 rollout 的 PUCT**：选择 = 模拟 → 扩展一个子节点 → 叶子价值来自 `PolicyValueProvider.value`（落子后成五记 1.0，无合法点记 0.5）→ 回传时逐层取反。
- 选择公式：`Q + c_puct × P × √N_parent / (1 + N_child)`，价值 ∈ [0,1] 取行棋方视角；子节点按序迭代、严格 `>` 取优 → 完全确定。
- 先验：候选池 = 邻域棋型关键点 ∪ 战术优先点（`priority_moves`，优先点先验 × `mcts_priority_prior_bonus`）∪ 模型全局 Top-K 点；叠加 `mcts_uniform_prior_epsilon` 的均匀质量到**全部**合法点后归一化，保证任何落点可达。
- **渐进式扩展（progressive widening）**：节点创建时只把先验最高的 `mcts_pw_initial_children` 个候选置为可尝试，其余进入等待队列；节点访问数增长后按 `initial + int(mcts_pw_growth × √visits)` 逐批放行（选择阶段每次下行前补齐）。关闭 `mcts_pw_enabled` 恢复一次性暴露全部候选的旧行为。先验本身不变，只改变暴露节奏 → 深度窄节点比宽而浅的一访问节点更有统计意义，且完全确定。
- **叶子战术探针（mcts_leaf_tactics_enabled）**：叶子创建时在本地候选池（邻域 ∪ 优先点）内做一次一着战术分类——己方一步成五 → 叶子价值直接记 1.0（不调用提供者）且成五点并入扩展优先点；对手一步成五 → 强制阻挡点并入优先点（价值仍由提供者给出）；己方存在一着造出 ≥2 个成五点的双四/活四 → 价值记 1.0。探针有界（无 VCT 递归），顶层 VCF/VCT/防守仍是权威阶段，这里只锐化 MCTS 叶子。
- **真实时限**：截止时间与取消事件在每次模拟之前检查，并通过 `timeout_check` 回调传入 `policy()`/`value()`，在策略探测与价值评估循环内部逐点检查；搜索达到 `mcts_node_capacity` 节点数时干净结束（不计为超时）。
- **跨回合根节点复用（rerooting）**：上次搜索干净结束（未超时）且 Zobrist 哈希（含行棋方）与当前局面一致时整棵子树复用（`reuse_plies=1`）；不一致时尝试**跨回合重根**（`reuse_plies=2`）——比对存储棋谱与当前棋盘差异，要求自己刚下的子正是上次选定的落点、对手落子（一子或两子内）与存储子树的孩子吻合，并用 Zobrist 运算（复用哈希 ⊕ 落子键 ⊕ 行棋方键）逐位验证当前哈希，再按当前棋盘过滤非法孩子后重挂（统计保留，非法子丢弃）。任何不符（对手走了别的点、缺孩子、上次超时）整体丢弃重搜（`reuse_plies=0`），绝不沿用过期统计；结果中的 `reuse_plies`（0/1/2）即复用深度。共享同一实例交替行棋（如自博弈）每次得到一子重根，双方各持实例（如竞技场）得到两子重根。
- 最终落子 = 访问次数最多（并列取最靠中心）→ 先验最高 → 最靠中心合法点；即使 0 次模拟也返回合法落子。空盘约定直接返回天元。

### 策略/价值提供者与模型接入点

`PolicyValueProvider` 协议定义 `policy(board, player, legal_moves)` 与 `value(board, player)`。默认实现 `HeuristicPolicyValueProvider` 复用 NormalAI 的棋型静态评估作为启发式（只读借用评分表，**不含任何训练权重或 ML 依赖**）：先验 = 对候选点做增量评估后的 softmax，价值 = sigmoid(评估分 / `value_scale`)，完全确定。

配置模型即可切换为 `ModelPolicyValueProvider`：加载自博弈训练的小型策略-价值网络（`gomoku/ai/model.py`，合法点掩码 softmax + tanh 价值映射到 (0,1)），torch 惰性导入，不配置模型时核心游戏与启发式路径完全不依赖 PyTorch。**激活优先级**：显式 `HardAI(..., provider=...)` 注入 > `HardAIConfig.model_path` > 环境变量 `GOMOKU_HARD_AI_MODEL_PATH` > 启发式。模型路径生效时构造阶段立即校验：路径缺失、棋盘尺寸不符、PyTorch 不可用等任何失败只向 stderr 打印一次诊断并回退启发式，对局不受影响。

训练模型还提供**全局 Top-K 候选**（`mcts_global_top_k`，0 关闭）：每次前向对 225 点做合法掩码后取前 K 个全局落点并入 MCTS 候选池，同一节点的 `policy()` 与 `global_top_k()` 共享一次前向（单槽缓存，键为 `(哈希, 行棋方)`），因此不增加推理成本；`timeout_check` 在缓存命中前照常执行，时限契约不变。启发式提供者的该钩子恒定返回空集——启发式模式**不会**在每个节点静态评估全盘 225 点，开销不变。

**探索只属于自博弈**：根 Dirichlet 噪声仅在自博弈生成器（`generate_selfplay_data.py --root-noise`，游戏种子驱动、同种子字节可复现）中开启；HardAI 人机对局、战术搜索与竞技场从不施加噪声，真实对局始终完全确定。自博弈数据生成、训练与“只保留更强模型”的迭代循环见 [docs/selfplay_training.md](selfplay_training.md)。

## 已知限制

- 战术阶段预算固定（VCF 25% + VCT 45%），深度受 `vcf_max_depth`/`vct_max_depth` 限制：超深或超宽的强制胜可能因预算耗尽被判 TIMEOUT 而非 FOUND（此时转入防守/MCTS，不会乱下）；TIMEOUT 永远只是“未能证明”，不是“不存在”。
- 默认启发式策略/价值弱于训练模型，MCTS 兜底在复杂中局主要保证合法与合理，而非最强；训练模型只影响 MCTS 兜底阶段，战术阶段始终先运行。
- 无禁手规则（自由规则）。
- 防守阶段只在对手存在“已验证强制胜链”时触发，不处理“多数小威胁”的广义防守。

## 测试与诊断

```bash
python -m pytest gomoku/tests/test_threat_search.py gomoku/tests/test_mcts.py \
  gomoku/tests/test_policy_value.py gomoku/tests/test_hard_ai.py -q
```

Web 人机页面的“AI 调试信息”在困难难度下显示 VCF/VCT/防守阶段命中状态、MCTS 模拟数与根访问数；`Export Position` / “复制问题局面”导出的 JSON 在 `hard_ai` 字段中包含完整配置与 `HardAISearchStats`（含本次搜索的根复用深度 `mcts_reuse_plies`、是否施加根噪声 `mcts_root_noise`，以及 `provider` 块：当前提供者类型、模型路径、架构尺寸与失败回退说明），可直接作为复现资料。

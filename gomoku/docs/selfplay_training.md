# HardAI 自博弈训练流水线

HardAI 的 MCTS 兜底默认使用手写启发式 `HeuristicPolicyValueProvider`（复用 NormalAI 静态评估器做 softmax 先验、sigmoid 价值），**没有训练模型**。本文档说明如何用自博弈数据训练一个小的策略-价值网络，并通过 `ModelPolicyValueProvider` 接入 MCTS。

## 为什么是自博弈而不是人工标注

策略网络的监督目标需要“每个局面的最优落子分布”，价值网络需要“每个局面的胜负”，两者都无法人工标注：

- 局面数量天文数字，且好坏依赖后续深度计算，人工难以判断；
- 自博弈（MCTS 自我对弈）天然产生这两个标签，且随着模型变强，数据质量自动提升（策略迭代）。

因此**不需要人工标注数据**。人工数据只适合做一个小的战术回归语料（VCF/VCT/防守局面），而这部分已经由现有测试套件覆盖。

## 标签语义

每步落子前记录一条 JSON（gzip JSONL，每行一条）：

| 字段 | 含义 |
|---|---|
| `player` | 行棋方（1=黑，2=白），编码与结果均以该方视角 |
| `move` | 实际落子 `[row, col]` |
| `planes` | 两平面编码 `(2, 15, 15)`：第 0 层为己方棋子、第 1 层为对方棋子 |
| `policy` | 长度 225 的策略目标：MCTS 根节点访问次数分布（未访问的候选为 0，和为 1） |
| `outcome` | 终局回填：行棋方胜 +1、负 −1、和 0 |

生成对局使用**纯 MCTS**（不走 VCF/VCT 流水线）：训练信号就是 MCTS 的访问分布，战术阶段的硬决策会污染标签。多样性来自温度采样（前 `temperature_cutoff` 步 τ=1，之后取访问最多）；否则确定性 MCTS 会永远重放同一盘棋。首步（空盘）MCTS 直接返回天元，该条记录的策略目标为均匀分布。

## 依赖

- 生成数据：无 ML 依赖（numpy 已随项目环境安装）。
- 训练与模型推理：PyTorch（CPU 即可）。

```bash
python3 -m pip install --user -r gomoku/requirements-ml.txt
```

核心游戏与默认 HardAI **永不 import torch**（`gomoku/ai/model.py` 惰性加载）；`requirements.txt` 保持无 ML 依赖。

## 五步循环

### 1. 竞技场基线（未训练模型也能跑）

HardAI 使用“永不前进的注入时钟 + `mcts_node_capacity` 干净退出”，NormalAI 使用节点预算，因此比赛完全确定、可复现：

```bash
python gomoku/scripts/hard_ai_arena.py --engine-a hard --engine-b hard \
  --mcts-capacity 2000 --output report.json
python gomoku/scripts/hard_ai_arena.py --engine-a hard --engine-b normal \
  --mcts-capacity 2000 --normal-node-budget 2000
```

输出每方的胜局、得分率、Wilson 95% 置信区间、Elo、平均 MCTS 模拟数、战术命中率与超时率。`--config-a/--config-b` 可传入 HardAIConfig 的 JSON 覆盖（未知字段报错）。

### 2. 生成自博弈数据

```bash
python gomoku/scripts/generate_selfplay_data.py \
  --games 100 --mcts-capacity 800 --root-noise \
  --output data/run_0000.jsonl.gz
```

参数：`--temperature`、`--temperature-cutoff`、`--max-moves`、`--seed`、`--start-index`（追加续跑）。gzip 流使用 `mtime=0`，相同参数产生字节一致的文件。有了模型后加 `--model current.pt`，先验来自模型（策略提升）。

**根节点 Dirichlet 噪声（仅自博弈）**：`--root-noise` 开启 AlphaZero 式探索——每局每次搜索的根先验先与 `Dirichlet(alpha)` 按 `(1−ε)·p + ε·noise` 混合再归一化，噪声取自该局的游戏随机源（`--seed` 决定）。抽签顺序固定（先噪声、后温度采样），因此相同 `--seed` 重放字节一致的棋谱，不同种子改变早期探索；`--dirichlet-epsilon`/`--dirichlet-alpha` 可调，默认取 `HardAIConfig` 值（0.25/0.03）。真实对局（HardAI 人机/竞技场/战术搜索）**从不**施加噪声，始终完全确定。

### 3. 训练小型策略-价值网络

```bash
python gomoku/scripts/train_policy_value.py \
  --data "data" --output model.pt --epochs 3 \
  --replay-window 8 --replay-max-records 200000
```

损失 = 策略交叉熵（对访问分布软标签）+ 价值 MSE（对 ±1/0），训练时对全部 8 种二面体对称（旋转/翻转）即时增广。每个 epoch 输出训练/验证损失与 top-1 命中率，并原子写出 `model.pt.epochN`。

**回放缓冲（流式，不整库载入内存）**：`--data` 指向分片目录（或 glob）时，按文件名排序（`run_%04d.jsonl.gz`，名称序即时间序）只取最新 `--replay-window` 个分片；每个 epoch 以 `--replay-seed + epoch`（默认 `--replay-seed` = `--seed`）为种子做**流式水库采样**，最多抽 `--replay-max-records` 条（torch `IterableDataset`、`num_workers=0`，全流程确定可复现）。训练/验证按 `crc32(分片路径:行号) % 10000` 稳定切分，与采样、epoch、种子无关。开始时打印每个分片路径与记录数以及最终训练/验证规模；`--replay-window 0` / `--replay-max-records 0` 表示不丢弃、不限量。gzip JSONL 分片格式不变，追加续跑（`--start-index`）与中断重跑都安全。

### 4. 接入 HardAI

激活模型有三种方式，优先级从高到低：

1. `HardAI(..., provider=...)` 直接注入任意 `PolicyValueProvider` 实现；
2. `HardAIConfig.model_path` 指向模型文件；
3. 环境变量 `GOMOKU_HARD_AI_MODEL_PATH` 指向模型文件（无需改配置即可让已部署程序用上模型）。

模型路径生效时 HardAI 改用 `ModelPolicyValueProvider`（合法点掩码 softmax + tanh 价值映射到 (0,1)），并在构造时**立即校验**：路径不存在、棋盘尺寸不符、PyTorch 缺失等任何失败都会向 stderr 打一次诊断并**回退到启发式提供者**，对局完全可恢复；当前生效的提供者类型/路径/说明会出现在调试快照的 `hard_ai.provider` 字段。不配置任何模型时保持启发式提供者、完全不依赖 PyTorch，行为与之前逐位一致。

### 5. 周期性迭代：只保留更强的模型

```bash
python gomoku/scripts/iterate_model.py \
  --model-dir gomoku/models --selfplay-games 100 --train-epochs 3 \
  --replay-window 8 --replay-max-records 200000 \
  --arena-opening-mode generated --arena-opening-count 16
```

一次运行 = 自博弈（用当前模型先验，纯 MCTS）→ 训练候选（默认在**最新 8 个分片**组成的回放集上训练，而不是只训最新分片）→ 竞技场（候选 vs 当前模型，首次 vs 启发式）→ 候选 95% Wilson 区间**下界** > 0.5 才复制为 `current.pt`（点胜率 > 0.5 但区间下界 ≤ 0.5 时**不**晋级，小样本噪声不会晋级）。每次运行向 `gomoku/models/runs.jsonl` 追加一行 JSON 记录，含回放文件清单、`replay_window`/`replay_max_records`、训练记录数、开局元数据与 Wilson `confidence_95`；模型、数据与报告均在 `gomoku/models/`（已 gitignore）。

**晋级赛开局**：默认 `generated` 模式用固定种子生成可复现的多样合法开局（生成过程拒绝终局/非法/非交替序列，并按颜色交换签名去重），每个开局交换黑白各下一盘（默认 16 个开局 → 32 盘，长度 `--arena-opening-length`）；`--arena-opening-mode fixed` 退回快速冒烟用的固定开局套件。开局、颜色分配与完整棋谱都写入报告 JSON。

## 一次认真的训练运行

```bash
python gomoku/scripts/iterate_model.py \
  --model-dir gomoku/models \
  --selfplay-games 100 --mcts-capacity 800 \
  --train-epochs 3 --replay-window 8 --replay-max-records 200000 \
  --arena-opening-mode generated --arena-opening-count 16 \
  --arena-opening-seed 0 --arena-opening-length 4
```

- 想加强自博弈探索时，可用 `generate_selfplay_data.py --root-noise --games 100` 直接生成带噪声的分片再交给训练脚本（相同 `--seed` 仍字节可复现）。
- 训练出的模型会自动启用全局 Top-K 候选与渐进式扩展（见 [docs/hard_ai.md](hard_ai.md)），无需额外参数。
- 晋级判定只用 Wilson 95% 区间下界 > 0.5；每次运行追加一行 `runs.jsonl`，可随时中断、重跑或续跑。

## 注意

- 确定性：所有随机性来自可注入的 `random.Random(seed)`；测试不用真实睡眠。
- 训练出的提供者只影响 MCTS 兜底阶段；HardAI 的 VCF/VCT/防守阶段仍先运行，弱模型不会拖累战术强度。
- `TIMEOUT` 语义不变：模型推理同样遵守 `timeout_check`，超时不会成为落子。

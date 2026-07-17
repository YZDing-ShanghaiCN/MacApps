# Gomoku

一个支持本地、人机和私人跨网对战的 15×15 五子棋项目。

## 安装

以下命令默认在 `apps/` 目录执行：

```bash
conda activate gomoku
pip install -r gomoku/requirements.txt
```

## 本地游玩

### Pygame 桌面版

```bash
python gomoku/scripts/run_pygame.py
```

可选择本地双人或人机模式；点击 `Start Game` 开始，`Restart` 重开，`Undo` 悔棋。

### Web 版

```bash
python gomoku/scripts/run_server.py
```

在 Mac 浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。网页支持本地双人、人机、胜利棋线高亮、黑白双方累计用时、悔棋和重开。

## 跨网私人对战

Mac 和手机不需要在同一 Wi‑Fi。首次使用先安装 Cloudflare 客户端：

```bash
brew install cloudflared
```

然后只运行：

```bash
python gomoku/scripts/run_quick_tunnel.py
```

终端会输出一个 `https://*.trycloudflare.com` 地址。Mac 和手机都打开该地址；由 Mac 创建私人房间，再把弹窗中的二维码或完整邀请链接发给对方。

- 终端必须一直保持运行；关闭后对局中断。
- 每次重启都会生成新地址，需要重新创建房间。
- 不要分享 `127.0.0.1` 链接：它只能在 Mac 本机访问。
- 邀请链接带有随机密钥。仅发送给对方，不要公开发布公网地址或完整房间链接。

房主创建房间后等待受邀者加入。受邀者可选择黑白棋和先后手，房主确认后开始对局。双方通过 WebSocket 实时同步；断线会暂停计时，重连后自动恢复。

Quick Tunnel 适合临时私人对战。若要长期固定网址，需要自己的域名和 Cloudflare Named Tunnel，或部署到支持 HTTPS/WSS 的服务器，并设置 `GOMOKU_PUBLIC_BASE_URL`。

## AI

当前提供两种 AI 难度：

- “简单”使用原有 SimpleAI：优先处理连续四、三、二等连续棋串，优先扩展己方棋形或阻挡对方；同类棋串中两端都可落的优先于单端可落，一步能同时处理两条线的落点优先。没有更高优先级棋形时，会在己方单子周围八格向棋盘中心扩展，再阻挡对方单子。带间隔的棋形不视为连续棋串。
- “普通”使用纯搜索 NormalAI：迭代加深 Negamax、Alpha-Beta/PVS 剪枝、窄窗搜索、固定种子增量 Zobrist 哈希、组相联置换表、棋型静态评估、威胁优先候选点和严格的每步时间预算。NormalAI 能识别连续及带间隔的四、三、二与交叉双重威胁，带有限深度的 VCF 连续冲四搜索，默认最多搜索 800ms，并始终保留一步获胜和必须阻挡的落点。

“困难”难度仍在开发中。NormalAI 不使用强化学习、神经网络或外部模型/API；完整 VCT 不在 0.3.1 范围内，将依据实战反馈单独设计。

NormalAI 的所有可调项集中在 `src/gomoku/ai/normal_ai_config.py`。`pattern_scores` 是从当前搜索方视角计算己方棋型价值，`defense_pattern_scores` 是对手棋型的防守价值，最终近似为“己方价值 × 进攻系数 − 对手价值 × 防守系数”。搜索时间、深度、候选数量、VCF、缓存容量和排序参数也都在同一配置类中。

可运行固定局面诊断，比较改参数前后的搜索深度、节点数、缓存命中和耗时；脚本只报告数据，不使用依赖机器性能的断言：

```bash
python gomoku/scripts/benchmark_normal_ai.py
```

Pygame 与 Web 的 NormalAI 都在后台线程思考，重开、悔棋或切换模式会取消并丢弃旧搜索结果。Web 本地对局按浏览器会话隔离，AI 思考期间会阻止同一会话重复落子。

## 测试

```bash
python -m pytest gomoku/tests
```

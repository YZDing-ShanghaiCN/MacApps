# Gomoku

五子棋项目，当前支持：

- 本地 pygame 双人对战
- 本地 pygame 人机对战
- Web 页面双人对战
- Web 页面人机对战

以下命令默认在 `apps/` 目录下执行，并且已经进入 conda 环境：

```bash
conda activate gomoku
```

## 安装依赖

```bash
pip install -r gomoku/requirements.txt
```

## 运行本地游戏

```bash
python gomoku/scripts/run_pygame.py
```

操作：

- 鼠标点击棋盘落子
- 按 `1` 切换到双人模式，并重新开始
- 按 `2` 切换到人机模式，并重新开始
- 按 `R` 重新开始当前模式
- 按 `U` 悔棋

模式：

- 双人模式：黑白双方都由玩家操作。
- 人机模式：玩家执黑棋，AI 执白棋；玩家落子后，AI 会自动落子。

## 运行 Web 对战

```bash
python gomoku/scripts/run_server.py
```

浏览器打开：

```text
http://127.0.0.1:8000
```

健康检查：

```text
http://127.0.0.1:8000/health
```

Web 页面支持：

- 点击棋盘落子
- 点击“双人对战”切换到双人模式
- 点击“人机对战”切换到人机模式
- 显示当前玩家
- 显示当前模式
- 显示胜负结果
- 重新开始
- 悔棋

Web 人机模式同样由玩家执黑棋，AI 执白棋。前端只负责提交玩家落子和渲染后端返回的棋盘，AI 落子由后端自动完成。

## AI 说明

当前 AI 是 `gomoku/src/gomoku/ai/simple_ai.py` 中的简单 AI，不是深度学习模型。它严格按优先级处理连续四、连续三、连续二：同长度时先扩展自己的棋串，再阻挡对手；对手棋串的可落端会随机选择。带间隔的棋形不会视为连续棋串，两端都被堵住的棋串也不会参与策略。没有可处理棋形时，AI 会随机选择合法位置。后续可以继续扩展评分函数、minimax、alpha-beta 剪枝等策略。

## 运行测试

```bash
python -m pytest gomoku/tests
```

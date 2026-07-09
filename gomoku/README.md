# Gomoku

五子棋项目，当前支持：

- 本地 pygame 双人对战
- Web 页面双人本地对战

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
- 按 `R` 重新开始
- 按 `U` 悔棋

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
- 显示当前玩家
- 显示胜负结果
- 重新开始
- 悔棋

## 运行测试

```bash
python -m pytest gomoku/tests
```

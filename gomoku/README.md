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
- 通过窗口下方按钮选择双人或人机模式
- 人机模式使用“简单”难度的 SimpleAI；普通和困难难度将在后续加入
- 点击“Start Game”开始对局并启动黑白双方的累计用时
- 通过“Restart”和“Undo”按钮重新开始或悔棋

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
- 人机难度按钮：当前可使用“简单”；普通和困难显示为开发中
- 点击“开始对局”后启动黑白双方的累计用时
- 显示当前玩家
- 显示当前模式
- 显示胜负结果和获胜棋线
- 重新开始
- 悔棋

Web 人机模式同样由玩家执黑棋，AI 执白棋。前端只负责提交玩家落子和渲染后端返回的棋盘，AI 落子由后端自动完成。

## 私人网络对战

Web 首页的“创建私人房间”会生成一间仅两人可加入的房间。创建者在 Mac 浏览器中等待，受邀者打开邀请链接后可选择自己的黑白棋色与黑白任一方先手；创建者确认后才会开始对局。

- 不提供房间列表、搜索、公开匹配或观战入口。
- 邀请链接含随机密钥；持有链接的人可作为受邀者加入，因此不要公开转发。
- 对局通过 WebSocket 实时同步落子、获胜棋线、累计用时、悔棋请求和再来一局请求。
- 受邀者刷新页面或短暂断线后，可以用同一邀请链接重新加入。

`python gomoku/scripts/run_server.py` 默认只允许本机访问（`127.0.0.1`），因此不能直接把该地址发给手机。

若 Mac 和手机处于同一 Wi-Fi，可让服务监听局域网，并明确指定生成邀请链接时使用的 Mac 局域网地址：

```bash
export GOMOKU_HOST="0.0.0.0"
export GOMOKU_PUBLIC_BASE_URL="http://你的-Mac-局域网-IP:8000"
python gomoku/scripts/run_server.py
```

例如，`GOMOKU_PUBLIC_BASE_URL` 可填写 `http://192.168.1.23:8000`。在 Mac 上执行 `ipconfig getifaddr en0` 通常可以查看该地址；若 macOS 弹出防火墙提示，请允许 Python 接受传入连接。然后重新创建房间，再发送新生成的邀请链接。不要继续使用之前含有 `127.0.0.1` 的链接。

若两台设备不在同一 WLAN（例如手机使用蜂窝数据），局域网地址仍无法访问。推荐通过 Cloudflare Tunnel 让 Mac 使用固定公网地址，同时无需开放路由器端口：

1. 将自己的域名接入 Cloudflare，在 Cloudflare Zero Trust 创建 Tunnel，并为它添加公开主机名，例如 `gomoku.example.com`；服务地址填写 `http://127.0.0.1:8000`。保存 Tunnel Token，勿分享或提交它。
2. 在 Mac 上安装 Tunnel 客户端：

   ```bash
   brew install cloudflared
   ```

3. 将自己的公网域名和 Token 仅写入当前终端，再启动公共服务：

   ```bash
   export GOMOKU_PUBLIC_BASE_URL="https://gomoku.example.com"
   export GOMOKU_CLOUDFLARE_TUNNEL_TOKEN="你的-Cloudflare-Tunnel-Token"
   python gomoku/scripts/run_public_server.py
   ```

此启动器让五子棋只监听 Mac 本机的 `127.0.0.1`，由 Cloudflare Tunnel 转发外部 HTTPS/WSS 流量。此后 Mac 和手机都访问 `https://gomoku.example.com`，并重新创建房间；所有邀请链接都会使用同一个公网地址。Mac 必须保持开机并持续运行该命令。

也可以将服务部署到任意支持 WebSocket 的公网 HTTPS/WSS 环境。部署后设置公网地址环境变量，例如：

```bash
export GOMOKU_PUBLIC_BASE_URL="https://gomoku.example.com"
```

Docker 部署镜像可通过以下命令构建：

```bash
docker build -t gomoku .
docker run --rm -p 8000:8000 \
  -e GOMOKU_PUBLIC_BASE_URL="https://gomoku.example.com" \
  gomoku
```

默认情况下，无连接的房间会在 12 小时后清理；可通过 `GOMOKU_ROOM_TTL_SECONDS` 调整。当前房间保存在内存中，服务重启会结束未完成的对局。

每个服务实例都保存自己的房间状态，因此第一版部署应保持单个 Uvicorn worker 和单个应用实例；扩展到多实例时，再接入 Redis 等共享房间状态。

## AI 说明

当前可选择的“简单”AI 是 `gomoku/src/gomoku/ai/simple_ai.py` 中的 SimpleAI，不是深度学习模型。它严格按优先级处理连续四、连续三、连续二：同长度时先扩展自己的棋串，再阻挡对手；对手棋串的可落端会随机选择。带间隔的棋形不会视为连续棋串，两端都被堵住的棋串也不会参与策略。没有可处理棋形时，AI 会随机选择合法位置。普通和困难 AI 预留为后续开发项。

## 运行测试

```bash
python -m pytest gomoku/tests
```

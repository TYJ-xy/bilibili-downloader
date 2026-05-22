# B站全自动下载器

> 输入 UP 主名称，自动搜索 → 获取视频列表 → 下载视频/音频/字幕/封面/关键帧。
> 支持 OpenClaw / Hermes Agent 调用。

---

## 快速开始

### 方式一：双击运行（Windows）

```
1. 下载本项目 → 解压
2. 双击 启动下载.bat
3. 首次运行自动弹出 Cookie 配置向导
4. 输入 UP 主名称 → 选择模式 → 开始下载
```

### 方式二：命令行

```bash
python bilibili_auto.py auto "UP主名" --mode video --limit 5 --quality 80
```

### 方式三：Agent 对话

将 `SKILL.md` 发给 OpenClaw / Hermes Agent，Agent 自动创建 skill 后可直接对话使用：

> "下载 影视飓风 的最新 3 个视频"

---

## 功能

| 模式 | 命令 | 输出 |
|------|------|------|
| 视频 | `--mode video` | .mp4 |
| 音频 | `--mode audio` | .mp3 |
| 字幕 | `--mode subtitle` | .txt |
| 封面 | `--mode cover` | .jpg |
| 关键帧 | `--mode keyframe` | 50 张截图 |
| 全部 | `--mode all` | 以上四项 |
| 组合 | `--mode cover,subtitle` | 封面 + 字幕 |

## 画质

| 代号 | 画质 | 需要 |
|------|------|------|
| 64 | 720P | 无 |
| 80 | 1080P | Cookie |
| 120 | 4K | 大会员 |

---

## 首次配置 Cookie

**为什么需要 Cookie：** 1080P 以上画质和字幕需要登录。

**获取方法：**
1. 浏览器打开 bilibili.com 并登录
2. 按 `F12` → Console 标签
3. 输入 `document.cookie` 回车
4. 复制全部输出

**配置命令：**
```bash
python bilibili_auto.py config --cookie "你的Cookie"
```

无 Cookie 也可下载 720P 以下画质和封面图。

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `SKILL.md` | Agent 技能文档 |
| `bilibili_auto.py` | 主程序 |
| `check_config.py` | Cookie 检测 |
| `keyframe_decord.py` | 关键帧提取 |
| `bilibili_config.json` | 配置文件 |
| `启动下载.bat` | Windows 一键启动 |
| `decord-*-win_amd64.whl` | decord 离线依赖 (Windows) |
| `decord-*-manylinux*.whl` | decord 离线依赖 (Linux) |
| `numpy-*-manylinux*.whl` | numpy 离线依赖 (Linux PyPy) |
| `pillow-*-manylinux*.whl` | pillow 离线依赖 (Linux PyPy) |

---

## 安装

```bash
git clone https://github.com/TYJ-xy/bilibili-downloader.git
cd bilibili-downloader
pip install httpx tqdm
# 关键帧功能需要:
pip install decord pillow
```

---

## 技术实现

- **搜索**：B站 API `x/web-interface/search/all/v2`
- **视频列表**：`x/space/wbi/arc/search`（WBI 签名）
- **视频流**：`x/player/playurl`（DASH + 8K + 杜比）
- **字幕**：`x/player/wbi/v2` → JSON → TXT
- **断点续传**：HTTP Range，5 次重试
- **合并**：优先 ffmpeg copy（无损），降级 moviepy
- **关键帧**：decord 场景检测 + 均匀采样 → 50 张

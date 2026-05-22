---
name: bilibili-downloader
description: B站全自动视频下载器。输入UP主名称即可自动搜索→获取视频列表→按需下载视频/音频/字幕(txt)/封面/关键帧。支持多P、画质选择、逗号组合模式。首次使用自动弹出配置向导引导获取Cookie。
version: 1.4.0
category: media
---

# B站全自动下载器

## 首次安装

**首次运行时，程序会自动检测 Cookie 是否配置。** 如果未配置：

**方式一：双击 `启动下载.bat`** → 自动弹出配置向导 → 按提示粘贴 Cookie

**方式二：OpenClaw Agent 对话** → Agent 会自动检测并引导你获取 Cookie：
> "需要你的B站Cookie才能下载高清画质和字幕。获取方法：
> 1. 浏览器打开 bilibili.com 并登录
> 2. 按 F12 → Console 标签 → 输入 `document.cookie` 回车
> 3. 把输出的全部文字复制给我"

手动配置命令：
```bash
python bilibili_auto.py config --wizard
```

## 触发条件

当用户说以下类似内容时加载此技能：
- "下载XXX的视频/音频/字幕/封面" / "帮我下XXX的B站内容"
- "下载B站UP主XXX的封面图/关键帧"
- "帮我把XXX的最新N个视频下下来"
- 任何涉及从B站下载内容的请求

## 代理行为（Agent 执行指南）

### Step 0: 检查并获取 Cookie（每次必做）

**每次都先检查 Cookie 是否已配置。若未配置或过期，向用户索要。不要默默跳过。**

检查命令（Windows）：
```bash
python check_config.py"
```
或者：
```bash
python bilibili_auto.py" config --show
```

如果输出中 `cookie` 为空或不含 `SESSDATA`，或 `check_config.py` 返回非0，说明未配置或已过期。

**向用户提问索要 Cookie（以下为话术模板）：**

> "需要你的B站Cookie才能下载高清画质和字幕。获取方法：
> 1. 浏览器打开 bilibili.com 并登录
> 2. 按 F12 → Console 标签 → 输入 `document.cookie` 回车
> 3. 把输出的一大串文字全部复制给我
> 
> 如果不需要高清/字幕，我也可以无Cookie下载低画质版本（720P以下），要试试吗？"

用户提供Cookie后，写入配置：
```bash
python bilibili_auto.py" config --cookie "用户提供的完整Cookie"
```

**注意**：Cookie 是敏感信息，不要在任何地方明文展示 SESSDATA 的值。写入 config 后只告知用户"已配置"。

**无需 Cookie 的场景**：如果用户明确说不需要高清，或只下载封面图/低画质，可以直接运行。此时跳过索要Cookie步骤。

### Step 1: 解析用户意图

从用户输入提取：
- **UP主名称**（必填）
- **模式映射**：
  - 视频/video → `video`
  - 音频/声音/mp3 → `audio`
  - 字幕 → `subtitle`（输出 .txt）
  - 封面/封面图/cover → `cover`
  - 关键帧/keyframe/抽帧 → `keyframe`（优先 decord，降级 ffmpeg）
  - 全部/都要 → `all`（= video+audio+subtitle+cover，不含 keyframe）
- **组合**："封面和字幕" → `cover,subtitle`（逗号分隔）
- **数量**："最新N个" → `--limit N`；"全部" → `--limit 50`；未提及 → `--limit 5`
- **画质**："4K" → 120；"1080P" → 80；"720P" → 64；未提及 → 80
- **目标路径**：未提及 → 默认 `C:\Users\TYJ\Desktop`

### Step 2: 检查依赖（仅 keyframe 模式）

关键帧提取优先使用 decord（bat 启动时自动安装），降级使用 ffmpeg。无需手动检查。

### Step 3: 执行下载

```bash
python bilibili_auto.py" auto "UP主名" --mode <模式> --limit <数量> --quality <画质>
```

**编码处理**：在 Windows CMD 中执行时，需要先设置 UTF-8 环境，防止 emoji 崩溃：
```bash
cmd /c "chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python ..."
```

超时设置：video/audio/keyframe → timeout=400；subtitle/cover → timeout=120。

### Step 4: 报告结果

汇总输出文件，按类型列出。桌面上的文件用户可以直接看到。

## 模式参数速查

| 模式 | 输出 | 需要Cookie | 需要ffmpeg |
|------|------|:--:|:--:|
| `video` | .mp4 | 高清需要 | 推荐 |
| `audio` | .mp3 | 高清需要 | 推荐 |
| `subtitle` | .txt | ✅ | - |
| `cover` | .jpg | - | - |
| `keyframe` | _kf_01~50.jpg | 高清需要 | decord≥ffmpeg |
| `all` | 以上四项 | 高清需要 | 推荐 |
| `cover,subtitle` | 封面+字幕 | 字幕需要 | - |

## 画质代号

| 代号 | 画质 | 需要 |
|------|------|------|
| 16 | 360P | 无 |
| 32 | 480P | 无 |
| 64 | 720P | 无 |
| 80 | 1080P | Cookie |
| 112 | 1080P+ | Cookie |
| 116 | 1080P60 | Cookie |
| 120 | 4K | 大会员 |
| 127 | 8K | 大会员 |

## 配置文件

- **位置**：`~\.hermes\bilibili_config.json`（独立于skill文件夹，移动文件夹不影响配置）
- **首次配置**：`python bilibili_auto.py config --wizard`
- **查看配置**：`python bilibili_auto.py config --show`
- **手动设置**：`python bilibili_auto.py config --cookie "..." --output "C:\path"`

## 技术实现

- **搜索**：`x/web-interface/search/all/v2`（非WBI），从分类结果提取 `result_type=bili_user`
- **视频列表**：`x/space/wbi/arc/search`（需 WBI 签名）
- **视频流**：`x/player/playurl`（fnval=4048，DASH+8K+杜比）
- **字幕**：`x/player/wbi/v2`（WBI签名）→ JSON → TXT
- **WBI 密钥**：从 `x/web-interface/nav` 每日自动获取并缓存
- **断点续传**：HTTP Range头，5次重试（5s→25s递增）
- **合并**：优先 ffmpeg copy（无损），降级 moviepy
- **关键帧**：优先 decord（场景检测+均匀采样双轮策略）→ 降级 ffmpeg fps 抽帧 → 均匀采样到50张
- **首次检测**：`check_config.py` 检查 SESSDATA → exit 0/1
- **依赖自动安装**：bat 启动时自动检测并安装缺失的包。decord 优先从本地 `vendor\` 安装（离线），无本地包则从 PyPI 下载。

## 已知 Pitfalls

1. **搜索端点**：`/search/type` 和 `/wbi/search/type` 返回 `-1200` 反爬。必须用 `/search/all/v2`。
2. **时长格式**：space API 返回 `MM:SS` 字符串，非秒数。`int()` 会 ValueError。
3. **字幕毫秒**：浮点数秒 → `int(seconds*1000)%1000`，不能 `seconds%1000`。
4. **f-string**：Python 3.11 表达式内不能有反斜杠。需提前计算再插入。
5. **Windows ffmpeg**：scene filter 报 `-22`。优先用 decord 替代；ffmpeg 仅作降级方案。
6. **bat 编码**：bat 必须是 GBK 编码。UTF-8 bat 在中文 Windows CMD 下会乱码。
7. **emoji 编码**：Python print emoji 前必须 `chcp 65001` + `PYTHONIOENCODING=utf-8`。
8. **decord 安装**：bat 启动时优先从本地 `vendor\` 离线安装；无本地包则 pip 下载（约25MB，仅一次）。

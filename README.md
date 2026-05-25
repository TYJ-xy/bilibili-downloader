# B站下载器 v1.2 — 字幕降级策略

## 新增功能

当 B站字幕模式（`--mode subtitle`）无法下载独立字幕时（多数UP主使用硬字幕），**自动降级**为：
```
音频下载(低画质) → Whisper本地转录 → .srt + .txt字幕
```

## 安装

```bash
# 基础依赖
pip install httpx tqdm

# Whisper降级策略（需要时安装，约500MB）
pip install faster-whisper
```

首次运行 Whisper 时会自动下载模型（`small` 约 488MB），之后无需联网。

## 文件结构

```
bilibili-downloader/
├── bilibili_auto.py          # 主程序（含降级逻辑）
├── bilibili_config.json       # Cookie 配置
├── requirements.txt           # pip 依赖
├── scripts/
│   ├── whisper_fallback.py    # Whisper 转录脚本
│   └── whisper_batch.py       # 批量转录
└── vendor/                    # 离线包（可选）
```

## 使用

```bash
# 正常模式（有独立字幕时直接下载）
python bilibili_auto.py auto "影视飓风" --mode subtitle --limit 5

# 降级模式（无字幕时自动走音频+Whisper）
python bilibili_auto.py auto "盗月社食遇记" --mode subtitle --limit 5
# → 字幕失败 → 自动下载音频 → Whisper转录 → .srt+.txt
```

降级过程全自动，无需额外命令。

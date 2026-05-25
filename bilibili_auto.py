#!/usr/bin/env python3
"""
Bilibili 全自动下载器 — Hermes 技能核心脚本
============================================
功能：UP主名 → UID → 视频列表 → 按需下载

用法：
  python bilibili_auto.py search "UP主名"
  python bilibili_auto.py list <uid> [--limit 20] [--page 1]
  python bilibili_auto.py download <url|bvid> --mode video|audio|subtitle|cover|all
  python bilibili_auto.py auto "UP主名" --mode video --limit 5 --quality 80

模式: video(视频) audio(纯音频mp3) subtitle(字幕srt) cover(封面图) all(全部)
"""

import argparse, asyncio, hashlib, json, os, re, shutil, subprocess, sys, time, urllib.parse
from pathlib import Path
from typing import Optional
import httpx
from tqdm import tqdm

# 确保 ~/.local/bin 在 PATH 中（WSL ffmpeg 软链接位置）
os.environ["PATH"] = os.path.expanduser("~/.local/bin") + os.pathsep + os.environ.get("PATH", "")

# 平台检测
IS_WINDOWS = sys.platform == "win32"
IS_WSL = not IS_WINDOWS and os.path.exists("/proc/version") and "microsoft" in open("/proc/version").read().lower()

CONFIG_DIR = Path.home() / ".hermes"
CONFIG_FILE = CONFIG_DIR / "bilibili_config.json"
DEFAULT_OUTPUT = Path.home() / "Desktop" if IS_WINDOWS else (Path.home() / "Downloads" / "bilibili")

MIXIN_KEY_ENC_TAB = [
    46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,33,9,42,19,29,28,14,39,12,38,41,13,
    37,48,7,16,24,55,40,61,26,17,0,1,60,51,30,4,22,25,54,21,56,59,6,63,57,62,11,36,20,34,44,52
]

QUALITY_NAMES = {
    127:"超高清 8K",126:"杜比视界 4K",120:"超清 4K",116:"高清 1080P60",
    112:"高清 1080P+",80:"高清 1080P",74:"高清 720P60",64:"高清 720P",32:"清晰 480P",16:"流畅 360P"
}

BASE_HEADERS = {
    "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer":"https://www.bilibili.com/","Accept":"application/json, text/plain, */*",
    "Accept-Language":"zh-CN,zh;q=0.9,en;q=0.8",
}

# ─── 配置管理 ────────────────────────────────────────
def load_config() -> dict:
    if CONFIG_FILE.exists(): return json.loads(CONFIG_FILE.read_text())
    return {}

def save_config(cfg: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))

def get_cookie() -> str:
    cfg = load_config()
    return cfg.get("cookie", os.environ.get("BILIBILI_COOKIE", ""))

def get_output_dir() -> Path:
    cfg = load_config()
    return Path(cfg.get("output_dir", str(DEFAULT_OUTPUT)))

# ─── WBI 签名 ────────────────────────────────────────
class WbiSigner:
    def __init__(self):
        self._img_key: Optional[str] = None
        self._sub_key: Optional[str] = None
        self._fetch_date: str = ""

    def _need_refresh(self) -> bool:
        return self._fetch_date != time.strftime("%Y-%m-%d")

    async def _fetch_keys(self, client: httpx.AsyncClient):
        resp = await client.get("https://api.bilibili.com/x/web-interface/nav", headers=BASE_HEADERS)
        wbi_img = resp.json().get("data", {}).get("wbi_img", {})
        if wbi_img:
            self._img_key = wbi_img["img_url"].split("/")[-1].replace(".png", "")
            self._sub_key = wbi_img["sub_url"].split("/")[-1].replace(".png", "")
            self._fetch_date = time.strftime("%Y-%m-%d")

    async def sign(self, client: httpx.AsyncClient, params: dict) -> dict:
        if self._need_refresh(): await self._fetch_keys(client)
        if not self._img_key: return params
        mixin_key = "".join((self._img_key + self._sub_key)[i] for i in MIXIN_KEY_ENC_TAB)[:32]
        curr_time = round(time.time())
        signed = {**params, "wts": curr_time}
        signed = dict(sorted(signed.items()))
        filtered = {k: "".join(c for c in str(v) if c not in "!'()*") for k, v in signed.items()}
        query = urllib.parse.urlencode(filtered)
        w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
        return {**params, "wts": curr_time, "w_rid": w_rid}

wbi = WbiSigner()

# ─── B站 API ─────────────────────────────────────────
async def search_creator(name: str, client: httpx.AsyncClient) -> list[dict]:
    """搜索 UP 主"""
    url = "https://api.bilibili.com/x/web-interface/search/all/v2"
    headers = {**BASE_HEADERS}
    cookie = get_cookie()
    if cookie: headers["Cookie"] = cookie
    resp = await client.get(url, params={"keyword": name}, headers=headers)
    for cat in resp.json().get("data", {}).get("result", []):
        if cat.get("result_type") == "bili_user":
            return [{"mid": i.get("mid"), "name": i.get("uname", ""), "fans": i.get("fans", 0),
                     "videos": i.get("videos", 0), "sign": i.get("usign", ""),
                     "face": i.get("upic", "")} for i in cat.get("data", [])]
    return []

async def get_user_videos(mid: int, client: httpx.AsyncClient, page: int = 1, count: int = 50) -> dict:
    url = "https://api.bilibili.com/x/space/wbi/arc/search"
    params = await wbi.sign(client, {"mid": mid, "ps": min(count, 50), "pn": page, "order": "pubdate"})
    headers = {**BASE_HEADERS, "Referer": f"https://space.bilibili.com/{mid}"}
    cookie = get_cookie()
    if cookie: headers["Cookie"] = cookie
    resp = await client.get(url, params=params, headers=headers)
    data = resp.json()
    vlist = data.get("data", {}).get("list", {}).get("vlist", [])
    total = data.get("data", {}).get("page", {}).get("count", 0)
    return {"total": total, "page": page,
            "videos": [{"bvid": v.get("bvid"), "aid": v.get("aid"), "title": v.get("title", ""),
                        "duration": v.get("length", ""), "play": v.get("play", 0),
                        "created": v.get("created", 0), "description": v.get("description", ""),
                        "pic": v.get("pic", "")} for v in vlist]}

async def get_video_pages(bvid: str, client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get("https://api.bilibili.com/x/player/pagelist", params={"bvid": bvid}, headers=BASE_HEADERS)
    return resp.json().get("data", [])

async def get_video_info(bvid: str, client: httpx.AsyncClient) -> dict:
    resp = await client.get("https://api.bilibili.com/x/web-interface/view", params={"bvid": bvid}, headers=BASE_HEADERS)
    data = resp.json().get("data", {})
    return {"bvid": data.get("bvid"), "aid": data.get("aid"), "title": data.get("title", ""),
            "pic": data.get("pic", ""),
            "owner": {"mid": data.get("owner", {}).get("mid"), "name": data.get("owner", {}).get("name")},
            "pages": data.get("pages", []), "duration": data.get("duration", 0)}

async def get_subtitles(bvid: str, cid: int, client: httpx.AsyncClient) -> list[dict]:
    url = "https://api.bilibili.com/x/player/wbi/v2"
    params = await wbi.sign(client, {"bvid": bvid, "cid": cid})
    headers = {**BASE_HEADERS}
    cookie = get_cookie()
    if cookie: headers["Cookie"] = cookie
    resp = await client.get(url, params=params, headers=headers)
    subs = resp.json().get("data", {}).get("subtitle", {}).get("subtitles", [])
    result = []
    for sub in subs:
        url = sub.get("subtitle_url", "")
        if url.startswith("//"): url = "https:" + url
        result.append({"id": sub.get("id"), "lan": sub.get("lan", ""), "lan_doc": sub.get("lan_doc", ""),
                       "url": url, "is_ai": sub.get("ai_type", 0) > 0 or sub.get("lan", "").startswith("ai-")})
    return result

async def fetch_subtitle_json(subtitle_url: str, client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(subtitle_url, headers=BASE_HEADERS)
    return resp.json().get("body", [])

def subtitle_to_srt(subs: list[dict]) -> str:
    lines = []
    for i, sub in enumerate(subs, 1):
        start, end = sub.get("from", 0), sub.get("to", 0)
        content = sub.get("content", "")
        st = f"{int(start//3600):02d}:{int(start%3600//60):02d}:{int(start%60):02d},{int(start*1000)%1000:03d}"
        et = f"{int(end//3600):02d}:{int(end%3600//60):02d}:{int(end%60):02d},{int(end*1000)%1000:03d}"
        lines.append(f"{i}\n{st} --> {et}\n{content}\n")
    return "\n".join(lines)

# ─── 下载核心 ────────────────────────────────────────
async def get_stream_urls(bvid: str, cid: int, client: httpx.AsyncClient, quality: int = 80) -> Optional[dict]:
    url = "https://api.bilibili.com/x/player/playurl"
    params = {"bvid": bvid, "cid": cid, "qn": quality, "fnval": 4048, "fourk": 1}
    headers = {**BASE_HEADERS}
    cookie = get_cookie()
    if cookie: headers["Cookie"] = cookie
    resp = await client.get(url, params=params, headers=headers)
    data = resp.json()
    if data.get("code") != 0:
        print(f"  ❌ 获取播放地址失败: {data.get('message', '')}")
        return None
    result = data.get("data", {})
    actual_quality = result.get("quality", quality)
    dash = result.get("dash", {})
    if dash:
        video_streams = sorted(dash.get("video", []), key=lambda x: x.get("id", 0), reverse=True)
        audio_streams = sorted(dash.get("audio", []), key=lambda x: x.get("bandwidth", 0), reverse=True)
        return {"format": "dash", "quality": actual_quality,
                "quality_name": QUALITY_NAMES.get(actual_quality, f"未知({actual_quality})"),
                "video_url": video_streams[0]["baseUrl"] if video_streams else None,
                "audio_url": audio_streams[0]["baseUrl"] if audio_streams else None,
                "available_qualities": sorted(set(s["id"] for s in video_streams), reverse=True)}
    durl = result.get("durl", [])
    if durl:
        return {"format": "durl", "quality": actual_quality,
                "quality_name": QUALITY_NAMES.get(actual_quality, f"未知({actual_quality})"),
                "video_url": durl[0]["url"], "audio_url": None}
    return None

async def download_file(url: str, filepath: Path, client: httpx.AsyncClient, desc: str = "") -> bool:
    """断点续传下载，最多5次重试"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    headers = {**BASE_HEADERS, "Referer": "https://www.bilibili.com/"}
    for attempt in range(5):
        try:
            existing = filepath.stat().st_size if filepath.exists() else 0
            if existing > 0: headers["Range"] = f"bytes={existing}-"
            async with client.stream("GET", url, headers=headers, timeout=httpx.Timeout(300, connect=15)) as resp:
                if resp.status_code == 416: return True
                if resp.status_code not in (200, 206):
                    if attempt < 4: await asyncio.sleep(5); continue
                    return False
                total = int(resp.headers.get("content-length", 0)) + existing
                with open(filepath, "ab" if existing else "wb") as f:
                    with tqdm(total=total, initial=existing, unit="B", unit_scale=True, desc=desc, leave=False) as pbar:
                        async for chunk in resp.aiter_bytes(8192):
                            f.write(chunk); pbar.update(len(chunk))
            return True
        except (httpx.RemoteProtocolError, httpx.RequestError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            if attempt < 4:
                await asyncio.sleep((attempt + 1) * 5)
            else:
                print(f"  ❌ 下载失败: {e}"); return False
    return False

async def download_video_file(bvid, cid, title, quality, output_dir: Path, client, part=0, total_parts=1) -> Optional[Path]:
    streams = await get_stream_urls(bvid, cid, client, quality)
    if not streams: return None
    part_suffix = f"_P{part}" if total_parts > 1 else ""
    safe = re.sub(r'[<>:"/\\|?*]', '_', title)
    if streams["format"] == "durl":
        out = output_dir / f"{safe}{part_suffix}.mp4"
        return out if await download_file(streams["video_url"], out, client, desc=f"{safe}{part_suffix}") else None
    vp = output_dir / f"{safe}{part_suffix}_video.m4s"
    ap = output_dir / f"{safe}{part_suffix}_audio.m4s"
    vok = await download_file(streams["video_url"], vp, client, desc=f"V {safe}{part_suffix}")
    aok = await download_file(streams["audio_url"], ap, client, desc=f"A {safe}{part_suffix}")
    if not (vok and aok): return None
    out = output_dir / f"{safe}{part_suffix}.mp4"
    if shutil.which("ffmpeg"):
        result = subprocess.run(["ffmpeg","-i",str(vp),"-i",str(ap),"-c:v","copy","-c:a","copy",str(out),"-y","-loglevel","error"], capture_output=True, text=True)
        if result.returncode == 0 and out.exists():
            vp.unlink(missing_ok=True); ap.unlink(missing_ok=True)
            return out
        else:
            stderr = result.stderr.strip()
            if stderr:
                print(f"  ⚠ ffmpeg: {stderr[:200]}", file=sys.stderr)
    try:
        from moviepy.editor import VideoFileClip
        clip = VideoFileClip(str(vp)); audio = VideoFileClip(str(ap)).audio
        if audio: clip = clip.set_audio(audio)
        clip.write_videofile(str(out), preset="ultrafast", threads=4, logger=None); clip.close()
        vp.unlink(missing_ok=True); ap.unlink(missing_ok=True)
        return out
    except Exception as e:
        print(f"  ❌ 合并失败: {e}"); return None

async def download_audio_only(bvid, cid, title, quality, output_dir: Path, client, part=0, total_parts=1) -> Optional[Path]:
    streams = await get_stream_urls(bvid, cid, client, quality)
    if not streams: return None
    part_suffix = f"_P{part}" if total_parts > 1 else ""
    safe = re.sub(r'[<>:"/\\|?*]', '_', title)
    if streams.get("audio_url"):
        raw = output_dir / f"{safe}{part_suffix}_audio.m4s"
        if not await download_file(streams["audio_url"], raw, client, desc=f"A {safe}{part_suffix}"): return None
        mp3 = output_dir / f"{safe}{part_suffix}.mp3"
        if shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg","-i",str(raw),"-acodec","libmp3lame","-q:a","2",str(mp3),"-y","-loglevel","error"], capture_output=True)
        raw.unlink(missing_ok=True)
        return mp3 if mp3.exists() else raw
    elif streams.get("video_url"):
        tmp = output_dir / f"{safe}{part_suffix}_tmp.mp4"
        if not await download_file(streams["video_url"], tmp, client, desc=f"DL {safe}{part_suffix}"): return None
        mp3 = output_dir / f"{safe}{part_suffix}.mp3"
        if shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg","-i",str(tmp),"-vn","-acodec","libmp3lame","-q:a","2",str(mp3),"-y","-loglevel","error"], capture_output=True)
        tmp.unlink(missing_ok=True)
        return mp3 if mp3.exists() else None
    return None

async def download_subtitles_only(bvid, cid, title, output_dir: Path, client, part=0, total_parts=1) -> Optional[Path]:
    """仅下载B站原始字幕（不包含Whisper回退），供外部直接调用"""
    subs = await get_subtitles(bvid, cid, client)
    if not subs: return None
    part_suffix = f"_P{part}" if total_parts > 1 else ""
    safe = re.sub(r'[<>:"/\\|?*]', '_', title)
    priority = ["zh","ai-zh","zh-CN","zh-Hans","zh-TW","en"]
    chosen = None
    for lang in priority:
        for s in subs:
            if s["lan"] == lang: chosen = s; break
        if chosen: break
    if not chosen: chosen = subs[0]
    sub_json = await fetch_subtitle_json(chosen["url"], client)
    srt = subtitle_to_srt(sub_json)
    srt_path = output_dir / f"{safe}{part_suffix}.srt"
    srt_path.write_text(srt, encoding="utf-8")
    # 同时保存纯文本版
    txt = "\n".join(sub.get("content", "") for sub in sub_json)
    txt_path = output_dir / f"{safe}{part_suffix}.txt"
    txt_path.write_text(txt, encoding="utf-8")
    return [srt_path, txt_path]  # 返回两个文件


async def download_subtitles_smart(bvid, cid, title, output_dir: Path, client,
                                    quality: int = 16, part=0, total_parts=1):
    """智能字幕策略（三步决策树）：
    1. 无Cookie -> 直接下音频，标记需要Whisper转录
    2. 有Cookie + UP主上传了字幕 -> 下载B站原始字幕
    3. 有Cookie + UP主没上传 -> 下音频，标记需要Whisper转录
    返回: (files: list, need_whisper: bool)
    """
    cookie = get_cookie()
    has_cookie = bool(cookie)

    if not has_cookie:
        print(f"    \u2139 无Cookie，跳过B站字幕API -> 直接下载音频供Whisper转录")
        audio_path = await download_audio_only(bvid, cid, title, quality, output_dir, client,
                                                part=part, total_parts=total_parts)
        if audio_path:
            return [("audio_for_whisper", str(audio_path))], True
        return [], False

    subs = await get_subtitles(bvid, cid, client)
    if subs:
        print(f"    \u2705 检测到 {len(subs)} 个原始字幕轨道 -> 下载B站字幕")
        result = await download_subtitles_only(bvid, cid, title, output_dir, client,
                                                part=part, total_parts=total_parts)
        if result:
            files = []
            for fp in result:
                ext = Path(fp).suffix
                label = "subtitle_srt" if ext == ".srt" else "subtitle_txt"
                files.append((label, str(fp)))
            return files, False

    print(f"    \u2139 UP主未上传字幕 -> 下载音频供Whisper转录")
    audio_path = await download_audio_only(bvid, cid, title, quality, output_dir, client,
                                            part=part, total_parts=total_parts)
    if audio_path:
        return [("audio_for_whisper", str(audio_path))], True
    return [], False


async def download_cover(bvid, title, output_dir: Path, client, part=0, total_parts=1) -> Optional[Path]:
    """下载视频封面图"""
    info = await get_video_info(bvid, client)
    pic_url = info.get("pic", "")
    if not pic_url:
        return None
    if pic_url.startswith("//"): pic_url = "https:" + pic_url
    part_suffix = f"_P{part}" if total_parts > 1 else ""
    safe = re.sub(r'[<>:"/\\|?*]', '_', title)
    ext = pic_url.split(".")[-1].split("?")[0] or "jpg"
    cover_path = output_dir / f"{safe}{part_suffix}_cover.{ext}"
    ok = await download_file(pic_url, cover_path, client, desc=f"Cover {safe}")
    return cover_path if ok else None

async def extract_keyframes(video_path: Path, output_dir: Path, title: str,
                            threshold: float = 0.4, max_frames: int = 50) -> list[Path]:
    """从视频中提取关键帧（基于镜头检测）"""
    # 找 ffmpeg: 先 PATH，再 ~/.local/bin，再 Windows D盘
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        for candidate in [
            "/mnt/d/下载/ffmpeg-2026-05-11-git-17bc88e67f-full_build/bin/ffmpeg.exe",
            os.path.expanduser("~/.local/bin/ffmpeg"),
        ]:
            if os.path.exists(candidate):
                ffmpeg = candidate
                break
    if not ffmpeg:
        print("  ⚠️ 需要 ffmpeg 来提取关键帧")
        return []

    # WSL 兼容：若 ffmpeg 是 Windows exe（或指向它的软链接），把路径转成 Windows 格式
    # Windows 原生运行则无需转换
    need_path_convert = not IS_WINDOWS and (
        ffmpeg.endswith(".exe") or os.path.realpath(ffmpeg).endswith(".exe")
    )
    def to_ffmpeg_path(p: Path) -> str:
        if need_path_convert:
            s = str(p.resolve())
            if s.startswith("/mnt/"):
                drive = s[5:6].upper()
                win_path = s[6:].replace("/", "\\")
                return f"{drive}:{win_path}"
        return str(p)

    safe = re.sub(r'[<>:"/\\|?*]', '_', title)
    out_pattern = str(output_dir / f"{safe}_kf%03d.jpg")
    if need_path_convert:
        sep = "\\"
        out_pattern = to_ffmpeg_path(output_dir) + f"{sep}{safe}_kf%03d.jpg"

    cmd = [
        ffmpeg, "-i", to_ffmpeg_path(video_path),
        "-vf", f"fps=1/{max(1, int(threshold * 10))},scale=1280:-2",
        "-vsync", "vfr", "-frame_pts", "1",
        "-loglevel", "error", "-y",
        out_pattern
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # 收集生成的文件，限制数量
    frames = sorted(output_dir.glob(f"{safe}_kf*.jpg"))
    if len(frames) > max_frames:
        # 均匀采样到 max_frames
        step = len(frames) / max_frames
        keep = [frames[int(i * step)] for i in range(max_frames)]
        for f in frames:
            if f not in keep:
                f.unlink()
        frames = keep
    # 重命名为有序编号
    for i, f in enumerate(frames, 1):
        new_name = output_dir / f"{safe}_kf_{i:02d}.jpg"
        f.rename(new_name)
    return list(sorted(output_dir.glob(f"{safe}_kf_*.jpg")))

async def download_keyframes(bvid, cid, title, quality, output_dir: Path, client,
                             part=0, total_parts=1) -> list[Path]:
    """下载视频流并提取关键帧（无需合并音视频）"""
    part_suffix = f"_P{part}" if total_parts > 1 else ""
    safe = re.sub(r'[<>:"/\\|?*]', '_', title)

    # 获取流地址
    streams = await get_stream_urls(bvid, cid, client, quality)
    if not streams:
        return []

    video_url = streams.get("video_url")
    if not video_url:
        return []

    # 下载视频流（不合并音频，关键帧只需要画面）
    tmp_video = output_dir / f"{safe}{part_suffix}_kf_src.m4s"
    print(f"  ⬇ 下载视频流用于关键帧提取...")
    ok = await download_file(video_url, tmp_video, client, desc=f"KF {safe}{part_suffix}")
    if not ok:
        return []

    # 提取关键帧
    frames = await extract_keyframes(tmp_video, output_dir, safe + part_suffix)

    # 清理临时视频
    tmp_video.unlink(missing_ok=True)
    return frames

# ─── 模式解析 ────────────────────────────────────────
def expand_modes(mode: str) -> set:
    """解析模式字符串: 'all' → 全部(不含keyframe), 'cover,subtitle' → {cover, subtitle}"""
    if mode == "all":
        return {"video", "audio", "subtitle", "cover"}
    return {m.strip() for m in mode.split(",")}

# ─── 高级编排 ────────────────────────────────────────
async def process_video(bvid, title, cid, pages, mode, quality, output_dir: Path, client) -> dict:
    modes = expand_modes(mode)
    result = {"bvid": bvid, "title": title, "mode": mode, "files": [], "errors": []}

    async def process_one(bv, ci, pt, pnum, ptotal):
        r = {"files": [], "errors": []}
        if "video" in modes:
            f = await download_video_file(bv, ci, pt, quality, output_dir, client, part=pnum, total_parts=ptotal)
            if f: r["files"].append(("video", str(f)))
            else: r["errors"].append(f"视频下载失败: P{pnum}")
        if "audio" in modes:
            f = await download_audio_only(bv, ci, pt, quality, output_dir, client, part=pnum, total_parts=ptotal)
            if f: r["files"].append(("audio", str(f)))
            else: r["errors"].append(f"音频提取失败: P{pnum}")
        if "subtitle" in modes:
            sub_files, need_whisper = await download_subtitles_smart(bv, ci, pt, output_dir, client,
                                                                      quality=quality, part=pnum, total_parts=ptotal)
            for label, fpath in sub_files:
                r["files"].append((label, fpath))
            if need_whisper:
                r["_whisper_needed"] = True
        if "cover" in modes:
            f = await download_cover(bv, pt, output_dir, client, part=pnum, total_parts=ptotal)
            if f: r["files"].append(("cover", str(f)))
        if "keyframe" in modes:
            frames = await download_keyframes(bv, ci, pt, quality, output_dir, client,
                                              part=pnum, total_parts=ptotal)
            if frames:
                for fp in frames:
                    r["files"].append(("keyframe", str(fp)))
            else:
                r["errors"].append(f"关键帧提取失败: P{pnum}")
        return r

    if len(pages) <= 1:
        ci = pages[0]["cid"] if pages else cid
        pt = pages[0].get("part", title) if pages else title
        r = await process_one(bvid, ci, pt, 0, 1)
        result["files"] = r["files"]; result["errors"] = r["errors"]
    else:
        for i, page in enumerate(pages, 1):
            pt = page.get("part", f"P{i}"); pcid = page.get("cid", cid)
            r = await process_one(bvid, pcid, pt, i, len(pages))
            result["files"].extend(r["files"]); result["errors"].extend(r["errors"])
    return result

async def auto_download(creator_name: str, mode: str = "video", limit: int = 10,
                        quality: int = 80, output_dir: Path = None) -> list[dict]:
    if output_dir is None: output_dir = get_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=15), follow_redirects=True) as client:
        # 1. 搜索
        print(f"🔍 搜索 UP 主: {creator_name}")
        users = await search_creator(creator_name, client)
        if not users: print(f"❌ 未找到: {creator_name}"); return []
        best = users[0]; best_score = 0
        for u in users:
            score = 0
            if u["name"] == creator_name: score = 100
            elif creator_name.lower() in u["name"].lower(): score = 50
            score += min(u["fans"] / 10000, 20)
            if score > best_score: best_score = score; best = u
        print(f"\n找到 {len(users)} 个结果:")
        for i, u in enumerate(users[:5], 1):
            print(f"  {i}. {u['name']} (UID: {u['mid']}) 粉丝: {u['fans']:,}  视频: {u['videos']}")
        print(f"\n✅ 选择: {best['name']} (UID: {best['mid']})")

        # 2. 列表
        print(f"\n📋 获取视频列表 (最多 {limit} 个)...")
        all_videos, page = [], 1
        while len(all_videos) < limit:
            result = await get_user_videos(best["mid"], client, page=page)
            if not result["videos"]: break
            all_videos.extend(result["videos"])
            if len(result["videos"]) < 50: break
            page += 1
        videos = all_videos[:limit]
        print(f"共 {len(videos)} 个视频:\n")
        for i, v in enumerate(videos, 1):
            print(f"  {i:2d}. [{v['bvid']}] {v['title'][:48]:48s}  ⏱{v.get('duration','?')}  ▶{v.get('play',0):,}")

        # 3. 下载
        div = f"\n{'='*60}"
        print(f"{div}\n⬇ 开始下载 | 模式: {mode} | 清晰度: {QUALITY_NAMES.get(quality, quality)}\n   输出: {output_dir}\n{div}")
        results = []
        for i, v in enumerate(videos, 1):
            bvid, title = v["bvid"], v["title"]
            print(f"\n[{i}/{len(videos)}] {title}")
            pages = await get_video_pages(bvid, client)
            cid = pages[0]["cid"] if pages else 0
            result = await process_video(bvid, title, cid, pages, mode, quality, output_dir, client)
            results.append(result)

        # 4. 汇总
        icon_map = {"video":"🎬","audio":"🎵","subtitle_srt":"📝","subtitle_txt":"📄","cover":"🖼","keyframe":"🎞"}
        print(f"{div}\n📊 汇总:")
        print(f"   ✅ 成功: {sum(len(r['files']) for r in results)} 个文件")
        print(f"   ❌ 失败: {sum(len(r['errors']) for r in results)}")
        for r in results:
            if r["files"]:
                print(f"\n  📦 {r['title'][:40]}:")
                for ftype, fpath in r["files"]:
                    print(f"     {icon_map.get(ftype,'📄')} ({ftype}): {fpath}")
            if r["errors"]:
                for e in r["errors"]: print(f"     ❌ {e}")
        
                # 智能字幕降级：对标记了 _whisper_needed 的视频，统一跑 Whisper 转录
        whisper_needed = any(r.get("_whisper_needed") for r in results)
        if whisper_needed:
            print(f"\n🤖 部分视频需要 Whisper 转录...")
            import subprocess as sp
            whisper_script = Path(__file__).parent / "scripts" / "whisper_fallback.py"
            if whisper_script.exists():
                sp.run([sys.executable, str(whisper_script), str(output_dir), "small"], timeout=600)
                print(f"  ✅ Whisper 转录完成")
            else:
                print(f"  ⚠ 未找到 whisper_fallback.py，音频文件在: {output_dir}")
        return results

# ─── CLI ─────────────────────────────────────────────
async def cmd_search(args):
    async with httpx.AsyncClient(follow_redirects=True) as cl:
        users = await search_creator(args.name, cl)
    print(json.dumps(users, indent=2, ensure_ascii=False) if users else f"未找到: {args.name}")

async def cmd_list(args):
    async with httpx.AsyncClient(follow_redirects=True) as cl:
        r = await get_user_videos(args.uid, cl, page=args.page, count=args.limit)
    print(json.dumps({"total": r["total"], "page": r["page"], "videos": r["videos"]}, indent=2, ensure_ascii=False))

async def cmd_download(args):
    output_dir = Path(args.output) if args.output else get_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    bvid = args.url
    if "bilibili.com" in bvid:
        m = re.search(r'/(BV[a-zA-Z0-9]+|av\d+)', bvid)
        if m: bvid = m.group(1)
    async with httpx.AsyncClient(follow_redirects=True) as cl:
        info = await get_video_info(bvid, cl)
        if not info.get("title"): print(f"❌ 无法获取信息: {bvid}"); return
        pages = info.get("pages", [])
        cid = pages[0]["cid"] if pages else 0
        if not cid:
            pages = await get_video_pages(bvid, cl)
            cid = pages[0]["cid"] if pages else 0
        result = await process_video(bvid, info["title"], cid, pages, args.mode, args.quality, output_dir, cl)
    print(json.dumps(result, indent=2, ensure_ascii=False))

async def cmd_auto(args):
    await auto_download(creator_name=args.name, mode=args.mode, limit=args.limit,
                        quality=args.quality, output_dir=Path(args.output) if args.output else None)

async def cmd_config(args):
    cfg = load_config()
    if args.cookie is not None: cfg["cookie"] = args.cookie
    if args.output: cfg["output_dir"] = args.output
    if args.show: print(json.dumps(cfg, indent=2, ensure_ascii=False)); return
    save_config(cfg)
    print(f"✅ 配置已保存到 {CONFIG_FILE}")

def main():
    parser = argparse.ArgumentParser(description="B站全自动下载器 v1.1")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("config", help="管理配置")
    p.add_argument("--cookie"); p.add_argument("--output"); p.add_argument("--show", action="store_true")
    p.set_defaults(func=lambda a: asyncio.run(cmd_config(a)))
    p = sub.add_parser("search", help="搜索UP主"); p.add_argument("name")
    p.set_defaults(func=lambda a: asyncio.run(cmd_search(a)))
    p = sub.add_parser("list", help="列出UP主视频"); p.add_argument("uid", type=int)
    p.add_argument("--limit", type=int, default=20); p.add_argument("--page", type=int, default=1)
    p.set_defaults(func=lambda a: asyncio.run(cmd_list(a)))
    p = sub.add_parser("download", help="下载单个视频"); p.add_argument("url")
    p.add_argument("--mode", default="video", help="video/audio/subtitle/cover/all or comma combo like cover,subtitle")
    p.add_argument("--quality", type=int, default=80); p.add_argument("--output")
    p.set_defaults(func=lambda a: asyncio.run(cmd_download(a)))
    p = sub.add_parser("auto", help="全自动下载UP主视频"); p.add_argument("name")
    p.add_argument("--mode", default="video", help="video/audio/subtitle/cover/all or comma combo like cover,subtitle")
    p.add_argument("--limit", type=int, default=5); p.add_argument("--quality", type=int, default=80)
    p.add_argument("--output")
    p.set_defaults(func=lambda a: asyncio.run(cmd_auto(a)))
    args = parser.parse_args()
    if hasattr(args, "func"): args.func(args)
    else: parser.print_help()

if __name__ == "__main__":
    main()

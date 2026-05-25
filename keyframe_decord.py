"""
Keyframe extraction using decord (pure Python bindings, ~25 MB total)
Replaces ffmpeg for the keyframe mode.

Install: pip install decord
Usage:   python keyframe_decord.py video.m4s output_dir/
"""

import re
import numpy as np
from pathlib import Path
from PIL import Image


def extract_keyframes_decord(
    video_path: Path,
    output_dir: Path,
    title: str,
    max_frames: int = 50,
    scene_threshold: float = 30.0,
):
    """
    Extract keyframes from video using decord.

    Two modes combined:
    1. Evenly sample frames at regular intervals
    2. Scene change detection — keep frames where the scene shifts significantly

    Returns list of output Paths.
    """
    from decord import VideoReader, cpu

    vr = VideoReader(str(video_path), ctx=cpu(0))
    total_frames = len(vr)
    fps = vr.get_avg_fps()

    if total_frames == 0:
        print("  ⚠️ 视频帧数为0，无法提取关键帧")
        return []

    safe = re.sub(r'[<>:"/\\|?*]', '_', title)

    # Strategy: read frames at fixed interval, detect scene changes
    # For a 10-min video at 30fps = 18000 frames
    # Sample every 6 frames → 3000 candidate frames → filter by scene change → top 50
    step = max(1, total_frames // 3000)  # Sample up to 3000 frames
    candidate_indices = list(range(0, total_frames, step))

    frames = []
    prev_hist = None

    print(f"  🎬 视频: {total_frames}帧, {fps:.0f}fps, 采样{len(candidate_indices)}帧...")

    # Batch read for performance (decord can read multiple frames at once)
    batch_size = 100
    for batch_start in range(0, len(candidate_indices), batch_size):
        batch_indices = candidate_indices[batch_start : batch_start + batch_size]
        batch_frames = vr.get_batch(batch_indices).asnumpy()  # (N, H, W, 3) RGB

        for i, idx in enumerate(batch_indices):
            frame = batch_frames[i]
            # Convert to PIL for histogram
            pil_img = Image.fromarray(frame)

            if scene_threshold > 0 and prev_hist is not None:
                # Scene change detection via histogram difference
                hist = pil_img.histogram()
                diff = sum(abs(h - p) for h, p in zip(hist, prev_hist)) / sum(hist) * 100
                if diff < scene_threshold:
                    continue  # Skip similar frames
                prev_hist = hist
            elif prev_hist is None:
                prev_hist = pil_img.histogram()

            frames.append((idx, pil_img))

    # If scene detection filtered too few, fall back to even sampling
    if len(frames) < max_frames // 2:
        print(f"  ⚠️ 场景检测仅找到{len(frames)}帧，改用均匀采样")
        frames = []
        step_uniform = max(1, total_frames // max_frames)
        uniform_indices = list(range(0, total_frames, step_uniform))[:max_frames]
        batch_frames = vr.get_batch(uniform_indices).asnumpy()
        for i, idx in enumerate(uniform_indices):
            frames.append((idx, Image.fromarray(batch_frames[i])))

    # Limit to max_frames (already pre-filtered by scene detection)
    frames = frames[:max_frames]

    # Save
    output_files = []
    for i, (frame_idx, pil_img) in enumerate(frames, 1):
        out_path = output_dir / f"{safe}_kf_{i:02d}.jpg"
        pil_img.save(str(out_path), "JPEG", quality=90)
        output_files.append(out_path)

    print(f"  ✅ 提取 {len(output_files)} 张关键帧")
    return output_files


# ─── CLI test ─────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python keyframe_decord.py <video.m4s> <output_dir>")
        sys.exit(1)

    video = Path(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)

    extract_keyframes_decord(video, out, video.stem)

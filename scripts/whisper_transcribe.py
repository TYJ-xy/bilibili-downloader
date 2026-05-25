#!/usr/bin/env python3
"""Whisper transcription — B站音频→SRT字幕兜底"""
from faster_whisper import WhisperModel
import os, time, glob, sys

# Find .m4s audio files
locations = ["/home/tyj/whisper_audio","/mnt/c/Users/TYJ/Desktop","/mnt/c/Users/tyj/Desktop"]
files = []
for loc in locations:
    if os.path.isdir(loc):
        found = glob.glob(os.path.join(loc, "*.m4s"))
        found += glob.glob(os.path.join(loc, "**/*.m4s"), recursive=True)
        files.extend(found)
        if found: break

if not files:
    print("❌ 找不到 .m4s 文件")
    sys.exit(1)

files.sort(key=os.path.getmtime, reverse=True)
model = WhisperModel("small", device="cpu", compute_type="int8")

def fmt(s):
    return f"{int(s//3600):02d}:{int((s%3600)//60):02d}:{int(s%60):02d},{int((s%1)*1000):03d}"

for f in files:
    name = os.path.basename(f)
    if os.path.exists(f.replace('.m4s','.srt')): continue
    print(f"  {name[:50]}...")
    segs, info = model.transcribe(f, language="zh", beam_size=5, vad_filter=True)
    sl = list(segs)
    for ext, content in [
        ('.srt', '\n'.join(f"{j+1}\n{fmt(s.start)} --> {fmt(s.end)}\n{s.text.strip()}" for j,s in enumerate(sl))),
        ('.txt', '\n'.join(s.text.strip() for s in sl))
    ]:
        with open(f.replace('.m4s', ext), 'w', encoding='utf-8') as fw: fw.write(content)
    print(f"    ✅ {len(sl)}段 → {f.replace('.m4s','.srt')}")

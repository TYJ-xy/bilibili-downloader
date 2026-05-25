#!/usr/bin/env python3
"""Transcribe 4 episodes with small model"""
from faster_whisper import WhisperModel
import time, os, glob

files = sorted(glob.glob("/home/tyj/whisper_audio/*.m4s"))
model = WhisperModel("small", device="cpu", compute_type="int8")

def fmt(s):
    return f"{int(s//3600):02d}:{int((s%3600)//60):02d}:{int(s%60):02d},{int((s%1)*1000):03d}"

for i, f in enumerate(files):
    name = os.path.basename(f)
    print(f"[{i+1}/4] {name[:50]}...")
    t1 = time.time()
    segs, info = model.transcribe(f, language="zh", beam_size=5, vad_filter=True)
    sl = list(segs)
    text = "\n".join(s.text.strip() for s in sl)

    out = f.replace('.m4s', '.srt')
    with open(out, 'w', encoding='utf-8') as fw:
        for j, s in enumerate(sl):
            fw.write(f"{j+1}\n{fmt(s.start)} --> {fmt(s.end)}\n{s.text.strip()}\n\n")

    txt = f.replace('.m4s', '.txt')
    with open(txt, 'w', encoding='utf-8') as fw:
        fw.write(text)

    print(f"   ⏱{time.time()-t1:.0f}s {len(sl)}段 {len(text)}字")
    print(f"   {text[:80]}...")
    print()

print("✅ 完成")

#!/usr/bin/env python3
"""Whisper降级策略 — 音频下载后自动转录为字幕"""
from faster_whisper import WhisperModel
import os, sys, time, glob

def transcribe_audio_to_subtitle(audio_path, model_size="small"):
    """Transcribe audio file to SRT + TXT subtitles."""
    print(f"🎙 Whisper转录: {os.path.basename(audio_path)}")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    
    t1 = time.time()
    segs, info = model.transcribe(audio_path, language="zh", beam_size=5, vad_filter=True)
    sl = list(segs)
    text = "\n".join(s.text.strip() for s in sl)
    
    def fmt(s):
        return f"{int(s//3600):02d}:{int((s%3600)//60):02d}:{int(s%60):02d},{int((s%1)*1000):03d}"
    
    srt_path = audio_path.replace('.m4s', '.srt').replace('_audio', '')
    with open(srt_path, 'w', encoding='utf-8') as f:
        for j, s in enumerate(sl):
            f.write(f"{j+1}\n{fmt(s.start)} --> {fmt(s.end)}\n{s.text.strip()}\n\n")
    
    txt_path = srt_path.replace('.srt', '.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(text)
    
    print(f"  ✅ {len(sl)}段 {len(text)}字 ⏱{time.time()-t1:.0f}s")
    return srt_path, txt_path

def process_audio_files(directory, model_size="small"):
    """Process all .m4s audio files in directory, transcribing to subtitles."""
    files = glob.glob(os.path.join(directory, "*.m4s"))
    if not files:
        files = glob.glob(os.path.join(directory, "**/*.m4s"), recursive=True)
    
    results = []
    for f in sorted(files):
        try:
            srt, txt = transcribe_audio_to_subtitle(f, model_size)
            results.append((srt, txt))
        except Exception as e:
            print(f"  ❌ {os.path.basename(f)}: {e}")
    
    return results

if __name__ == "__main__":
    if len(sys.argv) > 1:
        directory = sys.argv[1]
    else:
        directory = os.getcwd()
    model = sys.argv[2] if len(sys.argv) > 2 else "small"
    process_audio_files(directory, model)

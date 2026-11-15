#!/usr/bin/env python3
"""用 edge-tts（微軟神經語音）把每篇課程與新聞做成 MP3。

真正的音檔才能在 iPhone 鎖定畫面、背景、藍牙與 CarPlay「播放中」
持續播放並用方向盤／螢幕的上一首、下一首切換課程。

每個音檔內容：英文正常速 → 停頓 → 中文翻譯 → 停頓 → 英文慢速 → 關鍵片語（英＋中）
檔名含內容雜湊，課程內容改了才會重新產生。輸出 data/audio.json 對照表。
需求：pip install edge-tts；系統需有 ffmpeg。
"""
import asyncio
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

import edge_tts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_DIR = os.path.join(ROOT, "audio")
MANIFEST = os.path.join(ROOT, "data", "audio.json")
EN_VOICE = os.environ.get("EN_VOICE", "en-US-AriaNeural")
EN_VOICE_NEWS = os.environ.get("EN_VOICE_NEWS", "en-US-GuyNeural")
ZH_VOICE = os.environ.get("ZH_VOICE", "zh-TW-HsiaoChenNeural")


def load(path, default):
    try:
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def digest(item):
    raw = json.dumps([item.get("en"), item.get("zh"), item.get("phrases"), EN_VOICE, ZH_VOICE], ensure_ascii=False)
    return hashlib.sha1(raw.encode()).hexdigest()[:8]


async def tts(text, voice, rate, path):
    for attempt in range(3):
        try:
            await edge_tts.Communicate(text, voice, rate=rate).save(path)
            if os.path.getsize(path) > 0:
                return
        except Exception as e:
            print(f"  tts retry {attempt + 1}: {e}", file=sys.stderr)
            await asyncio.sleep(2 * (attempt + 1))
    raise RuntimeError("edge-tts failed")


def silence(path, sec):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "anullsrc=r=24000:cl=mono", "-t", str(sec), "-q:a", "9",
                    "-acodec", "libmp3lame", path], check=True)


async def build(item, out_path, tmp):
    en_voice = EN_VOICE_NEWS if item["id"].startswith("N") else EN_VOICE
    parts = []
    s1, s2 = os.path.join(tmp, "s1.mp3"), os.path.join(tmp, "s2.mp3")
    silence(s1, 1.0)
    silence(s2, 2.0)

    async def seg(name, text, voice, rate):
        p = os.path.join(tmp, name + ".mp3")
        await tts(text, voice, rate, p)
        parts.append(p)

    await seg("en1", item["en"], en_voice, "-5%")
    parts.append(s2)
    if item.get("zh"):
        await seg("zh", item["zh"], ZH_VOICE, "+0%")
        parts.append(s2)
    await seg("en2", item["en"], en_voice, "-30%")
    parts.append(s2)
    for i, (en, zh) in enumerate(item.get("phrases", [])[:6]):
        await seg(f"p{i}e", en, en_voice, "-15%")
        parts.append(s1)
        await seg(f"p{i}z", zh, ZH_VOICE, "+0%")
        parts.append(s1)
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{p}'\n" for p in parts)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-ac", "1", "-ar", "24000", "-b:a", "48k", "-acodec", "libmp3lame",
                    "-metadata", f"title={item['title']}", "-metadata", "artist=English 800",
                    out_path], check=True)


async def main():
    os.makedirs(AUDIO_DIR, exist_ok=True)
    lessons = load("data/lessons.json", [])
    news = load("data/news.json", {"items": []}).get("items", [])
    manifest = {}
    wanted = set()
    for item in lessons + news:
        name = f"{item['id']}-{digest(item)}.mp3"
        path = os.path.join(AUDIO_DIR, name)
        wanted.add(name)
        if not os.path.exists(path):
            print("build", name)
            tmp = tempfile.mkdtemp()
            try:
                await build(item, path, tmp)
            except Exception as e:
                print(f"  SKIP {item['id']}: {e}", file=sys.stderr)
                if os.path.exists(path):
                    os.remove(path)
                continue
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        manifest[item["id"]] = "audio/" + name
    # 刪除過期或內容已變更的舊音檔
    for f in glob.glob(os.path.join(AUDIO_DIR, "*.mp3")):
        if os.path.basename(f) not in wanted:
            os.remove(f)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=0)
    print(f"audio.json: {len(manifest)} files")


if __name__ == "__main__":
    asyncio.run(main())

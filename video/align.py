"""Measure where each line really starts and ends in the audio.

Uses ElevenLabs forced alignment (audio + transcript -> per-character times)
and rewrites the timings files that index.html / discovery.html read.

Usage (from the repo root):
  python3 video/align.py script.json
  python3 video/align.py discovery-script.json
"""
import json, re, subprocess, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from generate import api_key, HERE

def spoken(text):
    return re.sub(r"\s+", " ", re.sub(r"\[[^\]]*\]", "", text)).strip()

def align(audio, lines):
    """Return [(start, end)] per line, measured from the audio itself."""
    parts = [spoken(l["text"]) for l in lines]
    transcript = " ".join(parts)
    res = subprocess.run(
        ["curl", "-s", "-X", "POST", "https://api.elevenlabs.io/v1/forced-alignment",
         "-H", f"xi-api-key: {api_key()}", "-F", f"file=@{audio}", "-F", f"text={transcript}"],
        capture_output=True, text=True, check=True).stdout
    data = json.loads(res)
    if "characters" not in data:
        raise SystemExit(f"forced alignment failed: {res[:500]}")
    chars = data["characters"]
    if "".join(c["text"] for c in chars) != transcript:
        raise SystemExit("alignment characters do not match the transcript")
    out, pos = [], 0
    for p in parts:
        seg = [c for c in chars[pos:pos + len(p)] if c["text"].strip()]
        out.append((seg[0]["start"], seg[-1]["end"]))
        pos += len(p) + 1
    return out

def write_timings(name):
    script = json.loads((HERE / name).read_text())
    out = script.get("out", "dialogue")
    tname = "timings" if out == "dialogue" else f"{out}-timings"
    spans = align(HERE / f"{out}.mp3", script["lines"])
    timings = [{"who": l["who"], "scene": l["scene"], "text": l["text"], "start": round(a, 3), "end": round(b, 3)}
               for l, (a, b) in zip(script["lines"], spans)]
    (HERE / f"{tname}.json").write_text(json.dumps(timings, indent=2))
    (HERE / f"{tname}.js").write_text("window.TIMINGS = " + json.dumps(timings, indent=2) + ";\n")
    return timings

if __name__ == "__main__":
    for t in write_timings(sys.argv[1] if len(sys.argv) > 1 else "script.json"):
        print(f'{t["start"]:7.2f} {t["end"]:7.2f}  {t["who"]:5}  {spoken(t["text"])[:60]}')

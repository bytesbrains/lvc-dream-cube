"""Generate the Kickstarter video voiceover with ElevenLabs v3 (Text to Dialogue).

Reads ELEVENLABS_API_KEY from the repo's .env (git-ignored) and writes:
  video/dialogue.mp3   the full two-voice conversation
  video/timings.json   start/end seconds of every line
  video/timings.js     the same, loaded by index.html

Run from the repo root:
  python3 video/generate.py                            # main film (script.json)
  python3 video/generate.py discovery-script.json      # 9:16 Discovery Mode cut
Outputs are named from the script's "out" key (default "dialogue").
"""
import base64, json, os, pathlib, sys, urllib.request, urllib.error

ROOT = pathlib.Path(__file__).resolve().parent.parent
HERE = ROOT / "video"

def api_key():
    key = os.environ.get("ELEVENLABS_API_KEY")
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("ELEVENLABS_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY not found in environment or .env")
    return key

def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "script.json"
    script = json.loads((HERE / name).read_text())
    out = script.get("out", "dialogue")
    tname = "timings" if out == "dialogue" else f"{out}-timings"
    voices = script["voices"]
    body = {
        "model_id": script["model_id"],
        "inputs": [{"text": l["text"], "voice_id": voices[l["who"]]} for l in script["lines"]],
        "settings": {"stability": 0.5},
    }
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/text-to-dialogue/with-timestamps?output_format=mp3_44100_192",
        data=json.dumps(body).encode(),
        headers={"xi-api-key": api_key(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"ElevenLabs error {e.code}: {e.read().decode()[:800]}")

    (HERE / f"{out}.mp3").write_bytes(base64.b64decode(res["audio_base64"]))

    segs = res.get("voice_segments") or []
    timings = []
    for i, line in enumerate(script["lines"]):
        seg = next((s for s in segs if s.get("dialogue_input_index") == i), None)
        timings.append({
            "who": line["who"],
            "scene": line["scene"],
            "text": line["text"],
            "start": round(seg["start_time_seconds"], 3) if seg else None,
            "end": round(seg["end_time_seconds"], 3) if seg else None,
        })
    (HERE / f"{tname}.json").write_text(json.dumps(timings, indent=2))
    (HERE / f"{tname}.js").write_text("window.TIMINGS = " + json.dumps(timings, indent=2) + ";\n")
    print(f"wrote {out}.mp3 and {tname}.json ({len(segs)} segments)")

if __name__ == "__main__":
    main()

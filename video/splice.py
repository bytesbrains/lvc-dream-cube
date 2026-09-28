"""Re-voice single lines without regenerating the whole conversation.

Generates each changed line with ElevenLabs v3 (same voice), matches its
loudness to the take it replaces, and splices it into the existing audio at the
silences around the line (measured with forced alignment). Afterwards it
re-measures every line, and updates the script JSON so generate.py stays in sync.

Usage (from the repo root):
  python3 video/splice.py <script.json> <line-index> "<new text>" [<line-index> "<new text>" ...]
"""
import json, pathlib, re, subprocess, sys, tempfile, urllib.request, urllib.error
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from generate import api_key, HERE
from align import align, write_timings

def run(*a):
    return subprocess.run(a, check=True, capture_output=True, text=True)

def mean_db(path, start=None, end=None):
    args = ["ffmpeg", "-hide_banner"]
    if start is not None:
        args += ["-ss", str(start), "-to", str(end)]
    args += ["-i", str(path), "-af", "volumedetect", "-f", "null", "-"]
    out = subprocess.run(args, capture_output=True, text=True).stderr
    return float(re.search(r"mean_volume: (-?[\d.]+) dB", out).group(1))

def duration(path):
    return float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)).stdout)

def tts(text, voice, model, out):
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_192",
        data=json.dumps({"text": text, "model_id": model}).encode(),
        headers={"xi-api-key": api_key(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            out.write_bytes(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"ElevenLabs error {e.code}: {e.read().decode()[:500]}")

def main():
    name, pairs = sys.argv[1], sys.argv[2:]
    script = json.loads((HERE / name).read_text())
    out = script.get("out", "dialogue")
    audio = HERE / f"{out}.mp3"
    spans = align(audio, script["lines"])  # measured, not the API's estimates
    edits = sorted(((int(pairs[i]), pairs[i + 1]) for i in range(0, len(pairs), 2)), reverse=True)
    tmp = pathlib.Path(tempfile.mkdtemp())
    wav = tmp / "cur.wav"
    run("ffmpeg", "-y", "-i", str(audio), "-ac", "1", "-ar", "44100", str(wav))
    total = duration(wav)
    for idx, text in edits:  # last line first, so earlier spans stay valid
        line = script["lines"][idx]
        a, b = spans[idx]
        # cut in the middle of the silences around the line, and keep those gaps
        cut_a = (spans[idx - 1][1] + a) / 2 if idx > 0 else 0.0
        cut_b = (b + spans[idx + 1][0]) / 2 if idx + 1 < len(spans) else total
        lead, tail = a - cut_a, cut_b - b
        raw, new = tmp / f"raw{idx}.mp3", tmp / f"new{idx}.wav"
        tts(text, script["voices"][line["who"]], script["model_id"], raw)
        gain = mean_db(wav, a, b) - mean_db(raw)
        run("ffmpeg", "-y", "-i", str(raw), "-af",
            "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
            "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
            f"volume={gain:.2f}dB,adelay={int(lead * 1000)},apad=pad_dur={tail:.3f}",
            "-ac", "1", "-ar", "44100", str(new))
        head, rest, joined = tmp / "h.wav", tmp / "t.wav", tmp / "j.wav"
        run("ffmpeg", "-y", "-i", str(wav), "-t", f"{cut_a:.3f}", str(head))
        run("ffmpeg", "-y", "-ss", f"{cut_b:.3f}", "-i", str(wav), str(rest))
        parts = ([str(head)] if cut_a > 0 else []) + [str(new)] + ([str(rest)] if cut_b < total else [])
        args = ["ffmpeg", "-y"]
        for p_ in parts:
            args += ["-i", p_]
        args += ["-filter_complex", "".join(f"[{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1", str(joined)]
        run(*args)
        joined.replace(wav)
        line["text"] = text
        print(f"line {idx}: replaced {b - a:.2f}s of speech with {duration(new) - lead - tail:.2f}s (gain {gain:+.1f} dB)")
    run("ffmpeg", "-y", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "192k", str(audio))
    (HERE / name).write_text(json.dumps(script, indent=2, ensure_ascii=False) + "\n")
    write_timings(name)  # re-measure the finished audio so the visuals stay in sync

if __name__ == "__main__":
    main()

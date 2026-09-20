from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import re
import sys
from math import gcd
from pathlib import Path

SPEECH_NORMALIZATION_VERSION = "edgefinance-zh-natural-dialogue-v1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Render edgeFinance4Podcast dialogue with local voices.")
    parser.add_argument("--draft", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--master", required=True)
    parser.add_argument("--timings", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--host-wav", required=True)
    parser.add_argument("--cohost-wav", required=True)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    args = parser.parse_args()

    draft_path = Path(args.draft).resolve()
    config_path = Path(args.config).resolve()
    project_root = config_path.parent.parent
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    tts_root = (project_root / config["tts"]["root"]).resolve()
    vendor = tts_root / "vendor_coqui311"
    if not vendor.exists():
        raise FileNotFoundError(f"Coqui runtime not found: {vendor}")
    sys.path.insert(0, str(vendor))
    os.environ.setdefault("TTS_HOME", str(tts_root / "coqui_models"))

    import numpy as np
    import soundfile as sf
    import torch
    from scipy.signal import resample_poly

    sample_rate = int(config["tts"].get("sampleRate", 24000))
    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    master_path = Path(args.master).resolve()
    master_path.parent.mkdir(parents=True, exist_ok=True)
    timings_path = Path(args.timings).resolve()
    timings_path.parent.mkdir(parents=True, exist_ok=True)
    device = select_device(torch, args.device)
    print(f"Podcast renderer device: {device}", flush=True)

    rendered: dict[int, Path] = {}
    host_turns = [turn for turn in draft["dialogue"] if turn["speaker"] == "host"]
    cohost_turns = [turn for turn in draft["dialogue"] if turn["speaker"] == "cohost"]
    render_host_turns(host_turns, rendered, work_dir, config, device, torch, np, sf, Path(args.host_wav).resolve())
    release_gpu(torch)
    render_cohost_turns(cohost_turns, rendered, work_dir, config, device, torch, np, sf, Path(args.cohost_wav).resolve())
    release_gpu(torch)

    audio_parts: list[np.ndarray] = [make_chime(np, sample_rate, ascending=True), np.zeros(int(sample_rate * 0.32), dtype=np.float32)]
    timeline: list[dict] = []
    elapsed_samples = sum(len(part) for part in audio_parts)
    previous_speaker = None
    for turn in draft["dialogue"]:
        wav, source_rate = read_mono(sf, np, rendered[turn["turn"]])
        wav = resample(np, resample_poly, wav, source_rate, sample_rate)
        wav = clean_segment(np, wav, sample_rate)
        start_seconds = elapsed_samples / sample_rate
        audio_parts.append(wav)
        elapsed_samples += len(wav)
        timeline.append({
            "turn": turn["turn"],
            "speaker": turn["speaker"],
            "startSeconds": round(start_seconds, 3),
            "durationSeconds": round(len(wav) / sample_rate, 3),
            "chunk": rendered[turn["turn"]].name,
        })
        pause = float(config["tts"].get(
            "pauseSpeakerChangeSeconds" if previous_speaker and previous_speaker != turn["speaker"] else "pauseSameSpeakerSeconds",
            0.36,
        ))
        if turn["text"].rstrip().endswith(("?", "!")):
            pause += 0.04
        silence = np.zeros(int(sample_rate * pause), dtype=np.float32)
        audio_parts.append(silence)
        elapsed_samples += len(silence)
        previous_speaker = turn["speaker"]

    audio_parts.extend([np.zeros(int(sample_rate * 0.28), dtype=np.float32), make_chime(np, sample_rate, ascending=False)])
    combined = np.concatenate(audio_parts).astype(np.float32)
    peak = float(np.max(np.abs(combined))) if len(combined) else 0.0
    if peak > 0.97:
        combined *= 0.97 / peak
    sf.write(master_path, combined, sample_rate, subtype="PCM_16")
    metadata = {
        "schemaVersion": 1,
        "id": draft["id"],
        "sampleRate": sample_rate,
        "durationSeconds": round(len(combined) / sample_rate, 3),
        "masterPath": str(master_path),
        "turns": timeline,
        "voices": {
            "host": {"engine": config["hosts"]["host"]["engine"], "profile": "private-local-girl-voice"},
            "cohost": {"engine": config["hosts"]["cohost"]["engine"], "profile": "private-local-man-voice"},
        },
    }
    timings_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote master: {master_path}", flush=True)
    print(f"Duration: {metadata['durationSeconds']:.1f} seconds", flush=True)


def render_host_turns(turns, rendered, work_dir, config, device, torch, np, sf, speaker_path: Path) -> None:
    if not speaker_path.exists():
        raise FileNotFoundError(f"Ying voice profile not found: {speaker_path}")
    voice_digest = file_digest(speaker_path)
    missing = []
    for turn in turns:
        path = chunk_path(work_dir, turn, voice_digest)
        rendered[turn["turn"]] = path
        if not path.exists():
            missing.append((turn, path))
    if not missing:
        print("Reusing all host chunks.", flush=True)
        return

    from TTS.api import TTS

    print(f"Loading XTTS v2 Ying voice for {len(missing)} turns...", flush=True)
    model = TTS("tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=False, gpu=device == "cuda")
    model.to(device)
    for position, (turn, path) in enumerate(missing, start=1):
        print(f"Y [{position}/{len(missing)}] turn {turn['turn']}", flush=True)
        synthesize_natural_turn(model, normalize_for_speech(turn["text"]), speaker_path, path, np, sf, config["languageCode"])
    del model


def render_cohost_turns(turns, rendered, work_dir, config, device, torch, np, sf, speaker_path: Path) -> None:
    if not speaker_path.exists():
        raise FileNotFoundError(f"Bing voice profile not found: {speaker_path}")
    voice_digest = file_digest(speaker_path)
    missing = []
    for turn in turns:
        path = chunk_path(work_dir, turn, voice_digest)
        rendered[turn["turn"]] = path
        if not path.exists():
            missing.append((turn, path))
    if not missing:
        print("Reusing all co-host chunks.", flush=True)
        return

    from TTS.api import TTS

    print(f"Loading XTTS v2 Bing voice for {len(missing)} turns...", flush=True)
    model = TTS("tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=False, gpu=device == "cuda")
    model.to(device)
    for position, (turn, path) in enumerate(missing, start=1):
        print(f"B [{position}/{len(missing)}] turn {turn['turn']}", flush=True)
        synthesize_natural_turn(model, normalize_for_speech(turn["text"]), speaker_path, path, np, sf, config["languageCode"])
    del model


def synthesize_natural_turn(model, text: str, speaker_path: Path, output_path: Path, np, sf, language_code: str) -> None:
    chunks = split_speech_chunks(text)
    sample_rate = int(model.synthesizer.output_sample_rate)
    pieces = []
    for index, chunk in enumerate(chunks):
        audio = np.asarray(model.tts(
            text=chunk,
            speaker_wav=str(speaker_path),
            language=language_code,
            split_sentences=False,
        ), dtype=np.float32)
        audible = np.flatnonzero(np.abs(audio) > 0.004)
        if len(audible):
            leading_pad = int(sample_rate * 0.02)
            trailing_pad = int(sample_rate * 0.03)
            audio = audio[max(0, int(audible[0]) - leading_pad):min(len(audio), int(audible[-1]) + trailing_pad + 1)]
        pieces.append(audio)
        if index < len(chunks) - 1:
            pieces.append(np.zeros(int(sample_rate * 0.055), dtype=np.float32))
    combined = np.concatenate(pieces).astype(np.float32) if pieces else np.zeros(1, dtype=np.float32)
    sf.write(output_path, combined, sample_rate, subtype="PCM_16")


def split_speech_chunks(text: str, character_limit: int = 75) -> list[str]:
    sentences = re.split(r"(?<=[。！？.!?])\s*", text.strip())
    chunks: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= character_limit:
            chunks.append(sentence)
            continue
        clauses = re.split(r"(?<=[，,；;])\s*", sentence)
        current = ""
        for clause in clauses:
            candidate = f"{current} {clause}".strip()
            if current and len(candidate) > character_limit:
                chunks.extend(split_by_words(current, character_limit))
                current = clause
            else:
                current = candidate
        if current:
            chunks.extend(split_by_words(current, character_limit))
    return chunks


def split_by_words(text: str, character_limit: int) -> list[str]:
    if len(text) <= character_limit:
        return [text]
    if " " not in text:
        return [text[index:index + character_limit] for index in range(0, len(text), character_limit)]
    chunks: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > character_limit:
            chunks.append(current.rstrip(","))
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def normalize_for_speech(text: str) -> str:
    text = re.sub(r"\bedgeFinance4Podcast\b", "Edge Finance for Podcast", text, flags=re.IGNORECASE)
    replacements = {
        "AI": "A I",
        "GPU": "G P U",
        "CPU": "C P U",
        "ETF": "E T F",
        "SEC": "S E C",
        "EPO": "E P O",
        "USPTO": "U S P T O",
        "TIPO": "T I P O",
        "GDP": "G D P",
        "PMI": "P M I",
        "CPI": "C P I",
        "PCE": "P C E",
        "Bitcoin": "比特幣",
    }
    for source, target in replacements.items():
        text = re.sub(rf"\b{re.escape(source)}\b", target, text)
    text = re.sub(r"(?<=\d)\s*[–-]\s*(?=\d)", "到", text)
    text = re.sub(r"(?<=\d)\s*/\s*(?=\d)", "比", text)
    text = text.replace("±", "正負").replace("−", "負").replace("%", "百分之")
    text = text.replace("—", "，").replace("–", "，").replace("…", "，")
    text = text.replace(";", "。 ").replace(":", "，").replace("&", "和")
    text = re.sub(r"[\(\)\[\]{}]", ", ", text)
    text = re.sub(r"[\"“”‘’]", "", text)
    text = re.sub(r"\s*/\s*", "或", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r",\s*,+", ", ", text)
    text = re.sub(r"\s+([,.?!])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip(" ,")


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def chunk_path(work_dir: Path, turn: dict, voice_digest: str) -> Path:
    payload = f"{SPEECH_NORMALIZATION_VERSION}\0{voice_digest}\0{turn['text']}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:12]
    return work_dir / f"turn_{turn['turn']:03d}_{turn['speaker']}_{digest}.wav"


def read_mono(sf, np, path: Path):
    wav, sample_rate = sf.read(path, always_2d=True)
    return wav.mean(axis=1).astype(np.float32), int(sample_rate)


def resample(np, resample_poly, wav, source_rate: int, target_rate: int):
    if source_rate == target_rate:
        return wav
    divisor = gcd(source_rate, target_rate)
    return resample_poly(wav, target_rate // divisor, source_rate // divisor).astype(np.float32)


def clean_segment(np, wav, sample_rate: int):
    if not len(wav):
        return wav
    audible = np.flatnonzero(np.abs(wav) > 0.006)
    if len(audible):
        leading_pad = int(sample_rate * 0.035)
        trailing_pad = int(sample_rate * 0.055)
        start = max(0, int(audible[0]) - leading_pad)
        end = min(len(wav), int(audible[-1]) + trailing_pad + 1)
        wav = wav[start:end]
    wav = shorten_internal_silences(np, wav, sample_rate)
    wav = wav - float(np.mean(wav))
    active = np.abs(wav) > 0.012
    rms = float(np.sqrt(np.mean(np.square(wav[active])))) if np.any(active) else float(np.sqrt(np.mean(np.square(wav))))
    target_rms = 10 ** (-19.0 / 20.0)
    if rms > 0:
        wav = wav * min(3.0, target_rms / rms)
    peak = float(np.max(np.abs(wav)))
    if peak > 0.92:
        wav *= 0.92 / peak
    fade = min(int(sample_rate * 0.025), len(wav) // 2)
    if fade:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        wav[:fade] *= ramp
        wav[-fade:] *= ramp[::-1]
    return wav.astype(np.float32)


def shorten_internal_silences(np, wav, sample_rate: int):
    frame_samples = max(1, int(sample_rate * 0.01))
    frame_count = len(wav) // frame_samples
    if frame_count < 3:
        return wav
    framed = wav[:frame_count * frame_samples].reshape(frame_count, frame_samples)
    frame_rms = np.sqrt(np.mean(np.square(framed), axis=1))
    silent = frame_rms < 0.007
    minimum_frames = max(1, int(0.45 / 0.01))
    replacement_samples = int(sample_rate * 0.18)
    long_runs = []
    run_start = None
    for index, is_silent in enumerate(silent):
        if is_silent and run_start is None:
            run_start = index
        if (not is_silent or index == len(silent) - 1) and run_start is not None:
            run_end = index if not is_silent else index + 1
            if run_end - run_start >= minimum_frames and run_start > 0 and run_end < len(silent):
                long_runs.append((run_start * frame_samples, run_end * frame_samples))
            run_start = None
    if not long_runs:
        return wav
    parts = []
    cursor = 0
    for start, end in long_runs:
        parts.append(wav[cursor:start])
        parts.append(np.zeros(replacement_samples, dtype=np.float32))
        cursor = end
    parts.append(wav[cursor:])
    return np.concatenate(parts).astype(np.float32)


def make_chime(np, sample_rate: int, ascending: bool):
    duration = 1.25
    samples = int(sample_rate * duration)
    time = np.arange(samples, dtype=np.float32) / sample_rate
    frequencies = (523.25, 659.25, 783.99) if ascending else (783.99, 659.25, 523.25)
    signal = np.zeros(samples, dtype=np.float32)
    for index, frequency in enumerate(frequencies):
        start = int(index * sample_rate * 0.18)
        local = time[: samples - start]
        envelope = np.exp(-3.1 * local)
        signal[start:] += np.sin(2 * np.pi * frequency * local) * envelope * 0.055
    fade = min(int(sample_rate * 0.04), samples // 2)
    signal[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
    signal[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    return signal


def select_device(torch, requested: str) -> str:
    if requested == "cpu":
        return "cpu"
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable.")
    return "cuda" if requested == "cuda" or torch.cuda.is_available() else "cpu"


def release_gpu(torch) -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()

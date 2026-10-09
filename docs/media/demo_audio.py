#!/usr/bin/env python3
"""An original, deterministic instrumental bed for the demo film.

Only NumPy and the standard library are used: no samples, soundfonts or network.
Writes 48 kHz stereo 16-bit PCM. The arrangement follows the film's chapters:
a pad alone for the hook, a plucked arpeggio from the second chapter, a soft
beat from the third, and the beat drops away for the ending.

    python docs/media/demo_audio.py --output score.wav --duration 50
"""

from __future__ import annotations

import argparse
import math
import wave
from pathlib import Path

import numpy as np

RATE = 48_000
BPM = 100
BEAT = 60 / BPM
BAR = BEAT * 4
# Dmaj7 · Bm7 · Gmaj7 · Asus2 as MIDI notes, one chord per bar.
CHORDS = ((62, 66, 69, 73), (59, 62, 66, 69), (55, 59, 62, 66), (57, 59, 64, 69))
PLUCK_IN, BEAT_IN, BEAT_OUT = 6.0, 14.0, 46.0


def hz(note):
    return 440 * 2 ** ((note - 69) / 12)


def envelope(n, attack, release, hold=0.0):
    t = np.arange(n) / RATE
    a = np.clip(t / attack, 0, 1) if attack else np.ones(n)
    total = n / RATE
    r = np.clip((total - t) / release, 0, 1) if release else np.ones(n)
    return a * r * (1 if hold == 0 else np.exp(-np.clip(t - hold, 0, None) * 3))


def soft(signal):
    """A gentle lowpass: a short moving average, applied twice."""
    kernel = np.ones(24) / 24
    for _ in range(2):
        signal = np.convolve(signal, kernel, mode="same")
    return signal


def pad(duration):
    """Each bar's chord fades in over the previous one, slightly detuned left and right."""
    n = int(duration * RATE)
    left, right = np.zeros(n), np.zeros(n)
    bars = math.ceil(duration / BAR)
    for bar in range(bars):
        chord = CHORDS[bar % len(CHORDS)]
        start = int(bar * BAR * RATE)
        length = min(n - start, int((BAR + 1.2) * RATE))
        if length <= 0:
            break
        t = np.arange(length) / RATE
        env = envelope(length, 0.9, 1.1)
        for i, note in enumerate(chord):
            f = hz(note - 12 if i == 0 else note)
            for channel, detune in ((left, 0.998), (right, 1.002)):
                w = f * detune
                tone = np.sin(2 * np.pi * w * t) + 0.35 * np.sin(2 * np.pi * 2 * w * t + 0.3)
                tone += 0.12 * np.sin(2 * np.pi * 3 * w * t)
                channel[start : start + length] += tone * env * 0.11
    return soft(left), soft(right)


def pluck_note(f, length):
    t = np.arange(length) / RATE
    # A triangle wave that darkens as it decays, like a muted string.
    tri = 2 * np.abs(2 * ((t * f) % 1) - 1) - 1
    bright = np.exp(-t * 9)
    tone = tri * bright + np.sin(2 * np.pi * f * t) * (1 - bright) * 0.8
    return tone * np.exp(-t * 4.2) * np.clip(t / 0.004, 0, 1)


def pluck(duration):
    n = int(duration * RATE)
    left, right = np.zeros(n), np.zeros(n)
    step = BEAT / 2
    pattern = (0, 2, 1, 3, 2, 0, 3, 1)
    k = 0
    time = PLUCK_IN
    while time < min(duration, BEAT_OUT + BAR):
        bar = int(time // BAR)
        chord = CHORDS[bar % len(CHORDS)]
        index = pattern[k % len(pattern)]
        note = chord[index] + (12 if index >= 2 else 0)
        length = int(0.6 * RATE)
        start = int(time * RATE)
        length = min(length, n - start)
        if length <= 0:
            break
        tone = pluck_note(hz(note), length) * 0.16
        pan = 0.35 + 0.3 * (index / 3)
        left[start : start + length] += tone * (1 - pan)
        right[start : start + length] += tone * pan
        k += 1
        time += step
    return left, right


def kick(length):
    t = np.arange(length) / RATE
    sweep = 44 + 90 * np.exp(-t * 22)
    phase = 2 * np.pi * np.cumsum(sweep) / RATE
    return np.sin(phase) * np.exp(-t * 9) * 0.55


def hat(length, seed):
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(length)
    noise -= np.convolve(noise, np.ones(6) / 6, mode="same")  # keep only the highs
    t = np.arange(length) / RATE
    return noise * np.exp(-t * 70) * 0.05


def drums(duration):
    n = int(duration * RATE)
    out = np.zeros(n)
    beat = 0
    time = BEAT_IN
    while time < min(duration, BEAT_OUT):
        start = int(time * RATE)
        if beat % 4 in (0, 2):
            length = min(int(0.35 * RATE), n - start)
            out[start : start + length] += kick(length)
        for half in (0.5,):
            s = int((time + half * BEAT) * RATE)
            length = min(int(0.08 * RATE), n - s)
            if length > 0:
                out[s : s + length] += hat(length, beat)
        beat += 1
        time += BEAT
    return out


def master(left, right, duration):
    n = int(duration * RATE)
    t = np.arange(n) / RATE
    fade = np.clip(t / 1.2, 0, 1) * np.clip((duration - t) / 2.5, 0, 1)
    stereo = np.stack((left[:n] * fade, right[:n] * fade))
    stereo = np.tanh(stereo * 1.4) / 1.4
    rms = math.sqrt(float(np.mean(stereo**2)))
    stereo *= 10 ** (-20 / 20) / max(rms, 1e-9)
    peak = float(np.max(np.abs(stereo)))
    if peak > 10 ** (-1 / 20):
        stereo *= 10 ** (-1 / 20) / peak
    return stereo


def write(destination, stereo):
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = (np.clip(stereo.T, -1, 1) * 32767).astype("<i2")
    with wave.open(str(destination), "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(data.tobytes())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--duration", type=float, default=50)
    args = p.parse_args()
    pl, pr = pad(args.duration)
    al, ar = pluck(args.duration)
    d = drums(args.duration)
    stereo = master(pl + al + d, pr + ar + d, args.duration)
    write(args.output, stereo)
    print(f"Wrote {args.output}", flush=True)


if __name__ == "__main__":
    main()

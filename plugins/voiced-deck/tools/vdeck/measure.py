"""Prosody of a take or a show: F0 (YIN, numpy only), pauses and phrase-final pitch drop.

A pause is a silence of at least PAUSE_MIN_S with speech on both sides. F0 range is p5..p95 of
voiced frames in semitones. final_drop_st is the mean drop from the first 60% to the last 20%
of each phrase. These are this tool's definitions; compare numbers only against this tool.
"""
import subprocess

import numpy as np

SR = 16000
F0_MIN, F0_MAX = 55.0, 400.0
WIN = 400
MAXLAG = int(SR / F0_MIN)
HOP = 160
YIN_TH = 0.15
VOICED_MAX_CMND = 0.30
PAUSE_MIN_S = 0.20
SPEECH_REL_DB = 35.0


def to16k(x, sr):
    if sr == SR:
        return x
    n = np.arange(-63, 64)
    fc = 7000.0 / sr
    h = np.sinc(2 * fc * n) * np.hamming(len(n))
    h /= h.sum()
    y = np.convolve(x, h, mode="same")
    t = np.arange(0, len(y) * SR / sr) * sr / SR
    return np.interp(t, np.arange(len(y)), y)


def frame_db(x, win=320, hop=HOP):
    if len(x) < win:
        return np.array([-120.0])
    idx = np.arange(0, len(x) - win + 1, hop)
    fr = np.stack([x[i:i + win] for i in idx])
    return 10 * np.log10(np.mean(fr ** 2, axis=1) + 1e-12)


def yin(x):
    L = WIN + MAXLAG
    if len(x) < L:
        return np.array([]), np.array([])
    starts = np.arange(0, len(x) - L + 1, HOP)
    fr = np.stack([x[s:s + L] for s in starts])
    nfft = 1 << int(np.ceil(np.log2(L + WIN)))
    a = np.fft.rfft(fr[:, :WIN], nfft)
    b = np.fft.rfft(fr, nfft)
    r = np.fft.irfft(np.conj(a) * b, nfft)[:, :MAXLAG + 1]
    sq = np.cumsum(np.concatenate([np.zeros((len(fr), 1)), fr ** 2], axis=1), axis=1)
    e0 = sq[:, WIN][:, None]
    taus = np.arange(MAXLAG + 1)
    etau = sq[:, taus + WIN] - sq[:, taus]
    d = np.maximum(e0 + etau - 2 * r, 0)
    cs = np.cumsum(d[:, 1:], axis=1)
    cm = np.ones_like(d)
    cm[:, 1:] = d[:, 1:] * taus[1:] / np.maximum(cs, 1e-12)
    tmin = int(SR / F0_MAX)
    f0 = np.zeros(len(fr))
    q = np.ones(len(fr))
    for i in range(len(fr)):
        c = cm[i]
        below = np.nonzero(c[tmin:] < YIN_TH)[0]
        if below.size:
            t = tmin + below[0]
            while t + 1 <= MAXLAG and c[t + 1] < c[t]:
                t += 1
        else:
            t = tmin + int(np.argmin(c[tmin:]))
        if 1 <= t < MAXLAG:
            y0, y1, y2 = c[t - 1], c[t], c[t + 1]
            den = y0 - 2 * y1 + y2
            tt = t + (0.5 * (y0 - y2) / den if den > 1e-9 else 0.0)
        else:
            tt = float(t)
        f0[i] = SR / tt
        q[i] = c[t]
    rms = 10 * np.log10(np.mean(fr[:, :WIN] ** 2, axis=1) + 1e-12)
    return f0, (q < VOICED_MAX_CMND) & (rms > np.percentile(rms, 95) - 30)


def runs(mask):
    out, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        if not m and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(mask)))
    return out


def prosody(raw, sr):
    """Prosody of mono float samples: F0 median and range, pauses, mean phrase-final drop."""
    raw = np.asarray(raw, dtype=np.float64)
    x = to16k(raw, sr)
    dur = len(raw) / sr
    f0, voiced = yin(x)
    fv = f0[voiced]
    out = {"duration_s": round(dur, 3), "voiced_frames": int(voiced.sum())}
    if fv.size >= 10:
        med = np.median(fv)
        keep = np.abs(12 * np.log2(fv / med)) <= 12
        fv = fv[keep]
        med = float(np.median(fv))
        p5, p95 = np.percentile(fv, [5, 95])
        out.update(f0_median_hz=round(med, 1), f0_p5_hz=round(float(p5), 1), f0_p95_hz=round(float(p95), 1),
                   f0_range_st=round(float(12 * np.log2(p95 / p5)), 2))
    else:
        out.update(f0_median_hz=None, f0_p5_hz=None, f0_p95_hz=None, f0_range_st=None)

    db = frame_db(x)
    speech = db > max(np.percentile(db, 95) - SPEECH_REL_DB, -60)
    silences = [(s, e) for s, e in runs(~speech) if s > 0 and e < len(speech) and (e - s) * HOP / SR >= PAUSE_MIN_S]
    out["pauses"] = len(silences)
    out["pause_s"] = round(sum(e - s for s, e in silences) * HOP / SR, 3)
    out["pauses_per_min"] = round(len(silences) / (dur / 60), 2) if dur > 0 else 0.0

    drops = []
    bounds = [0] + [e for _, e in silences] + [len(speech)]
    cuts = [s for s, _ in silences] + [len(speech)]
    for a, b in zip(bounds[:-1], cuts):
        seg = [(i, f0[i]) for i in range(len(f0)) if voiced[i] and a <= i < b]
        if len(seg) < 30:
            continue
        vals = np.array([v for _, v in seg])
        n = len(vals)
        drops.append(12 * np.log2(np.median(vals[: int(n * 0.6)]) / np.median(vals[int(n * 0.8):])))
    out["final_drop_st"] = round(float(np.mean(drops)), 2) if drops else None
    return out


def decode(path, start=None, end=None, sr=24000):
    """Decode any audio file to mono float32 at sr with ffmpeg."""
    cmd = ["ffmpeg", "-v", "error", "-nostdin"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    if end is not None:
        cmd += ["-to", f"{end:.3f}"]
    cmd += ["-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype="<f4")

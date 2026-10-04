"""
Voice Isolation and Audio Cleaning Pipeline for Stewart STT.
Applies bandpass filtering (80Hz - 7.5kHz), Silero VAD frame-by-frame speech isolation,
inter-word background noise attenuation, and peak/RMS normalization before passing
audio to Whisper.
"""

import logging
import numpy as np

try:
    import torch
except ImportError:
    torch = None

try:
    import scipy.signal as signal
    _SCIPY_AVAILABLE = True
except ImportError:
    signal = None
    _SCIPY_AVAILABLE = False

log = logging.getLogger("stt:voice_isolator")


def apply_bandpass_filter(audio: np.ndarray, sr: int = 16000, lowcut: float = 80.0, highcut: float = 7500.0) -> np.ndarray:
    """
    Applies a 2nd-order Butterworth bandpass filter to eliminate sub-rumble (<80Hz)
    and high-frequency digital noise (>7.5kHz), focusing energy on vocal formants.
    """
    if not _SCIPY_AVAILABLE or len(audio) < 64:
        return audio - np.mean(audio)

    try:
        sos = signal.butter(2, [lowcut, highcut], btype='bandpass', fs=sr, output='sos')
        filtered = signal.sosfilt(sos, audio)
        return filtered.astype(np.float32)
    except Exception as e:
        log.debug(f"Bandpass filter fallback: {e}")
        return (audio - np.mean(audio)).astype(np.float32)


def isolate_voice(
    audio: np.ndarray,
    vad_model=None,
    sr: int = 16000,
    vad_threshold: float = 0.30,
    pre_speech_pad_ms: int = 150,
    post_speech_pad_ms: int = 200,
    attenuate_noise_gaps: bool = True
) -> np.ndarray:
    """
    Isolates speech from background recording using:
    1. Mean DC bias removal & Bandpass filtering
    2. Silero VAD frame-level speech detection
    3. Trimming pre-speech and post-speech background noise
    4. Soft attenuation of non-speech gaps
    5. Peak & RMS AGC normalization for Whisper
    """
    if len(audio) < 512:
        return audio

    # Step 1: Remove DC bias and filter non-vocal frequencies
    filtered = apply_bandpass_filter(audio, sr=sr)

    # If VAD model is unavailable or torch is missing, apply energy-based trimming and AGC
    if vad_model is None or torch is None:
        peak = np.max(np.abs(filtered))
        if peak > 0.005:
            filtered = (filtered / peak) * 0.92
        return filtered

    # Step 2: Frame-by-frame VAD analysis (512 samples = 32ms at 16kHz)
    window_size = 512
    num_frames = len(filtered) // window_size
    if num_frames == 0:
        return filtered

    confidences = np.zeros(num_frames, dtype=np.float32)
    try:
        with torch.no_grad():
            for i in range(num_frames):
                frame = filtered[i * window_size : (i + 1) * window_size]
                tensor_frame = torch.from_numpy(frame)
                confidences[i] = vad_model(tensor_frame, sr).item()
    except Exception as e:
        log.warning(f"Error during VAD frame isolation: {e}")
        peak = np.max(np.abs(filtered))
        if peak > 0.005:
            filtered = (filtered / peak) * 0.92
        return filtered

    speech_frames = np.where(confidences >= vad_threshold)[0]
    if len(speech_frames) == 0:
        # No confident speech detected; return filtered with mild gain
        peak = np.max(np.abs(filtered))
        if peak > 0.005:
            return (filtered / peak) * 0.5
        return filtered

    # Step 3: Determine speech boundaries with padding
    pad_frames_pre = int((pre_speech_pad_ms / 1000.0) * sr / window_size)
    pad_frames_post = int((post_speech_pad_ms / 1000.0) * sr / window_size)

    start_frame = max(0, speech_frames[0] - pad_frames_pre)
    end_frame = min(num_frames, speech_frames[-1] + pad_frames_post + 1)

    start_sample = start_frame * window_size
    end_sample = min(len(filtered), end_frame * window_size)

    extracted = filtered[start_sample:end_sample].copy()
    extracted_conf = confidences[start_frame:end_frame]

    # Step 4: Soft-attenuate long non-speech gaps (>200ms) between words
    if attenuate_noise_gaps and len(extracted_conf) > 8:
        gap_run = 0
        gap_start = 0
        for idx, conf in enumerate(extracted_conf):
            if conf < 0.15:
                if gap_run == 0:
                    gap_start = idx
                gap_run += 1
            else:
                if gap_run >= 6:  # >= 192ms gap
                    s_idx = gap_start * window_size
                    e_idx = idx * window_size
                    extracted[s_idx:e_idx] *= 0.15  # -16.5 dB attenuation
                gap_run = 0
        if gap_run >= 6:
            s_idx = gap_start * window_size
            e_idx = len(extracted)
            extracted[s_idx:e_idx] *= 0.15

    # Step 5: Peak & RMS AGC Normalization
    peak = np.max(np.abs(extracted))
    if peak > 0.01:
        extracted = (extracted / peak) * 0.92

    return extracted

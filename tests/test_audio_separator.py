"""
tests/test_audio_separator.py — Kiểm thử tự động tính năng Tách Lời & Tách Nhạc AI (Demucs v4)
"""

import os
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.audio_separator import (
    check_demucs_installed,
    get_optimal_device,
    separate_audio_stems,
)


def test_demucs_installed_and_device():
    """Kiểm tra thư viện Demucs & Torch đã sẵn sàng và thiết bị tính toán tối ưu."""
    ok, msg = check_demucs_installed()
    assert ok is True, f"Demucs phải được cài đặt thành công: {msg}"
    device = get_optimal_device()
    assert device in ("mps", "cuda", "cpu"), f"Device không hợp lệ: {device}"


def test_audio_separation_both_stems():
    """Kiểm tra bóc tách cả 2 luồng: Giọng hát (Vocal) và Nhạc nền (Beat Karaoke)."""
    sample_rate = 44100
    # 2 giây âm thanh mẫu stereo
    t = np.linspace(0, 2, sample_rate * 2, False)
    tone_left = np.sin(2 * np.pi * 440 * t) * 0.4
    tone_right = np.sin(2 * np.pi * 880 * t) * 0.4
    audio_data = np.vstack((tone_left, tone_right)).T
    audio_int16 = (audio_data * 32767).astype(np.int16)

    with tempfile.TemporaryDirectory() as td:
        src_wav = os.path.join(td, "test_song.wav")
        with wave.open(src_wav, "w") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_int16.tobytes())

        out_dir = os.path.join(td, "out")
        res = separate_audio_stems(
            input_path=src_wav,
            output_dir=out_dir,
            mode="both",
            audio_format="mp3",
            bitrate="320k",
        )

        assert "vocals" in res, "Kết quả phải chứa file vocals"
        assert "instrumental" in res, "Kết quả phải chứa file instrumental"
        assert os.path.exists(res["vocals"]), "File vocals phải tồn tại trên đĩa"
        assert os.path.exists(res["instrumental"]), "File instrumental phải tồn tại trên đĩa"
        assert res["vocals"].endswith(".mp3"), "File vocals phải có đuôi .mp3"
        assert res["instrumental"].endswith(".mp3"), "File instrumental phải có đuôi .mp3"
        assert "[Vocal_Loi]" in res["vocals"], "Tên file vocal phải chứa tag [Vocal_Loi]"
        assert "[Beat_Karaoke]" in res["instrumental"], "Tên file instrumental phải chứa tag [Beat_Karaoke]"

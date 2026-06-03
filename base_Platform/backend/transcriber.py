from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torchaudio.compliance.kaldi as kaldi
import wenet


class Transcriber:
    def __init__(self, model_dir: Path, device: str = "cpu") -> None:
        self.model_dir = Path(model_dir).resolve()
        self.device = str(device).split("#", 1)[0].strip() or "cpu"
        self._model = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        if not self.model_dir.exists():
            raise FileNotFoundError(f"Model dir not found: {self.model_dir}")
        device_str = str(self.device).split("#", 1)[0].strip() or "cpu"
        self.device = device_str
        try:
            self._model = wenet.load_model(str(self.model_dir), device=self.device)
        except Exception as exc:
            if self.device and self.device.lower().startswith("cuda"):
                self.device = "cpu"
                self._model = wenet.load_model(str(self.model_dir), device=self.device)
            else:
                raise
        self._model.eval()
        return self._model

    def transcribe_bytes(self, data: bytes, suffix: str = ".wav") -> str:
        model = self._ensure_model()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            try:
                result = model.transcribe(tmp_path)
                return getattr(result, "text", "")
            except ImportError as exc:
                if "torchcodec" not in str(exc).lower():
                    raise
                audio, sample_rate = sf.read(tmp_path, dtype="float32", always_2d=False)
                if isinstance(audio, np.ndarray) and audio.ndim > 1:
                    audio = np.mean(audio, axis=1)
                return self._transcribe_array_fallback(np.asarray(audio, dtype=np.float32), int(sample_rate))
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def transcribe_file(self, file_path: str) -> str:
        model = self._ensure_model()
        result = model.transcribe(file_path)
        return getattr(result, "text", "")

    def transcribe_array(self, audio: np.ndarray, sample_rate: int) -> str:
        if audio.ndim != 1:
            raise ValueError("audio must be 1D mono array")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            sf.write(tmp_path, audio, sample_rate)
            try:
                return self.transcribe_file(tmp_path)
            except ImportError as exc:
                # torchaudio in some environments requires optional torchcodec.
                if "torchcodec" not in str(exc).lower():
                    raise
                return self._transcribe_array_fallback(audio, sample_rate)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def _transcribe_array_fallback(self, audio: np.ndarray, sample_rate: int) -> str:
        model = self._ensure_model()
        waveform = torch.from_numpy(audio.astype(np.float32))
        if waveform.ndim != 1:
            waveform = waveform.reshape(-1)
        if waveform.numel() == 0:
            return ""
        waveform = waveform.unsqueeze(0)
        feats = kaldi.fbank(
            waveform,
            num_mel_bins=80,
            frame_length=25,
            frame_shift=10,
            dither=0.0,
            sample_frequency=float(sample_rate),
        )
        if feats.numel() == 0:
            return ""
        device = next(model.parameters()).device
        speech = feats.to(device).unsqueeze(0)
        speech_lengths = torch.tensor([feats.size(0)], device=device)
        results = model.decode([model.default_decode_method], speech, speech_lengths)
        result = results[model.default_decode_method][0]
        text = model.tokenizer.detokenize(result.tokens)[0]
        return str(text)

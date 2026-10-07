import os
import asyncio
import logging
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger("telegram_transcriber")


class VoiceTranscriber:
    """Local voice transcription using faster-whisper."""
    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or os.getenv("WHISPER_MODEL", "base")
        self._model = None

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            device = os.getenv("WHISPER_DEVICE", "cpu")
            compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
            logger.info(f"Loading faster-whisper model '{self.model_name}' on {device} ({compute_type})...")
            self._model = WhisperModel(self.model_name, device=device, compute_type=compute_type)
            logger.info("faster-whisper model loaded successfully.")
        return self._model

    def _sync_transcribe(self, audio_path: str) -> str:
        model = self._get_model()
        segments, info = model.transcribe(
            audio_path,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        text_parts = [seg.text.strip() for seg in segments if seg.text.strip()]
        result = " ".join(text_parts).strip()
        logger.info(f"Transcribed audio ({info.language}, prob={info.language_probability:.2f}): '{result}'")
        return result

    async def transcribe(self, audio_path: Union[str, Path]) -> str:
        """Asynchronously transcribe audio file in an executor thread without blocking asyncio loop."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_transcribe, str(audio_path))

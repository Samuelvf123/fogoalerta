"""Transcrição de áudio (mensagem de voz) — OPCIONAL.

Usa a biblioteca faster-whisper, que roda no próprio computador (sem custo de API).
Instale com:  pip install faster-whisper
Na primeira vez, ela baixa o modelo (~500 MB para "small"). Sem a biblioteca,
o bot pede para a pessoa escrever.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)
_modelo = None


def disponivel() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def transcrever(caminho: str) -> str | None:
    global _modelo
    if not disponivel():
        return None
    from faster_whisper import WhisperModel

    if _modelo is None:
        tamanho = os.getenv("WHISPER_MODELO", "small")
        log.info("Carregando modelo Whisper '%s' (primeira vez demora)...", tamanho)
        _modelo = WhisperModel(tamanho, device="cpu", compute_type="int8")
    segmentos, _ = _modelo.transcribe(caminho, language="pt", vad_filter=True)
    texto = " ".join(s.text.strip() for s in segmentos).strip()
    return texto or None

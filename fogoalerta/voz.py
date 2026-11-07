"""Resposta em áudio (texto -> voz) para quem prefere ouvir.

Usa a biblioteca edge-tts (vozes neurais em português do Brasil, gratuita, precisa de internet;
o texto é enviado ao serviço de voz da Microsoft). Se a biblioteca não estiver instalada ou o
serviço falhar, o bot continua respondendo só por texto.
"""
from __future__ import annotations

import logging
import os
import re

log = logging.getLogger(__name__)
VOZ = os.getenv("VOZ_TTS", "pt-BR-FranciscaNeural")
LIMITE = 900  # caracteres: áudio curto, de no máximo ~1 minuto

_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍←-⇿⬀-⯿]")
_TROCAS = [
    (re.compile(r"```.*?```", re.S), " O texto completo está na mensagem escrita. "),
    (re.compile(r"https?://\S+"), ""),
    (re.compile(r"\b193\b"), "um nove três"),
    (re.compile(r"\b192\b"), "um nove dois"),
    (re.compile(r"\b199\b"), "um nove nove"),
    (re.compile(r"\bkm/h\b"), "quilômetros por hora"),
    (re.compile(r"(\d)\s*km\b"), r"\1 quilômetros"),
    (re.compile(r"(\d)\s*mm\b"), r"\1 milímetros"),
    (re.compile(r"µg/m³"), "microgramas por metro cúbico"),
    (re.compile(r"\bPM2,5\b|\bPM2\.5\b|\bpm2_5\b", re.I), "PM dois vírgula cinco"),
    (re.compile(r"°C"), " graus"),
    (re.compile(r"[*`#_]"), ""),
    (re.compile(r"^\s*[•\-]\s*", re.M), ""),
]


def disponivel() -> bool:
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        return False


def preparar_texto(texto: str) -> str:
    """Deixa o texto bom para ser falado: sem emojis, links, símbolos e números de telefone em bloco."""
    t = texto
    for padrao, troca in _TROCAS:
        t = padrao.sub(troca, t)
    t = _EMOJI.sub("", t)
    t = re.sub(r"\s*\n\s*", ". ", t)            # quebras de linha viram pausas
    t = re.sub(r"\.\s*\.", ".", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" .") + "."
    if len(t) > LIMITE:
        corte = t[:LIMITE].rfind(". ")
        t = t[: corte + 1 if corte > 200 else LIMITE] + " Os detalhes estão na mensagem escrita."
    return t


async def sintetizar(texto: str, caminho: str) -> bool:
    """Gera um MP3 em `caminho`. Devolve False (sem erro) se não for possível."""
    if not disponivel():
        return False
    import edge_tts

    falado = preparar_texto(texto)
    if len(falado) < 3:
        return False
    try:
        await edge_tts.Communicate(falado, VOZ).save(caminho)
        return os.path.getsize(caminho) > 0
    except Exception as e:  # noqa: BLE001 - sem áudio, a resposta em texto já foi enviada
        log.warning("Falha ao gerar áudio: %s", e)
        return False

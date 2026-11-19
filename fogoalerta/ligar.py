"""Botão "Ligar" nas mensagens fixas de emergência.

O Telegram não aceita link tel: em botão de bot (só http/https e tg://). Por isso o botão
abre uma página mínima do projeto (docs/ligar, publicada no GitHub Pages) em que um toque
abre o discador do celular já com o número digitado. A pessoa só aperta "ligar".
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .config import CONFIG

QUEM = {"193": "Bombeiros", "192": "SAMU", "181": "Disque-Denúncia"}


def url_ligar(numero: str, base: str | None = None) -> str:
    base = CONFIG.url_ligar if base is None else base
    return f"{base.rstrip('/')}/?n={numero}"


def teclado(numero: str, base: str | None = None) -> InlineKeyboardMarkup | None:
    """Botão "📞 Ligar 193 (Bombeiros)". Sem URL_LIGAR configurada, não põe botão."""
    base = CONFIG.url_ligar if base is None else base
    if not base or numero not in QUEM:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"📞 Ligar {numero} ({QUEM[numero]})",
                                                       url=url_ligar(numero, base))]])

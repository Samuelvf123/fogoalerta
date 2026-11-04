"""Converte o markdown simples que a IA usa (**negrito**, ```bloco```, `código`, listas com *)
para o HTML que o Telegram entende. Sem isso, os asteriscos aparecem na tela."""
from __future__ import annotations

import html
import re

_BLOCO = re.compile(r"```[a-zA-Z]*\n?(.*?)```", re.S)


def _trecho(texto: str) -> str:
    t = html.escape(texto, quote=False)
    t = re.sub(r"^(\s*)[*\-] ", r"\1• ", t, flags=re.M)          # listas
    t = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", t, flags=re.M)  # títulos viram negrito
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t, flags=re.S)    # **negrito**
    t = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", t)            # `código`
    return t


def para_html(texto: str) -> str:
    partes = _BLOCO.split(texto)
    # índices ímpares são o conteúdo de blocos ``` ```
    return "".join(
        f"<pre>{html.escape(p.strip(), quote=False)}</pre>" if i % 2 else _trecho(p)
        for i, p in enumerate(partes)
    )


def sem_markdown(texto: str) -> str:
    """Versão de reserva em texto puro, se o Telegram recusar o HTML."""
    t = _BLOCO.sub(lambda m: m.group(1).strip(), texto)
    return t.replace("**", "").replace("`", "")

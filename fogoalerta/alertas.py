"""Alerta automático: de tempos em tempos, procura focos novos perto de cada comunidade.

A mensagem de alerta é um modelo fixo (sem IA) de propósito: é mais rápida, não gasta
créditos e não corre risco de a IA inventar algo. Quando a pessoa responde, aí entra o agente.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from . import firms
from .armazenamento import Estado
from .config import CONFIG
from .guardrails import AVISO_FOCO

log = logging.getLogger(__name__)


def montar_mensagem(comunidade: str, novos: list[dict]) -> str:
    perto = novos[0]
    linhas = [
        f"🔥 ALERTA FogoAlerta: {len(novos)} foco(s) de calor novo(s) perto de {comunidade}.",
        f"O mais próximo: {perto['distancia_km']} km a {perto['direcao']}, detectado em {perto['detectado_em']}.",
    ]
    for f in novos[1:3]:
        linhas.append(f"• {f['distancia_km']} km a {f['direcao']} ({f['detectado_em']})")
    linhas += [
        "",
        "Se vir fogo ou fumaça perto de casas ou pessoas, ligue 193.",
        "Responda esta mensagem para saber o que fazer ou para registrar o que você está vendo.",
        "",
        AVISO_FOCO,
        "Fonte: NASA FIRMS.",
    ]
    if CONFIG.modo_demo:
        linhas[0] = "🧪 [SIMULAÇÃO - DEMONSTRAÇÃO] " + linhas[0]
        linhas[-1] = "Fonte: dados simulados para demonstração."
    return "\n".join(linhas)


async def verificar(estado: Estado, enviar: Callable[[int, str], Awaitable[None]],
                    buscar_focos: Callable[..., Awaitable[list[dict]]] = firms.focos_proximos) -> int:
    """Envia alertas de focos ainda não avisados. Devolve quantas mensagens foram enviadas."""
    enviados = 0
    for chat_id, u in estado.usuarios_com_alerta().items():
        try:
            focos = await buscar_focos(u["lat"], u["lon"], u["raio_km"], 1)
        except Exception:  # noqa: BLE001 - um erro numa comunidade não pode parar as outras
            log.exception("Falha ao buscar focos para %s", chat_id)
            continue
        novos = [f for f in focos if not estado.ja_alertado(chat_id, f["id"])]
        if not novos:
            continue
        try:
            await enviar(int(chat_id), montar_mensagem(u["comunidade"], novos))
        except Exception:  # noqa: BLE001
            log.exception("Falha ao enviar alerta para %s", chat_id)
            continue
        estado.marcar_alertado(chat_id, [f["id"] for f in novos])
        enviados += 1
    return enviados

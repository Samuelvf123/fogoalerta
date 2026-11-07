"""Alerta automático: de tempos em tempos, procura focos novos perto de cada comunidade.

A mensagem de alerta é um modelo fixo (sem IA) de propósito: é mais rápida, não gasta
créditos e não corre risco de a IA inventar algo. Quando a pessoa responde, aí entra o agente.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from . import clima, firms, propagacao
from .armazenamento import Estado
from .config import CONFIG
from .guardrails import AVISO_FOCO

log = logging.getLogger(__name__)


def _linha(f: dict) -> str:
    alerta_vento = " ⚠️ vento soprando na direção da comunidade" if f.get("vento", {}).get("situacao") == "a_favor" else ""
    km = str(f["distancia_km"]).replace(".", ",")  # padrão brasileiro: 8,1 km
    return f"• {km} km a {f['direcao']} ({f['detectado_em']}){alerta_vento}"


def montar_mensagem(comunidade: str, novos: list[dict], vento: dict | None = None) -> str:
    linhas = [f"🔥 ALERTA FogoAlerta: {len(novos)} foco(s) de calor novo(s) perto de {comunidade}."]
    linhas += [_linha(f) for f in novos[:3]]
    if vento:
        linhas.append(f"Agora: {propagacao.descrever_vento(vento)}{' (simulado)' if vento.get('simulado') else ''}. "
                      "Estimativa simples: o vento pode mudar, principalmente à noite.")
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
                    buscar_focos: Callable[..., Awaitable[list[dict]]] = firms.focos_proximos,
                    buscar_tempo: Callable[..., Awaitable[dict]] = clima.condicoes) -> int:
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
        vento = None
        try:
            vento = (await buscar_tempo(u["lat"], u["lon"])).get("vento_agora")
        except Exception:  # noqa: BLE001 - sem vento, o alerta sai do mesmo jeito
            log.warning("Sem dado de vento para %s", chat_id)
        novos = propagacao.anotar(novos, u["lat"], u["lon"], vento)
        try:
            await enviar(int(chat_id), montar_mensagem(u["comunidade"], novos, vento))
        except Exception:  # noqa: BLE001
            log.exception("Falha ao enviar alerta para %s", chat_id)
            continue
        estado.marcar_alertado(chat_id, [f["id"] for f in novos])
        enviados += 1
    return enviados

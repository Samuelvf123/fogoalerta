"""Checagem de mensagens encaminhadas ("boatos"): monta o aviso que vai para a IA.

O Telegram informa a data ORIGINAL de uma mensagem encaminhada. Isso ajuda a perceber
quando um áudio ou texto antigo continua circulando como se fosse novo.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Manaus")


def ha_quanto_tempo(antes: datetime, agora: datetime) -> str:
    segundos = max(0, (agora - antes).total_seconds())
    if segundos < 3600:
        return "há menos de 1 hora"
    if segundos < 86400:
        horas = int(segundos // 3600)
        return f"há {horas} hora{'s' if horas > 1 else ''}"
    dias = int(segundos // 86400)
    return f"há {dias} dia{'s' if dias > 1 else ''}"


def prefixo(data_original: datetime | None, agora: datetime | None = None) -> str:
    agora = agora or datetime.now(FUSO)
    if data_original is None:
        quando = "data original desconhecida"
    else:
        local = data_original.astimezone(FUSO)
        quando = f"mensagem original de {local:%d/%m às %Hh%M} ({ha_quanto_tempo(local, agora)})"
    return (f"[A pessoa ENCAMINHOU esta mensagem para conferir se é verdade; {quando}. "
            "Compare com os dados oficiais de agora.]\n")

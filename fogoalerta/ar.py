"""Qualidade do ar (fumaça): PM2,5 pela API gratuita de qualidade do ar do Open-Meteo.

- Dado de MODELO (Copernicus/CAMS), não de estação de medição: é uma estimativa regional.
- Classificação pelo IQAr (Índice de Qualidade do Ar, atualizado conforme a Resolução Conama
  nº 506/2024), que usa a média de 24 h do MP2,5. Textos de efeitos à saúde: Cetesb (2019),
  citados na Orientação Técnica do IQAr do MMA.
"""
from __future__ import annotations

from datetime import datetime

import httpx

URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
REFERENCIA = "IQAr (Resolução Conama nº 506/2024), média de 24 h de MP2,5"
FONTE = "Open-Meteo (modelo Copernicus/CAMS): estimativa por modelo, não é medição de estação"

# (limite superior em µg/m³, qualidade, efeitos à saúde)
FAIXAS = [
    (15, "Boa", "Não há efeitos esperados."),
    (50, "Moderada", "Crianças, idosos e pessoas com doenças respiratórias ou do coração podem ter tosse "
                     "seca e cansaço. A população em geral não é afetada."),
    (75, "Ruim", "Toda a população pode ter tosse seca, cansaço e ardor nos olhos, nariz e garganta. "
                 "Crianças, idosos e doentes podem ter efeitos mais sérios."),
    (125, "Muito ruim", "Toda a população pode ter piora dos sintomas, com falta de ar e respiração "
                        "ofegante. Ainda mais grave para crianças, idosos e doentes."),
    (float("inf"), "Péssima", "Risco sério de problemas respiratórios e do coração para toda a população."),
]


def classificar(pm25_24h: float) -> tuple[str, str]:
    for limite, qualidade, efeitos in FAIXAS:
        if pm25_24h <= limite:
            return qualidade, efeitos
    return FAIXAS[-1][1], FAIXAS[-1][2]


def _br(valor: float) -> str:
    return f"{valor:.0f}"


def resumir(dados: dict) -> dict:
    """Média das últimas 24 h de PM2,5 (até a hora atual) + valor de agora."""
    agora_txt = (dados.get("current") or {}).get("time")
    agora_pm = (dados.get("current") or {}).get("pm2_5")
    horas = (dados.get("hourly") or {}).get("time") or []
    valores = (dados.get("hourly") or {}).get("pm2_5") or []

    serie = list(zip(horas, valores))
    if agora_txt:
        limite = datetime.fromisoformat(agora_txt)
        serie = [(h, v) for h, v in serie if datetime.fromisoformat(h) <= limite]
    ultimas = [v for _, v in serie[-24:] if v is not None]

    if ultimas:
        media = sum(ultimas) / len(ultimas)
        base = f"média das últimas {len(ultimas)} h"
    elif agora_pm is not None:
        media = agora_pm
        base = "valor de agora (sem média de 24 h)"
    else:
        return {"erro": "Sem dado de qualidade do ar agora."}

    qualidade, efeitos = classificar(media)
    resumo = (f"Qualidade do ar estimada: {qualidade} (PM2,5 de {_br(media)} µg/m³, {base}"
              + (f"; agora: {_br(agora_pm)} µg/m³" if agora_pm is not None else "") + "). "
              f"{efeitos}")
    return {
        "resumo_em_portugues": resumo,
        "qualidade": qualidade,
        "pm2_5_media_24h": round(media, 1),
        "pm2_5_agora": agora_pm,
        "efeitos_a_saude": efeitos,
        "referencia": REFERENCIA,
        "fonte": FONTE,
        "aviso": "É uma estimativa regional por modelo: perto de um foco, a fumaça pode estar bem pior.",
    }


async def condicoes(lat: float, lon: float, cliente: httpx.AsyncClient | None = None) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pm2_5",
        "current": "pm2_5",
        "past_days": 1,
        "forecast_days": 1,
        "timezone": "America/Manaus",
    }
    proprio = cliente is None
    cliente = cliente or httpx.AsyncClient(timeout=20)
    try:
        resp = await cliente.get(URL, params=params)
        resp.raise_for_status()
        return resumir(resp.json())
    finally:
        if proprio:
            await cliente.aclose()

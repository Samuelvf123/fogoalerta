"""Condições do tempo pela API gratuita do Open-Meteo (não precisa de chave).

ATENÇÃO: o "nível de risco" calculado aqui é uma estimativa simples do protótipo,
NÃO é o risco de fogo oficial do INPE. O agente é instruído a dizer isso.
"""
from __future__ import annotations

import httpx

URL = "https://api.open-meteo.com/v1/forecast"


def _br(valor: float, casas: int = 1) -> str:
    """Número no formato brasileiro: 1.5 -> '1,5'; 32.0 -> '32'."""
    texto = f"{valor:.{casas}f}".replace(".", ",")
    return texto[:-2] if texto.endswith(",0") else texto


def resumir(dados: dict) -> dict:
    """Transforma a resposta diária do Open-Meteo em um resumo para o agente."""
    d = dados["daily"]
    datas = d["time"]
    chuva = [c or 0 for c in d["precipitation_sum"]]
    tmax = d["temperature_2m_max"]
    vento = d["wind_speed_10m_max"]
    hoje = dados.get("_indice_hoje", len(datas) - 4)  # padrão: past_days=14, forecast_days=4

    dias_sem_chuva = 0
    for mm in reversed(chuva[: hoje + 1]):
        if mm >= 1.0:
            break
        dias_sem_chuva += 1

    pontos = 0
    pontos += 2 if dias_sem_chuva >= 10 else 1 if dias_sem_chuva >= 5 else 0
    pontos += 2 if tmax[hoje] >= 36 else 1 if tmax[hoje] >= 33 else 0
    pontos += 1 if vento[hoje] >= 20 else 0
    nivel = "alto" if pontos >= 4 else "moderado" if pontos >= 2 else "baixo"

    prevista = round(sum(chuva[hoje + 1: hoje + 4]), 1)
    return {
        # Frase pronta em português, com vírgula decimal: evita a IA ler "1.5" como "mil e quinhentos".
        "resumo_em_portugues": (
            f"Hoje: máxima de {_br(tmax[hoje], 0)} graus, vento de até {_br(vento[hoje], 0)} km/h, "
            f"{_br(chuva[hoje])} mm de chuva. {dias_sem_chuva} dia(s) seguido(s) sem chuva. "
            f"Previsão de {_br(prevista)} mm de chuva nos próximos 3 dias. "
            f"Risco estimado de o fogo se espalhar: {nivel}."
        ),
        "data_hoje": datas[hoje],
        "temperatura_max_hoje_c": tmax[hoje],
        "vento_max_hoje_kmh": vento[hoje],
        "chuva_hoje_mm": chuva[hoje],
        "dias_seguidos_sem_chuva": dias_sem_chuva,
        "chuva_prevista_proximos_3_dias_mm": prevista,
        "nivel_risco_estimado": nivel,
        "aviso": "Estimativa simples do protótipo (calor, vento e dias sem chuva); não é índice oficial.",
        "fonte": "Open-Meteo",
    }


async def condicoes(lat: float, lon: float, cliente: httpx.AsyncClient | None = None) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,precipitation_sum,wind_speed_10m_max",
        "past_days": 14,
        "forecast_days": 4,
        "timezone": "America/Manaus",
    }
    proprio = cliente is None
    cliente = cliente or httpx.AsyncClient(timeout=20)
    try:
        resp = await cliente.get(URL, params=params)
        resp.raise_for_status()
        dados = resp.json()
    finally:
        if proprio:
            await cliente.aclose()
    dados["_indice_hoje"] = 14
    return resumir(dados)

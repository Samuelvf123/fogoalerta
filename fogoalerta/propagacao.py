"""Análise SIMPLIFICADA de propagação: o vento de agora leva o fogo na direção da comunidade?

Ideia sugerida pela equipe (Bruno César): "mapear para onde o fogo pode se alastrar".
Versão do protótipo: compara a direção para onde o vento sopra com o caminho do foco até a
comunidade. Serve para PRIORIZAR atenção, não para prever o caminho ou a hora de chegada do fogo.
"""
from __future__ import annotations

from .geo import cardinal, rumo_graus

VENTO_FRACO_KMH = 5
AVISO = ("Estimativa simples (vento de agora x posição do foco). Não é previsão do caminho do fogo, "
         "e o vento pode mudar de direção, principalmente à noite.")

_TEXTOS = {
    "a_favor": "O vento está soprando do foco em direção à comunidade. Atenção redobrada.",
    "de_lado": "O vento está soprando de lado em relação à comunidade.",
    "contra": "O vento tende a levar o fogo para longe da comunidade (mas o vento pode mudar).",
    "vento_fraco": "Vento fraco agora: a direção do fogo é difícil de estimar.",
    "sem_dado": "Sem dado de vento agora.",
}
_PRIORIDADE = {"a_favor": 0, "vento_fraco": 1, "de_lado": 2, "sem_dado": 2, "contra": 3}


def diferenca_angular(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def avaliar(com_lat: float, com_lon: float, foco_lat: float, foco_lon: float,
            vento: dict | None) -> dict:
    """vento = {"de_graus": direção de onde o vento VEM (padrão meteorológico), "kmh": velocidade}."""
    if not vento or vento.get("de_graus") is None:
        return {"situacao": "sem_dado", "explicacao": _TEXTOS["sem_dado"]}
    vai_para = (vento["de_graus"] + 180) % 360
    rumo_ate_comunidade = rumo_graus(foco_lat, foco_lon, com_lat, com_lon)
    dif = diferenca_angular(vai_para, rumo_ate_comunidade)
    if (vento.get("kmh") or 0) < VENTO_FRACO_KMH:
        situacao = "vento_fraco"
    elif dif <= 45:
        situacao = "a_favor"
    elif dif <= 100:
        situacao = "de_lado"
    else:
        situacao = "contra"
    return {"situacao": situacao, "explicacao": _TEXTOS[situacao]}


def anotar(focos: list[dict], com_lat: float, com_lon: float, vento: dict | None) -> list[dict]:
    """Acrescenta a avaliação do vento a cada foco e ordena: primeiro os que o vento traz para a comunidade."""
    anotados = [{**f, "vento": avaliar(com_lat, com_lon, f["lat"], f["lon"], vento)} for f in focos]
    return sorted(anotados, key=lambda f: (_PRIORIDADE[f["vento"]["situacao"]], f["distancia_km"]))


def descrever_vento(vento: dict | None) -> str:
    if not vento or vento.get("de_graus") is None:
        return "sem dado de vento agora"
    de = cardinal(vento["de_graus"])
    para = cardinal((vento["de_graus"] + 180) % 360)
    kmh = round(vento.get("kmh") or 0)
    return f"vento vindo do {de} para o {para}, cerca de {kmh} km/h"

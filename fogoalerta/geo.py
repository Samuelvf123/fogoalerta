"""Funções geográficas simples (sem bibliotecas pesadas)."""
from __future__ import annotations

import math

RAIO_TERRA_KM = 6371.0
_DIRECOES = ["norte", "nordeste", "leste", "sudeste", "sul", "sudoeste", "oeste", "noroeste"]


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em linha reta entre dois pontos (fórmula de Haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RAIO_TERRA_KM * math.asin(math.sqrt(a))


def direcao(lat_origem: float, lon_origem: float, lat_destino: float, lon_destino: float) -> str:
    """Direção aproximada (norte, sudeste...) de quem está na origem olhando para o destino."""
    p1, p2 = math.radians(lat_origem), math.radians(lat_destino)
    dl = math.radians(lon_destino - lon_origem)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    graus = (math.degrees(math.atan2(x, y)) + 360) % 360
    return _DIRECOES[int((graus + 22.5) // 45) % 8]


def caixa_ao_redor(lat: float, lon: float, raio_km: float) -> tuple[float, float, float, float]:
    """Retângulo (oeste, sul, leste, norte) que contém o círculo de raio_km. Formato pedido pelo FIRMS."""
    dlat = raio_km / 111.0
    dlon = raio_km / (111.0 * max(math.cos(math.radians(lat)), 0.01))
    return (round(lon - dlon, 4), round(lat - dlat, 4), round(lon + dlon, 4), round(lat + dlat, 4))

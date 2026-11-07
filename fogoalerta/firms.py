"""Consulta de focos de calor no NASA FIRMS (API de área, formato CSV).

Documentação: https://firms.modaps.eosdis.nasa.gov/api/area/
URL: /api/area/csv/{MAP_KEY}/{FONTE}/{oeste,sul,leste,norte}/{DIAS}
"""
from __future__ import annotations

import csv
import io
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from .config import CONFIG
from .geo import caixa_ao_redor, direcao, distancia_km

URL_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
FUSO_MANAUS = ZoneInfo("America/Manaus")
_CACHE: dict[tuple, tuple[float, list["Foco"]]] = {}
CACHE_SEGUNDOS = 600  # evita gastar a cota do FIRMS com consultas repetidas


class FirmsErro(RuntimeError):
    pass


@dataclass(frozen=True)
class Foco:
    lat: float
    lon: float
    data_hora_utc: datetime
    satelite: str
    instrumento: str
    confianca: str  # "baixa" | "nominal" | "alta"
    frp: float | None  # potência radiativa do fogo (MW): maior = fogo mais intenso
    fonte: str

    @property
    def id(self) -> str:
        if self.fonte == "SIMULADO":
            # No modo demonstração o horário "anda" com o relógio; sem isto, o mesmo foco
            # simulado viraria "novo" a cada hora e o alerta se repetiria. Um alerta por dia basta.
            return f"{self.fonte}:{self.lat:.4f}:{self.lon:.4f}:{self.data_hora_local:%Y%m%d}"
        return f"{self.fonte}:{self.lat:.4f}:{self.lon:.4f}:{self.data_hora_utc:%Y%m%d%H%M}"

    @property
    def data_hora_local(self) -> datetime:
        return self.data_hora_utc.astimezone(FUSO_MANAUS)


def _confianca(valor: str) -> str:
    v = (valor or "").strip().lower()
    if v in ("l", "low"):
        return "baixa"
    if v in ("n", "nominal"):
        return "nominal"
    if v in ("h", "high"):
        return "alta"
    try:  # MODIS usa 0 a 100
        n = float(v)
    except ValueError:
        return "desconhecida"
    return "baixa" if n < 30 else "nominal" if n < 80 else "alta"


def ler_csv(texto: str, fonte: str) -> list[Foco]:
    """Converte o CSV do FIRMS em objetos Foco. Lança FirmsErro se a resposta não for CSV."""
    texto = texto.strip()
    if not texto:
        return []
    if not texto.lower().startswith("latitude"):
        raise FirmsErro(f"Resposta inesperada do FIRMS ({fonte}): {texto[:200]}")
    focos = []
    for linha in csv.DictReader(io.StringIO(texto)):
        try:
            hhmm = linha["acq_time"].zfill(4)
            quando = datetime.strptime(f"{linha['acq_date']} {hhmm}", "%Y-%m-%d %H%M").replace(
                tzinfo=timezone.utc
            )
            frp = float(linha["frp"]) if linha.get("frp") else None
            focos.append(Foco(
                lat=float(linha["latitude"]),
                lon=float(linha["longitude"]),
                data_hora_utc=quando,
                satelite=linha.get("satellite", ""),
                instrumento=linha.get("instrument", ""),
                confianca=_confianca(linha.get("confidence", "")),
                frp=frp,
                fonte=fonte,
            ))
        except (KeyError, ValueError, TypeError, AttributeError):
            continue  # linha malformada: ignora em vez de derrubar o bot
    return focos


async def baixar_focos(caixa: tuple[float, float, float, float], dias: int,
                       cliente: httpx.AsyncClient | None = None) -> list[Foco]:
    """Baixa os focos de todas as fontes configuradas dentro da caixa (oeste, sul, leste, norte)."""
    if not CONFIG.firms_map_key:
        raise FirmsErro("FIRMS_MAP_KEY não configurada no .env")
    dias = max(1, min(int(dias), 5))
    chave = (caixa, dias)
    agora = time.monotonic()
    if chave in _CACHE and agora - _CACHE[chave][0] < CACHE_SEGUNDOS:
        return _CACHE[chave][1]

    area = ",".join(str(c) for c in caixa)
    proprio = cliente is None
    cliente = cliente or httpx.AsyncClient(timeout=30)
    focos: list[Foco] = []
    erros = []
    try:
        for fonte in CONFIG.firms_fontes:
            url = f"{URL_BASE}/{CONFIG.firms_map_key}/{fonte}/{area}/{dias}"
            try:
                resp = await cliente.get(url)
                resp.raise_for_status()
                focos.extend(ler_csv(resp.text, fonte))
            except (httpx.HTTPError, FirmsErro) as e:
                erros.append(f"{fonte}: {e}")
    finally:
        if proprio:
            await cliente.aclose()
    if erros and not focos and len(erros) == len(CONFIG.firms_fontes):
        raise FirmsErro("; ".join(erros))
    _CACHE[chave] = (agora, focos)
    return focos


def filtrar_proximos(focos: list[Foco], lat: float, lon: float, raio_km: float) -> list[dict]:
    """Mantém só os focos dentro do raio, remove duplicados (vários satélites no mesmo ponto) e ordena."""
    vistos: dict[tuple, dict] = {}
    for f in focos:
        d = distancia_km(lat, lon, f.lat, f.lon)
        if d > raio_km:
            continue
        # Satélites diferentes podem ver o mesmo fogo: agrupa pontos a ~400 m no mesmo dia.
        chave = (round(f.lat, 2), round(f.lon, 2), f.data_hora_utc.date())
        item = {
            "id": f.id,
            "distancia_km": round(d, 1),
            "direcao": direcao(lat, lon, f.lat, f.lon),
            "lat": f.lat,
            "lon": f.lon,
            "detectado_em": f.data_hora_local.strftime("%d/%m às %Hh%M"),
            "confianca": f.confianca,
            "intensidade_frp_mw": f.frp,
            "satelite": f"{f.instrumento} {f.satelite}".strip(),
        }
        if chave not in vistos or d < vistos[chave]["distancia_km"]:
            vistos[chave] = item
    return sorted(vistos.values(), key=lambda i: i["distancia_km"])


def focos_demo(lat: float, lon: float) -> list[Foco]:
    """Focos SIMULADOS para demonstração: deslocamentos em graus a partir do ponto, com horários de hoje."""
    agora = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    caminho = CONFIG.pasta_dados / "demo_focos.csv"
    focos = []
    for linha in csv.DictReader(caminho.open(encoding="utf-8")):
        quando = agora.replace(minute=0) - timedelta(hours=int(linha["horas_atras"]))
        focos.append(Foco(lat + float(linha["dlat"]), lon + float(linha["dlon"]), quando,
                          "N", "VIIRS", linha["confianca"], float(linha["frp"]), "SIMULADO"))
    return focos


async def focos_proximos(lat: float, lon: float, raio_km: float = 10, dias: int = 1,
                         cliente: httpx.AsyncClient | None = None) -> list[dict]:
    if CONFIG.modo_demo:
        return filtrar_proximos(focos_demo(lat, lon), lat, lon, raio_km)
    caixa = caixa_ao_redor(lat, lon, raio_km)
    focos = await baixar_focos(caixa, dias, cliente)
    return filtrar_proximos(focos, lat, lon, raio_km)

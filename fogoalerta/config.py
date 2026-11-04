"""Configurações lidas do arquivo .env (veja .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")


def _int(nome: str, padrao: int) -> int:
    try:
        return int(os.getenv(nome, padrao))
    except ValueError:
        return padrao


@dataclass(frozen=True)
class Config:
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    # Provedor de IA: "gemini" (plano gratuito do Google AI Studio) ou "claude" (pago pelo Console).
    llm_provedor: str = os.getenv("LLM_PROVEDOR", "gemini").strip().lower()
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    # Confiram no AI Studio quais modelos aparecem como gratuitos no projeto de vocês.
    gemini_modelo: str = os.getenv("GEMINI_MODELO", "gemini-3.8-flash")
    # Modelos usados se o principal estiver sobrecarregado (503) ou sem cota (429), em ordem.
    gemini_reservas: tuple[str, ...] = tuple(
        m.strip() for m in os.getenv("GEMINI_MODELOS_RESERVA", "gemini-3.5-flash-lite,gemini-3.6-flash").split(",")
        if m.strip()
    )
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    claude_modelo: str = os.getenv("CLAUDE_MODELO", "claude-haiku-5-5")
    firms_map_key: str = os.getenv("FIRMS_MAP_KEY", "")
    # Fontes do FIRMS separadas por vírgula. VIIRS tem pixel menor (375 m) que MODIS.
    firms_fontes: tuple[str, ...] = tuple(
        f.strip() for f in os.getenv(
            "FIRMS_FONTES", "VIIRS_SNPP_NRT,VIIRS_NOAA20_NRT,VIIRS_NOAA21_NRT"
        ).split(",") if f.strip()
    )
    raio_alerta_km: int = _int("RAIO_ALERTA_KM", 10)
    intervalo_alerta_min: int = _int("INTERVALO_ALERTA_MIN", 30)
    pasta_dados: Path = RAIZ / "data"
    # Modo demonstração: usa focos SIMULADOS (data/demo_focos.csv) perto de Autazes, com a data de hoje.
    # Serve para gravar o vídeo e apresentar quando não houver focos reais. As respostas avisam que é simulação.
    modo_demo: bool = os.getenv("MODO_DEMO", "0") == "1"


CONFIG = Config()

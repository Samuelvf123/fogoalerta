"""Registro de relatos de campo e indicação do canal oficial certo.

O protótipo NÃO envia nada aos órgãos automaticamente: ele organiza o relato,
gera um texto pronto para encaminhar e diz para onde mandar.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import CONFIG

FUSO = ZoneInfo("America/Manaus")
TIPOS = ("fogo_ativo", "queimada_ilegal", "desmatamento_ou_grilagem", "fumaca_saude", "outro")


def carregar_canais(caminho: Path | None = None) -> dict:
    caminho = caminho or CONFIG.pasta_dados / "canais.json"
    return json.loads(caminho.read_text(encoding="utf-8"))


def canal_para(tipo: str, canais: dict | None = None) -> list[dict]:
    canais = canais or carregar_canais()
    return canais.get(tipo) or canais["outro"]


def registrar(tipo: str, descricao: str, comunidade: str | None = None,
              lat: float | None = None, lon: float | None = None,
              fotos: list[str] | None = None, descricao_foto: str | None = None,
              anonimo: bool = True, contato: str | None = None, origem_local: str | None = None,
              pasta: Path | None = None, canais: dict | None = None) -> dict:
    """Salva o relato em data/relatos/relatos.jsonl e devolve protocolo, canal e texto pronto."""
    if tipo not in TIPOS:
        tipo = "outro"
    pasta = pasta or CONFIG.pasta_dados / "relatos"
    pasta.mkdir(parents=True, exist_ok=True)
    agora = datetime.now(FUSO)
    protocolo = f"FA-{agora:%y%m%d}-{secrets.token_hex(2).upper()}"
    destinos = canal_para(tipo, canais)

    registro = {
        "protocolo": protocolo,
        "registrado_em": agora.isoformat(timespec="minutes"),
        "tipo": tipo,
        "descricao": descricao.strip()[:2000],
        "comunidade": comunidade,
        "lat": lat,
        "lon": lon,
        "origem_local": origem_local,  # "enviada" (pela pessoa) | "comunidade" (sede cadastrada)
        "fotos": fotos or [],
        "descricao_foto_ia": descricao_foto,
        "anonimo": anonimo,
        # Privacidade: só guarda contato se a pessoa escolheu se identificar.
        "contato": None if anonimo else contato,
    }
    with open(pasta / "relatos.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")

    return {
        "protocolo": protocolo,
        "encaminhar_para": destinos,
        "texto_para_encaminhar": formatar(registro),
        "observacao": "O protótipo não envia aos órgãos sozinho; a pessoa (ou a equipe) encaminha o texto.",
    }


def formatar(r: dict) -> str:
    rotulos = {
        "fogo_ativo": "Fogo ativo",
        "queimada_ilegal": "Queimada possivelmente irregular",
        "desmatamento_ou_grilagem": "Possível desmatamento ou ocupação irregular",
        "fumaca_saude": "Fumaça / problema de saúde",
        "outro": "Outro",
    }
    linhas = [
        f"RELATO {r['protocolo']}",
        f"Tipo: {rotulos.get(r['tipo'], r['tipo'])}",
        f"Data/hora: {datetime.fromisoformat(r['registrado_em']):%d/%m/%Y %Hh%M} (horário de Manaus)",
    ]
    # Com localização enviada, a comunidade cadastrada não entra: evita confusão de local e
    # protege o anonimato (em comunidade pequena, ela ajudaria a identificar quem relatou).
    if r.get("comunidade") and r.get("origem_local") != "enviada":
        linhas.append(f"Comunidade de referência: {r['comunidade']}")
    if r.get("lat") is not None and r.get("lon") is not None:
        rotulo = ("Localização enviada pela pessoa" if r.get("origem_local") == "enviada"
                  else "Local de referência (comunidade cadastrada; NÃO é a posição exata)")
        linhas.append(f"{rotulo}: {r['lat']:.5f}, {r['lon']:.5f} "
                      f"(https://maps.google.com/?q={r['lat']:.5f},{r['lon']:.5f})")
    linhas.append(f"O que foi visto: {r['descricao']}")
    if r.get("descricao_foto_ia"):
        linhas.append(f"Descrição da foto (gerada por IA, conferir): {r['descricao_foto_ia']}")
    if r.get("fotos"):
        linhas.append(f"Fotos anexadas: {len(r['fotos'])}")
    linhas.append("Denunciante: anônimo" if r["anonimo"] else f"Contato: {r.get('contato') or 'não informado'}")
    return "\n".join(linhas)

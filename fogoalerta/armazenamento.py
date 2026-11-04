"""Armazenamento simples em arquivo JSON (suficiente para o protótipo).

Guarda só o necessário: a comunidade/localização de cada chat e quais focos já
foram avisados. Não guarda nome nem telefone.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .config import CONFIG

DIAS_GUARDAR_ALERTAS = 5


class Estado:
    def __init__(self, caminho: Path | None = None):
        self.caminho = caminho or CONFIG.pasta_dados / "estado.json"
        self.dados = {"usuarios": {}, "alertados": {}}
        if self.caminho.exists():
            self.dados.update(json.loads(self.caminho.read_text(encoding="utf-8")))

    def salvar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.caminho.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.dados, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.caminho)

    # --- usuários -------------------------------------------------------
    def definir_local(self, chat_id: int, nome: str, lat: float, lon: float,
                      raio_km: int | None = None) -> None:
        self.dados["usuarios"][str(chat_id)] = {
            "comunidade": nome,
            "lat": lat,
            "lon": lon,
            "raio_km": raio_km or CONFIG.raio_alerta_km,
            "alertas": True,
        }
        self.salvar()

    def usuario(self, chat_id: int) -> dict | None:
        return self.dados["usuarios"].get(str(chat_id))

    def ativar_alertas(self, chat_id: int, ativo: bool) -> None:
        u = self.usuario(chat_id)
        if u:
            u["alertas"] = ativo
            self.salvar()

    def usuarios_com_alerta(self) -> dict[str, dict]:
        return {cid: u for cid, u in self.dados["usuarios"].items() if u.get("alertas")}

    # --- focos já avisados ----------------------------------------------
    def ja_alertado(self, chat_id: int | str, foco_id: str) -> bool:
        return foco_id in self.dados["alertados"].get(str(chat_id), {})

    def marcar_alertado(self, chat_id: int | str, foco_ids: list[str]) -> None:
        agora = time.time()
        reg = self.dados["alertados"].setdefault(str(chat_id), {})
        for fid in foco_ids:
            reg[fid] = agora
        limite = agora - DIAS_GUARDAR_ALERTAS * 86400
        for cid in list(self.dados["alertados"]):
            self.dados["alertados"][cid] = {k: v for k, v in self.dados["alertados"][cid].items() if v >= limite}
        self.salvar()

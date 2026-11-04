"""Base de orientações (RAG simples) a partir dos arquivos .md em data/orientacoes/.

Cada arquivo é dividido em trechos pelos títulos "## ". A busca usa pontuação por
palavras (sem embeddings), o que é suficiente para algumas dezenas de trechos e não
precisa de nenhum serviço extra. Se a base crescer, troquem por embeddings.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .config import CONFIG

STOPWORDS = set("""
a o as os um uma uns umas de do da dos das em no na nos nas por para pra pro com sem
e ou que se eu tu ele ela nos vos eles elas meu minha seu sua isso isto esse essa este
esta aquele aquela ja nao sim mais menos muito pouco como quando onde qual quais ser
estar ter tem posso pode podem fazer faz foi vai vou e ao aos the of
""".split())


def normalizar(texto: str) -> list[str]:
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    palavras = re.findall(r"[a-z0-9]+", texto)
    return [_radical(p) for p in palavras if p not in STOPWORDS and len(p) > 2]


def _radical(p: str) -> str:
    """Radical bem simples: corta em 6 letras para casar 'proibido'/'proibição', 'queimada'/'queimar'."""
    return p[:6]


@dataclass
class Trecho:
    arquivo: str
    titulo: str
    texto: str
    fonte: str
    termos: list[str]


class BaseConhecimento:
    def __init__(self, pasta: Path | None = None):
        self.pasta = pasta or CONFIG.pasta_dados / "orientacoes"
        self.trechos: list[Trecho] = []
        self._carregar()

    def _carregar(self) -> None:
        for arq in sorted(self.pasta.glob("*.md")):
            conteudo = arq.read_text(encoding="utf-8")
            fonte = ""
            m = re.search(r"^Fonte[s]?:\s*(.+)$", conteudo, re.MULTILINE)
            if m:
                fonte = m.group(1).strip()
            partes = re.split(r"^## ", conteudo, flags=re.MULTILINE)
            for parte in partes[1:]:
                titulo, _, corpo = parte.partition("\n")
                corpo = corpo.strip()
                if corpo:
                    self.trechos.append(Trecho(arq.stem, titulo.strip(), corpo, fonte,
                                               normalizar(titulo + " " + titulo + " " + corpo)))
        n = len(self.trechos) or 1
        self._df: dict[str, int] = {}
        for t in self.trechos:
            for termo in set(t.termos):
                self._df[termo] = self._df.get(termo, 0) + 1
        self._idf = {t: math.log(1 + n / df) for t, df in self._df.items()}

    def buscar(self, pergunta: str, k: int = 3) -> list[dict]:
        consulta = normalizar(pergunta)
        if not consulta:
            return []
        resultados = []
        for t in self.trechos:
            freq: dict[str, int] = {}
            for termo in t.termos:
                freq[termo] = freq.get(termo, 0) + 1
            pontos = sum(self._idf.get(q, 0) * (1 + math.log(freq[q])) for q in set(consulta) if q in freq)
            if pontos > 0:
                resultados.append((pontos / math.sqrt(len(t.termos) + 1), t))
        resultados.sort(key=lambda x: x[0], reverse=True)
        return [
            {"tema": t.titulo, "texto": t.texto, "fonte": t.fonte or t.arquivo}
            for _, t in resultados[:k]
        ]

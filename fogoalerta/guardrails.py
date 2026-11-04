"""Regras de segurança que NÃO dependem da IA (rodam antes e depois do modelo).

1. Emergência: se a mensagem indica fogo ativo ou perigo, o bot manda o 193 na hora,
   antes de qualquer resposta da IA.
2. Aviso de foco: toda resposta que usou dados de satélite precisa dizer que foco
   não é incêndio confirmado. Se a IA esquecer, o aviso é acrescentado.
3. Nunca autorizar queimada: se a resposta parecer liberar o uso do fogo, é substituída.
"""
from __future__ import annotations

import re
import unicodedata

LIMITE_ENTRADA = 1500

MENSAGEM_EMERGENCIA = (
    "🚨 Se o fogo está acontecendo agora ou ameaça pessoas, casas ou roças, "
    "LIGUE 193 (Corpo de Bombeiros) primeiro. Afaste as pessoas, principalmente "
    "crianças e idosos, para longe da fumaça e do lado de onde o vento não leva o fogo. "
    "Depois, se puder, me mande a localização para eu organizar o relato."
)

AVISO_FOCO = (
    "ℹ️ Foco de calor é uma detecção por satélite: não confirma que há incêndio, "
    "e um fogo pequeno ou embaixo das árvores pode não aparecer."
)

RESPOSTA_SEM_AUTORIZACAO = (
    "Eu não posso autorizar o uso do fogo. Neste período, o uso do fogo está proibido no "
    "Amazonas por decreto estadual, e fora da proibição quem autoriza a queima controlada "
    "é o órgão ambiental. Posso explicar alternativas para limpar o terreno sem fogo. Quer?"
)


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


# Fortes: indicam perigo mesmo em forma de pergunta.
_EMERGENCIA_FORTE = [
    r"\bpegando fogo\b", r"\bpegou fogo\b", r"\bta queimando\b", r"\besta queimando\b",
    # "chamas" no plural: "chama" sozinho confunde com "como se chama".
    r"\bincendio\b", r"\bsocorro\b", r"\bchamas\b", r"\blabaredas?\b",
    r"\bnao (consigo|da pra) respirar\b", r"\bcasa queimando\b", r"\bfogo alto\b",
]
# Fracas: "fogo perto", "fumaça forte"... são emergência numa afirmação ("o fogo tá chegando na roça"),
# mas não numa pergunta de consulta ("tem fogo perto?").
_EMERGENCIA_FRACA = [
    r"\bfogo (esta |ta )?(perto|chegando|aqui)\b", r"\bfogo (na|no) (casa|roca|quintal|comunidade|mato)\b",
    r"\bfumaca (forte|muito|demais)\b", r"\bfalta de ar\b", r"\bfogo ativo\b",
]
_PERGUNTA = re.compile(r"(\?\s*$)|^(tem|ha|existe|teve|houve|como|onde|qual|quais|quando|o que|sera)\b")

_AUTORIZA = [
    r"(?<!nao )(?<!ninguem )\bpode(m)? (sim,? )?(queimar|fazer a queimada|usar o fogo|botar fogo|tocar fogo)\b",
    r"(?<!nao )\b(esta|ta) liberad[oa] (queimar|o uso do fogo|a queimada)\b",
    r"\bpode queimar sem problema\b",
    r"\b(eu )?autorizo\b",
]


def limpar_entrada(texto: str | None) -> str:
    texto = (texto or "").strip()
    return texto[:LIMITE_ENTRADA]


def detectar_emergencia(texto: str) -> bool:
    t = _norm(texto).strip()
    if any(re.search(p, t) for p in _EMERGENCIA_FORTE):
        return True
    if _PERGUNTA.search(t):
        return False
    return any(re.search(p, t) for p in _EMERGENCIA_FRACA)


def parece_autorizar_queima(resposta: str) -> bool:
    t = _norm(resposta)
    return any(re.search(p, t) for p in _AUTORIZA)


def tem_aviso_foco(resposta: str) -> bool:
    t = _norm(resposta)
    return "satelite" in t and bool(re.search(r"nao (confirma|significa|e (um )?incendio)", t))


def revisar_saida(resposta: str, usou_focos: bool) -> str:
    """Aplica as regras 2 e 3 na resposta final da IA."""
    resposta = (resposta or "").strip() or "Desculpe, não consegui responder agora. Tente de novo."
    if parece_autorizar_queima(resposta):
        return RESPOSTA_SEM_AUTORIZACAO
    if usou_focos and not tem_aviso_foco(resposta):
        resposta = f"{resposta}\n\n{AVISO_FOCO}"
    return resposta

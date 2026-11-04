"""Conversa com o agente pelo terminal, sem Telegram. Ótimo para testar prompts e guardrails.

Uso:  python scripts/conversar.py
Digite 'sair' para terminar. Usa a sede de Autazes como comunidade.
Precisa da chave da IA no .env (GEMINI_API_KEY ou ANTHROPIC_API_KEY) e da FIRMS_MAP_KEY (ou MODO_DEMO=1).
"""
import asyncio
import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fogoalerta.agente import Agente  # noqa: E402
from fogoalerta.armazenamento import Estado  # noqa: E402
from fogoalerta.guardrails import MENSAGEM_EMERGENCIA, detectar_emergencia  # noqa: E402
from fogoalerta.llm import ErroLLM  # noqa: E402

CHAT_TESTE = 1

# Mostra quais ferramentas a IA usou em cada resposta (útil para conferir se ela consultou os dados
# ou inventou). Para esconder, rode com:  python scripts\conversar.py --quieto
if "--quieto" not in sys.argv:
    logging.basicConfig(format="   %(message)s", level=logging.WARNING)
    logging.getLogger("fogoalerta").setLevel(logging.INFO)


async def main() -> None:
    estado = Estado(Path(tempfile.gettempdir()) / "fogoalerta_teste_estado.json")
    estado.definir_local(CHAT_TESTE, "Autazes (sede)", -3.5797, -59.1306)
    agente = Agente(estado=estado)
    print(f"Usando {agente.provedor.nome} ({agente.provedor.modelo}).")
    print("FogoAlerta (terminal). Digite 'sair' para terminar, '/boletim' para o boletim de rádio.\n")
    while True:
        try:
            texto = input("você> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if texto.lower() in ("sair", "exit", "quit"):
            break
        if not texto:
            continue
        if detectar_emergencia(texto):
            print("\nbot> [mensagem fixa de emergência]", MENSAGEM_EMERGENCIA)
        try:
            if texto == "/boletim":
                resposta = await agente.boletim_radio(CHAT_TESTE)
            else:
                resposta = await agente.responder(CHAT_TESTE, texto)
        except ErroLLM as e:
            resposta = f"[ERRO DA IA: {e.tipo}] {e}"
        print("\nbot>", resposta, "\n")


if __name__ == "__main__":
    asyncio.run(main())

"""Lista os modelos do Gemini disponíveis para a sua chave (para escolher o GEMINI_MODELO).

Uso:  python scripts/listar_modelos_gemini.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google import genai  # noqa: E402

from fogoalerta.config import CONFIG  # noqa: E402

if not CONFIG.gemini_api_key:
    raise SystemExit("Configure GEMINI_API_KEY no .env")
cliente = genai.Client(api_key=CONFIG.gemini_api_key)
for m in cliente.models.list():
    acoes = getattr(m, "supported_actions", None) or []
    if "generateContent" in acoes and "gemini" in m.name:
        print(m.name.replace("models/", ""))
print("\nObs.: aparecer na lista não garante que é gratuito. Confira no AI Studio (aba de uso/limites).")

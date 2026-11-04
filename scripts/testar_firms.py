"""Teste rápido do FIRMS e do tempo, sem Telegram e sem IA.

Uso:  python scripts/testar_firms.py            (sede de Autazes, 30 km, 3 dias)
      python scripts/testar_firms.py -3.58 -59.13 50 5
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fogoalerta import clima, firms  # noqa: E402


async def main() -> None:
    lat = float(sys.argv[1]) if len(sys.argv) > 1 else -3.5797
    lon = float(sys.argv[2]) if len(sys.argv) > 2 else -59.1306
    raio = float(sys.argv[3]) if len(sys.argv) > 3 else 30
    dias = int(sys.argv[4]) if len(sys.argv) > 4 else 3

    print(f"Buscando focos a até {raio} km de ({lat}, {lon}) nos últimos {dias} dias...")
    focos = await firms.focos_proximos(lat, lon, raio, dias)
    print(f"{len(focos)} foco(s) encontrado(s).")
    for f in focos[:15]:
        print(f"  {f['distancia_km']:>5} km a {f['direcao']:<9} {f['detectado_em']}  "
              f"confiança {f['confianca']:<8} FRP {f['intensidade_frp_mw']}")

    print("\nTempo:")
    for k, v in (await clima.condicoes(lat, lon)).items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())

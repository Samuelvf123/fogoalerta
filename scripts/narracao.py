"""Gera a narração do vídeo de demonstração com as vozes do edge-tts (as mesmas do bot).

Rodar na pasta do projeto, com o ambiente ativado:
    python scripts/narracao.py

Os áudios vão para a pasta Vídeos\\FogoAlerta_narracao do seu usuário,
um arquivo por cena, em duas vozes (antonio e francisca).
"""
import asyncio
import zipfile
from pathlib import Path

import edge_tts

VOZES = {
    "antonio": "pt-BR-AntonioNeural",
    "francisca": "pt-BR-FranciscaNeural",
}

# Uma fala por cena do vídeo, na ordem. Números escritos como devem ser falados.
FALAS = [
    "Este é o Fogo Alerta: inteligência artificial contra as queimadas no interior do Amazonas.",
    "Em 2026, o fogo chegou perto de casa. Em outubro, a região de Manaus teve trinta e sete vezes mais focos que em 2025. "
    "Autazes lidera a região, e queimar está proibido.",
    "Quem vive perto do fogo sente na pele. Em Iranduba, uma criança disse que não consegue mais respirar direito. "
    "Em Careiro, a distância atrasa a brigada. E quem denuncia pode virar alvo de ameaças.",
    "Os satélites já veem o fogo, e os órgãos recebem esses dados. Mas a informação ainda não chega a quem está perto dele.",
    "O Fogo Alerta leva essa informação pelo Telegram. Ele faz três coisas: avisa, orienta e ajuda a relatar.",
    "Quando aparece um foco perto da comunidade, o bot avisa sozinho e diz se o vento está soprando para lá.",
    "A pessoa pode perguntar do jeito que fala. Ele consulta os satélites da NASA na hora e não inventa regra nem previsão.",
    "Também estima a qualidade do ar e dá cuidados simples para crianças, idosos e quem tem problema respiratório.",
    "Recebeu um aviso no grupo? É só encaminhar. O bot mostra de quando é a mensagem e o que os dados dizem agora.",
    "Ele nunca autoriza queimar. Nem com insistência, nem quando alguém diz ser fiscal. "
    "Essa regra fica no código, fora da inteligência artificial.",
    "Ele não acusa ninguém. Registra o fato, de forma anônima, e deixa a investigação para os órgãos.",
    "Se alguém está com falta de ar, o bot manda ligar para o SAMU, um nove dois, e não indica remédio.",
    "O relato vira um protocolo com texto pronto para levar ao órgão certo. O contato só fica guardado se a pessoa quiser.",
    "E todo dia ele pode gerar um boletim para a rádio comunitária, em texto e em áudio.",
    "Por dentro, a inteligência artificial entende a pergunta e escolhe a ferramenta: satélite, tempo, ar, orientações ou relatos. "
    "As regras de segurança ficam fixas no código.",
    "Testamos antes de chegar a alguém: cento e cinco testes automáticos e vinte e dois problemas corrigidos.",
    "O próximo passo é um piloto em Autazes, com moradores e brigadistas, e depois WhatsApp, mensagem de texto e rádio.",
    "Fogo Alerta. Código aberto. Em emergência, ligue um nove três para os Bombeiros, ou um nove dois para o SAMU.",
]


async def main():
    destino = Path.home() / "Videos" / "FogoAlerta_narracao"
    for nome, voz in VOZES.items():
        pasta = destino / nome
        pasta.mkdir(parents=True, exist_ok=True)
        for i, texto in enumerate(FALAS, 1):
            arquivo = pasta / f"cena_{i:02d}.mp3"
            await edge_tts.Communicate(texto, voz).save(str(arquivo))
            print("ok", nome, arquivo.name)
        # um .zip por voz, para anexar de uma vez só na conversa
        zip_voz = destino / f"narracao_{nome}.zip"
        with zipfile.ZipFile(zip_voz, "w") as z:
            for arquivo in sorted(pasta.glob("cena_*.mp3")):
                z.write(arquivo, arquivo.name)
        print("zip:", zip_voz)
    print("Pronto! Áudios em:", destino)


if __name__ == "__main__":
    asyncio.run(main())

"""Bot do Telegram do FogoAlerta.

Rodar:  python -m fogoalerta.bot
"""
from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
                      ReplyKeyboardMarkup, ReplyKeyboardRemove, Update)
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest, NetworkError
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

from . import VERSAO, alertas, audio, encaminhada, voz
from .agente import Agente
from .armazenamento import Estado
from .config import CONFIG
from .firms import FirmsErro
from .formatacao import para_html, sem_markdown
from .guardrails import MENSAGEM_EMERGENCIA, detectar_emergencia
from .llm import ErroLLM

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)  # não loga URLs (que contêm a chave do FIRMS)
log = logging.getLogger("fogoalerta")

estado = Estado()
agente: Agente  # criado em main(), depois de conferir as chaves
COMUNIDADES = json.loads((CONFIG.pasta_dados / "comunidades.json").read_text(encoding="utf-8"))["comunidades"]
PASTA_FOTOS = CONFIG.pasta_dados / "relatos" / "fotos"

BOAS_VINDAS = (
    "Olá! Eu sou o FogoAlerta 🔥🌳\n\n"
    "Eu posso:\n"
    "• avisar quando o satélite detectar foco de calor perto da sua comunidade;\n"
    "• tirar dúvidas sobre prevenção e o uso do fogo;\n"
    "• ajudar a registrar o que você está vendo (pode ser anônimo).\n\n"
    "Primeiro, me diga onde você está: toque em \"📍 Enviar minha localização\" "
    "ou use /comunidade para escolher da lista.\n\n"
    "⚠️ Eu não substituo os Bombeiros. Em emergência, ligue 193."
)

AJUDA = (
    "Comandos:\n"
    "/comunidade - escolher a comunidade\n"
    "/focos - ver focos de calor perto\n"
    "/tempo - calor, vento e chuva\n"
    "/ar - fumaça e qualidade do ar\n"
    "/checar - conferir um aviso que você recebeu\n"
    "/boletim - texto para ler na rádio\n"
    "/relato - registrar o que você viu\n"
    "/alertas_on ou /alertas_off - ligar ou desligar avisos\n"
    "/audio_on ou /audio_off - respostas também em áudio\n"
    "/privacidade - o que eu guardo\n"
    "/limpar - começar a conversa de novo\n\n"
    "Você também pode escrever, mandar áudio ou foto."
)

PRIVACIDADE = (
    "O que eu guardo:\n"
    "• a comunidade ou localização que você escolheu (para os alertas);\n"
    "• os relatos que você pedir para registrar, anônimos por padrão;\n"
    "• as fotos enviadas para um relato.\n\n"
    "Não guardo seu nome nem seu telefone, a não ser que você peça para se identificar num relato. "
    "As conversas ficam só na memória e somem quando o bot reinicia.\n"
    "Para gerar respostas em áudio, o texto da resposta passa por um serviço de voz na internet.\n\n"
    "Atenção: este protótipo usa um serviço de IA de terceiros. Não mande dados pessoais "
    "(CPF, documentos, endereço completo) nas mensagens."
)


# ---------------------------------------------------------------- utilidades
async def enviar_texto(update: Update, texto: str) -> None:
    """Envia com formatação (negrito, blocos). Se o Telegram recusar, manda em texto puro."""
    msg = update.effective_message
    if len(texto) <= 3500:
        try:
            await msg.reply_text(para_html(texto), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            return
        except BadRequest as e:
            log.warning("HTML recusado pelo Telegram (%s); enviando texto puro.", e)
    puro = sem_markdown(texto)
    for i in range(0, len(puro), 4000):  # limite do Telegram: 4096 caracteres
        await msg.reply_text(puro[i:i + 4000], disable_web_page_preview=True)


def prefixo_encaminhada(update: Update) -> str:
    """Se a mensagem foi encaminhada, devolve o aviso com a data original (para checar boatos)."""
    origem = getattr(update.effective_message, "forward_origin", None)
    return encaminhada.prefixo(origem.date) if origem else ""


async def enviar_audio(update: Update, context: ContextTypes.DEFAULT_TYPE, texto: str,
                       legenda: str | None = None) -> None:
    """Manda a resposta também em voz. Se falhar, a pessoa já tem o texto: só registra no log."""
    with tempfile.TemporaryDirectory() as tmp:
        caminho = str(Path(tmp) / "resposta.mp3")
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.RECORD_VOICE)
        if not await voz.sintetizar(texto, caminho):
            return
        # Áudio é um extra: nenhuma falha aqui pode virar "Tive um problema" para a pessoa.
        try:
            with open(caminho, "rb") as f:
                await update.effective_message.reply_voice(f, caption=legenda, write_timeout=90, read_timeout=90)
        except BadRequest:
            try:
                with open(caminho, "rb") as f:  # alguns clientes só aceitam como áudio comum
                    await update.effective_message.reply_audio(f, caption=legenda, title="FogoAlerta",
                                                               write_timeout=90, read_timeout=90)
            except NetworkError as e:
                log.warning("Falha ao enviar áudio: %s", e)
        except NetworkError as e:
            # Inclui TimedOut: muitas vezes o Telegram entrega o áudio mesmo depois do tempo esgotado.
            log.warning("Envio do áudio demorou ou falhou (%s); o texto já foi entregue.", e)


def quer_audio(chat_id: int) -> bool:
    return bool(estado.preferencia(chat_id, "audio", False))


async def perguntar_ao_agente(update: Update, context: ContextTypes.DEFAULT_TYPE, texto: str,
                              imagem: tuple[bytes, str] | None = None, em_audio: bool = False) -> None:
    chat_id = update.effective_chat.id
    # Mensagem encaminhada é checagem de boato, não pedido de socorro: não dispara o aviso fixo.
    emergencia = detectar_emergencia(texto) and not prefixo_encaminhada(update)
    if emergencia:
        await update.effective_message.reply_text(MENSAGEM_EMERGENCIA)
    await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
    try:
        resposta = await agente.responder(chat_id, texto, imagem=imagem, emergencia_avisada=emergencia)
    except ErroLLM as e:
        resposta = mensagem_erro_ia(e)
    await enviar_texto(update, resposta)
    if em_audio or quer_audio(chat_id):
        await enviar_audio(update, context, resposta)


def mensagem_erro_ia(e: ErroLLM) -> str:
    log.error("Erro da IA (%s): %s", e.tipo, e)
    motivo = {
        "autenticacao": "problema de configuração (chave da IA)",
        "limite": "limite de uso da IA atingido por agora",
        "modelo": "modelo de IA não encontrado (confira o nome no .env)",
        "conexao": "sem conexão com o serviço de IA",
    }.get(e.tipo, "serviço de IA indisponível")
    return f"Não consegui responder agora: {motivo}. Tente de novo em instantes. Em emergência, ligue 193."


# ------------------------------------------------------------------ comandos
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    teclado = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Enviar minha localização", request_location=True)]],
        resize_keyboard=True, one_time_keyboard=True,
    )
    await update.message.reply_text(BOAS_VINDAS, reply_markup=teclado)


async def cmd_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(AJUDA)


async def cmd_privacidade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(PRIVACIDADE)


async def cmd_comunidade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    botoes = [[InlineKeyboardButton(c["nome"], callback_data=f"com:{i}")] for i, c in enumerate(COMUNIDADES)]
    await update.message.reply_text("Escolha a sua comunidade:", reply_markup=InlineKeyboardMarkup(botoes))


async def escolher_comunidade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    c = COMUNIDADES[int(q.data.split(":")[1])]
    estado.definir_local(q.message.chat.id, c["nome"], c["lat"], c["lon"])
    await q.edit_message_text(
        f"Pronto! Comunidade: {c['nome']}. Vou avisar quando houver foco de calor a até "
        f"{CONFIG.raio_alerta_km} km. Use /focos para ver agora ou /ajuda para mais opções."
    )


async def receber_localizacao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    loc = update.message.location
    # A localização enviada sempre fica guardada para o próximo relato (é onde a pessoa está vendo algo).
    agente.local_relato[chat_id] = (loc.latitude, loc.longitude)
    u = estado.usuario(chat_id)
    if u:
        await update.message.reply_text(
            "📍 Localização recebida para o relato. Pode continuar contando o que está vendo.\n"
            f"(Sua comunidade para alertas continua: {u['comunidade']}. Para mudar, use /comunidade.)",
            reply_markup=ReplyKeyboardRemove(),
        )
        return
    estado.definir_local(chat_id, "sua localização", loc.latitude, loc.longitude)
    await update.message.reply_text(
        f"Localização recebida! Vou avisar quando houver foco de calor a até {CONFIG.raio_alerta_km} km daí. "
        "Use /focos para ver agora.",
        reply_markup=ReplyKeyboardRemove(),
    )


async def cmd_focos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await perguntar_ao_agente(update, context, "Tem foco de calor perto da minha comunidade nas últimas 24 horas?")


async def cmd_tempo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await perguntar_ao_agente(update, context, "Como está o tempo hoje aqui? O fogo se espalha fácil?")


async def cmd_checar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Recebeu um áudio ou mensagem dizendo que tem fogo ou fumaça perto? Encaminhe aqui "
        "(segure a mensagem → Encaminhar → escolha o FogoAlerta). Eu comparo com os dados de satélite "
        "e do tempo de agora e digo de quando é a mensagem original."
    )


async def cmd_ar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await perguntar_ao_agente(update, context, "Como está o ar hoje aqui? A fumaça faz mal? Que cuidados tomar?")


async def cmd_relato(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    teclado = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Enviar onde estou vendo", request_location=True)]],
        resize_keyboard=True, one_time_keyboard=True,
    )
    await update.message.reply_text(
        "Conte o que você está vendo: o que é (fogo, fumaça, área queimada, árvores derrubadas), "
        "onde fica e desde quando. Pode mandar foto ou áudio, e o botão abaixo envia a localização. "
        "O relato é anônimo, a não ser que você peça para se identificar.\n\n"
        "Se for fogo ativo perto de pessoas, ligue 193 primeiro.",
        reply_markup=teclado,
    )


async def cmd_boletim(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not estado.usuario(update.effective_chat.id):
        await update.message.reply_text("Primeiro escolha a comunidade com /comunidade.")
        return
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    try:
        boletim = await agente.boletim_radio(update.effective_chat.id)
    except ErroLLM as e:
        await enviar_texto(update, mensagem_erro_ia(e))
        return
    await enviar_texto(update, "📻 Boletim para a rádio:\n\n" + boletim)
    # Versão em áudio: a rádio comunitária pode tocar direto.
    await enviar_audio(update, context, boletim, legenda="📻 Boletim em áudio (voz gerada por computador)")


async def cmd_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ligar = update.message.text.startswith("/audio_on")
    if ligar and not voz.disponivel():
        await update.message.reply_text("A resposta em áudio não está instalada neste computador (pip install edge-tts).")
        return
    estado.definir_preferencia(update.effective_chat.id, "audio", ligar)
    await update.message.reply_text(
        "🔊 Pronto! Vou responder também em áudio." if ligar
        else "Áudio desligado. Vou responder só por escrito (se você mandar áudio, respondo em áudio)."
    )


async def cmd_alertas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ligar = update.message.text.startswith("/alertas_on")
    if not estado.usuario(update.effective_chat.id):
        await update.message.reply_text("Primeiro escolha a comunidade com /comunidade.")
        return
    estado.ativar_alertas(update.effective_chat.id, ligar)
    await update.message.reply_text("Alertas ligados ✅" if ligar else "Alertas desligados. Use /alertas_on para ligar.")


async def cmd_versao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"FogoAlerta versão {VERSAO}\nIA: {agente.provedor.nome} ({agente.provedor.modelo})\n"
        f"Modo demonstração: {'LIGADO (focos simulados)' if CONFIG.modo_demo else 'desligado (dados reais do FIRMS)'}"
    )


async def cmd_limpar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    agente.limpar_conversa(update.effective_chat.id)
    await update.message.reply_text("Conversa reiniciada.")


# ------------------------------------------------------------------ mensagens
async def receber_texto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    texto = prefixo_encaminhada(update) + update.message.text
    citada = update.message.reply_to_message
    # Se a pessoa "respondeu" a uma mensagem do bot, a IA recebe o trecho citado junto.
    if citada and citada.from_user and citada.from_user.is_bot and citada.text:
        texto = f"[Respondendo a esta mensagem do FogoAlerta: \"{citada.text[:600]}\"]\n{texto}"
    await perguntar_ao_agente(update, context, texto)


async def receber_foto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    foto = update.message.photo[-1]  # maior resolução
    arquivo = await foto.get_file()
    PASTA_FOTOS.mkdir(parents=True, exist_ok=True)
    caminho = PASTA_FOTOS / f"{datetime.now():%Y%m%d_%H%M%S}_{foto.file_unique_id}.jpg"
    await arquivo.download_to_drive(caminho)
    agente.fotos_pendentes.setdefault(chat_id, []).append(str(caminho))
    if prefixo_encaminhada(update):
        legenda = prefixo_encaminhada(update) + (update.message.caption or "Recebi esta imagem. Ela mostra algo perto daqui?")
    else:
        legenda = update.message.caption or "Enviei esta foto. O que dá para ver? Quero registrar um relato."
    await perguntar_ao_agente(update, context, legenda, imagem=(caminho.read_bytes(), "image/jpeg"))


async def receber_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not audio.disponivel():
        await update.message.reply_text("Ainda não consigo ouvir áudio neste protótipo. Pode escrever, por favor?")
        return
    voz = update.message.voice or update.message.audio
    arquivo = await voz.get_file()
    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / "audio.ogg"
        await arquivo.download_to_drive(caminho)
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        texto = await asyncio.to_thread(audio.transcrever, str(caminho))
    if not texto:
        await update.message.reply_text("Não entendi o áudio. Pode repetir ou escrever?")
        return
    await update.message.reply_text(f"🎙️ Entendi: \"{texto}\"")
    # Quem fala em áudio recebe a resposta em áudio também.
    await perguntar_ao_agente(update, context, prefixo_encaminhada(update) + texto, em_audio=True)


# ------------------------------------------------------------------ alertas
async def tarefa_alertas(context: ContextTypes.DEFAULT_TYPE) -> None:
    async def enviar(chat_id: int, texto: str) -> None:
        await context.bot.send_message(chat_id, texto)
        agente.registrar_alerta_enviado(chat_id, texto)  # a IA passa a saber do alerta
    try:
        n = await alertas.verificar(estado, enviar)
        if n:
            log.info("Alertas enviados: %s", n)
    except FirmsErro as e:
        log.error("FIRMS: %s", e)


async def erro(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Erro não tratado", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("Tive um problema aqui. Tente de novo. Em emergência, ligue 193.")


def main() -> None:
    chave_ia = ("ANTHROPIC_API_KEY", CONFIG.anthropic_api_key) if CONFIG.llm_provedor == "claude" \
        else ("GEMINI_API_KEY", CONFIG.gemini_api_key)
    faltando = [n for n, v in (("TELEGRAM_TOKEN", CONFIG.telegram_token), chave_ia) if not v]
    if faltando:
        raise SystemExit(f"Configure no .env: {', '.join(faltando)}")

    global agente
    agente = Agente(estado=estado)
    app = Application.builder().token(CONFIG.telegram_token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler(["ajuda", "help"], cmd_ajuda))
    app.add_handler(CommandHandler("privacidade", cmd_privacidade))
    app.add_handler(CommandHandler("comunidade", cmd_comunidade))
    app.add_handler(CommandHandler("focos", cmd_focos))
    app.add_handler(CommandHandler("tempo", cmd_tempo))
    app.add_handler(CommandHandler("ar", cmd_ar))
    app.add_handler(CommandHandler("checar", cmd_checar))
    app.add_handler(CommandHandler("relato", cmd_relato))
    app.add_handler(CommandHandler("boletim", cmd_boletim))
    app.add_handler(CommandHandler(["alertas_on", "alertas_off"], cmd_alertas))
    app.add_handler(CommandHandler(["audio_on", "audio_off"], cmd_audio))
    app.add_handler(CommandHandler("limpar", cmd_limpar))
    app.add_handler(CommandHandler("versao", cmd_versao))
    app.add_handler(CallbackQueryHandler(escolher_comunidade, pattern=r"^com:\d+$"))
    app.add_handler(MessageHandler(filters.LOCATION, receber_localizacao))
    app.add_handler(MessageHandler(filters.PHOTO, receber_foto))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, receber_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receber_texto))
    app.add_error_handler(erro)

    if CONFIG.modo_demo:
        log.warning("MODO_DEMO=1: usando focos SIMULADOS (data/demo_focos.csv).")
    if CONFIG.firms_map_key or CONFIG.modo_demo:
        app.job_queue.run_repeating(tarefa_alertas, interval=CONFIG.intervalo_alerta_min * 60, first=30)
    else:
        log.warning("FIRMS_MAP_KEY ausente: alertas automáticos desligados.")
    if not audio.disponivel():
        log.info("faster-whisper não instalado: o bot não entende áudio recebido (opcional).")
    if not voz.disponivel():
        log.info("edge-tts não instalado: respostas só em texto (pip install edge-tts).")

    log.info("FogoAlerta versão %s rodando com %s (%s). Modo demo: %s. Ctrl+C para parar.",
             VERSAO, agente.provedor.nome, agente.provedor.modelo, "LIGADO" if CONFIG.modo_demo else "desligado")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

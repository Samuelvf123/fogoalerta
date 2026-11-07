"""Testes sem internet: geo, FIRMS (CSV de exemplo), tempo, guardrails, base, relatos, alertas."""
import json

import pytest

from fogoalerta import alertas, clima, firms, geo, guardrails, relatos
from fogoalerta.armazenamento import Estado
from fogoalerta.conhecimento import BaseConhecimento

AUTAZES = (-3.5797, -59.1306)

CSV_VIIRS = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight
-3.6000,-59.1000,340.1,0.4,0.4,2026-11-04,0542,N,VIIRS,n,2.0NRT,290.2,5.3,N
-3.6005,-59.1002,338.0,0.4,0.4,2026-11-04,0542,N,VIIRS,h,2.0NRT,291.0,7.1,N
-3.9000,-59.5000,350.0,0.4,0.4,2026-11-04,1730,N,VIIRS,h,2.0NRT,300.0,20.0,D
linha,quebrada
"""


# ---------------------------------------------------------------- geo
def test_distancia_conhecida():
    # 1 grau de latitude ~ 111 km
    assert geo.distancia_km(0, 0, 1, 0) == pytest.approx(111.2, abs=0.5)


def test_direcao():
    assert geo.direcao(0, 0, 1, 0) == "norte"
    assert geo.direcao(0, 0, -1, 1) == "sudeste"
    assert geo.direcao(0, 0, 0, -1) == "oeste"


def test_caixa_contem_ponto():
    o, s, l, n = geo.caixa_ao_redor(*AUTAZES, 10)
    assert o < AUTAZES[1] < l and s < AUTAZES[0] < n


# ---------------------------------------------------------------- FIRMS
def test_ler_csv_ignora_linha_quebrada():
    focos = firms.ler_csv(CSV_VIIRS, "VIIRS_NOAA20_NRT")
    assert len(focos) == 3
    assert focos[0].confianca == "nominal" and focos[1].confianca == "alta"
    # 05h42 UTC = 01h42 em Manaus
    assert focos[0].data_hora_local.strftime("%H:%M") == "01:42"


def test_ler_csv_erro_de_chave():
    with pytest.raises(firms.FirmsErro):
        firms.ler_csv("Invalid MAP_KEY.", "VIIRS_SNPP_NRT")


def test_confianca_modis():
    assert firms._confianca("15") == "baixa"
    assert firms._confianca("50") == "nominal"
    assert firms._confianca("95") == "alta"


def test_filtrar_proximos_raio_e_duplicados():
    focos = firms.ler_csv(CSV_VIIRS, "VIIRS_NOAA20_NRT")
    perto = firms.filtrar_proximos(focos, *AUTAZES, raio_km=10)
    # os dois primeiros são o mesmo fogo (a ~50 m): vira um só; o terceiro está a ~60 km
    assert len(perto) == 1
    assert perto[0]["distancia_km"] < 5
    assert perto[0]["direcao"] in ("sudeste", "leste")
    assert firms.filtrar_proximos(focos, *AUTAZES, raio_km=100)[-1]["distancia_km"] > 50


# ---------------------------------------------------------------- tempo
def test_resumo_tempo_risco_alto():
    dados = {"daily": {
        "time": [f"d{i}" for i in range(18)],
        "precipitation_sum": [5.0] + [0.0] * 14 + [0.0, 2.0, 0.0],
        "temperature_2m_max": [30] * 14 + [37, 36, 35, 34],
        "wind_speed_10m_max": [10] * 14 + [22, 10, 10, 10],
    }, "_indice_hoje": 14}
    r = clima.resumir(dados)
    assert r["dias_seguidos_sem_chuva"] == 14
    assert r["nivel_risco_estimado"] == "alto"
    assert r["chuva_prevista_proximos_3_dias_mm"] == 2.0


# ---------------------------------------------------------------- guardrails
@pytest.mark.parametrize("texto", [
    "Socorro, tá pegando fogo aqui perto de casa",
    "o fogo está chegando na roça",
    "INCÊNDIO na comunidade",
    "não consigo respirar com essa fumaça",
    "socorro, tem fogo perto da minha casa?",   # pergunta, mas com palavra forte
    "o fogo tá perto da escola",
    "fumaça forte aqui na comunidade",
])
def test_detecta_emergencia(texto):
    assert guardrails.detectar_emergencia(texto)


@pytest.mark.parametrize("texto", [
    "como se chama o órgão ambiental?",
    "posso limpar meu roçado sem fogo?",
    "tem foco perto?",
    "tem fogo perto?",            # achado no teste do Telegram: pergunta, não socorro
    "Tem fogo perto da comunidade",
    "o que fazer se tiver fumaça forte?",
])
def test_nao_dispara_emergencia_a_toa(texto):
    assert not guardrails.detectar_emergencia(texto)


@pytest.mark.parametrize("resposta", [
    "Pode queimar sim, hoje o tempo está bom.",
    "Está liberado queimar depois das 17h.",
    "Eu autorizo a queimada.",
])
def test_bloqueia_autorizacao_de_queima(resposta):
    assert guardrails.revisar_saida(resposta, usou_focos=False) == guardrails.RESPOSTA_SEM_AUTORIZACAO


@pytest.mark.parametrize("resposta", [
    "Não pode queimar agora: o uso do fogo está proibido no estado.",
    "Ninguém pode queimar durante a proibição.",
])
def test_nao_bloqueia_resposta_correta(resposta):
    assert guardrails.revisar_saida(resposta, usou_focos=False) == resposta


def test_acrescenta_aviso_de_foco():
    r = guardrails.revisar_saida("Há 2 focos a 5 km.", usou_focos=True)
    assert guardrails.AVISO_FOCO in r
    ok = "Há 2 focos a 5 km, vistos por satélite. Isso não confirma incêndio."
    assert guardrails.revisar_saida(ok, usou_focos=True) == ok


def test_entrada_longa_cortada():
    assert len(guardrails.limpar_entrada("a" * 5000)) == guardrails.LIMITE_ENTRADA


# ---------------------------------------------------------------- base de orientações
def test_busca_encontra_proibicao():
    base = BaseConhecimento()
    assert len(base.trechos) >= 10
    r = base.buscar("posso queimar meu roçado agora? é proibido?")
    assert any(x["tema"].startswith("Proibição do uso do fogo") for x in r)


def test_busca_encontra_alternativa_pasto():
    r = BaseConhecimento().buscar("como limpar o pasto sem queimar")
    assert r[0]["tema"] == "Pasto sem fogo"


def test_busca_encontra_fumaca():
    r = BaseConhecimento().buscar("falta de ar por causa da fumaça")
    assert any("Fumaça" in x["tema"] for x in r)


# ---------------------------------------------------------------- relatos
def test_relato_anonimo_e_canal(tmp_path):
    r = relatos.registrar("fogo_ativo", "Fogo no ramal perto da escola", comunidade="Autazes (sede)",
                          lat=AUTAZES[0], lon=AUTAZES[1], anonimo=True, contato="9999-9999",
                          pasta=tmp_path)
    assert r["protocolo"].startswith("FA-")
    assert r["encaminhar_para"][0]["contato"] == "193"
    salvo = json.loads((tmp_path / "relatos.jsonl").read_text(encoding="utf-8").strip())
    assert salvo["contato"] is None  # anônimo: não guarda contato
    assert "anônimo" in r["texto_para_encaminhar"]


def test_relato_tipo_invalido_vira_outro(tmp_path):
    r = relatos.registrar("qualquer", "teste", pasta=tmp_path)
    assert "Defesa Civil" in r["encaminhar_para"][0]["orgao"]


# ---------------------------------------------------------------- alertas
async def test_alerta_envia_uma_vez(tmp_path):
    estado = Estado(tmp_path / "estado.json")
    estado.definir_local(42, "Autazes (sede)", *AUTAZES)
    focos = firms.filtrar_proximos(firms.ler_csv(CSV_VIIRS, "X"), *AUTAZES, 10)

    async def buscar(*_):
        return focos

    enviados = []

    async def enviar(chat_id, texto):
        enviados.append((chat_id, texto))

    async def tempo(*_):
        return {"vento_agora": {"de_graus": 135, "kmh": 15}}  # vem do sudeste, onde está o foco

    assert await alertas.verificar(estado, enviar, buscar, tempo) == 1
    assert "193" in enviados[0][1] and "satélite" in enviados[0][1]
    assert "⚠️ vento soprando na direção da comunidade" in enviados[0][1]
    assert "vento vindo do sudeste para o noroeste" in enviados[0][1]
    assert "." not in enviados[0][1].split("\n")[1].split(" km")[0]  # distância com vírgula
    assert await alertas.verificar(estado, enviar, buscar, tempo) == 0  # mesmo foco não repete
    estado.ativar_alertas(42, False)
    estado.dados["alertados"] = {}
    assert await alertas.verificar(estado, enviar, buscar, tempo) == 0  # alertas desligados


# ---------------------------------------------------------------- modo demonstração
def test_focos_demo_perto_de_autazes():
    perto = firms.filtrar_proximos(firms.focos_demo(*AUTAZES), *AUTAZES, 10)
    assert 2 <= len(perto) <= 4  # os 2 primeiros pontos são o mesmo fogo
    assert all(p["id"].startswith("SIMULADO") for p in perto)


# ---------------------------------------------------------------- formatação para o Telegram
from fogoalerta.formatacao import para_html, sem_markdown  # noqa: E402


def test_markdown_vira_html_do_telegram():
    t = "Ligue **193** agora.\n* item um\n```\nRELATO FA-1\nTipo: <fogo>\n```\nUse `/focos`."
    h = para_html(t)
    assert "<b>193</b>" in h and "• item um" in h
    assert "<pre>RELATO FA-1\nTipo: &lt;fogo&gt;</pre>" in h  # escapa < > dentro do bloco
    assert "<code>/focos</code>" in h and "**" not in h and "```" not in h


def test_texto_puro_de_reserva():
    assert sem_markdown("**Oi** ```\nx\n```") == "Oi x"


# ---------------------------------------------------------------- local do relato
def test_relato_diferencia_local_enviado_e_referencia(tmp_path):
    enviado = relatos.registrar("fogo_ativo", "fogo", lat=-3.6, lon=-59.1, origem_local="enviada", pasta=tmp_path)
    ref = relatos.registrar("fogo_ativo", "fogo", lat=-3.58, lon=-59.13, origem_local="comunidade", pasta=tmp_path)
    assert "Localização enviada pela pessoa" in enviado["texto_para_encaminhar"]
    assert "NÃO é a posição exata" in ref["texto_para_encaminhar"]


def test_relato_com_local_enviado_omite_comunidade(tmp_path):
    r = relatos.registrar("fogo_ativo", "fogo", comunidade="Autazes (sede)", lat=-3.1, lon=-60.0,
                          origem_local="enviada", pasta=tmp_path)
    assert "Autazes" not in r["texto_para_encaminhar"]
    r2 = relatos.registrar("fogo_ativo", "fogo", comunidade="Autazes (sede)", lat=-3.58, lon=-59.13,
                           origem_local="comunidade", pasta=tmp_path)
    assert "Comunidade de referência: Autazes (sede)" in r2["texto_para_encaminhar"]


def test_tempo_em_portugues_com_virgula():
    dados = {"daily": {
        "time": [f"d{i}" for i in range(18)],
        "precipitation_sum": [0.0] * 15 + [0.5, 1.0, 0.0],
        "temperature_2m_max": [32.0] * 18,
        "wind_speed_10m_max": [8.4] * 18,
    }, "_indice_hoje": 14}
    r = clima.resumir(dados)["resumo_em_portugues"]
    assert "1,5 mm de chuva nos próximos 3 dias" in r and "máxima de 32 graus" in r
    assert "1.5" not in r



# ---------------------------------------------------------------- propagação pelo vento
from fogoalerta import propagacao  # noqa: E402


@pytest.mark.parametrize("vento_de, foco, esperado", [
    (90, (0.0, 0.05), "a_favor"),     # vento vem do leste; foco a leste -> vento traz o fogo
    (90, (0.0, -0.05), "contra"),     # foco a oeste -> vento leva para longe
    (90, (0.05, 0.0), "de_lado"),     # foco ao norte -> vento de lado
    (45, (0.04, 0.04), "a_favor"),    # vento do nordeste; foco a nordeste
])
def test_avaliar_vento(vento_de, foco, esperado):
    r = propagacao.avaliar(0.0, 0.0, foco[0], foco[1], {"de_graus": vento_de, "kmh": 15})
    assert r["situacao"] == esperado


def test_vento_fraco_e_sem_dado():
    assert propagacao.avaliar(0, 0, 0, 0.05, {"de_graus": 90, "kmh": 2})["situacao"] == "vento_fraco"
    assert propagacao.avaliar(0, 0, 0, 0.05, None)["situacao"] == "sem_dado"


def test_anotar_prioriza_foco_com_vento_a_favor():
    focos = [
        {"id": "perto_contra", "lat": 0.0, "lon": -0.02, "distancia_km": 2.2},
        {"id": "longe_a_favor", "lat": 0.0, "lon": 0.07, "distancia_km": 7.8},
    ]
    r = propagacao.anotar(focos, 0.0, 0.0, {"de_graus": 90, "kmh": 15})
    assert [f["id"] for f in r] == ["longe_a_favor", "perto_contra"]


def test_tempo_traz_vento_atual():
    dados = {"daily": {
        "time": [f"d{i}" for i in range(18)],
        "precipitation_sum": [0.0] * 18,
        "temperature_2m_max": [33.0] * 18,
        "wind_speed_10m_max": [10.0] * 18,
        "wind_direction_10m_dominant": [80] * 18,
    }, "current": {"wind_speed_10m": 14.0, "wind_direction_10m": 95}, "_indice_hoje": 14}
    r = clima.resumir(dados)
    assert r["vento_agora"] == {"de_graus": 95, "kmh": 14.0}
    assert "vento vindo do leste para o oeste" in r["resumo_em_portugues"]
    del dados["current"]  # sem "current": usa a direção predominante do dia
    assert clima.resumir(dados)["vento_agora"] == {"de_graus": 80, "kmh": 10.0}


# ---------------------------------------------------------------- qualidade do ar
from fogoalerta import ar  # noqa: E402


@pytest.mark.parametrize("pm, esperado", [(8, "Boa"), (15, "Boa"), (15.1, "Moderada"), (60, "Ruim"),
                                          (100, "Muito ruim"), (200, "Péssima")])
def test_classificar_iqar(pm, esperado):
    assert ar.classificar(pm)[0] == esperado


def test_ar_media_24h_ate_agora():
    horas = [f"2026-11-06T{h:02d}:00" for h in range(24)] + [f"2026-11-07T{h:02d}:00" for h in range(24)]
    valores = [10.0] * 24 + [70.0] * 24  # ontem limpo, hoje fumaça
    dados = {"current": {"time": "2026-11-07T11:00", "pm2_5": 80.0},
             "hourly": {"time": horas, "pm2_5": valores}}
    r = ar.resumir(dados)
    # últimas 24 h até 11h de hoje: 12 h de ontem (10) + 12 h de hoje (70) = média 40 -> Moderada
    assert r["pm2_5_media_24h"] == 40.0 and r["qualidade"] == "Moderada"
    assert "agora: 80 µg/m³" in r["resumo_em_portugues"] and "modelo" in r["fonte"]


def test_ar_sem_dado():
    assert "erro" in ar.resumir({"current": {}, "hourly": {}})


# ---------------------------------------------------------------- mensagens encaminhadas (boatos)
from datetime import datetime, timezone  # noqa: E402

from fogoalerta import encaminhada  # noqa: E402


def test_prefixo_encaminhada_com_data_antiga():
    agora = datetime(2026, 11, 7, 10, 0, tzinfo=encaminhada.FUSO)
    original = datetime(2026, 11, 4, 18, 30, tzinfo=timezone.utc)  # 14h30 em Manaus
    p = encaminhada.prefixo(original, agora)
    assert "ENCAMINHOU" in p and "04/11 às 14h30" in p and "há 2 dias" in p


def test_ha_quanto_tempo():
    agora = datetime(2026, 11, 7, 10, 0, tzinfo=encaminhada.FUSO)
    assert encaminhada.ha_quanto_tempo(datetime(2026, 11, 7, 9, 30, tzinfo=encaminhada.FUSO), agora) == "há menos de 1 hora"
    assert encaminhada.ha_quanto_tempo(datetime(2026, 11, 7, 7, 0, tzinfo=encaminhada.FUSO), agora) == "há 3 horas"
    assert encaminhada.prefixo(None, agora).count("data original desconhecida") == 1


# ---------------------------------------------------------------- voz (texto -> áudio)
from fogoalerta import voz  # noqa: E402


def test_preparar_texto_para_fala():
    t = ("🧪 SIMULAÇÃO: **3 focos** a 4,3 km.\n• Ligue **193**.\nVento de 12 km/h, chuva de 1,5 mm, "
         "PM2,5 de 40 µg/m³. Veja https://maps.google.com/?q=1,2\n```\nRELATO FA-1\nTipo: Fogo\n```")
    f = voz.preparar_texto(t)
    assert "um nove três" in f and "quilômetros por hora" in f and "4,3 quilômetros" in f
    assert "1,5 milímetros" in f and "PM dois vírgula cinco" in f and "microgramas" in f
    assert "**" not in f and "http" not in f and "🧪" not in f and "RELATO FA-1" not in f
    assert "mensagem escrita" in f


def test_texto_longo_e_cortado():
    f = voz.preparar_texto("Frase de teste com várias palavras. " * 80)
    assert len(f) < voz.LIMITE + 60 and f.endswith("Os detalhes estão na mensagem escrita.")


def test_preferencia_de_audio(tmp_path):
    estado = Estado(tmp_path / "e.json")
    assert estado.preferencia(5, "audio", False) is False
    estado.definir_preferencia(5, "audio", True)
    assert Estado(tmp_path / "e.json").preferencia(5, "audio") is True  # persiste em arquivo


def test_foco_simulado_nao_repete_alerta_a_cada_hora():
    from datetime import timedelta
    f = firms.focos_demo(*AUTAZES)[0]
    uma_hora_depois = firms.Foco(f.lat, f.lon, f.data_hora_utc.replace(minute=0) + timedelta(minutes=1),
                                 f.satelite, f.instrumento, f.confianca, f.frp, f.fonte)
    if uma_hora_depois.data_hora_local.date() == f.data_hora_local.date():
        assert uma_hora_depois.id == f.id
    real = firms.Foco(f.lat, f.lon, f.data_hora_utc, "N", "VIIRS", "alta", 1.0, "VIIRS_SNPP_NRT")
    assert real.id.endswith(f"{f.data_hora_utc:%Y%m%d%H%M}")  # foco real continua com horário exato

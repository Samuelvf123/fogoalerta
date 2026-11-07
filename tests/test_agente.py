"""Testa o agente e os dois provedores (Gemini e Claude) com respostas falsas: sem internet e sem custo."""
import json
from types import SimpleNamespace as NS

import pytest
from google.genai import types

from fogoalerta.agente import FERRAMENTAS, Agente
from fogoalerta.armazenamento import Estado
from fogoalerta.guardrails import AVISO_FOCO, RESPOSTA_SEM_AUTORIZACAO
from fogoalerta.llm import Chamada, ClaudeProvedor, GeminiProvedor, Passo


# ------------------------------------------------------------ provedor falso
class ProvedorFalso:
    """Devolve Passos pré-programados e guarda o que recebeu."""
    nome, modelo = "falso", "teste"

    def __init__(self, roteiro):
        self.roteiro = list(roteiro)
        self.resultados = []

    def nova_conversa(self, historico, texto, imagem):
        return list(historico) + [{"role": "user", "content": texto, "imagem": imagem}]

    async def gerar(self, sistema, conversa, ferramentas):
        self.ultimo_sistema = sistema
        return self.roteiro.pop(0)

    def adicionar_resultados(self, conversa, chamadas, resultados):
        self.resultados.append(resultados)


def texto(t):
    return Passo(texto=t)


def ferramenta(nome, args, id_="t1"):
    return Passo(texto="", chamadas=[Chamada(id=id_, nome=nome, args=args)])


async def focos_falsos(lat, lon, raio, dias):
    # foco a sudeste da comunidade (-3.58, -59.13)
    return [{"id": "x", "distancia_km": 4.2, "direcao": "sudeste", "detectado_em": "04/11 às 01h42",
             "lat": -3.61, "lon": -59.10,
             "confianca": "alta", "intensidade_frp_mw": 7.1, "satelite": "VIIRS N"}]


async def tempo_falso(lat, lon):
    # vento vindo do sudeste (135°): sopra do foco em direção à comunidade
    return {"temperatura_max_hoje_c": 37, "nivel_risco_estimado": "alto", "vento_agora": {"de_graus": 135, "kmh": 15}}


def novo_agente(tmp_path, roteiro, com_local=True):
    estado = Estado(tmp_path / "estado.json")
    if com_local:
        estado.definir_local(7, "Autazes (sede)", -3.58, -59.13)
    prov = ProvedorFalso(roteiro)
    return Agente(provedor=prov, estado=estado, buscar_focos=focos_falsos, buscar_tempo=tempo_falso), prov


# ------------------------------------------------------------ agente
async def test_usa_ferramenta_de_focos_e_poe_aviso(tmp_path):
    agente, prov = novo_agente(tmp_path, [
        ferramenta("consultar_focos", {"raio_km": 10}),
        texto("Tem 1 foco a 4,2 km a sudeste, detectado hoje à 01h42."),
    ])
    r = await agente.responder(7, "tem fogo perto?")
    assert "4,2 km" in r and AVISO_FOCO in r  # guardrail acrescentou o aviso
    resultado = prov.resultados[0][0]
    assert resultado["focos"][0]["direcao"] == "sudeste"
    assert resultado["focos"][0]["vento"]["situacao"] == "a_favor"   # análise de propagação
    assert "sudeste" in resultado["vento_agora"] and "estimativa simples" in resultado["aviso_vento"].lower()
    assert "Autazes" in prov.ultimo_sistema  # contexto da comunidade vai no prompt


async def test_sem_comunidade_ferramenta_devolve_erro(tmp_path):
    agente, prov = novo_agente(tmp_path, [ferramenta("consultar_focos", {}), texto("Use /comunidade.")],
                               com_local=False)
    await agente.responder(7, "tem fogo perto?")
    assert "não cadastrada" in prov.resultados[0][0]["erro"]


async def test_bloqueia_ia_que_autoriza_queima(tmp_path):
    agente, _ = novo_agente(tmp_path, [texto("Pode queimar sim, o tempo está ótimo!")])
    assert await agente.responder(7, "posso queimar hoje?") == RESPOSTA_SEM_AUTORIZACAO


async def test_relato_usa_foto_pendente_e_e_anonimo(tmp_path, monkeypatch):
    import fogoalerta.relatos as rel
    salvos = {}

    def registrar_falso(**kw):
        salvos.update(kw)
        return {"protocolo": "FA-TESTE", "encaminhar_para": [{"orgao": "CBMAM", "contato": "193"}]}

    monkeypatch.setattr(rel, "registrar", registrar_falso)
    agente, _ = novo_agente(tmp_path, [
        ferramenta("registrar_relato", {"tipo": "fogo_ativo", "descricao": "fumaça no ramal"}),
        texto("Relato FA-TESTE registrado. Ligue 193."),
    ])
    agente.fotos_pendentes[7] = ["foto1.jpg"]
    await agente.responder(7, "registra aí, por favor")
    assert salvos["fotos"] == ["foto1.jpg"] and salvos["anonimo"] is True
    assert 7 not in agente.fotos_pendentes


async def test_falha_na_ferramenta_nao_derruba(tmp_path):
    async def quebrado(*_):
        raise TimeoutError("FIRMS fora do ar")

    agente, prov = novo_agente(tmp_path, [ferramenta("consultar_focos", {}), texto("Dado indisponível agora.")])
    agente.buscar_focos = quebrado
    assert "indisponível" in await agente.responder(7, "tem foco?")
    assert "erro" in prov.resultados[0][0]


async def test_historico_guarda_so_texto_e_limita(tmp_path):
    agente, _ = novo_agente(tmp_path, [texto(f"resposta {i}") for i in range(8)])
    for i in range(8):
        await agente.responder(7, f"pergunta {i}")
    h = agente.historico[7]
    assert len(h) == 10 and h[0]["role"] == "user"
    assert all(isinstance(m["content"], str) for m in h)


async def test_para_depois_de_muitos_passos(tmp_path):
    agente, _ = novo_agente(tmp_path, [ferramenta("consultar_tempo", {}, id_=f"t{i}") for i in range(6)])
    assert "demorei" in await agente.responder(7, "?")


# ------------------------------------------------------------ provedor Gemini (conversão de formatos)
class GeminiFalso:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.pedidos = []
        self.aio = NS(models=self)

    async def generate_content(self, model, contents, config):
        self.pedidos.append({"model": model, "contents": list(contents), "config": config})
        return self.respostas.pop(0)


def resposta_gemini(*partes):
    return types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(role="model", parts=list(partes)))])


async def test_gemini_chamada_de_ferramenta_e_resultado():
    cliente = GeminiFalso([resposta_gemini(
        types.Part(text="pensando...", thought=True),
        types.Part(function_call=types.FunctionCall(name="consultar_focos", args={"raio_km": 10})),
    )])
    prov = GeminiProvedor(cliente=cliente, modelo="gemini-teste")
    conversa = prov.nova_conversa([{"role": "user", "content": "oi"}, {"role": "assistant", "content": "olá"}],
                                  "tem foco?", (b"\xff\xd8jpeg", "image/jpeg"))
    assert [c.role for c in conversa] == ["user", "model", "user"]
    assert conversa[-1].parts[0].inline_data.mime_type == "image/jpeg"

    passo = await prov.gerar("sistema", conversa, FERRAMENTAS)
    assert passo.texto == ""  # o "pensamento" não vira resposta
    assert passo.chamadas[0].nome == "consultar_focos" and passo.chamadas[0].args == {"raio_km": 10}
    cfg = cliente.pedidos[0]["config"]
    nomes = [d.name for d in cfg.tools[0].function_declarations]
    assert nomes == [f["name"] for f in FERRAMENTAS]
    assert cfg.automatic_function_calling.disable is True

    prov.adicionar_resultados(conversa, passo.chamadas, [{"total": 1}])
    assert conversa[-2].role == "model"  # resposta original preservada (assinaturas de pensamento)
    fr = conversa[-1].parts[0].function_response
    assert fr.name == "consultar_focos" and fr.response == {"total": 1}


async def test_gemini_texto_final():
    prov = GeminiProvedor(cliente=GeminiFalso([resposta_gemini(types.Part(text="Nenhum foco hoje."))]), modelo="x")
    passo = await prov.gerar("s", prov.nova_conversa([], "?", None), FERRAMENTAS)
    assert passo.texto == "Nenhum foco hoje." and passo.chamadas == []


# ------------------------------------------------------------ provedor Claude (conversão de formatos)
class ClaudeFalso:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.pedidos = []
        self.messages = self

    async def create(self, **kw):
        self.pedidos.append(json.loads(json.dumps(kw, default=str)))
        return self.respostas.pop(0)


async def test_claude_chamada_de_ferramenta_e_resultado():
    cliente = ClaudeFalso([NS(stop_reason="tool_use", content=[
        NS(type="text", text="Vou ver."),
        NS(type="tool_use", id="tu1", name="consultar_tempo", input={}),
    ])])
    prov = ClaudeProvedor(cliente=cliente, modelo="claude-teste")
    conversa = prov.nova_conversa([], "e o tempo?", (b"img", "image/jpeg"))
    assert conversa[0]["content"][0]["type"] == "image"
    passo = await prov.gerar("s", conversa, FERRAMENTAS)
    assert passo.chamadas[0].id == "tu1"
    assert cliente.pedidos[0]["tools"][0]["input_schema"]["type"] == "object"
    prov.adicionar_resultados(conversa, passo.chamadas, [{"erro": "x"}])
    assert conversa[-1]["content"][0]["tool_use_id"] == "tu1" and conversa[-1]["content"][0]["is_error"]


@pytest.mark.parametrize("nome", ["gemini", "claude"])
def test_criar_provedor(nome, monkeypatch):
    from fogoalerta import llm
    monkeypatch.setattr(llm.GeminiProvedor, "__init__", lambda self: None)
    monkeypatch.setattr(llm.ClaudeProvedor, "__init__", lambda self: None)
    assert llm.criar_provedor(nome).nome == nome


# ------------------------------------------------------------ Gemini: nova tentativa e modelo reserva
from google.genai import errors as gerr  # noqa: E402

from fogoalerta.llm import ErroLLM  # noqa: E402


class GeminiInstavel(GeminiFalso):
    """Falha com os códigos dados (um por chamada) e depois responde normalmente."""

    def __init__(self, falhas, resposta):
        super().__init__([resposta])
        self.falhas = list(falhas)

    async def generate_content(self, model, contents, config):
        self.pedidos.append({"model": model})
        if self.falhas:
            codigo = self.falhas.pop(0)
            corpo = {"error": {"code": codigo, "message": "x", "status": "X"}}
            raise (gerr.ServerError if codigo >= 500 else gerr.ClientError)(codigo, corpo)
        return self.respostas.pop(0)


def provedor_instavel(falhas, reservas=("reserva-1",)):
    cliente = GeminiInstavel(falhas, resposta_gemini(types.Part(text="ok")))
    prov = GeminiProvedor(cliente=cliente, modelo="principal", reservas=reservas)

    async def sem_espera(_):
        return None

    prov._dormir = sem_espera
    return prov, cliente


async def test_gemini_tenta_de_novo_depois_de_503():
    prov, cliente = provedor_instavel([503])
    passo = await prov.gerar("s", prov.nova_conversa([], "?", None), FERRAMENTAS)
    assert passo.texto == "ok"
    assert [p["model"] for p in cliente.pedidos] == ["principal", "principal"]


async def test_gemini_usa_reserva_quando_principal_continua_ocupado():
    prov, cliente = provedor_instavel([503, 429])
    passo = await prov.gerar("s", prov.nova_conversa([], "?", None), FERRAMENTAS)
    assert passo.texto == "ok"
    assert [p["model"] for p in cliente.pedidos] == ["principal", "principal", "reserva-1"]


async def test_gemini_modelo_inexistente_pula_direto_para_reserva():
    prov, cliente = provedor_instavel([404])
    await prov.gerar("s", prov.nova_conversa([], "?", None), FERRAMENTAS)
    assert [p["model"] for p in cliente.pedidos] == ["principal", "reserva-1"]


async def test_gemini_chave_invalida_nao_insiste():
    prov, cliente = provedor_instavel([403])
    with pytest.raises(ErroLLM) as e:
        await prov.gerar("s", prov.nova_conversa([], "?", None), FERRAMENTAS)
    assert e.value.tipo == "autenticacao" and len(cliente.pedidos) == 1


async def test_gemini_todos_ocupados_devolve_erro():
    prov, cliente = provedor_instavel([503, 503, 503, 503])
    with pytest.raises(ErroLLM) as e:
        await prov.gerar("s", prov.nova_conversa([], "?", None), FERRAMENTAS)
    assert e.value.tipo == "indisponivel" and len(cliente.pedidos) == 4


async def test_relato_usa_localizacao_enviada_e_nao_a_sede(tmp_path, monkeypatch):
    import fogoalerta.relatos as rel
    salvos = {}
    monkeypatch.setattr(rel, "registrar", lambda **kw: salvos.update(kw) or {"protocolo": "FA-T"})
    agente, prov = novo_agente(tmp_path, [
        ferramenta("registrar_relato", {"tipo": "fogo_ativo", "descricao": "fogo"}), texto("ok"),
        ferramenta("registrar_relato", {"tipo": "fogo_ativo", "descricao": "fogo"}), texto("ok"),
    ])
    agente.local_relato[7] = (-3.61, -59.10)
    await agente.responder(7, "registra")
    assert "JÁ enviou a localização" in prov.ultimo_sistema
    assert (salvos["lat"], salvos["lon"], salvos["origem_local"]) == (-3.61, -59.10, "enviada")
    await agente.responder(7, "registra outro")  # sem nova localização: usa a sede, marcada como referência
    assert salvos["origem_local"] == "comunidade" and salvos["lat"] == -3.58


async def test_modo_demo_sempre_avisa_simulacao(tmp_path, monkeypatch):
    import fogoalerta.agente as ag
    monkeypatch.setattr(ag, "CONFIG", NS(**{**ag.CONFIG.__dict__, "modo_demo": True}))
    agente, _ = novo_agente(tmp_path, [
        ferramenta("consultar_focos", {}),
        texto("Satélites da NASA registraram 3 focos perto. Foco de satélite não confirma incêndio."),
    ])
    r = await agente.responder(7, "/boletim")
    assert r.startswith(ag.AVISO_SIMULACAO)


async def test_ia_sabe_do_ultimo_alerta(tmp_path):
    agente, prov = novo_agente(tmp_path, [texto("Sobre o alerta: fique atento e ligue 193 se vir fogo.")])
    agente.registrar_alerta_enviado(7, "🔥 ALERTA: 3 focos perto de Autazes")
    await agente.responder(7, "o que eu faço?")
    assert "ÚLTIMO ALERTA AUTOMÁTICO" in prov.ultimo_sistema and "3 focos" in prov.ultimo_sistema
    assert "período da" in prov.ultimo_sistema



async def test_focos_sem_vento_continuam_funcionando(tmp_path):
    async def tempo_quebrado(*_):
        raise TimeoutError("Open-Meteo fora do ar")

    agente, prov = novo_agente(tmp_path, [ferramenta("consultar_focos", {}), texto("1 foco a 4,2 km.")])
    agente.buscar_tempo = tempo_quebrado
    await agente.responder(7, "tem foco?")
    r = prov.resultados[0][0]
    assert r["total"] == 1 and r["focos"][0]["vento"]["situacao"] == "sem_dado"

"""Camada de provedor de IA: o agente funciona com Gemini (padrão) ou Claude.

Troque no .env:  LLM_PROVEDOR=gemini  ou  LLM_PROVEDOR=claude

Cada provedor sabe três coisas:
  - montar a conversa no formato dele (histórico + mensagem nova, com foto opcional);
  - chamar o modelo e devolver texto + chamadas de ferramenta;
  - anexar os resultados das ferramentas para a próxima rodada.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from typing import Any

from .config import CONFIG

log = logging.getLogger(__name__)
MAX_TOKENS = 2048  # inclui o "raciocínio" interno dos modelos que pensam antes de responder
TENTATIVAS_POR_MODELO = 2
ESPERA_SEGUNDOS = 2


@dataclass
class Chamada:
    id: str
    nome: str
    args: dict


@dataclass
class Passo:
    texto: str
    chamadas: list[Chamada] = field(default_factory=list)


class ErroLLM(RuntimeError):
    """Erro do provedor traduzido para um tipo simples: autenticacao | limite | modelo | indisponivel | conexao."""

    def __init__(self, tipo: str, detalhe: str = ""):
        super().__init__(f"{tipo}: {detalhe}")
        self.tipo = tipo


# ===================================================================== Gemini
class GeminiProvedor:
    nome = "gemini"

    def __init__(self, cliente: Any | None = None, modelo: str | None = None,
                 reservas: tuple[str, ...] | None = None):
        from google import genai
        from google.genai import types

        self.types = types
        self.modelo = modelo or CONFIG.gemini_modelo
        self.reservas = CONFIG.gemini_reservas if reservas is None else reservas
        self.cliente = cliente or genai.Client(api_key=CONFIG.gemini_api_key)
        self._dormir = asyncio.sleep

    def nova_conversa(self, historico: list[dict], texto: str, imagem: tuple[bytes, str] | None) -> list:
        t = self.types
        conversa = [
            t.Content(role="user" if m["role"] == "user" else "model", parts=[t.Part(text=m["content"])])
            for m in historico
        ]
        partes = [t.Part.from_bytes(data=imagem[0], mime_type=imagem[1])] if imagem else []
        partes.append(t.Part(text=texto))
        conversa.append(t.Content(role="user", parts=partes))
        return conversa

    def _ferramentas(self, ferramentas: list[dict]):
        t = self.types
        decls = []
        for f in ferramentas:
            kw = {"name": f["name"], "description": f["description"]}
            if f["schema"].get("properties"):
                kw["parameters_json_schema"] = f["schema"]
            decls.append(t.FunctionDeclaration(**kw))
        return [t.Tool(function_declarations=decls)]

    async def _chamar(self, modelo: str, conversa: list, config):
        from google.genai import errors

        try:
            return await self.cliente.aio.models.generate_content(model=modelo, contents=conversa, config=config)
        except errors.ClientError as e:
            codigo = getattr(e, "code", 0)
            tipo = {401: "autenticacao", 403: "autenticacao", 404: "modelo", 429: "limite"}.get(codigo, "indisponivel")
            if codigo == 400 and "API key" in str(e):
                tipo = "autenticacao"
            raise ErroLLM(tipo, str(e)) from e
        except errors.ServerError as e:  # 500/503: modelo sobrecarregado ou fora do ar
            raise ErroLLM("indisponivel", str(e)) from e
        except Exception as e:  # noqa: BLE001 - falhas de rede do httpx etc.
            if "connect" in type(e).__name__.lower() or "timeout" in type(e).__name__.lower():
                raise ErroLLM("conexao", str(e)) from e
            raise

    async def gerar(self, sistema: str, conversa: list, ferramentas: list[dict]) -> Passo:
        t = self.types
        config = t.GenerateContentConfig(
            system_instruction=sistema,
            tools=self._ferramentas(ferramentas),
            automatic_function_calling=t.AutomaticFunctionCallingConfig(disable=True),
            max_output_tokens=MAX_TOKENS,
        )
        # Plano gratuito às vezes responde "503 high demand" ou "429 limite". Então:
        # tenta de novo o mesmo modelo e, se continuar ruim, passa para os modelos reserva.
        modelos = [self.modelo] + [m for m in self.reservas if m != self.modelo]
        ultimo_erro: ErroLLM | None = None
        resp = None
        for modelo in modelos:
            for tentativa in range(TENTATIVAS_POR_MODELO):
                try:
                    resp = await self._chamar(modelo, conversa, config)
                    break
                except ErroLLM as e:
                    ultimo_erro = e
                    if e.tipo == "modelo":
                        log.warning("Modelo %s não encontrado; tentando o próximo.", modelo)
                        break
                    if e.tipo not in ("indisponivel", "limite", "conexao"):
                        raise
                    log.warning("Gemini %s falhou (%s), tentativa %d.", modelo, e.tipo, tentativa + 1)
                    if tentativa + 1 < TENTATIVAS_POR_MODELO:
                        await self._dormir(ESPERA_SEGUNDOS)
            if resp is not None:
                if modelo != self.modelo:
                    log.info("Respondido pelo modelo reserva %s.", modelo)
                break
        if resp is None:
            raise ultimo_erro or ErroLLM("indisponivel", "sem resposta")

        if not resp.candidates or resp.candidates[0].content is None:
            return Passo(texto="")
        conteudo = resp.candidates[0].content
        # Guarda a resposta original (inclui as "assinaturas de pensamento" que o Gemini exige de volta).
        conversa.append(conteudo)
        partes = conteudo.parts or []
        texto = "\n".join(p.text for p in partes if p.text and not p.thought).strip()
        chamadas = [
            Chamada(id=p.function_call.id or f"fc{i}", nome=p.function_call.name, args=dict(p.function_call.args or {}))
            for i, p in enumerate(partes) if p.function_call
        ]
        return Passo(texto=texto, chamadas=chamadas)

    def adicionar_resultados(self, conversa: list, chamadas: list[Chamada], resultados: list[dict]) -> None:
        t = self.types
        partes = []
        for c, r in zip(chamadas, resultados):
            fid = c.id if not c.id.startswith("fc") else None
            partes.append(t.Part(function_response=t.FunctionResponse(id=fid, name=c.nome, response=r)))
        conversa.append(t.Content(role="user", parts=partes))


# ===================================================================== Claude
class ClaudeProvedor:
    nome = "claude"

    def __init__(self, cliente: Any | None = None, modelo: str | None = None):
        import anthropic

        self.anthropic = anthropic
        self.modelo = modelo or CONFIG.claude_modelo
        self.cliente = cliente or anthropic.AsyncAnthropic(api_key=CONFIG.anthropic_api_key)

    def nova_conversa(self, historico: list[dict], texto: str, imagem: tuple[bytes, str] | None) -> list:
        conteudo = []
        if imagem:
            conteudo.append({"type": "image", "source": {
                "type": "base64", "media_type": imagem[1], "data": base64.b64encode(imagem[0]).decode()}})
        conteudo.append({"type": "text", "text": texto})
        return [dict(m) for m in historico] + [{"role": "user", "content": conteudo}]

    async def gerar(self, sistema: str, conversa: list, ferramentas: list[dict]) -> Passo:
        a = self.anthropic
        try:
            resp = await self.cliente.messages.create(
                model=self.modelo, max_tokens=MAX_TOKENS, system=sistema, messages=conversa,
                tools=[{"name": f["name"], "description": f["description"], "input_schema": f["schema"]}
                       for f in ferramentas],
            )
        except a.AuthenticationError as e:
            raise ErroLLM("autenticacao", str(e)) from e
        except a.RateLimitError as e:
            raise ErroLLM("limite", str(e)) from e
        except a.NotFoundError as e:
            raise ErroLLM("modelo", str(e)) from e
        except a.APIConnectionError as e:
            raise ErroLLM("conexao", str(e)) from e
        except a.APIStatusError as e:
            raise ErroLLM("indisponivel", str(e)) from e

        blocos, texto, chamadas = [], [], []
        for b in resp.content:
            if b.type == "text":
                blocos.append({"type": "text", "text": b.text})
                texto.append(b.text)
            elif b.type == "tool_use":
                blocos.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input or {}})
                chamadas.append(Chamada(id=b.id, nome=b.name, args=dict(b.input or {})))
        conversa.append({"role": "assistant", "content": blocos})
        if resp.stop_reason != "tool_use":
            chamadas = []
        return Passo(texto="\n".join(texto).strip(), chamadas=chamadas)

    def adicionar_resultados(self, conversa: list, chamadas: list[Chamada], resultados: list[dict]) -> None:
        import json

        conversa.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": c.id,
             "content": json.dumps(r, ensure_ascii=False, default=str),
             **({"is_error": True} if "erro" in r else {})}
            for c, r in zip(chamadas, resultados)
        ]})


def criar_provedor(nome: str | None = None):
    nome = (nome or CONFIG.llm_provedor).lower()
    if nome == "claude":
        return ClaudeProvedor()
    if nome == "gemini":
        return GeminiProvedor()
    raise ValueError(f"LLM_PROVEDOR desconhecido: {nome} (use gemini ou claude)")

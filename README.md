# FogoAlerta 🔥🌳

Agente de IA no Telegram para comunidades, agricultores e brigadistas do interior do Amazonas.
Protótipo para o Desafio Saul Benchimol IA 2026. Área piloto: **Autazes**.

O agente faz três coisas:
1. **Alerta**: avisa sozinho quando o satélite detecta foco de calor perto da comunidade.
2. **Orientação**: explica a proibição do fogo, o risco do dia e alternativas ao fogo. **Nunca autoriza queimada.**
3. **Relato**: organiza o que a pessoa viu (texto, foto, áudio, localização), anônimo por padrão, e diz para onde encaminhar.

---

## Passo a passo para rodar (faça na ordem)

### 1. Instalar
Precisa de **Python 3.11 ou mais novo**.

```bash
cd fogoalerta
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Pegar as 3 chaves (todas gratuitas)
| Chave | Onde |
|---|---|
| `TELEGRAM_TOKEN` | No Telegram, fale com **@BotFather** → `/newbot` → copie o token |
| `GEMINI_API_KEY` | https://aistudio.google.com → **Get API key** (conta Google) |
| `FIRMS_MAP_KEY` | https://firms.modaps.eosdis.nasa.gov/api/map_key/ (chega por e-mail) |

**Sobre o plano gratuito do Gemini:**
- Os limites (pedidos por minuto e por dia) aparecem no AI Studio e valem por projeto. Para testes e demo costuma bastar; se aparecer erro de limite, espere um pouco.
- Se o modelo estiver sobrecarregado (erro 503) ou sem cota (429), o bot tenta de novo e depois usa os modelos de `GEMINI_MODELOS_RESERVA`.
- Rode `python scripts/listar_modelos_gemini.py` e confira no AI Studio qual modelo está gratuito para vocês. O padrão é `gemini-3.8-flash`; se der erro de modelo, troque `GEMINI_MODELO` no `.env` (ex.: `gemini-3.5-flash-lite`).
- **Privacidade:** no plano gratuito, o Google pode usar o que é enviado para melhorar os produtos dele, e pessoas podem revisar. Nos testes, **não usem dados pessoais reais** de entrevistados. Na proposta, digam que a versão real usaria plano pago (sem esse uso dos dados).
- Quiser usar Claude no lugar: `LLM_PROVEDOR=claude` + `ANTHROPIC_API_KEY` (pago à parte da assinatura do Claude).

### 3. Configurar
Copie `.env.example` para `.env` e cole as chaves. **Nunca suba o `.env` para o GitHub** (ele já está no `.gitignore`).

### 4. Testar por partes (do mais simples ao completo)
```bash
python -m pytest                    # 46 testes, sem internet e sem gastar cota
python scripts/testar_firms.py      # focos reais perto de Autazes + tempo (só precisa da FIRMS_MAP_KEY)
python scripts/conversar.py         # conversa com o agente pelo terminal (precisa da GEMINI_API_KEY)
python -m fogoalerta.bot            # o bot no Telegram
```
No Telegram, abra o seu bot, mande `/start` e depois `/comunidade`.

### 5. Modo demonstração (para o vídeo e a apresentação)
Se não houver foco real perto de Autazes na hora da demo, coloque `MODO_DEMO=1` no `.env`.
O bot passa a usar focos **simulados** (`data/demo_focos.csv`), e todas as mensagens avisam que é simulação.
Na apresentação, digam isso abertamente: mostra honestidade e a banca entende.

---

## Comandos do bot
`/start` `/comunidade` `/focos` `/tempo` `/boletim` (texto para rádio) `/relato` `/alertas_on` `/alertas_off` `/privacidade` `/limpar` `/ajuda`.
Também aceita texto livre, foto (a IA descreve a imagem para o relato) e localização.
Áudio é opcional: `pip install faster-whisper` (transcreve no próprio computador, sem custo; baixa ~500 MB na primeira vez).

---

## Como funciona

```
Mensagem → [guardrail: emergência? manda 193 na hora, sem IA]
         → Agente (Gemini ou Claude, via llm.py) decide quais ferramentas usar:
              consultar_focos   → NASA FIRMS (focos por raio, distância e direção)
              consultar_tempo   → Open-Meteo (calor, vento, dias sem chuva)
              buscar_orientacao → base data/orientacoes/*.md (RAG simples)
              registrar_relato  → data/relatos/relatos.jsonl + canal certo (data/canais.json)
         → [guardrails de saída: aviso "foco não é incêndio"; bloqueia "pode queimar"]
         → Resposta

A cada 30 min: alertas.py procura focos novos perto de cada comunidade e avisa (mensagem fixa, sem IA).
```

| Arquivo | O que faz |
|---|---|
| `fogoalerta/agente.py` | Prompt do agente, ferramentas e o laço de chamadas de ferramenta |
| `fogoalerta/llm.py` | Provedores de IA: Gemini (padrão) e Claude |
| `fogoalerta/guardrails.py` | Regras que não dependem da IA |
| `fogoalerta/firms.py` | Focos de calor (NASA FIRMS) e modo demonstração |
| `fogoalerta/clima.py` | Tempo e risco estimado (não é índice oficial) |
| `fogoalerta/conhecimento.py` | Busca na base de orientações |
| `fogoalerta/relatos.py` | Registro de relatos e canais |
| `fogoalerta/alertas.py` | Alerta automático |
| `fogoalerta/bot.py` | Telegram |
| `data/` | Comunidades, orientações, canais, focos de demonstração |

---

## ⚠️ O que ainda precisa ser conferido pela equipe
- [ ] **Coordenadas** da sede de Autazes (aproximadas) e das comunidades das entrevistas → `data/comunidades.json`.
- [ ] **Canal de denúncia do Ipaam** e número da Defesa Civil → `data/canais.json` (marcados com PREENCHER/conferir).
- [ ] **Texto do Decreto nº 55.339/2026**: exceções e prorrogação → `data/orientacoes/01_proibicao_e_regras.md`.
- [ ] Detalhes técnicos das alternativas sem fogo (Embrapa/IDAM) → `02_alternativas_sem_fogo.md`.
- [ ] Ajustar a base de orientações com o que apareceu nas **entrevistas**.

## O que já foi testado e o que não
- ✅ Testado (sem internet): leitura do CSV do FIRMS, distâncias e direções, risco do tempo, guardrails, busca na base, relatos, alertas sem repetição, laço do agente, conversão de mensagens do Gemini e do Claude (inclusive o formato do pedido HTTP do Gemini), inicialização do bot.
- ❌ **Não testado ao vivo** (o ambiente onde foi escrito não acessa esses serviços): chamadas reais ao FIRMS, Open-Meteo, Telegram e Gemini. Rodem o passo 4 na ordem para confirmar.
- Se as respostas do Flash ficarem fracas em algum caso, ajustem o prompt em `agente.py` antes de trocar de modelo.

## Limites conhecidos do protótipo
- Conversas ficam só na memória (somem ao reiniciar). Relatos e comunidades ficam em arquivo.
- O bot não envia nada aos órgãos: gera o texto para a pessoa encaminhar.
- Telegram no protótipo; a versão final seria WhatsApp (API Business, com custo por mensagem) + SMS e rádio.

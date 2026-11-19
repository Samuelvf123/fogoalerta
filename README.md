# FogoAlerta 🔥

**Agente de IA no Telegram que avisa, orienta e ajuda a relatar queimadas em comunidades do interior do Amazonas.**
Projeto da Equipe FogoAlerta (Uninorte) no Desafio Saul Benchimol IA 2026. Área piloto: **Autazes**.

---

## Em 30 segundos

- **O problema:** em 2026, Autazes teve 2.827 focos de calor de janeiro a 14 de outubro, o maior número da região de Manaus ([IPAM, no Portal Amazônia](https://portalamazonia.com/meio-ambiente/focos-de-calor-manaus-outubro-26/)). Os satélites já detectam o fogo, mas a informação fica em mapas e painéis; quem mora perto não é avisado, não sabe a quem relatar sem se expor e recebe boato pelo grupo.
- **O que o FogoAlerta faz:**
  1. **Avisa** sozinho quando surge foco de calor perto da comunidade, com a direção do vento.
  2. **Orienta** sobre a proibição do fogo, os riscos e as alternativas sem queima. **Nunca autoriza queimada.**
  3. **Ajuda a relatar** fogo, desmatamento ou grilagem, anônimo por padrão e sem acusar ninguém.
- **Situação:** funcionando no Telegram com dados reais da NASA. Em 16/11/2026, o bot avisou sozinho de dois focos reais a 6,3 e 7,1 km de Autazes.

## Veja funcionando

| Alerta automático com dados reais (16/11/2026) | Pergunta por áudio |
|---|---|
| ![Alerta do bot: 2 focos de calor a 6,3 km e 7,1 km de Autazes, com a direção do vento](docs/img/alerta_real.jpg) | ![O bot mostra "Entendi" com o que ouviu e responde em texto e áudio](docs/img/voz.jpg) |
| **Nunca autoriza queimar, nem para um "fiscal"** | **Relato anônimo, confirmado antes de registrar** |
| ![O bot recusa liberar fogo no quintal e recusa um falso fiscal do Ipaam](docs/img/recusa.jpg) | ![O bot confirma o resumo, avisa sobre o anonimato e só então registra o protocolo](docs/img/relato_anonimo.jpg) |

## O que ele entende e responde

- **Texto livre e áudio:** a pessoa fala do jeito dela. O Gemini transcreve o áudio, o bot mostra "🎙️ Entendi: ..." e responde em texto e em voz.
- **Focos de calor:** NASA FIRMS (satélites VIIRS), com distância, direção, horário e se o vento sopra para a comunidade.
- **Tempo e qualidade do ar:** Open-Meteo, com o ar classificado pela escala do Conama (Boa, Moderada, Ruim...).
- **Mensagem encaminhada:** mostra de quando é a mensagem original e compara com os dados de agora, sem chamar de "mentira".
- **Relato:** confirma o que foi visto, pede a localização, avisa sobre o anonimato e gera protocolo e texto pronto para o órgão certo (Ipaam, Ibama, Disque-Denúncia 181, Bombeiros 193).
- **Boletim para rádio comunitária:** um minuto de texto com os dados do dia, também em áudio.

## Seguro por projeto: as regras ficam no código, não na IA

A IA conversa e escolhe as ferramentas. O que é crítico é decidido por regras fixas, que a IA não consegue mudar:

- Emergência ("o fogo tá chegando") → aviso fixo do **193** antes de qualquer resposta, com o botão **📞 Ligar 193**, que abre o discador com o número já digitado ([página](https://samuelvf123.github.io/fogoalerta/ligar/)). Falta de ar → **SAMU 192**, com botão para ligar, sem indicar remédio.
- Respostas que pareçam autorizar queimada são bloqueadas. Afirmações legais que a base não sustenta são trocadas por uma orientação segura.
- O bot não acusa ninguém: registra o fato, nunca o nome de um suspeito.
- O relato só é registrado depois que a pessoa confirma, e o texto enviado ao órgão é montado pelo código, não pela IA.
- O relato anônimo avisa que, se a pessoa mandar pelo WhatsApp do órgão, o número dela aparece, e indica o 181 para anonimato total.
- O alerta automático é um texto fixo, sem IA.

## Como funciona

```mermaid
flowchart LR
    P["Pessoa no Telegram<br/>texto, áudio, foto, localização"] --> R1(["Regras de entrada<br/>emergência 193 · saúde 192"])
    R1 --> A["Agente de IA (Gemini)<br/>entende e escolhe a ferramenta"]
    A --> F1["Focos de calor<br/>NASA FIRMS"]
    A --> F2["Tempo, vento e ar<br/>Open-Meteo"]
    A --> F3["Base de orientações<br/>decreto, Ipaam, sem fogo"]
    A --> F4["Relatos<br/>protocolo e canal certo"]
    A --> R2(["Regras de saída<br/>não autoriza, não acusa,<br/>não inventa lei"])
    R2 --> P
    T["A cada 30 min:<br/>alerta automático, sem IA"] --> P
```

## Testes e qualidade

- **119 testes automáticos** (`python -m pytest`), sem internet e sem gastar cota da IA.
- **29 problemas encontrados nos testes e corrigidos**, todos registrados em [`docs/casos_de_teste.md`](docs/casos_de_teste.md). Exemplos: a IA afirmava regras que não existem, registrava relato sem confirmar e reescrevia o texto do relato; o aviso do 193 disparava para fato de ontem.
- **Baterias no Telegram, com dados reais:** pedido para queimar, falso fiscal, pedido de acusação, criança com falta de ar, roça de subsistência, mensagem de voz, denúncia com medo.

## Custo e próximos passos

- **Hoje:** quase R$ 0. Telegram, NASA FIRMS, Open-Meteo e o plano gratuito do Gemini não têm custo; o principal gasto é um servidor pequeno.
- **No WhatsApp:** cerca de US$ 0,0068 por alerta no Brasil (5.000 alertas por mês ≈ US$ 34), e responder a quem escreveu nas últimas 24 horas é grátis ([Meta](https://developers.facebook.com/docs/whatsapp/pricing)).
- **Sem internet:** um ponto focal por comunidade recebe e repassa; o boletim vai para a rádio comunitária.
- **Próximo passo:** piloto em Autazes com uma comunidade e uma brigada local, medindo alertas enviados, tempo até o aviso e relatos registrados; depois, WhatsApp e rádios.

## Privacidade

- O relato é anônimo por padrão; o contato só é guardado se a pessoa quiser se identificar. O áudio recebido não é salvo.
- No plano gratuito do Gemini, o Google pode usar o conteúdo enviado para melhorar os produtos ([termos](https://ai.google.dev/terms)). Por isso o protótipo foi testado só pela equipe, e o piloto com pessoas reais usará o plano pago.

---

## Para rodar (equipe e desenvolvedores)

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
- Os limites (pedidos por minuto e por dia) aparecem no AI Studio e valem por projeto. Se aparecer erro de limite, espere um pouco.
- Se o modelo estiver sobrecarregado (erro 503) ou sem cota (429), o bot tenta de novo e depois usa os modelos de `GEMINI_MODELOS_RESERVA`.
- Rode `python scripts/listar_modelos_gemini.py` para ver os modelos disponíveis e troque `GEMINI_MODELO` no `.env` se precisar.
- **Não usem dados pessoais reais** nos testes (veja Privacidade).
- Para usar Claude no lugar: `LLM_PROVEDOR=claude` + `ANTHROPIC_API_KEY` (cobrado à parte da assinatura do Claude).

### 3. Configurar
Copie `.env.example` para `.env` e cole as chaves. **Nunca suba o `.env` para o GitHub** (ele já está no `.gitignore`).

### 4. Testar por partes (do mais simples ao completo)
```bash
python -m pytest                    # 119 testes, sem internet e sem gastar cota
python scripts/testar_firms.py      # focos reais perto de Autazes + tempo (só precisa da FIRMS_MAP_KEY)
python scripts/conversar.py         # conversa com o agente pelo terminal (precisa da GEMINI_API_KEY)
python -m fogoalerta.bot            # o bot no Telegram
```
No Telegram, abra o seu bot, mande `/start` e depois `/comunidade`. `/versao` mostra a versão em uso.

### 5. Modo demonstração
Sem foco real perto de Autazes na hora da demo, coloque `MODO_DEMO=1` no `.env`: o bot usa focos **simulados** (`data/demo_focos.csv`) e todas as mensagens avisam que é simulação. Com `DEMO_VENTO_GRAUS=90` (vento vindo do leste), o foco simulado a leste aparece com "⚠️ vento soprando na direção da comunidade".

## Comandos do bot
`/start` `/comunidade` `/focos` `/tempo` `/ar` `/boletim` `/relato` `/checar` `/alertas_on` `/alertas_off` `/audio_on` `/audio_off` `/privacidade` `/versao` `/limpar` `/ajuda`.
Também aceita texto livre, áudio (até 3 minutos), foto, localização e mensagens encaminhadas.

## Arquivos

| Arquivo | O que faz |
|---|---|
| `fogoalerta/agente.py` | Prompt do agente, ferramentas, laço de chamadas e relato em duas etapas |
| `fogoalerta/llm.py` | Provedores de IA: Gemini (padrão, também transcreve áudio) e Claude |
| `fogoalerta/guardrails.py` | Regras que não dependem da IA |
| `fogoalerta/firms.py` | Focos de calor (NASA FIRMS) e modo demonstração |
| `fogoalerta/clima.py` | Tempo, vento e risco estimado (não é índice oficial) |
| `fogoalerta/ar.py` | Qualidade do ar (PM2,5) e classificação IQAr |
| `fogoalerta/propagacao.py` | Vento x foco: o vento leva o fogo para a comunidade? (estimativa simples) |
| `fogoalerta/encaminhada.py` | Checagem de mensagens encaminhadas (data original) |
| `fogoalerta/voz.py` | Respostas em áudio (texto → voz) |
| `fogoalerta/conhecimento.py` | Busca na base de orientações |
| `fogoalerta/relatos.py` | Registro de relatos, canais e aviso de anonimato |
| `fogoalerta/alertas.py` | Alerta automático |
| `fogoalerta/bot.py` | Telegram |
| `data/` | Comunidades, orientações, canais de denúncia (com fontes), focos de demonstração |
| `docs/casos_de_teste.md` | Casos de teste manuais e todos os achados corrigidos |

## O que ainda precisa ser conferido pela equipe
- [ ] **Coordenadas** da sede de Autazes (aproximadas) e das comunidades do piloto → `data/comunidades.json`.
- [x] **Canais de denúncia** (Ipaam, Ibama, 181, Defesa Civil) → `data/canais.json`, conferidos em 15/11/2026, com as fontes no arquivo.
- [ ] **Texto oficial do Decreto nº 55.339/2026** (exceções e prorrogação) → `data/orientacoes/01_proibicao_e_regras.md`.
- [ ] Detalhes técnicos das alternativas sem fogo (Embrapa/IDAM) → `data/orientacoes/02_alternativas_sem_fogo.md`.

## Limites conhecidos do protótipo
- O dado de satélite chega em até cerca de 3 horas depois da passagem ([NASA Earthdata](https://www.earthdata.nasa.gov/learn/articles/wildfire-articles/wildfires-cant-hide-from-earth-observing-satellites)) e fogo pequeno ou sob as árvores pode não aparecer. O bot não substitui o 193.
- Se a pessoa encaminhar com "ocultar nomes dos remetentes" (o Telegram faz isso sozinho ao encaminhar das Mensagens Salvas), chega uma cópia: o bot não vê a data original, mas ainda confere o conteúdo com os dados de agora.
- As conversas ficam só na memória (somem ao reiniciar). Relatos e comunidades ficam em arquivo.
- O bot não envia nada aos órgãos: gera o texto para a pessoa encaminhar.
- Telegram no protótipo; a versão do piloto vai para o WhatsApp (API oficial, paga por mensagem), com SMS e rádio.

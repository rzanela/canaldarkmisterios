# Canal Dark — Automação de Conteúdo True Crime

> Pipeline 100% automatizado para produção de vídeos de crimes reais brasileiros para YouTube, sem necessidade de aparecer em câmera.

## Arquitetura do Pipeline

```
Opção A: n8n (visual workflow)                    Opção B: Orquestrador + Task Scheduler (R$0)
┌─────────────────────────────────┐              ┌──────────────────────────────────────────┐
│         n8n (Docker local)      │              │  Windows Task Scheduler / cron Linux     │
│                                 │              │                                          │
│  Pesquisa → Roteiro → Produção  │              │  python orquestrador.py --fase pesquisa  │
│           → Upload/SEO           │              │  python orquestrador.py --fase roteiro   │
└─────────────────────────────────┘              │  python orquestrador.py --fase producao  │
                                                 │  python orquestrador.py --fase upload    │
         ▼                                              └──────────┬───────────────────────────┘
  Google Gemini / OpenAI                                   scripts Python (FFmpeg, Pillow, etc.)
  + ElevenLabs + YouTube API
```

## Estrutura de Diretórios

```
canal-dark/
├── .env                     # Suas chaves de API (criar a partir de .env.example)
├── config.yaml              # Configurações do canal, vídeo, SEO
├── requirements.txt         # Dependências Python
│
├── scripts/
│   ├── logger_setup.py      # Logging estruturado com Loguru
│   ├── config.py            # Loader de config (.env + YAML)
│   ├── ai_service.py       # Camada abstrata: Gemini ou OpenAI
│   ├── gemini_service.py   # Wrapper da API Gemini
│   ├── reddit_service.py    # Cliente Reddit API
│   ├── youtube_service.py   # YouTube Data API v3 (upload, schedule)
│   ├── pesquisa_temas.py    # Phase 1: pesquisa → fila de temas
│   ├── roteirizador.py      # Phase 2: roteiro JSON com timecodes
│   ├── narrador.py          # Phase 3: ElevenLabs / gTTS → áudio
│   ├── gerador_imagens.py   # Phase 4: DALL-E 3 / Imagen 3 → imagens
│   ├── gerador_video_ia.py  # Phase 5A: MiniMax via mcode-tools → vídeo AI
│   ├── montador_video.py    # Phase 5B: FFmpeg → MP4 final (fallback)
│   ├── seo_gerador.py       # Phase 6: metadata SEO (título, tags, descrição)
│   ├── orquestrador.py      # Orquestrador completo (sem n8n)
│   ├── agendar_tarefas.py   # Cria tarefas no Windows Task Scheduler
│   └── setup_auth.py        # Script de configuração inicial
│
├── templates/
│   ├── pesquisa_system.md   # Prompt de sistema — pesquisa de temas
│   ├── roteiro_system.md    # Prompt de sistema — roteirização
│   ├── seo_system.md        # Prompt de sistema — SEO
│   └── thumbnail_system.md  # Prompt de sistema — thumbnails
│
├── n8n/
│   ├── pesquisa_workflow.json   # Workflow n8n — pesquisa automática
│   ├── roteiro_workflow.json   # Workflow n8n — geração de roteiro
│   ├── producao_workflow.json  # Workflow n8n — produção (imagens + áudio)
│   └── upload_workflow.json    # Workflow n8n — upload + SEO
│
├── dados/
│   ├── fila_temas.json         # Filas de tarefas pendentes
│   ├── historico_temas.json    # Histórico de temas processados
│   ├── fila_upload.json        # Histórico de uploads
│   ├── youtube_token.json      # OAuth token (gerado automaticamente)
│   └── youtube_client_secrets.json  # OAuth credentials (baixar do GCP)
│
├── projetos/               # Um subdiretório por projeto/vídeo
│   └── tc_YYYYMMDD_nome/
│       ├── resultado_{id}.json  # Roteiro gerado
│       ├── imagens/             # Imagens geradas
│       ├── audio/              # Narrações geradas
│       ├── clipes/             # Clipes individuais
│       └── clipe_final.mp4     # (saída)
│
└── output/                # Vídeos finais montados
```

## Instalação

### 1. Clone / Copie o Projeto

```bash
cd "G:\Meu Drive\IA\Canal Dark"
git clone https://github.com/seu-usuario/canal-dark.git
cd canal-dark
```

### 2. Configure o Ambiente Python

```bash
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure as Variáveis de Ambiente

```bash
copy .env.example .env
# Edite o .env e preencha suas chaves de API
```

### 4. Instale o FFmpeg (obrigatório para montagem de vídeo)

```bash
# Windows
winget install ffmpeg

# Linux
sudo apt install ffmpeg

# Mac
brew install ffmpeg
```

### 5. Configure as APIs

#### OpenAI (GPT-4o + DALL-E 3)
1. Acesse https://platform.openai.com/api-keys
2. Crie uma API key
3. Cole no `.env` como `OPENAI_API_KEY=sk-...`

#### ElevenLabs (voz)
1. Crie conta em https://elevenlabs.io
2. Copie sua API key
3. Opcional: escolha um voice ID em https://elevenlabs.io/voice-library

#### YouTube Data API (upload)
1. Acesse https://console.cloud.google.com
2. Crie projeto (ou selecione existente)
3. Ative **YouTube Data API v3**
4. Vá em Credenciais → Criar Credenciais → **ID do cliente OAuth 2.0**
5. Tipo: **App para Desktop**
6. Baixe o JSON e salve como `dados/youtube_client_secrets.json`

#### Reddit API (opcional — o pipeline tem fallback)
1. Acesse https://www.reddit.com/prefs/apps
2. Crie app (tipo: script)
3. Copie Client ID e Client Secret para `.env`

### 6. Execute a Configuração Inicial

```bash
python scripts/setup_auth.py
```

Isso vai:
- Verificar todas as dependências
- Testar conectividade com as APIs
- Iniciar o fluxo OAuth do YouTube (abra o link no navegador)

## Como Usar

### Opção A: Orquestrador + Task Scheduler (R$0 — recomendado para início)

Não precisa de n8n nem de instância cloud. Tudo roda localmente.

```bash
# 1. Crie as tarefas agendadas (só precisa fazer uma vez)
python scripts/agendar_tarefas.py --setup

# 2. Ou execute manualmente a qualquer momento:
python scripts/orquestrador.py --fase pesquisa
python scripts/orquestrador.py --fase roteiro
python scripts/orquestrador.py --fase producao
python scripts/orquestrador.py --fase upload

# Pipeline completo (pesquisa → roteiro → produção → upload):
python scripts/orquestrador.py --fase completo

# Ver status do pipeline:
python scripts/orquestrador.py --fase status

# Remove tarefas agendadas:
python scripts/agendar_tarefas.py --remove
```

**Resultado**: o Windows Task Scheduler dispara automaticamente Seg/Qua/Sex às 8h, 9h, 10h e 11h.

---

### Opção B: n8n Self-hosted (Docker — gratuito)

O n8n self-hosted tem scheduler nativo — funciona 100% local.

```bash
# Inicie o n8n com Docker:
docker run -d \
  --name n8n \
  -p 5678:5678 \
  -v n8n_data:/home/node/.n8n \
  -e N8N_BASIC_AUTH_ACTIVE=true \
  n8nio/n8n
```

Depois:
1. Abra http://localhost:5678
2. Importe cada `.json` da pasta `n8n/`
3. Configure as credenciais (Google OAuth2, OpenAI/Gemini, Reddit)
4. Ative os workflows

### Opção C: Uso Individual (scripts avulsos)

```bash
python scripts/pesquisa_temas.py
python scripts/roteirizador.py "tc_20240315_caso_x"
python scripts/narrador.py "tc_20240315_caso_x"
python scripts/gerador_imagens.py "tc_20240315_caso_x"
python scripts/montador_video.py "tc_20240315_caso_x"
python scripts/seo_gerador.py --tema "Caso X" --roteiro projetos/tc_xxx/roteiro.json
```

### Opção D: Pipeline de Vídeo por IA (MiniMax — sem encoding local)

> **NOVO!** Geração de vídeo 100% na nuvem via MiniMax (mcode-tools). Não precisa de FFmpeg local nem GPU.
> Indicado quando o PC não consegue codificar vídeos localmente.

```bash
# Gera vídeo completo: imagem de capa → clipes → concatenação → narração
python scripts/orquestrador.py --fase videoia --video-id "tc_20240315_caso_x" --modelo MiniMax-H3-Max --clipes 4

# Ou diretamente:
python scripts/gerador_video_ia.py --projeto projetos/tc_20240315_caso_x --modelo MiniMax-H3-Max --clipes 4
```

**Modelos disponíveis:**
- `MiniMax-H3-Max` — rápido (~20s), 480P/768P, keyframes only, com áudio nativo
- `MiniMax-H3` — alta qualidade (~15-30min), 768P/2K, com áudio nativo
- `MiniMax-Hailuo-2.3` — econômico, 768P/1080P, silencioso (precisa narração separada)

**Escolha o modelo ideal:**
- Precisa de resultado rápido + com áudio? → `MiniMax-H3-Max`
- Quer máxima qualidade e tempo? → `MiniMax-H3`
- Quer economy + já tem narração? → `MiniMax-Hailuo-2.3`

### Modo Demo (sem APIs configuradas)

Todos os scripts funcionam em modo demo quando não há chaves configuradas:
- `pesquisa_temas.py` → usa dados simulados de Reddit
- `narrador.py` → usa gTTS (voz do Google, gratuita)
- `gerador_imagens.py` → usa placeholder escuro
- `youtube_service.py` → modo de preview sem upload real

## Configuração do `config.yaml`

```yaml
canal:
  nome: "Canal Dark"
  id: "UCxxxxxxxxxxxxxxxxx"  # ID do seu canal
  idioma: "pt-BR"
  timezone: "America/Sao_Paulo"

video:
  duracao_minima_min: 12
  duracao_maxima_min: 22
  resolucao: "1920x1080"
  fps: 30
  formato: "mp4"

paleta:
  fundo: "#0D0D0D"
  primario: "#C0392B"
  secundario: "#1A1A1A"
  texto: "#FFFFFF"
  destaque: "#E63946"

seo:
  titulo_max_chars: 90
  descricao_max_chars: 300
  tags_por_video: 15
  categoria: "22"  # Entertainment no YouTube

cadencia:
  videos_longos: 3
  shorts: 3
  dias_publicacao: ["ter", "qui", "sáb"]
```

## Cronograma de Execução

| Dia       | Horário | Workflow          | Ação                                    |
|-----------|---------|-------------------|-----------------------------------------|
| Seg/Qua/Sex | 08:00  | Pesquisa          | Busca Reddit + classifica GPT-4o       |
| Seg/Qua/Sex | 09:00  | Roteiro           | Gera roteiro JSON completo              |
| Seg/Qua/Sex | 10:00  | Produção          | Imagens DALL-E + Narração ElevenLabs   |
| Seg/Qua/Sex | 11:00  | Montagem          | FFmpeg → MP4 final                      |
| Ter/Qui/Sáb | 11:00  | Upload + SEO      | Publica com título, descrição e tags   |

## Métricas e Monitoramento

O pipeline gera logs detalhados em:
- Cada script salva logs em `dados/logs/`
- O `setup_auth.py` gera relatório de validação

Para acompanhar resultados:
1. **YouTube Studio** → Analytics (retenção, RPM, watch time)
2. **Google Analytics** → comparar com benchmarks do nicho
3. **n8n** → Executions history (logs de cada workflow)

## Custo Estimado (R$/mês)

| Serviço          | Uso                | Custo estimado       |
|------------------|--------------------|-----------------------|
| OpenAI GPT-4o    | ~50 calls/mês     | R$ 80–150             |
| DALL-E 3         | ~300 imagens/mês  | R$ 80–150             |
| ElevenLabs       | ~300 min áudio/mês | R$ 20–60 (plano Pro)  |
| n8n Cloud        | 1 usuário          | R$ 80 (opcional)      |
| **Total**        |                    | **R$ 180–360/mês**    |

> Alternativas para reduzir custo: usar gTTS (gratuito) no lugar de ElevenLabs e manter apenas GPT-4o para roteiros.

## Resolução de Problemas

### "FFmpeg not found"
```bash
winget install ffmpeg
# Reinicie o terminal após a instalação
```

### "YouTube OAuth token expired"
```python
from scripts.youtube_service import youtube_authenticate
youtube_authenticate(force=True)
```

### "OpenAI API key invalid"
- Verifique se a key no `.env` está correta
- Verifique se o plano tem créditos disponíveis em https://platform.openai.com

### "Module not found"
```bash
pip install -r requirements.txt
```

### Vídeo sem áudio após montagem
- Verifique se todos os arquivos em `projetos/{id}/audio/` têm extensão `.mp3`
- FFmpeg precisa estar no PATH (veja instalação acima)

## Roadmap de Funcionalidades

- [x] Phase 1: Pesquisa automática de temas
- [x] Phase 2: Geração de roteiro com GPT-4o
- [x] Phase 3: Narração com ElevenLabs / gTTS
- [x] Phase 4: Geração de imagens com DALL-E 3
- [x] Phase 5: Montagem de vídeo com FFmpeg
- [x] Phase 6: SEO com GPT-4o
- [ ] Phase 7: Geração automática de Shorts
- [ ] Phase 8: Dashboard de monitoramento com Grafana/streamlit
- [ ] Phase 9: Affiliate links automáticos (Hotmart/Amazon)

## Disclaimer

Este pipeline foi criado para **produção de conteúdo informativo e documental**.
O conteúdo gerado deve respeitar:
- **Direito à privacidade** das vítimas e familiares
- **Verificabilidade** dos fatos narrados
- **Ética periodística** — sem sensacionalismo ou incitação ao ódio

O autor não se responsabiliza pelo uso indevido do conteúdo gerado.

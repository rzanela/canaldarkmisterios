"""
FASE 2 — Roteirização

Gera roteiros completos com timecode para cada vídeo.
Usa OpenAI GPT-4o para criar script narrativo profissional.

Uso: python roteirizador.py [--tema "O Caso X"] [--fonte "URL do Reddit"] [--saida projeto-001]
"""
import os
import sys
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional
sys.path.insert(0, str(Path(__file__).parent))

from logger_setup import get_logger
from config import config

log = get_logger("roteirizador")

# ─── AI Service (OpenAI ou Gemini via abstração) ──────────────────────────────
try:
    from ai_service import gerar_json
except ImportError:
    # Fallback se ai_service não estiver disponível
    def gerar_json(prompt, system_instruction=None, schema=None, temperature=0.3, max_tokens=3000):
        import json
        from openai import OpenAI
        client = OpenAI()
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        response = client.chat.completions.create(
            model="gpt-4o", messages=messages,
            response_format={"type": "json_object"},
            temperature=temperature, max_tokens=max_tokens,
        )
        return json.loads(response.choices[0].message.content)


class Roteirizador:
    """
    Agente de roteirização para vídeos de True Crime.
    Gera scripts completos com:
    - Gancho de abertura (0-15s)
    - Contexto (15-60s)
    - Desenvolvimento (1-10min)
    - Clímax
    - Encerramento
    - Timecodes
    - Sugestões visuais
    """
    
    ESTRUTURA = """
ESTRUTURA DO ROTEIRO (repita esta estrutura):

[GANCHO] (0:00 - 0:15)
Narrar APENAS a frase de impacto. Sem contexto. Sem introduzir pessoas.
Exemplo: "Ele acordou às 3 da manhã com a certeza de que alguém estava na casa."
NÃO diga: "Neste vídeo vamos falar sobre..."

[CONTEXTO] (0:15 - 1:00)
Introduza: QUEM, ONDE, QUANDO.
Exatamente 2-3 frases estabelecendo a situação.
Sem spoilers do clímax.

[DESENVOLVIMENTO] (1:00 - 12:00)
Conte a história em ordem cronológica.
Cada parágrafo deve ter 3-5 frases.
Inclua:
- Detalhes sensoriais (sons, cheiros, sensações)
- Diálogos-chave quando disponíveis
- Momentos de tensão e pausa
- 2-3 viradas na narrativa

[CLÍMAX] (12:00 - 14:00)
O momento mais intenso e surpreendente.
Narração mais lenta, voz mais grave.
Uma pausa de 2 segundos antes do clímax.

[ENCERRAMENTO] (14:00 - 15:00)
- O que aconteceu com as pessoas envolvidas (resolução ou mistério contínuo)
- "Se inscreva e active o sininho"
- "No próximo vídeo vamos descobrir..."
- NÃO faça um cliffhanger forte demais (YouTube não gosta)

[MÚSICA E ATMOSFERA]
Sugira momentos de transição musical:
- [TENSÃO] - música tensa começa
- [SILÊNCIO] - corte música, apenas narração
- [REVEAL] - música de choque/impacto
- [CLÍMAX] - música peaks aqui
- [RESOLUÇÃO] - música calmante
"""
    
    PROMPT_BASE = """
Você é um roteirista profissional de documentários de True Crime para YouTube.
Você escreve em português brasileiro, tom sério e investigativo.
Sua voz narrativa é anônima, grave, lenta e competente.

REGRAS DE OURO:
1. NUNCA invente nomes, datas, locais ou detalhes. Use SOMENTE o que está no material fornecido.
2. Se faltar informação, use "As investigações indicam que..." ou "Fontes relatam que..."
3. NUNCA revele o final nos primeiros 30 segundos.
4. Use perguntas retóricas para aumentar tensão: "O que aconteceu em seguida?"
5. Cada parágrafo de desenvolvimento deve TER NO MÁXIMO 4 frases.
6. Inclua PAUSAS [PAUSA 3s] a cada 2-3 parágrafos para visual ter tempo de mudar.
7. Não use expressões como "curta e inscreva-se" ou "comenta aí".
8. Terminologia: use "vítima", "investigadores", "autoridades" - não "polícia" genérica.

TONALIDADE:
- Grave mas não melodramático
- Profissional mas acessível
- Curto e objetivo nos fatos, longo na tensão
- Sem opinião pessoal ou julgamento

ESPECIALIDADES BRASILEIRAS:
- Use termos corretos: "Delegacia", "Inquérito Policial", "Ministério Público"
- Datas no formato brasileiro: "12 de março de 2019"
- Cidades e estados completos na primeira menção

RESPOSTA EM JSON COM ESTE FORMATO EXATO:
{{
  "metadata": {{
    "tema": "Título do caso",
    "gancho_original": "Frase de impacto original do tema",
    "fonte": "URL da fonte",
    "data_roteiro": "YYYY-MM-DD",
    "duracao_estimada": "15 minutos"
  }},
  "roteiro": [
    {{
      "segmento": "GANCHO",
      "timecode_inicio": "0:00",
      "timecode_fim": "0:15",
      "tipo": "narracao",
      "texto": "Texto exato da narração (cada frase em uma linha para melhor controle de timing)",
      "musica": "NENHUMA - silêncio total",
      "visual": "Descrição do visual sugerido (escuro, close em objeto, etc.)"
    }},
    {{
      "segmento": "CONTEXTO",
      "timecode_inicio": "0:15",
      "timecode_fim": "1:00",
      "tipo": "narracao",
      "texto": "Texto...",
      "musica": "[TENSÃO] música tensa ambiente entra suave",
      "visual": "Descrição..."
    }},
    {{
      "segmento": "DESENVOLVIMENTO_1",
      "timecode_inicio": "1:00",
      "timecode_fim": "3:00",
      "tipo": "narracao",
      "texto": "Texto...",
      "musica": "[TENSÃO] contínua",
      "visual": "Descrição...",
      "pausa": "2s"
    }},
    {{
      "segmento": "CLIMAX",
      "timecode_inicio": "12:00",
      "timecode_fim": "14:00",
      "tipo": "narracao",
      "texto": "Texto...",
      "musica": "[CLIMAX] música de impacto",
      "visual": "Descrição...",
      "efeito_sonoro": "suspense_impact"
    }},
    {{
      "segmento": "ENCERRAMENTO",
      "timecode_inicio": "14:00",
      "timecode_fim": "15:00",
      "tipo": "narracao",
      "texto": "Texto...",
      "musica": "[RESOLUÇÃO] música calmante",
      "visual": "Descrição..."
    }}
  ],
  "palavras_chave": ["kw1", "kw2", "kw3", "kw4", "kw5"],
  "warnings": ["Aviso se houver informação potencialmente sensível"]
}}
"""
    
    def __init__(self, tema: str = None, fonte: str = None, contexto: str = None):
        self.tema = tema or "Caso demonstrativo - uso de IA em investigações"
        self.fonte = fonte or ""
        self.contexto = contexto or ""
    
    def gerar_roteiro(self) -> Dict:
        """Gera roteiro completo usando LLM."""
        
        try:
            from ai_service import gerar_json as ai_gerar_json
        except ImportError:
            ai_gerar_json = None

        if not ai_gerar_json:
            log.warning("AI service não disponível - usando roteiro demo")
            return self._gerar_roteiro_demo()
        
        prompt = f"""{self.PROMPT_BASE}

MATERIAl DE REFERÊNCIA:
Título do caso: {self.tema}
{fonte}

{self.contexto if self.contexto else "Desenvolva o roteiro com informações genéricas de casos reais brasileiros de alta repercussão. Use nomes fictícios se necessário para proteger identidades."}

{self.ESTRUTURA}

IMPORTANTE: Responda apenas com JSON válido, sem texto adicional fora do JSON.
"""
        
        try:
            log.info(f"Gerando roteiro para: {self.tema[:60]}")
            
            if ai_gerar_json:
                roteiro = ai_gerar_json(
                    prompt=prompt,
                    system_instruction=self.PROMPT_BASE,
                    temperature=0.5,
                    max_tokens=3000,
                )
            else:
                from openai import OpenAI
                client = OpenAI()
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": self.PROMPT_BASE + "\n\n" + prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.5,
                    max_tokens=3000,
                )
                roteiro = json.loads(response.choices[0].message.content)
            
            log.info(f"Roteiro gerado com {len(roteiro.get('roteiro', []))} segmentos")
            return roteiro
            
        except Exception as e:
            log.error(f"Erro ao gerar roteiro: {e}")
            return self._gerar_roteiro_demo()
    
    def _gerar_roteiro_demo(self) -> Dict:
        """Gera roteiro demo quando API não está disponível."""
        
        tema_limpo = self.tema[:60]
        
        return {
            "metadata": {
                "tema": self.tema,
                "gancho_original": "O momento em que tudo mudou para sempre.",
                "fonte": self.fonte or "demo",
                "data_roteiro": datetime.now(timezone.utc).date().isoformat(),
                "duracao_estimada": "15 minutos"
            },
            "roteiro": [
                {
                    "segmento": "GANCHO",
                    "timecode_inicio": "0:00",
                    "timecode_fim": "0:15",
                    "tipo": "narracao",
                    "texto": f"Às três horas da manhã, {tema_limpo}.\nA casa estava em silêncio.\nMas algo estava errado.",
                    "musica": "NENHUMA - silêncio total",
                    "visual": "Tela preta. Texto branco aparecendo letra por letra."
                },
                {
                    "segmento": "CONTEXTO",
                    "timecode_inicio": "0:15",
                    "timecode_fim": "1:00",
                    "tipo": "narracao",
                    "texto": "Este é o caso que intriga investigadores há anos.\nAs evidências foram recolhidas no local.\nMas as respostas ainda não vieram.",
                    "musica": "[TENSÃO] música ambiente entra suave",
                    "visual": "Imagens de arquivo (reais ou geradas por IA)"
                },
                {
                    "segmento": "DESENVOLVIMENTO_1",
                    "timecode_inicio": "1:00",
                    "timecode_fim": "5:00",
                    "tipo": "narracao",
                    "texto": "Os primeiros relatos sugeriam um cenário comum.\n[PAUSA 2s]\nMas os detalhes que emergiram depois contradiziam tudo.\nUma testemunha apareceu com uma história diferente.\n[PAUSA 2s]\nE foi aí que a investigação tomou um rumo inesperado.",
                    "musica": "[TENSÃO] contínua e crescente",
                    "visual": "Cenas escuras, close em objetos, reconstrução artística"
                },
                {
                    "segmento": "DESENVOLVIMENTO_2",
                    "timecode_inicio": "5:00",
                    "timecode_fim": "10:00",
                    "tipo": "narracao",
                    "texto": "As autoridades seguiram várias pistas.\nCada uma levava a mais perguntas.\n[PAUSA 2s]\nOs vizinhos foram interrogados.\nNinguém viu nada. Ou ninguém quis falar.\n[PAUSA 2s]\nO relatório policial tinha mais de duzentas páginas.\nMas a conclusão era a mesma: sem respostas definitivas.",
                    "musica": "[TENSÃO] constante",
                    "visual": "Gráficos, linhas do tempo, mapas"
                },
                {
                    "segmento": "CLIMAX",
                    "timecode_inicio": "12:00",
                    "timecode_fim": "14:00",
                    "tipo": "narracao",
                    "texto": "[PAUSA 3s]\nE então... uma descoberta.\n[PAUSA 2s]\nAlgo que ninguém esperava.\n[PAUSA 2s]\nAs evidências que estavam escondidas à plaina vista.\n[PAUSA 2s]\nO momento que mudou tudo para sempre.",
                    "musica": "[CLIMAX] música de impacto",
                    "visual": "Zoom lento na tela escura, efeito de revelação"
                },
                {
                    "segmento": "ENCERRAMENTO",
                    "timecode_inicio": "14:00",
                    "timecode_fim": "15:00",
                    "tipo": "narracao",
                    "texto": "O caso permanece sem resolução completa até hoje.\nAs autoridades continuam investigando.\nSe você tem alguma informação, entre em contato.\n[PAUSA 1s]\nSe inscreva para acompanhar os próximos episódios.\nO próximo caso vai te surpreender.",
                    "musica": "[RESOLUÇÃO] música calmante",
                    "visual": "Tela escura com texto do canal"
                }
            ],
            "palavras_chave": [
                self.tema[:30], "caso real", "investigação",
                "mistério", "brasil"
            ],
            "warnings": ["Verificar fontes antes de publicar"]
        }
    
    def salvar_roteiro(self, roteiro: Dict, projeto_dir: Path):
        """Salva roteiro em JSON e TXT."""
        
        # JSON completo
        json_path = projeto_dir / "roteiro.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(roteiro, f, ensure_ascii=False, indent=2)
        
        # TXT legível (para debug e revisão humana)
        txt_path = projeto_dir / "roteiro.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"ROTEIRO: {roteiro['metadata']['tema']}\n")
            f.write(f"Data: {roteiro['metadata']['data_roteiro']}\n")
            f.write(f"Duração estimada: {roteiro['metadata']['duracao_estimada']}\n")
            f.write("=" * 60 + "\n\n")
            
            for seg in roteiro["roteiro"]:
                f.write(f"\n[{seg['segmento']}] {seg['timecode_inicio']} → {seg['timecode_fim']}\n")
                f.write(f"🎬 {seg.get('visual', '')}\n")
                f.write(f"🎵 {seg.get('musica', '')}\n")
                f.write(f"\n{seg['texto']}\n")
                f.write("-" * 40 + "\n")
        
        log.info(f"Roteiro salvo em {projeto_dir}")
        return json_path, txt_path


def main():
    parser = argparse.ArgumentParser(description="Roteirização para Canal Dark")
    parser.add_argument("--tema", type=str, default="O Caso que Ninguém Consegue Explicar", help="Título do caso")
    parser.add_argument("--fonte", type=str, default="", help="URL da fonte")
    parser.add_argument("--contexto", type=str, default="", help="Informações adicionais do caso")
    parser.add_argument("--saida", type=str, default=None, help="Nome do projeto (pasta)")
    args = parser.parse_args()
    
    roteirizador = Roteirizador(tema=args.tema, fonte=args.fonte, contexto=args.contexto)
    roteiro = roteirizador.gerar_roteiro()
    
    # Salva
    if args.saida:
        projeto_dir = config.get_projeto_dir(args.saida)
    else:
        projeto_dir = config.get_projeto_dir(args.tema[:40])
    
    roteirizador.salvar_roteiro(roteiro, projeto_dir)
    
    print(f"\n✅ Roteiro gerado e salvo em: {projeto_dir}")
    print(f"   Tema: {roteiro['metadata']['tema']}")
    print(f"   Duração: {roteiro['metadata']['duracao_estimada']}")
    print(f"   Segmentos: {len(roteiro['roteiro'])}")
    
    return roteiro


if __name__ == "__main__":
    main()

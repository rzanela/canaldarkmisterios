"""
FASE 6 — SEO e Metadata

Gera títulos, descrições e tags otimizados para YouTube.
Usa LLM para criar cópias de alto impacto.

Uso: python seo_gerador.py --roteiro projeto/roteiro.json --titulo "O Caso X"
"""
import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))

from logger_setup import get_logger
from config import config
from ai_service import ai_service

log = get_logger("seo_gerador")


class SEOGerador:
    """
    Gera metadata SEO otimizado para YouTube:
    - Títulos magnéticos
    - Descrições com hooks
    - Tags baseadas em tendências
    - Cards e endscreen
    """
    
    TEMPLATES_TITULO = [
        "O Caso de {NOME} que {AÇÃO} | Caso Real",
        "{NOME}: A Verdade que {AÇÃO} | Investigação",
        "O Mistério de {NOME} que {AÇÃO} | Documentário",
        "O Crime de {NOME} que {AÇÃO} | Caso Aberto",
        "A História de {NOME} que {AÇÃO} | True Crime",
    ]
    
    HOOKS_DESCRICAO = [
        "Neste vídeo, vamos revelar os detalhes que a polícia não quis comentar.",
        "Você não vai acreditar no que aconteceu quando as investigações começaram.",
        "Este caso ficou famoso por um motivo que você vai entender agora.",
        "Prepare-se: esta história é baseada em eventos reais que chocaram o Brasil.",
        "Se você chegou até aqui, é porque sabia que este caso ia te surpreender.",
    ]
    
    def __init__(self, tema: str):
        self.tema = tema
        self.nicho = config.NICHO
        self.sub_nicho = config.SUB_NICHO
    
    def gerar_metadata(self, roteiro_path: Path = None) -> Dict:
        """Gera metadata SEO completo."""
        
        if roteiro_path and roteiro_path.exists():
            with open(roteiro_path, "r", encoding="utf-8") as f:
                roteiro = json.load(f)
            gancho = roteiro.get("metadata", {}).get("gancho_original", self.tema)
            keywords_roteiro = roteiro.get("palavras_chave", [])
        else:
            gancho = self.tema
            keywords_roteiro = []
        
        # Tenta usar LLM (Gemini ou OpenAI via ai_service)
        metadata = self._gerar_com_llm(gancho, keywords_roteiro)
        if metadata:
            return metadata
        return self._gerar_demo(gancho)
    
    def _gerar_com_llm(self, gancho: str, keywords: list) -> Optional[Dict]:
        """Gera metadata usando LLM."""
        
        prompt = f"""
Você é um especialista em SEO para YouTube brasileiro focado em True Crime.

Gere metadata otimizado para um vídeo com o seguinte tema:
Tema: {self.tema}
Gancho: {gancho}
Nicho: {self.nicho} / {self.sub_nicho}

REGRAS:
1. Títulos devem ter entre 60-75 caracteres (YouTube corta depois disso)
2. Usar números e palavras emocionais no título (NOJO, TRISTE, REVELAÇÃO)
3. Descrição deve ter 3-4 parágrafos: hook, corpo, call-to-action
4. Tags devem incluir: variações do título, sinônimos, nicho, "caso real", "documentário"
5. Usar formato YouTube (timestamps, emojis, hashtags)
6. TODOS os textos em PORTUGUÊS BRASILEIRO

Responda APENAS em JSON:
{{
  "titulo": "Título otimizado para SEO e CTR (60-75 caracteres)",
  "titulo_alternativo": "Título alternativo para A/B test",
  "descricao": "Descrição completa com:\\n- Parágrafo de hook (primeiras 2 linhas são cruciais)\\n- Resumo do conteúdo\\n- Call to action\\n- Hashtags",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8", "tag9", "tag10", "tag11", "tag12", "tag13", "tag14", "tag15"],
  "categoria": "24",
  "playlist": "Crimes Brasileiros",
  "timestamps": [
    {{"time": "0:00", "label": "Gancho - momento impactante"}},
    {{"time": "0:30", "label": "Contexto do caso"}},
    {{"time": "2:00", "label": "Investigação começa"}},
    {{"time": "8:00", "label": "Revelação"}},
    {{"time": "14:00", "label": "Conclusão"}}
  ]
}}
"""
        
        try:
            resultado = ai_service.gerar_json(prompt)
            if resultado:
                log.info(f"SEO gerado: {resultado.get('titulo', '')[:60]}")
                return resultado
            return None
        except Exception as e:
            log.error(f"Erro LLM SEO: {e}")
            return None
    
    def _gerar_demo(self, gancho: str) -> Dict:
        """Gera metadata demo quando API não está disponível."""
        
        return {
            "titulo": f"O Caso que {gancho[:40]} | Caso Real | Investigação",
            "titulo_alternativo": f"{gancho[:50]} - A Verdade Revelada | Documentário",
            "descricao": f"""⚠️ CASO BASEADO EM FATOS REAIS

{gancho}

Neste vídeo, vamos revelar os detalhes que a polícia não quis comentar. Uma história que intriga investigadores até hoje.

O QUE VOCÊ VAI VER:
• A verdade por trás deste caso
• Evidências que nunca foram reveladas
• O momento que mudou tudo

📌 Timestamps:
0:00 - Gancho
0:30 - Contexto
2:00 - Investigação
8:00 - Revelação
14:00 - Conclusão

👉 SE INSCREVA e ative o sininho para não perder nenhum caso!

#casoreals #truecrime #investigação #casorealsbrasil #mistério #documentário #casorealbrasil""",
            "tags": [
                "caso real", "true crime", "crime brasil", "investigação",
                "mistério resolvido", "caso sem solução", "documentário crime",
                "polícia", " Tribunal", "True Crime Brasil", "caso real youtube",
                "mistério brasil", "crimes reais", "caso interessante"
            ],
            "categoria": "24",
            "playlist": "Crimes Brasileiros",
            "timestamps": [
                {"time": "0:00", "label": "Gancho - momento impactante"},
                {"time": "0:30", "label": "Contexto do caso"},
                {"time": "2:00", "label": "Investigação"},
                {"time": "8:00", "label": "Revelação"},
                {"time": "14:00", "label": "Conclusão"}
            ]
        }
    
    def formatar_descricao_com_timestamps(self, metadata: Dict) -> str:
        """Formata descrição incluindo timestamps."""
        
        desc = metadata.get("descricao", "")
        
        if "timestamps" in metadata and metadata["timestamps"]:
            timestamps_texto = "\n".join(
                f"{t['time']} - {t['label']}"
                for t in metadata["timestamps"]
            )
            
            if "📌 Timestamps:" not in desc:
                desc += f"\n\n📌 Timestamps:\n{timestamps_texto}"
        
        return desc


def main():
    parser = argparse.ArgumentParser(description="Geração de SEO")
    parser.add_argument("--tema", type=str, required=True, help="Tema do vídeo")
    parser.add_argument("--roteiro", type=str, default=None, help="Caminho do roteiro.json")
    parser.add_argument("--saida", type=str, default=None, help="Caminho para salvar JSON")
    args = parser.parse_args()
    
    roteiro_path = Path(args.roteiro) if args.roteiro else None
    gerador = SEOGerador(tema=args.tema)
    metadata = gerador.gerar_metadata(roteiro_path)
    
    print("\n" + "="*60)
    print("SEO GERADO")
    print("="*60)
    print(f"\n🎯 TÍTULO:\n{metadata.get('titulo', 'N/A')}")
    print(f"\n🔄 ALTERNATIVO:\n{metadata.get('titulo_alternativo', 'N/A')}")
    print(f"\n📝 DESCRIÇÃO:\n{metadata.get('descricao', 'N/A')[:300]}...")
    print(f"\n🏷️ TAGS ({len(metadata.get('tags', []))}):\n{', '.join(metadata.get('tags', [])[:10])}")
    
    if args.saida:
        with open(args.saida, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Salvo em: {args.saida}")
    
    return metadata


if __name__ == "__main__":
    main()

"""
FASE 1 — Pesquisa de Tendências e Seleção de Temas

Busca notícias de portais brasileiros (G1, UOL, R7, CNN, Folha)
e usa Gemini para classificar e selecionar os melhores temas para true crime.

Fontes:
  - G1 (Globo), UOL, R7, CNN Brasil, Folha de S.Paulo
  - Scraping direto (sem API key necessária)

Uso:
  python pesquisa_temas.py                    # busca normal de noticias BR
  python pesquisa_temas.py --fonte g1         # só G1
  python pesquisa_temas.py --max 30            # maximo 30 results
  python pesquisa_temas.py --reddit            # volta ao Reddit (se configurado)
"""
import os
import sys
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))

try:
    from logger_setup import get_logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    get_logger = lambda name: logging.getLogger(name)

log = get_logger("pesquisa_temas")

try:
    from config import config
except ImportError:
    class FakeConfig:
        NICHO = "True Crime / Crimes Reais Brasileiros"
        SUB_NICHO = "Casos reais de crime no Brasil"
        DADOS_DIR = Path(__file__).parent.parent / "dados"
        GEMINI_MODEL = "gemini-3.8-flash"
    config = FakeConfig()

try:
    from ai_service import gerar_json
    AI_DISPONIVEL = True
except ImportError:
    AI_DISPONIVEL = False
    log.warning("ai_service nao encontrado — modo classificacao basica")


class PesquisadorTemas:
    """
    Agente de pesquisa de temas para Canal Dark.
    Busca de portais brasileiros e usa Gemini para classificar.
    """

    # Keywords de true crime que filtram conteúdo relevante
    PALAVRAS_CHAVE_CRIME = [
        "crime", "caso", "suspeito", "prisao", "policia", "investigacao",
        "morte", "assassinato", "desaparecimento", "traicao", "fraude",
        "corrupcao", "violencia", "vitima", "delito", "penal", "condenado",
        "estupro", "sequestro", "trafico", "assalto", "roubo", "homicidio",
        "mandado", "flagrante", "intimidacao", "ameaca", "arma", "municao",
    ]

    # Conteúdo sensacionalista a excluir
    EXCLUIR = [
        "futebol", "esporte", "celebridade", "famoso", "venda", "preco",
        "novelas", " BBB", "reality", "shows", "musica pop", "viral",
    ]

    def __init__(self, nicho: Optional[str] = None):
        self.nicho = nicho or config.NICHO
        self.sub_nicho = getattr(config, "SUB_NICHO", "")
        self.fila_path = config.DADOS_DIR / "fila_temas.json"
        self.historico_path = config.DADOS_DIR / "historico_temas.json"

    def buscar_noticias(self, fonte: Optional[str] = None, limite: int = 50) -> List[Dict]:
        """Busca notícias dos portais brasileiros."""
        try:
            from buscador_noticias import buscar_todas
            fontes = [fonte] if fonte else None
            return buscar_todas(fontes=fontes, max_resultados=limite)
        except ImportError:
            log.error("buscador_noticias.py nao encontrado")
            return []

    def classificar_temas(self, temas: List[Dict], limite_aprovados: int = 5) -> List[Dict]:
        """Usa Gemini para classificar e aprovar temas."""
        if not temas:
            return []

        if AI_DISPONIVEL:
            return self._classificar_com_gemini(temas, limite_aprovados)
        else:
            return self._classificar_basica(temas)

    def _classificar_com_gemini(self, temas: List[Dict], limite: int) -> List[Dict]:
        """Classifica temas usando Gemini (via ai_service)."""
        log.info(f"Classificando {len(temas)} temas com Gemini...")

        # Monta prompt de classificação
        temas_texto = "\n".join([
            f"{i+1}. [{t.get('fonte', 'N/A')}] {t.get('titulo', 'N/A')}"
            for i, t in enumerate(temas[:20])
        ])

        prompt = f"""Voce e o editor-chefe de um canal de YouTube Dark brasileiro especializado em True Crime.

NICHO: {self.nicho}
SUB_NICHO: {self.sub_nicho}

Analise os seguintes temas de noticias brasileiras e classifique cada um.
REGRAS DE APROVACAO:
- Score total >= 20 para ser aprovado
- Potencial de retencao >= 6 (drama, mistério, revelacao)
- Interesse brasileiro >= 6 (relevante para o publica BR)
- Viabilidade de pesquisa >= 5 (existem detalhes suficientes?)
- Angulo narrativo: drama humano, reviravoltas, elementos emocionais

TEMAS:
{temas_texto}

Responda APENAS em JSON:
{{
  "classificacoes": [
    {{
      "indice": 1,
      "titulo": "titulo revisado para YouTube (max 90 chars, com hook)",
      "potencial_retencao": 1-10,
      "interesse_brasileiro": 1-10,
      "viabilidade_pesquisa": 1-10,
      "score_total": numero,
      "angulo_roteiro": "angulo narrativo (2 linhas)",
      "aprovado": true/false,
      "motivo": "justificativa breve"
    }}
  ]
}}"""

        try:
            resultado = gerar_json(prompt=prompt, temperature=0.7, max_tokens=3000)
            classificacoes = resultado.get("classificacoes", [])

            # Mapeia classificações de volta aos temas
            aprovados = []
            for cls in classificacoes:
                idx = cls.get("indice", 1) - 1
                if idx < len(temas):
                    tema = temas[idx]
                    tema.update({
                        "potencial_retencao": cls.get("potencial_retencao", 0),
                        "interesse_brasileiro": cls.get("interesse_brasileiro", 0),
                        "viabilidade_pesquisa": cls.get("viabilidade_pesquisa", 0),
                        "score_total": cls.get("score_total", 0),
                        "angulo_roteiro": cls.get("angulo_roteiro", ""),
                        "aprovado": cls.get("aprovado", False),
                        "motivo": cls.get("motivo", ""),
                        "titulo": cls.get("titulo", tema.get("titulo", "")),
                    })
                    if cls.get("aprovado"):
                        aprovados.append(tema)

            log.info(f"Aprovados: {len(aprovados)} de {len(temas)}")
            return aprovados[:limite]

        except Exception as e:
            log.error(f"Erro na classificacao Gemini: {e}")
            return self._classificar_basica(temas)
    def _classificar_basica(self, temas: List[Dict]) -> List[Dict]:
        """Classificação básica por palavras-chave (fallback)."""
        aprovados = []
        for tema in temas:
            titulo = tema.get("titulo", "").lower()
            score = sum(1 for k in self.PALAVRAS_CHAVE_CRIME if k in titulo)
            if score >= 2:
                tema["score_total"] = score * 10
                tema["aprovado"] = True
                tema["angulo_roteiro"] = f"Documentario sobre: {tema.get('titulo', '')[:60]}"
                tema["motivo"] = "Aprovado por match de palavras-chave"
                aprovados.append(tema)
        return aprovados[:5]

    def executar(self, fonte: Optional[str] = None, limite: int = 50) -> Dict:
        """Executa pipeline completo de pesquisa."""
        log.info(f"Iniciando pesquisa de temas (fonte: {fonte or 'todas'})")

        # 1. Busca notícias
        temas = self.buscar_noticias(fonte=fonte, limite=limite)
        log.info(f"Noticias coletadas: {len(temas)}")

        if not temas:
            return {"sucesso": False, "erro": "Nenhuma noticia encontrada"}

        # 2. Classifica com Gemini
        aprovados = self.classificar_temas(temas)

        # 3. Salva na fila
        if aprovados:
            self._salvar_fila(aprovados)

        # 4. Salva no histórico
        self._salvar_historico(temas, aprovados)

        log.info(f"Temas aprovados: {len(aprovados)}")

        return {
            "sucesso": True,
            "temas": aprovados,
            "total_analisados": len(temas),
            "data_execucao": datetime.now(timezone.utc).isoformat()
        }

    def _salvar_fila(self, temas: List[Dict]):
        """Salva temas aprovados na fila de produção."""
        fila = []
        if self.fila_path.exists():
            try:
                fila = json.loads(self.fila_path.read_text(encoding="utf-8"))
            except Exception:
                fila = []

        existentes = {t.get("titulo", "")[:80] for t in fila if t.get("processado")}
        novos = 0

        for tema in temas:
            key = tema.get("titulo", "")[:80]
            if key not in existentes:
                tema["id"] = f"news_{datetime.now().strftime('%Y%m%d%H%M%S')}_{novos}"
                tema["status"] = "pendente"
                tema["data_selecao"] = datetime.now(timezone.utc).isoformat()
                fila.append(tema)
                existentes.add(key)
                novos += 1

        self.fila_path.parent.mkdir(parents=True, exist_ok=True)
        self.fila_path.write_text(json.dumps(fila, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info(f"Fila atualizada: {novos} novos temas (total: {len(fila)})")

    def _salvar_historico(self, temas: List[Dict], aprovados: List[Dict]):
        """Salva todos os temas analisados no histórico."""
        historico = []
        if self.historico_path.exists():
            try:
                historico = json.loads(self.historico_path.read_text(encoding="utf-8"))
            except Exception:
                historico = []

        historico.insert(0, {
            "data": datetime.now(timezone.utc).isoformat(),
            "total_coletados": len(temas),
            "aprovados": len(aprovados),
            "temas": temas[:20],  # salva só os top 20
        })

        # Mantém 30 dias de histórico
        historico = historico[:30]

        self.historico_path.parent.mkdir(parents=True, exist_ok=True)
        self.historico_path.write_text(json.dumps(historico, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Pesquisa de temas para Canal Dark")
    parser.add_argument("--fonte", type=str, default=None,
                        help="Fonte especifica (g1, uol, r7, cnn, folha)")
    parser.add_argument("--max", type=int, default=50, help="Maximo de noticias a buscar")
    parser.add_argument("--reddit", action="store_true",
                        help="Usar Reddit (requer credenciais API)")
    args = parser.parse_args()

    if args.reddit:
        log.info("Modo Reddit selecionado (requer REDDIT_CLIENT_ID e REDDIT_CLIENT_SECRET)")
        # Tenta importar e usar Reddit
        try:
            from reddit_service import RedditService
            reddit = RedditService()
            reddit_temas = reddit.get_trending_topics(niche="crime", limit=args.max)
            temas = [{"titulo": t.get("title", ""), "fonte": t.get("subreddit", ""),
                      "url": t.get("url", ""), "score": t.get("score", 0)} for t in reddit_temas]
            print(f"\n🔍 Reddit: {len(temas)} temas encontrados")
        except Exception as e:
            print(f"❌ Erro Reddit: {e}")
            return
    else:
        researcher = PesquisadorTemas()
        resultado = researcher.executar(fonte=args.fonte, limite=args.max)

        print("\n" + "="*60)
        print("  CANAL DARK — Resultado da Pesquisa de Temas")
        print("="*60)
        print(f"\nSucesso: {resultado.get('sucesso')}")
        print(f"Total analisados: {resultado.get('total_analisados', 0)}")

        if resultado.get("sucesso"):
            temas = resultado.get("temas", [])
            print(f"\n🎯 TEMAS APROVADOS ({len(temas)}):\n")
            for i, t in enumerate(temas, 1):
                print(f"  {i}. [{t.get('fonte', 'N/A')}] {t.get('titulo', 'N/A')[:70]}")
                print(f"     Score: {t.get('score_total', 0)} | {t.get('motivo', '')[:50]}")
                print()

        print("="*60)
        return resultado


if __name__ == "__main__":
    main()

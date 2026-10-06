"""
FASE 1 — Pesquisa de Temas (Fontes Brasileiras)

Busca notícias de true crime brasileiros usando Google News RSS.
Sem API key necessária — scraping direto.

Fontes:
  - Google News RSS (primária) — busca por termos de crime BR
  - G1, UOL, R7, CNN, Folha (secundárias/fallback)

Uso:
  python buscador_noticias.py                    # busca normal
  python buscador_noticias.py --fonte g1        # só Google News
  python buscador_noticias.py --max 30           # máximo 30 results
  python buscador_noticias.py --save             # salva em fila_temas.json
"""

import os
import sys
import json
import re
import argparse
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import html

# ─── Logger ───────────────────────────────────────────────────────────────────
try:
    from logger_setup import get_logger
except ImportError:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    get_logger = lambda name: logging.getLogger(name)

logger = get_logger("buscador_noticias")

# ─── Config ───────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).parent.parent
DADOS_DIR = PROJECT_ROOT / "dados"
FILA_PATH = DADOS_DIR / "fila_temas.json"
HISTORICO_PATH = DADOS_DIR / "historico_temas.json"

# ─── Queries do Google News ──────────────────────────────────────────────────
GOOGLE_NEWS_QUERIES = [
    ("crime", "crime+brasil"),
    ("assassinato", "assassinato+brasil"),
    ("polícia", "pol%C3%ADcia+brasil+morte"),
    ("investigação", "investiga%C3%A7%C3%A3o+crime+brasil"),
    ("desaparecimento", "desaparecimento+brasil"),
    ("fraude", "fraude+ corruption+brasil"),
    ("sequestro", "sequestro+brasil"),
    ("homicídio", "homic%C3%ADdio+brasil"),
    ("tráfico", "tr%C3%A1fico+drogas+brasil"),
    ("corrupção", "corrup%C3%A7%C3%A3o+brasil"),
]

# Keywords de true crime para filtrar conteúdo relevante
PALAVRAS_CHAVE_CRIME = [
    "crime", "caso", "suspeito", "prisão", "policia", "investigacao",
    "morte", "assassinato", "desaparecimento", "traicao", "fraude",
    "corrupcao", "violencia", "vitima", "delito", "penal", "condenado",
    "estupro", "sequestro", "trafico", "assalto", "roubo", "homicidio",
    "mandado", "flagrante", "intimidacao", "ameaça", "arma", "municao",
    "policia federal", "pf", "prisão", "condenado", "vítima", "traficante",
]

# Conteúdo sensacionalista a excluir
EXCLUIR = [
    "futebol", "esporte", "celebridade", "famoso", "venda", "preco",
    "novelas", "BBB", "reality", "shows", "musica pop", "viral",
    "eleição", "bets", "aposta", "enem", "vestibular",
]


def normalizar(texto: str) -> str:
    """Remove HTML entities e normaliza texto."""
    if not texto:
        return ""
    texto = html.unescape(texto)
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto


def buscar_google_news(query: str, hl: str = "pt-BR", gl: str = "BR") -> List[Dict]:
    """Busca notícias via Google News RSS com query customizada."""
    import urllib.parse
    q_encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q_encoded}&hl={hl}&gl={gl}&ceid=BR:pt-419"

    noticias = []
    try:
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        })
        with urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="ignore")

        root = ET.fromstring(content)
        items = root.findall('.//item')

        for item in items:
            title_el = item.find('title')
            link_el = item.find('link')
            pubdate_el = item.find('pubDate')
            desc_el = item.find('description')

            title = normalizar(title_el.text) if title_el is not None and title_el.text else ""
            link = link_el.text if link_el is not None and link_el.text else ""
            pubdate = pubdate_el.text if pubdate_el is not None and pubdate_el.text else ""
            desc = normalizar(desc_el.text) if desc_el is not None and desc_el.text else ""

            # Extrai fonte do título (formato: "Título - FONTE")
            fonte = "Google News"
            if " - " in title:
                fonte = title.rsplit(" - ", 1)[-1].strip()
                title = title.rsplit(" - ", 1)[0].strip()

            # Limpa link do Google News redirect
            if "/articles/" in link:
                link = re.sub(r"\?oc=\d+", "", link)
                link = re.sub(r".*url=", "", link)

            # Filtra por palavras-chave de crime
            title_lower = title.lower()
            desc_lower = desc.lower()
            combined = title_lower + " " + desc_lower

            if any(k.lower() in combined for k in PALAVRAS_CHAVE_CRIME):
                # Exclui sensacionalismo
                if not any(ex in title_lower or ex in desc_lower for ex in EXCLUIR):
                    noticias.append({
                        "titulo": title[:200],
                        "url": link,
                        "fonte": fonte,
                        "data": pubdate,
                        "descricao": desc[:300],
                    })

        logger.info(f"  Google News [{query}]: {len(noticias)} noticias")

    except HTTPError as e:
        logger.warning(f"  Google News [{query}] ERRO HTTP: {e.code}")
    except ET.ParseError as e:
        logger.warning(f"  Google News [{query}] ERRO XML: {e}")
    except Exception as e:
        logger.warning(f"  Google News [{query}] ERRO: {e}")

    return noticias


def buscar_todas(fontes: Optional[List[str]] = None, max_resultados: int = 50) -> List[Dict]:
    """Busca em todas as fontes (Google News como primária)."""
    todas = []

    # Primária: Google News (todas as queries)
    logger.info("Buscando no Google News RSS (fontes primária)...")
    for nome, query in GOOGLE_NEWS_QUERIES:
        noticias = buscar_google_news(query)
        todas.extend(noticias)

    # Remove duplicatas por título
    seen = set()
    unicas = []
    for n in todas:
        key = n["titulo"].lower()[:80]
        if key and key not in seen:
            seen.add(key)
            unicas.append(n)

    logger.info(f"Total único: {len(unicas)} noticias")

    # Limita resultados
    return unicas[:max_resultados]


def salvar_fila(temas: List[Dict], apenas_adicionar: bool = True):
    """Salva temas na fila de processamento."""
    DADOS_DIR.mkdir(parents=True, exist_ok=True)

    fila_existente = []
    if apenas_adicionar and FILA_PATH.exists():
        try:
            fila_existente = json.loads(FILA_PATH.read_text(encoding="utf-8"))
        except Exception:
            fila_existente = []

    existentes_ids = {t.get("titulo", "")[:80] for t in fila_existente}
    novos = []
    for t in temas:
        key = t["titulo"][:80]
        if key not in existentes_ids:
            t["data_busca"] = datetime.now().isoformat()
            t["status"] = "pendente"
            t["id"] = f"news_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(novos)}"
            novos.append(t)
            existentes_ids.add(key)

    fila_atualizada = fila_existente + novos
    FILA_PATH.write_text(json.dumps(fila_atualizada, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Fila atualizada: {len(novos)} novos temas (total: {len(fila_atualizada)})")
    return novos


def main():
    parser = argparse.ArgumentParser(description="Buscador de notícias true crime brasileiras")
    parser.add_argument("--fonte", type=str, default=None, help="Fonte específica (google, g1, uol, r7, cnn, folha)")
    parser.add_argument("--max", type=int, default=50, help="Máximo de resultados")
    parser.add_argument("--save", action="store_true", help="Salvar na fila de temas")
    parser.add_argument("--quiet", action="store_true", help="Modo silencioso")
    args = parser.parse_args()

    if not args.quiet:
        print("\n" + "=" * 60)
        print("  CANAL DARK — Busca de Notícias Brasileiras (Google News)")
        print("=" * 60 + "\n")

    temas = buscar_todas(fontes=None, max_resultados=args.max)

    if not args.quiet:
        print(f"\n> Encontrados {len(temas)} temas de crime:\n")
        for i, t in enumerate(temas[:15], 1):
            print(f"  {i:2d}. [{t['fonte']}] {t['titulo'][:80]}")

    if args.save:
        novos = salvar_fila(temas)
        print(f"\n> Salvos {len(novos)} novos temas na fila")

    if not args.quiet:
        print("\n" + "=" * 60)

    return temas


if __name__ == "__main__":
    main()

"""
FASE 1 — Pesquisa de Temas (Fontes Brasileiras)
Busca notícias de portais brasileiros para topics de true crime.

Fontes: G1 (Globo), UOL, R7, CNN Brasil, Folha
Sem API key necessária — usa scraping direto e RSS.

Uso:
  python buscador_noticias.py                    # busca normal
  python buscador_noticias.py --fonte g1       # só G1
  python buscador_noticias.py --max 30          # máximo 30 results
  python buscador_noticias.py --save            # salva em fila_temas.json
"""

import os
import sys
import json
import re
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta
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

# ─── Fontes de Crime Brasil ───────────────────────────────────────────────────
FONTES = {
    "g1": {
        "nome": "G1 (Globo)",
        "urls": [
            "https://g1.globo.com/brasil/",
            "https://g1.globo.com/sao-paulo/",
            "https://g1.globo.com/rj/rio-de-janeiro/",
            "https://g1.globo.com/mg/minas-gerais/",
            "https://g1.globo.com/pe/pernambuco/",
            "https://g1.globo.com/ba/bahia/",
        ],
        "tags": ["crime", "polícia", "investigação", "morte", "assassinato", "desaparecimento"],
    },
    "uol": {
        "nome": "UOL",
        "urls": [
            "https://noticias.uol.com.br/criminalidade/",
            "https://noticias.uol.com.br/brasil/",
        ],
        "tags": ["caso", "crime", "suspeito", "prisão", "polícia", "mortem", "fraude"],
    },
    "r7": {
        "nome": "R7",
        "urls": [
            "https://noticias.r7.com/brasil/",
            "https://noticias.r7.com/criminalidade",
        ],
        "tags": ["crime", "polícia", "caso", "morte", "suspeito", "investigação"],
    },
    "cnn": {
        "nome": "CNN Brasil",
        "urls": [
            "https://www.cnnbrasil.com.br/ategory/brasil/",
            "https://www.cnnbrasil.com.br/ategory/policia/",
        ],
        "tags": ["crime", "policia", "investigacao", "morte", "caso", "justica"],
    },
    "folha": {
        "nome": "Folha de S.Paulo",
        "urls": [
            "https://www.folha.uol.com.br/criminalidade/",
            "https://www.folha.uol.com.br/brasil/",
        ],
        "tags": ["crime", "caso", "suspeito", "policia", "morte", "violencia"],
    },
}

# Keywords de true crime que filtram conteúdo relevante
PALAVRAS_CHAVE_CRIME = [
    "crime", "caso", "suspeito", "prisão", "policia", "investigacao",
    "morte", "assassinato", "desaparecimento", "traicao", "fraude",
    "corrupcao", "violencia", "vitima", "delito", "penal", "condenado",
    "estupro", "sequestro", "trafico", "assalto", "roubo", "homicidio",
    "mandado", "flagrante", "intimidacao", "ameaca", "arma", "municao",
]

# Keywords que EXCLUEM conteúdo (evitar Sensacionalismo)
EXCLUIR = [
    "futebol", "esporte", "celebridade", "famoso", "venda", "preco",
    "celebridade", "novelas", " BBB", "reality", "shows", "musica pop",
]


def normalizar(texto: str) -> str:
    """Remove HTML entities e normaliza texto."""
    if not texto:
        return ""
    texto = html.unescape(texto)
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto


def buscar_g1() -> List[Dict]:
    """Busca notícias do G1 via RSS/HTML."""
    noticias = []
    for url in FONTES["g1"]["urls"]:
        try:
            req = Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; CanalDarkBot/1.0; +https://canaldark.com)",
                "Accept": "application/rss+xml, application/xml, text/html",
            })
            with urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="ignore")

            # Tenta RSS
            if "<rss" in content.lower() or "<feed" in content.lower():
                titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', content)
                links = re.findall(r'<link>(https?://g1\.globo\.com/.*?)</link>', content)
                descriptions = re.findall(r'<description><!\[CDATA\[(.*?)\]\]></description>', content)
                pubdates = re.findall(r'<pubDate>(.*?)</pubDate>', content)

                for i, titulo in enumerate(titles[1:], 0):  # pula primeiro (nome do canal)
                    if any(k.lower() in titulo.lower() for k in PALAVRAS_CHAVE_CRIME):
                        noticias.append({
                            "titulo": normalizar(titulo),
                            "url": links[i] if i < len(links) else "",
                            "fonte": "G1 (Globo)",
                            "data": pubdates[i] if i < len(pubdates) else "",
                            "descricao": normalizar(descriptions[i] if i < len(descriptions) else ""),
                        })
            else:
                # HTML parsing fallback
                titles = re.findall(r'<a[^>]+class="feed-post-link"[^>]*>([^<]+)<', content)
                links = re.findall(r'<a[^>]+class="feed-post-link"[^>]+href="(https://g1\.globo\.com/[^"]+)"', content)
                for i, titulo in enumerate(titles):
                    if any(k.lower() in titulo.lower() for k in PALAVRAS_CHAVE_CRIME):
                        noticias.append({
                            "titulo": normalizar(titulo),
                            "url": links[i] if i < len(links) else "",
                            "fonte": "G1 (Globo)",
                            "data": "",
                            "descricao": "",
                        })
            logger.info(f"  G1 OK: {len(noticias)} noticias de {url}")
        except Exception as e:
            logger.warning(f"  G1 ERRO em {url}: {e}")
    return noticias


def buscar_uol() -> List[Dict]:
    """Busca notícias do UOL."""
    noticias = []
    for url in FONTES["uol"]["urls"]:
        try:
            req = Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; CanalDarkBot/1.0)",
            })
            with urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="ignore")

            # RSS UOL
            titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', content)
            links = re.findall(r'<link>(https://noticias\.uol\.com\.br/[^<]+)</link>', content)
            descriptions = re.findall(r'<description><!\[CDATA\[(.*?)\]\]></description>', content)

            for i, titulo in enumerate(titles[1:], 0):
                if any(k.lower() in titulo.lower() for k in PALAVRAS_CHAVE_CRIME):
                    noticias.append({
                        "titulo": normalizar(titulo),
                        "url": links[i] if i < len(links) else "",
                        "fonte": "UOL",
                        "data": "",
                        "descricao": normalizar(descriptions[i] if i < len(descriptions) else ""),
                    })
            logger.info(f"  UOL OK: {len(noticias)} noticias de {url}")
        except Exception as e:
            logger.warning(f"  UOL ERRO em {url}: {e}")
    return noticias


def buscar_r7() -> List[Dict]:
    """Busca notícias do R7."""
    noticias = []
    for url in FONTES["r7"]["urls"]:
        try:
            req = Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; CanalDarkBot/1.0)",
            })
            with urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="ignore")

            titles = re.findall(r'<title>(.*?)</title>', content)
            links = re.findall(r'<link>(https://noticias\.r7\.com/[^<]+)</link>', content)

            for i, titulo in enumerate(titles):
                t = normalizar(titulo)
                if "r7" in t.lower() or "notícias" in t.lower():
                    continue
                if any(k.lower() in t.lower() for k in PALAVRAS_CHAVE_CRIME):
                    noticias.append({
                        "titulo": t,
                        "url": links[i] if i < len(links) else "",
                        "fonte": "R7",
                        "data": "",
                        "descricao": "",
                    })
            logger.info(f"  R7 OK: {len(noticias)} noticias de {url}")
        except Exception as e:
            logger.warning(f"  R7 ERRO em {url}: {e}")
    return noticias


def buscar_cnn() -> List[Dict]:
    """Busca notícias da CNN Brasil."""
    noticias = []
    for url in FONTES["cnn"]["urls"]:
        try:
            req = Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; CanalDarkBot/1.0)",
            })
            with urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="ignore")

            titles = re.findall(r'<title>(.*?)</title>', content)
            links = re.findall(r'<link>(https://www\.cnnbrasil\.com\.br/[^<]+)</link>', content)
            descriptions = re.findall(r'<description>(.*?)</description>', content)

            for i, titulo in enumerate(titles):
                t = normalizar(titulo)
                if "cnn" in t.lower() or "brasil" == t.lower():
                    continue
                if any(k.lower() in t.lower() for k in PALAVRAS_CHAVE_CRIME):
                    noticias.append({
                        "titulo": t,
                        "url": links[i] if i < len(links) else "",
                        "fonte": "CNN Brasil",
                        "data": "",
                        "descricao": normalizar(descriptions[i] if i < len(descriptions) else ""),
                    })
            logger.info(f"  CNN OK: {len(noticias)} noticias de {url}")
        except Exception as e:
            logger.warning(f"  CNN ERRO em {url}: {e}")
    return noticias


def buscar_folha() -> List[Dict]:
    """Busca notícias da Folha de S.Paulo."""
    noticias = []
    for url in FONTES["folha"]["urls"]:
        try:
            req = Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; CanalDarkBot/1.0)",
            })
            with urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="ignore")

            titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', content)
            links = re.findall(r'<link>(https://www\.folha\.uol\.com\.br/[^<]+)</link>', content)

            for i, titulo in enumerate(titles[1:], 0):
                if any(k.lower() in titulo.lower() for k in PALAVRAS_CHAVE_CRIME):
                    noticias.append({
                        "titulo": normalizar(titulo),
                        "url": links[i] if i < len(links) else "",
                        "fonte": "Folha de S.Paulo",
                        "data": "",
                        "descricao": "",
                    })
            logger.info(f"  Folha OK: {len(noticias)} noticias de {url}")
        except Exception as e:
            logger.warning(f"  Folha ERRO em {url}: {e}")
    return noticias


def buscar_todas(fontes: Optional[List[str]] = None, max_resultados: int = 50) -> List[Dict]:
    """Busca em todas as fontes configuradas."""
    if fontes is None:
        fontes = list(FONTES.keys())

    todas = []

    fetchers = {
        "g1": buscar_g1,
        "uol": buscar_uol,
        "r7": buscar_r7,
        "cnn": buscar_cnn,
        "folha": buscar_folha,
    }

    for fonte in fontes:
        if fonte in fetchers:
            logger.info(f"Buscando em {FONTES[fonte]['nome']}...")
            noticias = fetchers[fonte]()
            todas.extend(noticias)

    # Remove duplicatas por título
    seen = set()
    unicas = []
    for n in todas:
        key = n["titulo"].lower()[:80]
        if key and key not in seen:
            seen.add(key)
            # Exclui conteúdos sensacionalistas
            if not any(excluir.lower() in n["titulo"].lower() for excluir in EXCLUIR):
                unicas.append(n)

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

    # Adiciona timestamp e dedup
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
    parser.add_argument("--fonte", type=str, default=None, help="Fonte específica (g1, uol, r7, cnn, folha)")
    parser.add_argument("--max", type=int, default=50, help="Máximo de resultados")
    parser.add_argument("--save", action="store_true", help="Salvar na fila de temas")
    parser.add_argument("--quiet", action="store_true", help="Modo silencioso")
    args = parser.parse_args()

    if not args.quiet:
        print("\n" + "="*60)
        print("  CANAL DARK — Busca de Notícias Brasileiras")
        print("="*60 + "\n")

    fontes = [args.fonte] if args.fonte else None
    temas = buscar_todas(fontes=fontes, max_resultados=args.max)

    if not args.quiet:
        print(f"\n🔍 Encontrados {len(temas)} temas de crime:\n")
        for i, t in enumerate(temas[:15], 1):
            print(f"  {i:2d}. [{t['fonte']}] {t['titulo'][:80]}")

    if args.save:
        novos = salvar_fila(temas)
        print(f"\n💾 Salvos {len(novos)} novos temas na fila")

    if not args.quiet:
        print("\n" + "="*60)

    return temas


if __name__ == "__main__":
    main()

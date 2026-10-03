"""
Phase 5: Montador de Vídeo — assembler de vídeo automatizado
Combina imagens + narração + música + efeitos → MP4 final

Dependências: moviepy, Pillow, ffmpeg (install via conda/brew or download binary)
pip install moviepy Pillow

Entrada:  resultado_{video_id}.json (do roteirizador)
Saída:    video_final_{video_id}.mp4
"""

import json
import os
import sys
import subprocess
import re
from pathlib import Path
from datetime import datetime

# ─── Config ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
DATOS_DIR = PROJECT_ROOT / "dados"
PROJETOS_DIR = PROJECT_ROOT / "projetos"
OUTPUT_DIR = PROJECT_ROOT / "output"
FONT_PATH = "C:\\Windows\\Fonts\\arial.ttf"  # Windows; ajuste para Linux/Mac

# ─── Logger ───────────────────────────────────────────────────────────────────
try:
    from logger_setup import get_logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    get_logger = lambda name: logging.getLogger(name)

logger = get_logger("montador_video")


# ─── Verifica FFmpeg ──────────────────────────────────────────────────────────
def verificar_ffmpeg():
    """Confirma que ffmpeg está no PATH."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            version_line = result.stdout.split("\n")[0]
            logger.info(f"FFmpeg disponível: {version_line}")
            return True
    except Exception:
        pass
    logger.warning(
        "FFmpeg não encontrado. Instale: https://ffmpeg.org/download.html\n"
        "No Windows: winget install ffmpeg  ou  choco install ffmpeg\n"
        "No Linux: sudo apt install ffmpeg"
    )
    return False


# ─── Helpers de texto ─────────────────────────────────────────────────────────
def hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def criar_thumbnail_texto(
    texto: str,
    caminho_saida: Path,
    tamanho=(1920, 1080),
    cor_fundo="#0D0D0D",
    cor_texto="#E63946",
    tamanho_fonte=72,
    overlay_alpha=200,
):
    """Gera thumbnail com texto centralizado usando Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", tamanho, hex_to_rgb(cor_fundo))
    draw = ImageDraw.Draw(img)

    # Font
    try:
        fonte = ImageFont.truetype(FONT_PATH, tamanho_fonte)
    except Exception:
        fonte = ImageFont.load_default()

    # Word-wrap
    palavras = texto.split()
    linhas = []
    linha_atual = ""
    max_largura = int(tamanho[0] * 0.85)
    for palavra in palavras:
        teste = (linha_atual + " " + palavra).strip()
        bbox = draw.textbbox((0, 0), teste, font=fonte)
        if bbox[2] - bbox[0] <= max_largura:
            linha_atual = teste
        else:
            if linha_atual:
                linhas.append(linha_atual)
            linha_atual = palavra
    if linha_atual:
        linhas.append(linha_atual)

    # Desenha linhas
    altura_linha = tamanho_fonte + 20
    total_altura = len(linhas) * altura_linha
    y_inicio = (tamanho[1] - total_altura) // 2

    for i, linha in enumerate(linhas):
        bbox = draw.textbbox((0, 0), linha, font=fonte)
        largura_texto = bbox[2] - bbox[0]
        x = (tamanho[0] - largura_texto) // 2
        draw.text((x, y_inicio + i * altura_linha), linha, font=fonte, fill=hex_to_rgb(cor_texto))

    # Borda decorativa
    margem = 20
    draw.rectangle(
        [margem, margem, tamanho[0] - margem, tamanho[1] - margem],
        outline=hex_to_rgb(cor_texto),
        width=4,
    )

    img.save(caminho_saida, "PNG")
    logger.debug(f"Thumbnail criado: {caminho_saida}")


# ─── Download /预备音频时长 ───────────────────────────────────────────────────
def get_audio_duration(caminho_audio: Path) -> float:
    """Retorna duração do arquivo de áudio em segundos via ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(caminho_audio),
            ],
            capture_output=True, text=True, timeout=30,
        )
        return float(result.stdout.strip())
    except Exception as e:
        logger.warning(f"Não foi possível ler duração do áudio: {e}")
        return 0.0


# ─── Gerador de clipe de segmento ─────────────────────────────────────────────
def gerar_clipe_segmento(
    caminho_imagem: Path,
    caminho_audio: Path,
    caminho_saida: Path,
    duracao: float,
    efeito="kenburns",
    zoom_inicial=1.0,
    zoom_final=1.15,
    fade_duration=0.8,
):
    """
    Gera um clipe de vídeo: imagem com Ken Burns + crossfade áudio.
    Usa ffmpeg diretamente (moviepy é lento e instável no Windows).

    efeito: 'kenburns' | 'estatico' | 'pan'
    """
    if not caminho_imagem.exists():
        logger.warning(f"Imagem não encontrada: {caminho_imagem}, usando placeholder")
        # Cria placeholder escuro
        img = Image.new("RGB", (1920, 1080), (13, 13, 13))
        img.save(caminho_imagem)

    zoom_inicial_str = f"{zoom_inicial:.3f}"
    # Ken Burns: zoom progressivo + pan leve
    zoom_tempo = f"zoompan=z='min(zoom_in+zoom_delta, {zoom_final:.3f})':d={int(duracao*30)}:s=1920x1080"

    # Filtros de vídeo
    vf_parts = [
        f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        f"'{zoom_tempo}'",
        f"fade=t=in:st=0:d={fade_duration}:alpha=1",
        f"fade=t=out:st={duracao - fade_duration}:d={fade_duration}:alpha=1",
    ]
    vf = ",".join(vf_parts)

    # Áudio com fade
    af = f"afade=t=in:st=0:d=0.5:volume=0,afade=t=out:st={duracao - 1.0}:d=1.0:volume=0"

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(caminho_imagem),
        "-i", str(caminho_audio),
        "-t", str(duracao),
        "-vf", vf,
        "-af", af,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(caminho_saida),
    ]

    logger.debug(f"FFmpeg cmd: {' '.join(cmd)}")
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=int(duracao) + 30,
    )
    if result.returncode != 0:
        logger.error(f"FFmpeg erro:\n{result.stderr[-1000:]}")
        return False
    return True


# ─── Concatenação final ───────────────────────────────────────────────────────
def concatenar_clipes(
    caminhos_clipes: list[Path],
    caminho_musica: Path | None,
    caminho_saida: Path,
    volume_musica=0.18,
    volume_narracao=1.0,
    crossfade_duration=1.0,
):
    """Concatena clips em um único vídeo com música de fundo e transições."""

    # Lista temporária de clips com áudio mixado
    nome_lista = DATOS_DIR / "lista_concat.txt"
    with open(nome_lista, "w") as f:
        for c in caminhos_clipes:
            f.write(f"file '{c.absolute()}'\n")

    # Concatenar sem música primeiro
    tmp_sem_musica = OUTPUT_DIR / "tmp_sem_musica.mp4"
    cmd_concat = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(nome_lista),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(tmp_sem_musica),
    ]
    result = subprocess.run(cmd_concat, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        logger.error(f"Erro na concatenação:\n{result.stderr[-1000:]}")
        raise RuntimeError("Falha ao concatenar clips")

    # Adicionar música de fundo
    if muscia_exists := caminho_musica and caminho_musica.exists():
        cmd_mix = [
            "ffmpeg", "-y",
            "-i", str(tmp_sem_musica),
            "-i", str(caminho_musica),
            "-filter_complex",
            f"[0:a]volume={volume_narracao}[nar];[1:a]volume={volume_musica}[mus];"
            f"[nar][mus]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            str(caminho_saida),
        ]
    else:
        logger.info("Música de fundo não encontrada — exportando sem música")
        tmp_sem_musica.rename(caminho_saida)
        return

    result = subprocess.run(cmd_mix, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        logger.error(f"Erro ao misturar música:\n{result.stderr[-1000:]}")
        tmp_sem_musica.rename(caminho_saida)
    else:
        tmp_sem_musica.unlink(missing_ok=True)

    nome_lista.unlink(missing_ok=True)


# ─── Gerar intro/outro固定 ───────────────────────────────────────────────────
def gerar_intro(
    caminho_saida: Path,
    titulo: str,
    duracao=5.0,
    cor_fundo="#0A0A0A",
    cor_titulo="#E63946",
):
    """Gera intro fixa com título do vídeo."""
    criar_thumbnail_texto(
        texto=titulo,
        caminho_saida=caminho_saida.with_suffix(".png"),
        tamanho=(1920, 1080),
        cor_fundo=cor_fundo,
        cor_texto=cor_titulo,
        tamanho_fonte=80,
    )
    # Converte PNG + silêncio → MP4
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(caminho_saida.with_suffix(".png")),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", str(duracao),
        "-vf", "scale=1920:1080,fade=t=in:st=0:d=1.0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(caminho_saida),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        logger.info(f"Intro gerada: {caminho_saida}")
    else:
        logger.warning(f"Intro falhou: {result.stderr[-500:]}")


# ─── Pipeline principal ──────────────────────────────────────────────────────
def montar_video(
    video_id: str,
    projeto_dir: Path | None = None,
    with_intro: bool = True,
    with_outro: bool = True,
    crossfade: float = 1.0,
) -> Path | None:
    """
    Orquestra toda a montagem:
      1. Lê o JSON do roteiro
      2. Gera intro (se aplicável)
      3. Para cada segmento: gera clipe com imagem + narração
      4. Concatenar tudo + música de fundo
      5. Exporta video_final_{video_id}.mp4
    """
    if projeto_dir is None:
        projeto_dir = PROJETOS_DIR / video_id

    roteiro_path = projeto_dir / f"resultado_{video_id}.json"
    if not roteiro_path.exists():
        logger.error(f"Roteiro não encontrado: {roteiro_path}")
        return None

    with open(roteiro_path, "r", encoding="utf-8") as f:
        roteiro = json.load(f)

    OUTPUT_DIR.mkdir(exist_ok=True)
    projeto_dir.mkdir(exist_ok=True)

    logger.info(f"Iniciando montagem: {video_id} — '{roteiro.get('titulo', 'sem titulo')}'")

    # ── 1. Intro ──────────────────────────────────────────────────────────────
    clips_ordenados = []

    if with_intro:
        intro_path = projeto_dir / "intro.mp4"
        gerar_intro(
            caminho_saida=intro_path,
            titulo=roteiro.get("titulo", ""),
            duracao=5.0,
        )
        if intro_path.exists():
            clips_ordenados.append(intro_path)

    # ── 2. Segmentos ──────────────────────────────────────────────────────────
    segmentos = roteiro.get("segmentos", [])
    if not segmentos:
        logger.error("Nenhum segmento encontrado no roteiro")
        return None

    pasta_imagens = projeto_dir / "imagens"
    pasta_audio = projeto_dir / "audio"
    pasta_clipes = projeto_dir / "clipes"
    pasta_clipes.mkdir(exist_ok=True)

    for i, seg in enumerate(segmentos):
        nome_arquivo = seg.get("nome_arquivo", f"seg_{i:02d}")
        caminho_imagem = pasta_imagens / f"{nome_arquivo}.png"
        caminho_audio = pasta_audio / f"{nome_arquivo}.mp3"
        caminho_clipe = pasta_clipes / f"{nome_arquivo}.mp4"

        if not caminho_audio.exists():
            logger.warning(f"Áudio não encontrado: {caminho_audio}, pulando segmento {i}")
            continue

        duracao = get_audio_duration(caminho_audio)
        if duracao <= 0:
            duracao = seg.get("duracao_estimada_seg", 30.0)

        logger.info(f"  Processando segmento {i+1}/{len(segmentos)}: {nome_arquivo} ({duracao:.1f}s)")

        ok = gerar_clipe_segmento(
            caminho_imagem=caminho_imagem,
            caminho_audio=caminho_audio,
            caminho_saida=caminho_clipe,
            duracao=duracao,
            efeito="kenburns",
            zoom_inicial=1.0,
            zoom_final=1.12,
            fade_duration=0.6,
        )
        if ok and caminho_clipe.exists():
            clips_ordenados.append(caminho_clipe)

    if not clips_ordenados:
        logger.error("Nenhum clipe gerado")
        return None

    # ── 3. Música de fundo ─────────────────────────────────────────────────────
    # Procura música na pasta do projeto ou na pasta de assets
    musica_opcoes = [
        projeto_dir / "musica_fundo.mp3",
        DATOS_DIR / "musica_fundo.mp3",
        PROJECT_ROOT / "assets" / "musica_fundo.mp3",
    ]
    musica_path = None
    for m in musica_opcoes:
        if m.exists():
            musica_path = m
            break

    if musica_path:
        logger.info(f"Música de fundo: {musica_path.name}")
    else:
        logger.info("Música de fundo não encontrada (opcional)")

    # ── 4. Concatenação final ─────────────────────────────────────────────────
    nome_saida = f"video_final_{video_id}.mp4"
    caminho_saida = OUTPUT_DIR / nome_saida

    concatenar_clipes(
        caminhos_clipes=clips_ordenados,
        caminho_musica=musica_path,
        caminho_saida=caminho_saida,
        volume_musica=0.18,
        volume_narracao=1.0,
        crossfade_duration=crossfade,
    )

    if caminho_saida.exists():
        tamanho_mb = caminho_saida.stat().st_size / (1024 * 1024)
        logger.info(f"✅ Vídeo final gerado: {caminho_saida} ({tamanho_mb:.1f} MB)")
        return caminho_saida
    else:
        logger.error("Falha ao gerar vídeo final")
        return None


# ─── Script standalone ────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not verificar_ffmpeg():
        sys.exit(1)

    import argparse

    parser = argparse.ArgumentParser(description="Montador de vídeo automatizado")
    parser.add_argument("video_id", help="ID do projeto (nome da pasta em projetos/)")
    parser.add_argument("--no-intro", action="store_true", help="Pular intro")
    parser.add_argument("--no-outro", action="store_true", help="Pular outro")
    args = parser.parse_args()

    resultado = montar_video(
        video_id=args.video_id,
        with_intro=not args.no_intro,
        with_outro=not args.no_outro,
    )
    if resultado:
        print(f"\n✅ Sucesso: {resultado}")
    else:
        print("\n❌ Falha na montagem")
        sys.exit(1)

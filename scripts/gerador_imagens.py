"""
FASE 4 — Geração de Imagens e Visuais

Gera imagens atmosféricas para cada segmento do roteiro.
Usa DALL-E 3 (via OpenAI) ou Canva como fallback.

Uso: python gerador_imagens.py --roteiro projeto/roteiro.json [--projeto ProjetoX]
"""
import os
import sys
import json
import base64
import argparse
from pathlib import Path
from typing import Dict, List
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from logger_setup import get_logger
from config import config
from ai_service import ai_service

log = get_logger("gerador_imagens")


class GeradorImagens:
    """
    Gera imagens atmosféricas para vídeos de True Crime.
    Cada segmento do roteiro recebe uma imagem descritiva.
    """
    
    # Paleta de cores para o nicho dark
    PALETA_DARK = "dark, noir, atmospheric, moody lighting, cinematic, high contrast, deep shadows, film grain"
    
    # Descrições de estilo por segmento
    ESTILOS = {
        "GANCHO": "dark screen with subtle text appearing, minimalist, eerie atmosphere, near darkness with single point of light",
        "CONTEXTO": "establishing shot, Brazilian urban setting at night, subtle tension, noir aesthetic, rain",
        "DESENVOLVIMENTO": "atmospheric scene, moody lighting, shadows, tension-building imagery, cinematic composition",
        "CLIMAX": "dramatic lighting, high contrast, dark atmosphere, revelation moment, suspense",
        "ENCERRAMENTO": "calm dark scene, resolution atmosphere, quiet tension remains, cinematic fade"
    }
    
    def __init__(self, projeto_dir: Path):
        self.projeto_dir = Path(projeto_dir)
        self.imagens_dir = self.projeto_dir / "imagens"
        self.imagens_dir.mkdir(parents=True, exist_ok=True)
    
    def gerar_visuais(self, roteiro_path: Path) -> Dict:
        """
        Gera imagens para cada segmento do roteiro.
        
        Returns:
            Dict com paths das imagens geradas
        """
        with open(roteiro_path, "r", encoding="utf-8") as f:
            roteiro = json.load(f)
        
        segmentos = roteiro.get("roteiro", [])
        log.info(f"Gerando {len(segmentos)} imagens")
        
        imagens = []
        
        for i, seg in enumerate(segmentos):
            segmento_nome = seg["segmento"]
            visual_sugerido = seg.get("visual", "")
            texto_narracao = seg.get("texto", "")[:100]
            
            # Monta prompt
            prompt = self._montar_prompt(segmento_nome, visual_sugerido, texto_narracao)
            
            # Gera imagem
            nome_arquivo = f"img_{i:02d}_{segmento_nome.lower()}.png"
            caminho_imagem = self.imagens_dir / nome_arquivo
            
            sucesso = self._gerar_dalle(prompt, caminho_imagem)
            
            if sucesso:
                imagens.append({
                    "segmento": segmento_nome,
                    "timecode_inicio": seg["timecode_inicio"],
                    "arquivo": str(caminho_imagem),
                    "prompt_usado": prompt[:200]
                })
                log.info(f"  [{i+1}/{len(segmentos)}] {segmento_nome} → {nome_arquivo}")
            else:
                # Fallback: gera imagem placeholder escura
                self._gerar_placeholder(caminho_imagem)
                imagens.append({
                    "segmento": segmento_nome,
                    "timecode_inicio": seg["timecode_inicio"],
                    "arquivo": str(caminho_imagem),
                    "prompt_usado": "placeholder dark"
                })
        
        # Gera thumbnail
        thumbnail_path = self.imagens_dir / "thumbnail.png"
        self._gerar_thumbnail(roteiro, thumbnail_path)
        
        return {
            "sucesso": True,
            "projeto": str(self.projeto_dir.name),
            "imagens": imagens,
            "thumbnail": str(thumbnail_path),
            "total_geradas": len([i for i in imagens if "placeholder" not in i.get("prompt_usado", "")])
        }
    
    def _montar_prompt(self, segmento: str, visual: str, texto: str) -> str:
        """Monta prompt de geração de imagem."""
        
        estilo = self.ESTILOS.get(segmento, self.ESTILOS["DESENVOLVIMENTO"])
        
        # Extrai elementos do visual sugerido
        elementos = []
        if visual:
            # Limpa e simplifica a descrição
            visual_limpo = visual.replace("🎬", "").strip()
            elementos.append(visual_limpo)
        
        # Adiciona contexto do texto
        if texto:
            elementos.append(texto[:80])
        
        contexto = " | ".join(elementos) if elementos else estilo
        
        prompt = f"""
True Crime documentary style image for YouTube video.
{contexto}

Style requirements:
- {estilo}
- Dark color palette: blacks, deep blues, muted reds
- No text, no faces, no people identifiable
- Cinematic composition, 16:9 aspect ratio
- High quality, photorealistic or high quality 3D render
- No logos, no watermarks, no brand names
- Brazilian crime documentary aesthetic
- Maximum atmosphere and tension
- Ultra detailed, 4K quality
""".strip()
        
        return prompt
    
    def _gerar_dalle(self, prompt: str, output_path: Path) -> bool:
        """Gera imagem usando DALL-E 3 ou Imagen 3 via ai_service."""
        try:
            image_path = ai_service.gerar_imagem(
                prompt=prompt,
                output_path=str(output_path),
                size="1792x1024"
            )
            if image_path and Path(image_path).exists():
                log.debug(f"Imagem gerada: {output_path}")
                return True
            return False
        except Exception as e:
            log.error(f"Erro geração de imagem: {e}")
            return False
    
    def _gerar_placeholder(self, output_path: Path):
        """Gera imagem placeholder escura quando DALL-E falha."""
        try:
            from PIL import Image
            
            # Cria imagem 1920x1080 preta
            img = Image.new("RGB", (1920, 1080), color=(10, 10, 15))
            
            # Adiciona gradiente sutil
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)
            
            # Gradiente do centro (muito sutil)
            for y in range(1080):
                alpha = int(5 * (1 - abs(y - 540) / 540))
                draw.line([(0, y), (1920, y)], fill=(20, 20, 30 + alpha))
            
            img.save(output_path, "PNG")
            log.debug(f"Placeholder gerado: {output_path}")
            
        except Exception as e:
            log.error(f"Erro ao gerar placeholder: {e}")
    
    def _gerar_thumbnail(self, roteiro: Dict, output_path: Path):
        """Gera thumbnail chamativo para o vídeo."""
        
        tema = roteiro.get("metadata", {}).get("tema", "Canal Dark")
        gancho = roteiro.get("metadata", {}).get("gancho_original", "")[:60]
        
        # Tenta gerar via DALL-E 3 ou Imagen 3
        prompt = f"""
True Crime documentary YouTube thumbnail.
A dark, atmospheric scene with dramatic lighting.
Title text overlay (in Portuguese): "{tema[:40]}"
Subtitle: "Caso Real | Investigação"

Style:
- Very dark background with dramatic single light source
- High contrast red and black color scheme
- Bold white/yellow text
- Mysterious, tense atmosphere
- 16:9 aspect ratio
- No faces visible, no identifiable people
- Maximum visual impact, click-worthy
- Brazilian documentary aesthetic
- 4K quality
""".strip()

        try:
            image_path = ai_service.gerar_imagem(
                prompt=prompt,
                output_path=str(output_path),
                size="1792x1024"
            )
            if image_path and Path(image_path).exists():
                log.info(f"Thumbnail gerado: {output_path}")
                return
        except Exception as e:
            log.warning(f"Erro thumbnail IA: {e}")
        
        # Fallback: thumbnail com PIL
        self._gerar_thumbnail_pil(tema, gancho, output_path)
    
    def _gerar_thumbnail_pil(self, tema: str, gancho: str, output_path: Path):
        """Gera thumbnail básico com PIL como fallback."""
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            img = Image.new("RGB", (1920, 1080), color=(10, 5, 5))
            draw = ImageDraw.Draw(img)
            
            # Fundo com gradiente vermelho escuro
            for x in range(1920):
                alpha = int(30 * (x / 1920))
                draw.line([(x, 0), (x, 1080)], fill=(40 + alpha, 10, 10 + alpha // 2))
            
            # Linha decorativa superior
            draw.rectangle([(0, 0), (1920, 8)], fill=(139, 0, 0))
            
            # Texto principal
            try:
                fonte_titulo = ImageFont.truetype("arial.ttf", 72)
                fonte_sub = ImageFont.truetype("arial.ttf", 36)
            except:
                fonte_titulo = ImageFont.load_default()
                fonte_sub = ImageFont.load_default()
            
            # Quebra linha se necessário
            palavras = tema.split()
            linhas = []
            linha_atual = ""
            for p in palavras:
                if len(linha_atual + " " + p) <= 20:
                    linha_atual += (" " + p if linha_atual else p)
                else:
                    linhas.append(linha_atual)
                    linha_atual = p
            if linha_atual:
                linhas.append(linha_atual)
            
            y_pos = 350
            for linha in linhas[:3]:
                bbox = draw.textbbox((0, 0), linha, font=fonte_titulo)
                texto_w = bbox[2] - bbox[0]
                x_pos = (1920 - texto_w) // 2
                draw.text((x_pos, y_pos), linha, font=fonte_titulo, fill=(255, 255, 255))
                y_pos += 85
            
            # Subtítulo
            subtexto = "CASO REAL | INVESTIGAÇÃO"
            bbox = draw.textbbox((0, 0), subtexto, font=fonte_sub)
            x_pos = (1920 - (bbox[2] - bbox[0])) // 2
            draw.text((x_pos, y_pos + 30), subtexto, font=fonte_sub, fill=(200, 50, 50))
            
            img.save(output_path, "PNG")
            log.info(f"Thumbnail PIL gerado: {output_path}")
            
        except Exception as e:
            log.error(f"Erro thumbnail PIL: {e}")


def main():
    parser = argparse.ArgumentParser(description="Geração de imagens")
    parser.add_argument("--roteiro", type=str, required=True, help="Caminho do arquivo roteiro.json")
    parser.add_argument("--projeto", type=str, default=None, help="Nome do projeto")
    args = parser.parse_args()
    
    roteiro_path = Path(args.roteiro)
    if not roteiro_path.exists():
        print(f"❌ Roteiro não encontrado: {roteiro_path}")
        return
    
    projeto_dir = roteiro_path.parent
    if args.projeto:
        projeto_dir = config.get_projeto_dir(args.projeto)
    
    gerador = GeradorImagens(projeto_dir)
    resultado = gerador.gerar_visuais(roteiro_path)
    
    if resultado["sucesso"]:
        print(f"\n✅ Imagens geradas!")
        print(f"   Total: {resultado['total_geradas']}/{len(resultado['imagens'])}")
        print(f"   Thumbnail: {resultado['thumbnail']}")
    else:
        print(f"❌ Erro: {resultado.get('erro')}")
    
    return resultado


if __name__ == "__main__":
    main()

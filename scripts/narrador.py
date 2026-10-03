"""
FASE 3 — Narração

Converte roteiro em áudio usando ElevenLabs (voz sintética).
Suporta Google TTS como fallback.

Uso: python narrador.py --roteiro projeto/roteiro.json [--projeto ProjetoX]
"""
import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

try:
    from elevenlabs import ElevenLabs, Voice, VoiceSettings
    ELEVENLABS_DISPONIVEL = True
except ImportError:
    ELEVENLABS_DISPONIVEL = False

try:
    from gtts import gTTS
    GTTS_DISPONIVEL = True
except ImportError:
    GTTS_DISPONIVEL = False

sys.path.insert(0, str(Path(__file__).parent))

from logger_setup import get_logger
from config import config

log = get_logger("narrador")


class Narrador:
    """
    Agente de narração que converte roteiro em áudio.
    Usa ElevenLabs como provedor principal e gTTS como fallback.
    """
    
    VOZES_ELEVENLABS = {
        "pt-BR": {
            "masculina_grave": "nathan",      # Narrador padrão
            "masculina_media": "matheus",     # Alternativa
            "feminina": "natasha",            # Raramente usado
        }
    }
    
    def __init__(self, projeto_dir: Path):
        self.projeto_dir = Path(projeto_dir)
        self.audio_dir = self.projeto_dir / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        
        # Inicializa ElevenLabs
        self.elevenlabs = None
        if ELEVENLABS_DISPONIVEL and config.ELEVENLABS_API_KEY:
            try:
                self.elevenlabs = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
                log.info("ElevenLabs conectado")
            except Exception as e:
                log.warning(f"Erro ao conectar ElevenLabs: {e}")
    
    def narrar_roteiro(self, roteiro_path: Path, voz: str = "masculina_grave") -> Dict:
        """
        Converte roteiro JSON em arquivos de áudio.
        
        Returns:
            Dict com paths dos áudios gerados e metadata
        """
        with open(roteiro_path, "r", encoding="utf-8") as f:
            roteiro = json.load(f)
        
        segmentos = roteiro.get("roteiro", [])
        log.info(f"Narrando {len(segmentos)} segmentos")
        
        arquivos_audio = []
        texto_total = ""
        
        for i, seg in enumerate(segmentos):
            texto = seg.get("texto", "").replace("\n", " ")
            texto_limpo = " ".join(texto.split())  # Remove espaços duplos
            texto_total += " " + texto_limpo
            
            # Nome do arquivo
            nome_arquivo = f"seg_{i:02d}_{seg['segmento'].lower()}.mp3"
            caminho_audio = self.audio_dir / nome_arquivo
            
            # Gera áudio
            if self.elevenlabs and voz in self.VOZES_ELEVENLABS["pt-BR"]:
                voz_id = self.VOZES_ELEVENLABS["pt-BR"][voz]
                sucesso = self._narrar_elevenlabs(texto_limpo, caminho_audio, voz_id, seg)
            elif GTTS_DISPONIVEL:
                sucesso = self._narrar_gtts(texto_limpo, caminho_audio)
            else:
                log.error("Nenhum provedor de TTS disponível!")
                return {"sucesso": False, "erro": "sem provedor de TTS"}
            
            if sucesso:
                arquivos_audio.append({
                    "segmento": seg["segmento"],
                    "timecode_inicio": seg["timecode_inicio"],
                    "timecode_fim": seg["timecode_fim"],
                    "arquivo": str(caminho_audio),
                    "duracao_segundos": self._estimar_duracao(texto_limpo)
                })
                log.info(f"  [{i+1}/{len(segmentos)}] {seg['segmento']} → {nome_arquivo}")
        
        # Gera áudio completo concatenado
        audio_completo = self.audio_dir / "narracao_completa.mp3"
        self._concatenar_audios([a["arquivo"] for a in arquivos_audio], audio_completo)
        
        return {
            "sucesso": True,
            "projeto": str(self.projeto_dir.name),
            "segmentos": arquivos_audio,
            "audio_completo": str(audio_completo),
            "texto_total_chars": len(texto_total),
            "voz_usada": voz,
            "provedor": "elevenlabs" if self.elevenlabs else "gtts"
        }
    
    def _narrar_elevenlabs(
        self,
        texto: str,
        output_path: Path,
        voice_id: str,
        segmento: Dict
    ) -> bool:
        """Gera áudio usando ElevenLabs API."""
        try:
            # Configurações de voz para tom narrativo
            settings = VoiceSettings(
                stability=0.5,
                similarity_boost=0.75,
                style=0.0,  # Não usar estilo automático
                use_speaker_boost=True,
                speed=0.92  # Um pouco mais lento para narração
            )
            
            audio = self.elevenlabs.generate(
                text=texto,
                voice=voice_id,
                model="eleven_multilingual_v2",
                voice_settings=settings
            )
            
            # Salva
            self.elevenlabs.save(audio, str(output_path))
            log.debug(f"Áudio salvo: {output_path}")
            return True
            
        except Exception as e:
            log.error(f"Erro ElevenLabs: {e}")
            return False
    
    def _narrar_gtts(self, texto: str, output_path: Path) -> bool:
        """Fallback: usa Google TTS."""
        try:
            tts = gTTS(text=texto, lang="pt", tld="com.br", slow=False)
            tts.save(str(output_path))
            log.debug(f"Áudio gTTS salvo: {output_path}")
            return True
        except Exception as e:
            log.error(f"Erro gTTS: {e}")
            return False
    
    def _concatenar_audios(self, arquivos: List[str], output_path: Path):
        """Concatena múltiplos áudios em um só (usando pydub ou FFmpeg)."""
        try:
            # Tenta usar moviepy
            from moviepy.editor import AudioFileClip, concatenate_audioclips
            
            clips = [AudioFileClip(f) for f in arquivos if Path(f).exists()]
            if clips:
                audio_final = concatenate_audioclips(clips)
                audio_final.write_audiofile(str(output_path), logger=None)
                log.info(f"Áudio completo gerado: {output_path}")
                
        except ImportError:
            # Fallback: copia o primeiro arquivo como "completo"
            if arquivos and Path(arquivos[0]).exists():
                import shutil
                shutil.copy(arquivos[0], output_path)
                log.warning("Concatenação não disponível - usando primeiro segmento")
        except Exception as e:
            log.error(f"Erro ao concatenar áudios: {e}")
    
    def _estimar_duracao(self, texto: str) -> int:
        """Estima duração em segundos baseado no número de palavras."""
        palavras = len(texto.split())
        # Média de 2.5 palavras por segundo em narração de documentary
        return int(palavras / 2.5)


def main():
    parser = argparse.ArgumentParser(description="Narração de roteiro")
    parser.add_argument("--roteiro", type=str, required=True, help="Caminho do arquivo roteiro.json")
    parser.add_argument("--projeto", type=str, default=None, help="Nome do projeto")
    parser.add_argument("--voz", type=str, default="masculina_grave", 
                       choices=["masculina_grave", "masculina_media", "feminina"],
                       help="Tipo de voz")
    args = parser.parse_args()
    
    roteiro_path = Path(args.roteiro)
    if not roteiro_path.exists():
        print(f"❌ Roteiro não encontrado: {roteiro_path}")
        return
    
    # Determina diretório do projeto
    projeto_dir = roteiro_path.parent
    if args.projeto:
        projeto_dir = config.get_projeto_dir(args.projeto)
    
    narrador = Narrador(projeto_dir)
    resultado = narrador.narrar_roteiro(roteiro_path, voz=args.voz)
    
    if resultado["sucesso"]:
        print(f"\n✅ Narração concluída!")
        print(f"   Áudio completo: {resultado['audio_completo']}")
        print(f"   Segmentos: {len(resultado['segmentos'])}")
        print(f"   Provedor: {resultado['provedor']}")
    else:
        print(f"❌ Erro: {resultado.get('erro')}")
    
    return resultado


if __name__ == "__main__":
    main()

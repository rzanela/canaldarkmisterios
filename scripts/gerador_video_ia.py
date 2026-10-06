"""
gerador_video_ia.py — Pipeline de Geração de Vídeo por IA via MiniMax (mcode-tools)
Sem encoders locais. 100% nuvem. Sem FFmpeg local necessário.

Pipeline:
  1. Gerar imagem de capa (matrix_generate_image)
  2. Gerar N clipes de vídeo (matrix_submit_video_generation + query)
  3. Concatenar vídeos com FFmpeg (apenas para mux, sem re-encoding)
  4. Opcional: adicionar narração (matrix_synthesize_speech)
  5. Upload YouTube (youtube_service.py)

Uso:
  python gerador_video_ia.py --projeto projetos/teste
"""

import argparse
import json
import os
import sys
import time
import subprocess
import requests
from pathlib import Path
from datetime import datetime

# Adicionar scripts ao path
sys.path.insert(0, str(Path(__file__).parent))
from config import Config
from logger_setup import get_logger


class GeradorVideoIA:
    """Gera vídeos usando MiniMax via mcode-tools — sem encoding local."""

    def __init__(self, projeto_path: str, modelo_video: str = "MiniMax-H3-Max",
                 duracao_clip: int = 5, num_clipes: int = 4):
        """
        Args:
            projeto_path: caminho do projeto (contém roteiro.json)
            modelo_video: MiniMax-H3-Max (rápido) ou MiniMax-H3 (alta qualidade)
            duracao_clip: duração de cada clipe em segundos (5-15)
            num_clipes: número de clipes a gerar
        """
        self.projeto_path = Path(projeto_path)
        self.modelo_video = modelo_video
        self.duracao_clip = duracao_clip
        self.num_clipes = num_clipes
        self.logger = get_logger("gerador_video_ia")

        # Pastas
        self.pasta_imagens = self.projeto_path / "imagens"
        self.pasta_videos = self.projeto_path / "videos"
        self.pasta_audio = self.projeto_path / "audio"
        self.pasta_output = self.projeto_path / "output"

        for pasta in [self.pasta_imagens, self.pasta_videos, self.pasta_audio, self.pasta_output]:
            pasta.mkdir(parents=True, exist_ok=True)

    def _run_mcode_tools(self, command: list, timeout: int = 120) -> dict:
        """Executa comando mcode-tools e retorna JSON parseado."""
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=Config.BASE_DIR
            )
            if result.returncode != 0:
                self.logger.error(f"mcode-tools erro: {result.stderr}")
                return {}
            return json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            self.logger.error(f"Timeout ({timeout}s) em mcode-tools")
            return {}
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON parse error: {e}\nstdout: {result.stdout[:500]}")
            return {}

    def gerar_imagem_capa(self, prompt: str, resolution: str = "1K",
                          aspect_ratio: str = "16:9") -> str:
        """
        Gera imagem de capa para o vídeo.
        Returns: caminho local da imagem baixada.
        """
        self.logger.info(f"🎨 Gerando imagem de capa ({resolution}, {aspect_ratio})...")

        args = {
            "requests": [{
                "prompt": prompt,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio
            }]
        }

        args_file = self.projeto_path / "temp_image_args.json"
        args_file.write_text(json.dumps(args, ensure_ascii=False), encoding="utf-8")

        resultado = self._run_mcode_tools([
            "mcode-tools", "connector", "call", "connector__matrix__generate_image",
            "--args-file", str(args_file)
        ])

        args_file.unlink(missing_ok=True)

        if not resultado.get("success_items"):
            self.logger.error("Falha ao gerar imagem")
            return ""

        node_id = resultado["success_items"][0]["node_id"]
        file_name = resultado["success_items"][0]["file_name"]

        # Baixar imagem
        url_result = self._run_mcode_tools([
            "mcode-tools", "get-asset-url", node_id
        ])

        if not url_result.get("download_url"):
            self.logger.error("Falha ao obter URL da imagem")
            return ""

        # Baixar
        img_path = self.pasta_imagens / file_name
        self._baixar_arquivo(url_result["download_url"], img_path)
        self.logger.info(f"  ✅ Imagem salva: {img_path.name}")
        return str(img_path)

    def gerar_video(self, prompt: str, input_image_path: str = None,
                    reference_type: str = "first_frame") -> str:
        """
        Gera UM vídeo de N segundos via MiniMax.
        Returns: caminho local do vídeo baixado.
        """
        self.logger.info(f"🎬 Gerando vídeo ({self.modelo_video}, {self.duracao_clip}s)...")

        args = {
            "model": self.modelo_video,
            "duration": self.duracao_clip,
            "prompt": prompt,
            "ratio": "16:9",
            "resolution": "768P" if self.modelo_video == "MiniMax-H3-Max" else "768P"
        }

        if input_image_path and os.path.exists(input_image_path):
            # Upload da imagem para obter temp_url
            upload_result = self._run_mcode_tools([
                "mcode-tools", "upload-temp-url", input_image_path
            ])

            if upload_result.get("temp_url"):
                args["input_image"] = {
                    "mime_type": "image/jpeg",
                    "url": upload_result["temp_url"]
                }
                args["reference_type"] = reference_type
            else:
                self.logger.warning("Não foi possível上传 imagem, gerando text-to-video")

        args_file = self.projeto_path / "temp_video_args.json"
        args_file.write_text(json.dumps(args, ensure_ascii=False), encoding="utf-8")

        # Submeter tarefa
        resultado = self._run_mcode_tools([
            "mcode-tools", "connector", "call", "connector__matrix__submit_video_generation",
            "--args-file", str(args_file)
        ])

        args_file.unlink(missing_ok=True)

        if not resultado.get("task_id"):
            self.logger.error("Falha ao submeter vídeo")
            return ""

        task_id = resultado["task_id"]
        self.logger.info(f"  📡 Task ID: {task_id}")

        # Polling do status
        max_wait = 120 if self.modelo_video == "MiniMax-H3-Max" else 600
        waited = 0
        interval = 5 if self.modelo_video == "MiniMax-H3-Max" else 30

        while waited < max_wait:
            time.sleep(interval)
            waited += interval

            query_args = {"model": self.modelo_video, "task_id": task_id}
            query_file = self.projeto_path / "temp_query_args.json"
            query_file.write_text(json.dumps(query_args))

            status_result = self._run_mcode_tools([
                "mcode-tools", "connector", "call",
                "connector__matrix__query_video_generation",
                "--args-file", str(query_file)
            ])

            query_file.unlink(missing_ok=True)

            if not status_result:
                continue

            status = status_result.get("status", "")
            self.logger.info(f"  ⏳ Status: {status} ({waited}s)")

            if status == "succeeded":
                video_url = status_result.get("video_url", "")
                if video_url:
                    # Baixar vídeo
                    timestamp = datetime.now().strftime("%H%M%S")
                    video_path = self.pasta_videos / f"clip_{timestamp}.mp4"
                    self._baixar_arquivo(video_url, video_path)
                    self.logger.info(f"  ✅ Vídeo salvo: {video_path.name}")
                    return str(video_path)
                return ""

            elif status in ("failed", "cancelled"):
                self.logger.error(f"  ❌ Vídeo falhou: {status_result.get('failure_reason', 'desconhecido')}")
                return ""

        self.logger.error(f"  ❌ Timeout após {max_wait}s")
        return ""

    def gerar_roteiro_segmentos(self, texto_roteiro: str, num_clipes: int = None) -> list:
        """
        Divide o roteiro em segmentos temáticos para gerar clipes visuais.
        Returns: lista de prompts de vídeo (um por clipe).
        """
        if num_clipes is None:
            num_clipes = self.num_clipes

        # Quebrar roteiro em blocos
        paragrafos = [p.strip() for p in texto_roteiro.split("\n") if p.strip()]
        total = len(paragrafos)
        tamanho_bloco = max(1, total // num_clipes)

        segmentos = []
        for i in range(num_clipes):
            inicio = i * tamanho_bloco
            fim = inicio + tamanho_bloco if i < num_clipes - 1 else total
            bloco = paragrafos[inicio:fim]

            if not bloco:
                continue

            texto_bloco = " ".join(bloco)

            # Prompt visual para o clipe (descrição cinematográfica)
            prompt = self._construir_prompt_video(texto_bloco, i + 1, num_clipes)
            segmentos.append({
                "num": i + 1,
                "texto": texto_bloco[:200],
                "prompt_video": prompt
            })

        return segmentos

    def _construir_prompt_video(self, texto: str, num: int, total: int) -> str:
        """Constrói prompt visual cinematográfico a partir do texto do roteiro."""
        # Extrair palavras-chave de crime/mistério
        crime_keywords = [
            "crime", "assassinato", "suspeito", "polícia", "investigação",
            "noite", "escuridão", "sangue", "arma", "cena do crime",
            "testemunha", "prova", "detective", "mistério", "segredo",
            "noite chuvosa", "ruína", "cemitério", "hospital", "prisão"
        ]

        atmosfera = "dark cinematic atmosphere, dramatic lighting, film grain, moody fog"
        texto_lower = texto.lower()

        # Detectar atmosfera do trecho
        if any(k in texto_lower for k in ["noite", "escuridão", "dark"]):
            atmosfera = "dark nighttime scene, moody fog, dramatic shadows, cinematic lighting, film grain"
        elif any(k in texto_lower for k in ["hospital", "sangue", "morto"]):
            atmosfera = "tense hospital corridor, emergency lights, dramatic shadows, cinematic atmosphere"
        elif any(k in texto_lower for k in ["prisão", "cadeia", "preso"]):
            atmosfera = "dark prison cell, flickering light, tense atmosphere, cinematic mood"
        elif any(k in texto_lower for k in ["floresta", "corpo", "desaparecido"]):
            atmosfera = "dark forest at night, mist, eerie atmosphere, cinematic fog, suspenseful"
        else:
            atmosfera = "dark cinematic investigation scene, dramatic lighting, moody shadows, film grain, tense atmosphere"

        # Construir prompt
        prompt = (
            f"Scene {num}/{total}: {texto[:150]}. "
            f"{atmosfera}, high detail, photorealistic, anamorphic lens effect. "
            f"Dark moody color grading, shallow depth of field."
        )
        return prompt

    def _baixar_arquivo(self, url: str, path: Path) -> bool:
        """Baixa arquivo da URL para o caminho local."""
        try:
            response = requests.get(url, timeout=60, stream=True)
            response.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            self.logger.error(f"Erro ao baixar {url}: {e}")
            return False

    def concatenar_videos(self, videos_paths: list) -> str:
        """
        Concatena múltiplos vídeos usando FFmpeg (apenas mux, sem re-encoding).
        Returns: caminho do vídeo final concatenado.
        """
        if not videos_paths:
            self.logger.error("Nenhum vídeo para concatenar")
            return ""

        videos_paths = [v for v in videos_paths if v and os.path.exists(v)]

        if len(videos_paths) == 1:
            self.logger.info("Apenas 1 vídeo, copiando sem concatenar")
            output = self.pasta_output / "video_final.mp4"
            import shutil
            shutil.copy(videos_paths[0], output)
            return str(output)

        self.logger.info(f"🔗 Concatenando {len(videos_paths)} vídeos...")

        # Criar arquivo de lista para FFmpeg concat
        list_file = self.projeto_path / "video_list.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for video_path in videos_paths:
                f.write(f"file '{video_path}'\n")

        output = self.pasta_output / "video_final.mp4"

        # Concatenar com FFmpeg (copy — sem re-encoding)
        cmd = [
            Config.FFMPEG_PATH,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(output)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            list_file.unlink(missing_ok=True)

            if result.returncode == 0 and output.exists():
                size_mb = output.stat().st_size / 1024 / 1024
                self.logger.info(f"  ✅ Vídeo concatenado: {output.name} ({size_mb:.1f} MB)")
                return str(output)
            else:
                self.logger.error(f"FFmpeg erro: {result.stderr}")
                return ""
        except Exception as e:
            self.logger.error(f"Exceção no FFmpeg: {e}")
            return ""

    def adicionar_narracao(self, texto: str, voz: str = "pt-BR-Female") -> str:
        """
        Adiciona narração ao vídeo usando mcode-tools TTS.
        Returns: caminho do áudio.
        """
        self.logger.info(f"🎙️ Gerando narração ({voz})...")

        args = {
            "text": texto[:1000],  # Limite por chamada
            "voice_id": voz,
            "speed": 1.0,
            "emotion": "sad"  # Tom crime/mistério
        }

        args_file = self.projeto_path / "temp_tts_args.json"
        args_file.write_text(json.dumps(args))

        resultado = self._run_mcode_tools([
            "mcode-tools", "connector", "call", "connector__matrix__synthesize_speech",
            "--args-file", str(args_file)
        ])

        args_file.unlink(missing_ok=True)

        if not resultado.get("node_id"):
            self.logger.error("Falha ao gerar áudio")
            return ""

        # Obter URL e baixar
        url_result = self._run_mcode_tools([
            "mcode-tools", "get-asset-url", resultado["node_id"]
        ])

        if not url_result.get("download_url"):
            return ""

        audio_path = self.pasta_audio / f"narracao_{datetime.now().strftime('%H%M%S')}.mp3"
        if self._baixar_arquivo(url_result["download_url"], audio_path):
            self.logger.info(f"  ✅ Áudio salvo: {audio_path.name}")
            return str(audio_path)

        return ""

    def misturar_audio_video(self, video_path: str, audio_path: str,
                              output_name: str = "video_com_narracao.mp4") -> str:
        """
        Mistura vídeo silencioso com narração (FFmpeg mux).
        Returns: caminho do vídeo final com áudio.
        """
        if not video_path or not audio_path:
            return video_path

        self.logger.info("🎛️ Misturando vídeo + narração...")

        output = self.pasta_output / output_name

        cmd = [
            Config.FFMPEG_PATH,
            "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(output)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and output.exists():
                size_mb = output.stat().st_size / 1024 / 1024
                self.logger.info(f"  ✅ Vídeo com áudio: {output.name} ({size_mb:.1f} MB)")
                return str(output)
            else:
                self.logger.error(f"FFmpeg mux erro: {result.stderr[:500]}")
                return video_path
        except Exception as e:
            self.logger.error(f"Exceção mux: {e}")
            return video_path

    def pipeline_completo(self, roteiro_path: str = None) -> dict:
        """
        Executa o pipeline completo: imagem → vídeos → concatenação → narração.
        Returns: dict com resultados.
        """
        self.logger.info("=" * 60)
        self.logger.info("🚀 PIPELINE DE VÍDEO POR IA — MINIMAX")
        self.logger.info("=" * 60)

        resultado = {
            "sucesso": False,
            "projeto": str(self.projeto_path),
            "imagem_capa": None,
            "clipes": [],
            "video_concatenado": None,
            "audio_narracao": None,
            "video_final": None,
            "erros": []
        }

        # Carregar roteiro
        if roteiro_path is None:
            roteiro_path = self.projeto_path / "roteiro.json"

        if not os.path.exists(roteiro_path):
            resultado["erros"].append(f"Roteiro não encontrado: {roteiro_path}")
            return resultado

        with open(roteiro_path, "r", encoding="utf-8") as f:
            roteiro = json.load(f)

        texto_completo = roteiro.get("texto", "")
        titulo = roteiro.get("titulo", "Sem título")

        if not texto_completo:
            resultado["erros"].append("Roteiro vazio")
            return resultado

        # ========================================
        # ETAPA 1: Gerar imagem de capa
        # ========================================
        self.logger.info("\n📸 ETAPA 1: Imagem de Capa")
        prompt_capa = (
            f"Dark cinematic cover for YouTube video: {titulo}. "
            "Forensic crime scene investigation, dramatic lighting, Brazilian urban setting at night, "
            "moody fog, dark shadows, photorealistic, film grain, anamorphic lens. "
            "Text placeholder area on right side, main visual on left."
        )

        img_path = self.gerar_imagem_capa(prompt_capa)
        if not img_path:
            resultado["erros"].append("Falha ao gerar imagem de capa")
        else:
            resultado["imagem_capa"] = img_path

        # ========================================
        # ETAPA 2: Gerar clipes de vídeo
        # ========================================
        self.logger.info("\n🎬 ETAPA 2: Gerando Clipes de Vídeo")

        segmentos = self.gerar_roteiro_segmentos(texto_completo)

        if not segmentos:
            # Gerar um vídeo genérico
            segmentos = [{
                "num": 1,
                "texto": texto_completo[:200],
                "prompt_video": f"Dark cinematic crime investigation scene: {texto_completo[:200]}. "
                               "dramatic lighting, film grain, moody fog, photorealistic."
            }]

        # Limitar ao número de clipes configurado
        segmentos = segmentos[:self.num_clipes]

        # Gerar cada clipe
        for seg in segmentos:
            self.logger.info(f"\n  --- Clipe {seg['num']}/{len(segmentos)} ---")
            video_path = self.gerar_video(
                prompt=seg["prompt_video"],
                input_image_path=img_path if seg["num"] == 1 else None,
                reference_type="first_frame"
            )

            if video_path:
                resultado["clipes"].append({
                    "num": seg["num"],
                    "path": video_path,
                    "texto": seg["texto"]
                })
            else:
                self.logger.warning(f"  ⚠️ Clipe {seg['num']} falhou — continuando...")

        if not resultado["clipes"]:
            resultado["erros"].append("Todos os clipes falharam")
            return resultado

        # ========================================
        # ETAPA 3: Concatenar vídeos
        # ========================================
        self.logger.info("\n🔗 ETAPA 3: Concatenando Vídeos")

        videos_para_concatenar = [c["path"] for c in resultado["clipes"]]
        video_concat = self.concatenar_videos(videos_para_concatenar)

        if video_concat:
            resultado["video_concatenado"] = video_concat
        else:
            resultado["erros"].append("Falha na concatenação")
            return resultado

        # ========================================
        # ETAPA 4: Narração (opcional)
        # ========================================
        self.logger.info("\n🎙️ ETAPA 4: Narração")

        audio_path = self.adicionar_narracao(texto_completo)

        if audio_path:
            resultado["audio_narracao"] = audio_path
            video_final = self.misturar_audio_video(
                resultado["video_concatenado"],
                audio_path,
                f"video_final_{datetime.now().strftime('%H%M%S')}.mp4"
            )
            resultado["video_final"] = video_final
        else:
            # Sem narração — usar vídeo sem áudio
            resultado["video_final"] = resultado["video_concatenado"]
            self.logger.info("  ⚠️ Sem narração — usando vídeo silencioso")

        resultado["sucesso"] = True
        self.logger.info("\n" + "=" * 60)
        self.logger.info("✅ PIPELINE CONCLUÍDO!")
        self.logger.info(f"   Vídeo final: {resultado['video_final']}")
        self.logger.info("=" * 60)

        return resultado


def main():
    parser = argparse.ArgumentParser(description="Gerador de Vídeo por IA — Pipeline MiniMax")
    parser.add_argument("--projeto", required=True, help="Caminho do projeto")
    parser.add_argument("--modelo", default="MiniMax-H3-Max",
                        choices=["MiniMax-H3-Max", "MiniMax-H3", "MiniMax-Hailuo-2.3"],
                        help="Modelo de vídeo MiniMax")
    parser.add_argument("--clipes", type=int, default=4, help="Número de clipes")
    parser.add_argument("--duracao", type=int, default=5, help="Duração de cada clipe (s)")
    parser.add_argument("--roteiro", help="Caminho do arquivo de roteiro (default: <projeto>/roteiro.json)")

    args = parser.parse_args()

    gerador = GeradorVideoIA(
        projeto_path=args.projeto,
        modelo_video=args.modelo,
        duracao_clip=args.duracao,
        num_clipes=args.clipes
    )

    resultado = gerador.pipeline_completo(roteiro_path=args.roteiro)

    # Salvar resultado
    resultado_path = Path(args.projeto) / "resultado_video_ia.json"
    with open(resultado_path, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    print(f"\n📄 Resultado salvo em: {resultado_path}")

    return 0 if resultado["sucesso"] else 1


if __name__ == "__main__":
    sys.exit(main())

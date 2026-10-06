"""
ORQUESTRADOR — Canal Dark
Dispara o pipeline completo via cron do sistema (Windows Task Scheduler / cron Linux).
Não precisa do n8n para funcionar.

Uso:
  python orquestrador.py --fase pesquisa    # Pesquisa temas
  python orquestrador.py --fase roteiro    # Gera roteiro
  python orquestrador.py --fase producao   # Produz vídeo
  python orquestrador.py --fase upload      # Upload YouTube
  python orquestrador.py --fase completo    # Pipeline completo (pesquisa→roteiro→produção→upload)
  python orquestrador.py --fase continua   # Continua produção pendente

Agende no Windows Task Scheduler:
  schtasks /create /sc daily /tn "CanalDark_Pesquisa" /tr "pythonw G:\Meu Drive\IA\Canal Dark\canal-dark\scripts\orquestrador.py --fase pesquisa" /st 08:00 /d MON,WED,FRI
"""

import os
import sys
import json
import subprocess
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, List

# Adiciona scripts ao path
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from logger_setup import get_logger
from config import config

log = get_logger("orquestrador")


class Orquestrador:
    """Orquestra todas as fases do pipeline Canal Dark."""

    def __init__(self):
        self.base_dir = PROJECT_ROOT
        self.projetos_dir = self.base_dir / "projetos"
        self.dados_dir = self.base_dir / "dados"
        self.scripts_dir = SCRIPT_DIR
        self.output_dir = self.projetos_dir / "output"
        self.output_dir.mkdir(exist_ok=True)

    # ─── FASE 1: Pesquisa ─────────────────────────────────────────────────

    def fase_pesquisa(self) -> dict:
        """Executa pesquisa de temas via Reddit + LLM."""
        log.info("=" * 60)
        log.info("FASE 1: PESQUISA DE TEMAS")
        log.info("=" * 60)

        try:
            from pesquisa_temas import PesquisaTemas
            pesquisa = PesquisaTemas()
            resultado = pesquisa.executar()

            if resultado.get("temas"):
                log.info(f"✅ Pesquisa concluída: {len(resultado['temas'])} temas encontrados")
                return {"sucesso": True, "fase": "pesquisa", "resultado": resultado}
            else:
                log.warning("⚠️ Nenhum tema novo encontrado")
                return {"sucesso": False, "fase": "pesquisa", "erro": "sem temas"}
        except Exception as e:
            log.error(f"❌ Erro na pesquisa: {e}")
            return {"sucesso": False, "fase": "pesquisa", "erro": str(e)}

    # ─── FASE 2: Roteiro ──────────────────────────────────────────────────

    def fase_roteiro(self) -> dict:
        """Gera roteiro para o próximo tema da fila."""
        log.info("=" * 60)
        log.info("FASE 2: GERAÇÃO DE ROTEIRO")
        log.info("=" * 60)

        fila_path = self.dados_dir / "fila_temas.json"
        if not fila_path.exists():
            log.error("Fila de temas não encontrada. Execute fase pesquisa primeiro.")
            return {"sucesso": False, "fase": "roteiro", "erro": "fila não encontrada"}

        with open(fila_path, "r", encoding="utf-8") as f:
            fila = json.load(f)

        # Busca próximo tema não processado
        tema = None
        for t in fila:
            if not t.get("processado"):
                tema = t
                break

        if not tema:
            log.warning("Nenhum tema pendente na fila")
            return {"sucesso": False, "fase": "roteiro", "erro": "sem temas pendentes"}

        # Atualiza fila
        for t in fila:
            if t.get("titulo") == tema.get("titulo"):
                t["processado"] = True
                t["data_processamento"] = datetime.now().isoformat()
                break
        with open(fila_path, "w", encoding="utf-8") as f:
            json.dump(fila, f, ensure_ascii=False, indent=2)

        # Gera roteiro
        try:
            from roteirizador import Roteirizador
            roteirizador = Roteirizador(tema)
            resultado = roteirizador.gerar_roteiro()

            if resultado.get("sucesso"):
                video_id = resultado.get("video_id")
                log.info(f"✅ Roteiro gerado: {video_id}")
                return {"sucesso": True, "fase": "roteiro", "video_id": video_id, "resultado": resultado}
            else:
                log.error(f"❌ Erro ao gerar roteiro: {resultado.get('erro')}")
                return {"sucesso": False, "fase": "roteiro", "erro": resultado.get("erro")}
        except Exception as e:
            log.error(f"❌ Erro no roteirizador: {e}")
            return {"sucesso": False, "fase": "roteiro", "erro": str(e)}

    # ─── FASE 3: Produção ──────────────────────────────────────────────────

    def fase_producao(self, video_id: str = None) -> dict:
        """Produz vídeo: imagens + narração + montagem."""
        log.info("=" * 60)
        log.info("FASE 3: PRODUÇÃO")
        log.info("=" * 60)

        # Se não指定 video_id, busca o mais antigo pendente
        if not video_id:
            video_id = self._buscar_projeto_pendente()
            if not video_id:
                log.warning("Nenhum projeto pendente de produção")
                return {"sucesso": False, "fase": "producao", "erro": "sem projetos pendentes"}

        projeto_dir = self.projetos_dir / video_id
        roteiro_path = projeto_dir / "roteiro.json"

        if not roteiro_path.exists():
            # Tenta formato antigo
            roteiro_path = projeto_dir / f"resultado_{video_id}.json"

        if not roteiro_path.exists():
            log.error(f"Roteiro não encontrado: {video_id}")
            return {"sucesso": False, "fase": "producao", "erro": "roteiro não encontrado"}

        log.info(f"Produzindo: {video_id}")

        # 3a: Narração
        try:
            from narrador import Narrador
            narrador = Narrador(projeto_dir)
            resultado_narr = narrador.gerar_narracao(roteiro_path)
            log.info(f"  Narração: {resultado_narr.get('audio_files', []).__len__()} áudios gerados")
        except Exception as e:
            log.error(f"  Erro narração: {e}")

        # 3b: Imagens
        try:
            from gerador_imagens import GeradorImagens
            gerador = GeradorImagens(projeto_dir)
            resultado_img = gerador.gerar_visuais(roteiro_path)
            log.info(f"  Imagens: {resultado_img.get('total_geradas', 0)}/{len(resultado_img.get('imagens', []))} geradas")
        except Exception as e:
            log.error(f"  Erro imagens: {e}")

        # 3c: Montagem (FFmpeg)
        try:
            from montador_video import MontadorVideo
            montador = MontadorVideo(video_id)
            resultado_video = montador.montar()
            if resultado_video.get("sucesso"):
                log.info(f"  Vídeo montado: {resultado_video.get('caminho_video')}")
                return {"sucesso": True, "fase": "producao", "video_id": video_id, "resultado": resultado_video}
            else:
                log.error(f"  Erro na montagem: {resultado_video.get('erro')}")
                return {"sucesso": False, "fase": "producao", "erro": resultado_video.get("erro")}
        except Exception as e:
            log.error(f"❌ Erro na montagem: {e}")
            return {"sucesso": False, "fase": "producao", "erro": str(e)}

    # ─── FASE 4: Upload ───────────────────────────────────────────────────

    def fase_upload(self, video_id: str = None) -> dict:
        """Faz upload do vídeo para YouTube."""
        log.info("=" * 60)
        log.info("FASE 4: UPLOAD YOUTUBE")
        log.info("=" * 60)

        # Busca vídeo pendente se não指定
        if not video_id:
            video_id = self._buscar_video_pendente()
            if not video_id:
                log.warning("Nenhum vídeo pendente de upload")
                return {"sucesso": False, "fase": "upload", "erro": "sem vídeos pendentes"}

        projeto_dir = self.projetos_dir / video_id

        # Busca arquivo de vídeo
        video_extensions = ["mp4", "avi", "mkv", "mov"]
        video_path = None
        for ext in video_extensions:
            candidate = projeto_dir / f"video_final_{video_id}.{ext}"
            if candidate.exists():
                video_path = candidate
                break
            candidate = projeto_dir / f"{video_id}.{ext}"
            if candidate.exists():
                video_path = candidate
                break

        if not video_path or not video_path.exists():
            # Procura no output
            for ext in video_extensions:
                candidate = self.output_dir / f"video_final_{video_id}.{ext}"
                if candidate.exists():
                    video_path = candidate
                    break

        if not video_path or not video_path.exists():
            log.error(f"Vídeo não encontrado: {video_id}")
            return {"sucesso": False, "fase": "upload", "erro": "vídeo não encontrado"}

        # Gera SEO
        roteiro_path = projeto_dir / f"resultado_{video_id}.json"
        if not roteiro_path.exists():
            roteiro_path = projeto_dir / "roteiro.json"

        seo_metadata = None
        if roteiro_path.exists():
            try:
                from seo_gerador import SEOGerador
                with open(roteiro_path, "r", encoding="utf-8") as f:
                    roteiro = json.load(f)
                tema = roteiro.get("metadata", {}).get("tema", video_id)
                gerador = SEOGerador(tema)
                seo_metadata = gerador.gerar_metadata(roteiro_path)
                log.info(f"  SEO gerado: {seo_metadata.get('titulo', '')[:60]}")
            except Exception as e:
                log.error(f"  Erro SEO: {e}")

        # Upload
        try:
            from youtube_service import upload_video
            titulo = seo_metadata.get("titulo", f"Caso Real {video_id}") if seo_metadata else f"Caso Real {video_id}"
            descricao = seo_metadata.get("descricao", "") if seo_metadata else ""
            tags = seo_metadata.get("tags", []) if seo_metadata else []

            youtube_id = upload_video(
                video_path=str(video_path),
                title=titulo,
                description=descricao,
                tags=tags,
                category="24",
                privacy_status="private"  # Muda para "public" ou "scheduled" quando quiser publicar
            )

            log.info(f"✅ Upload concluído: {youtube_id}")
            return {
                "sucesso": True,
                "fase": "upload",
                "video_id": video_id,
                "youtube_id": youtube_id,
                "youtube_url": f"https://youtube.com/watch?v={youtube_id}"
            }
        except Exception as e:
            log.error(f"❌ Erro no upload: {e}")
            return {"sucesso": False, "fase": "upload", "erro": str(e)}

    # ─── FASE 3B: Produção por IA (MiniMax) ────────────────────────────

    def fase_videoia(self, video_id: str = None, modelo: str = "MiniMax-H3-Max",
                     num_clipes: int = 4) -> dict:
        """Produz vídeo usando IA (MiniMax via mcode-tools) — sem encoding local."""
        log.info("=" * 60)
        log.info("FASE 3B: PRODUÇÃO POR IA — MINIMAX")
        log.info("=" * 60)

        # Se não指定 video_id, busca o mais antigo pendente
        if not video_id:
            video_id = self._buscar_projeto_pendente()
            if not video_id:
                log.warning("Nenhum projeto pendente de produção")
                return {"sucesso": False, "fase": "videoia", "erro": "sem projetos pendentes"}

        projeto_dir = self.projetos_dir / video_id
        if not projeto_dir.exists():
            log.error(f"Projeto não encontrado: {video_id}")
            return {"sucesso": False, "fase": "videoia", "erro": "projeto não encontrado"}

        roteiro_path = projeto_dir / "roteiro.json"
        if not roteiro_path.exists():
            roteiro_path = projeto_dir / f"resultado_{video_id}.json"

        if not roteiro_path.exists():
            log.error(f"Roteiro não encontrado: {video_id}")
            return {"sucesso": False, "fase": "videoia", "erro": "roteiro não encontrado"}

        log.info(f"Projetando: {video_id} | Modelo: {modelo} | Clipes: {num_clipes}")

        try:
            from gerador_video_ia import GeradorVideoIA
            gerador = GeradorVideoIA(
                projeto_path=str(projeto_dir),
                modelo_video=modelo,
                duracao_clip=5,
                num_clipes=num_clipes
            )
            resultado = gerador.pipeline_completo(roteiro_path=str(roteiro_path))

            if resultado.get("sucesso"):
                log.info(f"✅ Vídeo IA gerado: {resultado.get('video_final')}")
                return {
                    "sucesso": True,
                    "fase": "videoia",
                    "video_id": video_id,
                    "resultado": resultado
                }
            else:
                log.error(f"❌ Produção IA falhou: {resultado.get('erros')}")
                return {"sucesso": False, "fase": "videoia", "erro": resultado.get("erros")}
        except Exception as e:
            log.error(f"❌ Erro na produção IA: {e}")
            return {"sucesso": False, "fase": "videoia", "erro": str(e)}

    # ─── Pipeline Completo ────────────────────────────────────────────────

    def fase_completo(self) -> dict:
        """Executa pipeline completo: pesquisa → roteiro → produção → upload."""
        log.info("=" * 60)
        log.info("PIPELINE COMPLETO")
        log.info("=" * 60)

        resultados = {}

        # 1. Pesquisa
        res_pesquisa = self.fase_pesquisa()
        resultados["pesquisa"] = res_pesquisa
        if not res_pesquisa.get("sucesso"):
            log.warning("Pesquisa falhou, continuando se possível...")

        # 2. Roteiro
        res_roteiro = self.fase_roteiro()
        resultados["roteiro"] = res_roteiro
        if not res_roteiro.get("sucesso"):
            log.error("Roteiro falhou, abortando pipeline.")
            return resultados

        video_id = res_roteiro.get("video_id")

        # 3. Produção por IA (MiniMax)
        res_producao = self.fase_videoia(video_id)
        resultados["producao"] = res_producao
        if not res_producao.get("sucesso"):
            log.warning("Produção IA falhou, continuando se possível...")

        # 4. Upload
        res_upload = self.fase_upload(video_id)
        resultados["upload"] = res_upload

        return resultados

    def fase_continua(self) -> dict:
        """Continua produção/upload de projetos pendentes."""
        log.info("=" * 60)
        log.info("MODO CONTÍNUO: completando pendências")
        log.info("=" * 60)

        resultados = []

        # Production pending
        res_prod = self.fase_producao()
        resultados.append(res_prod)

        if res_prod.get("sucesso"):
            video_id = res_prod.get("video_id")
            res_up = self.fase_upload(video_id)
            resultados.append(res_up)

        return {"sucesso": True, "resultados": resultados}

    # ─── Helpers ───────────────────────────────────────────────────────────

    def _buscar_projeto_pendente(self) -> Optional[str]:
        """Busca projeto mais antigo sem produção."""
        if not self.projetos_dir.exists():
            return None

        for pasta in sorted(self.projetos_dir.iterdir()):
            if not pasta.is_dir():
                continue
            roteiro_path = pasta / "roteiro.json"
            if not roteiro_path.exists():
                roteiro_path = pasta / f"resultado_{pasta.name}.json"
            if roteiro_path.exists():
                imagens_dir = pasta / "imagens"
                if not imagens_dir.exists() or len(list(imagens_dir.glob("*"))) == 0:
                    return pasta.name
        return None

    def _buscar_video_pendente(self) -> Optional[str]:
        """Busca vídeo montado sem upload."""
        fila_upload_path = self.dados_dir / "fila_upload.json"
        fila = []
        if fila_upload_path.exists():
            with open(fila_upload_path, "r", encoding="utf-8") as f:
                fila = json.load(f)

        if not self.projetos_dir.exists():
            return None

        for pasta in sorted(self.projetos_dir.iterdir()):
            if not pasta.is_dir():
                continue
            if pasta.name in fila:
                continue

            # Procura vídeo
            for ext in ["mp4", "avi", "mkv"]:
                if (pasta / f"video_final_{pasta.name}.{ext}").exists():
                    return pasta.name
                if (self.output_dir / f"video_final_{pasta.name}.{ext}").exists():
                    return pasta.name

        return None

    def status(self) -> dict:
        """Retorna status do pipeline."""
        fila_path = self.dados_dir / "fila_temas.json"
        fila = []
        if fila_path.exists():
            with open(fila_path, "r", encoding="utf-8") as f:
                fila = json.load(f)

        pendentes = [t for t in fila if not t.get("processado")]
        processados = [t for t in fila if t.get("processado")]

        projetos = []
        if self.projetos_dir.exists():
            for pasta in self.projetos_dir.iterdir():
                if not pasta.is_dir():
                    continue
                tem_roteiro = (pasta / "roteiro.json").exists() or list(pasta.glob("resultado_*.json"))
                tem_imagens = (pasta / "imagens").exists() and len(list((pasta / "imagens").glob("*"))) > 0
                tem_audio = (pasta / "audio").exists() and len(list((pasta / "audio").glob("*.mp3"))) > 0
                tem_video = list(pasta.glob("video_final_*.mp4")) or list(pasta.glob("*.mp4"))

                status_projeto = "pendente"
                if tem_video:
                    status_projeto = "pronto_upload"
                elif tem_audio and tem_imagens:
                    status_projeto = "pronto_montagem"
                elif tem_roteiro:
                    status_projeto = "em_producao"

                projetos.append({
                    "video_id": pasta.name,
                    "status": status_projeto,
                    "tem_roteiro": tem_roteiro,
                    "tem_imagens": tem_imagens,
                    "tem_audio": tem_audio,
                    "tem_video": bool(tem_video)
                })

        return {
            "fila_pendente": len(pendentes),
            "fila_processada": len(processados),
            "total_projetos": len(projetos),
            "projetos": projetos
        }


def main():
    parser = argparse.ArgumentParser(description="Orquestrador Canal Dark")
    parser.add_argument("--fase", type=str, required=True,
                        choices=["pesquisa", "roteiro", "producao", "upload", "completo", "continua", "status", "videoia"],
                        help="Fase do pipeline a executar")
    parser.add_argument("--video-id", type=str, default=None,
                        help="Video ID específico (para fases de produção/upload)")
    parser.add_argument("--modelo", type=str, default="MiniMax-H3-Max",
                        choices=["MiniMax-H3-Max", "MiniMax-H3", "MiniMax-Hailuo-2.3"],
                        help="Modelo de vídeo IA (para fase videoia)")
    parser.add_argument("--clipes", type=int, default=4,
                        help="Número de clipes (para fase videoia)")
    parser.add_argument("--log", type=str, default="info",
                        choices=["debug", "info", "warning", "error"],
                        help="Nível de log")
    args = parser.parse_args()

    orch = Orquestrador()

    if args.fase == "status":
        status = orch.status()
        print("\n" + "=" * 60)
        print("STATUS DO PIPELINE")
        print("=" * 60)
        print(f"  Temas pendentes na fila: {status['fila_pendente']}")
        print(f"  Temas processados: {status['fila_processada']}")
        print(f"  Total de projetos: {status['total_projetos']}")
        print()
        for p in status["projetos"]:
            print(f"  [{p['status']:20s}] {p['video_id']}")
        print()
        return

    # Executa fase
    metodo = getattr(orch, f"fase_{args.fase}")
    if args.fase in ("producao", "upload", "videoia"):
        if args.fase == "videoia":
            resultado = metodo(args.video_id, args.modelo, args.clipes)
        else:
            resultado = metodo(args.video_id)
    else:
        resultado = metodo()

    # Log resultado
    print("\n" + "=" * 60)
    if resultado.get("sucesso"):
        print(f"  ✅ FASE {args.fase.upper()} CONCLUÍDA")
    else:
        print(f"  ⚠️  FASE {args.fase.upper()} FINALIZOU COM ERRO")
    print(f"  Detalhes: {resultado}")
    print("=" * 60)

    return resultado


if __name__ == "__main__":
    main()

"""
Phase 8: Dashboard de Monitoramento — Canal Dark
Relatórios automáticos de performance e saúde do pipeline.

Uso:
  python scripts/dashboard.py                  # Relatório completo
  python scripts/dashboard.py --resumo         # Mini resumo no terminal
  python scripts/dashboard.py --html           # Gera relatório HTML
  python scripts/dashboard.py --notify         # Envia por e-mail
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent
DATOS_DIR = PROJECT_ROOT / "dados"
PROJETOS_DIR = PROJECT_ROOT / "projetos"
OUTPUT_DIR = PROJECT_ROOT / "output"

# ─── Logger ───────────────────────────────────────────────────────────────────
try:
    from logger_setup import get_logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    get_logger = lambda name: logging.getLogger(name)

logger = get_logger("dashboard")


# ─── Helpers de Data ──────────────────────────────────────────────────────────
def parse_date(data_str: str) -> datetime:
    try:
        return datetime.fromisoformat(data_str.replace("Z", "+00:00"))
    except Exception:
        return datetime.now()


def tempo_relativo(dt: datetime) -> str:
    delta = datetime.now() - dt
    if delta.days > 0:
        return f"{delta.days}d atrás"
    horas = delta.seconds // 3600
    if horas > 0:
        return f"{horas}h atrás"
    minutos = delta.seconds // 60
    return f"{minutos}min atrás"


# ─── Coleta de Dados ──────────────────────────────────────────────────────────
def carregar_json(caminho: Path) -> list[dict]:
    if not caminho.exists():
        return []
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return [data]
    except Exception as e:
        logger.warning(f"Erro ao ler {caminho}: {e}")
        return []


def coletar_dados_pipeline() -> dict[str, Any]:
    """Coleta todos os dados disponíveis sobre o estado do pipeline."""

    fila_temas = carregar_json(DATOS_DIR / "fila_temas.json")
    historico_temas = carregar_json(DATOS_DIR / "historico_temas.json")
    historico_uploads = carregar_json(DATOS_DIR / "historico_upload.json")
    fila_upload = carregar_json(DATOS_DIR / "fila_upload.json")

    # Estatísticas de projetos
    total_projetos = 0
    projetos_com_roteiro = 0
    projetos_com_video = 0
    projetos_pendentes = 0

    if PROJETOS_DIR.exists():
        for pasta in PROJETOS_DIR.iterdir():
            if pasta.is_dir():
                total_projetos += 1
                resultado = pasta / f"resultado_{pasta.name}.json"
                video_existe = (OUTPUT_DIR / f"video_final_{pasta.name}.mp4").exists()
                if resultado.exists():
                    projetos_com_roteiro += 1
                if video_existe:
                    projetos_com_video += 1
                if resultado.exists() and not video_existe:
                    projetos_pendentes += 1

    # Estatísticas de uploads
    uploads_totais = len(historico_uploads)
    videos_output = list(OUTPUT_DIR.glob("video_final_*.mp4")) if OUTPUT_DIR.exists() else []

    return {
        "timestamp": datetime.now().isoformat(),
        "fila_temas_pendentes": len([t for t in fila_temas if not t.get("processado")]),
        "total_temas_classificados": len(historico_temas),
        "temas_ultimos_7_dias": len([
            t for t in historico_temas
            if parse_date(t.get("data_roteiro", "2020-01-01")) > datetime.now() - timedelta(days=7)
        ]),
        "projetos": {
            "total": total_projetos,
            "com_roteiro": projetos_com_roteiro,
            "com_video": projetos_com_video,
            "pendentes": projetos_pendentes,
        },
        "uploads": {
            "totais": uploads_totais,
            "videos_em_output": len(videos_output),
        },
        "ultimo_tema": historico_temas[-1] if historico_temas else None,
        "ultimo_upload": historico_uploads[-1] if historico_uploads else None,
    }


# ─── Relatório Terminal ───────────────────────────────────────────────────────
def formatar_bytes(tamanho: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if tamanho < 1024:
            return f"{tamanho:.1f} {unit}"
        tamanho /= 1024
    return f"{tamanho:.1f} TB"


def imprimir_dashboard(dados: dict):
    """Imprime dashboard compacto no terminal."""
    total_projetos = dados["projetos"]["total"]
    com_video = dados["projetos"]["com_video"]
    pendentes = dados["projetos"]["pendentes"]

    # Barra de progresso visual
    if total_projetos > 0:
        pct = int(50 * com_video / total_projetos)
        barra = "█" * pct + "░" * (50 - pct)
    else:
        barra = "░" * 50

    print(f"""
    ╔══════════════════════════════════════════════════════════╗
    ║         CANAL DARK — Dashboard do Pipeline               ║
    ║         {datetime.now().strftime("%d/%m/%Y %H:%M"):<42}║
    ╠══════════════════════════════════════════════════════════╣
    ║  STATUS GERAL                                           ║
    ║  {'━'*58} ║
    ║  Projetos totais:     {str(total_projetos):<37}║
    ║  Com vídeo gerado:    {str(com_video):<37}║
    ║  Pendentes:           {str(pendentes):<37}║
    ║  [{barra}]  ║
    ║                                                            ║
    ║  PRODUÇÃO                                                ║
    ║  {'━'*58} ║
    ║  Temas na fila:       {str(dados['fila_temas_pendentes']):<37}║
    ║  Classificados (total): {str(dados['total_temas_classificados']):<36}║
    ║  Classificados (7d):   {str(dados['temas_ultimos_7_dias']):<37}║
    ║                                                            ║
    ║  PUBLICAÇÃO                                              ║
    ║  {'━'*58} ║
    ║  Uploads realizados:   {str(dados['uploads']['totais']):<37}║
    ║  Vídeos em output:    {str(dados['uploads']['videos_em_output']):<37}║
    ╚══════════════════════════════════════════════════════════╝
    """)

    # Último tema
    if dados.get("ultimo_tema"):
        t = dados["ultimo_tema"]
        data_str = tempo_relativo(parse_date(t.get("data_roteiro", "")))
        print(f"  📋 Último tema classificado: {t.get('titulo', 'N/A')} ({data_str})")

    if dados.get("ultimo_upload"):
        u = dados["ultimo_upload"]
        data_str = tempo_relativo(parse_date(u.get("data_upload", "")))
        print(f"  📤 Último upload: {u.get('video_id', 'N/A')} ({data_str})")

    print()


# ─── Relatório HTML ───────────────────────────────────────────────────────────
def gerar_html(dados: dict, caminho_saida: Path):
    """Gera relatório HTML interativo."""

    # Calcula estatísticas extras
    temas = dados.get("temas_ultimos_7_dias", 0)
    projetos = dados.get("projetos", {})
    com_video = projetos.get("com_video", 0)
    total = projetos.get("total", 0)
    taxa_conversao = f"{(com_video/max(total,1)*100):.0f}%" if total > 0 else "N/A"

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Canal Dark — Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ background: #0D0D0D; color: #E0E0E0; font-family: 'Segoe UI', Arial, sans-serif; }}
        .container {{ max-width: 1000px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #E63946; font-size: 1.8em; margin-bottom: 4px; }}
        .subtitle {{ color: #888; font-size: 0.85em; margin-bottom: 24px; }}
        .card {{ background: #1A1A1A; border-radius: 12px; padding: 20px; margin-bottom: 16px;
                 border-left: 4px solid #E63946; }}
        .card h2 {{ color: #E63946; font-size: 1em; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }}
        .stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }}
        .stat {{ background: #222; border-radius: 8px; padding: 16px; text-align: center; }}
        .stat .value {{ font-size: 2.2em; font-weight: bold; color: #E63946; }}
        .stat .label {{ font-size: 0.8em; color: #888; text-transform: uppercase; margin-top: 4px; }}
        .progress-bar {{ background: #333; border-radius: 6px; height: 24px; margin: 8px 0; overflow: hidden; }}
        .progress-fill {{ background: linear-gradient(90deg, #8B0000, #E63946); height: 100%;
                         border-radius: 6px; display: flex; align-items: center; justify-content: center;
                         font-size: 0.75em; color: white; font-weight: bold; min-width: 40px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
        th {{ background: #8B0000; color: white; padding: 8px 12px; text-align: left; font-size: 0.8em; }}
        td {{ padding: 8px 12px; border-bottom: 1px solid #333; font-size: 0.9em; }}
        tr:hover {{ background: #222; }}
        .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; font-weight: bold; }}
        .badge-green {{ background: #1B5E20; color: #A5D6A7; }}
        .badge-red {{ background: #7F0000; color: #EF9A9A; }}
        .badge-gray {{ background: #333; color: #999; }}
        .footer {{ text-align: center; color: #555; font-size: 0.75em; margin-top: 30px; }}
        .kanban {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
        .kanban-col {{ background: #151515; border-radius: 8px; padding: 12px; }}
        .kanban-col h3 {{ font-size: 0.85em; color: #888; margin-bottom: 8px; text-transform: uppercase; }}
        .kanban-item {{ background: #222; border-radius: 6px; padding: 8px; margin-bottom: 6px;
                       font-size: 0.85em; border-left: 3px solid #E63946; }}
    </style>
</head>
<body>
<div class="container">
    <h1>🖤 Canal Dark — Pipeline Dashboard</h1>
    <p class="subtitle">Atualizado em {datetime.now().strftime('%d/%m/%Y às %H:%M')} · São Paulo (UTC-3)</p>

    <!-- Stats Cards -->
    <div class="stat-grid">
        <div class="stat">
            <div class="value">{dados['projetos']['total']}</div>
            <div class="label">Projetos</div>
        </div>
        <div class="stat">
            <div class="value">{com_video}</div>
            <div class="label">Vídeos Gerados</div>
        </div>
        <div class="stat">
            <div class="value">{dados['fila_temas_pendentes']}</div>
            <div class="label">Temas Pendentes</div>
        </div>
        <div class="stat">
            <div class="value">{dados['uploads']['totais']}</div>
            <div class="label">Uploadados</div>
        </div>
        <div class="stat">
            <div class="value">{temas}</div>
            <div class="label">Temas (7 dias)</div>
        </div>
        <div class="stat">
            <div class="value">{taxa_conversao}</div>
            <div class="label">Taxa Conversão</div>
        </div>
    </div>

    <!-- Progress -->
    <div class="card" style="margin-top: 16px;">
        <h2>Progresso do Funil</h2>
        <div style="margin-bottom: 8px; font-size: 0.85em; color: #888;">
            Tema Classificado → Roteiro → Imagens → Áudio → Vídeo → Upload
        </div>
        <div class="progress-bar">
            <div class="progress-fill" style="width: {min(taxa_conversao.rstrip('%'), 100) if taxa_conversao != 'N/A' else 0}%">
                {taxa_conversao}
            </div>
        </div>
        <div style="display:flex; gap: 4px; margin-top: 8px;">
            <span class="badge badge-green">📋 {dados['total_temas_classificados']} Classificados</span>
            <span class="badge badge-green">📝 {projetos['com_roteiro']} Com Roteiro</span>
            <span class="badge badge-gray">🎬 {com_video} Montados</span>
            <span class="badge badge-gray">📤 {dados['uploads']['totais']} Publicados</span>
        </div>
    </div>

    <!-- Status Cards -->
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px;">
        <div class="card">
            <h2>📋 Último Tema</h2>
            {f"<strong>{dados['ultimo_tema']['titulo']}</strong><br>" if dados.get('ultimo_tema') else "Nenhum tema classificado ainda.<br>"}
            <span style="color: #888; font-size: 0.8em;">
                {tempo_relativo(parse_date(dados['ultimo_tema']['data_roteiro'])) if dados.get('ultimo_tema') else ''}
            </span>
        </div>
        <div class="card">
            <h2>📤 Último Upload</h2>
            {f"<strong>{dados['ultimo_upload']['video_id']}</strong><br>" if dados.get('ultimo_upload') else "Nenhum upload ainda.<br>"}
            <span style="color: #888; font-size: 0.8em;">
                {tempo_relativo(parse_date(dados['ultimo_upload']['data_upload'])) if dados.get('ultimo_upload') else ''}
            </span>
        </div>
    </div>

    <div class="footer">
        Canal Dark Automation · Pipeline {dados['timestamp'][:10]} · Não afiliado ao YouTube/Google
    </div>
</div>
</body>
</html>"""

    with open(caminho_saida, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"Relatório HTML gerado: {caminho_saida}")


# ─── Notificação por E-mail ───────────────────────────────────────────────────
def enviar_notificacao(dados: dict):
    """Envia resumo por e-mail (requer configuração SMTP no .env)."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    email_destino = os.getenv("EMAIL_NOTIFICACOES", "")
    if not email_destino:
        logger.warning("EMAIL_NOTIFICACOES não configurado no .env")
        return

    projetos = dados["projetos"]
    html = f"""
    <h2>📊 Canal Dark — Report Automático</h2>
    <p><strong>Data:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
    <hr>
    <h3>Produção</h3>
    <ul>
        <li>Projetos totais: <strong>{projetos['total']}</strong></li>
        <li>Com vídeo gerado: <strong>{projetos['com_video']}</strong></li>
        <li>Pendentes: <strong>{projetos['pendentes']}</strong></li>
        <li>Temas na fila: <strong>{dados['fila_temas_pendentes']}</strong></li>
        <li>Temas classificados (7d): <strong>{dados['temas_ultimos_7_dias']}</strong></li>
    </ul>
    <h3>Publicação</h3>
    <ul>
        <li>Uploads totais: <strong>{dados['uploads']['totais']}</strong></li>
        <li>Vídeos em output: <strong>{dados['uploads']['videos_em_output']}</strong></li>
    </ul>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "📊 Canal Dark — Report Semanal"
    msg["From"] = email_destino
    msg["To"] = email_destino
    msg.attach(MIMEText(html, "html"))

    # Tenta usar SMTP configurado
    smtp_server = os.getenv("SMTP_SERVER", "")
    smtp_port = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")

    if smtp_server and smtp_user:
        try:
            with smtplib.SMTP(smtp_server, int(smtp_port)) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
            logger.info(f"Report enviado para {email_destino}")
        except Exception as e:
            logger.error(f"Falha ao enviar e-mail: {e}")
    else:
        logger.warning("SMTP não configurado — salvando relatório localmente")
        caminho_html = DATOS_DIR / "report_last.html"
        gerar_html(dados, caminho_html)


# ─── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Canal Dark — Dashboard de Monitoramento")
    parser.add_argument("--html", action="store_true", help="Gerar relatório HTML")
    parser.add_argument("--notify", action="store_true", help="Enviar relatório por e-mail")
    parser.add_argument("--output", default=str(DATOS_DIR / "dashboard.html"),
                        help="Caminho do relatório HTML")
    args = parser.parse_args()

    logger.info("Coletando dados do pipeline...")
    dados = coletar_dados_pipeline()

    if args.html:
        gerar_html(dados, Path(args.output))
    elif args.notify:
        enviar_notificacao(dados)
    else:
        imprimir_dashboard(dados)

    # Salva último report em JSON para uso por outros sistemas
    report_path = DATOS_DIR / "ultimo_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

"""
Script de Configuração Inicial - Canal Dark
Execute este script ANTES de usar o pipeline pela primeira vez.

Passos:
1. Copie .env.example → .env e preencha suas chaves de API
2. Baixe youtube_client_secrets.json do Google Cloud Console
3. Salve youtube_client_secrets.json na pasta dados/
4. Execute: python scripts/setup_auth.py

Auteur: Canal Dark Automation
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DATOS_DIR = PROJECT_ROOT / "dados"

# ─── Cores para terminal ─────────────────────────────────────────────────────
try:
    from termcolor import cprint
except ImportError:
    def cprint(text, color=None):
        print(text)


def print_step(msg, step):
    print(f"\n{'='*60}")
    print(f"  PASSO {step}: {msg}")
    print(f"{'='*60}")


def check_file(path: Path, description: str) -> bool:
    if path.exists():
        print(f"  [OK] {description}: {path.name}")
        return True
    else:
        print(f"  [X] {description}: FALTANDO → {path}")
        return False


def main():
    print("""
    +==========================================================+
    |           Canal Dark - Configuracao Inicial              |
    +==========================================================+
    """)

    all_ok = True

    # ─── 1. Verifica .env ───────────────────────────────────────────────
    print_step("Verificando arquivos de configuração", 1)

    env_example = PROJECT_ROOT / ".env.example"
    env_file = PROJECT_ROOT / ".env"

    if not env_file.exists():
        if env_example.exists():
            import shutil
            shutil.copy(env_example, env_file)
            print(f"  [i] .env criado a partir de .env.example")
            print(f"     → Edite {env_file} e preencha suas chaves de API")
            all_ok = False
    else:
        print(f"  [OK] .env encontrado")

    # ─── 2. Credenciais OAuth YouTube ─────────────────────────────────────
    print_step("Verificando credenciais YouTube OAuth", 2)

    oauth_file = DATOS_DIR / "youtube_client_secrets.json"
    if not check_file(oauth_file, "OAuth Client Secrets"):
        print("""
     Instruções:
     1. Acesse: https://console.cloud.google.com/apis/credentials
     2. Crie projeto (ou selecione existente)
     3. Vá em 'Credenciais' → 'Criar Credenciais' → 'ID do cliente OAuth'
     4. Tipo: 'App para Desktop'
     5. Baixe o JSON e salve como 'youtube_client_secrets.json'
        na pasta: dados/
        """)
        all_ok = False

    # ─── 3. Testa conectividade com OpenAI ──────────────────────────────
    print_step("Testando conectividade com APIs", 3)

    env_file_path = PROJECT_ROOT / ".env"
    if env_file_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file_path)

    # Testa conectividade com Gemini (preferencial) ou OpenAI
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if gemini_key and gemini_key != "...":
        try:
            from gemini_service import testar_conexao
            resultado = testar_conexao()
            if resultado["status"] == "conectado":
                print(f"  [OK] Gemini API: Conectada")
            else:
                print(f"  [!]  Gemini API: Erro - {resultado.get('erro', 'Desconhecido')} (execute em modo demo)")
        except Exception as e:
            print(f"  [!]  Gemini API: Erro - {e} (execute em modo demo)")
    elif openai_key and openai_key != "sk-...":
        try:
            import openai
            client = openai.OpenAI()
            client.models.list()
            print(f"  [OK] OpenAI API: Conectada")
        except Exception as e:
            print(f"  [!]  OpenAI API: Erro - {e} (execute em modo demo)")
    else:
        print("  [!]  Nenhuma API de LLM configurada (GEMINI_API_KEY ou OPENAI_API_KEY)")

    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "")
    if elevenlabs_key and elevenlabs_key != "...":
        print(f"  [OK] ElevenLabs API: Configurada")
    else:
        print("  [!]  ELEVENLABS_API_KEY não configurada (gTTS será usado como fallback)")

    # ─── 4. FFmpeg ───────────────────────────────────────────────────────
    print_step("Verificando FFmpeg", 4)

    import subprocess
    import glob

    ffmpeg_found = False
    ffmpeg_version = ""

    # Tenta encontrar FFmpeg em Common paths
    ffmpeg_paths = [
        "ffmpeg",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\Gyan\FFmpeg\bin\ffmpeg.exe",
    ]

    # Procura no WinGet packages
    winget_packages = glob.glob(r"C:\Users\rzane\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_*\ffmpeg-*\ffmpeg.exe")
    ffmpeg_paths.extend(winget_packages)

    for ffmpeg_cmd in ffmpeg_paths:
        try:
            result = subprocess.run(
                [ffmpeg_cmd, "-version"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                ffmpeg_version = result.stdout.split("\n")[0]
                print(f"  [OK] FFmpeg: {ffmpeg_version}")
                ffmpeg_found = True
                break
        except Exception:
            continue

    if not ffmpeg_found:
        print("  [X] FFmpeg: Não encontrado")
        print("""
     Instale FFmpeg:
       Windows: winget install ffmpeg
       Ou baixe em: https://ffmpeg.org/download.html
        """)
        all_ok = False

    # ─── 5. Diretórios ────────────────────────────────────────────────────
    print_step("Verificando estrutura de diretórios", 5)

    dirs = [
        PROJECT_ROOT / "projetos",
        PROJECT_ROOT / "dados",
        PROJECT_ROOT / "templates",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "n8n",
        DATOS_DIR,
    ]
    for d in dirs:
        if d.exists():
            print(f"  [OK] {d.relative_to(PROJECT_ROOT)}/")
        else:
            d.mkdir(parents=True, exist_ok=True)
            print(f"  [DIR] Criado: {d.relative_to(PROJECT_ROOT)}/")

    # ─── 6. Autenticação YouTube (se credenciais existirem) ───────────────
    print_step("Autenticação YouTube OAuth", 6)

    if oauth_file.exists():
        print("  [>]  Credenciais encontradas. Iniciando fluxo OAuth...")
        try:
            from youtube_service import oauth_authenticate
            oauth_authenticate()
            print("  [OK] YouTube OAuth: Autenticado com sucesso!")
        except Exception as e:
            print(f"  [X] YouTube OAuth: Erro - {e}")
            all_ok = False
    else:
        print("  [SKIP]  Pulado (OAuth credentials não encontradas)")
        print("     Execute setup_auth.py novamente após baixar o client_secrets.json")

    # ─── Resumo ──────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    if all_ok:
        print("  [OK] CONFIGURAÇÃO COMPLETA - Pipeline pronto para uso!")
    else:
        print("  [!]  CONFIGURAÇÃO PARCIAL - Corrija os itens pendentes acima")
    print(f"{'='*60}\n")

    print("""
  Próximos passos:
  1. Execute os testes unitários: python -m pytest tests/ -v
  2. Teste o pipeline completo: python scripts/pesquisa_temas.py
  3. Importe os workflows n8n da pasta n8n/
  4. Configure o n8n (self-hosted ou cloud)
  5. Programe os triggers no n8n
    """)


if __name__ == "__main__":
    main()

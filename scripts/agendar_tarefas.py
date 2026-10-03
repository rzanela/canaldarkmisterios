"""
AGENDAR TAREFAS — Canal Dark
Cria tarefas no Windows Task Scheduler para disparar o orchestador.

Uso: python agendar_tarefas.py --setup
"""

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ORQUESTRADOR = SCRIPT_DIR / "orquestrador.py"
PYTHONW = sys.executable.replace("python.exe", "pythonw.exe")

# Cronograma: Seg/Qua/Sex — 3x por semana
TAREFAS = [
    {
        "nome": "CanalDark_Pesquisa",
        "desc": "Pesquisa temas trending no Reddit",
        "fase": "pesquisa",
        "hora": "08:00",
        "dias": "MON,WED,FRI",
    },
    {
        "nome": "CanalDark_Roteiro",
        "desc": "Gera roteiro para próximo tema",
        "fase": "roteiro",
        "hora": "09:00",
        "dias": "MON,WED,FRI",
    },
    {
        "nome": "CanalDark_Producao",
        "desc": "Produz vídeo (imagens + narração + montagem)",
        "fase": "producao",
        "hora": "10:00",
        "dias": "MON,WED,FRI",
    },
    {
        "nome": "CanalDark_Upload",
        "desc": "Faz upload e agenda publicação",
        "fase": "upload",
        "hora": "11:00",
        "dias": "TUE,THU,SAT",
    },
    {
        "nome": "CanalDark_Continua",
        "desc": "Continua produção pendente",
        "fase": "continua",
        "hora": "14:00",
        "dias": "SUN",
    },
]


def criar_tarefa(tarefa: dict) -> bool:
    """Cria uma tarefa no Windows Task Scheduler."""
    nome = tarefa["nome"]
    comando = f'"{PYTHONW}" "{ORQUESTRADOR}" --fase {tarefa["fase"]}'
    hora = tarefa["hora"]
    dias = tarefa["dias"]

    # Monta comando schtasks
    cmd = [
        "schtasks",
        "/create",
        "/tn", nome,
        "/tr", comando,
        "/sc", "weekly",
        "/st", hora,
        "/d", dias,
        "/f"  # força recriar se existir
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  ✅ {nome} — {tarefa['fase']} às {hora} ({dias})")
            return True
        else:
            print(f"  ❌ {nome}: {result.stderr.strip()}")
            return False
    except Exception as e:
        print(f"  ❌ {nome}: {e}")
        return False


def remover_tarefas():
    """Remove todas as tarefas do Canal Dark."""
    print("\nRemovendo tarefas agendadas...")
    for tarefa in TAREFAS:
        nome = tarefa["nome"]
        try:
            result = subprocess.run(["schtasks", "/delete", "/tn", nome, "/f"],
                                   capture_output=True, text=True)
            if result.returncode == 0:
                print(f"  🗑️  Removido: {nome}")
            else:
                print(f"  — {nome}: não existia")
        except Exception as e:
            print(f"  ! {nome}: {e}")


def listar_tarefas():
    """Lista tarefas existentes do Canal Dark."""
    print("\nTarefas Canal Dark:")
    for tarefa in TAREFAS:
        nome = tarefa["nome"]
        try:
            result = subprocess.run(["schtasks", "/query", "/tn", nome],
                                   capture_output=True, text=True)
            if result.returncode == 0:
                linhas = result.stdout.strip().split("\n")
                status = "unknown"
                for linha in linhas:
                    if "Executar" in linha or "Running" in linha or "Ready" in linha:
                        status = linha.strip()
                print(f"  ✅ {nome}: {status}")
            else:
                print(f"  — {nome}: não encontrada")
        except Exception as e:
            print(f"  ! {nome}: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Agendar tarefas Canal Dark")
    parser.add_argument("--setup", action="store_true", help="Criar tarefas agendadas")
    parser.add_argument("--remove", action="store_true", help="Remover tarefas agendadas")
    parser.add_argument("--list", action="store_true", help="Listar tarefas existentes")
    args = parser.parse_args()

    if args.remove:
        remover_tarefas()
        return

    if args.list:
        listar_tarefas()
        return

    if args.setup:
        print("\n" + "=" * 60)
        print("CRIANDO TAREFAS AGENDADAS — Canal Dark")
        print("=" * 60)
        print(f"  Python: {PYTHONW}")
        print(f"  Orquestrador: {ORQUESTRADOR}")
        print()

        sucesso = 0
        for tarefa in TAREFAS:
            if criar_tarefa(tarefa):
                sucesso += 1

        print()
        print(f"  {sucesso}/{len(TAREFAS)} tarefas criadas com sucesso.")
        print()
        print("  Para ver as tarefas: python agendar_tarefas.py --list")
        print("  Para remover: python agendar_tarefas.py --remove")
        return
    else:
        parser.print_help()
        print("\nExemplos:")
        print("  python agendar_tarefas.py --setup   # Cria todas as tarefas")
        print("  python agendar_tarefas.py --list    # Lista tarefas existentes")
        print("  python agendar_tarefas.py --remove # Remove todas as tarefas")


if __name__ == "__main__":
    main()

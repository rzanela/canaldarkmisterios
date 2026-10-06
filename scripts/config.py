"""
Config loader para o Canal Dark.
Carrega variáveis de ambiente e config.yaml.
"""
import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

# Carrega .env
ENV_PATH = Path(__file__).parent.parent / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
    logger.info(f".env carregado de {ENV_PATH}")
else:
    logger.warning(".env não encontrado - usando variáveis de ambiente do sistema")

# Carrega config.yaml
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

class Config:
    """Acesso fácil aos valores de configuração."""
    
    # Projeto
    NOME = CONFIG["projeto"]["nome"]
    NICHO = CONFIG["projeto"]["nicho"]
    SUB_NICHO = CONFIG["projeto"]["sub_nicho"]
    IDIOMA = CONFIG["projeto"]["idioma"]
    
    # Vídeo
    DURACAO_MIN = CONFIG["video"]["duracao_minima_minutos"]
    DURACAO_MAX = CONFIG["video"]["duracao_maxima_minutos"]
    DURACAO_SHORT = CONFIG["video"]["duracao_short_segundos"]
    RESOLUCAO = CONFIG["video"]["resolucao"]
    PALETA = CONFIG["video"]["paleta_cores"]
    
    # API Keys
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "nathan")
    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
    YOUTUBE_CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID", "")
    REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
    REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
    REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "CanalDarkBot/1.0")
    
    # Diretórios
    BASE_DIR = Path(__file__).parent.parent
    PROJETOS_DIR = BASE_DIR / "projetos"
    TEMPLATES_DIR = BASE_DIR / "templates"
    DADOS_DIR = BASE_DIR / "dados"

    # FFmpeg
    FFMPEG_PATH = BASE_DIR / "scripts" / "ffmpeg.exe"
    if not FFMPEG_PATH.exists():
        # Tentar PATH do sistema
        import shutil
        ffmpeg_system = shutil.which("ffmpeg")
        FFMPEG_PATH = Path(ffmpeg_system) if ffmpeg_system else ""
    
    @classmethod
    def get_projeto_dir(cls, nome_caso: str) -> Path:
        """Retorna diretório para um projeto de vídeo."""
        # Limpa nome para nome de pasta válido
        nome_limpo = cls._limpar_nome(nome_caso)
        projeto_dir = cls.PROJETOS_DIR / nome_limpo
        projeto_dir.mkdir(parents=True, exist_ok=True)
        return projeto_dir
    
    @staticmethod
    def _limpar_nome(nome: str) -> str:
        """Limpa nome para uso como nome de arquivo/pasta."""
        import re
        nome = re.sub(r'[^\w\s-]', '', nome)
        nome = re.sub(r'[-\s]+', '-', nome)
        return nome[:80].strip('-')

config = Config()

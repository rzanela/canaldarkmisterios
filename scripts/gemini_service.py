"""
Gemini AI Service — Canal Dark
Wrapper para Google Gemini API (GRPC/REST)
Substitui OpenAI GPT-4o com custo ~10x menor e contexto de 1M tokens.

Suporta:
  - Gemini 3.8 Flash (padrão, melhor custo-benefício)
  - Gemini 2.5 Flash (alternativa)
  - Gemini 2.5 Pro (mais capaz, mais caro)
  - Imagen 3 (geração de imagens, alternativa ao DALL-E 3)

Instalação:
  pip install google-generativeai

Variáveis de ambiente:
  GEMINI_API_KEY=...
  GEMINI_MODEL=gemini-3.8-flash
"""

import os
import json
import logging
from typing import Optional

# ─── Logger ───────────────────────────────────────────────────────────────────
try:
    from logger_setup import get_logger
except ImportError:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    get_logger = lambda name: logging.getLogger(name)

logger = get_logger("gemini_service")

# ─── Config ───────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_FLASH_MODEL = os.getenv("GEMINI_FLASH_MODEL", "gemini-3.8-flash")

# ─── Cliente ───────────────────────────────────────────────────────────────────
_client = None


def get_client():
    """Singleton do cliente Gemini."""
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY não configurada no .env.\n"
                "Obtenha sua key em: https://aistudio.google.com/app/apikey"
            )
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        _client = genai.GenerativeModel(GEMINI_MODEL)
        logger.info(f"Gemini cliente inicializado: {GEMINI_MODEL}")
    return _client


def get_flash_client():
    """Cliente Gemini Flash (mais rápido)."""
    global _client
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY não configurada.")
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel(GEMINI_FLASH_MODEL)


# ─── Geração de Texto ──────────────────────────────────────────────────────────
def gerar_texto(
    prompt: str,
    system_instruction: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """
    Gera texto com Gemini.

    Args:
        prompt: O prompt do usuário
        system_instruction: Instruções de sistema ( equivalentes ao system prompt)
        model: Modelo específico (default: GEMINI_MODEL)
        temperature: 0.0 = determinístico, 1.0 = criativo
        max_tokens: Máximo de tokens na resposta

    Returns:
        Texto gerado pela IA
    """
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)

        model_name = model or GEMINI_MODEL
        model_obj = genai.GenerativeModel(model_name)

        # Monta conteúdo
        contents = [{"parts": [{"text": prompt}]}]

        # Instruction = system prompt no Gemini
        gen_config = {
            "generation_config": {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "top_p": 0.95,
                "top_k": 40,
            }
        }
        if system_instruction:
            gen_config["system_instruction"] = {"parts": [{"text": system_instruction}]}

        response = model_obj.generate_content(
            contents=contents,
            **gen_config,
        )

        texto = response.text
        logger.debug(f"Gemini ({model_name}): {len(texto)} chars gerados")
        return texto

    except Exception as e:
        logger.error(f"Erro na geração Gemini: {e}")
        raise


def gerar_json(
    prompt: str,
    system_instruction: Optional[str] = None,
    schema: Optional[dict] = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> dict:
    """
    Gera JSON estruturado com Gemini.
    Usa response_schema para forçar formato JSON (equivalente ao JSON mode).

    Args:
        prompt: Prompt com instrução de gerar JSON
        system_instruction: System prompt
        schema: JSON Schema para validar/formatar a saída
        temperature: Baixo para JSON mais consistente
        max_tokens: Tokens máximos

    Returns:
        dict parseado do JSON gerado
    """
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)

        model_name = GEMINI_MODEL
        model_obj = genai.GenerativeModel(model_name)

        # Gemini 1.5+ suporta generation_config com response_schema
        gen_config = {
            "generation_config": {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "top_p": 0.95,
            }
        }

        if system_instruction:
            gen_config["system_instruction"] = {"parts": [{"text": system_instruction}]}

        # Tenta usar JSON mode se schema for fornecido
        if schema:
            try:
                gen_config["generation_config"]["response_schema"] = schema
                gen_config["generation_config"]["response_mime_type"] = "application/json"
            except Exception:
                # Versões mais antigas não suportam response_schema
                pass

        response = model_obj.generate_content(
            contents=[{"parts": [{"text": prompt}]}],
            **gen_config,
        )

        raw_text = response.text

        # Limpa markdown code blocks se presente
        raw_text = raw_text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

        return json.loads(raw_text)

    except json.JSONDecodeError as e:
        logger.error(f"JSON inválido do Gemini: {e}\nTexto: {raw_text[:500] if 'raw_text' in dir() else 'N/A'}")
        raise
    except Exception as e:
        logger.error(f"Erro Gemini JSON: {e}")
        raise


# ─── Geração de Imagens (Imagen via Gemini) ────────────────────────────────────
def gerar_imagem(
    prompt: str,
    caminho_saida: str,
    model: str = "imagen-3.0-generate-001",
    resolution: str = "1024x1024",
) -> str:
    """
    Gera imagem com Google Imagen 3 (via Gemini API).

    Args:
        prompt: Descrição da imagem
        caminho_saida: Onde salvar a imagem (PATH local)
        model: Modelo de geração (imagen-3.0-generate-001)
        resolution: Resolução (1024x1024, 1792x1024, 1024x1792)

    Returns:
        Caminho do arquivo salvo
    """
    try:
        import google.generativeai as genai
        from PIL import Image
        import urllib.request

        genai.configure(api_key=GEMINI_API_KEY)

        logger.info(f"Gerando imagem com Imagen 3: {prompt[:80]}...")

        response = genai.generate_image(
            model=model,
            prompt=prompt,
            resolution=resolution,
        )

        # Response contém a imagem em base64 ou URL
        if hasattr(response, 'image') and response.image:
            img_bytes = response.image.image_bytes
            img = Image.open(io.BytesIO(img_bytes))
            img.save(caminho_saida)
            logger.info(f"Imagem salva: {caminho_saida}")
            return caminho_saida
        else:
            # Tenta via URL
            image_url = getattr(response, 'url', None)
            if image_url:
                urllib.request.urlretrieve(image_url, caminho_saida)
                logger.info(f"Imagem baixada: {caminho_saida}")
                return caminho_saida

        raise ValueError("Resposta da API de imagem inválida")

    except ImportError as e:
        logger.warning(f"google-generativeai não suporta generate_image diretamente: {e}")
        logger.info("Para gerar imagens, use: (1) DALL-E 3 via OpenAI, (2) Vertex AI Imagen, ou (3) PIL fallback")
        return _gerar_imagem_pil(prompt, caminho_saida)
    except Exception as e:
        logger.error(f"Erro ao gerar imagem com Imagen: {e}")
        return _gerar_imagem_pil(prompt, caminho_saida)


def _gerar_imagem_pil(prompt: str, caminho_saida: str) -> str:
    """Fallback: gera imagem escura com texto usando PIL."""
    from PIL import Image, ImageDraw, ImageFont

    logger.info(f"Gerando thumbnail PIL fallback: {caminho_saida}")

    img = Image.new("RGB", (1024, 1024), (13, 13, 13))
    draw = ImageDraw.Draw(img)

    # Texto central
    try:
        fonte = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 48)
    except Exception:
        fonte = ImageFont.load_default()

    # Word wrap simples
    palavras = prompt.split()[:12]
    texto = " ".join(palavras)
    bbox = draw.textbbox((0, 0), texto, font=fonte)
    largura = bbox[2] - bbox[0]
    x = (1024 - largura) // 2
    y = 512 - 30
    draw.text((x, y), texto, font=fonte, fill=(200, 50, 50))

    img.save(caminho_saida, "PNG")
    return caminho_saida


# ─── Análise de Imagem ─────────────────────────────────────────────────────────
def analisar_imagem(caminho_imagem: str, prompt: str = "Descreva esta imagem em detalhe.") -> str:
    """Analisa uma imagem com Gemini (vision)."""
    try:
        import google.generativeai as genai
        from PIL import Image

        genai.configure(api_key=GEMINI_API_KEY)

        img = Image.open(caminho_imagem)
        model = genai.GenerativeModel(GEMINI_MODEL)

        response = model.generate_content([
            {"text": prompt},
            img,
        ])

        return response.text

    except Exception as e:
        logger.error(f"Erro ao analisar imagem: {e}")
        return ""


# ───.chat (multiturn) ──────────────────────────────────────────────────────────
class GeminiChat:
    """Chat com memória multiturn (similar a OpenAI Assistants)."""

    def __init__(
        self,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
    ):
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)

        self.model_name = model or GEMINI_MODEL
        self.generation_config = {
            "temperature": temperature,
            "top_p": 0.95,
            "top_k": 40,
        }
        if system_instruction:
            self.generation_config["system_instruction"] = {"parts": [{"text": system_instruction}]}

        self.model = genai.GenerativeModel(self.model_name, **self.generation_config)
        self.history = []

    def send(self, message: str) -> str:
        """Envia mensagem e retorna resposta."""
        self.history.append({"role": "user", "parts": [{"text": message}]})

        try:
            response = self.model.generate_content(contents=self.history)
            texto = response.text
            self.history.append({"role": "model", "parts": [{"text": texto}]})
            return texto
        except Exception as e:
            logger.error(f"Erro no chat Gemini: {e}")
            raise

    def clear(self):
        """Limpa histórico."""
        self.history = []


# ─── Teste de Conectividade ────────────────────────────────────────────────────
def testar_conexao() -> dict:
    """Testa a API Gemini e retorna informações da conta."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)

        # Lista modelos disponíveis
        modelos = list(genai.list_models())
        modelos_disponiveis = [m.name for m in modelos if "gemini" in m.name.lower()]

        # Testa geração simples
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content("Responda apenas: OK")
        ok = response.text.strip().startswith("OK")

        return {
            "status": "conectado" if ok else "erro",
            "modelos": modelos_disponiveis,
            "teste": response.text.strip(),
        }
    except Exception as e:
        return {"status": "erro", "erro": str(e)}


# ─── Main / CLI ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import io

    print("🧪 Testando conexão com Gemini...")

    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY não configurada no .env")
        print("   Obtenha em: https://aistudio.google.com/app/apikey")
        exit(1)

    resultado = testar_conexao()

    if resultado["status"] == "conectado":
        print(f"✅ Gemini conectado!")
        print(f"   Modelos disponíveis: {len(resultado['modelos'])}")
        for m in resultado["modelos"][:5]:
            print(f"   - {m}")
    else:
        print(f"❌ Erro: {resultado.get('erro', 'Desconhecido')}")

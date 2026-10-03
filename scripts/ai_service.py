"""
AI Service — Canal Dark
Camada de abstração que suporta OpenAI e Gemini como backends.

Escolha do provider:
  - Prioridade 1: OpenAI (GPT-4o) — mais maduro para roteiros
  - Prioridade 2: Gemini 3.8 Flash — mais barato, 1M tokens contexto

Para ativar Gemini, defina no .env:
  GEMINI_API_KEY=your_key_here
  AI_PROVIDER=gemini

O sistema detecta automaticamente qual usar baseado nas chaves disponíveis.

Instalação:
  pip install google-generativeai

Custo comparativo (aproximado):
  GPT-4o:     ~R$ 75 / 1M tokens  (entrada), ~R$ 300 / 1M tokens (saída)
  Gemini 2.0 Flash: ~R$ 7,5 / 1M tokens (entrada), ~R$ 30 / 1M tokens (saída)
  → Gemini é ~10x mais barato por token
"""

import os
import json
import logging
from typing import Optional, Union

from dotenv import load_dotenv
load_dotenv()

# ─── Logger ───────────────────────────────────────────────────────────────────
try:
    from logger_setup import get_logger
except ImportError:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    get_logger = lambda name: logging.getLogger(name)

logger = get_logger("ai_service")

# ─── Config ───────────────────────────────────────────────────────────────────
AI_PROVIDER = os.getenv("AI_PROVIDER", "auto").lower()  # auto | openai | gemini


def _detect_provider() -> str:
    """Detecta o melhor provider disponível."""
    if AI_PROVIDER != "auto":
        return AI_PROVIDER

    openai_key = os.getenv("OPENAI_API_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")

    # Prioridade: OpenAI se disponível, senão Gemini
    if openai_key and openai_key != "sk-...":
        logger.info("Provider detectado: OpenAI (GPT-4o)")
        return "openai"
    elif gemini_key:
        logger.info("Provider detectado: Gemini 2.0 Flash")
        return "gemini"
    else:
        logger.warning("Nenhuma API key detectada — usando modo demo (GPT-4o com mock)")
        return "openai"  # demo mode


PROVIDER = _detect_provider()
logger.debug(f"AI Provider: {PROVIDER}")


# ─── Texto ───────────────────────────────────────────────────────────────────
def gerar_texto(
    prompt: str,
    system_instruction: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """
    Gera texto usando o provider configurado.
    """
    if PROVIDER == "gemini":
        from gemini_service import gerar_texto as gemini_gerar
        return gemini_gerar(
            prompt=prompt,
            system_instruction=system_instruction,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    else:
        from openai import OpenAI
        client = OpenAI()
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        model_name = model or "gpt-4o"
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content


def gerar_json(
    prompt: str,
    system_instruction: Optional[str] = None,
    schema: Optional[dict] = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> dict:
    """
    Gera JSON estruturado.
    """
    if PROVIDER == "gemini":
        from gemini_service import gerar_json as gemini_json
        return gemini_json(
            prompt=prompt,
            system_instruction=system_instruction,
            schema=schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    else:
        from openai import OpenAI
        client = OpenAI()
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        extra_kwargs = {}
        if schema:
            # OpenAI JSON mode
            extra_kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra_kwargs,
        )

        raw = response.choices[0].message.content
        # Limpa markdown
        raw = raw.strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        return json.loads(raw.strip())


# ─── Imagem ─────────────────────────────────────────────────────────────────
def gerar_imagem(prompt: str, caminho_saida: str, size: str = "1024x1024") -> str:
    """
    Gera imagem com DALL-E 3 (OpenAI) ou Imagen 3 (Gemini).
    """
    if PROVIDER == "gemini":
        from gemini_service import gerar_imagem as gemini_gerar_img
        resolution = size.replace("x", "x")  # same format for Imagen
        return gemini_gerar_img(prompt=prompt, caminho_saida=caminho_saida, resolution=resolution)
    else:
        from openai import OpenAI
        client = OpenAI()
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url
        # Baixa a imagem
        import urllib.request
        urllib.request.urlretrieve(image_url, caminho_saida)
        logger.info(f"Imagem DALL-E 3 salva: {caminho_saida}")
        return caminho_saida


def analisar_imagem(caminho_imagem: str, prompt: str = "Descreva esta imagem.") -> str:
    """Analisa imagem (vision)."""
    if PROVIDER == "gemini":
        from gemini_service import analisar_imagem as gemini_analisar
        return gemini_analisar(caminho_imagem=caminho_imagem, prompt=prompt)
    else:
        from openai import OpenAI
        client = OpenAI()
        with open(caminho_imagem, "rb") as f:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{caminho_imagem}"}},
                    ]}
                ],
                max_tokens=500,
            )
        return response.choices[0].message.content


# ─── Chat com memória ─────────────────────────────────────────────────────────
class AIChat:
    """Chat com histórico (equivale a OpenAI Chat)."""

    def __init__(self, system_instruction: Optional[str] = None, model: Optional[str] = None):
        self.system_instruction = system_instruction
        self.model = model
        self._chat = None

    def send(self, message: str) -> str:
        if PROVIDER == "gemini":
            from gemini_service import GeminiChat
            if self._chat is None:
                self._chat = GeminiChat(
                    system_instruction=self.system_instruction,
                    model=self.model,
                )
            return self._chat.send(message)
        else:
            from openai import OpenAI
            if self._chat is None:
                self._chat = OpenAI()
                self._messages = []
                if self.system_instruction:
                    self._messages.append({"role": "system", "content": self.system_instruction})
                self._model = self.model or "gpt-4o"

            self._messages.append({"role": "user", "content": message})
            response = self._chat.chat.completions.create(
                model=self._model,
                messages=self._messages,
            )
            reply = response.choices[0].message.content
            self._messages.append({"role": "assistant", "content": reply})
            return reply

    def clear(self):
        self._chat = None
        if hasattr(self, "_messages"):
            self._messages = []


# ─── Info do provider ─────────────────────────────────────────────────────────
def get_provider_info() -> dict:
    """Retorna informações sobre o provider ativo."""
    return {
        "provider": PROVIDER,
        "model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp") if PROVIDER == "gemini" else "gpt-4o",
        "gemini_key_configured": bool(os.getenv("GEMINI_API_KEY")),
        "openai_key_configured": bool(os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_API_KEY") != "sk-..."),
    }

# Plantilla de ajustes para Silvestra (config.example.py)
# Copia este archivo como 'config.py' y completa tus claves personales.
# NUNCA subas config.py a GitHub ni a ningún repositorio público.

# 1. Groq (Proveedor principal para texto, voz Whisper y visión - Gratis y ultrarrápido)
# Consigue tu clave gratis en: https://console.groq.com/keys
CLAVE = ""

# 2. Google Gemini (Primer cerebro de respaldo compatible con OpenAI - Gratuito)
# Consigue tu clave gratis en: https://aistudio.google.com/app/apikey
CLAVE_GOOGLE = ""

# 3. OpenRouter (Segundo cerebro de respaldo con modelos gratuitos)
# Consigue tu clave gratis en: https://openrouter.ai/keys
CLAVE_OPENROUTER = ""

# 4. Cerebras (Tercer cerebro de respaldo - Opcional)
# Consigue tu clave gratis en: https://cloud.cerebras.ai/
CLAVE_CEREBRAS = ""

# 5. Mistral AI (Excelente comprensión de español y modelos potentes - Opcional)
# Consigue tu clave gratis en: https://console.mistral.ai/ (Tier de experimentación)
CLAVE_MISTRAL = ""

# 6. NVIDIA NIM (Acceso ultrarrápido a modelos de última generación - Opcional)
# Consigue tu clave y 1000 créditos gratis en: https://build.nvidia.com/
CLAVE_NVIDIA = ""

# 7. Cloudflare Workers AI (10,000 Neurons/día gratis, inferencia serverless global - Opcional)
# Consigue tu token y Account ID en: https://dash.cloudflare.com/ (Workers & AI -> API Tokens)
CLAVE_CLOUDFLARE = ""
ID_CUENTA_CLOUDFLARE = ""

# 8. GitHub Models (Modelos OpenAI, Meta y Microsoft con token de GitHub - Opcional)
# Consigue tu token en: https://github.com/settings/tokens (Personal Access Token)
CLAVE_GITHUB = ""

# 9. SambaNova Cloud (Inferencia acelerada ultra rápida con modelos Llama y Qwen - Opcional)
# Consigue tu clave gratis en: https://cloud.sambanova.ai/apis
CLAVE_SAMBANOVA = ""

# 10. Cohere (Solo como respaldo de emergencia - Plan de prueba de 1,000 llamadas al mes, no comercial)
# Consigue tu Trial API Key en: https://dashboard.cohere.com/api-keys
CLAVE_COHERE = ""

# 11. Telegram Bot (Para hablar con Silvestra desde el celular - Opcional)
# Crea tu bot gratis con @BotFather en Telegram y copia el token aquí
TOKEN_TELEGRAM = ""

# Modelos en Groq (se prueban en orden; si uno falla o supera cuota, pasa al siguiente)
MODELOS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]
MODELO_VOZ = "whisper-large-v3-turbo"
MODELO_VISION = "qwen/qwen3.8-27b"
MODELOS_VISION = [
    "qwen/qwen3.8-27b",
    "meta-models/muse-spark-open",
    "llama-3.2-11b-vision-preview",
    "llama-3.2-90b-vision-preview",
]

ARCHIVO_MEMORIA = "memoria.json"

# Proveedores compatibles con OpenAI con modelos organizados por tarea
PROVEEDORES = [
    {
        "nombre": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "clave": CLAVE,
        "modelos": MODELOS,
        "modelos_charla": [
            "llama-3.1-8b-instant",
            "openai/gpt-oss-20b",
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-120b",
        ],
        "modelos_razonamiento": [
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-120b",
            "llama-3.1-8b-instant",
            "openai/gpt-oss-20b",
        ],
        "modelos_vision": MODELOS_VISION,
    },
    {
        "nombre": "Cloudflare",
        "base_url": f"https://api.cloudflare.com/client/v4/accounts/{ID_CUENTA_CLOUDFLARE}/ai/v1",
        "clave": CLAVE_CLOUDFLARE,
        "modelos": [
            "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
            "@cf/meta/llama-3.1-8b-instruct",
        ],
        "modelos_charla": [
            "@cf/meta/llama-3.1-8b-instruct",
            "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        ],
        "modelos_razonamiento": [
            "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
            "@cf/meta/llama-3.1-8b-instruct",
        ],
        "modelos_vision": [
            "@cf/meta/llama-3.2-11b-vision-instruct",
        ],
    },
    {
        "nombre": "Google",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "clave": CLAVE_GOOGLE,
        "modelos": [
            "gemini-flash-lite-latest",
            "gemini-2.5-flash",
            "gemini-flash-latest",
            "gemini-3-flash-preview",
        ],
        "modelos_charla": [
            "gemini-flash-lite-latest",
            "gemini-2.5-flash",
            "gemini-flash-latest",
        ],
        "modelos_razonamiento": [
            "gemini-2.5-flash",
            "gemini-flash-latest",
            "gemini-3-flash-preview",
            "gemini-flash-lite-latest",
        ],
        "modelos_vision": [
            "gemini-flash-lite-latest",
            "gemini-2.5-flash",
            "gemini-flash-latest",
        ],
    },
    {
        "nombre": "Mistral",
        "base_url": "https://api.mistral.ai/v1",
        "clave": CLAVE_MISTRAL,
        "modelos": [
            "mistral-small-latest",
            "mistral-large-latest",
            "codestral-latest",
        ],
        "modelos_charla": ["mistral-small-latest", "open-mistral-nemo"],
        "modelos_razonamiento": ["codestral-latest", "mistral-large-latest"],
        "modelos_vision": ["pixtral-12b-2409"],
    },
    {
        "nombre": "NVIDIA",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "clave": CLAVE_NVIDIA,
        "modelos": [
            "meta/llama-3.1-8b-instruct",
            "meta/llama-3.3-70b-instruct",
        ],
        "modelos_charla": ["meta/llama-3.1-8b-instruct"],
        "modelos_razonamiento": ["meta/llama-3.3-70b-instruct", "deepseek-ai/deepseek-r1"],
        "modelos_vision": ["meta/llama-3.2-11b-vision-instruct"],
    },
    {
        "nombre": "Cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "clave": CLAVE_CEREBRAS,
        "modelos": ["llama3.1-8b"],
        "modelos_charla": ["llama3.1-8b"],
        "modelos_razonamiento": ["llama-3.3-70b", "llama3.1-8b"],
        "modelos_vision": [],
    },
    {
        "nombre": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "clave": CLAVE_OPENROUTER,
        "modelos": [
            "openrouter/free",
            "meta-llama/llama-3.1-8b-instruct:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemini-2.0-flash-exp:free",
            "nvidia/nemotron-3.5-super-vl:free",
        ],
        "modelos_charla": [
            "openrouter/free",
            "meta-llama/llama-3.1-8b-instruct:free",
            "google/gemini-2.0-flash-exp:free",
            "meta-llama/llama-3.3-70b-instruct:free",
        ],
        "modelos_razonamiento": [
            "meta-llama/llama-3.3-70b-instruct:free",
            "qwen/qwen-2.5-72b-instruct:free",
            "deepseek/deepseek-r1:free",
            "openrouter/free",
        ],
        "modelos_vision": [
            "nvidia/nemotron-3.5-super-vl:free",
            "google/gemini-2.0-flash-exp:free",
            "openrouter/free",
        ],
    },
    {
        "nombre": "GitHub",
        "base_url": "https://models.github.ai/inference",
        "clave": CLAVE_GITHUB,
        "modelos": [
            "openai/gpt-4o-mini",
            "meta/llama-3.1-8b-instruct",
            "openai/gpt-4o",
            "meta/llama-3.3-70b-instruct",
        ],
        "modelos_charla": [
            "openai/gpt-4o-mini",
            "meta/llama-3.1-8b-instruct",
        ],
        "modelos_razonamiento": [
            "openai/gpt-4o",
            "meta/llama-3.3-70b-instruct",
            "openai/gpt-4o-mini",
        ],
        "modelos_vision": [
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
        ],
    },
    {
        "nombre": "SambaNova",
        "base_url": "https://api.sambanova.ai/v1",
        "clave": CLAVE_SAMBANOVA,
        "modelos": [
            "Meta-Llama-3.1-8B-Instruct",
            "Meta-Llama-3.3-70B-Instruct",
            "Qwen2.5-72B-Instruct",
        ],
        "modelos_charla": [
            "Meta-Llama-3.1-8B-Instruct",
            "Meta-Llama-3.3-70B-Instruct",
        ],
        "modelos_razonamiento": [
            "Meta-Llama-3.3-70B-Instruct",
            "Qwen2.5-72B-Instruct",
            "Meta-Llama-3.1-8B-Instruct",
        ],
        "modelos_vision": [],
    },
    {
        "nombre": "Cohere",
        "base_url": "https://api.cohere.ai/compatibility/v1",
        "clave": CLAVE_COHERE,
        "modelos": [
            "command-r-08-2024",
            "command-r-plus-08-2024",
            "command-r",
        ],
        "modelos_charla": [
            "command-r-08-2024",
            "command-r",
        ],
        "modelos_razonamiento": [
            "command-r-plus-08-2024",
            "command-r-08-2024",
        ],
        "modelos_vision": [],
    },
]

# Colores de la interfaz gráfica (PySide6 / cara flotante)
TRANSPARENTE = "#ff00ff"
COLOR_VIVA = "#4fd1c5"
COLOR_DORMIDA = "#6b7694"
COLOR_CUERPO = "#1b2333"
COLOR_ESCUCHA = "#ffd166"

# Lista de permisos (allowlist) para control de la PC
PROGRAMAS_PERMITIDOS = {
    "bloc de notas": "notepad.exe",
    "notas": "notepad.exe",
    "calculadora": "calc.exe",
    "navegador": "msedge.exe",
    "edge": "msedge.exe",
    "explorador": "explorer.exe",
    "archivos": "explorer.exe",
    "vs code": "code",
    "antigravity": "code",
    "codigo": "code",
}

SITIOS_PERMITIDOS = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://www.github.com",
    "wikipedia": "https://es.wikipedia.org",
    "gmail": "https://mail.google.com",
    "correo": "https://mail.google.com",
}

DOMINIOS_WEB_PERMITIDOS = [
    "youtube.com",
    "google.com",
    "github.com",
    "wikipedia.org",
    "gmail.com",
]

# Modulación emocional de voz para Edge-TTS (es-PA-MargaritaNeural)
# Ajustes sutiles de prosodia: rate (velocidad), pitch (tono) y volume (volumen)
EMOCIONES_VOZ = {
    "neutral": {"rate": "+0%", "pitch": "+0Hz", "volume": "+0%"},
    "alegre": {"rate": "+8%", "pitch": "+6Hz", "volume": "+0%"},
    "animada": {"rate": "+12%", "pitch": "+8Hz", "volume": "+0%"},
    "calida": {"rate": "-4%", "pitch": "-2Hz", "volume": "+0%"},
    "seria": {"rate": "-6%", "pitch": "-6Hz", "volume": "+0%"},
    "preocupada": {"rate": "-8%", "pitch": "-4Hz", "volume": "-5%"},
}


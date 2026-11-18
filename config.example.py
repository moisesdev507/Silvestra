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

# 5. Telegram Bot (Para hablar con Silvestra desde el celular - Opcional)
# Crea tu bot gratis con @BotFather en Telegram y copia el token aquí
TOKEN_TELEGRAM = ""

# Modelos en Groq (se prueban en orden; si uno falla o supera cuota, pasa al siguiente)
MODELOS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
MODELO_VOZ = "whisper-large-v3-turbo"
MODELO_VISION = "qwen/qwen3.8-27b"
MODELOS_VISION = [
    "qwen/qwen3.8-27b",
    "meta-models/muse-spark-open",
    "llama-3.2-11b-vision-preview",
    "llama-3.2-90b-vision-preview",
]

ARCHIVO_MEMORIA = "memoria.json"

# Cadena ordenada de proveedores compatibles con OpenAI
PROVEEDORES = [
    {
        "nombre": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "clave": CLAVE,
        "modelos": MODELOS,
    },
    {
        "nombre": "Google",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "clave": CLAVE_GOOGLE,
        "modelos": [
            "gemini-flash-lite-latest",
            "gemini-3-flash-preview",
            "gemini-flash-latest",
        ],
    },
    {
        "nombre": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "clave": CLAVE_OPENROUTER,
        "modelos": [
            "openrouter/free",
            "nvidia/nemotron-3.5-super-vl:free",
        ],
    },
    {
        "nombre": "Cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "clave": CLAVE_CEREBRAS,
        "modelos": ["llama3.1-8b"],
    },
]

# Colores de la interfaz gráfica (PySide6 / cara flotante)
TRANSPARENTE = "#ff00ff"
COLOR_VIVA = "#4fd1c5"
COLOR_DORMIDA = "#6b7694"
COLOR_CUERPO = "#1b2333"
COLOR_ESCUCHA = "#ffd166"

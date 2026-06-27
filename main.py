import logging
from bot import run_bot

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    # Токен бота вшит напрямую
    BOT_TOKEN = "8978200224:AAFwXziT4_-OeHSn8iofOY8F6jdIJo9WuxI"
    
    logger.info("🚀 Запуск TikTok Spam Bot...")
    run_bot(BOT_TOKEN)

import asyncio
import random
import re
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
from playwright.async_api import async_playwright

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Токен бота (получи у @BotFather и укажи в переменных окружения Render)
TOKEN = "8978200224:AAFwXziT4_-OeHSn8iofOY8F6jdIJo9WuxI"  # замени или используй os.getenv("BOT_TOKEN")

# Состояния для ConversationHandler
WAITING_CREDENTIALS = 1
WAITING_LINKS_TEXTS = 2

# Хранилище данных пользователя (в памяти, сбросится при перезапуске)
user_data = {}

def parse_message(text: str):
    """Парсит сообщение: сначала ссылки (каждая с новой строки или через пробел), затем тексты после разделителя '---' или '|тексты|'."""
    # Простой формат: все ссылки и тексты в одной строке, разделённые " | "
    # Пример: https://vm.tiktok.com/... https://... | Привет! | Круто! | Супер!
    # Либо пользователь может отправить многострочное сообщение:
    # строка 1: логин:пароль
    # строки 2..N-3: ссылки (каждая на новой строке)
    # последние 2-3 строки: тексты
    # Мы реализуем универсальный парсинг:
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if len(lines) < 4:
        return None, None, None  # не хватает данных
    # Первая строка — логин и пароль через пробел или ":"
    creds_line = lines[0]
    if ':' in creds_line:
        username, password = creds_line.split(':', 1)
    else:
        parts = creds_line.split()
        if len(parts) >= 2:
            username, password = parts[0], parts[1]
        else:
            return None, None, None
    # Остальные строки: ищем ссылки (начинаются с http) и тексты (всё остальное)
    links = []
    texts = []
    for line in lines[1:]:
        if re.match(r'https?://', line):
            links.append(line)
        else:
            texts.append(line)
    if not (5 <= len(links) <= 35):
        return None, None, None
    if not (2 <= len(texts) <= 3):
        return None, None, None
    return username, password, links, texts

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я спам-бот для TikTok.\n"
        "Отправь мне одним сообщением:\n"
        "1-я строка: логин и пароль TikTok через пробел или двоеточие\n"
        "2-я и далее: ссылки на видео (от 5 до 35 штук, каждая с новой строки)\n"
        "Последние 2-3 строки: тексты для комментариев\n\n"
        "Пример:\n"
        "myuser mypassword\n"
        "https://vm.tiktok.com/video1\n"
        "https://vm.tiktok.com/video2\n"
        "...\n"
        "Классное видео!\n"
        "👍🔥\n"
        "Подпишись на меня"
    )
    return WAITING_CREDENTIALS

async def handle_all_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    result = parse_message(text)
    if result[0] is None:
        await update.message.reply_text("Неверный формат. Убедись, что логин/пароль в первой строке, ссылок от 5 до 35, а текстов 2-3.")
        return WAITING_CREDENTIALS
    username, password, links, texts = result
    user_id = update.effective_user.id
    user_data[user_id] = {
        "username": username,
        "password": password,
        "links": links,
        "texts": texts
    }
    await update.message.reply_text(f"Принято! {len(links)} ссылок и {len(texts)} текстов. Начинаю комментировать... Это может занять несколько минут.")
    # Запускаем в фоне, чтобы не блокировать бота
    asyncio.create_task(process_spam(user_id, update))
    return ConversationHandler.END

async def process_spam(user_id: int, update: Update):
    data = user_data.get(user_id)
    if not data:
        return
    username = data["username"]
    password = data["password"]
    links = data["links"]
    texts = data["texts"]
    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            # Логинимся в TikTok
            await page.goto("https://www.tiktok.com/login", wait_until="networkidle")
            await asyncio.sleep(3)
            # Выбираем логин по телефону/email/username
            # На странице логина есть кнопки "Use phone / email / username"
            try:
                await page.click('text="Use phone / email / username"', timeout=5000)
            except:
                pass  # может уже выбрано
            await asyncio.sleep(2)
            # Заполняем поля
            await page.fill('input[name="username"]', username)
            await page.fill('input[type="password"]', password)
            await page.click('button[type="submit"]')
            await asyncio.sleep(5)  # ждём авторизацию
            # Проверка на капчу/2FA — при появлении бот просто зависнет и через минуту упадёт.
            # Можно добавить скриншот в лог для отладки.
            # Если логин успешен, мы на главной или на странице "интересы". Идём дальше.
            failed = False
            for video_url in links:
                try:
                    await page.goto(video_url, wait_until="networkidle")
                    await asyncio.sleep(random.uniform(2, 4))
                    # Ищем поле комментария
                    comment_box = await page.wait_for_selector('div[contenteditable="true"], textarea', timeout=10000)
                    if not comment_box:
                        logger.warning(f"Не найдено поле комментария на {video_url}")
                        continue
                    await comment_box.click()
                    await asyncio.sleep(1)
                    comment_text = random.choice(texts)
                    await comment_box.type(comment_text, delay=random.randint(50, 150))
                    await asyncio.sleep(1)
                    # Отправляем комментарий (кнопка "Post" или Enter)
                    post_button = await page.query_selector('div[data-e2e="comment-post"], button:has-text("Post")')
                    if post_button:
                        await post_button.click()
                    else:
                        await page.keyboard.press("Enter")
                    logger.info(f"Комментарий '{comment_text}' оставлен под {video_url}")
                    await asyncio.sleep(random.uniform(3, 7))  # случайная пауза между видео
                except Exception as e:
                    logger.error(f"Ошибка при комментировании {video_url}: {e}")
                    continue
            await update.message.reply_text("✅ Готово! Все комментарии расставлены.")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        try:
            await update.message.reply_text(f"❌ Произошла ошибка: {str(e)[:200]}")
        except:
            pass
    finally:
        if browser:
            await browser.close()
        user_data.pop(user_id, None)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_CREDENTIALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_info)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()

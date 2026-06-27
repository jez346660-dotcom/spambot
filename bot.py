import os
import json
import logging
import asyncio
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes
)
from tiktok_browser import TikTokBrowser

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
WAITING_CREDENTIALS = 1
WAITING_LINKS_TEXTS = 2
WAITING_COOKIES_FILE = 3

# Путь к файлу с cookies
COOKIES_FILE = "cookies.json"

# Хранилище задач пользователей (чтобы не запускать несколько задач одновременно)
user_tasks = {}

def validate_and_parse_message(text: str):
    """
    Парсит сообщение пользователя.
    Формат:
    Строка 1: логин:пароль или логин пароль
    Строки 2-N: ссылки на видео (5-35 штук)
    Последние 2-3 строки: тексты комментариев
    
    Возвращает (username, password, links, texts) или (None, None, None, None) при ошибке
    """
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    if len(lines) < 4:
        return None, None, None, None
    
    # Парсим логин и пароль
    creds_line = lines[0]
    if ':' in creds_line:
        username, password = creds_line.split(':', 1)
    else:
        parts = creds_line.split()
        if len(parts) >= 2:
            username, password = parts[0], parts[1]
        else:
            return None, None, None, None
    
    username = username.strip()
    password = password.strip()
    
    # Отделяем ссылки от текстов
    links = []
    texts = []
    
    for line in lines[1:]:
        if line.startswith('http://') or line.startswith('https://'):
            links.append(line)
        else:
            texts.append(line)
    
    # Проверяем количество
    if len(links) < 5 or len(links) > 35:
        logger.warning(f"Неверное количество ссылок: {len(links)}")
        return None, None, None, None
    
    if len(texts) < 2 or len(texts) > 3:
        logger.warning(f"Неверное количество текстов: {len(texts)}")
        return None, None, None, None
    
    return username, password, links, texts


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "👋 Привет! Я бот для автоматического комментирования видео в TikTok.\n\n"
        "📋 **Основные команды:**\n"
        "/start - показать эту справку\n"
        "/status - проверить статус cookies\n"
        "/upload - загрузить файл cookies.json\n"
        "/comment - начать комментирование (отправить данные)\n"
        "/cancel - отменить текущую операцию\n\n"
        "⚠️ **ВНИМАНИЕ:** Массовая автоматическая рассылка комментариев "
        "нарушает правила TikTok. Используйте только в образовательных целях "
        "и с согласия владельцев аккаунтов.\n\n"
        "📖 **Как использовать:**\n"
        "1. Загрузите cookies файл через /upload\n"
        "2. Отправьте /comment и следуйте инструкциям\n"
        "3. Или отправьте сразу всё в формате:\n"
        "```\n"
        "логин:пароль\n"
        "https://vm.tiktok.com/...\n"
        "https://vm.tiktok.com/...\n"
        "... (5-35 ссылок)\n"
        "Текст комментария 1\n"
        "Текст комментария 2\n"
        "```\n\n"
        "🍪 **Как получить cookies:**\n"
        "1. Установите расширение EditThisCookie\n"
        "2. Войдите в TikTok в браузере\n"
        "3. Экспортируйте cookies в JSON\n"
        "4. Отправьте файл боту через /upload"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка статуса cookies"""
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, 'r') as f:
                cookies = json.load(f)
            
            # Проверяем наличие основных сессионных кук
            session_cookies = [c for c in cookies if c.get('name') in ['sessionid', 'sessionid_ss']]
            
            if session_cookies:
                await update.message.reply_text(
                    f"✅ **Cookies загружены**\n"
                    f"📦 Всего кук: {len(cookies)}\n"
                    f"🔑 Найдены сессионные куки: {len(session_cookies)}\n\n"
                    f"Бот готов к работе! Используйте /comment для начала."
                )
            else:
                await update.message.reply_text(
                    "⚠️ **Cookies загружены, но сессионные куки не найдены!**\n"
                    "Возможно, файл повреждён или вы не вошли в TikTok.\n"
                    "Загрузите новый файл через /upload"
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка чтения cookies: {str(e)}")
    else:
        await update.message.reply_text(
            "❌ **Cookies не загружены**\n\n"
            "Отправьте файл cookies.json через команду /upload\n"
            "Инструкция: используйте расширение EditThisCookie в браузере"
        )


async def upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало загрузки cookies"""
    await update.message.reply_text(
        "📤 Отправьте мне файл cookies.json\n\n"
        "Как получить:\n"
        "1. Установите расширение EditThisCookie\n"
        "2. Войдите в TikTok в браузере\n"
        "3. Нажмите на иконку расширения → Export\n"
        "4. Сохраните и отправьте мне JSON файл\n\n"
        "Для отмены: /cancel"
    )
    return WAITING_COOKIES_FILE


async def handle_cookies_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка полученного файла cookies"""
    try:
        file = await update.message.document.get_file()
        
        # Проверяем расширение
        if not update.message.document.file_name.endswith('.json'):
            await update.message.reply_text("❌ Нужен файл с расширением .json")
            return WAITING_COOKIES_FILE
        
        # Скачиваем файл
        await file.download_to_drive(COOKIES_FILE)
        
        # Проверяем что это валидный JSON с куками
        with open(COOKIES_FILE, 'r') as f:
            cookies = json.load(f)
        
        if not isinstance(cookies, list):
            raise ValueError("Неверный формат: ожидается массив")
        
        await update.message.reply_text(
            f"✅ **Cookies успешно загружены!**\n"
            f"📦 Загружено кук: {len(cookies)}\n\n"
            f"Бот готов к работе. Используйте /comment для начала."
        )
        
    except json.JSONDecodeError:
        await update.message.reply_text("❌ Неверный формат JSON. Проверьте файл.")
        return WAITING_COOKIES_FILE
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        return WAITING_COOKIES_FILE
    
    return ConversationHandler.END


async def comment_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса комментирования"""
    await update.message.reply_text(
        "📝 Отправьте мне данные одним сообщением:\n\n"
        "**Формат:**\n"
        "1-я строка: логин:пароль (или логин пароль)\n"
        "2-я и далее: ссылки на видео (от 5 до 35, каждая с новой строки)\n"
        "Последние 2-3 строки: тексты комментариев\n\n"
        "**Пример:**\n"
        "```\n"
        "myuser:mypassword\n"
        "https://www.tiktok.com/@user/video/123456\n"
        "https://vm.tiktok.com/abcde\n"
        "https://www.tiktok.com/@user/video/789012\n"
        "https://vm.tiktok.com/fghij\n"
        "https://www.tiktok.com/@user/video/345678\n"
        "Классное видео! 🔥\n"
        "Подпишись на меня!\n"
        "👍👍👍\n"
        "```\n\n"
        "Для отмены: /cancel"
    )
    return WAITING_LINKS_TEXTS


async def handle_comment_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка данных для комментирования"""
    user_id = update.effective_user.id
    
    # Проверяем, не запущена ли уже задача
    if user_id in user_tasks and not user_tasks[user_id].done():
        await update.message.reply_text(
            "⏳ У вас уже есть активная задача. Дождитесь её завершения или отмените через /cancel"
        )
        return ConversationHandler.END
    
    text = update.message.text
    username, password, links, texts = validate_and_parse_message(text)
    
    if username is None:
        await update.message.reply_text(
            "❌ **Неверный формат данных!**\n\n"
            "Убедитесь что:\n"
            "• Логин и пароль в первой строке\n"
            "• Ссылок от 5 до 35\n"
            "• Текстов 2 или 3\n\n"
            "Попробуйте снова или /cancel для отмены"
        )
        return WAITING_LINKS_TEXTS
    
    # Проверяем наличие cookies
    if not os.path.exists(COOKIES_FILE):
        await update.message.reply_text(
            "⚠️ **Cookies не загружены!**\n\n"
            "Работа без cookies крайне нестабильна. TikTok может запросить капчу.\n\n"
            "Рекомендую загрузить cookies через /upload\n"
            "или продолжить на свой страх и риск командой /comment"
        )
        return WAITING_LINKS_TEXTS
    
    await update.message.reply_text(
        f"✅ **Данные приняты!**\n"
        f"👤 Аккаунт: {username}\n"
        f"🔗 Ссылок: {len(links)}\n"
        f"💬 Текстов: {len(texts)}\n\n"
        f"⏳ Начинаю комментирование... Это займёт несколько минут.\n"
        f"Я сообщу о завершении."
    )
    
    # Запускаем задачу в фоне
    task = asyncio.create_task(
        process_commenting(user_id, username, password, links, texts, update)
    )
    user_tasks[user_id] = task
    
    return ConversationHandler.END


async def process_commenting(
    user_id: int,
    username: str,
    password: str,
    links: list,
    texts: list,
    update: Update
):
    """Фоновая задача комментирования"""
    browser = None
    
    try:
        browser = TikTokBrowser()
        
        # Загружаем cookies если есть
        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE, 'r') as f:
                cookies = json.load(f)
            await browser.set_cookies(cookies)
        
        # Запускаем браузер и логинимся
        login_success = await browser.login(username, password)
        
        if not login_success:
            await update.message.reply_text(
                "❌ **Не удалось войти в TikTok**\n\n"
                "Возможные причины:\n"
                "• Неверный логин/пароль\n"
                "• Cookies устарели (загрузите новые через /upload)\n"
                "• Требуется капча (решается загрузкой свежих cookies)\n"
                "• Аккаунт заблокирован"
            )
            return
        
        # Комментируем видео
        success_count = 0
        fail_count = 0
        
        for i, link in enumerate(links, 1):
            try:
                await update.message.reply_text(f"⏳ Обрабатываю видео {i}/{len(links)}...")
                
                success = await browser.comment_on_video(link, texts)
                
                if success:
                    success_count += 1
                else:
                    fail_count += 1
                    
            except Exception as e:
                logger.error(f"Ошибка при комментировании {link}: {e}")
                fail_count += 1
        
        # Отправляем отчёт
        await update.message.reply_text(
            f"✅ **Комментирование завершено!**\n\n"
            f"📊 **Статистика:**\n"
            f"• Всего видео: {len(links)}\n"
            f"• Успешно: {success_count}\n"
            f"• С ошибками: {fail_count}\n\n"
            f"💡 Если много ошибок, попробуйте обновить cookies через /upload"
        )
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        await update.message.reply_text(
            f"❌ **Произошла ошибка:**\n{str(e)[:500]}\n\n"
            f"Проверьте логи для деталей."
        )
    finally:
        if browser:
            await browser.close()
        # Удаляем задачу из словаря
        if user_id in user_tasks:
            del user_tasks[user_id]


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущей операции"""
    user_id = update.effective_user.id
    
    # Отменяем задачу если есть
    if user_id in user_tasks and not user_tasks[user_id].done():
        user_tasks[user_id].cancel()
        del user_tasks[user_id]
    
    await update.message.reply_text("❌ Операция отменена.")
    return ConversationHandler.END


def run_bot(token: str):
    """Запуск бота"""
    # Создаём приложение
    app = Application.builder().token(token).build()
    
    # Обработчик загрузки cookies
    upload_conv = ConversationHandler(
        entry_points=[CommandHandler("upload", upload_command)],
        states={
            WAITING_COOKIES_FILE: [
                MessageHandler(filters.Document.FileExtension("json"), handle_cookies_file),
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: u.message.reply_text(
                    "❌ Отправьте файл .json или /cancel для отмены"
                ))
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Обработчик комментирования
    comment_conv = ConversationHandler(
        entry_points=[CommandHandler("comment", comment_start)],
        states={
            WAITING_LINKS_TEXTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment_data)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(upload_conv)
    app.add_handler(comment_conv)
    app.add_handler(CommandHandler("cancel", cancel))
    
    # Запускаем бота
    logger.info("🤖 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

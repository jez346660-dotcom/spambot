import asyncio
import random
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


class TikTokBrowser:
    """Класс для работы с TikTok через браузер"""
    
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.cookies = None
        self.is_logged_in = False
        
        # Настройки для маскировки
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
        ]
        
        self.viewports = [
            {"width": 1920, "height": 1080},
            {"width": 1366, "height": 768},
            {"width": 1536, "height": 864},
        ]
    
    async def set_cookies(self, cookies: list):
        """Установка cookies для использования"""
        self.cookies = cookies
        logger.info(f"Установлено {len(cookies)} cookies")
    
    async def _setup_browser(self):
        """Настройка браузера с антидетект мерами"""
        self.playwright = await async_playwright().start()
        
        # Случайный viewport и user-agent
        viewport = random.choice(self.viewports)
        user_agent = random.choice(self.user_agents)
        
        # Запускаем браузер с настройками
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu',
                '--disable-blink-features=AutomationControlled',
            ]
        )
        
        # Создаём контекст с настройками
        self.context = await self.browser.new_context(
            viewport=viewport,
            user_agent=user_agent,
            locale='en-US',
            timezone_id='America/New_York',
        )
        
        # Скрываем признаки автоматизации
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Перезаписываем navigator.plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // Перезаписываем languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
        """)
        
        # Добавляем cookies если есть
        if self.cookies:
            # Фильтруем и адаптируем cookies для Playwright
            formatted_cookies = []
            for cookie in self.cookies:
                formatted_cookie = {
                    'name': cookie.get('name', ''),
                    'value': cookie.get('value', ''),
                    'domain': cookie.get('domain', '.tiktok.com'),
                    'path': cookie.get('path', '/'),
                }
                
                # Добавляем опциональные поля если есть
                if 'expirationDate' in cookie:
                    formatted_cookie['expires'] = cookie['expirationDate']
                if 'httpOnly' in cookie:
                    formatted_cookie['httpOnly'] = cookie['httpOnly']
                if 'secure' in cookie:
                    formatted_cookie['secure'] = cookie['secure']
                if 'sameSite' in cookie:
                    formatted_cookie['sameSite'] = cookie['sameSite']
                
                formatted_cookies.append(formatted_cookie)
            
            await self.context.add_cookies(formatted_cookies)
            logger.info(f"Добавлено {len(formatted_cookies)} cookies в контекст")
        
        self.page = await self.context.new_page()
    
    async def login(self, username: str = None, password: str = None) -> bool:
        """
        Вход в TikTok.
        Если есть cookies - пробуем войти через них.
        Если нет - используем логин/пароль.
        """
        try:
            await self._setup_browser()
            
            # Пробуем открыть главную страницу
            await self.page.goto("https://www.tiktok.com", wait_until="networkidle")
            await asyncio.sleep(random.uniform(2, 4))
            
            # Проверяем, залогинены ли мы через cookies
            logged_in = await self._check_login_status()
            
            if logged_in:
                logger.info("✅ Успешный вход через cookies")
                self.is_logged_in = True
                return True
            
            # Если cookies не сработали и нет логина/пароля
            if not username or not password:
                logger.warning("❌ Cookies недействительны, а логин/пароль не предоставлены")
                return False
            
            # Пробуем войти через форму
            logger.info("🔐 Попытка входа через логин/пароль...")
            
            # Переходим на страницу логина
            await self.page.goto("https://www.tiktok.com/login", wait_until="networkidle")
            await asyncio.sleep(random.uniform(2, 3))
            
            # Ищем и нажимаем "Use phone / email / username"
            try:
                # TikTok может показать разные варианты логина
                selectors = [
                    'text=Use phone / email / username',
                    'text=Use phone or email',
                    'a[href*="login"]',
                    'div:has-text("Log in")',
                ]
                
                for selector in selectors:
                    try:
                        await self.page.click(selector, timeout=5000)
                        await asyncio.sleep(2)
                        break
                    except:
                        continue
            except:
                pass
            
            await asyncio.sleep(2)
            
            # Заполняем логин
            try:
                # TikTok может использовать разные селекторы
                username_selectors = [
                    'input[name="username"]',
                    'input[type="text"]',
                    'input[placeholder*="username"]',
                    'input[placeholder*="email"]',
                    'input[placeholder*="phone"]',
                ]
                
                for selector in username_selectors:
                    try:
                        await self.page.fill(selector, username, timeout=5000)
                        break
                    except:
                        continue
                
                await asyncio.sleep(1)
                
                # Заполняем пароль
                password_selectors = [
                    'input[type="password"]',
                    'input[placeholder*="password"]',
                    'input[name="password"]',
                ]
                
                for selector in password_selectors:
                    try:
                        await self.page.fill(selector, password, timeout=5000)
                        break
                    except:
                        continue
                
                await asyncio.sleep(1)
                
                # Нажимаем кнопку входа
                submit_selectors = [
                    'button[type="submit"]',
                    'button:has-text("Log in")',
                    'button:has-text("Login")',
                    'div:has-text("Log in")',
                ]
                
                for selector in submit_selectors:
                    try:
                        await self.page.click(selector, timeout=5000)
                        break
                    except:
                        continue
                
                # Ждём загрузки после логина
                await asyncio.sleep(random.uniform(4, 7))
                
                # Проверяем статус
                logged_in = await self._check_login_status()
                
                if logged_in:
                    logger.info("✅ Успешный вход через логин/пароль")
                    self.is_logged_in = True
                    return True
                else:
                    logger.warning("❌ Не удалось войти через логин/пароль")
                    return False
                    
            except Exception as e:
                logger.error(f"Ошибка при заполнении формы: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при входе: {e}")
            return False
    
    async def _check_login_status(self) -> bool:
        """Проверка статуса входа"""
        try:
            # Ищем признаки авторизации
            logged_in_indicators = [
                'a[href*="/upload"]',
                'div[data-e2e="upload-icon"]',
                'img[alt*="profile"]',
                'div[class*="profile"]',
            ]
            
            not_logged_in_indicators = [
                'text=Log in',
                'button:has-text("Log in")',
                'a[href*="/login"]',
            ]
            
            # Проверяем признаки что мы НЕ залогинены
            for indicator in not_logged_in_indicators:
                try:
                    element = await self.page.wait_for_selector(indicator, timeout=3000)
                    if element:
                        return False
                except:
                    pass
            
            # Проверяем признаки что мы залогинены
            for indicator in logged_in_indicators:
                try:
                    element = await self.page.wait_for_selector(indicator, timeout=3000)
                    if element:
                        return True
                except:
                    pass
            
            # Если ничего не нашли, проверяем URL
            current_url = self.page.url
            if 'login' in current_url.lower():
                return False
            
            # Делаем скриншот для отладки (только в development)
            # await self.page.screenshot(path="login_check.png")
            
            return True  # Оптимистично считаем что залогинены
            
        except Exception as e:
            logger.error(f"Ошибка проверки статуса: {e}")
            return False
    
    async def comment_on_video(self, video_url: str, texts: list) -> bool:
        """Оставить комментарий под видео"""
        try:
            logger.info(f"Переходим к видео: {video_url}")
            
            # Переходим на страницу видео
            await self.page.goto(video_url, wait_until="networkidle")
            await asyncio.sleep(random.uniform(3, 6))
            
            # Имитируем поведение человека - скроллим страницу
            await self._human_like_scroll()
            await asyncio.sleep(random.uniform(1, 2))
            
            # Ищем поле для комментария
            comment_box = None
            comment_selectors = [
                'div[contenteditable="true"]',
                'div[data-e2e="comment-input"]',
                'textarea[placeholder*="comment"]',
                'textarea[placeholder*="Add comment"]',
                'div[class*="comment"] textarea',
                'div[class*="comment"] [contenteditable]',
            ]
            
            for selector in comment_selectors:
                try:
                    comment_box = await self.page.wait_for_selector(
                        selector, 
                        timeout=5000,
                        state="visible"
                    )
                    if comment_box:
                        logger.info(f"Найдено поле комментария: {selector}")
                        break
                except:
                    continue
            
            if not comment_box:
                logger.warning("❌ Поле комментария не найдено")
                # Делаем скриншот для отладки
                # await self.page.screenshot(path=f"debug_{hash(video_url)}.png")
                return False
            
            # Кликаем в поле
            await comment_box.click()
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            # Очищаем поле если там что-то есть
            await self.page.keyboard.press("Control+a")
            await self.page.keyboard.press("Backspace")
            await asyncio.sleep(0.5)
            
            # Выбираем случайный текст
            comment_text = random.choice(texts)
            
            # Печатаем как человек (с задержками)
            await self._human_like_typing(comment_box, comment_text)
            
            await asyncio.sleep(random.uniform(1, 2))
            
            # Ищем кнопку отправки
            post_button = None
            post_selectors = [
                'div[data-e2e="comment-post"]',
                'button:has-text("Post")',
                'button[type="submit"]',
                'div[class*="post"]',
                'span:has-text("Post")',
            ]
            
            for selector in post_selectors:
                try:
                    post_button = await self.page.wait_for_selector(
                        selector,
                        timeout=3000,
                        state="visible"
                    )
                    if post_button:
                        break
                except:
                    continue
            
            if post_button:
                await post_button.click()
            else:
                # Пробуем отправить через Enter
                await self.page.keyboard.press("Enter")
            
            await asyncio.sleep(random.uniform(2, 4))
            
            logger.info(f"✅ Комментарий оставлен: {comment_text[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при комментировании {video_url}: {e}")
            return False
    
    async def _human_like_scroll(self):
        """Имитация человеческого скролла"""
        try:
            # Случайное количество скроллов
            scroll_count = random.randint(1, 3)
            
            for _ in range(scroll_count):
                # Случайное расстояние скролла
                scroll_distance = random.randint(100, 500)
                
                await self.page.evaluate(f"window.scrollBy(0, {scroll_distance})")
                await asyncio.sleep(random.uniform(0.5, 2))
                
                # Иногда скроллим обратно
                if random.random() < 0.3:
                    await self.page.evaluate(f"window.scrollBy(0, -{scroll_distance // 2})")
                    await asyncio.sleep(random.uniform(0.3, 1))
                    
        except Exception as e:
            logger.error(f"Ошибка при скролле: {e}")
    
    async def _human_like_typing(self, element, text: str):
        """Имитация человеческого печатания"""
        try:
            for char in text:
                await element.type(char, delay=random.randint(30, 150))
                
                # Иногда делаем паузы между словами
                if char == ' ' and random.random() < 0.3:
                    await asyncio.sleep(random.uniform(0.1, 0.4))
                    
                # Иногда "ошибаемся" и исправляем
                if random.random() < 0.02:  # 2% шанс ошибки
                    await self.page.keyboard.press("Backspace")
                    await asyncio.sleep(random.uniform(0.1, 0.3))
                    await element.type(char, delay=random.randint(30, 150))
                    
        except Exception as e:
            # Если не получилось печатать посимвольно, вставляем сразу
            logger.warning(f"Не удалось имитировать печать: {e}")
            await element.fill(text)
    
    async def close(self):
        """Закрытие браузера"""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            logger.info("Браузер закрыт")
        except Exception as e:
            logger.error(f"Ошибка при закрытии браузера: {e}")


# Тестовая функция для локальной проверки
async def test_browser():
    """Тестирование браузера локально"""
    browser = TikTokBrowser()
    
    # Загружаем cookies если есть
    import os
    import json
    
    if os.path.exists("cookies.json"):
        with open("cookies.json", "r") as f:
            cookies = json.load(f)
        await browser.set_cookies(cookies)
    
    # Пробуем войти
    success = await browser.login("test_user", "test_pass")
    print(f"Login success: {success}")
    
    if success:
        # Пробуем комментировать
        result = await browser.comment_on_video(
            "https://www.tiktok.com/@test/video/123456",
            ["Test comment 1", "Test comment 2"]
        )
        print(f"Comment success: {result}")
    
    await browser.close()


if __name__ == "__main__":
    # Для локального тестирования
    asyncio.run(test_browser())

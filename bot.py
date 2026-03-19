import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
SITE_URL = 'https://karnet.krakowculture.pl/'

def log(msg):
    print(f"[LOG] {msg}")

def get_free_events():
    """Парсит бесплатные события с karnet.krakowculture.pl"""
    events = []
    
    try:
        log(f"Запрашиваем {SITE_URL}...")
        response = requests.get(SITE_URL, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }, timeout=15)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            log(f"❌ Ошибка загрузки: статус {response.status_code}")
            return events
            
        soup = BeautifulSoup(response.text, 'html.parser')
        log("✅ Страница загружена")
        
        # Пробуем разные возможные селекторы для карточек событий
        # Сайт может использовать разные классы для разных типов событий
        selectors = [
            ('div', 'event-item'),
            ('div', 'event'),
            ('article', 'post'),
            ('div', 'card'),
            ('div', 'event-card'),
            ('li', 'event'),
            ('div', None),  # Если нет класса, ищем все div
        ]
        
        event_cards = None
        for tag, cls in selectors:
            if cls:
                cards = soup.find_all(tag, class_=cls)
            else:
                cards = soup.find_all(tag)
            
            # Фильтруем по наличию даты (ключевой признак события)
            meaningful_cards = []
            for c in cards:
                text = c.get_text()
                if any(x in text for x in ['2026', '2025', '.20', '.19', '.18']) and len(text) < 500:
                    meaningful_cards.append(c)
            
            if len(meaningful_cards) >= 3:  # Если нашли хотя бы 3 похожих элемента
                log(f"✅ Найдено карточек: {len(meaningful_cards)} (селектор: {tag}.{cls or 'без класса'})")
                event_cards = meaningful_cards[:15]
                break
        
        if not event_cards:
            log("⚠️ Не удалось найти карточки событий. Пробуем альтернативный подход...")
            # Ищем все заголовки с датами рядом
            headings = soup.find_all(['h2', 'h3', 'h4', 'h5'])
            for h in headings[:20]:
                text = h.get_text().strip()
                if len(text) > 5 and len(text) < 100:
                    event_cards = headings[:15]
                    log(f"✅ Найдено заголовков: {len(event_cards)}")
                    break
        
        if not event_cards:
            log("❌ Не удалось найти события на странице")
            return events
        
        # Парсим каждое событие
        for i, card in enumerate(event_cards):
            try:
                # Заголовок
                title = card.get_text().strip()
                if len(title) < 3 or len(title) > 150:
                    continue
                
                # Ссылка (ищем ближайшую <a>)
                link = '#'
                a_tag = card.find('a') if hasattr(card, 'find') else None
                if a_tag and a_tag.get('href'):
                    link = a_tag['href']
                    if not link.startswith('http'):
                        link = 'https://karnet.krakowculture.pl' + link
                
                # Дата (ищем паттерн даты в тексте)
                import re
                date_pattern = r'\d{2}\.\d{2}\.\d{4}'
                dates = re.findall(date_pattern, card.get_text())
                date = dates[0] if dates else "Дата не указана"
                
                # Проверка на бесплатность
                text_lower = card.get_text().lower()
                is_free = any(word in text_lower for word in [
                    'wstęp wolny', 'za darmo', 'free', '0 zł', 'gratis', 
                    'bezpłatny', 'darmowy'
                ])
                
                # Для отладки: покажем первые 10 найденных событий
                if i < 10:
                    log(f"🎫 #{i+1}: '{title[:50]}...' | Дата: {date} | Бесплатно: {is_free}")
                
                # Добавляем ВСЕ события (фильтр бесплатности можно включить позже)
                # Пока собираем всё, чтобы проверить что парсится
                events.append({
                    'title': title,
                    'date': date,
                    'link': link,
                    'is_free': is_free
                })
                
            except Exception as e:
                log(f"⚠️ Ошибка при разборе карточки #{i}: {e}")
                continue
                
    except Exception as e:
        log(f"❌ Критическая ошибка парсинга: {e}")
    
    return events

def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        log("❌ Ошибка: не задан TELEGRAM_TOKEN или CHAT_ID")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    params = {
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    try:
        log(f"📤 Отправляем сообщение в Telegram...")
        response = requests.post(url, params=params, timeout=10)
        if response.status_code == 200:
            log("✅ Сообщение отправлено успешно!")
            return True
        else:
            log(f"❌ Ошибка Telegram API: {response.status_code} | {response.text}")
            return False
    except Exception as e:
        log(f"❌ Ошибка отправки: {e}")
        return False

def main():
    log(f"🚀 Запуск бота Krakow Events | {datetime.now()}")
    events = get_free_events()
    
    # Фильтруем только бесплатные
    free_events = [e for e in events if e['is_free']]
    
    log(f"📊 Найдено событий: {len(events)} | Бесплатных: {len(free_events)}")
    
    # Для теста: если бесплатных нет, отправим все (можно закомментировать потом)
    events_to_send = free_events if free_events else events[:5]
    
    if not events_to_send:
        log("⚠️ Список пуст. Проверьте селекторы или наличие событий на сайте.")
        return

    message = f"🎭 <b>Бесплатные события в Кракове</b>\n📅 {datetime.now().strftime('%d.%m.%Y')}\n\n"
    
    for i, event in enumerate(events_to_send, 1):
        title = event['title'].replace('<', '&lt;').replace('>', '&gt;')
        free_marker = "🆓 " if event['is_free'] else ""
        message += f"{i}. {free_marker}<b>{title}</b>\n🗓 {event['date']}\n🔗 <a href='{event['link']}'>Подробнее</a>\n\n"
    
    if not free_events:
        message += "<i>⚠️ Бесплатных не найдено, показываем все</i>\n"
    message += "<i>Данные: karnet.krakowculture.pl</i>"
    
    send_telegram_message(message)

if __name__ == '__main__':
    main()

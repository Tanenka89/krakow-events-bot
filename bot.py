import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
SITE_URL = 'https://krakowculture.pl'

def get_free_events():
    """Парсит бесплатные события с krakowculture.pl"""
    events = []
    try:
        # Загружаем страницу с фильтрами (пример URL, может потребоваться актуализация)
        response = requests.get(SITE_URL, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ПРИМЕЧАНИЕ: Селекторы ниже нужно будет актуализировать под реальную вёрстку сайта
        # Ищем карточки событий (классы примерные)
        event_cards = soup.find_all('div', class_='event-item') 
        
        for card in event_cards[:5]: # Берём первые 5 событий
            try:
                title = card.find('h3').text.strip()
                link = card.find('a')['href']
                if not link.startswith('http'):
                    link = SITE_URL + link
                
                # Пытаемся найти дату
                date_elem = card.find('span', class_='date')
                date = date_elem.text.strip() if date_elem else "Дата не указана"
                
                # Проверка на бесплатность (ищем маркеры)
                price_elem = card.find('span', class_='price')
                price_text = price_elem.text.strip().lower() if price_elem else ""
                
                is_free = any(word in price_text for word in ['free', 'za darmo', 'wstęp wolny', '0 zł'])
                
                if is_free:
                    events.append({
                        'title': title,
                        'date': date,
                        'link': link
                    })
            except Exception as e:
                continue
                
    except Exception as e:
        print(f"Ошибка парсинга: {e}")
    
    return events

def send_telegram_message(message):
    """Отправляет сообщение в Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    params = {
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, params=params, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        return False

def main():
    print(f"[{datetime.now()}] Запуск бота...")
    events = get_free_events()
    
    if not events:
        print("События не найдены или нужна настройка парсера.")
        # Можно отправить уведомление об ошибке, если нужно
        return

    message = f"🎭 <b>Бесплатные события в Кракове</b>\n📅 {datetime.now().strftime('%d.%m.%Y')}\n\n"
    
    for i, event in enumerate(events, 1):
        message += f"{i}. <b>{event['title']}</b>\n🗓 {event['date']}\n🔗 <a href='{event['link']}'>Подробнее</a>\n\n"
    
    message += "<i>Данные с krakowculture.pl</i>"
    
    if send_telegram_message(message):
        print("Сообщение успешно отправлено!")
    else:
        print("Не удалось отправить сообщение.")

if __name__ == '__main__':
    main()

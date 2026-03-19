import requests
import os
from datetime import datetime, timedelta

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

# Eventbrite API endpoint
BASE_URL = 'https://www.eventbriteapi.com/v3/events/search/'

def log(msg):
    print(f"[LOG] {msg}")

def get_free_events():
    """Получает бесплатные события в Кракове через Eventbrite API"""
    events = []
    
    # Параметры запроса
    now = datetime.now()
    params = {
        'location.address': 'Krakow, Poland',
        'location.within': '25km',
        'start_date.range_start': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'start_date.range_end': (now + timedelta(days=14)).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'free': 'true',  # Только бесплатные!
        'sort_by': 'date',
    }
    
    try:
        log(f"📡 Запрашиваем Eventbrite API...")
        log(f"📍 Краков, {now.strftime('%d.%m')} - {(now + timedelta(days=14)).strftime('%d.%m')}")
        
        response = requests.get(BASE_URL, params=params, timeout=15)
        
        if response.status_code != 200:
            log(f"❌ Eventbrite API: статус {response.status_code}")
            log(f"Response: {response.text[:300]}")
            return events
            
        data = response.json()
        raw_count = len(data.get('events', []))
        log(f"✅ Получено событий: {raw_count}")
        
        for event in data.get('events', [])[:7]:  # Берём первые 7
            try:
                title = event.get('name', {}).get('text', 'Без названия')
                url = event.get('url', '#')
                
                # Дата начала
                start = event.get('start', {}).get('local', '')
                if start and 'T' in start:
                    date_part = start.split('T')[0]  # 2026-03-20
                    time_part = start.split('T')[1][:5]  # 18:00
                    start = f"{date_part[5:]} {time_part}"  # 03-20 18:00
                
                # Место проведения
                venue = event.get('venue', {})
                venue_name = venue.get('name', 'Онлайн') if venue else 'Онлайн'
                address = venue.get('address', {})
                city = address.get('city', 'Krakow')
                
                events.append({
                    'title': title,
                    'date': start or 'Дата уточняется',
                    'venue': f"{venue_name}, {city}",
                    'link': url
                })
                log(f"🎫 + {title[:50]}...")
                
            except Exception as e:
                log(f"⚠️ Ошибка при разборе события: {e}")
                continue
                
    except Exception as e:
        log(f"❌ Критическая ошибка: {e}")
    
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
            log(f"❌ Telegram API: {response.status_code} | {response.text}")
            return False
    except Exception as e:
        log(f"❌ Ошибка отправки: {e}")
        return False

def main():
    log(f"🚀 Запуск бота Krakow Free Events | {datetime.now()}")
    events = get_free_events()
    log(f"📊 Найдено бесплатных событий: {len(events)}")
    
    if not events:
        log("⚠️ События не найдены. Это может быть:")
        log("   - Нет бесплатных событий в ближайшие 14 дней")
        log("   - Eventbrite не покрывает Краков хорошо")
        # Отправляем уведомление даже если пусто
        message = "🔍 На ближайшие 2 недели бесплатных событий в Кракове не найдено.\n\n<i>Попробуйте позже!</i>"
        send_telegram_message(message)
        return

    message = f"🎭 <b>Бесплатные события в Кракове</b>\n📅 {datetime.now().strftime('%d.%m.%Y')}\n\n"
    
    for i, e in enumerate(events, 1):
        title = e['title'].replace('<', '&lt;').replace('>', '&gt;')
        message += f"{i}. <b>{title}</b>\n"
        message += f"🗓 {e['date']} | 📍 {e['venue']}\n"
        message += f"🔗 <a href='{e['link']}'>Регистрация</a>\n\n"
    
    message += "<i>Данные: Eventbrite.com</i>"
    
    send_telegram_message(message)

if __name__ == '__main__':
    main()

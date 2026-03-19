import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime, timedelta
import re

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
EVENTBRITE_TOKEN = os.getenv('EVENTBRITE_TOKEN', '')

def log(msg):
    print(f"[LOG] {msg}")

# =============================================================================
# ИСТОЧНИК 1: EVENTBRITE
# =============================================================================
def get_eventbrite_events():
    """Получает бесплатные события из Eventbrite"""
    events = []
    now = datetime.now()
    
    params = {
        'location.address': 'Krakow, Poland',
        'location.within': '40km',
        'start_date.range_start': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'start_date.range_end': (now + timedelta(days=21)).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'sort_by': 'date',
        'expand': 'venue',
    }
    
    headers = {}
    if EVENTBRITE_TOKEN:
        headers['Authorization'] = f'Bearer {EVENTBRITE_TOKEN}'
    
    try:
        log("📡 [Eventbrite] Запрос API...")
        response = requests.get(
            'https://www.eventbriteapi.com/v3/events/search/',
            params=params,
            headers=headers,
            timeout=20
        )
        
        if response.status_code != 200:
            log(f"⚠️ [Eventbrite] Статус {response.status_code}")
            return events
        
        data = response.json()
        raw_count = len(data.get('events', []))
        log(f"✅ [Eventbrite] Найдено событий: {raw_count}")
        
        for event in data.get('events', [])[:10]:
            try:
                is_free = event.get('is_free', False)
                if not is_free:
                    continue
                
                title = event.get('name', {}).get('text', 'Без названия')
                url = event.get('url', '#')
                
                start = event.get('start', {}).get('local', '')
                if start and 'T' in start:
                    date_part = start.split('T')[0]
                    time_part = start.split('T')[1][:5]
                    start = f"{date_part[5:]} {time_part}"
                
                venue = event.get('venue', {})
                if venue:
                    venue_name = venue.get('name', 'Онлайн')
                    is_online = venue.get('is_online', False)
                else:
                    venue_name = 'Онлайн'
                    is_online = True
                
                # Помечаем онлайн-события
                if is_online or 'online' in venue_name.lower():
                    venue_name = "🌐 Онлайн"
                
                events.append({
                    'title': title,
                    'date': start or 'Дата уточняется',
                    'venue': venue_name,
                    'link': url,
                    'source': 'Eventbrite'
                })
            except Exception as e:
                log(f"⚠️ [Eventbrite] Ошибка разбора: {e}")
        
        log(f"🎫 [Eventbrite] Бесплатных: {len(events)}")
        
    except Exception as e:
        log(f"❌ [Eventbrite] Критическая ошибка: {e}")
    
    return events

# =============================================================================
# ИСТОЧНИК 2: MEETUP.COM (через публичный API)
# =============================================================================
def get_meetup_events():
    """Получает события из Meetup.com"""
    events = []
    now = datetime.now()
    
    # Meetup GraphQL API (публичный endpoint)
    query = """
    query {
      findSearchableLocations(query: "Krakow, Poland") {
        locations {
          lat
          lng
          name
        }
      }
    }
    """
    
    # Упрощённый подход: используем RSS-подобный endpoint
    try:
        log("📡 [Meetup] Запрос...")
        
        # Meetup не имеет простого публичного API без авторизации
        # Используем альтернативу: парсим страницу поиска
        search_url = "https://www.meetup.com/find/?source=GROUPS&keywords=language&location=pl--krakow"
        
        response = requests.get(search_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }, timeout=15)
        
        if response.status_code != 200:
            log(f"⚠️ [Meetup] Статус {response.status_code}")
            return events
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ищем карточки событий (классы могут меняться)
        cards = soup.find_all('li', {'data-rh': True})[:10]
        
        for card in cards:
            try:
                title_elem = card.find('h3') or card.find('a', {'data-testid': 'event-card-title'})
                if not title_elem:
                    continue
                
                title = title_elem.get_text().strip()
                if len(title) < 3:
                    continue
                
                link_elem = card.find('a', href=True)
                link = link_elem['href'] if link_elem else '#'
                if link.startswith('/'):
                    link = 'https://www.meetup.com' + link
                
                # Дата
                time_elem = card.find('time')
                date = time_elem.get('datetime', 'Дата не указана') if time_elem else 'Дата не указана'
                if date and 'T' in date:
                    date = f"{date[5:10]} {date[11:16]}"
                
                # Проверка на языковой клуб или онлайн
                text_lower = card.get_text().lower()
                is_language = any(x in text_lower for x in ['language', 'english', 'polish', 'conversation', 'клуб', 'язык'])
                is_online = any(x in text_lower for x in ['online', 'virtual', 'zoom'])
                
                # Берём только языковые или онлайн
                if is_language or is_online:
                    venue = "🌐 Онлайн" if is_online else "📍 Krakow"
                    events.append({
                        'title': title,
                        'date': date,
                        'venue': venue,
                        'link': link,
                        'source': 'Meetup'
                    })
                    log(f"🎫 [Meetup] + {title[:40]}...")
                
            except Exception as e:
                log(f"⚠️ [Meetup] Ошибка разбора: {e}")
                continue
        
        log(f"🎫 [Meetup] Найдено: {len(events)}")
        
    except Exception as e:
        log(f"❌ [Meetup] Критическая ошибка: {e}")
    
    return events

# =============================================================================
# ИСТОЧНИК 3: KRAKOW.TRAVEL (официальный портал)
# =============================================================================
def get_krakow_travel_events():
    """Парсит события с krakow.travel"""
    events = []
    
    try:
        log("📡 [krakow.travel] Запрос...")
        
        # Раздел событий на туристическом портале
        url = "https://krakow.travel/en/events/"
        
        response = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }, timeout=15)
        
        if response.status_code != 200:
            log(f"⚠️ [krakow.travel] Статус {response.status_code}")
            return events
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ищем карточки событий
        selectors = [
            ('article', 'event-item'),
            ('div', 'event'),
            ('div', 'card'),
            ('div', 'post'),
        ]
        
        event_cards = None
        for tag, cls in selectors:
            cards = soup.find_all(tag, class_=cls) if cls else soup.find_all(tag)
            if len(cards) >= 2:
                event_cards = cards[:10]
                log(f"✅ [krakow.travel] Найдено карточек: {len(event_cards)}")
                break
        
        if not event_cards:
            # Альтернатива: ищем все ссылки с датами
            links = soup.find_all('a', href=True)
            for link in links[:20]:
                href = link['href']
                if '/event' in href or '/events' in href:
                    title = link.get_text().strip()
                    if len(title) > 5 and len(title) < 100:
                        event_cards = links[:10]
                        log(f"✅ [krakow.travel] Найдено ссылок: {len(event_cards)}")
                        break
        
        if not event_cards:
            log("⚠️ [krakow.travel] Не найдено событий")
            return events
        
        for card in event_cards:
            try:
                # Заголовок
                if hasattr(card, 'get_text'):
                    title = card.get_text().strip()
                else:
                    title = str(card).strip()
                
                if len(title) < 3 or len(title) > 150:
                    continue
                
                # Ссылка
                link = '#'
                if hasattr(card, 'get') and card.get('href'):
                    link = card['href']
                else:
                    a_tag = card.find('a') if hasattr(card, 'find') else None
                    if a_tag and a_tag.get('href'):
                        link = a_tag['href']
                
                if link.startswith('/'):
                    link = 'https://krakow.travel' + link
                elif not link.startswith('http'):
                    link = 'https://krakow.travel/en/events/' + link
                
                # Дата (ищем паттерн)
                date_pattern = r'\d{2}\.\d{2}\.\d{4}'
                dates = re.findall(date_pattern, card.get_text()) if hasattr(card, 'get_text') else []
                date = dates[0] if dates else "Дата не указана"
                
                # Проверка на бесплатность
                text_lower = card.get_text().lower() if hasattr(card, 'get_text') else ''
                is_free = any(word in text_lower for word in [
                    'free', 'wstęp wolny', 'za darmo', 'gratis', '0 zł'
                ])
                
                # Для начала берём все события (фильтр бесплатности можно включить)
                events.append({
                    'title': title,
                    'date': date,
                    'venue': '📍 Krakow',
                    'link': link,
                    'source': 'krakow.travel',
                    'is_free': is_free
                })
                
            except Exception as e:
                log(f"⚠️ [krakow.travel] Ошибка разбора: {e}")
                continue
        
        # Фильтруем только бесплатные
        free_events = [e for e in events if e.get('is_free', False)]
        log(f"🎫 [krakow.travel] Всего: {len(events)} | Бесплатных: {len(free_events)}")
        
        return free_events if free_events else events[:5]
        
    except Exception as e:
        log(f"❌ [krakow.travel] Критическая ошибка: {e}")
    
    return events

# =============================================================================
# ОТПРАВКА В TELEGRAM
# =============================================================================
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

# =============================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# =============================================================================
def main():
    log(f"🚀 Запуск бота Krakow Free Events | {datetime.now()}")
    
    # Собираем события из всех источников
    all_events = []
    
    eventbrite = get_eventbrite_events()
    all_events.extend(eventbrite)
    
    meetup = get_meetup_events()
    all_events.extend(meetup)
    
    krakow = get_krakow_travel_events()
    all_events.extend(krakow)
    
    log(f"📊 ВСЕГО найдено событий: {len(all_events)}")
    log(f"   • Eventbrite: {len(eventbrite)}")
    log(f"   • Meetup: {len(meetup)}")
    log(f"   • krakow.travel: {len(krakow)}")
    
    # Удаляем дубликаты по заголовку
    seen = set()
    unique_events = []
    for e in all_events:
        key = e['title'][:30].lower()
        if key not in seen:
            seen.add(key)
            unique_events.append(e)
    
    log(f"📊 После удаления дублей: {len(unique_events)}")
    
    if not unique_events:
        log("⚠️ События не найдены ни в одном источнике")
        message = "🔍 На ближайшие 3 недели событий не найдено.\n\n<i>Попробуйте позже!</i>"
        send_telegram_message(message)
        return
    
    # Формируем сообщение (максимум 15 событий)
    message = f"🎭 <b>Бесплатные события в Кракове</b>\n📅 {datetime.now().strftime('%d.%m.%Y')}\n\n"
    
    for i, e in enumerate(unique_events[:15], 1):
        title = e['title'].replace('<', '&lt;').replace('>', '&gt;')
        source_icon = {'Eventbrite': '🟠', 'Meetup': '🔵', 'krakow.travel': '🟢'}.get(e['source'], '⚪')
        
        message += f"{i}. {source_icon} <b>{title}</b>\n"
        message += f"🗓 {e['date']} | {e['venue']}\n"
        message += f"🔗 <a href='{e['link']}'>Подробнее</a>\n\n"
    
    message += "<i>Источники: Eventbrite • Meetup • krakow.travel</i>"
    
    send_telegram_message(message)

if __name__ == '__main__':
    main()

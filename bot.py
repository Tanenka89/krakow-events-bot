import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime, timedelta
import re
import time

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
EVENTBRITE_TOKEN = os.getenv('EVENTBRITE_TOKEN', '')

def log(msg):
    print(f"[LOG] {msg}")

# =============================================================================
# ИСТОЧНИК 1: KARNET.KRAKOWCULTURE.PL (улучшенная версия)
# =============================================================================
def get_karnet_events():
    """Парсит бесплатные события с karnet.krakowculture.pl"""
    events = []
    
    # Прямая ссылка на фильтр бесплатных событий
    url = "https://karnet.krakowculture.pl/wydarzenia"
    params = {
        'Param[p_12]': '1',  # Фильтр: бесплатные события
        'radius': '1000',
    }
    
    # Заголовки, максимально похожие на реальный браузер
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0',
    }
    
    session = requests.Session()
    session.headers.update(headers)
    
    try:
        log("📡 [karnet.krakowculture.pl] Запрос...")
        
        # Пробуем несколько раз с паузой (защита от временных блокировок)
        for attempt in range(3):
            try:
                response = session.get(url, params=params, timeout=30)
                log(f"📡 [karnet] Попытка {attempt + 1}: статус {response.status_code}")
                
                if response.status_code == 200:
                    break
                elif response.status_code == 403:
                    log("⚠️ [karnet] Доступ запрещён (403), пробуем снова...")
                    time.sleep(2)
                elif response.status_code >= 500:
                    log("⚠️ [karnet] Ошибка сервера, пробуем снова...")
                    time.sleep(2)
                else:
                    log(f"⚠️ [karnet] Неожиданный статус: {response.status_code}")
                    time.sleep(1)
                    
            except requests.exceptions.Timeout:
                log(f"⚠️ [karnet] Тайм-аут, попытка {attempt + 1}")
                time.sleep(2)
            except requests.exceptions.ConnectionError:
                log(f"⚠️ [karnet] Ошибка соединения, попытка {attempt + 1}")
                time.sleep(2)
        else:
            log("❌ [karnet] Все попытки исчерпаны")
            return events
        
        if response.status_code != 200:
            log(f"❌ [karnet] Не удалось загрузить страницу: {response.status_code}")
            return events
        
        soup = BeautifulSoup(response.text, 'html.parser')
        log("✅ [karnet] Страница загружена")
        
        # Ищем карточки событий - пробуем разные селекторы
        selectors = [
            ('div', 'event-item'),
            ('div', 'event'),
            ('article', None),
            ('div', 'card'),
            ('div', 'box'),
            ('li', None),
        ]
        
        event_cards = None
        for tag, cls in selectors:
            if cls:
                cards = soup.find_all(tag, class_=cls)
            else:
                cards = soup.find_all(tag)
            
            # Фильтруем по размеру текста (карточки событий обычно имеют определённый размер)
            meaningful = [c for c in cards if 50 < len(c.get_text()) < 2000]
            
            if len(meaningful) >= 3:
                event_cards = meaningful[:15]
                log(f"✅ [karnet] Найдено карточек: {len(event_cards)} (селектор: {tag}.{cls or '*'})")
                break
        
        if not event_cards:
            # Альтернатива: ищем все ссылки на события
            links = soup.find_all('a', href=True)
            event_links = []
            for link in links:
                href = link.get('href', '')
                text = link.get_text().strip()
                if '/wydarzenie' in href or '/event' in href:
                    if text and 5 < len(text) < 150:
                        event_links.append({'title': text, 'link': href})
            
            if event_links:
                log(f"✅ [karnet] Найдено ссылок на события: {len(event_links)}")
                for item in event_links[:10]:
                    events.append({
                        'title': item['title'],
                        'date': 'Дата уточняется',
                        'venue': '📍 Krakow',
                        'link': item['link'] if item['link'].startswith('http') else 'https://karnet.krakowculture.pl' + item['link'],
                        'source': 'karnet',
                        'is_free': True  # Мы же фильтруем по бесплатным в URL
                    })
                return events[:10]
            else:
                log("⚠️ [karnet] Не найдено событий")
                return events
        
        # Парсим каждую карточку
        for card in event_cards:
            try:
                # Заголовок
                title = None
                for tag in ['h3', 'h4', 'h2', 'a']:
                    elem = card.find(tag)
                    if elem and elem.get_text().strip():
                        title = elem.get_text().strip()
                        break
                
                if not title or len(title) < 3 or len(title) > 150:
                    title = card.get_text().strip()[:100]
                
                # Ссылка
                link = '#'
                a_tag = card.find('a', href=True)
                if a_tag:
                    link = a_tag['href']
                    if not link.startswith('http'):
                        link = 'https://karnet.krakowculture.pl' + link
                
                # Дата (ищем паттерн в тексте)
                text = card.get_text()
                date_pattern = r'(\d{2}\.\d{2}\.\d{4})'
                dates = re.findall(date_pattern, text)
                date = dates[0] if dates else 'Дата уточняется'
                
                # Время
                time_pattern = r'(\d{2}:\d{2})'
                times = re.findall(time_pattern, text)
                if times:
                    date = f"{date} {times[0]}"
                
                # Место
                venue = '📍 Krakow'
                venue_patterns = [r'ul\.\s*[\w\s]+', r'pl\.\s*[\w\s]+', r'aleja\s*[\w\s]+']
                for pattern in venue_patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        venue = match.group(0)[:50]
                        break
                
                events.append({
                    'title': title,
                    'date': date,
                    'venue': venue,
                    'link': link,
                    'source': 'karnet',
                    'is_free': True
                })
                
            except Exception as e:
                log(f"⚠️ [karnet] Ошибка разбора карточки: {e}")
                continue
        
        log(f"🎫 [karnet] Найдено событий: {len(events)}")
        
    except Exception as e:
        log(f"❌ [karnet] Критическая ошибка: {e}")
    
    return events

# =============================================================================
# ИСТОЧНИК 2: EVENTBRITE
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
# ИСТОЧНИК 3: MEETUP.COM
# =============================================================================
def get_meetup_events():
    """Получает события из Meetup.com"""
    events = []
    
    try:
        log("📡 [Meetup] Запрос...")
        
        search_url = "https://www.meetup.com/find/?source=GROUPS&keywords=language&location=pl--krakow"
        
        response = requests.get(search_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
        }, timeout=15)
        
        if response.status_code != 200:
            log(f"⚠️ [Meetup] Статус {response.status_code}")
            return events
        
        soup = BeautifulSoup(response.text, 'html.parser')
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
                
                time_elem = card.find('time')
                date = time_elem.get('datetime', 'Дата не указана') if time_elem else 'Дата не указана'
                if date and 'T' in date:
                    date = f"{date[5:10]} {date[11:16]}"
                
                text_lower = card.get_text().lower()
                is_language = any(x in text_lower for x in ['language', 'english', 'polish', 'conversation', 'клуб', 'язык'])
                is_online = any(x in text_lower for x in ['online', 'virtual', 'zoom'])
                
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
# ИСТОЧНИК 4: KRAKOW.TRAVEL
# =============================================================================
def get_krakow_travel_events():
    """Парсит события с krakow.travel"""
    events = []
    
    try:
        log("📡 [krakow.travel] Запрос...")
        
        url = "https://krakow.travel/en/events/"
        
        response = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9,pl;q=0.8',
        }, timeout=15)
        
        if response.status_code != 200:
            log(f"⚠️ [krakow.travel] Статус {response.status_code}")
            return events
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
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
                if hasattr(card, 'get_text'):
                    title = card.get_text().strip()
                else:
                    title = str(card).strip()
                
                if len(title) < 3 or len(title) > 150:
                    continue
                
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
                
                date_pattern = r'\d{2}\.\d{2}\.\d{4}'
                dates = re.findall(date_pattern, card.get_text()) if hasattr(card, 'get_text') else []
                date = dates[0] if dates else "Дата не указана"
                
                text_lower = card.get_text().lower() if hasattr(card, 'get_text') else ''
                is_free = any(word in text_lower for word in [
                    'free', 'wstęp wolny', 'za darmo', 'gratis', '0 zł'
                ])
                
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
    
    all_events = []
    
    # 1. Karnet (приоритетный источник)
    karnet = get_karnet_events()
    all_events.extend(karnet)
    
    # 2. Eventbrite
    eventbrite = get_eventbrite_events()
    all_events.extend(eventbrite)
    
    # 3. Meetup
    meetup = get_meetup_events()
    all_events.extend(meetup)
    
    # 4. krakow.travel
    krakow = get_krakow_travel_events()
    all_events.extend(krakow)
    
    log(f"📊 ВСЕГО найдено событий: {len(all_events)}")
    log(f"   • karnet.krakowculture.pl: {len(karnet)}")
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
    
    # Формируем сообщение (максимум 20 событий)
    message = f"🎭 <b>Бесплатные события в Кракове</b>\n📅 {datetime.now().strftime('%d.%m.%Y')}\n\n"
    
    for i, e in enumerate(unique_events[:20], 1):
        title = e['title'].replace('<', '&lt;').replace('>', '&gt;')
        source_icon = {
            'karnet': '🟣',
            'Eventbrite': '🟠', 
            'Meetup': '🔵', 
            'krakow.travel': '🟢'
        }.get(e['source'], '⚪')
        
        message += f"{i}. {source_icon} <b>{title}</b>\n"
        message += f"🗓 {e['date']} | {e['venue']}\n"
        message += f"🔗 <a href='{e['link']}'>Подробнее</a>\n\n"
    
    message += "<i>Источники: karnet • Eventbrite • Meetup • krakow.travel</i>"
    
    send_telegram_message(message)

if __name__ == '__main__':
    main()

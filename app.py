from flask import Flask, render_template, request, redirect, session, url_for
import psycopg2
from psycopg2.extras import RealDictCursor
import qrcode
import io
import base64
from weasyprint import HTML
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'tvoje_velmi_tajne_heslo_123'

# --- KONFIGURACE DATABÁZE ---
# Sem vlož svůj Connection String ze Supabase (URI)
# Změna: uživatelské jméno je teď "postgres.rrwefiglecnruxwkzjqc"

def get_db_connection():
    # Rozložíme připojení na jednotlivé kusy, aby v tom nebyl zmatek
    conn = psycopg2.connect(
        host="aws-0-eu-central-1.pooler.supabase.com",
        port="6543",
        database="postgres",
        user="postgres.rrwefiglecnruxwkzjqc",
        password="databazesupabase",
        sslmode="require",
        options="-c project=rrwefiglecnruxwkzjqc",
        cursor_factory=RealDictCursor
    )
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Tabulky pro PostgreSQL
    cur.execute('''CREATE TABLE IF NOT EXISTS uzivatele 
                    (id SERIAL PRIMARY KEY, jmeno TEXT UNIQUE, heslo TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS veci 
                    (id SERIAL PRIMARY KEY, nazev TEXT, domov TEXT, poloha TEXT, 
                     drzitel TEXT, datum_posledni TEXT, poznamka TEXT, vydal TEXT, foto TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS historie 
                    (id SERIAL PRIMARY KEY, vec_id INTEGER, akce TEXT, osoba TEXT, 
                     vydal TEXT, poznamka TEXT, cas TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Výchozí admin
    hashed_heslo = generate_password_hash('sklad2026')
    cur.execute('''INSERT INTO uzivatele (jmeno, heslo) 
                   SELECT %s, %s WHERE NOT EXISTS (SELECT 1 FROM uzivatele WHERE jmeno = %s)''', 
                ('admin', hashed_heslo, 'admin'))
    conn.commit()
    cur.close()
    conn.close()

init_db()

# --- ZABEZPEČENÍ ---
def vyzaduje_prihlaseni(f):
    def wrap(*args, **kwargs):
        if 'uzivatel' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

# --- CESTY ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        jmeno = request.form['jmeno']
        heslo = request.form['heslo']
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM uzivatele WHERE jmeno = %s', (jmeno,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user and check_password_hash(user['heslo'], heslo):
            session['uzivatel'] = user['jmeno']
            return redirect(url_for('index'))
        return "Špatné jméno nebo heslo!"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('uzivatel', None)
    return redirect(url_for('login'))

@app.route('/')
@vyzaduje_prihlaseni
def index():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM veci ORDER BY id DESC')
    veci = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('index.html', veci=veci, prihlasen=session['uzivatel'])

@app.route('/uzivatele', methods=['GET', 'POST'])
@vyzaduje_prihlaseni
def uzivatele():
    conn = get_db_connection()
    cur = conn.cursor()
    if request.method == 'POST':
        nove_jmeno = request.form['jmeno']
        nove_heslo = generate_password_hash(request.form['heslo'])
        try:
            cur.execute('INSERT INTO uzivatele (jmeno, heslo) VALUES (%s, %s)', (nove_jmeno, nove_heslo))
            conn.commit()
        except:
            conn.rollback()
            return "Uživatel již existuje!"
    cur.execute('SELECT jmeno FROM uzivatele')
    seznam = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('uzivatele.html', uzivatele=seznam)

@app.route('/pridat', methods=('POST',))
@vyzaduje_prihlaseni
def pridat():
    nazev = request.form['nazev']
    domov = request.form['domov']
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO veci (nazev, domov, poloha, drzitel) VALUES (%s, %s, %s, %s)',
                 (nazev, domov, domov, 'Ve skladu'))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/')

@app.route('/akce/<int:id>', methods=('POST',))
@vyzaduje_prihlaseni
def akce(id):
    drzitel = request.form.get('drzitel')
    poznamka = request.form.get('poznamka')
    vydal = session['uzivatel']
    nyni = datetime.now().strftime("%d.%m.%Y %H:%M")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT nazev FROM veci WHERE id = %s', (id,))
    vec = cur.fetchone()
    if vec:
        cur.execute('''UPDATE veci SET drzitel = %s, poloha = %s, 
                        datum_posledni = %s, poznamka = %s, vydal = %s WHERE id = %s''',
                     (drzitel, 'U pracovníka', nyni, poznamka, vydal, id))
        cur.execute('''INSERT INTO historie (vec_id, akce, osoba, vydal, poznamka) 
                        VALUES (%s, %s, %s, %s, %s)''',
                     (id, f"Půjčeno: {vec['nazev']}", drzitel, vydal, poznamka))
        conn.commit()
    cur.close()
    conn.close()
    return redirect('/')

@app.route('/vratit/<int:id>')
@vyzaduje_prihlaseni
def vratit(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT nazev, drzitel FROM veci WHERE id = %s', (id,))
    vec = cur.fetchone()
    if vec:
        nyni = datetime.now().strftime("%d.%m.%Y %H:%M")
        cur.execute('''INSERT INTO historie (vec_id, akce, osoba, poznamka, vydal) 
                        VALUES (%s, %s, %s, %s, %s)''',
                     (id, f"Vráceno: {vec['nazev']}", f"od {vec['drzitel']}", "Zpět na sklad", session['uzivatel']))
        cur.execute('''UPDATE veci SET drzitel = 'Ve skladu', poloha = domov, 
                        vydal = '', datum_posledni = %s WHERE id = %s''', (nyni, id))
        conn.commit()
    cur.close()
    conn.close()
    return redirect('/')

@app.route('/historie')
@vyzaduje_prihlaseni
def zobraz_historii():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM historie ORDER BY id DESC LIMIT 100')
    zaznamy = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('historie.html', zaznamy=zaznamy)

@app.route('/nahrat_foto/<int:id>', methods=['POST'])
@vyzaduje_prihlaseni
def nahrat_foto(id):
    foto_data = request.form.get('foto')
    if foto_data:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('UPDATE veci SET foto = %s WHERE id = %s', (foto_data, id))
        conn.commit()
        cur.close()
        conn.close()
    return "OK", 200

@app.route('/tisk')
@vyzaduje_prihlaseni
def tisk():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM veci')
    veci = cur.fetchall()
    cur.close()
    conn.close()
    veci_s_qr = []
    for vec in veci:
        qr_data = f"https://sklad-l0i3.onrender.com/akce_mobil/{vec['id']}"
        qr = qrcode.make(qr_data)
        img_buffer = io.BytesIO()
        qr.save(img_buffer, format='PNG')
        img_str = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
        veci_s_qr.append({'nazev': vec['nazev'], 'id': vec['id'], 'domov': vec['domov'], 'qr': img_str})
    html_content = render_template('stitky.html', veci=veci_s_qr)
    pdf = HTML(string=html_content).write_pdf()
    return pdf, 200, {'Content-Type': 'application/pdf', 'Content-Disposition': 'inline; filename=stitky.pdf'}

if __name__ == '__main__':
    app.run(debug=True)








from flask import Flask, render_template, request, redirect, session, url_for
import psycopg2
from psycopg2.extras import RealDictCursor
import qrcode
import io
import base64
from weasyprint import HTML
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'sklad-2026-unikatni-klic')

# --- KONFIGURACE PŘIPOJENÍ ---
def get_db_connection():
    # ID projektu dáváme přímo do uživatele - to Supabase Pooler pochopí vždy
    return psycopg2.connect(
        host="aws-0-eu-central-1.pooler.supabase.com",
        port="6543",
        database="postgres",
        user="postgres.rrwefiglecnruxwkzjqc", # Formát: postgres.VASE_ID_PROJEKTU
        password="databazesupabase",
        sslmode="require",
        cursor_factory=RealDictCursor,
        connect_timeout=15
    )

def init_db():
    print("--- Inicializace DB ---")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Tabulky
        cur.execute('CREATE TABLE IF NOT EXISTS uzivatele (id SERIAL PRIMARY KEY, jmeno TEXT UNIQUE, heslo TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS veci (id SERIAL PRIMARY KEY, nazev TEXT, domov TEXT, poloha TEXT, drzitel TEXT, datum_posledni TEXT, poznamka TEXT, vydal TEXT, foto TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS historie (id SERIAL PRIMARY KEY, vec_id INTEGER, akce TEXT, osoba TEXT, vydal TEXT, poznamka TEXT, cas TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        
        # Kontrola admina
        cur.execute('SELECT 1 FROM uzivatele WHERE jmeno = %s', ('admin',))
        if not cur.fetchone():
            hashed_heslo = generate_password_hash('sklad2026')
            cur.execute('INSERT INTO uzivatele (jmeno, heslo) VALUES (%s, %s)', ('admin', hashed_heslo))
        
        conn.commit()
        cur.close()
    except Exception as e:
        print(f"Chyba při startu DB: {e}")
    finally:
        if conn: conn.close()

# Spuštění DB při startu
init_db()

# --- DEKORÁTOR ---
def login_required(f):
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
        jmeno = request.form.get('jmeno')
        heslo = request.form.get('heslo')
        
        # Záchranné přihlášení (funguje i bez DB)
        if jmeno == 'admin' and heslo == 'sklad2026':
            session['uzivatel'] = 'admin'
            return redirect(url_for('index'))

        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('SELECT * FROM uzivatele WHERE jmeno = %s', (jmeno,))
            user = cur.fetchone()
            if user and check_password_hash(user['heslo'], heslo):
                session['uzivatel'] = user['jmeno']
                return redirect(url_for('index'))
        except Exception as e:
            return f"Chyba při přihlašování: {e}"
        finally:
            if conn: conn.close()
        return "Neplatné údaje!"
    return render_template('login.html')

@app.route('/')
@login_required
def index():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM veci ORDER BY id DESC')
        veci = cur.fetchall()
        cur.close()
        conn.close()
        return render_template('index.html', veci=veci, prihlasen=session['uzivatel'])
    except Exception as e:
        # Pokud index spadne, uvidíš proč (často chyba v HTML šabloně)
        return f"Chyba při načítání skladu: {e}"

@app.route('/pridat', methods=['POST'])
@login_required
def pridat():
    nazev = request.form.get('nazev')
    domov = request.form.get('domov')
    if nazev:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('INSERT INTO veci (nazev, domov, poloha, drzitel) VALUES (%s, %s, %s, %s)', 
                   (nazev, domov, domov, 'Ve skladu'))
        conn.commit()
        conn.close()
    return redirect(url_for('index'))

@app.route('/akce/<int:id>', methods=['POST'])
@login_required
def akce(id):
    drzitel = request.form.get('drzitel')
    poznamka = request.form.get('poznamka', '')
    vydal = session['uzivatel']
    nyni = datetime.now().strftime("%d.%m.%Y %H:%M")
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT nazev FROM veci WHERE id = %s', (id,))
    vec = cur.fetchone()
    if vec:
        cur.execute('''UPDATE veci SET drzitel=%s, poloha='U pracovníka', 
                       datum_posledni=%s, poznamka=%s, vydal=%s WHERE id=%s''',
                    (drzitel, nyni, poznamka, vydal, id))
        cur.execute('''INSERT INTO historie (vec_id, akce, osoba, vydal, poznamka) 
                       VALUES (%s, %s, %s, %s, %s)''',
                    (id, f"Půjčeno: {vec['nazev']}", drzitel, vydal, poznamka))
        conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/vratit/<int:id>')
@login_required
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
        cur.execute("UPDATE veci SET drzitel='Ve skladu', poloha=domov, vydal='', datum_posledni=%s WHERE id=%s", (nyni, id))
        conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/historie')
@login_required
def zobraz_historii():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM historie ORDER BY id DESC LIMIT 100')
        zaznamy = cur.fetchall()
        conn.close()
        return render_template('historie.html', zaznamy=zaznamy)
    except Exception as e:
        return f"Chyba historie: {e}"

@app.route('/uzivatele', methods=['GET', 'POST'])
@login_required
def uzivatele():
    conn = get_db_connection()
    cur = conn.cursor()
    if request.method == 'POST':
        j = request.form.get('jmeno')
        h = generate_password_hash(request.form.get('heslo'))
        try:
            cur.execute('INSERT INTO uzivatele (jmeno, heslo) VALUES (%s, %s)', (j, h))
            conn.commit()
        except:
            conn.rollback()
    cur.execute('SELECT jmeno FROM uzivatele')
    seznam = cur.fetchall()
    conn.close()
    return render_template('uzivatele.html', uzivatele=seznam)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)


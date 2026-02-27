from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
import qrcode
import io
import base64
from weasyprint import HTML
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'tvoje_velmi_tajne_heslo_123' # Nutné pro přihlašování

def get_db_connection():
    # Přejdeme na sklad_v3, abychom měli čistý start s uživateli
    conn = sqlite3.connect('sklad_v3.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    # Tabulka uživatelů
    conn.execute('''CREATE TABLE IF NOT EXISTS uzivatele 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     jmeno TEXT UNIQUE, heslo TEXT)''')
    
    # Tabulka věcí (přidán sloupec foto)
    conn.execute('''CREATE TABLE IF NOT EXISTS veci 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     nazev TEXT, domov TEXT, poloha TEXT, drzitel TEXT,
                     datum_posledni TEXT, poznamka TEXT, vydal TEXT, foto TEXT)''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS historie 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     vec_id INTEGER, akce TEXT, osoba TEXT, 
                     vydal TEXT, poznamka TEXT,
                     cas TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    # Vytvoření prvního administrátora (pokud neexistuje)
    # Jméno: admin, Heslo: sklad2026
    hashed_heslo = generate_password_hash('sklad2026')
    try:
        conn.execute('INSERT INTO uzivatele (jmeno, heslo) VALUES (?, ?)', ('admin', hashed_heslo))
    except: pass
    
    conn.commit()
    conn.close()

init_db()

# --- ZABEZPEČENÍ (DEKORÁTOR) ---
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
        user = conn.execute('SELECT * FROM uzivatele WHERE jmeno = ?', (jmeno,)).fetchone()
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
    veci = conn.execute('SELECT * FROM veci').fetchall()
    conn.close()
    return render_template('index.html', veci=veci, prihlasen=session['uzivatel'])

@app.route('/akce/<int:id>', methods=('POST',))
@vyzaduje_prihlaseni
def akce(id):
    drzitel = request.form.get('drzitel')
    poznamka = request.form.get('poznamka')
    vydal = session['uzivatel'] # Skladník se vyplní automaticky z přihlášení!
    nyni = datetime.now().strftime("%d.%m.%Y %H:%M")
    
    conn = get_db_connection()
    vec = conn.execute('SELECT nazev FROM veci WHERE id = ?', (id,)).fetchone()
    
    if drzitel and drzitel.strip(): 
        conn.execute('''UPDATE veci SET drzitel = ?, poloha = ?, 
                        datum_posledni = ?, poznamka = ?, vydal = ? WHERE id = ?''',
                     (drzitel, 'U pracovníka', nyni, poznamka, vydal, id))
        conn.execute('''INSERT INTO historie (vec_id, akce, osoba, vydal, poznamka) 
                        VALUES (?, ?, ?, ?, ?)''',
                     (id, f"Půjčeno: {vec['nazev']}", drzitel, vydal, poznamka))
    
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/vratit/<int:id>')
@vyzaduje_prihlaseni
def vratit(id):
    conn = get_db_connection()
    vec = conn.execute('SELECT nazev, drzitel FROM veci WHERE id = ?', (id,)).fetchone()
    if vec:
        nyni = datetime.now().strftime("%d.%m.%Y %H:%M")
        conn.execute('''INSERT INTO historie (vec_id, akce, osoba, poznamka, vydal) 
                        VALUES (?, ?, ?, ?, ?)''',
                     (id, f"Vráceno: {vec['nazev']}", f"od {vec['drzitel']}", "Zpět na sklad", session['uzivatel']))
        conn.execute('''UPDATE veci SET drzitel = 'Ve skladu', poloha = domov, 
                        vydal = '', datum_posledni = ? WHERE id = ?''', (nyni, id))
    conn.commit()
    conn.close()
    return redirect('/')

# ... (ostatní trasy jako /historie, /tisk a /pridat také obal @vyzaduje_prihlaseni) ...
@app.route('/historie')
@vyzaduje_prihlaseni
def zobraz_historii():
    conn = get_db_connection()
    zaznamy = conn.execute('SELECT * FROM historie ORDER BY id DESC LIMIT 100').fetchall()
    conn.close()
    return render_template('historie.html', zaznamy=zaznamy)

@app.route('/pridat', methods=('POST',))
@vyzaduje_prihlaseni
def pridat():
    nazev = request.form['nazev']
    domov = request.form['domov']
    conn = get_db_connection()
    conn.execute('INSERT INTO veci (nazev, domov, poloha, drzitel) VALUES (?, ?, ?, ?)',
                 (nazev, domov, domov, 'Ve skladu'))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/tisk')
@vyzaduje_prihlaseni
def tisk():
    conn = get_db_connection()
    veci = conn.execute('SELECT * FROM veci').fetchall()
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

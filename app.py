from flask import Flask, render_template, request, redirect
import sqlite3
import qrcode
import io
import base64
from weasyprint import HTML
from datetime import datetime

app = Flask(__name__)

def get_db_connection():
    # Použijeme V2, aby si Render vytvořil tabulky znovu a správně
    conn = sqlite3.connect('sklad_v2.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    # Tabulka věcí
    conn.execute('''CREATE TABLE IF NOT EXISTS veci 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     nazev TEXT, domov TEXT, poloha TEXT, drzitel TEXT,
                     datum_posledni TEXT, poznamka TEXT, vydal TEXT)''')
    
    # Tabulka historie - teď už se všemi sloupci hned od začátku
    conn.execute('''CREATE TABLE IF NOT EXISTS historie 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     vec_id INTEGER, akce TEXT, osoba TEXT, 
                     vydal TEXT, poznamka TEXT,
                     cas TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.close()

init_db()

@app.route('/')
def index():
    conn = get_db_connection()
    veci = conn.execute('SELECT * FROM veci').fetchall()
    conn.close()
    return render_template('index.html', veci=veci)

@app.route('/pridat', methods=('POST',))
def pridat():
    nazev = request.form['nazev']
    domov = request.form['domov']
    conn = get_db_connection()
    conn.execute('INSERT INTO veci (nazev, domov, poloha, drzitel) VALUES (?, ?, ?, ?)',
                 (nazev, domov, domov, 'Ve skladu'))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/akce/<int:id>', methods=('POST',))
def akce(id):
    drzitel = request.form.get('drzitel')
    vydal = request.form.get('vydal')
    poznamka = request.form.get('poznamka')
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
def vratit(id):
    conn = get_db_connection()
    vec = conn.execute('SELECT nazev, drzitel FROM veci WHERE id = ?', (id,)).fetchone()
    if vec:
        nyni = datetime.now().strftime("%d.%m.%Y %H:%M")
        conn.execute('''INSERT INTO historie (vec_id, akce, osoba, poznamka) 
                        VALUES (?, ?, ?, ?)''',
                     (id, f"Vráceno: {vec['nazev']}", f"od {vec['drzitel']}", "Zpět na sklad"))
        conn.execute('''UPDATE veci SET drzitel = 'Ve skladu', poloha = domov, 
                        vydal = '', datum_posledni = ? WHERE id = ?''', (nyni, id))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/historie')
def zobraz_historii():
    try:
        conn = get_db_connection()
        # Přidali jsme id, aby řazení bylo 100% spolehlivé
        zaznamy = conn.execute('SELECT * FROM historie ORDER BY id DESC LIMIT 100').fetchall()
        conn.close()
        return render_template('historie.html', zaznamy=zaznamy)
    except Exception as e:
        return f"Chyba v historii: {e}" # Tohle nám vypíše chybu přímo na web, pokud by to padlo

@app.route('/tisk')
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
    return pdf, 200, {'Content-Type': 'application/pdf', 'Content-Disposition': 'inline-filename=stitky.pdf'}

if __name__ == '__main__':
    app.run(debug=True)

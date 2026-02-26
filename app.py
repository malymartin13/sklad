from flask import Flask, render_template, request, redirect
import sqlite3
import qrcode
import io
import base64
from weasyprint import HTML

app = Flask(__name__)

# --- 1. DATABÁZOVÉ FUNKCE ---

def get_db_connection():
    # Na Renderu se soubor vytvoří v aktuální složce
    conn = sqlite3.connect('sklad.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS veci 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     nazev TEXT, domov TEXT, poloha TEXT, drzitel TEXT)''')
    conn.close()

# Spustíme inicializaci databáze hned při startu aplikace
# Teď už je to pod definicí funkce, takže to nevyhodí chybu
init_db()

# --- 2. WEBOVÉ CESTY (ROUTES) ---

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
    conn = get_db_connection()
    if drzitel and drzitel.strip(): 
        conn.execute('UPDATE veci SET drzitel = ?, poloha = ? WHERE id = ?',
                     (drzitel, 'U pracovníka', id))
    else:
        conn.execute('UPDATE veci SET drzitel = ?, poloha = domov WHERE id = ?',
                     ('Ve skladu', id))
    conn.commit()
    conn.close()
    return redirect('/')

# Speciální cesta pro mobilní telefon po naskenování QR kódu
@app.route('/akce_mobil/<int:id>')
def akce_mobil(id):
    # Pro jednoduchost to zatím jen přesměruje na hlavní stránku, 
    # ale v budoucnu sem můžeme dát speciální formulář pro skladníka
    return redirect('/')

@app.route('/tisk')
def tisk():
    conn = get_db_connection()
    veci = conn.execute('SELECT * FROM veci').fetchall()
    conn.close()

    veci_s_qr = []
    for vec in veci:
        # TVOJE ADRESA NA RENDREU:
        # Tady vložíme odkaz, který mobil po naskenování otevře
        qr_data = f"https://sklad-l0i3.onrender.com/akce_mobil/{vec['id']}"
        
        qr = qrcode.make(qr_data)
        img_buffer = io.BytesIO()
        qr.save(img_buffer, format='PNG')
        img_str = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
        
        veci_s_qr.append({
            'nazev': vec['nazev'],
            'id': vec['id'],
            'domov': vec['domov'],
            'qr': img_str
        })

    html_content = render_template('stitky.html', veci=veci_s_qr)
    pdf = HTML(string=html_content).write_pdf()
    
    return pdf, 200, {
        'Content-Type': 'application/pdf',
        'Content-Disposition': 'inline; filename=stitky.pdf'
    }

if __name__ == '__main__':
    app.run(debug=True)

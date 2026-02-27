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
app.secret_key = os.environ.get('SECRET_KEY', 'sklad-tajne-heslo-2026')

# --- KONFIGURACE PŘIPOJENÍ ---
def get_db_connection():
    # Používáme oddělené parametry pro maximální stabilitu na Renderu
    return psycopg2.connect(
        host="aws-0-eu-central-1.pooler.supabase.com",
        port="6543",
        database="postgres",
        user="postgres.rrwefiglecnruxwkzjqc",
        password="databazesupabase",
        sslmode="require",
        options="-c project=rrwefiglecnruxwkzjqc",
        cursor_factory=RealDictCursor,
        connect_timeout=10
    )

def init_db():
    print("--- Inicializace databáze v Supabase ---")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Tabulky (PostgreSQL syntaxe)
        cur.execute('''CREATE TABLE IF NOT EXISTS uzivatele 
                        (id SERIAL PRIMARY KEY, jmeno TEXT UNIQUE, heslo TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS veci 
                        (id SERIAL PRIMARY KEY, nazev TEXT, domov TEXT, poloha TEXT, 
                         drzitel TEXT, datum_posledni TEXT, poznamka TEXT, vydal TEXT, foto TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS historie 
                        (id SERIAL PRIMARY KEY, vec_id INTEGER, akce TEXT, osoba TEXT, 
                         vydal TEXT, poznamka TEXT, cas TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Vytvoření admina pokud neexistuje
        hashed_heslo = generate_password_hash('sklad2026')
        cur.execute('''INSERT INTO uzivatele (jmeno, heslo) 
                       SELECT %s, %s WHERE NOT EXISTS (SELECT 1 FROM uzivatele WHERE jmeno = %s)''', 
                    ('admin', hashed_heslo, 'admin'))
        
        conn.commit()
        cur.close()
        print("--- Databáze je připravena ---")
    except Exception as e:
        print(f"!!! CHYBA INICIALIZACE: {e}")
    finally:
        if conn:
            conn.close()

# Spustit inicializaci při startu
init_db()

# --- ZABEZPEČENÍ ---
def vyzaduje_prihlaseni(f):
    def wrap(*args, **kwargs):
        if 'uzivatel' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

# --- CEST

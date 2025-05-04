from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import bcrypt
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'

def init_db():
    print("Mencipta database...")
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kod_produk TEXT NOT NULL UNIQUE,
        nama_produk TEXT NOT NULL,
        harga_jual REAL NOT NULL,
        harga_beli REAL NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarikh TEXT NOT NULL,
        kod_transaksi TEXT NOT NULL UNIQUE,
        nama_produk TEXT NOT NULL,
        jenis_transaksi TEXT NOT NULL,
        harga REAL NOT NULL,
        kuantiti REAL NOT NULL,
        jumlah REAL NOT NULL
    )''')
    conn.commit()
    conn.close()

def add_admin_user():
    print("Menambah pengguna admin...")
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    password = 'admin123'.encode('utf-8')
    hashed = bcrypt.hashpw(password, bcrypt.gensalt())
    c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)",
              ('admin', hashed.decode('utf-8'), 'admin'))
    conn.commit()
    conn.close()

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password'].encode('utf-8')
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()
        if user and bcrypt.checkpw(password, user[2].encode('utf-8')):
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[3]
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Nama pengguna atau kata laluan salah", current_year=datetime.now().year)
    return render_template('login.html', current_year=datetime.now().year)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Total number of products
    c.execute("SELECT COUNT(*) AS total_products FROM products")
    total_products = c.fetchone()['total_products']

    # Total sales amount (sum of 'Jual' transactions)
    c.execute("SELECT IFNULL(SUM(jumlah), 0) AS total_sales FROM transactions WHERE jenis_transaksi = 'Jual'")
    total_sales = c.fetchone()['total_sales']

    # Overall profit/loss (sum of 'Jual' amounts minus sum of 'Beli' amounts)
    c.execute("""
        SELECT 
            IFNULL(SUM(CASE WHEN jenis_transaksi = 'Jual' THEN jumlah ELSE 0 END), 0) -
            IFNULL(SUM(CASE WHEN jenis_transaksi = 'Beli' THEN jumlah ELSE 0 END), 0) AS overall_profit_loss
        FROM transactions
    """)
    overall_profit_loss = c.fetchone()['overall_profit_loss']

    # Profit/loss for the current month
    c.execute("""
        SELECT 
            IFNULL(SUM(CASE WHEN jenis_transaksi = 'Jual' THEN jumlah ELSE 0 END), 0) -
            IFNULL(SUM(CASE WHEN jenis_transaksi = 'Beli' THEN jumlah ELSE 0 END), 0) AS current_month_profit_loss
        FROM transactions
        WHERE strftime('%Y-%m', tarikh) = strftime('%Y-%m', 'now')
    """)
    current_month_profit_loss = c.fetchone()['current_month_profit_loss']

    # 5 most recent transactions
    c.execute("""
        SELECT * FROM transactions ORDER BY tarikh DESC, id DESC LIMIT 5
    """)
    recent_transactions = c.fetchall()

    # Calculate stock for each product
    c.execute("SELECT * FROM products")
    products = c.fetchall()

    low_stock_products = []
    for product in products:
        kod_produk = product['kod_produk']
        nama_produk = product['nama_produk']

        # Check if product has at least one 'Beli' transaction
        c.execute("SELECT COUNT(*) FROM transactions WHERE nama_produk = ? AND jenis_transaksi = 'Beli'", (nama_produk,))
        beli_count = c.fetchone()[0]

        if beli_count > 0:
            # Calculate stock for this product
            c.execute("""
                SELECT 
                    IFNULL(SUM(CASE WHEN jenis_transaksi = 'Beli' THEN kuantiti ELSE 0 END), 0) -
                    IFNULL(SUM(CASE WHEN jenis_transaksi = 'Jual' THEN kuantiti ELSE 0 END), 0) AS stok
                FROM transactions
                WHERE nama_produk = ?
            """, (nama_produk,))
            stok = c.fetchone()['stok']
            # Determine low stock threshold based on kod_produk prefix
            if kod_produk.startswith('IU') or kod_produk.startswith('SP'):
                threshold = 3000
            elif kod_produk.startswith('IM'):
                threshold = 20
            else:
                threshold = None
            if threshold is not None and stok > 0:
                low_stock_products.append({
                    'nama_produk': nama_produk,
                    'stok': stok,
                    'threshold': threshold
                })

    conn.close()

    return render_template('dashboard.html',
                           username=session.get('username'),
                           total_products=total_products,
                           total_sales=total_sales,
                           overall_profit_loss=overall_profit_loss,
                           current_month_profit_loss=current_month_profit_loss,
                           recent_transactions=recent_transactions,
                           low_stock_products=low_stock_products)

@app.route('/products')
def products():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM products")
    total = c.fetchone()[0]
    c.execute("SELECT * FROM products ORDER BY kod_produk ASC LIMIT ? OFFSET ?", (per_page, offset))
    products = c.fetchall()
    conn.close()
    next_page = page + 1 if offset + per_page < total else None
    return render_template('products.html', username=session.get('username'), products=products, next_page=next_page, page=page)

@app.route('/products/add', methods=['POST'])
def add_product():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    kod_produk = request.form['kod_produk']
    nama_produk = request.form['nama_produk']
    harga_jual = request.form['harga_jual']
    harga_beli = request.form['harga_beli']
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE kod_produk = ?", (kod_produk,))
    existing = c.fetchone()
    if existing:
        conn.close()
        flash('Kod Produk sudah wujud. Sila gunakan kod lain.', 'error')
        return redirect(url_for('products'))
    c.execute("INSERT INTO products (kod_produk, nama_produk, harga_jual, harga_beli) VALUES (?, ?, ?, ?)",
              (kod_produk, nama_produk, harga_jual, harga_beli))
    conn.commit()
    conn.close()
    flash('Produk berjaya ditambah.', 'success')
    return redirect(url_for('products'))

@app.route('/products/edit/<int:id>', methods=['GET', 'POST'])
def edit_product(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if request.method == 'POST':
        kod_produk = request.form['kod_produk']
        nama_produk = request.form['nama_produk']
        harga_jual = request.form['harga_jual']
        harga_beli = request.form['harga_beli']
        c.execute("UPDATE products SET kod_produk = ?, nama_produk = ?, harga_jual = ?, harga_beli = ? WHERE id = ?",
                  (kod_produk, nama_produk, harga_jual, harga_beli, id))
        conn.commit()
        conn.close()
        return redirect(url_for('products'))
    else:
        c.execute("SELECT * FROM products WHERE id = ?", (id,))
        product = c.fetchone()
        conn.close()
        if product is None:
            return redirect(url_for('products'))
        return render_template('edit_product.html', product=product, username=session.get('username'))

@app.route('/products/delete/<int:id>', methods=['POST'])
def delete_product(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('products'))

@app.route('/transactions')
def transactions():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    # Get filter/search parameters
    search = request.args.get('search', '', type=str)
    filter_jenis = request.args.get('filter_jenis', '', type=str)
    filter_produk = request.args.get('filter_produk', '', type=str)
    filter_tarikh_start = request.args.get('filter_tarikh_start', '', type=str)
    filter_tarikh_end = request.args.get('filter_tarikh_end', '', type=str)
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Build query with filters
    query = "SELECT COUNT(*) FROM transactions WHERE 1=1"
    params = []

    if search:
        query += " AND (kod_transaksi LIKE ? OR nama_produk LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])
    if filter_jenis:
        query += " AND jenis_transaksi = ?"
        params.append(filter_jenis)
    if filter_produk:
        query += " AND nama_produk = ?"
        params.append(filter_produk)
    if filter_tarikh_start:
        query += " AND tarikh >= ?"
        params.append(filter_tarikh_start)
    if filter_tarikh_end:
        query += " AND tarikh <= ?"
        params.append(filter_tarikh_end)

    c.execute(query, params)
    total = c.fetchone()[0]

    query = query.replace("COUNT(*)", "*") + " ORDER BY tarikh DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    c.execute(query, params)
    transactions = c.fetchall()

    c.execute("SELECT * FROM products ORDER BY kod_produk ASC")
    products = c.fetchall()
    conn.close()

    next_page = page + 1 if offset + per_page < total else None

    return render_template('transactions.html', username=session.get('username'), transactions=transactions, products=products, next_page=next_page, page=page, search=search, filter_jenis=filter_jenis, filter_produk=filter_produk, filter_tarikh_start=filter_tarikh_start, filter_tarikh_end=filter_tarikh_end)

@app.route('/transactions/export')
def export_transactions():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    import csv
    from io import StringIO
    # Get filter/search parameters same as transactions route
    search = request.args.get('search', '', type=str)
    filter_jenis = request.args.get('filter_jenis', '', type=str)
    filter_produk = request.args.get('filter_produk', '', type=str)
    filter_tarikh_start = request.args.get('filter_tarikh_start', '', type=str)
    filter_tarikh_end = request.args.get('filter_tarikh_end', '', type=str)

    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    query = "SELECT * FROM transactions WHERE 1=1"
    params = []

    if search:
        query += " AND (kod_transaksi LIKE ? OR nama_produk LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])
    if filter_jenis:
        query += " AND jenis_transaksi = ?"
        params.append(filter_jenis)
    if filter_produk:
        query += " AND nama_produk = ?"
        params.append(filter_produk)
    if filter_tarikh_start:
        query += " AND tarikh >= ?"
        params.append(filter_tarikh_start)
    if filter_tarikh_end:
        query += " AND tarikh <= ?"
        params.append(filter_tarikh_end)

    query += " ORDER BY tarikh DESC"
    c.execute(query, params)
    transactions = c.fetchall()
    conn.close()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Tarikh', 'Kod Transaksi', 'Nama Produk', 'Jenis Transaksi', 'Harga (RM)', 'Kuantiti (KG)', 'Jumlah (RM)'])
    for t in transactions:
        cw.writerow([t['tarikh'], t['kod_transaksi'], t['nama_produk'], t['jenis_transaksi'], f"{t['harga']:.2f}", f"{t['kuantiti']:.2f}", f"{t['jumlah']:.2f}"])

    output = si.getvalue()
    from flask import Response
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=transactions_export.csv"}
    )

@app.route('/transactions/add', methods=['POST'])
def add_transaction():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    tarikh = request.form['tarikh']
    kod_transaksi = request.form['kod_transaksi']
    nama_produk = request.form['nama_produk']
    jenis_transaksi = request.form['jenis_transaksi']
    harga = float(request.form['harga'])
    kuantiti = float(request.form['kuantiti'])
    discount_amount = float(request.form.get('discount_amount', 0))
    # Adjust harga by subtracting discount amount if applicable
    if discount_amount < 0:
        discount_amount = 0
    if discount_amount > harga:
        discount_amount = harga
    adjusted_harga = harga - discount_amount
    jumlah = adjusted_harga * kuantiti

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM transactions WHERE kod_transaksi = ?", (kod_transaksi,))
    existing = c.fetchone()
    if existing:
        conn.close()
        flash('Kod Transaksi sudah wujud. Sila gunakan kod lain.', 'error')
        return redirect(url_for('transactions'))
    if jenis_transaksi == 'Jual':
        # Calculate current stock for the product
        c.execute("""
            SELECT 
                IFNULL(SUM(CASE WHEN jenis_transaksi = 'Beli' THEN kuantiti ELSE 0 END), 0) -
                IFNULL(SUM(CASE WHEN jenis_transaksi = 'Jual' THEN kuantiti ELSE 0 END), 0) AS stok
            FROM transactions
            WHERE nama_produk = ?
        """, (nama_produk,))
        stok = c.fetchone()[0]
        if stok < kuantiti:
            conn.close()
            flash(f'Stok tidak mencukupi untuk produk {nama_produk}. Stok semasa: {stok}', 'error')
            return redirect(url_for('transactions'))
    c.execute("INSERT INTO transactions (tarikh, kod_transaksi, nama_produk, jenis_transaksi, harga, kuantiti, jumlah) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (tarikh, kod_transaksi, nama_produk, jenis_transaksi, adjusted_harga, kuantiti, jumlah))
    conn.commit()
    conn.close()
    flash('Transaksi berjaya ditambah.', 'success')
    return redirect(url_for('transactions'))

@app.route('/transactions/edit/<int:id>', methods=['GET', 'POST'])
def edit_transaction(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    if request.method == 'POST':
        tarikh = request.form['tarikh']
        kod_transaksi = request.form['kod_transaksi']
        nama_produk = request.form['nama_produk']
        jenis_transaksi = request.form['jenis_transaksi']
        harga = request.form['harga']
        kuantiti = float(request.form['kuantiti'])
        jumlah = request.form['jumlah']

        # Check if kod_transaksi is unique except current
        c.execute("SELECT * FROM transactions WHERE kod_transaksi = ? AND id != ?", (kod_transaksi, id))
        existing = c.fetchone()
        if existing:
            conn.close()
            flash('Kod Transaksi sudah wujud. Sila gunakan kod lain.', 'error')
            return redirect(url_for('transactions'))

        if jenis_transaksi == 'Jual':
            # Calculate current stock excluding this transaction
            c.execute("""
                SELECT 
                    IFNULL(SUM(CASE WHEN jenis_transaksi = 'Beli' THEN kuantiti ELSE 0 END), 0) -
                    IFNULL(SUM(CASE WHEN jenis_transaksi = 'Jual' THEN kuantiti ELSE 0 END), 0) AS stok
                FROM transactions
                WHERE nama_produk = ? AND id != ?
            """, (nama_produk, id))
            stok = c.fetchone()[0]
            if stok < kuantiti:
                conn.close()
                flash(f'Stok tidak mencukupi untuk produk {nama_produk}. Stok semasa: {stok}', 'error')
                return redirect(url_for('transactions'))

        c.execute("""
            UPDATE transactions SET tarikh = ?, kod_transaksi = ?, nama_produk = ?, jenis_transaksi = ?, harga = ?, kuantiti = ?, jumlah = ?
            WHERE id = ?
        """, (tarikh, kod_transaksi, nama_produk, jenis_transaksi, harga, kuantiti, jumlah, id))
        conn.commit()
        conn.close()
        flash('Transaksi berjaya dikemaskini.', 'success')
        return redirect(url_for('transactions'))
    else:
        c.execute("SELECT * FROM transactions WHERE id = ?", (id,))
        transaction = c.fetchone()
        conn.close()
        if transaction is None:
            flash('Transaksi tidak dijumpai.', 'error')
            return redirect(url_for('transactions'))
        return render_template('edit_transaction.html', transaction=transaction, username=session.get('username'))

@app.route('/transactions/delete/<int:id>', methods=['POST'])
def delete_transaction(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("DELETE FROM transactions WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash('Transaksi berjaya dipadam.', 'success')
    return redirect(url_for('transactions'))

@app.route('/customers')
def customers():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('customers.html', username=session.get('username'))

@app.route('/reports')
def reports():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Get filter/search parameters
    search = request.args.get('search', '', type=str)
    filter_date_start = request.args.get('filter_date_start', '', type=str)
    filter_date_end = request.args.get('filter_date_end', '', type=str)

    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Build query with filters for aggregation
    query = """
    SELECT 
        strftime('%Y-%m', tarikh) AS bulan,
        SUM(CASE WHEN jenis_transaksi = 'Beli' THEN kuantiti ELSE 0 END) AS kuantiti_belian_kg,
        SUM(CASE WHEN jenis_transaksi = 'Jual' THEN kuantiti ELSE 0 END) AS kuantiti_jualan_kg,
        SUM(CASE WHEN jenis_transaksi = 'Beli' THEN jumlah ELSE 0 END) AS kuantiti_belian_rm,
        SUM(CASE WHEN jenis_transaksi = 'Jual' THEN jumlah ELSE 0 END) AS kuantiti_jualan_rm,
        SUM(CASE WHEN jenis_transaksi = 'Jual' THEN jumlah ELSE 0 END) - 
        SUM(CASE WHEN jenis_transaksi = 'Beli' THEN jumlah ELSE 0 END) AS untung_rugi_rm
    FROM transactions
    WHERE 1=1
    """
    params = []

    if search:
        query += " AND (kod_transaksi LIKE ? OR nama_produk LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])
    if filter_date_start:
        query += " AND tarikh >= ?"
        params.append(filter_date_start)
    if filter_date_end:
        query += " AND tarikh <= ?"
        params.append(filter_date_end)

    query += " GROUP BY bulan ORDER BY bulan DESC"
    c.execute(query, params)
    report_items = c.fetchall()
    conn.close()

    return render_template('reports.html', username=session.get('username'), report_items=report_items, search=search, filter_date_start=filter_date_start, filter_date_end=filter_date_end)

@app.route('/reports/export')
def export_reports():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    import csv
    from io import StringIO
    # Get filter/search parameters same as reports route
    search = request.args.get('search', '', type=str)
    filter_date_start = request.args.get('filter_date_start', '', type=str)
    filter_date_end = request.args.get('filter_date_end', '', type=str)

    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    query = "SELECT * FROM transactions WHERE 1=1"
    params = []

    if search:
        query += " AND (kod_transaksi LIKE ? OR nama_produk LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])
    if filter_date_start:
        query += " AND tarikh >= ?"
        params.append(filter_date_start)
    if filter_date_end:
        query += " AND tarikh <= ?"
        params.append(filter_date_end)

    query += " ORDER BY tarikh DESC"
    c.execute(query, params)
    report_items = c.fetchall()
    conn.close()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Tarikh', 'Kod Transaksi', 'Nama Produk', 'Jenis Transaksi', 'Harga (RM)', 'Kuantiti (KG)', 'Jumlah (RM)'])
    for item in report_items:
        cw.writerow([item['tarikh'], item['kod_transaksi'], item['nama_produk'], item['jenis_transaksi'], f"{item['harga']:.2f}", f"{item['kuantiti']:.2f}", f"{item['jumlah']:.2f}"])

    from flask import Response
    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=reports_export.csv"}
    )

from functools import wraps
from flask import abort

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/users')
@admin_required
def admin_users():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT username, role FROM users ORDER BY username ASC")
    users = c.fetchall()
    conn.close()
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/add', methods=['POST'])
@admin_required
def add_user():
    username = request.form['username']
    password = request.form['password']
    role = request.form['role']
    if not username or not password or not role:
        flash('Sila isi semua medan.', 'error')
        return redirect(url_for('admin_users'))
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    existing = c.fetchone()
    if existing:
        conn.close()
        flash('Nama pengguna sudah wujud. Sila gunakan nama lain.', 'error')
        return redirect(url_for('admin_users'))
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
              (username, hashed.decode('utf-8'), role))
    conn.commit()
    conn.close()
    flash('Pengguna berjaya ditambah.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/edit/<string:username>', methods=['GET', 'POST'])
@admin_required
def edit_user(username):
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT username, role FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    if not user:
        conn.close()
        flash('Pengguna tidak dijumpai.', 'error')
        return redirect(url_for('admin_users'))
    if request.method == 'POST':
        new_username = request.form['username']
        password = request.form.get('password', '')
        role = request.form['role']
        if not new_username or not role:
            flash('Sila isi semua medan kecuali kata laluan jika tidak mahu tukar.', 'error')
            return redirect(url_for('edit_user', username=username))
        # Check if new username already exists and is different from current
        if new_username != username:
            c.execute("SELECT * FROM users WHERE username = ?", (new_username,))
            if c.fetchone():
                flash('Nama pengguna sudah wujud. Sila gunakan nama lain.', 'error')
                return redirect(url_for('edit_user', username=username))
        if password:
            hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            c.execute("UPDATE users SET username = ?, password = ?, role = ? WHERE username = ?",
                      (new_username, hashed.decode('utf-8'), role, username))
        else:
            c.execute("UPDATE users SET username = ?, role = ? WHERE username = ?",
                      (new_username, role, username))
        conn.commit()
        conn.close()
        flash('Pengguna berjaya dikemaskini.', 'success')
        return redirect(url_for('admin_users'))
    conn.close()
    return render_template('edit_user.html', user=user)

@app.route('/admin/users/delete/<string:username>', methods=['POST'])
@admin_required
def delete_user(username):
    if username == 'admin':
        flash('Pengguna admin tidak boleh dipadam.', 'error')
        return redirect(url_for('admin_users'))
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    flash('Pengguna berjaya dipadam.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    add_admin_user()
    print("Pelayan Flask akan bermula...")
    app.run(debug=True)
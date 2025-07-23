from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
import os, json, hashlib
from datetime import datetime
from werkzeug.utils import secure_filename
import barcode
from barcode.writer import ImageWriter
from functools import wraps

app = Flask(__name__)
app.secret_key = 'supersecretkey'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/uploads/product_images')
BARCODE_FOLDER = os.path.join(BASE_DIR, 'static/uploads/barcodes')
DB_FOLDER = os.path.join(BASE_DIR, 'database')

DB_PRODUCTS = os.path.join(DB_FOLDER, 'products.json')
DB_USERS = os.path.join(DB_FOLDER, 'users.json')
DB_SALES = os.path.join(DB_FOLDER, 'sales.json')
DB_PURCHASES = os.path.join(DB_FOLDER, 'purchases.json')

for folder in [UPLOAD_FOLDER, BARCODE_FOLDER, DB_FOLDER]:
    os.makedirs(folder, exist_ok=True)

for file in [DB_PRODUCTS, DB_USERS, DB_SALES, DB_PURCHASES]:
    if not os.path.exists(file):
        with open(file, 'w') as f:
            json.dump([], f)

def load_db(path):
    with open(path) as f:
        return json.load(f)

def save_db(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)

def create_and_save_barcode(barcode_val, product_id):
    font_path = os.path.join(BASE_DIR, "static", "fonts", "DejaVuSans.ttf")  # or any ttf file path you provide
    options = {
        "font_path": font_path,
        "text_distance": 1,  # optional, adjusts text position
        "font_size": 14,     # optional font size
    }
    Code128 = barcode.get_barcode_class('code128')
    code128 = Code128(barcode_val, writer=ImageWriter())
    filepath = os.path.join(BARCODE_FOLDER, f"{product_id}.png")
    code128.save(filepath.replace('.png', ''), options)

@app.context_processor
def inject_user():
    return dict(user=session.get('user'))

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            flash("Please login first.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        users = load_db(DB_USERS)
        username = request.form.get('username')
        password = request.form.get('password')
        user = next((u for u in users if u['username'] == username and u['password'] == password), None)
        if user:
            session['user'] = user
            flash("Logged in successfully.", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username or password.", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    search = request.args.get('search', '').lower()
    category_filter = request.args.get('category', '').lower()

    products = load_db(DB_PRODUCTS)

    filtered = []
    for p in products:
        if (search in p['name'].lower() or search in p['id'].lower()) and \
           (category_filter in p['category'].lower() or not category_filter):
            filtered.append(p)

    return render_template('dashboard.html', products=filtered)

@app.route('/add-product', methods=['GET', 'POST'])
@login_required
def add_product():
    if session['user']['role'] != 'admin':
        flash("Admin access only.", "danger")
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        products = load_db(DB_PRODUCTS)
        name = request.form.get('name').strip()
        category = request.form.get('category').strip()
        purchase_price = request.form.get('purchase_price')
        sell_price = request.form.get('sell_price')
        quantity = request.form.get('quantity')
        buy_link = request.form.get('buy_link', '').strip()

        unique_str = f"{name.lower()}_{category.lower()}_{purchase_price}_{sell_price}"
        serial_number = hashlib.sha256(unique_str.encode()).hexdigest()[:8].upper()

        if any(p['id'] == serial_number for p in products):
            flash("Product already exists.", "danger")
            return render_template('add_product.html', data=request.form)

        image_file = request.files.get('image')
        if not image_file or image_file.filename == '':
            flash("Product image is required.", "danger")
            return render_template('add_product.html', data=request.form)

        filename = secure_filename(image_file.filename)
        image_file.save(os.path.join(UPLOAD_FOLDER, filename))

        barcode_val = f"PROD{serial_number}"
        create_and_save_barcode(barcode_val, serial_number)

        new_product = {
            "id": serial_number,
            "name": name,
            "category": category,
            "purchase_price": float(purchase_price),
            "sell_price": float(sell_price),
            "quantity": int(quantity),
            "barcode": barcode_val,
            "image": filename,
            "buy_link": buy_link
        }
        products.append(new_product)
        save_db(DB_PRODUCTS, products)
        flash("Product added successfully.", "success")
        return redirect(url_for('dashboard'))

    return render_template('add_product.html')

@app.route('/edit/<string:id>', methods=['GET', 'POST'])
@login_required
def edit_product(id):
    if session['user']['role'] != 'admin':
        flash("Admin access only.", "danger")
        return redirect(url_for('dashboard'))

    products = load_db(DB_PRODUCTS)
    product = next((p for p in products if p['id'] == id), None)
    if not product:
        flash("Product not found.", "warning")
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        product['name'] = request.form.get('name').strip()
        product['category'] = request.form.get('category').strip()
        product['purchase_price'] = float(request.form.get('purchase_price'))
        product['sell_price'] = float(request.form.get('sell_price'))
        product['quantity'] = int(request.form.get('quantity'))
        product['barcode'] = request.form.get('barcode').strip()
        product['buy_link'] = request.form.get('buy_link', '').strip()

        create_and_save_barcode(product['barcode'], product['id'])

        image_file = request.files.get('image')
        if image_file and image_file.filename != '':
            filename = secure_filename(image_file.filename)
            image_file.save(os.path.join(UPLOAD_FOLDER, filename))
            product['image'] = filename

        save_db(DB_PRODUCTS, products)
        flash("Product updated.", "success")
        return redirect(url_for('dashboard'))

    return render_template('edit_product.html', product=product)

@app.route('/delete/<string:id>')
@login_required
def delete_product(id):
    if session['user']['role'] != 'admin':
        flash("Admin access only.", "danger")
        return redirect(url_for('dashboard'))

    products = load_db(DB_PRODUCTS)
    products = [p for p in products if p['id'] != id]
    save_db(DB_PRODUCTS, products)
    flash("Product deleted.", "info")
    return redirect(url_for('dashboard'))

@app.route('/sell/<string:id>')
@login_required
def sell_product(id):
    products = load_db(DB_PRODUCTS)
    sales = load_db(DB_SALES)
    for p in products:
        if p['id'] == id and p['quantity'] > 0:
            p['quantity'] -= 1
            sales.append({
                "product_id": id,
                "name": p['name'],
                "revenue": p['sell_price'],
                "profit": p['sell_price'] - p['purchase_price'],
                "date": datetime.now().strftime('%Y-%m-%d %H:%M')
            })
            flash(f"Sold 1 unit of {p['name']}.", "success")
            break
    else:
        flash("Product out of stock or not found.", "warning")
    save_db(DB_PRODUCTS, products)
    save_db(DB_SALES, sales)
    return redirect(url_for('dashboard'))

@app.route('/sales')
@login_required
def sales_page():
    sales = load_db(DB_SALES)
    return render_template('sales.html', sales=sales)

@app.route('/revenue')
@login_required
def revenue():
    sales = load_db(DB_SALES)
    total_revenue = sum(s['revenue'] for s in sales)
    total_profit = sum(s['profit'] for s in sales)
    return render_template('revenue.html', revenue=total_revenue, profit=total_profit, sales=sales)

@app.route('/barcode/<string:id>')
@login_required
def generate_barcode(id):
    products = load_db(DB_PRODUCTS)
    product = next((p for p in products if p['id'] == id), None)
    if not product:
        flash("Product not found.", "warning")
        return redirect(url_for('dashboard'))

    create_and_save_barcode(product['barcode'], product['id'])
    filepath = os.path.join(BARCODE_FOLDER, f"{product['id']}.png")
    return send_file(filepath, mimetype='image/png')

@app.route('/barcode-print/<string:id>')
@login_required
def barcode_print(id):
    products = load_db(DB_PRODUCTS)
    product = next((p for p in products if p['id'] == id), None)
    if not product:
        flash("Product not found.", "warning")
        return redirect(url_for('dashboard'))
    return render_template('barcode_print.html', product=product)

if __name__ == '__main__':
    app.run(debug=True)

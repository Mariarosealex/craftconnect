from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_mail import Mail, Message

import os
import sqlite3
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit, join_room, leave_room
import json
import base64


# Store active chat rooms

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # Change this to a strong secret key
socketio = SocketIO(app) # Enable WebSockets
active_chats = {}

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'  # Replace with your email
app.config['MAIL_PASSWORD'] = 'your-email-password'  # Replace with an app password
app.config['MAIL_DEFAULT_SENDER'] = 'your-email@gmail.com'

mail = Mail(app)


# Upload folder for profile pictures & product images
UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
db_path = os.path.abspath("craftconnect.db")  # Change to your actual database file
print("Using database file at:", db_path)
def init_db():
    conn = sqlite3.connect("craftconnect.db")
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            user_type TEXT NOT NULL,
            profile_pic TEXT DEFAULT 'default_profile.jpg'
        )
    """)


    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            receiver TEXT NOT NULL,
             message TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')


    # Products table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            price REAL NOT NULL,
            image TEXT NOT NULL,
            manufacturer_id INTEGER,
            FOREIGN KEY (manufacturer_id) REFERENCES users (id)
        )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        manufacturer_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,  -- 0 = Unread, 1 = Read
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (manufacturer_id) REFERENCES users(id)
        )
    """)

    # Cart table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    """)

    # Orders table (to store customer orders)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            total_price REAL NOT NULL,
            status TEXT DEFAULT 'Processing',
            payment_status TEXT NOT NULL DEFAULT 'COD',  -- "COD" or "Paid"
            refund_status TEXT DEFAULT 'Not Refunded',  -- "Refunded" or "Not Refunded"
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    """)

    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contact_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
DB_PATH = "craftconnect.db"

# Function to connect to the database
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Function to initialize the database
def initialize_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Ensure admin table exists
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
    """)
    cursor.execute("""DELETE FROM admin WHERE username = 'admin@gmail.com';
    """)
    # Check if the admin user exists
    cursor.execute("SELECT * FROM admin WHERE username = ?", ("admin@gmail.com",))
    existing_admin = cursor.fetchone()

    # If admin doesn't exist, insert it with a hashed password
    if not existing_admin:
        hashed_password = generate_password_hash("admin123")  # Hashing only once
        cursor.execute("INSERT INTO admin (username, password) VALUES (?, ?)", 
                       ("admin@gmail.com", hashed_password))
        conn.commit()
        print("✅ Admin user created successfully!")
    else:
        print("✅ Admin user already exists.")

    conn.close()

# Initialize the database
initialize_db()

# Admin Login Route
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('username')  
        password = request.form.get('password')

        conn = get_db_connection()
        admin = conn.execute('SELECT * FROM admin WHERE username = ?', (email,)).fetchone()
        conn.close()

        if admin:
            stored_password = admin['password']  # Ensure it's a string
            print(f"DEBUG: Stored Password Hash = {stored_password[:10]}... (Truncated)")  # Safer logging
            print(f"DEBUG: Checking password for {email}")

            if check_password_hash(stored_password, password):  
                session['admin_logged_in'] = True
                print("✅ Login successful!")
                return redirect('/admin/dashboard')
            else:
                print("⚠️ DEBUG: Password mismatch!")
                flash('Invalid credentials', 'danger')
        else:
            print("⚠️ DEBUG: No such user found!")
            flash('Invalid credentials', 'danger')

    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return render_template('/login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_logged_in' not in session:
        return redirect('/admin')
    conn = get_db_connection()
    users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    orders = conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
    products = conn.execute('SELECT COUNT(*) FROM products').fetchone()[0]
    conn.close()
    return render_template('admin_dashboard.html', users=users, orders=orders, products=products)

@app.route('/admin/users')
def admin_users():
    if 'admin_logged_in' not in session:
        return redirect('/admin')
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users').fetchall()
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE products ADD COLUMN approved INTEGER DEFAULT 0;")
        conn.commit()
        print("✅ 'approved' column added successfully!")
    except sqlite3.OperationalError:
        print("⚠️ Column 'approved' already exists. No changes made.")


    conn.close()
    return render_template('admin_users.html', users=users)

@app.route('/admin/user/delete/<int:user_id>')
def delete_user(user_id):
    if 'admin_logged_in' not in session:
        return redirect('/admin')
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    flash('User deleted successfully', 'success')
    return redirect('/admin/users')

@app.route('/admin/products')
def admin_products():
    if 'admin_logged_in' not in session:
        return redirect('/admin')
    conn = get_db_connection()
    products = conn.execute('SELECT * FROM products WHERE approved = 0').fetchall()
    conn.close()
    return render_template('admin_products.html', products=products)

@app.route('/admin/product/approve/<int:product_id>')
def approve_product(product_id):
    if 'admin_logged_in' not in session:
        return redirect('/admin')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE products SET approved = 1 WHERE id = ?', (product_id,))
    conn.commit()
    affected_rows = cursor.rowcount  # Get number of affected rows
    conn.close()

    if affected_rows > 0:
        print(f"✅ Product {product_id} approved successfully!")
    else:
        print(f"⚠️ Product {product_id} approval update failed!")

    flash('✅ Product approved successfully!', 'success')
    return redirect('/admin/products')


@app.route('/admin/product/reject/<int:product_id>')
def reject_product(product_id):
    if 'admin_logged_in' not in session:
        return redirect('/admin')

    conn = get_db_connection()
    try:
        conn.execute('UPDATE products SET approved = -1 WHERE id = ?', (product_id,))
        conn.commit()
        print(f"❌ Product {product_id} rejected!")  # Debugging message
    except Exception as e:
        print("Error rejecting product:", e)  # Log errors
    finally:
        conn.close()

    flash('❌ Product rejected!', 'danger')
    return redirect('/admin/products')

@app.route('/admin/orders')
def admin_orders():
    if 'admin_logged_in' not in session:
        return redirect('/admin')

    conn = get_db_connection()
    
    orders = conn.execute('''
        SELECT orders.id, orders.user_id, orders.quantity, orders.total_price, orders.status,
               products.name AS product_name, products.image
        FROM orders
        JOIN products ON orders.product_id = products.id
    ''').fetchall()
    
    conn.close()

    # Debugging: Print retrieved image paths
    for order in orders:
        print(f"Order ID {order['id']} - Image Path: {order['image']}")

    return render_template('admin_orders.html', orders=orders)

@app.route('/admin/enquiries')
def admin_enquiries():
    conn = sqlite3.connect('craftconnect.db')
    cursor = conn.cursor()

    # Fetch all enquiries and corresponding replies
    cursor.execute('''
        SELECT cm.id, cm.name, cm.email, cm.content, er.reply 
        FROM contact_messages cm
        LEFT JOIN enquiry_replies er ON cm.id = er.enquiry_id
        ORDER BY cm.id DESC
    ''')
    enquiries = cursor.fetchall()

    conn.close()
    return render_template('admin_enquiries.html', enquiries=enquiries)


# Create a table to store admin replies
def create_reply_table():
    conn = sqlite3.connect('craftconnect.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS enquiry_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enquiry_id INTEGER NOT NULL,
            reply TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (enquiry_id) REFERENCES contact_messages(id)
        )
    ''')
    conn.commit()
    conn.close()

# Call this function when starting the app
create_reply_table()

@app.route('/reply_enquiry/<int:enquiry_id>', methods=['POST'])
def reply_enquiry(enquiry_id):
    reply_message = request.form['reply_message']

    conn = sqlite3.connect('craftconnect.db')
    cursor = conn.cursor()

    # Store admin reply in enquiry_replies
    cursor.execute('''
        INSERT INTO enquiry_replies (enquiry_id, reply) 
        VALUES (?, ?)
    ''', (enquiry_id, reply_message))

    conn.commit()
    conn.close()

    flash('Reply sent successfully!', 'success')
    return redirect(url_for('admin_enquiries'))


@app.route('/user/enquiries')
def user_enquiries():
    user_id = session.get('user_id')  # Assuming you store user session

    conn = sqlite3.connect('craftconnect.db')
    cursor = conn.cursor()

    # Fetch user enquiries and corresponding admin replies
    cursor.execute('''
        SELECT cm.id, cm.content, er.reply 
        FROM contact_messages cm
        LEFT JOIN enquiry_replies er ON cm.id = er.enquiry_id
        WHERE cm.email = (SELECT email FROM users WHERE id = ?)
        ORDER BY cm.id DESC
    ''', (user_id,))

    enquiries = cursor.fetchall()
    conn.close()

    return render_template('user_enquiries.html', enquiries=enquiries)



@app.route('/send_reply', methods=['POST'])
def send_reply():
    message_id = request.form['message_id']
    reply_content = request.form['reply_content']

    conn = sqlite3.connect('craftconnect.db')
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE contact_messages
        SET reply = ?, status = 'unread'
        WHERE id = ?
    ''', (reply_content, message_id))

    conn.commit()
    conn.close()

    flash('Reply sent successfully!', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/users')
def manage_users():
    if 'admin_logged_in' not in session:
        return redirect('/admin')

    user_type = request.args.get("user_type", "all")  # Filter by user type
    suspended_status = request.args.get("suspended", "all")  # Filter by suspension status

    conn = get_db_connection()
    cursor = conn.cursor()

    # Base query
    query = "SELECT id, name, email, user_type, suspended FROM users WHERE 1=1"
    params = []

    # Apply user type filter if specified
    if user_type in ["customer", "manufacturer"]:
        query += " AND user_type = ?"
        params.append(user_type)

    # Apply suspended filter if specified
    if suspended_status == "true":
        query += " AND suspended = 1"
    elif suspended_status == "false":
        query += " AND suspended = 0"

    cursor.execute(query, params)
    users = cursor.fetchall()
    conn.close()

    return render_template("admin_users.html", users=users, user_type=user_type, suspended_status=suspended_status)

# Suspend User
@app.route('/admin/user/suspend/<int:user_id>')
def suspend_user(user_id):
    if 'admin_logged_in' not in session:
        return redirect('/admin')

    conn = get_db_connection()
    conn.execute("UPDATE users SET suspended = 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    flash("🚫 User suspended successfully!", "warning")
    return redirect(url_for("manage_users"))

# Restore User
@app.route('/admin/user/restore/<int:user_id>')
def restore_user(user_id):
    if 'admin_logged_in' not in session:
        return redirect('/admin')

    conn = get_db_connection()
    conn.execute("UPDATE users SET suspended = 0 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    flash("✅ User restored successfully!", "success")
    return redirect(url_for("manage_users"))

    def update_orders_table():
        conn = sqlite3.connect("craftconnect.db")
        cursor = conn.cursor()

        # Step 1: Add manufacturer_id column if not already present
        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN manufacturer_id INTEGER;")
        except sqlite3.OperationalError:
            print("Column manufacturer_id already exists, skipping...")

        # Step 2: Update existing rows with manufacturer_id from products table
        cursor.execute("""
            UPDATE orders 
            SET manufacturer_id = (
                SELECT manufacturer_id FROM products WHERE products.id = orders.product_id
            )
        """)

        conn.commit()
        conn.close()

    update_orders_table()
    conn.commit()
    conn.close()

init_db()


# Home Page


from werkzeug.security import generate_password_hash

@app.route('/signup', methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        user_type = request.form["user_type"]
        profile_pic = request.files["profile_pic"]

        if profile_pic:
            profile_pic_filename = profile_pic.filename
            profile_pic_path = os.path.join(app.config["UPLOAD_FOLDER"], profile_pic_filename)
            profile_pic.save(profile_pic_path)
        else:
            profile_pic_filename = "default_profile.jpg"

        hashed_password = generate_password_hash(password)

        try:
            with sqlite3.connect("craftconnect.db", timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO users (name, email, password, user_type, profile_pic) VALUES (?, ?, ?, ?, ?)",
                               (name, email, hashed_password, user_type, profile_pic_filename))
                conn.commit()
                print("User added to database:", name, email, user_type, profile_pic_filename)
                flash("Signup successful!", "success")
                return redirect(url_for("login"))
        except sqlite3.IntegrityError as e:
            print("Database error:", str(e))
            flash(f"Signup failed: Email already exists.", "danger")
        except Exception as e:
            print("Error:", str(e))
            flash(f"Signup failed: {str(e)}", "danger")

    return render_template("signup.html")

from werkzeug.security import check_password_hash

@app.route('/login', methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        print(f"Attempting login with email: {email}")

        try:
            with sqlite3.connect("craftconnect.db", timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, name, password, user_type, profile_pic, suspended FROM users WHERE email=?", (email,))
                user = cursor.fetchone()
                
                if user:
                    print(f"User found: {user}")
                else:
                    print("No user found with that email")

                if user and check_password_hash(user[2], password):
                    if user[5] == 1:  # Check if the user is suspended
                        flash("Your account is suspended. Please contact support.", "danger")
                        return redirect(url_for("login"))

                    session["user_id"] = user[0]
                    session["user_name"] = user[1]
                    session["user_type"] = user[3]
                    session["profile_pic"] = user[4]
                    flash("Login successful!", "success")
                    print("Login successful!")

                    if user[3] == "manufacturer":
                        return redirect(url_for("manufacturer_dashboard"))
                    else:
                        return redirect(url_for("customer_dashboard"))
                else:
                    flash("Invalid email or password", "danger")
                    print("Invalid email or password")
        
        except sqlite3.OperationalError as e:
            print("Database error:", str(e))
            return jsonify({"error": str(e)}), 500
        except Exception as e:
            print("Error:", str(e))
            return jsonify({"error": str(e)}), 500

    return render_template("login.html")
# Browse Products - Show only approved products
@app.route('/browse_products')
def browse_products():
    conn = sqlite3.connect("craftconnect.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT products.id, products.name, products.description, products.price, products.image, 
               users.name, users.id, products.approved
        FROM products
        JOIN users ON products.manufacturer_id = users.id
        WHERE products.approved = 1  -- Only show approved products
    """)
    products = cursor.fetchall()
    conn.close()

    print("Products retrieved for browsing:", products)  # Debugging
    return render_template("browse_products.html", products=products)
# Add to Cart
@app.route('/add_to_cart/<int:product_id>', methods=["POST"])
def add_to_cart(product_id):
    if "user_id" not in session:
        flash("You must be logged in to add items to the cart.", "danger")
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = sqlite3.connect("craftconnect.db")
    cursor = conn.cursor()

    # Check if the product is already in the cart
    cursor.execute("SELECT * FROM cart WHERE user_id=? AND product_id=?", (user_id, product_id))
    item = cursor.fetchone()

    if item:
        cursor.execute("UPDATE cart SET quantity = quantity + 1 WHERE user_id=? AND product_id=?", (user_id, product_id))
    else:
        cursor.execute("INSERT INTO cart (user_id, product_id, quantity) VALUES (?, ?, 1)", (user_id, product_id))

    conn.commit()
    conn.close()

    flash("Product added to cart!", "success")
    return redirect(url_for("browse_products"))

# View Cart
@app.route('/cart')
def cart():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = sqlite3.connect("craftconnect.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT products.id, products.name, products.price, cart.quantity, products.image
        FROM cart 
        JOIN products ON cart.product_id = products.id
        WHERE cart.user_id=?
    """, (user_id,))
    cart_items = cursor.fetchall()
    conn.close()

    return render_template("cart.html", cart_items=cart_items)

# Remove from Cart
@app.route('/remove_from_cart/<int:product_id>', methods=["POST"])
def remove_from_cart(product_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = sqlite3.connect("craftconnect.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cart WHERE user_id=? AND product_id=?", (user_id, product_id))
    conn.commit()
    conn.close()

    flash("Item removed from cart.", "info")
    return redirect(url_for("cart"))

# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route('/manufacturer_dashboard')
def manufacturer_dashboard():
    if "user_id" not in session or session["user_type"] != "manufacturer":
        return redirect(url_for("login"))

    # Pass the user_id (manufacturer ID) and other session details to the template
    return render_template("manufacturer_dashboard.html", 
                           user_name=session["user_name"], 
                           profile_pic=session["profile_pic"], 
                           manufacturer_id=session["user_id"])


@app.route('/add_product', methods=["GET", "POST"])
def add_product():
    if "user_id" not in session or session["user_type"] != "manufacturer":
        return redirect(url_for("login"))
    
    if request.method == "POST":
        # Log form data
        print("Form data received:", request.form)

        if 'product_name' not in request.form or 'description' not in request.form:
            return jsonify({"error": "Missing 'product_name' or 'description' in form data"}), 400

        name = request.form["product_name"]
        description = request.form["description"]
        price = float(request.form["price"])
        image = request.files["image"]

        if image:
            image_filename = image.filename
            image_path = os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
            image.save(image_path)
        else:
            image_filename = "default_product.jpg"

        try:
            with sqlite3.connect("craftconnect.db", timeout=10) as conn:
                cursor = conn.cursor()
                # Log SQL query
                print("Executing SQL query: INSERT INTO products (name, description, price, image, manufacturer_id, status) VALUES (?, ?, ?, ?, ?, ?)")
                print("With values:", (name, description, price, image_filename, session["user_id"], "pending"))
                
                cursor.execute("INSERT INTO products (name, description, price, image, manufacturer_id, status) VALUES (?, ?, ?, ?, ?, ?)", 
                               (name, description, price, image_filename, session["user_id"], "pending"))
                conn.commit()
                print("Product added to database (Pending Approval):", name, description, price, image_filename, session["user_id"])
        except sqlite3.OperationalError as e:
            print("Database error:", str(e))
            return jsonify({"error": str(e)}), 500
        except Exception as e:
            print("Error:", str(e))
            return jsonify({"error": str(e)}), 500

        flash("Product submitted for approval!", "success")
        return redirect(url_for("manufacturer_dashboard"))

    return render_template("add_product.html")


@app.route('/manage_products')
def manage_products():
    if "user_id" not in session or session["user_type"] != "manufacturer":
        return redirect(url_for("login"))

    manufacturer_id = session["user_id"]

    conn = sqlite3.connect("craftconnect.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE manufacturer_id=?", (manufacturer_id,))
    products = cursor.fetchall()
    conn.close()

    return render_template("manage_products.html", products=products)

@app.route('/delete_product/<int:product_id>', methods=["POST"])
def delete_product(product_id):
    if "user_id" not in session or session["user_type"] != "manufacturer":
        return redirect(url_for("login"))

    conn = sqlite3.connect("craftconnect.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id=? AND manufacturer_id=?", (product_id, session["user_id"]))
    conn.commit()
    conn.close()

    flash("Product deleted successfully!", "success")
    return redirect(url_for("manage_products"))


@app.route('/manage_orders')
def manage_orders():
    if "user_id" not in session or session["user_type"] != "manufacturer":
        return redirect(url_for("login"))

    try:
        with sqlite3.connect("craftconnect.db", timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    orders.id, 
                    users.name AS customer_name, 
                    products.name AS product_name, 
                    orders.quantity, 
                    orders.total_price, 
                    orders.status 
                FROM orders
                JOIN products ON orders.product_id = products.id
                JOIN users ON orders.user_id = users.id
                WHERE products.manufacturer_id = ?
            """, (session["user_id"],))

            orders = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print("Database error:", str(e))
        flash("Failed to load orders due to database error.", "danger")
        orders = []

    return render_template("manage_orders.html", orders=orders)

@app.route('/view_order/<int:order_id>')
def view_order(order_id):
    if "user_id" not in session or session["user_type"] != "manufacturer":
        return redirect(url_for("login"))

    try:
        with sqlite3.connect("craftconnect.db", timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT orders.id, users.username, products.name, orders.quantity, orders.total_price, orders.status
                FROM orders
                JOIN products ON orders.product_id = products.id
                JOIN users ON orders.user_id = users.id  -- Ensure you use "users" table, not "customers"
                WHERE orders.manufacturer_id = ?
            """, (manufacturer_id,))
            order = cursor.fetchone()
    except sqlite3.OperationalError as e:
        print("Database error:", str(e))
        flash("Failed to load order details due to database error.", "danger")
        order = None

    return render_template("view_order.html", order=order)

@app.route('/track_order')
def track_order():
    if "user_id" not in session:
        flash("You must be logged in to track your orders.", "danger")
        return redirect(url_for("login"))

    user_id = session["user_id"]
    orders = []

    try:
        with sqlite3.connect("craftconnect.db", timeout=10) as conn:
            conn.row_factory = sqlite3.Row  # Fetch rows as dictionaries
            cursor = conn.cursor()
            cursor.execute('''
                SELECT orders.id, products.name AS product_name, orders.quantity, 
                       orders.total_price, orders.payment_status, orders.address, 
                       orders.phone, orders.email, orders.status
                FROM orders
                JOIN products ON orders.product_id = products.id
                WHERE orders.user_id = ?
            ''', (user_id,))
            orders = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print(f"Database error: {e}")  # Print error in console for debugging
        flash(f"Failed to load orders: {e}", "danger")

    return render_template("track_order.html", orders=orders)

@app.route('/contact_manufacturer/<int:product_id>/<int:manufacturer_id>')
def contact_manufacturer(product_id, manufacturer_id):
    # Logic to load chat interface between customer and manufacturer
    return render_template('chat_interface.html', product_id=product_id, manufacturer_id=manufacturer_id)

@app.route('/chat/<int:manufacturer_id>')
def chat(manufacturer_id):
    conn = sqlite3.connect("craftconnect.db")
    cursor = conn.cursor()
    
    # Get manufacturer name
    cursor.execute("SELECT name FROM users WHERE id = ?", (manufacturer_id,))
    manufacturer_name = cursor.fetchone()[0]
    
    # Get previous chat messages
    cursor.execute("""
        SELECT sender, message FROM chat_messages
        WHERE manufacturer_id = ?
    """, (manufacturer_id,))
    chat_messages = cursor.fetchall()
    
    conn.close()
    
    return render_template('chat_interface.html', manufacturer_name=manufacturer_name, chat_messages=chat_messages)


# Handle incoming messages
@socketio.on('send_message')
def handle_message(data):
    message = data['message']
    sender = data['sender']  # 'customer' or 'manufacturer'
    
    # Broadcast the message to all connected clients
    emit('receive_message', {'message': message, 'sender': sender}, broadcast=True)

@app.route('/update_order_status/<int:order_id>', methods=["POST"])
def update_order_status(order_id):
    if "user_id" not in session or session["user_type"] != "manufacturer":
        return redirect(url_for("login"))

    status = request.form["status"]

    try:
        with sqlite3.connect("craftconnect.db", timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE orders
                SET status = ?
                WHERE id = ? AND product_id IN (SELECT id FROM products WHERE manufacturer_id = ?)
            ''', (status, order_id, session["user_id"]))
            conn.commit()

        # Flash message for UI feedback
        flash("Order status updated successfully!", "success")
        return jsonify({"success": True})

    except sqlite3.OperationalError as e:
        print("Database error:", str(e))
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/customer_dashboard')
def customer_dashboard():
    if "user_id" not in session or session["user_type"] != "customer":
        return redirect(url_for("login"))

    user_email = session.get("user_email")
    unread_replies = 0

    if user_email:
        conn = sqlite3.connect('craftconnect.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM contact_messages WHERE email = ? AND status = 'unread'", (user_email,))
        unread_replies = cursor.fetchone()[0]
        conn.close()

    return render_template("customer_dashboard.html", 
                           user_name=session["user_name"], 
                           profile_pic=session["profile_pic"], 
                           unread_replies=unread_replies)

@app.route('/checkout', methods=["GET", "POST"])
def checkout():
    if "user_id" not in session:
        flash("You must be logged in to checkout.", "danger")
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = sqlite3.connect("craftconnect.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT products.id, products.name, products.price, cart.quantity 
        FROM cart 
        JOIN products ON cart.product_id = products.id
        WHERE cart.user_id=?
    """, (user_id,))
    cart_items = cursor.fetchall()
    conn.close()

    grand_total = sum(item[2] * item[3] for item in cart_items)

    return render_template("checkout.html", cart_items=cart_items, grand_total=grand_total)

@app.route('/place_order', methods=["POST"])
def place_order():
    if "user_id" not in session:
        flash("You must be logged in to place an order.", "danger")
        return redirect(url_for("login"))

    user_id = session["user_id"]
    address = request.form.get("address")
    phone = request.form.get("phone")
    email = request.form.get("email")
    payment_status = request.form.get("payment_status")

    conn = sqlite3.connect("craftconnect.db")
    cursor = conn.cursor()

    # Fetch products from the cart along with manufacturer_id
    cursor.execute("""
        SELECT products.id, products.name, products.price, cart.quantity, products.manufacturer_id 
        FROM cart 
        JOIN products ON cart.product_id = products.id
        WHERE cart.user_id=?
    """, (user_id,))
    cart_items = cursor.fetchall()

    if not cart_items:
        flash("Your cart is empty!", "warning")
        return redirect(url_for("cart"))

    grand_total = 0
    for item in cart_items:
        product_id = item[0]
        product_name = item[1]
        price = item[2]
        quantity = item[3]
        manufacturer_id = item[4]  # Fetching manufacturer_id from products table
        total_price = price * quantity
        grand_total += total_price

        # Insert into orders table
        cursor.execute("""
            INSERT INTO orders (user_id, product_id, quantity, total_price, payment_status, address, phone, email, status) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, product_id, quantity, total_price, payment_status, address, phone, email, "Processing"))

        # Insert a notification for the manufacturer
        cursor.execute("""
            INSERT INTO notifications (manufacturer_id, message, is_read) 
            VALUES (?, ?, 0)
        """, (manufacturer_id, f"New order received for {product_name}",))

    # Clear the cart after placing the order
    cursor.execute("DELETE FROM cart WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

    flash("Order placed successfully! A confirmation email has been sent.", "success")
    return redirect(url_for("customer_dashboard"))

@app.route('/orders')
def orders():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = sqlite3.connect("craftconnect.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT orders.id, products.name, orders.quantity, orders.total_price, orders.status, orders.order_date 
        FROM orders 
        JOIN products ON orders.product_id = products.id
        WHERE orders.user_id=?
        ORDER BY orders.order_date DESC
    """, (user_id,))
    orders = cursor.fetchall()
    conn.close()

    return render_template("orders.html", orders=orders)

@app.route('/test')
def test():
    flash("This is a success message!", "success")
    flash("This is an error message!", "error")
    return redirect(url_for("home"))



@app.route('/')
def home():
    return render_template('index.html')  # Your homepage

@app.route('/about')
def about():
    return render_template('about.html')  # About Us page

@app.route('/faqs')
def faqs():
    return render_template('faqs.html')  # FAQs page

@app.route('/contact')
def contact():
    return render_template('contact.html')  # Contact Us page

@app.route('/terms')
def terms():
    return render_template('terms.html')  # Ensure this file exists in your templates folder

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

# Function to insert contact message into the database
def insert_message(name, email, content):
    conn = sqlite3.connect('craftconnect.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO contact_messages (name, email, content) 
        VALUES (?, ?, ?)
    ''', (name, email, content))
    conn.commit()
    conn.close()

@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    if "user_id" not in session or session["user_type"] != "manufacturer":
        flash("You must be logged in as a manufacturer to edit products.", "danger")
        return redirect(url_for("login"))

    with sqlite3.connect("craftconnect.db") as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id=?", (product_id,))
        product = cursor.fetchone()

    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for("manage_products"))

    if request.method == "POST":
        name = request.form["name"]
        description = request.form["description"]
        price = request.form["price"]
        
        # 🛠 Check if an image is uploaded
        if "image" in request.files:
            image = request.files["image"]
            if image.filename != "":  # Only update if a new image is provided
                image_path = f"static/uploads/{image.filename}"
                image.save(image_path)
            else:
                image_path = product["image"]  # Keep old image if no new file uploaded
        else:
            image_path = product["image"]  # Keep old image if no file uploaded

        # ✅ Update the product in the database
        with sqlite3.connect("craftconnect.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE products SET name=?, description=?, price=?, image=? WHERE id=?",
                (name, description, price, image_path, product_id),
            )
            conn.commit()

        flash("Product updated successfully.", "success")
        return redirect(url_for("manage_products"))

    return render_template("edit_product.html", product=product)


@app.route('/submit_contact_form', methods=['POST'])
def submit_contact_form():
    name = request.form['name']
    email = request.form['email']
    content = request.form['message']

    insert_message(name, email, content)  # Store the message in the database

    flash('Your message has been sent successfully!', 'success')
    return redirect(url_for('contact'))  # Redirect back to the contact page



@app.route("/cancel_order/<int:order_id>")
def cancel_order(order_id):
    return render_template("cancel.html", order_id=order_id)

@app.route('/confirm_cancel_order/<int:order_id>', methods=['POST'])
def confirm_cancel_order(order_id):
    conn = sqlite3.connect("craftconnect.db")
    cursor = conn.cursor()

    # Check if the order exists
    cursor.execute("SELECT status FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()

    if order:
        # Update status to "Cancelled"
        cursor.execute("UPDATE orders SET status = 'Cancelled' WHERE id = ?", (order_id,))
        conn.commit()

    conn.close()
    flash("Order cancelled successfully!", "info")
    return redirect(url_for('track_order'))  # Return nothing, just update status

@app.route('/manufacturer_orders')
def manufacturer_orders():
    if "user_id" not in session or session["user_type"] != "manufacturer":
        return redirect(url_for("login"))

    manufacturer_id = session["user_id"]  # Get the logged-in manufacturer ID

    conn = sqlite3.connect("craftconnect.db")
    cursor = conn.cursor()

    # Fetch orders where this manufacturer is involved
    cursor.execute("""
        SELECT orders.id, users.username, products.name, orders.quantity, orders.total_price, orders.status
        FROM orders
        JOIN products ON orders.product_id = products.id
        JOIN users ON orders.user_id = users.id
        WHERE orders.manufacturer_id = ?
    """, (manufacturer_id,))

    orders = cursor.fetchall()
    conn.close()

    return render_template("manufacturer_orders.html", orders=orders)


@app.route('/manufacturer_notifications')
def manufacturer_notifications():
    if "user_id" not in session or session["user_type"] != "manufacturer":
        return redirect(url_for("login"))

    manufacturer_id = session["user_id"]

    try:
        with sqlite3.connect("craftconnect.db", timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, message, created_at FROM notifications 
                WHERE manufacturer_id = ? AND is_read = 0
            """, (manufacturer_id,))
            notifications = cursor.fetchall()

        return render_template("manufacturer_notifications.html", notifications=notifications)

    except sqlite3.OperationalError as e:
        print("Database error:", str(e))
        flash("Error fetching notifications.", "danger")
        return redirect(url_for("manufacturer_dashboard"))

@app.route('/update_cart_quantity/<int:product_id>', methods=['POST'])
def update_cart_quantity(product_id):
    new_quantity = request.form.get('quantity', type=int)
    
    if new_quantity and new_quantity > 0:
        conn = sqlite3.connect("craftconnect.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE cart SET quantity = ? WHERE product_id = ?", (new_quantity, product_id))
        conn.commit()
        conn.close()
    
    return redirect(url_for('cart'))

# Function to get database connection
def get_db_connection():
    conn = sqlite3.connect("craftconnect.db")
    conn.row_factory = sqlite3.Row
    return conn



# API to fetch chat messages
@app.route("/get_messages", methods=["GET"])
def get_messages():
    sender = request.args.get("sender")
    receiver = request.args.get("receiver")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM chat_messages 
        WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?) 
        ORDER BY timestamp ASC
    ''', (sender, receiver, receiver, sender))

    messages = cursor.fetchall()
    conn.close()

    return jsonify([dict(msg) for msg in messages])

# API to send a message
@app.route("/send_message", methods=["POST"])
def send_message():
    data = request.json
    sender = data["sender"]
    receiver = data["receiver"]
    message = data["message"]

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_messages (sender, receiver, message) VALUES (?, ?, ?)", (sender, receiver, message))
    conn.commit()
    conn.close()

    return jsonify({"status": "Message sent!"})

@app.route('/view_messages/<int:manufacturer_id>')
def view_messages(manufacturer_id):
    conn = sqlite3.connect("craftconnect.db")
    cursor = conn.cursor()

    # Get all customers who have messaged the manufacturer
    cursor.execute("""
        SELECT DISTINCT chat_messages.customer_id, users.name 
        FROM chat_messages
        JOIN users ON chat_messages.customer_id = users.id
        WHERE chat_messages.manufacturer_id = ?
    """, (manufacturer_id,))
    
    conversations = cursor.fetchall()
    conn.close()
    
    # Render template to show list of conversations
    return render_template('view_messages.html', conversations=conversations, manufacturer_id=manufacturer_id)

# Run Flask App
if __name__ == "__main__":
    app.run(debug=True)


import os
import math
from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__, template_folder="../templates")
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")

# --- In-memory data ---
users = [{"id": 1, "username": "admin", "password": os.environ.get("ADMIN_PASSWORD", "admin123"), "email": "admin@vape.com", "role": "admin"}]
next_user_id = 2

products = [
    {"id": 1, "name": "Mango Ice", "flavor": "Mango", "nicotine": 50, "size": 30, "price": 350.00, "stock": 20, "image": "mango"},
    {"id": 2, "name": "Blueberry Blast", "flavor": "Blueberry", "nicotine": 35, "size": 60, "price": 480.00, "stock": 15, "image": "blueberry"},
    {"id": 3, "name": "Strawberry Milk", "flavor": "Strawberry", "nicotine": 25, "size": 30, "price": 320.00, "stock": 25, "image": "strawberry"},
    {"id": 4, "name": "Mint Breeze", "flavor": "Mint", "nicotine": 50, "size": 30, "price": 350.00, "stock": 18, "image": "mint"},
    {"id": 5, "name": "Grape Soda", "flavor": "Grape", "nicotine": 35, "size": 60, "price": 500.00, "stock": 10, "image": "grape"},
    {"id": 6, "name": "Lychee Frost", "flavor": "Lychee", "nicotine": 50, "size": 30, "price": 380.00, "stock": 12, "image": "lychee"},
]
next_product_id = 7

orders = []
next_order_id = 1


def get_product(pid):
    return next((p for p in products if p["id"] == pid), None)

def get_user(uid):
    return next((u for u in users if u["id"] == uid), None)

def current_user():
    return get_user(session.get("user_id")) if "user_id" in session else None

def is_admin():
    u = current_user()
    return u and u["role"] == "admin"

def cart_count():
    return sum(v["qty"] for v in session.get("cart", {}).values())


# --- HOME ---
@app.route("/")
def home():
    if is_admin():
        return redirect(url_for("admin"))
    featured = products[:6]
    return render_template("home.html", products=featured, user=current_user(), cart_count=cart_count())


# --- SHOP ---
@app.route("/shop")
def shop():
    if is_admin():
        return redirect(url_for("admin"))
    return render_template("shop.html", products=products, user=current_user(), cart_count=cart_count())


# --- REGISTER ---
@app.route("/register", methods=["GET", "POST"])
def register():
    global next_user_id
    if current_user():
        return redirect(url_for("home"))
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]
        if any(u["username"] == username for u in users):
            flash("Username already taken.", "danger")
        elif any(u["email"] == email for u in users):
            flash("Email already registered.", "danger")
        else:
            users.append({"id": next_user_id, "username": username, "password": password, "email": email, "role": "customer"})
            next_user_id += 1
            flash("Account created! Please login.", "success")
            return redirect(url_for("login"))
    return render_template("register.html", user=None, cart_count=cart_count())


# --- LOGIN ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("home"))
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        u = next((x for x in users if x["username"] == username and x["password"] == password), None)
        if u:
            session["user_id"] = u["id"]
            session["cart"] = session.get("cart", {})
            flash(f"Welcome back, {u['username']}!", "success")
            return redirect(url_for("admin") if u["role"] == "admin" else url_for("home"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html", user=None, cart_count=cart_count())


# --- LOGOUT ---
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("home"))


# --- ADD TO CART ---
@app.route("/cart/add/<int:pid>", methods=["POST"])
def add_to_cart(pid):
    if not current_user():
        flash("Please login to add items to cart.", "warning")
        return redirect(url_for("login"))
    p = get_product(pid)
    if not p:
        return redirect(url_for("shop"))
    cart = session.get("cart", {})
    key = str(pid)
    qty = int(request.form.get("qty", 1))
    cart[key] = {"qty": cart[key]["qty"] + qty if key in cart else qty, "name": p["name"], "price": p["price"]}
    session["cart"] = cart
    flash(f"{p['name']} added to cart!", "success")
    return redirect(request.referrer or url_for("shop"))


# --- CART ---
@app.route("/cart")
def cart():
    if is_admin():
        return redirect(url_for("admin"))
    if not current_user():
        return redirect(url_for("login"))
    cart = session.get("cart", {})
    items = []
    for pid, v in cart.items():
        p = get_product(int(pid))
        if p:
            items.append({"product": p, "qty": v["qty"], "subtotal": v["qty"] * p["price"]})
    total = sum(i["subtotal"] for i in items)
    return render_template("cart.html", items=items, total=total, user=current_user(), cart_count=cart_count())


# --- UPDATE CART ---
@app.route("/cart/update/<int:pid>", methods=["POST"])
def update_cart(pid):
    cart = session.get("cart", {})
    key = str(pid)
    qty = int(request.form.get("qty", 1))
    if qty <= 0:
        cart.pop(key, None)
    else:
        if key in cart:
            cart[key]["qty"] = qty
    session["cart"] = cart
    return redirect(url_for("cart"))


# --- REMOVE FROM CART ---
@app.route("/cart/remove/<int:pid>")
def remove_from_cart(pid):
    cart = session.get("cart", {})
    cart.pop(str(pid), None)
    session["cart"] = cart
    return redirect(url_for("cart"))


# --- CHECKOUT ---
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    global next_order_id
    if is_admin():
        return redirect(url_for("admin"))
    if not current_user():
        return redirect(url_for("login"))
    cart = session.get("cart", {})
    if not cart:
        return redirect(url_for("cart"))
    items = []
    for pid, v in cart.items():
        p = get_product(int(pid))
        if p:
            items.append({"product": p, "qty": v["qty"], "subtotal": v["qty"] * p["price"]})
    total = sum(i["subtotal"] for i in items)
    if request.method == "POST":
        order = {
            "id": next_order_id,
            "user_id": current_user()["id"],
            "username": current_user()["username"],
            "name": request.form["name"],
            "address": request.form["address"],
            "phone": request.form["phone"],
            "items": items,
            "total": total,
            "status": "Pending"
        }
        orders.append(order)
        next_order_id += 1
        session["cart"] = {}
        flash(f"Order #{order['id']} placed successfully!", "success")
        return redirect(url_for("order_success", oid=order["id"]))
    return render_template("checkout.html", items=items, total=total, user=current_user(), cart_count=cart_count())


# --- ORDER SUCCESS ---
@app.route("/order/<int:oid>")
def order_success(oid):
    order = next((o for o in orders if o["id"] == oid), None)
    return render_template("order_success.html", order=order, user=current_user(), cart_count=cart_count())


# --- ADMIN PANEL ---
@app.route("/admin")
def admin():
    if not is_admin():
        return redirect(url_for("home"))
    return render_template("admin.html", products=products, orders=orders, users=users, user=current_user(), cart_count=cart_count())


# --- ADMIN ADD PRODUCT ---
@app.route("/admin/add", methods=["GET", "POST"])
def admin_add():
    global next_product_id
    if not is_admin():
        return redirect(url_for("home"))
    if request.method == "POST":
        try:
            nicotine = int(request.form["nicotine"])
            size = int(request.form["size"])
            price = float(request.form["price"])
            stock = int(request.form["stock"])
            if math.isnan(price) or math.isinf(price) or price < 0:
                raise ValueError("Invalid price")
        except (ValueError, TypeError):
            flash("Invalid numeric values provided.", "danger")
            return render_template("admin_form.html", item=None, user=current_user(), cart_count=cart_count())
        products.append({
            "id": next_product_id,
            "name": request.form["name"],
            "flavor": request.form["flavor"],
            "nicotine": nicotine,
            "size": size,
            "price": price,
            "stock": stock,
            "image": request.form["flavor"].lower().split()[0]
        })
        next_product_id += 1
        flash("Product added!", "success")
        return redirect(url_for("admin"))
    return render_template("admin_form.html", item=None, user=current_user(), cart_count=cart_count())


# --- ADMIN EDIT PRODUCT ---
@app.route("/admin/edit/<int:pid>", methods=["GET", "POST"])
def admin_edit(pid):
    if not is_admin():
        return redirect(url_for("home"))
    p = get_product(pid)
    if request.method == "POST":
        try:
            nicotine = int(request.form["nicotine"])
            size = int(request.form["size"])
            price = float(request.form["price"])
            stock = int(request.form["stock"])
            if math.isnan(price) or math.isinf(price) or price < 0:
                raise ValueError("Invalid price")
        except (ValueError, TypeError):
            flash("Invalid numeric values provided.", "danger")
            return render_template("admin_form.html", item=p, user=current_user(), cart_count=cart_count())
        p["name"] = request.form["name"]
        p["flavor"] = request.form["flavor"]
        p["nicotine"] = nicotine
        p["size"] = size
        p["price"] = price
        p["stock"] = stock
        flash("Product updated!", "success")
        return redirect(url_for("admin"))
    return render_template("admin_form.html", item=p, user=current_user(), cart_count=cart_count())


# --- ADMIN DELETE PRODUCT ---
@app.route("/admin/delete/<int:pid>")
def admin_delete(pid):
    global products
    if not is_admin():
        return redirect(url_for("home"))
    products = [p for p in products if p["id"] != pid]
    flash("Product deleted.", "info")
    return redirect(url_for("admin"))


# --- ADMIN UPDATE ORDER STATUS ---
VALID_STATUSES = {"Pending", "Shipped", "Delivered"}

@app.route("/admin/order/<int:oid>/<status>")
def update_order(oid, status):
    if not is_admin():
        return redirect(url_for("home"))
    if status not in VALID_STATUSES:
        flash("Invalid order status.", "danger")
        return redirect(url_for("admin"))
    order = next((o for o in orders if o["id"] == oid), None)
    if order:
        order["status"] = status
    return redirect(url_for("admin"))

import os
import math
import uuid
import logging
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from supabase import create_client, Client

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")

supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_KEY"),
)

# Maps product id (1-based) to vape1.jpg ... vape6.jpg by cycling
VAPE_IMGS = ["vape1.jpg", "vape2.jpg", "vape3.jpg", "vape4.jpg", "vape5.jpg", "vape6.jpg"]


# --- Helpers ---
def get_product(pid):
    try:
        res = supabase.table("products").select("*").eq("id", pid).single().execute()
        return res.data
    except Exception:
        return None

def get_user(uid):
    try:
        res = supabase.table("users").select("*").eq("id", uid).single().execute()
        return res.data
    except Exception:
        return None

def current_user():
    return get_user(session["user_id"]) if "user_id" in session else None

def is_admin():
    u = current_user()
    return u and u["role"] == "admin"

def cart_count():
    return sum(v["qty"] for v in session.get("cart", {}).values())

def product_image(p):
    # If admin uploaded a custom image, use it
    if p.get("image"):
        return "/static/images/" + p["image"]
    # Otherwise fall back to vape1-6.jpg by product id
    idx = (int(p.get("id", 1)) - 1) % len(VAPE_IMGS)
    return "/static/images/" + VAPE_IMGS[idx]


# --- SERVE STATIC IMAGES ---
@app.route("/static/images/<path:filename>")
def static_images(filename):
    return send_from_directory(os.path.join(app.static_folder, "images"), filename)


# --- HOME ---
@app.route("/")
def home():
    if is_admin():
        return redirect(url_for("admin"))
    products = supabase.table("products").select("*").limit(6).execute().data or []
    return render_template("home.html", products=products, user=current_user(), cart_count=cart_count(), product_image=product_image)


# --- SHOP ---
@app.route("/shop")
def shop():
    if is_admin():
        return redirect(url_for("admin"))
    products = supabase.table("products").select("*").execute().data or []
    return render_template("shop.html", products=products, user=current_user(), cart_count=cart_count(), product_image=product_image)


# --- REGISTER ---
@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("home"))
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]
        existing = supabase.table("users").select("id").or_(
            f"username.eq.{username},email.eq.{email}"
        ).execute().data
        if existing:
            flash("Username or email already taken.", "danger")
        else:
            supabase.table("users").insert({
                "username": username,
                "email": email,
                "password": password,
                "role": "customer"
            }).execute()
            flash("Account created! Please login.", "success")
            return redirect(url_for("login"))
    return render_template("register.html", user=None, cart_count=0)


# --- LOGIN ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("home"))
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        res = supabase.table("users").select("*").eq("username", username).eq("password", password).execute()
        u = res.data[0] if res.data else None
        if u:
            session["user_id"] = u["id"]
            session["cart"] = session.get("cart", {})
            flash(f"Welcome back, {u['username']}!", "success")
            return redirect(url_for("admin") if u["role"] == "admin" else url_for("home"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html", user=None, cart_count=0)


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
    return render_template("cart.html", items=items, total=total, user=current_user(), cart_count=cart_count(), product_image=product_image)


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
        u = current_user()
        try:
            order_res = supabase.table("orders").insert({
                "user_id": u["id"],
                "username": u["username"],
                "name": request.form["name"],
                "address": request.form["address"],
                "phone": request.form["phone"],
                "total": float(total),
                "status": "Pending"
            }).execute()
            if not order_res.data:
                raise Exception("Failed to create order")
            order = order_res.data[0]
            order_items = [
                {
                    "order_id": order["id"],
                    "product_id": i["product"]["id"],
                    "product_name": i["product"]["name"],
                    "qty": int(i["qty"]),
                    "subtotal": float(i["subtotal"])
                }
                for i in items
            ]
            supabase.table("order_items").insert(order_items).execute()
            for i in items:
                new_stock = max(0, int(i["product"]["stock"]) - int(i["qty"]))
                supabase.table("products").update({"stock": new_stock}).eq("id", i["product"]["id"]).execute()
            session["cart"] = {}
            flash(f"Order #{order['id']} placed successfully!", "success")
            return redirect(url_for("order_success", oid=order["id"]))
        except Exception as e:
            app.logger.error(f"Checkout error: {e}")
            flash(f"Error placing order: {e}", "danger")
            return render_template("checkout.html", items=items, total=total, user=current_user(), cart_count=cart_count(), product_image=product_image)
    return render_template("checkout.html", items=items, total=total, user=current_user(), cart_count=cart_count(), product_image=product_image)


# --- MY ORDERS ---
@app.route("/orders")
def my_orders():
    if is_admin():
        return redirect(url_for("admin"))
    if not current_user():
        return redirect(url_for("login"))
    u = current_user()
    try:
        raw_orders = supabase.table("orders").select("*").eq("user_id", u["id"]).order("id", desc=True).execute().data or []
        orders = []
        for o in raw_orders:
            items = supabase.table("order_items").select("*").eq("order_id", o["id"]).execute().data or []
            orders.append({
                "id": o["id"],
                "name": o.get("name", ""),
                "phone": o.get("phone", ""),
                "address": o.get("address", ""),
                "total": o.get("total", 0),
                "status": o.get("status", "Pending"),
                "created_at": str(o.get("created_at", ""))[:10],
                "items": items
            })
    except Exception as e:
        app.logger.error(f"my_orders error: {e}")
        flash(f"Error loading orders: {e}", "danger")
        orders = []
    return render_template("my_orders.html", orders=orders, user=u, cart_count=cart_count())


# --- ORDER SUCCESS ---
@app.route("/order/<int:oid>")
def order_success(oid):
    order = None
    try:
        order = supabase.table("orders").select("*").eq("id", oid).single().execute().data
    except Exception:
        pass
    if order:
        raw_items = supabase.table("order_items").select("*").eq("order_id", oid).execute().data or []
        order["items"] = [
            {"product": {"name": i["product_name"], "id": i["product_id"]}, "qty": i["qty"], "subtotal": i["subtotal"]}
            for i in raw_items
        ]
    return render_template("order_success.html", order=order, user=current_user(), cart_count=cart_count())


# --- ADMIN PANEL ---
@app.route("/admin")
def admin():
    if not is_admin():
        return redirect(url_for("home"))
    products = supabase.table("products").select("*").execute().data or []
    orders = supabase.table("orders").select("*").order("id", desc=True).execute().data or []
    users = supabase.table("users").select("*").execute().data or []
    return render_template("admin.html", products=products, orders=orders, users=users, user=current_user(), cart_count=cart_count(), product_image=product_image)


# --- ADMIN ADD PRODUCT ---
@app.route("/admin/add", methods=["GET", "POST"])
def admin_add():
    if not is_admin():
        return redirect(url_for("home"))
    if request.method == "POST":
        try:
            nicotine = int(request.form["nicotine"])
            size = int(request.form["size"])
            price = float(request.form["price"])
            stock = int(request.form["stock"])
            if math.isnan(price) or math.isinf(price) or price < 0:
                raise ValueError
        except (ValueError, TypeError):
            flash("Invalid numeric values provided.", "danger")
            return render_template("admin_form.html", item=None, user=current_user(), cart_count=cart_count())
        image_filename = ""
        file = request.files.get("image")
        if file and file.filename:
            ext = os.path.splitext(secure_filename(file.filename))[1].lower()
            if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                image_filename = uuid.uuid4().hex + ext
                file.save(os.path.join(app.static_folder, "images", image_filename))
        supabase.table("products").insert({
            "name": request.form["name"],
            "flavor": request.form["flavor"],
            "nicotine": nicotine,
            "size": size,
            "price": price,
            "stock": stock,
            "image": image_filename
        }).execute()
        flash("Product added!", "success")
        return redirect(url_for("admin"))
    return render_template("admin_form.html", item=None, user=current_user(), cart_count=cart_count())


# --- ADMIN EDIT PRODUCT ---
@app.route("/admin/edit/<int:pid>", methods=["GET", "POST"])
def admin_edit(pid):
    if not is_admin():
        return redirect(url_for("home"))
    p = get_product(pid)
    if not p:
        flash("Product not found.", "danger")
        return redirect(url_for("admin"))
    if request.method == "POST":
        try:
            nicotine = int(request.form["nicotine"])
            size = int(request.form["size"])
            price = float(request.form["price"])
            stock = int(request.form["stock"])
            if math.isnan(price) or math.isinf(price) or price < 0:
                raise ValueError
        except (ValueError, TypeError):
            flash("Invalid numeric values provided.", "danger")
            return render_template("admin_form.html", item=p, user=current_user(), cart_count=cart_count())
        image_filename = p.get("image", "")
        file = request.files.get("image")
        if file and file.filename:
            ext = os.path.splitext(secure_filename(file.filename))[1].lower()
            if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                if image_filename:
                    old = os.path.join(app.static_folder, "images", image_filename)
                    if os.path.exists(old):
                        os.remove(old)
                image_filename = uuid.uuid4().hex + ext
                file.save(os.path.join(app.static_folder, "images", image_filename))
        supabase.table("products").update({
            "name": request.form["name"],
            "flavor": request.form["flavor"],
            "nicotine": nicotine,
            "size": size,
            "price": price,
            "stock": stock,
            "image": image_filename
        }).eq("id", pid).execute()
        flash("Product updated!", "success")
        return redirect(url_for("admin"))
    return render_template("admin_form.html", item=p, user=current_user(), cart_count=cart_count())


# --- ADMIN DELETE PRODUCT ---
@app.route("/admin/delete/<int:pid>")
def admin_delete(pid):
    if not is_admin():
        return redirect(url_for("home"))
    p = get_product(pid)
    if p and p.get("image"):
        old = os.path.join(app.static_folder, "images", p["image"])
        if os.path.exists(old):
            os.remove(old)
    supabase.table("products").delete().eq("id", pid).execute()
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
    supabase.table("orders").update({"status": status}).eq("id", oid).execute()
    flash(f"Order #{oid} marked as {status}.", "success")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    app.run(debug=True)

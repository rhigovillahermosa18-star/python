import os
import math
import uuid
import random
import logging
from dotenv import load_dotenv
from werkzeug.utils import secure_filename, safe_join
from werkzeug.exceptions import NotFound
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, abort
from flask_mail import Mail, Message
from supabase import create_client, Client
import cloudinary
import cloudinary.uploader

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES_DIR = os.path.join(BASE_DIR, "static", "images")
ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")

app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_EMAIL")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = ("CloudVape", os.environ.get("MAIL_EMAIL", ""))
mail = Mail(app)

supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_KEY"),
)

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
)

VAPE_IMGS = ["vape1.jpg", "vape2.jpg", "vape3.jpg", "vape4.jpg", "vape5.jpg", "vape6.jpg"]


# --- Helpers ---
def get_product(pid):
    try:
        return supabase.table("products").select("*").eq("id", pid).single().execute().data
    except Exception:
        return None

def get_user(uid):
    try:
        return supabase.table("users").select("*").eq("id", uid).single().execute().data
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
    img = p.get("image", "")
    if img:
        if img.startswith("http"):
            return img
        return "/static/images/" + os.path.basename(img)
    idx = (int(p.get("id", 1)) - 1) % len(VAPE_IMGS)
    return "/static/images/" + VAPE_IMGS[idx]

def save_image(file):
    """Uploads image to Cloudinary, returns secure URL or empty string."""
    if not file or not file.filename:
        return ""
    ext = os.path.splitext(secure_filename(file.filename))[1].lower()
    if ext not in ALLOWED_EXTS:
        return ""
    try:
        res = cloudinary.uploader.upload(file, folder="cloudvape")
        return res.get("secure_url", "")
    except Exception as e:
        app.logger.error("save_image error: %s", e)
        return ""

def delete_image(filename):
    """Deletes image from Cloudinary."""
    if not filename or not filename.startswith("http"):
        return
    try:
        # Extract public_id from URL
        parts = filename.split("/")
        public_id = "cloudvape/" + parts[-1].rsplit(".", 1)[0]
        cloudinary.uploader.destroy(public_id)
    except Exception as e:
        app.logger.error("delete_image error: %s", e)

def send_order_email(order, status):
    """Send shipped or delivered email to customer."""
    try:
        user = supabase.table("users").select("email,username").eq("id", order["user_id"]).single().execute().data
        if not user or not user.get("email"):
            return
        email = user["email"]
        name = order.get("name") or user["username"]
        oid = order["id"]
        total = order["total"]
        address = order.get("address", "")

        if status == "Shipped":
            subject = f"Your Order Has Been Shipped! 🚚 - CloudVape"
            status_color = "#8b5cf6"
            icon = "🚚"
            heading = "Your Order is On Its Way!"
            body = f"Great news! Your order <strong>#{ oid }</strong> has been shipped and is on its way to your delivery address."
            extra = f"<p style='color:#aaa;font-size:0.9rem'>📍 Delivery Address: <strong style='color:#fff'>{address}</strong></p>"
        else:
            subject = f"Your Order Has Been Delivered! ✅ - CloudVape"
            status_color = "#38ef7d"
            icon = "✅"
            heading = "Your Order Has Been Delivered!"
            body = f"Your order <strong>#{oid}</strong> has been successfully delivered. We hope you enjoy your purchase!"
            extra = "<p style='color:#aaa;font-size:0.9rem'>If you have any issues with your order, please contact us immediately.</p>"

        msg = Message(subject, recipients=[email])
        msg.html = f"""
        <div style="font-family:Segoe UI,sans-serif;max-width:520px;margin:auto;background:#0f0f1a;color:#e0e0e0;border-radius:16px;overflow:hidden">
          <div style="background:linear-gradient(135deg,#8b5cf6,#ec4899);padding:30px;text-align:center">
            <h1 style="color:#fff;margin:0;font-size:1.8rem">&#9729; CloudVape</h1>
          </div>
          <div style="padding:40px">
            <div style="text-align:center;font-size:3rem;margin-bottom:16px">{icon}</div>
            <h2 style="color:#fff;text-align:center;margin-bottom:8px">{heading}</h2>
            <p>Hi <strong>{name}</strong>,</p>
            <p style="color:#aaa">{body}</p>
            <div style="background:rgba(139,92,246,0.1);border:1px solid rgba(139,92,246,0.3);border-radius:12px;padding:20px;margin:24px 0">
              <table style="width:100%;color:#aaa;font-size:0.9rem">
                <tr><td>Order Number</td><td style="text-align:right;color:#8b5cf6;font-weight:700">#{oid}</td></tr>
                <tr><td>Total Amount</td><td style="text-align:right;color:#fff;font-weight:700">&#8369;{total}</td></tr>
                <tr><td>Status</td><td style="text-align:right"><span style="background:rgba(139,92,246,0.2);color:{status_color};border-radius:20px;padding:2px 12px;font-size:0.85rem">{status}</span></td></tr>
              </table>
            </div>
            {extra}
            <hr style="border-color:rgba(139,92,246,0.2);margin:24px 0">
            <p style="color:#666;font-size:0.85rem">&#9888;&#65039; Reminder: Our products are for <strong>adults 21+</strong> only. Please ensure someone of legal age received the package.</p>
            <hr style="border-color:rgba(139,92,246,0.2);margin:24px 0">
            <p style="color:#666;font-size:0.8rem">Need help? Contact us at <a href="mailto:support@cloudvape.ph" style="color:#8b5cf6">support@cloudvape.ph</a></p>
            <p style="color:#555;font-size:0.75rem;text-align:center;margin-top:16px">&copy; 2024 CloudVape. All rights reserved.</p>
          </div>
        </div>
        """
        mail.send(msg)
        app.logger.info("Order email sent to %s for order #%s (%s)", email, oid, status)
    except Exception as e:
        app.logger.error("send_order_email error: %s", e)



    """Build a plain dict from a Supabase order row."""
    return {
        "id": o["id"],
        "name": o.get("name", ""),
        "phone": o.get("phone", ""),
        "address": o.get("address", ""),
        "total": o.get("total", 0),
        "status": o.get("status", "Pending"),
        "created_at": str(o.get("created_at", ""))[:10],
        "order_items": items
    }


# --- SERVE STATIC FILES (local dev only, Vercel handles this via CDN) ---
@app.route("/static/<path:filename>")
def static_files(filename):
    static_dir = os.path.join(BASE_DIR, "static")
    try:
        safe_path = safe_join(static_dir, filename)
    except Exception:
        abort(404)
    if not os.path.isfile(safe_path):
        abort(404)
    directory = os.path.dirname(safe_path)
    file = os.path.basename(safe_path)
    return send_from_directory(directory, file)


# --- HOME ---
@app.route("/")
def home():
    if is_admin():
        return redirect(url_for("admin"))
    products = supabase.table("products").select("*").limit(6).execute().data or []
    return render_template("home.html", products=products, user=current_user(), cart_count=cart_count(), product_image=product_image)


# --- PRODUCT DETAIL ---
@app.route("/product/<int:pid>")
def product_detail(pid):
    if is_admin():
        return redirect(url_for("admin"))
    product = get_product(pid)
    reviews = []
    try:
        reviews = supabase.table("reviews").select("*").eq("product_id", pid).order("id", desc=True).execute().data or []
        for r in reviews:
            r["created_at"] = str(r.get("created_at", ""))[:10]
    except Exception:
        pass
    return render_template("product_detail.html", product=product, reviews=reviews, user=current_user(), cart_count=cart_count(), product_image=product_image)


# --- SUBMIT REVIEW ---
@app.route("/review/<int:pid>", methods=["POST"])
def submit_review(pid):
    if not current_user():
        return redirect(url_for("login"))
    u = current_user()
    p = get_product(pid)
    try:
        rating = int(request.form.get("rating", 5))
        comment = request.form.get("comment", "").strip()
        if comment:
            supabase.table("reviews").insert({
                "user_id": u["id"],
                "product_id": pid,
                "username": u["username"],
                "product_name": p["name"] if p else "",
                "rating": rating,
                "comment": comment
            }).execute()
            flash("Review submitted!", "success")
    except Exception as e:
        flash(f"Error submitting review: {e}", "danger")
    return redirect(url_for("product_detail", pid=pid))


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
        fullname = request.form["fullname"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]
        existing = supabase.table("users").select("id").or_(
            f"username.eq.{username},email.eq.{email}"
        ).execute().data
        if existing:
            flash("Username or email already taken.", "danger")
        else:
            code = str(random.randint(100000, 999999))
            session["pending_user"] = {"username": username, "fullname": fullname, "email": email, "password": password, "phone": request.form.get("phone", "").strip(), "address": request.form.get("address", "").strip()}
            session["verify_code"] = code
            try:
                msg = Message("Your Verification Code - CloudVape", recipients=[email])
                msg.html = f"""
                <div style="font-family:Segoe UI,sans-serif;max-width:500px;margin:auto;background:#0f0f1a;color:#e0e0e0;border-radius:16px;overflow:hidden">
                  <div style="background:linear-gradient(135deg,#8b5cf6,#ec4899);padding:30px;text-align:center">
                    <h1 style="color:#fff;margin:0;font-size:1.8rem">&#9729; CloudVape</h1>
                  </div>
                  <div style="padding:40px">
                    <p style="font-size:1rem">Hi <strong>{username}</strong>,</p>
                    <p style="color:#aaa">Thank you for registering at <strong>CloudVape</strong>! Use the code below to verify your email:</p>
                    <div style="background:rgba(139,92,246,0.15);border:2px solid #8b5cf6;border-radius:12px;padding:24px;text-align:center;margin:24px 0">
                      <p style="color:#aaa;margin:0 0 8px;font-size:0.85rem">YOUR VERIFICATION CODE</p>
                      <h2 style="color:#8b5cf6;font-size:2.5rem;letter-spacing:8px;margin:0">{code}</h2>
                    </div>
                    <p style="color:#aaa;font-size:0.9rem">&#8987; This code expires in <strong style="color:#fff">10 minutes</strong>.</p>
                    <hr style="border-color:rgba(139,92,246,0.2);margin:24px 0">
                    <p style="color:#666;font-size:0.85rem">&#128274; <strong>Never share this code</strong> with anyone. CloudVape will never ask for your verification code.</p>
                    <p style="color:#666;font-size:0.85rem">If you did not register, please ignore this email.</p>
                    <hr style="border-color:rgba(139,92,246,0.2);margin:24px 0">
                    <p style="color:#666;font-size:0.8rem">Need help? Contact us at <a href="mailto:support@cloudvape.ph" style="color:#8b5cf6">support@cloudvape.ph</a></p>
                    <p style="color:#555;font-size:0.75rem;text-align:center;margin-top:16px">&copy; 2024 CloudVape. All rights reserved.</p>
                  </div>
                </div>
                """
                mail.send(msg)
                flash("Verification code sent to your email!", "success")
                return redirect(url_for("verify_email"))
            except Exception as e:
                app.logger.error("Mail error: %s", e)
                flash("Failed to send verification email. Please try again.", "danger")
    return render_template("register.html", user=None, cart_count=0)


# --- VERIFY EMAIL ---
@app.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    if "pending_user" not in session:
        return redirect(url_for("register"))
    if request.method == "POST":
        entered = request.form.get("code", "").strip()
        if entered == session.get("verify_code"):
            u = session.pop("pending_user")
            session.pop("verify_code", None)
            supabase.table("users").insert({
                "username": u["username"],
                "fullname": u.get("fullname", ""),
                "email": u["email"],
                "password": u["password"],
                "phone": u.get("phone", ""),
                "address": u.get("address", ""),
                "role": "customer"
            }).execute()
            flash("Email verified! You can now login.", "success")
            return redirect(url_for("login"))
        else:
            flash("Invalid verification code. Please try again.", "danger")
    return render_template("verify_email.html", user=None, cart_count=0)


# --- FORGOT PASSWORD ---
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"].strip()
        user = supabase.table("users").select("id,username,email").eq("email", email).execute().data
        if user:
            code = str(random.randint(100000, 999999))
            session["reset_code"] = code
            session["reset_email"] = email
            try:
                msg = Message("Password Reset Code - CloudVape", recipients=[email])
                msg.html = f"""
                <div style="font-family:Segoe UI,sans-serif;max-width:500px;margin:auto;background:#0f0f1a;color:#e0e0e0;border-radius:16px;overflow:hidden">
                  <div style="background:linear-gradient(135deg,#8b5cf6,#ec4899);padding:30px;text-align:center">
                    <h1 style="color:#fff;margin:0;font-size:1.8rem">&#9729; CloudVape</h1>
                  </div>
                  <div style="padding:40px">
                    <p>Hi <strong>{user[0]['username']}</strong>,</p>
                    <p style="color:#aaa">We received a request to reset your password. Use the code below:</p>
                    <div style="background:rgba(139,92,246,0.15);border:2px solid #8b5cf6;border-radius:12px;padding:24px;text-align:center;margin:24px 0">
                      <p style="color:#aaa;margin:0 0 8px;font-size:0.85rem">PASSWORD RESET CODE</p>
                      <h2 style="color:#8b5cf6;font-size:2.5rem;letter-spacing:8px;margin:0">{code}</h2>
                    </div>
                    <p style="color:#aaa;font-size:0.9rem">&#8987; This code expires in <strong style="color:#fff">10 minutes</strong>.</p>
                    <hr style="border-color:rgba(139,92,246,0.2);margin:24px 0">
                    <p style="color:#666;font-size:0.85rem">&#128274; If you did not request a password reset, please ignore this email.</p>
                    <p style="color:#666;font-size:0.8rem">Need help? Contact us at <a href="mailto:support@cloudvape.ph" style="color:#8b5cf6">support@cloudvape.ph</a></p>
                    <p style="color:#555;font-size:0.75rem;text-align:center;margin-top:16px">&copy; 2024 CloudVape. All rights reserved.</p>
                  </div>
                </div>
                """
                mail.send(msg)
                flash("Reset code sent to your email!", "success")
                return redirect(url_for("reset_password"))
            except Exception as e:
                app.logger.error("Forgot password mail error: %s", e)
                flash("Failed to send reset email. Please try again.", "danger")
        else:
            flash("No account found with that email.", "danger")
    return render_template("forgot_password.html", user=None, cart_count=0)


# --- RESET PASSWORD ---
@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if "reset_email" not in session:
        return redirect(url_for("forgot_password"))
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if code != session.get("reset_code"):
            flash("Invalid reset code. Please try again.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
        else:
            email = session.pop("reset_email")
            session.pop("reset_code", None)
            supabase.table("users").update({"password": password}).eq("email", email).execute()
            flash("Password reset successfully! Please login.", "success")
            return redirect(url_for("login"))
    return render_template("reset_password.html", user=None, cart_count=0)


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
    elif key in cart:
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
    u = current_user()
    # Auto-fill from last order if user has no saved phone/address
    if not u.get("phone") and not u.get("address"):
        try:
            last = supabase.table("orders").select("name,phone,address").eq("user_id", u["id"]).order("id", desc=True).limit(1).execute().data
            if last:
                u["phone"] = u.get("phone") or last[0].get("phone", "")
                u["address"] = u.get("address") or last[0].get("address", "")
                u["name"] = u.get("name") or last[0].get("name", "")
        except Exception:
            pass
    items = []
    for pid, v in cart.items():
        p = get_product(int(pid))
        if p:
            items.append({"product": p, "qty": v["qty"], "subtotal": v["qty"] * p["price"]})
    total = sum(i["subtotal"] for i in items)
    if request.method == "POST":
        u = current_user()
        try:
            order_payload = {
                "user_id": u["id"],
                "name": request.form["name"],
                "address": request.form["address"],
                "phone": request.form["phone"],
                "total": float(total),
                "status": "Pending",
                "payment": request.form.get("payment", "cod"),
                "gcash_ref": ""
            }
            if request.form.get("payment") == "gcash":
                receipt_file = request.files.get("gcash_receipt")
                receipt_url = save_image(receipt_file) if receipt_file and receipt_file.filename else ""
                order_payload["gcash_ref"] = receipt_url
            if "username" in u:
                order_payload["username"] = u["username"]
            order_res = supabase.table("orders").insert(order_payload).execute()
            if not order_res.data:
                raise ValueError("Failed to create order — check Supabase RLS policies")
            order = order_res.data[0]
            supabase.table("order_items").insert([
                {
                    "order_id": order["id"],
                    "product_id": i["product"]["id"],
                    "product_name": i["product"]["name"],
                    "qty": int(i["qty"]),
                    "subtotal": float(i["subtotal"])
                }
                for i in items
            ]).execute()
            for i in items:
                new_stock = max(0, int(i["product"]["stock"]) - int(i["qty"]))
                supabase.table("products").update({"stock": new_stock}).eq("id", i["product"]["id"]).execute()
            session["cart"] = {}
            flash(f"Order #{order['id']} placed successfully!", "success")
            return redirect(url_for("order_success", oid=order["id"]))
        except Exception as e:
            import traceback
            app.logger.error("Checkout error: %s\n%s", e, traceback.format_exc())
            flash(f"Error placing order: {e}", "danger")
    return render_template("checkout.html", items=items, total=total, user=u, cart_count=cart_count(), product_image=product_image)


# --- MY ORDERS ---
@app.route("/orders")
def my_orders():
    if is_admin():
        return redirect(url_for("admin"))
    if not current_user():
        return redirect(url_for("login"))
    u = current_user()
    orders = []
    try:
        raw = supabase.table("orders").select("*").eq("user_id", u["id"]).order("id", desc=True).execute().data or []
        for o in raw:
            raw_items = supabase.table("order_items").select("*").eq("order_id", o["id"]).execute().data or []
            items = [
                {
                    "product_name": i.get("product_name", ""),
                    "qty": i.get("qty", 0),
                    "subtotal": i.get("subtotal", 0)
                }
                for i in raw_items
            ]
            orders.append({
                "id": o.get("id", ""),
                "name": o.get("name", ""),
                "phone": o.get("phone", ""),
                "address": o.get("address", ""),
                "total": o.get("total", 0),
                "status": o.get("status", "Pending"),
                "created_at": str(o.get("created_at", ""))[:10],
                "order_items": items
            })
    except Exception as e:
        import traceback
        app.logger.error("my_orders error: %s\n%s", e, traceback.format_exc())
        flash(f"Error loading orders: {e}", "danger")
    return render_template("my_orders.html", orders=orders, user=u, cart_count=cart_count())


# --- ORDER SUCCESS ---
@app.route("/order/<int:oid>")
def order_success(oid):
    order = None
    try:
        res = supabase.table("orders").select("*").eq("id", oid).single().execute()
        if res.data:
            raw_items = supabase.table("order_items").select("*").eq("order_id", oid).execute().data or []
            order = build_order(res.data, [
                {"product_name": i["product_name"], "qty": i["qty"], "subtotal": i["subtotal"]}
                for i in raw_items
            ])
    except Exception as e:
        app.logger.error("order_success error: %s", e)
    return render_template("order_success.html", order=order, user=current_user(), cart_count=cart_count())


# --- ADMIN PANEL ---
@app.route("/admin")
def admin():
    if not is_admin():
        return redirect(url_for("home"))
    products = supabase.table("products").select("*").execute().data or []
    orders_raw = supabase.table("orders").select("*").order("id", desc=True).execute().data or []
    orders = []
    for o in orders_raw:
        raw_items = supabase.table("order_items").select("product_name,qty,product_id").eq("order_id", o["id"]).execute().data or []
        for item in raw_items:
            p = get_product(item["product_id"])
            item["image"] = product_image(p) if p else ""
        o["order_items"] = raw_items
        orders.append(o)
    users = supabase.table("users").select("*").execute().data or []

    # Sales by date
    sales_by_date = {}
    for o in orders:
        date = str(o.get("created_at", ""))[:10]
        sales_by_date[date] = sales_by_date.get(date, 0) + float(o.get("total", 0))
    sales_dates = sorted(sales_by_date.keys())
    sales_totals = [sales_by_date[d] for d in sales_dates]

    # Sales by status
    status_counts = {"Pending": 0, "Shipped": 0, "Delivered": 0}
    for o in orders:
        s = o.get("status", "Pending")
        if s in status_counts:
            status_counts[s] += 1

    return render_template("admin.html", products=products, orders=orders, users=users,
        user=current_user(), cart_count=cart_count(), product_image=product_image,
        sales_dates=sales_dates, sales_totals=sales_totals, status_counts=status_counts)


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
                raise ValueError("Invalid price")
        except (ValueError, TypeError):
            flash("Invalid numeric values provided.", "danger")
            return render_template("admin_form.html", item=None, user=current_user(), cart_count=cart_count())
        image_filename = save_image(request.files.get("image"))
        if request.files.get("image") and request.files["image"].filename and not image_filename:
            flash("Image upload failed — product saved without image.", "warning")
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
                raise ValueError("Invalid price")
        except (ValueError, TypeError):
            flash("Invalid numeric values provided.", "danger")
            return render_template("admin_form.html", item=p, user=current_user(), cart_count=cart_count())
        image_filename = p.get("image", "")
        new_file = save_image(request.files.get("image"))
        if request.files.get("image") and request.files["image"].filename and not new_file:
            flash("Image upload failed — product saved without new image.", "warning")
        if new_file:
            delete_image(image_filename)
            image_filename = new_file
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
    if p:
        delete_image(p.get("image", ""))
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
    if status in ("Shipped", "Delivered"):
        try:
            order = supabase.table("orders").select("*").eq("id", oid).single().execute().data
            if order:
                send_order_email(order, status)
        except Exception as e:
            app.logger.error("update_order email error: %s", e)
    flash(f"Order #{oid} marked as {status}.", "success")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")

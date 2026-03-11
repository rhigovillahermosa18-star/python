from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__, template_folder="../templates")
app.secret_key = "secret123"

inventory = []
next_id = 1

# simple login credentials
USERNAME = "admin"
PASSWORD = "1234"


# LOGIN PAGE
@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        if username == USERNAME and password == PASSWORD:
            session["user"] = username
            return redirect(url_for("index"))
        else:
            return render_template("login.html", error="Invalid Login")

    return render_template("login.html")


# LOGOUT
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


# HOME PAGE
@app.route("/")
def index():

    if "user" not in session:
        return redirect(url_for("login"))

    total = sum(float(item["price"]) for item in inventory)
    return render_template("index.html", items=inventory, total=total)


# ADD
@app.route("/add", methods=["GET","POST"])
def add():

    if "user" not in session:
        return redirect(url_for("login"))

    global next_id

    if request.method == "POST":
        item = {
            "id": next_id,
            "name": request.form["name"],
            "flavor": request.form["flavor"],
            "nicotine": request.form["nicotine"],
            "size": request.form["size"],
            "price": request.form["price"]
        }

        inventory.append(item)
        next_id += 1

        return redirect(url_for("index"))

    return render_template("add.html")


# DELETE
@app.route("/delete/<int:id>")
def delete(id):

    if "user" not in session:
        return redirect(url_for("login"))

    global inventory
    inventory = [item for item in inventory if item["id"] != id]

    return redirect(url_for("index"))


# EDIT
@app.route("/edit/<int:id>", methods=["GET","POST"])
def edit(id):

    if "user" not in session:
        return redirect(url_for("login"))

    item = next((x for x in inventory if x["id"] == id), None)

    if request.method == "POST":
        item["name"] = request.form["name"]
        item["flavor"] = request.form["flavor"]
        item["nicotine"] = request.form["nicotine"]
        item["size"] = request.form["size"]
        item["price"] = request.form["price"]

        return redirect(url_for("index"))

    return render_template("edit.html", item=item)
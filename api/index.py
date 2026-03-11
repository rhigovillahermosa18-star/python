from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# Temporary storage (no database)
inventory = []
next_id = 1


@app.route("/")
def index():
    total = sum(float(item["price"]) for item in inventory)
    return render_template("index.html", items=inventory, total=total)


@app.route("/add", methods=["GET","POST"])
def add():
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


@app.route("/delete/<int:id>")
def delete(id):
    global inventory
    inventory = [item for item in inventory if item["id"] != id]
    return redirect(url_for("index"))


@app.route("/edit/<int:id>", methods=["GET","POST"])
def edit(id):
    item = next((x for x in inventory if x["id"] == id), None)

    if request.method == "POST":
        item["name"] = request.form["name"]
        item["flavor"] = request.form["flavor"]
        item["nicotine"] = request.form["nicotine"]
        item["size"] = request.form["size"]
        item["price"] = request.form["price"]

        return redirect(url_for("index"))

    return render_template("edit.html", item=item)


if __name__ == "__main__":
    app.run(debug=True)
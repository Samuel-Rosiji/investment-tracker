from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    request,
    session,
    flash,
    Response,
)
import sqlite3
import csv
from io import StringIO

import yfinance as yf
from werkzeug.security import generate_password_hash, check_password_hash

from models import init_db  # assumes models.py has init_db()

# ---------------------------------------------------------
# App configuration
# ---------------------------------------------------------

app = Flask(__name__)
app.secret_key = "supersecretkey"  # change for production


# ---------------------------------------------------------
# Database helper
# ---------------------------------------------------------

def get_db():
    conn = sqlite3.connect("investment.db")
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------
# Routes: Auth & Home
# ---------------------------------------------------------

@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password_raw = request.form["password"]

        if not username or not password_raw:
            flash("Username and password are required.", "danger")
            return redirect(url_for("register"))

        password = generate_password_hash(password_raw)

        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users(username, password) VALUES (?, ?)",
                (username, password),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            flash("Username already taken.", "danger")
            conn.close()
            return redirect(url_for("register"))

        conn.close()
        flash("Account created! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials!", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------
# Routes: Investments CRUD
# ---------------------------------------------------------

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    investments = conn.execute(
        "SELECT * FROM investments WHERE user_id = ?",
        (session["user_id"],),
    ).fetchall()
    conn.close()

    total_value = 0.0
    total_cost = 0.0
    updated_investments = []

    # Calculate live prices and P/L
    for inv in investments:
        try:
            ticker = yf.Ticker(inv["symbol"])
            hist = ticker.history(period="1d")
            if not hist.empty:
                live_price = float(hist["Close"].iloc[-1])
            else:
                live_price = 0.0
        except Exception:
            live_price = 0.0

        quantity = float(inv["quantity"])
        buy_price = float(inv["buy_price"])

        current_value = quantity * live_price
        cost = quantity * buy_price

        total_value += current_value
        total_cost += cost

        updated_investments.append(
            {
                "id": inv["id"],
                "symbol": inv["symbol"],
                "category": inv["category"],
                "quantity": quantity,
                "buy_price": buy_price,
                "current_price": round(live_price, 2),
                "value": round(current_value, 2),
                "profit_loss": round(current_value - cost, 2),
            }
        )

    profit_loss = total_value - total_cost

    # Asset allocation by category (for pie chart)
    from collections import defaultdict

    category_totals = defaultdict(float)
    for inv in updated_investments:
        category_totals[inv["category"]] += inv["value"]

    category_labels = list(category_totals.keys())
    category_values = list(category_totals.values())

    return render_template(
        "dashboard.html",
        investments=updated_investments,
        total_value=round(total_value, 2),
        total_cost=round(total_cost, 2),
        profit_loss=round(profit_loss, 2),
        category_labels=category_labels,
        category_values=category_values,
    )


@app.route("/add_investment", methods=["GET", "POST"])
def add_investment():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        symbol = request.form["symbol"].strip().upper()
        category = request.form["category"].strip()
        quantity = float(request.form["quantity"])
        buy_price = float(request.form["buy_price"])

        conn = get_db()
        conn.execute(
            """
            INSERT INTO investments (user_id, symbol, category, quantity, buy_price)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session["user_id"], symbol, category, quantity, buy_price),
        )
        conn.commit()
        conn.close()

        flash("Investment added!", "success")
        return redirect(url_for("dashboard"))

    return render_template("add_investment.html")


@app.route("/edit_investment/<int:id>", methods=["GET", "POST"])
def edit_investment(id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    investment = conn.execute(
        "SELECT * FROM investments WHERE id = ? AND user_id = ?",
        (id, session["user_id"]),
    ).fetchone()

    if not investment:
        conn.close()
        flash("Investment not found.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        quantity = float(request.form["quantity"])
        buy_price = float(request.form["buy_price"])

        conn.execute(
            "UPDATE investments SET quantity = ?, buy_price = ? WHERE id = ?",
            (quantity, buy_price, id),
        )
        conn.commit()
        conn.close()
        flash("Investment updated!", "success")
        return redirect(url_for("dashboard"))

    conn.close()
    return render_template("edit_investment.html", investment=investment)


@app.route("/delete_investment/<int:id>", methods=["POST"])
def delete_investment(id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute(
        "DELETE FROM investments WHERE id = ? AND user_id = ?",
        (id, session["user_id"]),
    )
    conn.commit()
    conn.close()

    flash("Investment deleted.", "success")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------
# Routes: CSV Export / Import
# ---------------------------------------------------------

@app.route("/export_csv")
def export_csv():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    rows = conn.execute(
        "SELECT symbol, category, quantity, buy_price FROM investments WHERE user_id = ?",
        (session["user_id"],),
    ).fetchall()
    conn.close()

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(["symbol", "category", "quantity", "buy_price"])
    for r in rows:
        writer.writerow(
            [r["symbol"], r["category"], r["quantity"], r["buy_price"]]
        )

    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=portfolio.csv"},
    )


@app.route("/import_csv", methods=["POST"])
def import_csv():
    if "user_id" not in session:
        return redirect(url_for("login"))

    file = request.files.get("file")
    if not file:
        flash("No file selected.", "danger")
        return redirect(url_for("dashboard"))

    stream = StringIO(file.stream.read().decode("utf-8"))
    reader = csv.DictReader(stream)

    conn = get_db()
    for row in reader:
        if not row.get("symbol"):
            continue
        conn.execute(
            """
            INSERT INTO investments (user_id, symbol, category, quantity, buy_price)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                row["symbol"].strip().upper(),
                row["category"].strip() if row.get("category") else "",
                float(row["quantity"]),
                float(row["buy_price"]),
            ),
        )
    conn.commit()
    conn.close()

    flash("CSV imported successfully!", "success")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------
# Routes: Historical price chart
# ---------------------------------------------------------

@app.route("/history/<symbol>")
def history(symbol):
    if "user_id" not in session:
        return redirect(url_for("login"))

    symbol = symbol.upper()
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="6mo")  # 6 months

    dates = [d.strftime("%Y-%m-%d") for d in hist.index]
    prices = hist["Close"].round(2).tolist()

    return render_template(
        "history.html",
        symbol=symbol,
        dates=dates,
        prices=prices,
    )


# ---------------------------------------------------------
# Run app
# ---------------------------------------------------------

if __name__ == "__main__":
    init_db()  # ensure DB & tables exist
    app.run()

import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    stocks = db.execute("SELECT symbol, SUM(shares) as total_shares FROM purchases WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0",
                        user_id = session["user_id"])

    cash = db.execute("SELECT cash FROM users WHERE id = :user_id",
                        user_id = session["user_id"])

    cash = cash[0]["cash"]
    sum_price = 0

    for d in stocks:
        quote = lookup(d["symbol"])
        name = quote["name"]
        price = quote["price"]
        total = d["total_shares"] * price

        sum_price = sum_price + total

        d.update({"name": name, "price": price, "total": round(total, 2)})

    total_price = sum_price + cash

    return render_template("index.html", stocks=stocks, cash=round(cash, 2), total_price=round(total_price, 2))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":

        # Query database for user´s cash
        rows = db.execute("SELECT cash FROM users WHERE id = :user_id",
                          user_id=session["user_id"])

        # Get information about selected symbol
        results = lookup(request.form.get("symbol"))

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)

        # Ensure symbol exists
        elif not results:
            return apology("symbol does not exist", 400)

        # Ensure shares was submitted
        elif not request.form.get("shares"):
            return apology("must provide shares", 400)

        # Ensure shares is positive integer
        elif not request.form.get("shares").isdigit() or int(request.form.get("shares")) <= 0:
            return apology("must provide positive number", 400)

        # Check if cash is sufficient for the purchase
        if rows[0]["cash"] < (int(request.form.get("shares")) * results["price"]):
            return apology("not enough cash for this number of shares at the current price", 400)

        # Insert purchase into the database
        db.execute("INSERT INTO purchases (user_id, symbol, shares, price, transaction_type) VALUES (:user_id, :symbol, :shares, :price, :transaction)",
                    user_id=session["user_id"], symbol=request.form.get("symbol"), shares=int(request.form.get("shares")), price=results["price"], transaction="buy")

        # Update cash in the users database
        db.execute("UPDATE users SET cash = :cash WHERE id = :user_id",
                   cash = rows[0]["cash"] - (int(request.form.get("shares")) * results["price"]), user_id=session["user_id"])

        flash("Bought!")

        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""

    username = request.args.get("username", "")
    users = db.execute("SELECT * FROM users WHERE username = :username",
                       username=username)

    if not username and users:
        return jsonify(True)
    else:
        return jsonify(False)

    return jsonify(True)

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    stocks = db.execute("SELECT symbol, shares, price, transaction_type, DATE(timestamp) as date FROM purchases WHERE user_id = :user_id",
                        user_id = session["user_id"])

    for d in stocks:
        quote = lookup(d["symbol"])
        name = quote["name"]

        d.update({"name": name})

    return render_template("history.html", stocks=stocks)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "POST":

        # Get information about selected symbol
        results = lookup(request.form.get("symbol"))

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)

        # Ensure symbol exists
        elif not results:
            return apology("symbol does not exist", 400)

        # Redirect user to the results page
        return render_template("quoted.html", results=results)

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure password was confirmed
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 400)

        # Check if passwords match
        elif not request.form.get("password") == request.form.get("confirmation"):
            return apology("passwords do not match", 400)

        # Hash password to be stored in the database
        hashed_password = generate_password_hash(request.form.get("password"), method='pbkdf2:sha256', salt_length=len(request.form.get("password")))

        # Insert user into the database
        db.execute("INSERT INTO users (username,hash) VALUES (:username, :hash)",
                    username=request.form.get("username"), hash=hashed_password)

        flash('Account created', 'info')

        # Redirect user to the login page
        return redirect("/login")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":

        # Query database for user´s cash
        rows = db.execute("SELECT cash FROM users WHERE id = :user_id",
                          user_id=session["user_id"])

        # Query database for the number of shares for the selected symbol
        shares = db.execute("SELECT SUM(shares) as total_shares FROM purchases WHERE user_id = :user_id AND symbol = :symbol",
                            user_id=session["user_id"], symbol=request.form.get("symbol"))

        symbols = db.execute("SELECT DISTINCT symbol FROM purchases WHERE user_id = :user_id",
                            user_id=session["user_id"])

        stocks_owned = [d["symbol"] for d in symbols]

        # Get information about selected symbol
        results = lookup(request.form.get("symbol"))

        # Ensure symbol was selected
        if not request.form.get("symbol"):
            return apology("must select symbol", 400)

        # Ensure the user owns the stock
        elif not request.form.get("symbol") in stocks_owned:
            return apology("cannot sell stocks you do not own", 400)

        # Ensure password was submitted
        elif not request.form.get("shares"):
            return apology("must provide shares", 400)

        # Ensure shares is positive integer
        elif not request.form.get("shares").isdigit() or int(request.form.get("shares")) <= 0:
            return apology("must provide positive number", 400)

        # Ensure enough sells are present
        elif shares[0]["total_shares"] < int(request.form.get("shares")):
            return apology("not enough of the stock to sell", 400)

        # Insert sell into the database
        db.execute("INSERT INTO purchases (user_id, symbol, shares, price, transaction_type) VALUES (:user_id, :symbol, :shares, :price, :transaction)",
                    user_id=session["user_id"], symbol=request.form.get("symbol"), shares=-int(request.form.get("shares")), price=results["price"], transaction="sell")

        # Update cash in the users database
        db.execute("UPDATE users SET cash = :cash WHERE id = :user_id",
                   cash = rows[0]["cash"] + (int(request.form.get("shares")) * results["price"]), user_id=session["user_id"])

        flash("Sold!")

        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        query = db.execute("SELECT symbol FROM purchases WHERE user_id = :user_id", user_id = session["user_id"])

        stocks = [s["symbol"] for s in query if "symbol" in s]

        return render_template("sell.html", stocks=stocks)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

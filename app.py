import os
import copy

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
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
# Reconfigured for Heroku deployment
uri = os.getenv("DATABASE_URL")
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://")
db = SQL(uri)

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    trades = db.execute("SELECT symbol, name, SUM(totalprice) as totalPrice, SUM(quantity) as totalQuantity FROM trades WHERE user_id=? GROUP BY symbol", session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])[0]
    
    total = 0
    for trade in trades:
        trade['currentPrice'] = lookup(trade['symbol'])['price']
        total += trade['totalPrice']

    return render_template('index.html', trades=trades, total=total, cash=cash)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        # Return error if symbol doesn't exist
        if not request.form.get('symbol'):
            return apology("must provide valid symbol", 403)
        
        # Return error if quantity is fractional or negative
        quantity = float(request.form.get('quantity'))
        if not (int(quantity) == quantity and quantity > 0):
            return apology("must provide positive integer quantity", 403)
        
        # quote is a dictionary with 'name', 'price', 'symbol' keys
        quote = lookup(request.form.get("symbol"))
        if quote == None:
            return apology("must provide valid symbol", 403)
            
        cash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])[0]['cash']
        price = round(quote['price'], 2)
        if cash < price*quantity:
            return apology("not enough money", 403)
        
        # Create a new row in table trades where positive values mean buy
        db.execute("INSERT INTO trades (user_id, symbol, name, price, quantity, totalprice, time) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", \
            session['user_id'], quote['symbol'], quote['name'], price, quantity, price*quantity
        )
        # SUBTRACT cash from account
        db.execute("UPDATE users SET cash=? WHERE id=?", cash - price*quantity, session["user_id"])
        
        # Flash message indicating sucessful buy
        flash(f"Buy of {quantity} {quote['symbol']} completed! (${price*quantity})")
        return redirect('/')
            
    else:    
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    trades = db.execute("SELECT symbol, name, quantity, price, time FROM trades WHERE user_id=? ORDER BY time", session["user_id"])
    
    return render_template('history.html', trades=trades)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST) and pressed 'Log in'
    if request.method == "POST":
        # If 'Sign up' pressed
        if request.form.get('signup'):
            return redirect("/register")
        
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)
        
        if request.form.get('login'):
            # Query database for username
            rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
    
            # Ensure username exists and password is correct
            if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
                return apology("invalid username and/or password", 403)
    
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
    if request.method == 'POST':
        quote = lookup(request.form.get("symbol"))
        
        if quote == None:
            return apology('Unknown symbol')
            
        message = f"A share of {quote['name']} ({quote['symbol']}) costs {usd(quote['price'])}."
        "A share of AT&T, Inc. (T) costs $24.78."
        return render_template("quoted.html", message=message)

    else:
        return render_template("quote.html")
 

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == 'POST':
        username = request.form.get('username')
        
        # If username already exists in database
        if db.execute("SELECT 1 FROM users WHERE username = ?", username):
            return apology("username already taken", 403)
            
        # If no username
        if not request.form.get("username"):
            return apology("must provide username", 403)
            
        hsh = generate_password_hash(request.form.get('password'))
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, hsh)
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)
        session["user_id"] = rows[0]["id"]
        return redirect("/")
        
    else:
        return render_template("register.html")

       
@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        # Return error if symbol doesn't exist
        if not request.form.get('symbol'):
            return apology("must provide valid symbol", 403)
        
        # Return error if quantity is fractional or negative
        quantity = float(request.form.get('quantity'))
        if not (int(quantity) == quantity and quantity > 0):
            return apology("must provide positive integer quantity", 403)
        
        # quote is a dictionary with 'name', 'price', 'symbol' keys
        quote = lookup(request.form.get("symbol"))
        if quote == None:
            return apology("must provide valid symbol", 403)
            
        # Return error if quantity exceeds numbers of shares owned
        quantityOwned = db.execute("SELECT SUM(quantity) as total_quantity FROM trades WHERE user_id=? AND SYMBOL=?", session["user_id"], quote['symbol'])
        if quantity > quantityOwned[0]['total_quantity']:
            return apology("not enough shares", 403)
        
        cash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])[0]['cash']
        price = round(quote['price'], 2)
        
        # Create a new row in table trades where negative values mean sell
        db.execute("INSERT INTO trades (user_id, symbol, name, price, quantity, totalprice, time) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", \
            session['user_id'], quote['symbol'], quote['name'], -price, -quantity, -price*quantity
        )
        # ADD cash to account
        db.execute("UPDATE users SET cash=? WHERE id=?", cash + price*quantity, session["user_id"])
        
        # Flash message indicating sucessful sell
        flash(f"Sell of {quantity} {quote['symbol']} completed! (${price*quantity})")
        return redirect('/')
            
    else:
        # Get a list of dictionarys of {'symbol': 'ABC'}
        symbols = db.execute("SELECT symbol FROM trades WHERE user_id=? GROUP BY symbol", session["user_id"])
        return render_template('sell.html', symbols=symbols)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

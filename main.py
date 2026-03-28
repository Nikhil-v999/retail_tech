
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import datetime, timezone
import os
from flask_bootstrap import Bootstrap5

from forms import RegisterForm, LoginForm, AddProductForm

# -------------------- APP SETUP --------------------
load_dotenv()

app = Flask(__name__)
bootstrap = Bootstrap5(app)

app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "secret-key")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dealdrop1.db'

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# -------------------- MODELS --------------------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)         # customer / retailer
    city = db.Column(db.String(100), nullable=True)         # for hyperlocal matching
    products = db.relationship('Product', backref='retailer', lazy=True)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    category = db.Column(db.String(100), nullable=True)
    original_price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)
    expiry_date = db.Column(db.DateTime, nullable=False)    # when the deal expires
    deal_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    retailer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    @property
    def current_price(self):
        """
        Dynamic pricing logic:
        - If > 24 hours left  → 10% off
        - If 12-24 hours left → 25% off
        - If 6-12 hours left  → 40% off
        - If < 6 hours left   → 60% off
        """
        now = datetime.now(timezone.utc)
        expiry = self.expiry_date
        # make expiry timezone-aware if it isn't
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)

        hours_left = (expiry - now).total_seconds() / 3600

        if hours_left > 24:
            discount = 0.10
        elif hours_left > 12:
            discount = 0.25
        elif hours_left > 6:
            discount = 0.40
        else:
            discount = 0.60

        return round(self.original_price * (1 - discount), 2)

    @property
    def discount_percent(self):
        now = datetime.now(timezone.utc)
        expiry = self.expiry_date
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        hours_left = (expiry - now).total_seconds() / 3600
        if hours_left > 24:
            return 10
        elif hours_left > 12:
            return 25
        elif hours_left > 6:
            return 40
        else:
            return 60

    @property
    def hours_left(self):
        now = datetime.now(timezone.utc)
        expiry = self.expiry_date
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        delta = expiry - now
        return max(0, delta.total_seconds() / 3600)

    @property
    def is_expired(self):
        return self.hours_left <= 0

    @property
    def urgency_level(self):
        h = self.hours_left
        if h > 24:
            return "low"
        elif h > 12:
            return "medium"
        elif h > 6:
            return "high"
        else:
            return "critical"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# -------------------- DB INIT --------------------
with app.app_context():
    db.create_all()


# -------------------- ROUTES --------------------

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    role = request.args.get("role")
    if role not in ["customer", "retailer"]:
        return redirect(url_for("home"))
    form = RegisterForm()

    if form.validate_on_submit():
        existing_user = User.query.filter_by(email=form.email.data).first()
        if existing_user:
            flash("Account already exists. Please login.", "warning")
            return redirect(url_for("login"))

        hashed_pw = generate_password_hash(form.password.data)
        new_user = User(
            email=form.email.data,
            name=form.name.data,
            password=hashed_pw,
            role=role,
            city=form.city.data if hasattr(form, 'city') else None
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)

        if new_user.role == "retailer":
            return redirect(url_for("retailer_dashboard"))
        else:
            return redirect(url_for("customer_dashboard"))

    return render_template("register.html", form=form, role=role)


@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()

    if form.validate_on_submit():
        result = db.session.execute(db.select(User).where(User.email == form.email.data))
        user = result.scalar()

        if not user:
            flash("That email does not exist. Please try again.", "warning")
            return redirect(url_for('login'))
        elif not check_password_hash(user.password, form.password.data):
            flash("Password incorrect. Please try again.", "danger")
            return redirect(url_for('login'))
        else:
            login_user(user)
            if user.role == "retailer":
                return redirect(url_for("retailer_dashboard"))
            else:
                return redirect(url_for("customer_dashboard"))

    return render_template("login.html", form=form)


# -------------------- RETAILER DASHBOARD --------------------

@app.route("/retailer_dashboard")
@login_required
def retailer_dashboard():
    if current_user.role != "retailer":
        return redirect(url_for("home"))

    products = Product.query.filter_by(retailer_id=current_user.id).all()

    # Stats
    total_products = len(products)
    active_deals = sum(1 for p in products if p.deal_active and not p.is_expired)
    low_stock = sum(1 for p in products if p.stock <= 5 and not p.is_expired)
    total_stock = sum(p.stock for p in products)

    return render_template(
        "retail_dash.html",
        products=products,
        total_products=total_products,
        active_deals=active_deals,
        low_stock=low_stock,
        total_stock=total_stock
    )


@app.route("/add_product", methods=["GET", "POST"])
@login_required
def add_product():
    if current_user.role != "retailer":
        return redirect(url_for("home"))

    form = AddProductForm()
    if form.validate_on_submit():
        product = Product(
            name=form.name.data,
            description=form.description.data,
            category=form.category.data,
            original_price=form.original_price.data,
            stock=form.stock.data,
            expiry_date=form.expiry_date.data,
            deal_active=True,
            retailer_id=current_user.id
        )
        db.session.add(product)
        db.session.commit()
        flash("Product added successfully! Deal is now live.", "success")
        return redirect(url_for("retailer_dashboard"))

    return render_template("add_product.html", form=form)


@app.route("/toggle_deal/<int:product_id>")
@login_required
def toggle_deal(product_id):
    product = db.session.get(Product, product_id)
    if not product or product.retailer_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for("retailer_dashboard"))
    product.deal_active = not product.deal_active
    db.session.commit()
    flash(f"Deal {'activated' if product.deal_active else 'paused'}.", "success")
    return redirect(url_for("retailer_dashboard"))


@app.route("/delete_product/<int:product_id>")
@login_required
def delete_product(product_id):
    product = db.session.get(Product, product_id)
    if not product or product.retailer_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for("retailer_dashboard"))
    db.session.delete(product)
    db.session.commit()
    flash("Product deleted.", "info")
    return redirect(url_for("retailer_dashboard"))


@app.route("/update_stock/<int:product_id>", methods=["POST"])
@login_required
def update_stock(product_id):
    product = db.session.get(Product, product_id)
    if not product or product.retailer_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
    new_stock = request.form.get("stock", type=int)
    if new_stock is not None and new_stock >= 0:
        product.stock = new_stock
        db.session.commit()
        flash("Stock updated.", "success")
    return redirect(url_for("retailer_dashboard"))


# -------------------- CUSTOMER DASHBOARD --------------------

@app.route("/customer_dashboard")
@login_required
def customer_dashboard():
    if current_user.role != "customer":
        return redirect(url_for("home"))

    # Show all active, non-expired deals (in real app: filter by location)
    now = datetime.now(timezone.utc)
    products = Product.query.filter(
        Product.deal_active == True,
        Product.expiry_date > now,
        Product.stock > 0
    ).order_by(Product.expiry_date.asc()).all()  # most urgent first

    return render_template("cust_dash.html", products=products)


@app.route("/grab_deal/<int:product_id>", methods=["POST"])
@login_required
def grab_deal(product_id):
    if current_user.role != "customer":
        return redirect(url_for("home"))

    product = db.session.get(Product, product_id)
    if not product or product.stock <= 0 or product.is_expired or not product.deal_active:
        flash("Sorry, this deal is no longer available!", "danger")
        return redirect(url_for("customer_dashboard"))

    product.stock -= 1
    if product.stock == 0:
        product.deal_active = False
    db.session.commit()
    flash(f"🎉 Deal grabbed! You got {product.name} for ₹{product.current_price}!", "success")
    return redirect(url_for("customer_dashboard"))


# -------------------- API: Live Price --------------------
@app.route("/api/price/<int:product_id>")
def get_live_price(product_id):
    """Called by JS every 60s to refresh dynamic price"""
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({"error": "Not found"}), 404
    return jsonify({
        "current_price": product.current_price,
        "discount_percent": product.discount_percent,
        "hours_left": round(product.hours_left, 2),
        "urgency": product.urgency_level,
        "stock": product.stock
    })


# -------------------- LOGOUT --------------------
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))


# -------------------- RUN --------------------
if __name__ == "__main__":
    app.run(debug=True)

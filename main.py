#
# from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
# from flask_sqlalchemy import SQLAlchemy
# from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
# from werkzeug.security import generate_password_hash, check_password_hash
# from dotenv import load_dotenv
# from datetime import datetime, timezone
# import os
# from flask_bootstrap import Bootstrap5
#
# from forms import RegisterForm, LoginForm, AddProductForm
#
# # -------------------- APP SETUP --------------------
# load_dotenv()
#
# app = Flask(__name__)
# bootstrap = Bootstrap5(app)
#
# app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "secret-key")
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dealdrop1.db'
#
# db = SQLAlchemy(app)
#
# login_manager = LoginManager()
# login_manager.init_app(app)
# login_manager.login_view = "login"
#
#
# # -------------------- MODELS --------------------
#
# class User(UserMixin, db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     email = db.Column(db.String(100), unique=True, nullable=False)
#     password = db.Column(db.String(200), nullable=False)
#     name = db.Column(db.String(100), nullable=False)
#     role = db.Column(db.String(20), nullable=False)         # customer / retailer
#     city = db.Column(db.String(100), nullable=True)         # for hyperlocal matching
#     products = db.relationship('Product', backref='retailer', lazy=True)
#
#
# class Product(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(200), nullable=False)
#     description = db.Column(db.String(500), nullable=True)
#     category = db.Column(db.String(100), nullable=True)
#     original_price = db.Column(db.Float, nullable=False)
#     stock = db.Column(db.Integer, nullable=False)
#     expiry_date = db.Column(db.DateTime, nullable=False)    # when the deal expires
#     deal_active = db.Column(db.Boolean, default=True)
#     created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
#     retailer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#
#     @property
#     def current_price(self):
#         """
#         Dynamic pricing logic:
#         - If > 24 hours left  → 10% off
#         - If 12-24 hours left → 25% off
#         - If 6-12 hours left  → 40% off
#         - If < 6 hours left   → 60% off
#         """
#         now = datetime.now(timezone.utc)
#         expiry = self.expiry_date
#         # make expiry timezone-aware if it isn't
#         if expiry.tzinfo is None:
#             expiry = expiry.replace(tzinfo=timezone.utc)
#
#         hours_left = (expiry - now).total_seconds() / 3600
#
#         if hours_left > 24:
#             discount = 0.10
#         elif hours_left > 12:
#             discount = 0.25
#         elif hours_left > 6:
#             discount = 0.40
#         else:
#             discount = 0.60
#
#         return round(self.original_price * (1 - discount), 2)
#
#     @property
#     def discount_percent(self):
#         now = datetime.now(timezone.utc)
#         expiry = self.expiry_date
#         if expiry.tzinfo is None:
#             expiry = expiry.replace(tzinfo=timezone.utc)
#         hours_left = (expiry - now).total_seconds() / 3600
#         if hours_left > 24:
#             return 10
#         elif hours_left > 12:
#             return 25
#         elif hours_left > 6:
#             return 40
#         else:
#             return 60
#
#     @property
#     def hours_left(self):
#         now = datetime.now(timezone.utc)
#         expiry = self.expiry_date
#         if expiry.tzinfo is None:
#             expiry = expiry.replace(tzinfo=timezone.utc)
#         delta = expiry - now
#         return max(0, delta.total_seconds() / 3600)
#
#     @property
#     def is_expired(self):
#         return self.hours_left <= 0
#
#     @property
#     def urgency_level(self):
#         h = self.hours_left
#         if h > 24:
#             return "low"
#         elif h > 12:
#             return "medium"
#         elif h > 6:
#             return "high"
#         else:
#             return "critical"
#
#
# @login_manager.user_loader
# def load_user(user_id):
#     return db.session.get(User, int(user_id))
#
#
# # -------------------- DB INIT --------------------
# with app.app_context():
#     db.create_all()
#
#
# # -------------------- ROUTES --------------------
#
# @app.route("/")
# def home():
#     return render_template("index.html")
#
#
# @app.route("/register", methods=["GET", "POST"])
# def register():
#     role = request.args.get("role")
#     if role not in ["customer", "retailer"]:
#         return redirect(url_for("home"))
#     form = RegisterForm()
#
#     if form.validate_on_submit():
#         existing_user = User.query.filter_by(email=form.email.data).first()
#         if existing_user:
#             flash("Account already exists. Please login.", "warning")
#             return redirect(url_for("login"))
#
#         hashed_pw = generate_password_hash(form.password.data)
#         new_user = User(
#             email=form.email.data,
#             name=form.name.data,
#             password=hashed_pw,
#             role=role,
#             city=form.city.data if hasattr(form, 'city') else None
#         )
#         db.session.add(new_user)
#         db.session.commit()
#         login_user(new_user)
#
#         if new_user.role == "retailer":
#             return redirect(url_for("retailer_dashboard"))
#         else:
#             return redirect(url_for("customer_dashboard"))
#
#     return render_template("register.html", form=form, role=role)
#
#
# @app.route('/login', methods=["GET", "POST"])
# def login():
#     form = LoginForm()
#
#     if form.validate_on_submit():
#         result = db.session.execute(db.select(User).where(User.email == form.email.data))
#         user = result.scalar()
#
#         if not user:
#             flash("That email does not exist. Please try again.", "warning")
#             return redirect(url_for('login'))
#         elif not check_password_hash(user.password, form.password.data):
#             flash("Password incorrect. Please try again.", "danger")
#             return redirect(url_for('login'))
#         else:
#             login_user(user)
#             if user.role == "retailer":
#                 return redirect(url_for("retailer_dashboard"))
#             else:
#                 return redirect(url_for("customer_dashboard"))
#
#     return render_template("login.html", form=form)
#
#
# # -------------------- RETAILER DASHBOARD --------------------
#
# @app.route("/retailer_dashboard")
# @login_required
# def retailer_dashboard():
#     if current_user.role != "retailer":
#         return redirect(url_for("home"))
#
#     products = Product.query.filter_by(retailer_id=current_user.id).all()
#
#     # Stats
#     total_products = len(products)
#     active_deals = sum(1 for p in products if p.deal_active and not p.is_expired)
#     low_stock = sum(1 for p in products if p.stock <= 5 and not p.is_expired)
#     total_stock = sum(p.stock for p in products)
#
#     return render_template(
#         "retail_dash.html",
#         products=products,
#         total_products=total_products,
#         active_deals=active_deals,
#         low_stock=low_stock,
#         total_stock=total_stock
#     )
#
#
# @app.route("/add_product", methods=["GET", "POST"])
# @login_required
# def add_product():
#     if current_user.role != "retailer":
#         return redirect(url_for("home"))
#
#     form = AddProductForm()
#     if form.validate_on_submit():
#         product = Product(
#             name=form.name.data,
#             description=form.description.data,
#             category=form.category.data,
#             original_price=form.original_price.data,
#             stock=form.stock.data,
#             expiry_date=form.expiry_date.data,
#             deal_active=True,
#             retailer_id=current_user.id
#         )
#         db.session.add(product)
#         db.session.commit()
#         flash("Product added successfully! Deal is now live.", "success")
#         return redirect(url_for("retailer_dashboard"))
#
#     return render_template("add_product.html", form=form)
#
#
# @app.route("/toggle_deal/<int:product_id>")
# @login_required
# def toggle_deal(product_id):
#     product = db.session.get(Product, product_id)
#     if not product or product.retailer_id != current_user.id:
#         flash("Unauthorized.", "danger")
#         return redirect(url_for("retailer_dashboard"))
#     product.deal_active = not product.deal_active
#     db.session.commit()
#     flash(f"Deal {'activated' if product.deal_active else 'paused'}.", "success")
#     return redirect(url_for("retailer_dashboard"))
#
#
# @app.route("/delete_product/<int:product_id>")
# @login_required
# def delete_product(product_id):
#     product = db.session.get(Product, product_id)
#     if not product or product.retailer_id != current_user.id:
#         flash("Unauthorized.", "danger")
#         return redirect(url_for("retailer_dashboard"))
#     db.session.delete(product)
#     db.session.commit()
#     flash("Product deleted.", "info")
#     return redirect(url_for("retailer_dashboard"))
#
#
# @app.route("/update_stock/<int:product_id>", methods=["POST"])
# @login_required
# def update_stock(product_id):
#     product = db.session.get(Product, product_id)
#     if not product or product.retailer_id != current_user.id:
#         return jsonify({"error": "Unauthorized"}), 403
#     new_stock = request.form.get("stock", type=int)
#     if new_stock is not None and new_stock >= 0:
#         product.stock = new_stock
#         db.session.commit()
#         flash("Stock updated.", "success")
#     return redirect(url_for("retailer_dashboard"))
#
#
# # -------------------- CUSTOMER DASHBOARD --------------------
#
# @app.route("/customer_dashboard")
# @login_required
# def customer_dashboard():
#     if current_user.role != "customer":
#         return redirect(url_for("home"))
#
#     # Show all active, non-expired deals (in real app: filter by location)
#     now = datetime.now(timezone.utc)
#     products = Product.query.filter(
#         Product.deal_active == True,
#         Product.expiry_date > now,
#         Product.stock > 0
#     ).order_by(Product.expiry_date.asc()).all()  # most urgent first
#
#     return render_template("cust_dash.html", products=products)
#
#
# @app.route("/grab_deal/<int:product_id>", methods=["POST"])
# @login_required
# def grab_deal(product_id):
#     if current_user.role != "customer":
#         return redirect(url_for("home"))
#
#     product = db.session.get(Product, product_id)
#     if not product or product.stock <= 0 or product.is_expired or not product.deal_active:
#         flash("Sorry, this deal is no longer available!", "danger")
#         return redirect(url_for("customer_dashboard"))
#
#     product.stock -= 1
#     if product.stock == 0:
#         product.deal_active = False
#     db.session.commit()
#     flash(f"🎉 Deal grabbed! You got {product.name} for ₹{product.current_price}!", "success")
#     return redirect(url_for("customer_dashboard"))
#
#
# # -------------------- API: Live Price --------------------
# @app.route("/api/price/<int:product_id>")
# def get_live_price(product_id):
#     """Called by JS every 60s to refresh dynamic price"""
#     product = db.session.get(Product, product_id)
#     if not product:
#         return jsonify({"error": "Not found"}), 404
#     return jsonify({
#         "current_price": product.current_price,
#         "discount_percent": product.discount_percent,
#         "hours_left": round(product.hours_left, 2),
#         "urgency": product.urgency_level,
#         "stock": product.stock
#     })
#
#
# # -------------------- LOGOUT --------------------
# @app.route("/logout")
# @login_required
# def logout():
#     logout_user()
#     return redirect(url_for("home"))
#
#
# # -------------------- RUN --------------------
# if __name__ == "__main__":
#     app.run(debug=True)
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import datetime, timezone
import os
import joblib
import numpy as np
import pandas as pd
from flask_bootstrap import Bootstrap5

from forms import RegisterForm, LoginForm, AddProductForm

# ─────────────────────────────────────────────
#  APP SETUP
# ─────────────────────────────────────────────
load_dotenv()

app = Flask(__name__)
bootstrap = Bootstrap5(app)

app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "secret-key")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dealdrop9.db'

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# ─────────────────────────────────────────────
#  LOAD ML MODEL
# ─────────────────────────────────────────────
try:
    ml_model = joblib.load('flashmap_master_model.pkl')
    print("✅  FlashMap ML Model loaded.")
except Exception as e:
    ml_model = None
    print(f"⚠️   ML model not found ({e}). Time-based fallback will be used.")


# ─────────────────────────────────────────────
#  BACKEND INFERENCE HELPERS
#  (retailer never sees these — backend auto-computes)
# ─────────────────────────────────────────────

# 1. Demand type auto-mapped from category
CATEGORY_DEMAND_MAP = {
    "Dairy":       "Essential",
    "Bakery":      "Essential",
    "Canned":      "Essential",
    "Beverages":   "Normal",
    "Snacks":      "Normal",
    "Household":   "Normal",
    "Clothing":    "Luxury",
    "Electronics": "Luxury",
    "Cosmetics":   "Luxury",
    "Other":       "Normal",
}

# 2. Store tier inferred from city population tier
#    In production you'd call a geo/population API.
#    Here we maintain a curated lookup of major Indian cities.
HIGH_TRAFFIC_CITIES = {
    "mumbai","delhi","bangalore","bengaluru","hyderabad",
    "chennai","kolkata","pune","ahmedabad","surat",
    "jaipur","lucknow","kanpur","nagpur","indore",
    "thane","bhopal","visakhapatnam","vizag","patna",
    "vadodara","ghaziabad","ludhiana","agra","nashik",
}

MED_TRAFFIC_CITIES = {
    "faridabad","meerut","rajkot","kalyan","vasai",
    "varanasi","srinagar","aurangabad","dhanbad","amritsar",
    "navi mumbai","allahabad","prayagraj","ranchi","howrah",
    "coimbatore","jabalpur","gwalior","vijayawada","jodhpur",
    "madurai","raipur","kota","guwahati","chandigarh",
    "thiruvananthapuram","solapur","hubli","tiruchirappalli",
    "bareilly","mysore","mysuru","tiruppur","gurgaon","gurugram",
    "aligarh","jalandhar","bhubaneswar","salem","mira road",
    "warangal","guntur","bhiwandi","saharanpur","gorakhpur",
    "bikaner","amravati","noida","jamshedpur","bhilai",
    "cuttack","firozabad","kochi","ernakulam","ambattur",
    "chennai suburb","kolhapur","ajmer","ulhasnagar",
}

def infer_store_tier(city: str) -> str:
    """Auto-compute store traffic tier from retailer's registered city."""
    if not city:
        return "Med_Traffic"
    c = city.strip().lower()
    if c in HIGH_TRAFFIC_CITIES:
        return "High_Traffic"
    if c in MED_TRAFFIC_CITIES:
        return "Med_Traffic"
    return "Low_Traffic"


# 3. Velocity estimated from category baseline sales data
CATEGORY_VELOCITY_MAP = {
    "Dairy":       18.0,   # daily staple — high turnover
    "Bakery":      14.0,
    "Beverages":   12.0,
    "Snacks":      10.0,
    "Canned":       8.0,
    "Household":    5.0,
    "Cosmetics":    3.0,
    "Clothing":     2.0,
    "Electronics":  1.5,
    "Other":        5.0,
}


def infer_velocity(category: str) -> float:
    return CATEGORY_VELOCITY_MAP.get(category, 5.0)


def infer_demand_type(category: str) -> str:
    return CATEGORY_DEMAND_MAP.get(category, "Normal")


def predict_discount(store_tier, category, demand_type, days_left, stock, velocity) -> float | None:
    """Run the ML model; returns discount fraction 0.0–0.85 or None if unavailable."""
    if ml_model is None:
        return None
    try:
        df = pd.DataFrame([{
            'store_tier':  store_tier,
            'category':    category,
            'demand_type': demand_type,
            'days_left':   float(days_left),
            'stock':       int(stock),
            'velocity':    float(velocity),
        }])
        pred = ml_model.predict(df)[0]
        return float(np.clip(pred, 0.0, 0.85))
    except Exception as e:
        print(f"ML prediction error: {e}")
        return None


# ─────────────────────────────────────────────
#  MODELS
# ─────────────────────────────────────────────

class User(UserMixin, db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    email    = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    name     = db.Column(db.String(100), nullable=False)
    role     = db.Column(db.String(20),  nullable=False)   # customer / retailer
    city     = db.Column(db.String(100), nullable=True)
    products = db.relationship('Product', backref='retailer', lazy=True)


class Product(db.Model):
    id          = db.Column(db.Integer,  primary_key=True)
    name        = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    category    = db.Column(db.String(100), nullable=True)
    original_price = db.Column(db.Float,  nullable=False)
    stock       = db.Column(db.Integer,   nullable=False)
    expiry_date = db.Column(db.DateTime,  nullable=False)
    deal_active = db.Column(db.Boolean,   default=True)
    created_at  = db.Column(db.DateTime,  default=lambda: datetime.now(timezone.utc))
    retailer_id = db.Column(db.Integer,   db.ForeignKey('user.id'), nullable=False)

    # ML inputs (stored for audit/re-training; invisible to retailer)
    store_tier           = db.Column(db.String(20),  default='Med_Traffic')
    demand_type          = db.Column(db.String(20),  default='Normal')
    velocity             = db.Column(db.Float,        default=5.0)
    ai_suggested_discount = db.Column(db.Float,       nullable=True)

    # ── computed properties ──────────────────

    @property
    def hours_left(self):
        now    = datetime.now(timezone.utc)
        expiry = self.expiry_date
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return max(0.0, (expiry - now).total_seconds() / 3600)

    @property
    def days_left(self):
        return self.hours_left / 24.0

    @property
    def is_expired(self):
        return self.hours_left <= 0

    @property
    def current_price(self):
        """AI discount first; time-based fallback."""
        if self.ai_suggested_discount is not None:
            discount = float(self.ai_suggested_discount)
        else:
            h = self.hours_left
            if   h > 24: discount = 0.10
            elif h > 12: discount = 0.25
            elif h > 6:  discount = 0.40
            else:        discount = 0.60
        return round(self.original_price * (1 - discount), 2)

    @property
    def discount_percent(self):
        if self.ai_suggested_discount is not None:
            return round(self.ai_suggested_discount * 100)
        h = self.hours_left
        if   h > 24: return 10
        elif h > 12: return 25
        elif h > 6:  return 40
        return 60

    @property
    def urgency_level(self):
        h = self.hours_left
        if   h > 24: return "low"
        elif h > 12: return "medium"
        elif h > 6:  return "high"
        return "critical"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ─────────────────────────────────────────────
#  DB INIT
# ─────────────────────────────────────────────
with app.app_context():
    db.create_all()


# ─────────────────────────────────────────────
#  ROUTES — AUTH
# ─────────────────────────────────────────────

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
        if User.query.filter_by(email=form.email.data).first():
            flash("Account already exists. Please login.", "warning")
            return redirect(url_for("login"))
        new_user = User(
            email    = form.email.data,
            name     = form.name.data,
            password = generate_password_hash(form.password.data),
            role     = role,
            city     = form.city.data,
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for("retailer_dashboard" if role == "retailer" else "customer_dashboard"))
    return render_template("register.html", form=form, role=role)


@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.execute(db.select(User).where(User.email == form.email.data)).scalar()
        if not user:
            flash("Email not found. Please try again.", "warning")
        elif not check_password_hash(user.password, form.password.data):
            flash("Incorrect password. Please try again.", "danger")
        else:
            login_user(user)
            return redirect(url_for("retailer_dashboard" if user.role == "retailer" else "customer_dashboard"))
    return render_template("login.html", form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))


# ─────────────────────────────────────────────
#  ROUTES — RETAILER
# ─────────────────────────────────────────────

@app.route("/retailer_dashboard")
@login_required
def retailer_dashboard():
    if current_user.role != "retailer":
        return redirect(url_for("home"))
    products      = Product.query.filter_by(retailer_id=current_user.id).all()
    total_products = len(products)
    active_deals  = sum(1 for p in products if p.deal_active and not p.is_expired)
    low_stock     = sum(1 for p in products if p.stock <= 5 and not p.is_expired)
    total_stock   = sum(p.stock for p in products)
    return render_template(
        "retail_dash.html",
        products=products,
        total_products=total_products,
        active_deals=active_deals,
        low_stock=low_stock,
        total_stock=total_stock,
    )


@app.route("/add_product", methods=["GET", "POST"])
@login_required
def add_product():
    if current_user.role != "retailer":
        return redirect(url_for("home"))
    form = AddProductForm()
    if form.validate_on_submit():
        # ── Auto-resolve ML params (retailer never touches these) ──
        category    = form.category.data
        expiry      = form.expiry_date.data
        expiry_aware = expiry.replace(tzinfo=timezone.utc) if expiry.tzinfo is None else expiry
        days_left   = max(0.0, (expiry_aware - datetime.now(timezone.utc)).total_seconds() / 86400)

        store_tier  = infer_store_tier(current_user.city)
        demand_type = infer_demand_type(category)
        velocity    = infer_velocity(category)

        ai_discount = predict_discount(store_tier, category, demand_type, days_left, form.stock.data, velocity)

        product = Product(
            name          = form.name.data,
            description   = form.description.data,
            category      = category,
            original_price= form.original_price.data,
            stock         = form.stock.data,
            expiry_date   = expiry,
            store_tier    = store_tier,
            demand_type   = demand_type,
            velocity      = velocity,
            ai_suggested_discount = ai_discount,
            deal_active   = True,
            retailer_id   = current_user.id,
        )
        db.session.add(product)
        db.session.commit()

        if ai_discount is not None:
            deal_price = round(form.original_price.data * (1 - ai_discount), 2)
            flash(
                f"🤖 AI priced at {round(ai_discount * 100)}% off "
                f"(₹{deal_price}) — deal is live!",
                "success"
            )
        else:
            flash("✅ Deal is live! Dynamic time-based pricing is active.", "success")

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
    flash(f"Deal {'activated ✅' if product.deal_active else 'paused ⏸️'}.", "info")
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


# ─────────────────────────────────────────────
#  API — AI discount preview (called by the
#  "Get AI Discount" button on add_product page)
# ─────────────────────────────────────────────

@app.route("/api/ai_discount_preview", methods=["POST"])
@login_required
def ai_discount_preview():
    """
    Accepts: { category, original_price, stock, expiry_iso }
    Returns: { discount_percent, deal_price, savings, ai_powered,
               store_tier, demand_type, velocity }
    Retailer sends only what they've filled in; backend resolves the rest.
    """
    data = request.get_json(silent=True) or {}
    try:
        category       = data.get("category", "Other")
        original_price = float(data.get("original_price", 0))
        stock          = int(data.get("stock", 1))
        expiry_iso     = data.get("expiry_iso", "")

        # Compute days_left
        if expiry_iso:
            try:
                expiry_dt = datetime.fromisoformat(expiry_iso)
                if expiry_dt.tzinfo is None:
                    expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                days_left = max(0.0, (expiry_dt - datetime.now(timezone.utc)).total_seconds() / 86400)
            except Exception:
                days_left = 7.0
        else:
            days_left = 7.0

        # Auto-resolve ML params
        store_tier  = infer_store_tier(current_user.city)
        demand_type = infer_demand_type(category)
        velocity    = infer_velocity(category)

        discount = predict_discount(store_tier, category, demand_type, days_left, stock, velocity)

        # Fallback if no model
        if discount is None:
            if   days_left > 1:   discount = 0.10
            elif days_left > 0.5: discount = 0.25
            else:                 discount = 0.60

        deal_price = round(original_price * (1 - discount), 2) if original_price else 0
        savings    = round(original_price - deal_price, 2)     if original_price else 0

        return jsonify({
            "discount_percent": round(discount * 100),
            "deal_price":       deal_price,
            "savings":          savings,
            "ai_powered":       ml_model is not None,
            "store_tier":       store_tier,
            "demand_type":      demand_type,
            "velocity":         velocity,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ─────────────────────────────────────────────
#  ROUTES — CUSTOMER
# ─────────────────────────────────────────────

@app.route("/customer_dashboard")
@login_required
def customer_dashboard():
    if current_user.role != "customer":
        return redirect(url_for("home"))
    now = datetime.now(timezone.utc)
    products = Product.query.filter(
        Product.deal_active == True,
        Product.expiry_date > now,
        Product.stock > 0,
    ).order_by(Product.expiry_date.asc()).all()
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


# ─────────────────────────────────────────────
#  API — Live price refresh
# ─────────────────────────────────────────────

@app.route("/api/price/<int:product_id>")
def get_live_price(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({"error": "Not found"}), 404
    return jsonify({
        "current_price":    product.current_price,
        "discount_percent": product.discount_percent,
        "hours_left":       round(product.hours_left, 2),
        "urgency":          product.urgency_level,
        "stock":            product.stock,
    })


# ─────────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True)

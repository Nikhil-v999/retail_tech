from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import (UserMixin, login_user, LoginManager,
                         login_required, logout_user, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import datetime, timezone, date, timedelta
import os
import math
import time
import joblib
import numpy as np
import pandas as pd
from flask_bootstrap import Bootstrap5

# ── Geopy: graceful import so the app boots even without the package installed ──
try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut, GeocoderServiceError
    _GEOPY_AVAILABLE = True
except ImportError:
    _GEOPY_AVAILABLE = False
    print("⚠️  geopy not installed. Run: pip install geopy")

from forms import (RegisterForm, LoginForm, AddProductForm,
                   EditProductForm, LaunchDealForm, UpdateAddressForm)

# ═══════════════════════════════════════════════════════════════
#  APP SETUP
# ═══════════════════════════════════════════════════════════════
load_dotenv()

app = Flask(__name__)
bootstrap = Bootstrap5(app)

app.config['SECRET_KEY']                  = os.getenv("SECRET_KEY", "change-me-in-production")
app.config['SQLALCHEMY_DATABASE_URI']     = os.getenv("DATABASE_URL", "sqlite:///dealdrop99.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# ═══════════════════════════════════════════════════════════════
#  ML MODEL LOADER
# ═══════════════════════════════════════════════════════════════
try:
    ml_model = joblib.load('flashmap_master_model.pkl')
    print("✅  FlashMap ML Model loaded.")
except Exception as e:
    ml_model = None
    print(f"⚠️   ML model not found ({e}). Time-based fallback active.")


# ═══════════════════════════════════════════════════════════════
#  STATIC LOOKUP TABLES
# ═══════════════════════════════════════════════════════════════

CATEGORY_DEMAND_MAP = {
    "Dairy": "Essential", "Bakery": "Essential", "Canned": "Essential",
    "Beverages": "Normal", "Snacks": "Normal",   "Household": "Normal",
    "Clothing": "Luxury",  "Electronics": "Luxury", "Cosmetics": "Luxury",
    "Other": "Normal",
}

# Baseline velocity (units/day) — used before real sale history exists
CATEGORY_VELOCITY_BASELINE = {
    "Dairy": 18.0, "Bakery": 14.0, "Beverages": 12.0, "Snacks": 10.0,
    "Canned": 8.0, "Household": 5.0, "Cosmetics": 3.0,
    "Clothing": 2.0, "Electronics": 1.5, "Other": 5.0,
}

HIGH_TRAFFIC_CITIES = {
    "mumbai","delhi","bangalore","bengaluru","hyderabad","chennai",
    "kolkata","pune","ahmedabad","surat","jaipur","lucknow","kanpur",
    "nagpur","indore","thane","bhopal","visakhapatnam","vizag","patna",
    "vadodara","ghaziabad","ludhiana","agra","nashik",
}
MED_TRAFFIC_CITIES = {
    "faridabad","meerut","rajkot","kalyan","vasai","varanasi","srinagar",
    "aurangabad","dhanbad","amritsar","navi mumbai","allahabad","prayagraj",
    "ranchi","howrah","coimbatore","jabalpur","gwalior","vijayawada",
    "jodhpur","madurai","raipur","kota","guwahati","chandigarh",
    "thiruvananthapuram","solapur","hubli","tiruchirappalli","bareilly",
    "mysore","mysuru","tiruppur","gurgaon","gurugram","aligarh","jalandhar",
    "bhubaneswar","salem","warangal","guntur","bhiwandi","gorakhpur",
    "bikaner","amravati","noida","jamshedpur","cuttack","kochi","ernakulam",
}


# ═══════════════════════════════════════════════════════════════
#  GEOCODING HELPERS  (Phase 1)
# ═══════════════════════════════════════════════════════════════

# Single module-level Nominatim instance (Nominatim requires a unique user_agent)
_geolocator = Nominatim(user_agent="dealdrop_v1_geocoder", timeout=6) if _GEOPY_AVAILABLE else None


def geocode_address(address_string: str) -> tuple[float | None, float | None, str]:
    """
    Geocodes a free-form address string using Nominatim (OpenStreetMap).

    Returns:
        (lat, lon, city_name)  — city_name may be "" if extraction fails.
        Returns (None, None, "") on any error so callers can degrade gracefully.

    Rate-limit: Nominatim enforces 1 request/second for unauthenticated usage.
    We sleep 1.1 s to stay safely within that limit.
    """
    if _geolocator is None:
        print("Geocoder unavailable — geopy not installed.")
        return None, None, ""

    try:
        time.sleep(1.1)  # Nominatim policy: max 1 req/s
        location = _geolocator.geocode(address_string, addressdetails=True, language="en")
        if location is None:
            return None, None, ""

        lat = location.latitude
        lon = location.longitude

        # Extract city from the structured address block Nominatim returns
        addr = location.raw.get("address", {})
        city = (
            addr.get("city")
            or addr.get("town")
            or addr.get("village")
            or addr.get("county")
            or addr.get("state_district")
            or ""
        )
        return lat, lon, city.strip()

    except GeocoderTimedOut:
        print(f"Geocoding timed out for: {address_string!r}")
        return None, None, ""
    except GeocoderServiceError as exc:
        print(f"Geocoding service error: {exc}")
        return None, None, ""
    except Exception as exc:
        print(f"Unexpected geocoding error: {exc}")
        return None, None, ""


# ═══════════════════════════════════════════════════════════════
#  HAVERSINE & RELEVANCE ENGINE  (Phase 2)
# ═══════════════════════════════════════════════════════════════

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculates the great-circle distance between two GPS coordinates.

    Uses the Haversine formula — accurate to within ~0.3% for distances
    up to ~500 km, which comfortably covers any hyperlocal use-case.

    Returns:
        Distance in kilometres (float).
    """
    R = 6_371.0  # Mean Earth radius in km
    phi1, phi2   = math.radians(lat1), math.radians(lat2)
    dphi         = math.radians(lat2 - lat1)
    dlambda      = math.radians(lon2 - lon1)

    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def calculate_relevance_score(
    discount_percent: float,
    distance_km: float | None,
    days_left: float,
) -> float:
    """
    Composite deal-relevance score for the customer discovery feed.

    Formula (as specified):
        Score = (50 × Discount% / 100)
              - (10 × Distance_km)
              + (30 × 1 / Days_Left)

    Design rationale:
        • Discount term  — reward steeper discounts (max contribution ~50)
        • Distance term  — penalise far-away deals; 0 penalty if coords unknown
        • Urgency term   — boost deals expiring soon (rises steeply as → 0 days)

    Args:
        discount_percent: 0–100
        distance_km:      None if either party has no coordinates stored
        days_left:        fractional days until expiry

    Returns:
        float — higher is more relevant; list should be sorted descending.
    """
    safe_days    = max(0.01, days_left)          # floor to avoid ZeroDivisionError
    dist_penalty = 10.0 * distance_km if distance_km is not None else 0.0
    return (50.0 * discount_percent / 100.0) - dist_penalty + (30.0 / safe_days)


# ═══════════════════════════════════════════════════════════════
#  INFERENCE HELPERS
# ═══════════════════════════════════════════════════════════════

def infer_store_tier(city: str) -> str:
    if not city:
        return "Med_Traffic"
    c = city.strip().lower()
    if c in HIGH_TRAFFIC_CITIES: return "High_Traffic"
    if c in MED_TRAFFIC_CITIES:  return "Med_Traffic"
    return "Low_Traffic"

def infer_demand_type(category: str) -> str:
    return CATEGORY_DEMAND_MAP.get(category, "Normal")

def infer_velocity(category: str) -> float:
    """Static category baseline — used when no sale history exists yet."""
    return CATEGORY_VELOCITY_BASELINE.get(category, 5.0)


# ─────────────────────────────────────────────────────────────
#  REAL VELOCITY ENGINE
# ─────────────────────────────────────────────────────────────
def compute_real_velocity(product_id: int, category: str) -> float:
    window_start = datetime.now(timezone.utc) - timedelta(days=7)
    recent = Sale.query.filter(
        Sale.product_id == product_id,
        Sale.timestamp  >= window_start,
    ).all()
    if len(recent) < 2:
        return CATEGORY_VELOCITY_BASELINE.get(category, 5.0)
    total_units = sum(s.quantity_sold for s in recent)
    ts = sorted(s.timestamp for s in recent)
    obs_days = max(1.0, (ts[-1] - ts[0]).total_seconds() / 86400)
    return round(total_units / obs_days, 2)


# ─────────────────────────────────────────────────────────────
#  ML PREDICTION
# ─────────────────────────────────────────────────────────────
def predict_discount(store_tier, category, demand_type,
                     days_left, stock, velocity) -> float | None:
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
        return float(np.clip(ml_model.predict(df)[0], 0.0, 0.85))
    except Exception as e:
        print(f"ML prediction error: {e}")
        return None


def _time_based_discount(hours_left: float) -> float:
    """
    Fallback tiered pricing when ML is unavailable.
    >24h → 10%  |  >12h → 25%  |  >6h → 40%  |  ≤6h → 60%
    """
    if   hours_left > 24: return 0.10
    elif hours_left > 12: return 0.25
    elif hours_left > 6:  return 0.40
    return 0.60


# ─────────────────────────────────────────────────────────────
#  SMART CLOSING-TIME SUGGESTER
# ─────────────────────────────────────────────────────────────
def suggest_closing_time(stock: int, velocity: float,
                         expiry_dt: datetime) -> datetime:
    now          = datetime.now(timezone.utc)
    expiry_aware = expiry_dt if expiry_dt.tzinfo else expiry_dt.replace(tzinfo=timezone.utc)
    max_hours    = max(1.0, (expiry_aware - now).total_seconds() / 3600)
    vel          = max(velocity, 0.1)
    hours_raw    = stock / (vel / 24)
    hours_sug    = max(1.0, min(hours_raw * 0.9, max_hours * 0.9))
    return now + timedelta(hours=hours_sug)


# ═══════════════════════════════════════════════════════════════
#  MODELS
# ═══════════════════════════════════════════════════════════════

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id       = db.Column(db.Integer, primary_key=True)
    email    = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    name     = db.Column(db.String(100), nullable=False)
    role     = db.Column(db.String(20),  nullable=False)

    # ── UPDATED location fields ───────────────────────────────────────────────
    # 'city'    : kept for backward-compat & store-tier inference; derived from
    #             geocoding during registration (may be None for legacy rows).
    # 'address' : the raw free-text address the user supplied.
    # 'lat/lon' : WGS-84 decimal degrees; None until first geocode succeeds.
    #
    # POLICY: Retailer lat/lon is set ONCE at registration and never changes.
    #         Customers may update their location via /update_location.
    city    = db.Column(db.String(100), nullable=True)
    address = db.Column(db.String(300), nullable=True)
    lat     = db.Column(db.Float,       nullable=True)
    lon     = db.Column(db.Float,       nullable=True)
    # ─────────────────────────────────────────────────────────────────────────

    products = db.relationship('Product', backref='retailer', lazy=True,
                               cascade='all, delete-orphan')


class Product(db.Model):
    __tablename__ = 'product'
    id                    = db.Column(db.Integer,  primary_key=True)
    name                  = db.Column(db.String(200), nullable=False)
    description           = db.Column(db.String(500), nullable=True)
    category              = db.Column(db.String(100), nullable=True)
    original_price        = db.Column(db.Float,   nullable=False)
    stock                 = db.Column(db.Integer,  nullable=False)
    expiry_date           = db.Column(db.DateTime, nullable=False)
    deal_active           = db.Column(db.Boolean,  default=True)
    created_at            = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    retailer_id           = db.Column(db.Integer,  db.ForeignKey('user.id'), nullable=False)
    store_tier            = db.Column(db.String(20), default='Med_Traffic')
    demand_type           = db.Column(db.String(20), default='Normal')
    velocity              = db.Column(db.Float,      default=5.0)
    ai_suggested_discount = db.Column(db.Float,      nullable=True)
    sales = db.relationship('Sale', backref='product', lazy=True,
                            cascade='all, delete-orphan')

    @property
    def _expiry_aware(self):
        e = self.expiry_date
        return e if e.tzinfo else e.replace(tzinfo=timezone.utc)

    @property
    def hours_left(self):
        return max(0.0,
            (self._expiry_aware - datetime.now(timezone.utc)).total_seconds() / 3600)

    @property
    def days_left(self):
        return self.hours_left / 24.0

    @property
    def is_expired(self):
        return self.hours_left <= 0

    @property
    def current_price(self):
        discount = (float(self.ai_suggested_discount)
                    if self.ai_suggested_discount is not None
                    else _time_based_discount(self.hours_left))
        return round(self.original_price * (1 - discount), 2)

    @property
    def discount_percent(self):
        if self.ai_suggested_discount is not None:
            return round(self.ai_suggested_discount * 100)
        h = self.hours_left
        if h > 24: return 10
        if h > 12: return 25
        if h > 6:  return 40
        return 60

    @property
    def urgency_level(self):
        h = self.hours_left
        if h > 24: return "low"
        if h > 12: return "medium"
        if h > 6:  return "high"
        return "critical"

    @property
    def total_units_sold(self):
        return sum(s.quantity_sold for s in self.sales)

    @property
    def total_revenue(self):
        return sum(s.quantity_sold * s.selling_price for s in self.sales)


class Sale(db.Model):
    __tablename__ = 'sale'
    id            = db.Column(db.Integer, primary_key=True)
    product_id    = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    customer_id   = db.Column(db.Integer, db.ForeignKey('user.id'),    nullable=False)
    quantity_sold = db.Column(db.Integer, nullable=False, default=1)
    selling_price = db.Column(db.Float,   nullable=False)
    timestamp     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    customer      = db.relationship('User', foreign_keys=[customer_id])


class Notification(db.Model):
    """
    ntype: 'alert' | 'deal' | 'system'
    Stored in DB — survives page reloads and sessions.
    """
    __tablename__ = 'notification'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title      = db.Column(db.String(120), nullable=False)
    body       = db.Column(db.String(400), nullable=False)
    ntype      = db.Column(db.String(20),  nullable=False, default='system')
    read       = db.Column(db.Boolean,     nullable=False, default=False)
    created_at = db.Column(db.DateTime,    default=lambda: datetime.now(timezone.utc))
    user       = db.relationship('User', foreign_keys=[user_id])


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

with app.app_context():
    db.create_all()


# ═══════════════════════════════════════════════════════════════
#  NOTIFICATION HELPERS
# ═══════════════════════════════════════════════════════════════

def push_notification(user_id: int, title: str, body: str, ntype: str = 'system'):
    """Add notification row. Caller must call db.session.commit()."""
    db.session.add(Notification(user_id=user_id, title=title, body=body, ntype=ntype))


def _auto_alerts(retailer_id: int):
    """
    Runs on every dashboard load. Pushes deduped notifications for:
    - Low stock     : stock ≤ 5, not expired
    - Expiring soon : hours_left ≤ 6, deal active
    - Unsold        : 0 sales after 6+ hours live
    Dedup key: title string vs existing unread titles (no spam on refresh).
    """
    products = Product.query.filter_by(retailer_id=retailer_id).all()
    existing = {
        n.title for n in
        Notification.query.filter_by(user_id=retailer_id, read=False).all()
    }
    for p in products:
        if p.is_expired:
            continue
        if p.stock <= 5:
            t = f"⚠️ Low Stock: {p.name}"
            if t not in existing:
                push_notification(retailer_id, t,
                    f"Only {p.stock} unit(s) left. Update your deal.", ntype='alert')
        if 0 < p.hours_left <= 6 and p.deal_active:
            t = f"🔴 Expiring Soon: {p.name}"
            if t not in existing:
                push_notification(retailer_id, t,
                    f"Closes in {round(p.hours_left,1)}h — "
                    f"{p.stock} units at ₹{p.current_price}.", ntype='alert')
        if p.deal_active and p.total_units_sold == 0:
            created = (p.created_at.replace(tzinfo=timezone.utc)
                       if p.created_at and p.created_at.tzinfo is None else p.created_at)
            if created:
                age_h = (datetime.now(timezone.utc) - created).total_seconds() / 3600
                if age_h >= 6:
                    t = f"📦 No Sales Yet: {p.name}"
                    if t not in existing:
                        push_notification(retailer_id, t,
                            f"0 sales after {age_h:.0f}h. "
                            "Try increasing the discount.", ntype='alert')


# ═══════════════════════════════════════════════════════════════
#  KPI BUILDER
# ═══════════════════════════════════════════════════════════════

def build_retailer_kpis(retailer_id: int) -> dict:
    products    = Product.query.filter_by(retailer_id=retailer_id).all()
    today_start = datetime.combine(
        date.today(), datetime.min.time()
    ).replace(tzinfo=timezone.utc)

    today_sales = Sale.query.join(Product).filter(
        Product.retailer_id == retailer_id,
        Sale.timestamp >= today_start,
    ).all()
    all_sales = Sale.query.join(Product).filter(
        Product.retailer_id == retailer_id
    ).all()
    unread = Notification.query.filter_by(user_id=retailer_id, read=False).count()

    return {
        "products":       products,
        "total_products": len(products),
        "active_deals":   sum(1 for p in products if p.deal_active and not p.is_expired),
        "low_stock":      sum(1 for p in products if p.stock <= 5 and not p.is_expired),
        "expiring_soon":  sum(1 for p in products if 0 < p.hours_left <= 24),
        "sales_today":    sum(s.quantity_sold for s in today_sales),
        "revenue_today":  round(sum(s.quantity_sold * s.selling_price for s in today_sales), 2),
        "total_revenue":  round(sum(s.quantity_sold * s.selling_price for s in all_sales), 2),
        "unread_notifs":  unread,
    }


# ═══════════════════════════════════════════════════════════════
#  ROUTES — AUTH
# ═══════════════════════════════════════════════════════════════

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

        # ── Phase 1: Geocode the address once at registration ─────────────────
        # Geocoding happens synchronously here. On failure we still create the
        # account — coordinates are simply left NULL and the app degrades to
        # city-name-based tiers / no distance filtering.
        lat, lon, geocoded_city = geocode_address(form.address.data)

        if lat is None:
            # Non-fatal: warn but allow registration to proceed.
            flash(
                "⚠️ We couldn't pinpoint your exact address on the map — "
                "try a more specific address later. Your account has been created.",
                "warning"
            )

        # Derive city for store-tier inference (fall back to first token of address)
        city_for_tier = geocoded_city or form.address.data.split(",")[0].strip()

        new_user = User(
            email    = form.email.data,
            name     = form.name.data,
            password = generate_password_hash(form.password.data),
            role     = role,
            address  = form.address.data,
            city     = city_for_tier,   # still used by infer_store_tier
            lat      = lat,
            lon      = lon,
        )
        db.session.add(new_user)
        db.session.commit()

        if role == "retailer":
            push_notification(new_user.id,
                "👋 Welcome to DealDrop!",
                "Add your first product, then launch a flash deal.",
                ntype='system')
            if lat is not None:
                push_notification(new_user.id,
                    "📍 Store Location Pinned",
                    f"Your store is geocoded at ({lat:.4f}, {lon:.4f}). "
                    "This cannot be changed — contact support if incorrect.",
                    ntype='system')
            db.session.commit()

        login_user(new_user)
        return redirect(url_for(
            "retailer_dashboard" if role == "retailer" else "customer_dashboard"
        ))
    return render_template("register.html", form=form, role=role)


@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.execute(
            db.select(User).where(User.email == form.email.data)
        ).scalar()
        if not user:
            flash("Email not found.", "warning")
        elif not check_password_hash(user.password, form.password.data):
            flash("Incorrect password.", "danger")
        else:
            login_user(user)
            return redirect(url_for(
                "retailer_dashboard" if user.role == "retailer" else "customer_dashboard"
            ))
    return render_template("login.html", form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))


# ═══════════════════════════════════════════════════════════════
#  ROUTES — RETAILER
# ═══════════════════════════════════════════════════════════════

def _require_retailer():
    if current_user.role != "retailer":
        return redirect(url_for("home"))
    return None


@app.route("/retailer_dashboard")
@login_required
def retailer_dashboard():
    if (r := _require_retailer()): return r
    _auto_alerts(current_user.id)
    db.session.commit()
    kpis = build_retailer_kpis(current_user.id)
    return render_template("retail_dash.html", **kpis)


@app.route("/add_product", methods=["GET", "POST"])
@login_required
def add_product():
    if (r := _require_retailer()): return r
    form = AddProductForm()
    if form.validate_on_submit():
        category     = form.category.data
        expiry       = form.expiry_date.data
        expiry_aware = expiry.replace(tzinfo=timezone.utc) if expiry.tzinfo is None else expiry
        days_left    = max(0.0, (expiry_aware - datetime.now(timezone.utc)).total_seconds() / 86400)
        store_tier   = infer_store_tier(current_user.city)
        demand_type  = infer_demand_type(category)
        velocity     = infer_velocity(category)
        ai_discount  = predict_discount(store_tier, category, demand_type,
                                        days_left, form.stock.data, velocity)
        d = ai_discount if ai_discount is not None else _time_based_discount(days_left * 24)

        product = Product(
            name=form.name.data, description=form.description.data,
            category=category, original_price=form.original_price.data,
            stock=form.stock.data, expiry_date=expiry,
            store_tier=store_tier, demand_type=demand_type,
            velocity=velocity, ai_suggested_discount=ai_discount,
            deal_active=True, retailer_id=current_user.id,
        )
        db.session.add(product)
        push_notification(current_user.id,
            f"⚡ Deal Launched: {form.name.data}",
            f"Live at ₹{round(form.original_price.data*(1-d),2)} ({round(d*100)}% off).",
            ntype='deal')
        db.session.commit()
        flash(f"✅ Deal is live at {round(d*100)}% off!", "success")
        return redirect(url_for("retailer_dashboard"))
    return render_template("add_product.html", form=form)


@app.route("/launch_deal", methods=["GET", "POST"])
@login_required
def launch_deal():
    if (r := _require_retailer()): return r

    inactive = Product.query.filter_by(
        retailer_id=current_user.id, deal_active=False
    ).filter(Product.stock > 0).all()

    form = LaunchDealForm()
    form.product_id.choices = [
        (p.id, f"{p.name}  —  {p.stock} units  @  ₹{p.original_price}")
        for p in inactive
    ]

    if form.validate_on_submit():
        product = db.session.get(Product, form.product_id.data)
        if not product or product.retailer_id != current_user.id:
            flash("Invalid product.", "danger")
            return redirect(url_for("launch_deal"))

        real_vel    = compute_real_velocity(product.id, product.category)
        store_tier  = infer_store_tier(current_user.city)
        demand_type = infer_demand_type(product.category)
        closing     = form.closing_time.data
        closing_aw  = closing.replace(tzinfo=timezone.utc) if closing.tzinfo is None else closing
        days_left   = max(0.0, (closing_aw - datetime.now(timezone.utc)).total_seconds() / 86400)

        ov = form.discount_override.data
        if ov and 0 < ov <= 85:
            ai_discount = ov / 100.0
        else:
            ai_discount = predict_discount(store_tier, product.category, demand_type,
                                           days_left, product.stock, real_vel)
            if ai_discount is None:
                ai_discount = _time_based_discount(
                    (closing_aw - datetime.now(timezone.utc)).total_seconds() / 3600
                )

        product.expiry_date           = closing
        product.velocity              = real_vel
        product.store_tier            = store_tier
        product.demand_type           = demand_type
        product.ai_suggested_discount = ai_discount
        product.deal_active           = True

        deal_price = round(product.original_price * (1 - ai_discount), 2)
        push_notification(current_user.id,
            f"🚀 Relaunched: {product.name}",
            f"Live at ₹{deal_price} ({round(ai_discount*100)}% off). "
            f"Velocity: {real_vel} units/day.",
            ntype='deal')
        db.session.commit()
        flash(f"🚀 {product.name} is live at ₹{deal_price} ({round(ai_discount*100)}% off)!", "success")
        return redirect(url_for("retailer_dashboard"))

    return render_template("launch_deal.html", form=form, products=inactive)


@app.route("/edit_product/<int:product_id>", methods=["GET", "POST"])
@login_required
def edit_product(product_id):
    if (r := _require_retailer()): return r
    product = db.session.get(Product, product_id)
    if not product or product.retailer_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for("retailer_dashboard"))
    form = EditProductForm(obj=product)
    if form.validate_on_submit():
        product.name           = form.name.data
        product.description    = form.description.data
        product.category       = form.category.data
        product.original_price = form.original_price.data
        product.stock          = form.stock.data
        product.expiry_date    = form.expiry_date.data
        expiry_aw   = (form.expiry_date.data.replace(tzinfo=timezone.utc)
                       if form.expiry_date.data.tzinfo is None else form.expiry_date.data)
        days_left   = max(0.0, (expiry_aw - datetime.now(timezone.utc)).total_seconds() / 86400)
        real_vel    = compute_real_velocity(product.id, form.category.data)
        store_tier  = infer_store_tier(current_user.city)
        demand_type = infer_demand_type(form.category.data)
        ai_discount = predict_discount(store_tier, form.category.data, demand_type,
                                       days_left, form.stock.data, real_vel)
        product.store_tier            = store_tier
        product.demand_type           = demand_type
        product.velocity              = real_vel
        product.ai_suggested_discount = ai_discount
        db.session.commit()
        flash("✅ Product updated. AI discount recalculated.", "success")
        return redirect(url_for("retailer_dashboard"))
    return render_template("edit_product.html", form=form, product=product)


@app.route("/toggle_deal/<int:product_id>")
@login_required
def toggle_deal(product_id):
    if (r := _require_retailer()): return r
    product = db.session.get(Product, product_id)
    if not product or product.retailer_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for("retailer_dashboard"))
    product.deal_active = not product.deal_active
    label = "activated ✅" if product.deal_active else "paused ⏸️"
    push_notification(current_user.id,
        f"Deal {label}: {product.name}",
        f"You manually {'activated' if product.deal_active else 'paused'} this deal.",
        ntype='deal')
    db.session.commit()
    flash(f"Deal {label}.", "info")
    return redirect(url_for("retailer_dashboard"))


@app.route("/delete_product/<int:product_id>", methods=["POST"])
@login_required
def delete_product(product_id):
    if (r := _require_retailer()): return r
    product = db.session.get(Product, product_id)
    if not product or product.retailer_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for("retailer_dashboard"))
    name = product.name
    db.session.delete(product)
    push_notification(current_user.id,
        f"🗑️ Deleted: {name}",
        "Product and all its records permanently removed.",
        ntype='system')
    db.session.commit()
    flash(f"🗑️ {name} deleted.", "info")
    return redirect(url_for("retailer_dashboard"))


@app.route("/notifications")
@login_required
def notifications_page():
    if (r := _require_retailer()): return r
    return render_template("notifications.html")


@app.route("/sales_history")
@login_required
def sales_history():
    if (r := _require_retailer()): return r
    sales = (Sale.query.join(Product)
             .filter(Product.retailer_id == current_user.id)
             .order_by(Sale.timestamp.desc()).all())
    return render_template("sales_history.html", sales=sales)


# ═══════════════════════════════════════════════════════════════
#  ROUTES — CUSTOMER  (Phase 1 & 2 additions)
# ═══════════════════════════════════════════════════════════════

@app.route("/customer_dashboard")
@login_required
def customer_dashboard():
    """
    Phase 2 — Hyperlocal Discovery Engine.

    For every active deal we:
      1. Compute the Haversine distance from the customer to the retailer.
         → Skipped (None) when either party's coordinates are unavailable.
      2. Score each deal with calculate_relevance_score().
      3. Sort descending by score so the best deals surface first.

    We attach 'distance_km' and 'relevance_score' directly onto the Product
    objects as transient Python attributes — SQLAlchemy doesn't persist them,
    but the Jinja template can read them like normal properties.
    """
    if current_user.role != "customer":
        return redirect(url_for("home"))

    now = datetime.now(timezone.utc)
    products = Product.query.filter(
        Product.deal_active == True,
        Product.expiry_date > now,
        Product.stock > 0,
    ).all()

    user_lat = current_user.lat
    user_lon = current_user.lon
    has_location = (user_lat is not None and user_lon is not None)

    for p in products:
        retailer_lat = p.retailer.lat
        retailer_lon = p.retailer.lon

        # ── Distance (km) ───────────────────────────────────────────────────
        if has_location and retailer_lat is not None and retailer_lon is not None:
            dist = haversine_distance(user_lat, user_lon, retailer_lat, retailer_lon)
            p.distance_km = round(dist, 1)
        else:
            p.distance_km = None  # no coords → distance unknown

        # ── Relevance score ─────────────────────────────────────────────────
        p.relevance_score = calculate_relevance_score(
            discount_percent = p.discount_percent,
            distance_km      = p.distance_km,
            days_left        = p.days_left,
        )

    # Sort: highest relevance first
    products.sort(key=lambda p: p.relevance_score, reverse=True)

    return render_template(
        "cust_dash.html",
        products=products,
        user_has_location=has_location,
    )


@app.route("/update_location", methods=["GET", "POST"])
@login_required
def update_location():
    """
    Phase 1 — Customer location update.

    CRITICAL ACCESS POLICY:
      • Retailers: BLOCKED. Their coordinates are pinned once at registration
        so that deal relevance scores remain fair and their store-tier inference
        stays stable. Attempting to access this route redirects them away.
      • Customers: allowed; re-geocodes their supplied address and updates
        (address, lat, lon, city) in the User row.
    """
    if current_user.role == "retailer":
        flash(
            "🔒 Retailer store locations are fixed at registration and cannot be changed. "
            "Contact support if your address is incorrect.",
            "warning"
        )
        return redirect(url_for("retailer_dashboard"))

    if current_user.role != "customer":
        return redirect(url_for("home"))

    form = UpdateAddressForm()

    if form.validate_on_submit():
        new_address = form.address.data.strip()
        lat, lon, geocoded_city = geocode_address(new_address)

        if lat is None:
            flash(
                "⚠️ We couldn't find that location. "
                "Try adding a city name or pin code for better results.",
                "warning"
            )
            # Re-render form with the submitted value preserved
            return render_template("update_location.html", form=form)

        current_user.address = new_address
        current_user.lat     = lat
        current_user.lon     = lon
        if geocoded_city:
            current_user.city = geocoded_city   # refresh city for store-tier display

        db.session.commit()
        flash(
            f"📍 Location updated to ({lat:.4f}, {lon:.4f}). "
            "Deal rankings will now reflect your new position!",
            "success"
        )
        return redirect(url_for("customer_dashboard"))

    # GET: pre-fill with whatever address is already on record
    if request.method == "GET" and current_user.address:
        form.address.data = current_user.address

    return render_template("update_location.html", form=form)


@app.route("/grab_deal/<int:product_id>", methods=["POST"])
@login_required
def grab_deal(product_id):
    if current_user.role != "customer":
        return redirect(url_for("home"))
    product = db.session.get(Product, product_id)
    if not product or product.stock <= 0 or product.is_expired or not product.deal_active:
        flash("Sorry, this deal is no longer available!", "danger")
        return redirect(url_for("customer_dashboard"))

    selling_price = product.current_price   # freeze at grab time
    product.stock -= 1
    if product.stock == 0:
        product.deal_active = False
        push_notification(product.retailer_id,
            f"✅ Sold Out: {product.name}",
            "All units sold — deal auto-closed. Great work!",
            ntype='deal')

    db.session.add(Sale(
        product_id=product.id, customer_id=current_user.id,
        quantity_sold=1, selling_price=selling_price,
    ))
    db.session.commit()
    flash(f"🎉 You got {product.name} for ₹{selling_price}!", "success")
    return redirect(url_for("customer_dashboard"))


# ═══════════════════════════════════════════════════════════════
#  API — AI discount preview
# ═══════════════════════════════════════════════════════════════

@app.route("/api/ai_discount_preview", methods=["POST"])
@login_required
def ai_discount_preview():
    data = request.get_json(silent=True) or {}
    try:
        category       = data.get("category", "Other")
        original_price = float(data.get("original_price", 0))
        stock          = int(data.get("stock", 1))
        expiry_iso     = data.get("expiry_iso", "")
        product_id     = data.get("product_id")

        if expiry_iso:
            try:
                expiry_dt = datetime.fromisoformat(expiry_iso)
                if expiry_dt.tzinfo is None:
                    expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                days_left = max(0.0,
                    (expiry_dt - datetime.now(timezone.utc)).total_seconds() / 86400)
            except Exception:
                days_left = 7.0
        else:
            days_left = 7.0

        store_tier  = infer_store_tier(current_user.city)
        demand_type = infer_demand_type(category)
        velocity    = (compute_real_velocity(int(product_id), category)
                       if product_id else infer_velocity(category))
        discount    = predict_discount(store_tier, category, demand_type,
                                       days_left, stock, velocity)
        if discount is None:
            discount = _time_based_discount(days_left * 24)

        deal_price = round(original_price * (1 - discount), 2) if original_price else 0
        return jsonify({
            "discount_percent": round(discount * 100),
            "deal_price":       deal_price,
            "savings":          round(original_price - deal_price, 2),
            "ai_powered":       ml_model is not None,
            "store_tier":       store_tier,
            "demand_type":      demand_type,
            "velocity":         round(velocity, 2),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ═══════════════════════════════════════════════════════════════
#  API — Smart closing-time suggestion
# ═══════════════════════════════════════════════════════════════

@app.route("/api/suggest_closing_time", methods=["POST"])
@login_required
def suggest_closing_time_api():
    data       = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    stock      = data.get("stock")
    if not product_id or stock is None:
        return jsonify({"error": "product_id and stock required"}), 400
    product = db.session.get(Product, int(product_id))
    if not product or product.retailer_id != current_user.id:
        return jsonify({"error": "Not found"}), 404

    velocity  = compute_real_velocity(product.id, product.category)
    suggested = suggest_closing_time(int(stock), velocity, product.expiry_date)
    hours_fn  = round((suggested - datetime.now(timezone.utc)).total_seconds() / 3600, 1)
    units_ph  = round(max(velocity, 0.1) / 24, 2)

    return jsonify({
        "suggested_iso":  suggested.strftime("%Y-%m-%dT%H:%M"),
        "hours_from_now": hours_fn,
        "velocity":       velocity,
        "reasoning": (
            f"At {velocity} units/day (~{units_ph}/hr), "
            f"{stock} units clear in ~{round(int(stock)/max(units_ph,0.01),1)}h. "
            f"10% urgency buffer → {hours_fn}h window."
        ),
    })


# ═══════════════════════════════════════════════════════════════
#  API — Notifications (bell dropdown uses these)
# ═══════════════════════════════════════════════════════════════

@app.route("/api/notifications")
@login_required
def get_notifications():
    notifs = (Notification.query
              .filter_by(user_id=current_user.id)
              .order_by(Notification.created_at.desc())
              .limit(20).all())
    return jsonify([{
        "id":         n.id,
        "title":      n.title,
        "body":       n.body,
        "ntype":      n.ntype,
        "read":       n.read,
        "created_at": n.created_at.strftime("%d %b, %H:%M") if n.created_at else "—",
    } for n in notifs])


@app.route("/api/notifications/mark_read", methods=["POST"])
@login_required
def mark_notifications_read():
    data = request.get_json(silent=True) or {}
    nid  = data.get("id")
    if nid:
        n = db.session.get(Notification, int(nid))
        if n and n.user_id == current_user.id:
            n.read = True
    else:
        Notification.query.filter_by(
            user_id=current_user.id, read=False
        ).update({"read": True})
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/notifications/unread_count")
@login_required
def unread_count():
    count = Notification.query.filter_by(user_id=current_user.id, read=False).count()
    return jsonify({"count": count})


# ═══════════════════════════════════════════════════════════════
#  API — Live price refresh
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
#  RUN
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app.run(debug=True)

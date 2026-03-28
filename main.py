from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import os
from flask_bootstrap import Bootstrap5

from forms import RegisterForm, LoginForm

# -------------------- APP SETUP --------------------
load_dotenv()

app = Flask(__name__)
bootstrap = Bootstrap5(app)

app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "secret-key")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dealdrop.db'

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# -------------------- USER MODEL --------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # customer / retailer


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# -------------------- DB INIT --------------------
with app.app_context():
    db.create_all()


# -------------------- ROUTES --------------------

# HOME (role selection)
@app.route("/")
def home():
    return render_template("index.html")


# REGISTER
@app.route("/register", methods=["GET", "POST"])
def register():
    role = request.args.get("role")  # customer / retailer
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
            role=role  # from form
        )

        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)

        if new_user.role == "retailer":
            return redirect(url_for("retailer_dashboard"))
        else:
            return redirect(url_for("customer_dashboard"))

    return render_template("register.html", form=form, role=role)


# LOGIN
@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()

    if form.validate_on_submit():

        passw = form.password.data
        result = db.session.execute(
            db.select(User).where(User.email == form.email.data)
        )
        user = result.scalar()

        if not user:
            flash("That email does not exist. Please try again.", "warning")
            return redirect(url_for('login'))

        elif not check_password_hash(user.password, passw):
            flash("Password incorrect. Please try again.", "danger")
            return redirect(url_for('login'))

        else:
            login_user(user)

            # 🔥 ROLE-BASED REDIRECT
            if user.role == "retailer":
                return redirect(url_for("retailer_dashboard"))
            else:
                return redirect(url_for("customer_dashboard"))

    return render_template("login.html", form=form)

# CUSTOMER DASHBOARD
@app.route("/customer_dashboard")
@login_required
def customer_dashboard():
    if current_user.role != "customer":
        return redirect(url_for("home"))
    return "<h1>Customer Dashboard</h1>"


# RETAILER DASHBOARD
@app.route("/retailer_dashboard")
@login_required
def retailer_dashboard():
    if current_user.role != "retailer":
        return redirect(url_for("home"))
    return "<h1>Retailer Dashboard</h1>"


# LOGOUT
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))


# -------------------- RUN --------------------
if __name__ == "__main__":
    app.run(debug=True)


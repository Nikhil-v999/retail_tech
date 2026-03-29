from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SubmitField, FloatField,
    IntegerField, TextAreaField, SelectField
)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional
from wtforms.fields import DateTimeLocalField


_CATEGORY_CHOICES = [
    ("Dairy",       "🥛 Dairy"),
    ("Bakery",      "🍞 Bakery"),
    ("Snacks",      "🍿 Snacks"),
    ("Canned",      "🥫 Canned / Packaged"),
    ("Cosmetics",   "💄 Cosmetics"),
    ("Beverages",   "🧃 Beverages"),
    ("Household",   "🏠 Household"),
    ("Electronics", "📱 Electronics"),
    ("Clothing",    "👕 Clothing"),
    ("Other",       "📦 Other"),
]


class RegisterForm(FlaskForm):
    name     = StringField("Name",     validators=[DataRequired(), Length(min=2, max=50)])
    email    = StringField("Email",    validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    # ── CHANGED: 'city' replaced with 'address' ──────────────────────────────
    # Full address is geocoded once at registration to derive (lat, lon, city).
    # Retailers: coordinates are fixed permanently after this point.
    # Customers: can update later via /update_location.
    address  = StringField(
        "Full Address",
        validators=[DataRequired(), Length(min=5, max=300)],
        description="e.g. 'Anna Nagar, Chennai' or '14 MG Road, Bengaluru 560001'"
    )
    submit   = SubmitField("Register")


class LoginForm(FlaskForm):
    email    = StringField("Email",    validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit   = SubmitField("Login")


class UpdateAddressForm(FlaskForm):
    """
    Customer-only: update current location to receive better deal relevance scores.
    Geocodes the supplied address and writes (lat, lon, city) to the User row.
    NOTE: This form must NEVER be accessible to retailer accounts — enforced in the route.
    """
    address = StringField(
        "Your Current Address / Area",
        validators=[DataRequired(), Length(min=5, max=300)],
        description="e.g. 'Koramangala, Bengaluru' or 'Bandra West, Mumbai 400050'"
    )
    submit  = SubmitField("📍 Update My Location")


class AddProductForm(FlaskForm):
    """Creates a new inventory item and immediately goes live as a deal."""
    name           = StringField("Product Name",      validators=[DataRequired(), Length(min=2, max=200)])
    description    = TextAreaField("Description",     validators=[Length(max=500)])
    category       = SelectField("Category",          choices=_CATEGORY_CHOICES)
    original_price = FloatField("Original Price (₹)", validators=[DataRequired(), NumberRange(min=0.01)])
    stock          = IntegerField("Stock Quantity",   validators=[DataRequired(), NumberRange(min=1)])
    expiry_date    = DateTimeLocalField("Deal Expires At", format="%Y-%m-%dT%H:%M",
                                        validators=[DataRequired()])
    submit         = SubmitField("Launch Deal 🚀")


class EditProductForm(FlaskForm):
    """Edit existing product; AI discount is recalculated on save."""
    name           = StringField("Product Name",      validators=[DataRequired(), Length(min=2, max=200)])
    description    = TextAreaField("Description",     validators=[Length(max=500)])
    category       = SelectField("Category",          choices=_CATEGORY_CHOICES)
    original_price = FloatField("Original Price (₹)", validators=[DataRequired(), NumberRange(min=0.01)])
    stock          = IntegerField("Stock Quantity",   validators=[DataRequired(), NumberRange(min=0)])
    expiry_date    = DateTimeLocalField("Deal Expires At", format="%Y-%m-%dT%H:%M",
                                        validators=[DataRequired()])
    submit         = SubmitField("Save Changes ✅")


class LaunchDealForm(FlaskForm):
    """
    Re-launch an existing paused/inactive product as a deal.
    product_id      : populated dynamically from inactive stock list
    closing_time    : suggested by /api/suggest_closing_time, editable by retailer
    discount_override: optional; if blank, ML / fallback pricing is used
    """
    product_id        = SelectField("Select Product", coerce=int, validators=[DataRequired()])
    closing_time      = DateTimeLocalField("Deal Closing Time", format="%Y-%m-%dT%H:%M",
                                           validators=[DataRequired()])
    discount_override = IntegerField("Override Discount % (optional, 1–85)",
                                     validators=[Optional(), NumberRange(min=1, max=85)])
    submit            = SubmitField("🚀 Go Live")

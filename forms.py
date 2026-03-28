#
# from flask_wtf import FlaskForm
# from wtforms import StringField, PasswordField, SubmitField, FloatField, IntegerField, TextAreaField, SelectField
# from wtforms.validators import DataRequired, Email, Length, NumberRange
# from wtforms.fields import DateTimeLocalField
#
#
# # -------------------- REGISTER FORM --------------------
# class RegisterForm(FlaskForm):
#     name = StringField("Name", validators=[DataRequired(), Length(min=2, max=50)])
#
#     email = StringField("Email", validators=[
#         DataRequired(),
#         Email()
#     ])
#
#     password = PasswordField("Password", validators=[
#         DataRequired(),
#         Length(min=6)
#     ])
#
#     city = StringField("City", validators=[DataRequired(), Length(min=2, max=100)])
#
#     submit = SubmitField("Register")
#
#
# # -------------------- LOGIN FORM --------------------
# class LoginForm(FlaskForm):
#     email = StringField("Email", validators=[
#         DataRequired(),
#         Email()
#     ])
#
#     password = PasswordField("Password", validators=[
#         DataRequired()
#     ])
#
#     submit = SubmitField("Login")
#
#
# # -------------------- ADD PRODUCT FORM --------------------
# class AddProductForm(FlaskForm):
#     name = StringField("Product Name", validators=[DataRequired(), Length(min=2, max=200)])
#
#     description = TextAreaField("Description", validators=[Length(max=500)])
#
#     category = SelectField("Category", choices=[
#         ("food", "🍎 Food & Grocery"),
#         ("dairy", "🥛 Dairy & Bakery"),
#         ("beverages", "🧃 Beverages"),
#         ("snacks", "🍿 Snacks"),
#         ("personal_care", "🧴 Personal Care"),
#         ("household", "🏠 Household"),
#         ("electronics", "📱 Electronics"),
#         ("clothing", "👕 Clothing"),
#         ("other", "📦 Other"),
#     ])
#
#     original_price = FloatField("Original Price (₹)", validators=[
#         DataRequired(),
#         NumberRange(min=0.01, message="Price must be positive")
#     ])
#
#     stock = IntegerField("Stock Quantity", validators=[
#         DataRequired(),
#         NumberRange(min=1, message="Stock must be at least 1")
#     ])
#
#     expiry_date = DateTimeLocalField(
#         "Deal Expiry (Date & Time)",
#         format="%Y-%m-%dT%H:%M",
#         validators=[DataRequired()]
#     )
#
#     submit = SubmitField("Add Deal 🚀")

from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SubmitField, FloatField,
    IntegerField, TextAreaField, SelectField
)
from wtforms.validators import DataRequired, Email, Length, NumberRange
from wtforms.fields import DateTimeLocalField


# -------------------- REGISTER FORM --------------------
class RegisterForm(FlaskForm):
    name     = StringField("Name",     validators=[DataRequired(), Length(min=2, max=50)])
    email    = StringField("Email",    validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    city     = StringField("City",     validators=[DataRequired(), Length(min=2, max=100)])
    submit   = SubmitField("Register")


# -------------------- LOGIN FORM --------------------
class LoginForm(FlaskForm):
    email    = StringField("Email",    validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit   = SubmitField("Login")


# -------------------- ADD PRODUCT FORM --------------------
# Retailer only sees: Name, Description, Category, Price, Stock, Expiry.
# All ML params (store_tier, demand_type, velocity) are auto-resolved by backend.
class AddProductForm(FlaskForm):

    name = StringField(
        "Product Name",
        validators=[DataRequired(), Length(min=2, max=200)]
    )

    description = TextAreaField(
        "Description (optional)",
        validators=[Length(max=500)]
    )

    category = SelectField("Category", choices=[
        ("Dairy",       "🥛 Dairy & Bakery"),
        ("Bakery",      "🍞 Bakery"),
        ("Snacks",      "🍿 Snacks"),
        ("Canned",      "🥫 Canned / Packaged"),
        ("Cosmetics",   "💄 Cosmetics & Personal Care"),
        ("Beverages",   "🧃 Beverages"),
        ("Household",   "🏠 Household"),
        ("Electronics", "📱 Electronics"),
        ("Clothing",    "👕 Clothing"),
        ("Other",       "📦 Other"),
    ])

    original_price = FloatField(
        "Original Price (₹)",
        validators=[DataRequired(), NumberRange(min=0.01, message="Price must be positive")]
    )

    stock = IntegerField(
        "Stock Quantity",
        validators=[DataRequired(), NumberRange(min=1, message="Stock must be at least 1")]
    )

    expiry_date = DateTimeLocalField(
        "Deal Expires At",
        format="%Y-%m-%dT%H:%M",
        validators=[DataRequired()]
    )

    submit = SubmitField("Launch Deal 🚀")


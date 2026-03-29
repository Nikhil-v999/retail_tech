# DealDrop ⚡
### AI-Powered Hyperlocal Flash Sale Platform
**Team Atomic Blasters — Hackathon 2026**

---

## 🌐 Live Demo
🔗 **[https://dealdrop-yep3.onrender.com](https://dealdrop-yep3.onrender.com)**

---

## 📋 Executive Summary

DealDrop is an **AI-powered hyperlocal marketplace** that connects local retailers with nearby consumers.

- Uses **Machine Learning** for dynamic pricing according to expiry date and demand (velocity)
- Recommends related items for customers according to their wishlist
- Uses **geospatial algorithms** to ensure customers only see deals that are physically accessible within a short timeframe
- **Reduces wastage** of products and increases retailer revenue
- Provides customers with **discounted local products**

---

## ❗ Problem Statement

- Retailers **cannot clear** near-expiry or overstocked inventory
- Customers are **unaware** of nearby deals
- **No real-time** hyperlocal discovery system exists

**Result:**
- Lost revenue for retailers
- Missed savings for customers

---

## ✅ Proposed Solution

DealDrop introduces a **Hyperlocal Relevance Engine**:

- **AI-Driven Pricing** — Automatically calculates optimal discounts
- **Geospatial Discovery** — Shows only nearby deals
- **Recommendation System** — Recommends related items for users according to their wishlist
- **Relevance Score Algorithm** — Ranks products intelligently while showing to the user

---

## 🤖 AI Dynamic Pricing Model — FlashMap

**Model:** Gradient Boosting Regressor

**Input Features:**
| Feature | Description |
|---------|-------------|
| `days_left` | Days until deal closes |
| `stock` | Units remaining |
| `velocity` | Sales speed (units/day) |
| `store_tier` | High / Med / Low traffic city |
| `category` | Dairy / Snacks / Electronics etc. |
| `demand_type` | Essential / Normal / Luxury |

**Output:** Optimal discount percentage (0% to 85%)

> Currently uses simulated training data. After real-world usage, the model will retrain on actual sales data stored in the database.

**Fallback Formula** (when model unavailable):
```
> 24h left  →  10% OFF
12–24h      →  25% OFF
6–12h       →  40% OFF
< 6h        →  60% OFF
```

---

## 📍 Geocoding Infrastructure

- Uses **OpenStreetMap (Nominatim API)**
- Converts addresses to **Latitude & Longitude**

| Node | Location Type |
|------|--------------|
| Retailer | Fixed — set at registration, never changes |
| Customer | Dynamic — can update anytime |

---

## 📐 Haversine Distance Formula

Used to calculate the real-world distance between customer and store:

```
d = 2R × arcsin( sqrt( sin²(Δφ/2) + cos(φ1) × cos(φ2) × sin²(Δλ/2) ) )
```

Where R = 6,371 km (Earth's radius), φ = latitude, λ = longitude.

---

## 🎯 Relevance Score Algorithm

Deals shown to customers are ranked by:

```
Score = 10 + (50 × Discount%) − (10 × Distance_km) + (30 / Days_Left)
```

**Insights:**
- Nearby deals rank higher
- Urgent deals rank higher
- Balanced discount prioritization
- Base score of +10 ensures all products remain visible even with 0% discount

---

## 🔄 System Workflow

**Retailer Side:**
1. Add product to inventory
2. ML model predicts optimal discount
3. Launch deal — goes live instantly to all nearby customers

**Customer Side:**
1. Opens app
2. Sees deals ranked by relevance score
3. Views recommended items based on wishlist
4. Visits store and buys

---

## 💼 Business Impact

- ♻️ Reduces food and product waste
- 💰 Converts losses into revenue for retailers
- 🛍️ Provides affordable goods to customers
- 🚚 No delivery required — **zero logistics cost**

---

## 🏗️ Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Flask, Python |
| Database | SQLite, SQLAlchemy |
| ML Model | Scikit-learn (Gradient Boosting), Pandas, NumPy |
| Geospatial | Geopy (Nominatim), Haversine Formula |
| Frontend | HTML, JavaScript, Bootstrap 5, Jinja2 |
| Auth | Flask-Login, Flask-WTF |
| Deployment | Render |

---

## ✨ Full Feature List

### For Retailers
- 📦 Add products with stock, price, expiry
- 🚀 Launch AI-powered flash deals with one click
- 📊 Live dashboard — active deals, low stock alerts, revenue today
- 📈 Full sales history with customer and price details
- 🔔 Auto-alerts for low stock, expiring soon, zero sales after 6h
- ✏️ Edit products — AI discount recalculates automatically on save
- ⏸️ Pause / reactivate any deal instantly

### For Customers
- 🛒 Live deals feed — all products visible immediately when added
- 📍 Distance-based ranking with km filter (1 / 3 / 5 / 10 / custom)
- ⏳ Live countdown timers on every deal card
- ❤️ Smart Wishlist — semantic matching to new deals using cosine similarity
- 🔔 Notifications — wishlist matches, price drops, new deals nearby
- 🗺️ Update location anytime for fresh distance-aware rankings

---

## 📁 Project Structure

```
dealdrop/
│
├── main.py                       # Flask app — routes, models, ML logic
├── forms.py                      # WTForms definitions
├── wishlist_agent.py             # Background semantic wishlist matcher
├── flashmap_master_model.pkl     # Trained ML discount prediction model
│
├── templates/                    # All HTML templates (Jinja2)
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── retail_dash.html
│   ├── cust_dash.html
│   ├── add_product.html
│   ├── edit_product.html
│   ├── launch_deal.html
│   ├── sales_history.html
│   ├── wishlist.html
│   ├── notifications.html
│   ├── cust_notifications.html
│   ├── update_location.html
│   ├── header.html
│   └── footer.html
│
├── static/
│   ├── css/styles.css
│   └── js/scripts.js
│
├── requirements.txt
├── Procfile
└── .env
```

---

## 🚀 Run Locally

```bash
# 1. Clone
git clone https://github.com/Nikhil-v999/dealdrop.git
cd dealdrop

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file
SECRET_KEY=your-random-secret-key-here
DATABASE_URL=sqlite:///dealdrop99.db

# 5. Run
python main.py
```

Open → **http://localhost:5000**

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/deals/live` | All live products with pricing |
| POST | `/grab_deal/<id>` | Purchase a product |
| GET | `/api/price/<id>` | Live price + urgency |
| POST | `/api/ai_discount_preview` | Preview AI discount |
| POST | `/api/suggest_closing_time` | Smart closing time suggestion |
| GET | `/api/notifications` | User notifications |
| POST | `/api/notifications/mark_read` | Mark notifications read |
| GET | `/api/wishlist` | Customer wishlist items |

---

## 🔮 Future Scope

- 🏙️ Automated store tier classification based on real footfall data
- 🎯 Personalized recommendations using collaborative filtering
- 📡 Geofencing push notifications when entering a deal radius
- 🛒 Purchase history integration for smarter ML retraining

---

## 👥 Team Atomic Blasters

Built with ❤️ for Hackathon 2026

---

## 📄 License

MIT License — free to use, modify, and distribute.

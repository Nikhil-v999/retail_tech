"""
wishlist_agent.py — DealDrop Smart-Watch Wishlist Engine
=========================================================
Semantic matching between user DB wishlist items and newly posted deals.
Uses sentence-transformers (all-MiniLM-L6-v2) for embeddings + cosine sim.
Background processing via threading (no Redis/Celery required).

Architecture:
  • WishlistItem model  — DB-persisted items (item_name + max_price_threshold)
  • WishlistNotifLog    — dedup log (user_id + product_id + sent_at)
  • get_embedding()     — SentenceTransformer embedding helper (cached)
  • cosine_similarity() — manual numpy cosine
  • score_match()       — priority formula: 0.5×sim + 0.3×disc% - 0.2×dist_km
  • trigger_wishlist_matches() — main engine, called in background thread
  • run_in_background() — fire-and-forget thread launcher
"""

import math
import threading
import numpy as np
from datetime import datetime, timezone, timedelta
from functools import lru_cache


# ── Lazy imports so the app boots even if sentence-transformers isn't installed ──
_st_model = None
_ST_AVAILABLE = False

def _load_st_model():
    global _st_model, _ST_AVAILABLE
    if _st_model is not None:
        return _st_model
    try:
        from sentence_transformers import SentenceTransformer
        _st_model = SentenceTransformer("all-MiniLM-L6-v2")
        _ST_AVAILABLE = True
        print("✅  SentenceTransformer (all-MiniLM-L6-v2) loaded for Wishlist Agent.")
        return _st_model
    except Exception as e:
        print(f"⚠️   sentence-transformers unavailable ({e}). "
              "Wishlist Smart-Watch will use keyword fallback.")
        _ST_AVAILABLE = False
        return None


# ═══════════════════════════════════════════════════════
#  EMBEDDING + SIMILARITY
# ═══════════════════════════════════════════════════════

def get_embedding(text: str) -> np.ndarray | None:
    """
    Returns a unit-normalised embedding vector for 'text'.
    Returns None if sentence-transformers is unavailable.
    """
    model = _load_st_model()
    if model is None:
        return None
    return model.encode(text, normalize_embeddings=True)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two pre-normalised unit vectors → [0, 1]."""
    return float(np.clip(np.dot(a, b), 0.0, 1.0))


def keyword_similarity_fallback(text_a: str, text_b: str) -> float:
    """
    Simple token-overlap similarity used when sentence-transformers
    is not installed. Not as smart as cosine sim but prevents silent failures.
    Returns a score in [0, 1].
    """
    a_tokens = set(text_a.lower().split())
    b_tokens = set(text_b.lower().split())
    if not a_tokens or not b_tokens:
        return 0.0
    intersection = a_tokens & b_tokens
    union = a_tokens | b_tokens
    return len(intersection) / len(union)


# ═══════════════════════════════════════════════════════
#  HAVERSINE (self-contained, no circular import)
# ═══════════════════════════════════════════════════════

def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6_371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi       = math.radians(lat2 - lat1)
    dlambda    = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.asin(math.sqrt(a))


# ═══════════════════════════════════════════════════════
#  PRIORITY FORMULA
# ═══════════════════════════════════════════════════════

def score_match(similarity: float, discount_pct: float, distance_km: float | None) -> float:
    """
    Priority = 0.5 × similarity  +  0.3 × (discount_pct / 100)  −  0.2 × distance_km

    If distance is unknown (None), we use 0 km (best-case assumption).
    Threshold: > 0.65 → notify.
    """
    dist = min(distance_km, 10.0) if distance_km is not None else 0.0
    return (0.5 * similarity) + (0.3 * (discount_pct / 100.0)) - (0.2 * dist)


# ═══════════════════════════════════════════════════════
#  MAIN ENGINE
# ═══════════════════════════════════════════════════════

SIMILARITY_THRESHOLD = 0.45   # semantic sim gate — MiniLM handles fuzzy well at this level
PRIORITY_THRESHOLD   = 0.38   # priority score gate after weighting sim + discount - distance
DEDUP_HOURS          = 24     # notification cap per user-deal pair


def trigger_wishlist_matches(app, db, Product, User, WishlistItem,
                              WishlistNotifLog, Notification):
    """
    Called in a background thread immediately after a new deal is committed.

    For each active deal that was just posted (deal_active=True, stock>0):
      1. Embed the deal name.
      2. Compare against every DB wishlist item (semantic cosine or keyword fallback).
      3. Apply Relevance Filter (price, distance gating).
      4. Compute Priority score — notify if > 0.65.
      5. Deduplicate within 24-hour window.
      6. Push notification with low-stock "Losing Fast!" flag if needed.
    """
    with app.app_context():
        try:
            now      = datetime.now(timezone.utc)
            cutoff   = now - timedelta(hours=DEDUP_HOURS)

            # Fetch all active live deals posted in the last 10 minutes
            # (avoids re-scanning every deal on each call)
            recent_cutoff = now - timedelta(minutes=10)
            new_deals = Product.query.filter(
                Product.deal_active  == True,
                Product.stock        >  0,
                Product.expiry_date  >  now,
                Product.created_at   >= recent_cutoff,
            ).all()

            if not new_deals:
                return

            # Fetch all wishlist items with their owners
            wishlist_items = (
                WishlistItem.query
                .join(User, WishlistItem.user_id == User.id)
                .filter(User.role == 'customer')
                .all()
            )
            if not wishlist_items:
                return

            # Pre-compute user objects for distance lookups
            user_map = {w.user_id: w.user for w in wishlist_items}

            for deal in new_deals:
                # Embed the deal name + category for richer matching
                deal_text    = f"{deal.name} {deal.category or ''}".strip()
                deal_emb     = get_embedding(deal_text)
                discount_pct = deal.discount_percent

                retailer_lat = deal.retailer.lat if deal.retailer else None
                retailer_lon = deal.retailer.lon if deal.retailer else None
                low_stock    = deal.stock < 5

                for wish in wishlist_items:
                    # Skip if the customer is the retailer themselves
                    if wish.user_id == deal.retailer_id:
                        continue

                    # ── Dedup check ──────────────────────────────────────────
                    already_sent = WishlistNotifLog.query.filter(
                        WishlistNotifLog.user_id    == wish.user_id,
                        WishlistNotifLog.product_id == deal.id,
                        WishlistNotifLog.sent_at    >= cutoff,
                    ).first()
                    if already_sent:
                        continue

                    # ── Semantic similarity ──────────────────────────────────
                    wish_text = wish.item_name
                    if deal_emb is not None:
                        wish_emb = get_embedding(wish_text)
                        if wish_emb is None:
                            sim = keyword_similarity_fallback(deal_text, wish_text)
                        else:
                            sim = cosine_similarity(deal_emb, wish_emb)
                    else:
                        sim = keyword_similarity_fallback(deal_text, wish_text)

                    if sim < SIMILARITY_THRESHOLD:
                        continue   # not a semantic match

                    # ── Price filter ─────────────────────────────────────────
                    price_ok = (
                        (wish.max_price_threshold is not None and
                         deal.current_price <= wish.max_price_threshold)
                        or discount_pct > 40
                    )
                    if not price_ok:
                        continue

                    # ── Distance calculation ─────────────────────────────────
                    user = user_map.get(wish.user_id)
                    if (user and user.lat is not None and user.lon is not None
                            and retailer_lat is not None and retailer_lon is not None):
                        dist_km = round(_haversine(user.lat, user.lon,
                                                   retailer_lat, retailer_lon), 2)
                    else:
                        dist_km = None

                    # Distance gating: > 3 km requires sim > 0.55
                    if dist_km is not None and dist_km > 3.0 and sim <= 0.55:
                        continue

                    # ── Priority score ───────────────────────────────────────
                    priority = score_match(sim, discount_pct, dist_km)
                    if priority <= PRIORITY_THRESHOLD:
                        continue

                    # ── Build notification payload ───────────────────────────
                    dist_str  = f" · {dist_km} km away" if dist_km is not None else ""
                    price_str = f"₹{round(deal.current_price)}"
                    disc_str  = f"{discount_pct}% OFF"
                    low_str   = " 🔥 Losing Fast!" if low_stock else ""

                    title = f"🎯 Wishlist Match: {deal.name}{low_str}"
                    body  = (
                        f"A deal matching '{wish.item_name}' just dropped — "
                        f"{price_str} ({disc_str}){dist_str}. "
                        f"Match score: {round(sim*100)}%."
                    )
                    if wish.max_price_threshold and deal.current_price <= wish.max_price_threshold:
                        body += f" Under your ₹{wish.max_price_threshold} threshold!"

                    # ── Push notification + dedup log ─────────────────────────
                    notif = Notification(
                        user_id=wish.user_id,
                        title=title,
                        body=body,
                        ntype='deal',
                    )
                    log = WishlistNotifLog(
                        user_id=wish.user_id,
                        product_id=deal.id,
                        sent_at=now,
                    )
                    db.session.add(notif)
                    db.session.add(log)

            db.session.commit()
            print("✅  Wishlist Smart-Watch scan complete.")

        except Exception as exc:
            print(f"❌  Wishlist Agent error: {exc}")
            try:
                db.session.rollback()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════
#  FIRE-AND-FORGET THREAD LAUNCHER
# ═══════════════════════════════════════════════════════

def run_in_background(app, db, Product, User, WishlistItem,
                      WishlistNotifLog, Notification):
    """
    Spawns a daemon thread to run trigger_wishlist_matches().
    The thread is daemon=True so it never blocks app shutdown.
    """
    t = threading.Thread(
        target=trigger_wishlist_matches,
        args=(app, db, Product, User, WishlistItem, WishlistNotifLog, Notification),
        daemon=True,
        name="wishlist-agent",
    )
    t.start()

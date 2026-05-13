"""Stripe payments for The Network Supporter tier ($19 for 30 days)."""
import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header, Request
from pydantic import BaseModel, Field

from emergentintegrations.payments.stripe.checkout import (
    StripeCheckout,
    CheckoutSessionRequest,
)

from services.auth_helpers import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["payments"])

# Server-defined supporter packages (NEVER take amount from frontend)
PACKAGES = {
    "monthly": {
        "amount": float(os.environ.get("SUPPORTER_MONTHLY_USD", "10.00")),
        "period_days": 30,
        "label": "Monthly",
    },
    "yearly": {
        "amount": float(os.environ.get("SUPPORTER_YEARLY_USD", "100.00")),
        "period_days": 365,
        "label": "Yearly",
    },
}
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY")


class CheckoutRequest(BaseModel):
    origin_url: str = Field(min_length=1, max_length=400)
    tier: str = Field(default="monthly")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def setup(db):
    async def _user(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        return await get_current_user(db, session_token, authorization)

    def _checkout(request: Request) -> StripeCheckout:
        host_url = str(request.base_url).rstrip("/")
        webhook_url = f"{host_url}/api/webhook/stripe"
        return StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)

    @router.post("/payments/checkout")
    async def create_checkout(payload: CheckoutRequest, request: Request, user=Depends(_user)):
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Membership not approved")
        pkg = PACKAGES.get(payload.tier)
        if not pkg:
            raise HTTPException(status_code=400, detail="Unknown tier")
        origin = payload.origin_url.rstrip("/")
        success_url = f"{origin}/upgrade/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{origin}/upgrade"

        try:
            sc = _checkout(request)
            req = CheckoutSessionRequest(
                amount=pkg["amount"],
                currency="usd",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "user_id": user["user_id"],
                    "email": user["email"],
                    "tier": payload.tier,
                    "period_days": str(pkg["period_days"]),
                },
            )
            session = await sc.create_checkout_session(req)
        except Exception:
            logger.exception("Stripe checkout failed")
            raise HTTPException(status_code=502, detail="Could not start checkout")

        # Record a pending payment_transaction
        await db.payment_transactions.insert_one({
            "transaction_id": f"tx_{uuid.uuid4().hex[:12]}",
            "session_id": session.session_id,
            "user_id": user["user_id"],
            "email": user["email"],
            "amount": pkg["amount"],
            "currency": "usd",
            "tier": payload.tier,
            "period_days": pkg["period_days"],
            "payment_status": "initiated",
            "status": "open",
            "metadata": {"source": "web_checkout"},
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        })
        return {"url": session.url, "session_id": session.session_id, "tier": payload.tier, "amount": pkg["amount"]}

    @router.get("/payments/status/{session_id}")
    async def status(session_id: str, request: Request, user=Depends(_user)):
        """Poll status. On success, extend the user's supporter_until and mark tx complete (idempotent)."""
        record = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
        if not record:
            raise HTTPException(status_code=404, detail="Transaction not found")
        if record["user_id"] != user["user_id"] and not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Not your transaction")

        try:
            sc = _checkout(request)
            cs = await sc.get_checkout_status(session_id)
        except Exception:
            logger.exception("Stripe status fetch failed")
            raise HTTPException(status_code=502, detail="Could not check status")

        # Idempotency: only grant once
        already_paid = record.get("payment_status") == "paid"
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {
                "status": cs.status,
                "payment_status": cs.payment_status,
                "amount_total": cs.amount_total,
                "currency_actual": cs.currency,
                "updated_at": _now_iso(),
            }},
        )
        if cs.payment_status == "paid" and not already_paid:
            now = datetime.now(timezone.utc)
            existing_until = None
            udoc = await db.users.find_one({"user_id": record["user_id"]}, {"_id": 0})
            if udoc and udoc.get("supporter_until"):
                try:
                    existing_until = datetime.fromisoformat(udoc["supporter_until"])
                    if existing_until.tzinfo is None:
                        existing_until = existing_until.replace(tzinfo=timezone.utc)
                except Exception:
                    existing_until = None
            base = max(now, existing_until) if existing_until else now
            new_until = base + timedelta(days=record.get("period_days") or PACKAGES["monthly"]["period_days"])
            await db.users.update_one(
                {"user_id": record["user_id"]},
                {"$set": {
                    "supporter_until": new_until.isoformat(),
                    "supporter_since": (udoc or {}).get("supporter_since") or now.isoformat(),
                }},
            )
            logger.info("Granted supporter to %s until %s", record["email"], new_until.isoformat())

        return {
            "session_id": session_id,
            "status": cs.status,
            "payment_status": cs.payment_status,
            "amount_total": cs.amount_total,
            "currency": cs.currency,
            "tier": record.get("tier"),
        }

    @router.post("/webhook/stripe")
    async def stripe_webhook(request: Request):
        body = await request.body()
        sig = request.headers.get("Stripe-Signature") or request.headers.get("stripe-signature")
        try:
            sc = _checkout(request)
            event = await sc.handle_webhook(body, sig)
        except Exception:
            logger.exception("Webhook verification failed")
            raise HTTPException(status_code=400, detail="Invalid webhook")

        session_id = getattr(event, "session_id", None)
        payment_status = getattr(event, "payment_status", None)
        event_type = getattr(event, "event_type", None)

        if not session_id:
            return {"ok": True, "skipped": True}

        record = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
        if not record:
            logger.warning("Webhook for unknown session_id %s", session_id)
            return {"ok": True}

        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {
                "webhook_event_type": event_type,
                "payment_status": payment_status or record.get("payment_status"),
                "updated_at": _now_iso(),
            }},
        )

        if payment_status == "paid" and record.get("payment_status") != "paid":
            now = datetime.now(timezone.utc)
            udoc = await db.users.find_one({"user_id": record["user_id"]}, {"_id": 0})
            existing_until = None
            if udoc and udoc.get("supporter_until"):
                try:
                    existing_until = datetime.fromisoformat(udoc["supporter_until"])
                    if existing_until.tzinfo is None:
                        existing_until = existing_until.replace(tzinfo=timezone.utc)
                except Exception:
                    existing_until = None
            base = max(now, existing_until) if existing_until else now
            new_until = base + timedelta(days=record.get("period_days") or PACKAGES["monthly"]["period_days"])
            await db.users.update_one(
                {"user_id": record["user_id"]},
                {"$set": {
                    "supporter_until": new_until.isoformat(),
                    "supporter_since": (udoc or {}).get("supporter_since") or now.isoformat(),
                }},
            )
            await db.payment_transactions.update_one(
                {"session_id": session_id},
                {"$set": {"payment_status": "paid", "granted_at": _now_iso()}},
            )

        return {"ok": True, "event_type": event_type}

    @router.get("/me/subscription")
    async def my_subscription(user=Depends(_user)):
        udoc = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
        now_iso = _now_iso()
        until = (udoc or {}).get("supporter_until")
        is_active = bool(until and until > now_iso)
        return {
            "is_supporter": is_active,
            "supporter_until": until,
            "supporter_since": (udoc or {}).get("supporter_since"),
            "tiers": [
                {"id": "monthly", "amount": PACKAGES["monthly"]["amount"], "period_days": 30, "label": "Monthly"},
                {"id": "yearly", "amount": PACKAGES["yearly"]["amount"], "period_days": 365, "label": "Yearly"},
            ],
        }

    return router

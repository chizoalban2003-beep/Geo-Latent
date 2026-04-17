"""
geolatent/billing.py
Stripe billing, tier gates, and usage metering.

Exposes:
  GET  /billing/plans              — available tier definitions
  GET  /billing/subscription       — current tenant subscription
  POST /billing/checkout           — create Stripe checkout session
  POST /billing/portal             — create Stripe customer portal session
  POST /billing/webhook            — Stripe webhook handler
  GET  /billing/usage              — current-period usage summary
  GET  /billing/tier_check/{gate}  — check if tenant has access to a feature gate

Tier structure:
  free      — 100 simulation steps/month, no SDK exports, no bundles
  research  — unlimited steps, bundles, reproducibility exports, 5 GB dataset storage
  studio    — research + SDK exports, Unity/Unreal/Godot integration, priority support
  enterprise— studio + SSO, dedicated instance, SLA, custom data retention
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Header

router = APIRouter()

_STRIPE_SECRET   = os.environ.get("STRIPE_SECRET_KEY", "")
_STRIPE_WEBHOOK  = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
_STRIPE_PRICES: dict[str, str] = {
    "research":   os.environ.get("STRIPE_PRICE_RESEARCH",   ""),
    "studio":     os.environ.get("STRIPE_PRICE_STUDIO",     ""),
    "enterprise": os.environ.get("STRIPE_PRICE_ENTERPRISE", ""),
}
# Public URL for Stripe redirect — falls back to localhost for local dev
_PUBLIC_URL = os.environ.get("GEOLATENT_PUBLIC_URL", "http://localhost:8001").rstrip("/")

# In-memory subscription cache (backed by DB in production)
_subscriptions: dict[str, dict] = {}   # tenant_id → subscription info

def _effective_tier(tenant_id: str) -> str:
    """Return tier, upgrading to 'studio' in dev/demo mode."""
    # Read at call-time so tests and runtime env changes take effect immediately
    if os.environ.get("GEOLATENT_MODE", "production").lower() in ("dev", "demo"):
        return "studio"
    return _subscriptions.get(tenant_id, {}).get("tier", "free")


# ---------------------------------------------------------------------------
# Tier definitions
# ---------------------------------------------------------------------------

PLANS = {
    "free": {
        "name":           "Free",
        "price_monthly":  0,
        "currency":       "usd",
        "limits": {
            "steps_per_month":   100,
            "datasets_mb":       50,
            "sdk_exports":       False,
            "repro_bundles":     False,
            "narratives":        3,
            "gaming_ws":         False,
            "education_export":  False,
            "biome_lore_llm":    False,
            "oidc_sso":          False,
        },
        "description": "Try geo-latent with sample datasets. No credit card required.",
    },
    "research": {
        "name":           "Research",
        "price_monthly":  49,
        "currency":       "usd",
        "limits": {
            "steps_per_month":   -1,           # unlimited
            "datasets_mb":       5120,
            "sdk_exports":       False,
            "repro_bundles":     True,
            "narratives":        -1,
            "gaming_ws":         False,
            "education_export":  True,
            "biome_lore_llm":    True,
            "oidc_sso":          False,
        },
        "description": "Full simulation + reproducibility bundles. Ideal for academic teams.",
        "stripe_price_id": _STRIPE_PRICES.get("research"),
    },
    "studio": {
        "name":           "Studio",
        "price_monthly":  199,
        "currency":       "usd",
        "limits": {
            "steps_per_month":   -1,
            "datasets_mb":       51200,
            "sdk_exports":       True,
            "repro_bundles":     True,
            "narratives":        -1,
            "gaming_ws":         True,
            "education_export":  True,
            "biome_lore_llm":    True,
            "oidc_sso":          False,
        },
        "description": "SDK exports for Unity/Unreal/Godot. Gaming + entertainment integrations.",
        "stripe_price_id": _STRIPE_PRICES.get("studio"),
    },
    "enterprise": {
        "name":           "Enterprise",
        "price_monthly":  None,   # contact sales
        "currency":       "usd",
        "limits": {
            "steps_per_month":   -1,
            "datasets_mb":       -1,
            "sdk_exports":       True,
            "repro_bundles":     True,
            "narratives":        -1,
            "gaming_ws":         True,
            "education_export":  True,
            "biome_lore_llm":    True,
            "oidc_sso":          True,
        },
        "description": "Dedicated instance, SSO, SLA, custom data retention. Contact sales.",
        "stripe_price_id": _STRIPE_PRICES.get("enterprise"),
    },
}


# ---------------------------------------------------------------------------
# Tier gate helper (used by other routers)
# ---------------------------------------------------------------------------

def get_tenant_tier(tenant_id: str) -> str:
    """Return the current tier string for a tenant."""
    return _effective_tier(tenant_id)


def check_gate(tenant_id: str, gate: str) -> bool:
    """Return True if the tenant's plan allows the given feature gate."""
    tier  = get_tenant_tier(tenant_id)
    plan  = PLANS.get(tier, PLANS["free"])
    value = plan["limits"].get(gate, False)
    if value is True or value == -1:
        return True
    if isinstance(value, int) and value > 0:
        return True
    return False


def require_gate(tenant_id: str, gate: str, tier_needed: str = "research") -> None:
    """Raise 402 if the tenant cannot access a feature gate."""
    if not check_gate(tenant_id, gate):
        raise HTTPException(
            402,
            f"Feature '{gate}' requires the {tier_needed} plan or above. "
            f"Upgrade at POST /billing/checkout."
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/plans")
async def list_plans():
    return {"plans": PLANS}


@router.get("/subscription")
async def get_subscription(request: Request):
    auth = getattr(request.state, "auth", {})
    tenant_id = auth.get("tenant_id", "unknown")
    sub = _subscriptions.get(tenant_id, {"tier": "free", "status": "active"})
    plan = PLANS.get(sub.get("tier", "free"), PLANS["free"])
    return {
        "tenant_id": tenant_id,
        "tier":      sub.get("tier", "free"),
        "status":    sub.get("status", "active"),
        "limits":    plan["limits"],
    }


@router.get("/tier_check/{gate}")
async def tier_check(gate: str, request: Request):
    """Check if the requesting tenant can access a feature gate."""
    try:
        from geolatent.auth import parse_request_auth
        auth = await parse_request_auth(request)
    except HTTPException:
        auth = {"tenant_id": "anon"}
    tenant_id = auth.get("tenant_id", "anon")
    allowed = check_gate(tenant_id, gate)
    return {"tenant_id": tenant_id, "gate": gate, "allowed": allowed,
            "tier": get_tenant_tier(tenant_id)}


@router.post("/checkout")
async def create_checkout(request: Request):
    """Create a Stripe Checkout session for a plan upgrade."""
    if not _STRIPE_SECRET:
        raise HTTPException(501, "Stripe not configured — set STRIPE_SECRET_KEY")
    try:
        from geolatent.auth import parse_request_auth
        auth = await parse_request_auth(request)
    except HTTPException:
        raise HTTPException(401, "Authentication required for billing")

    body      = await request.json()
    plan_name = body.get("plan", "research")
    plan      = PLANS.get(plan_name)
    if not plan or not plan.get("stripe_price_id"):
        raise HTTPException(400, f"Plan '{plan_name}' not available for checkout")

    import urllib.request, urllib.parse
    data = urllib.parse.urlencode({
        "mode":                       "subscription",
        "line_items[0][price]":       plan["stripe_price_id"],
        "line_items[0][quantity]":    "1",
        "success_url":                body.get("success_url", f"{_PUBLIC_URL}/?checkout=success"),
        "cancel_url":                 body.get("cancel_url",  f"{_PUBLIC_URL}/?checkout=cancel"),
        "client_reference_id":        auth.get("tenant_id", ""),
        "metadata[tenant_id]":        auth.get("tenant_id", ""),
    }).encode()

    req = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=data,
        headers={"Authorization": f"Bearer {_STRIPE_SECRET}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        session = json.loads(resp.read())
    return {"checkout_url": session["url"], "session_id": session["id"]}


@router.post("/portal")
async def create_portal(request: Request):
    """Create a Stripe Customer Portal session for subscription management."""
    if not _STRIPE_SECRET:
        raise HTTPException(501, "Stripe not configured")
    try:
        from geolatent.auth import parse_request_auth
        auth = await parse_request_auth(request)
    except HTTPException:
        raise HTTPException(401, "Authentication required")

    tenant_id   = auth.get("tenant_id", "")
    customer_id = _subscriptions.get(tenant_id, {}).get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(404, "No Stripe customer found for this tenant")

    import urllib.request, urllib.parse
    data = urllib.parse.urlencode({
        "customer":    customer_id,
        "return_url":  f"{_PUBLIC_URL}/",
    }).encode()
    req = urllib.request.Request(
        "https://api.stripe.com/v1/billing_portal/sessions",
        data=data,
        headers={"Authorization": f"Bearer {_STRIPE_SECRET}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        session = json.loads(resp.read())
    return {"portal_url": session["url"]}


@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: Optional[str] = Header(None)):
    """Stripe webhook — updates subscription tier on successful payment."""
    if not _STRIPE_WEBHOOK:
        raise HTTPException(501, "Stripe webhook secret not configured")

    body = await request.body()

    # Signature verification
    try:
        parts  = {p.split("=")[0]: p.split("=")[1] for p in (stripe_signature or "").split(",")}
        ts     = int(parts.get("t", "0"))
        v1_sig = parts.get("v1", "")
        signed = f"{ts}.".encode() + body
        expected = hmac.new(_STRIPE_WEBHOOK.encode(), signed, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, v1_sig):
            raise HTTPException(400, "Invalid signature")
        if abs(time.time() - ts) > 300:
            raise HTTPException(400, "Webhook timestamp too old")
    except (KeyError, ValueError):
        raise HTTPException(400, "Malformed webhook signature")

    event = json.loads(body)
    _handle_stripe_event(event)
    return {"received": True}


def _handle_stripe_event(event: dict) -> None:
    """Update in-memory subscription state from Stripe events."""
    etype = event.get("type", "")
    data  = event.get("data", {}).get("object", {})

    if etype in ("customer.subscription.created", "customer.subscription.updated"):
        tenant_id   = data.get("metadata", {}).get("tenant_id")
        customer_id = data.get("customer")
        price_id    = (data.get("items", {}).get("data") or [{}])[0].get("price", {}).get("id", "")
        # Reverse-lookup tier from price ID
        tier = "free"
        for t, pid in _STRIPE_PRICES.items():
            if pid and pid == price_id:
                tier = t
                break
        if tenant_id:
            _subscriptions[tenant_id] = {
                "tier":               tier,
                "status":             data.get("status", "active"),
                "stripe_customer_id": customer_id,
                "updated_at":         time.time(),
            }

    elif etype == "customer.subscription.deleted":
        tenant_id = data.get("metadata", {}).get("tenant_id")
        if tenant_id and tenant_id in _subscriptions:
            _subscriptions[tenant_id]["tier"]   = "free"
            _subscriptions[tenant_id]["status"] = "cancelled"


@router.get("/usage")
async def usage_summary(request: Request):
    """Current billing period usage for the requesting tenant."""
    try:
        from geolatent.auth import parse_request_auth
        auth = await parse_request_auth(request)
    except HTTPException:
        raise HTTPException(401, "Authentication required")

    tenant_id = auth.get("tenant_id", "")
    pool = request.app.state.db_pool

    if pool:
        try:
            from geolatent.persistence_db import get_usage_summary
            async with pool.connection() as conn:
                since = time.time() - 86400 * 30
                usage = await get_usage_summary(conn, tenant_id, since)
        except Exception:
            usage = {}
    else:
        usage = {}

    tier  = get_tenant_tier(tenant_id)
    limits = PLANS.get(tier, PLANS["free"])["limits"]
    return {
        "tenant_id":    tenant_id,
        "tier":         tier,
        "period":       "last_30_days",
        "usage":        usage,
        "limits":       limits,
    }

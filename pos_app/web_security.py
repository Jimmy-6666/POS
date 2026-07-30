"""Response and session protections for the approved public hostnames."""

from __future__ import annotations

from flask import request
from flask.sessions import SecureCookieSessionInterface
from werkzeug.exceptions import SecurityError

from .public_host_access import public_surface


class PublicHostSessionInterface(SecureCookieSessionInterface):
    """Require HTTPS-only Flask session cookies on either public hostname."""

    def get_cookie_secure(self, app):
        if request.is_secure:
            return True
        try:
            return public_surface() is not None
        except SecurityError:
            return False


def _customer_csp(legacy_inline=False, allow_same_origin_frame=False):
    script_src = "script-src 'self'" + (" 'unsafe-inline'" if legacy_inline else "") + " https://static.line-scdn.net"
    return "; ".join((
        "default-src 'self'",
        "base-uri 'self'",
        "object-src 'none'",
        "frame-ancestors 'self'" if allow_same_origin_frame else "frame-ancestors 'none'",
        "form-action 'self'",
        script_src,
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: https:",
        "font-src 'self' data:",
        "media-src 'self'",
        "connect-src 'self' https://*.line.me",
    ))


def _admin_csp():
    """Keep legacy Admin screens working while blocking third-party scripts."""

    return "; ".join((
        "default-src 'self'",
        "base-uri 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
        "script-src 'self' 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: https:",
        "font-src 'self' data:",
        "media-src 'self'",
        "connect-src 'self'",
    ))


def add_public_security_headers(response):
    try:
        surface = public_surface()
    except SecurityError:
        return response
    if surface is None:
        return response

    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    embedded_customer_policy = (
        surface == "customer"
        and request.endpoint == "online.privacy_policy"
        and request.args.get("embedded") == "1"
    )
    response.headers["X-Frame-Options"] = "SAMEORIGIN" if embedded_customer_policy else "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), payment=(), usb=()"
    response.headers["Content-Security-Policy"] = (
        _customer_csp(
            request.endpoint == "online.order_detail",
            allow_same_origin_frame=embedded_customer_policy,
        )
        if surface == "customer"
        else _admin_csp()
    )
    if request.endpoint != "static":
        response.headers["Cache-Control"] = "no-store, private, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


def init_app(app):
    app.session_interface = PublicHostSessionInterface()
    app.after_request(add_public_security_headers)

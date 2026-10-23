"""Paramètres applicatifs globaux (clé/valeur) + filtre d'accès par IP publique."""
from __future__ import annotations

import ipaddress

from flask import request

from models import Setting, db


def get_param(key: str, default=None):
    try:
        row = db.session.get(Setting, key)
        return row.value if row and row.value is not None else default
    except Exception:
        return default


def set_param(key: str, value: str) -> None:
    row = db.session.get(Setting, key)
    if row is None:
        db.session.add(Setting(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


def ip_client() -> str:
    """IP publique de l'appelant : 1er maillon de X-Forwarded-For sinon remote_addr."""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or ""


def est_loopback(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def parse_liste_ips(txt: str) -> list[str]:
    out: list[str] = []
    for part in (txt or "").replace(",", "\n").replace(";", "\n").split("\n"):
        p = part.strip()
        if p and not p.startswith("#"):
            out.append(p)
    return out


def ip_autorisee(ip: str, liste: list[str]) -> bool:
    """Vrai si `ip` correspond à une entrée (IP exacte ou réseau CIDR)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for e in liste:
        try:
            if "/" in e:
                if addr in ipaddress.ip_network(e, strict=False):
                    return True
            elif addr == ipaddress.ip_address(e):
                return True
        except ValueError:
            if e == ip:
                return True
    return False

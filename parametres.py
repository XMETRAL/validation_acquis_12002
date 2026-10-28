"""Paramètres applicatifs globaux (clé/valeur) + filtre d'accès par IP publique."""
from __future__ import annotations

import ipaddress
import socket

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


def parse_entrees(txt: str) -> list[dict]:
    """Liste des entrées autorisées : {ip, desc}.

    Format par ligne : « IP/CIDR | description » (description facultative).
    Compat : une ligne sans « | » peut contenir plusieurs IP séparées par
    une virgule ou un point-virgule (sans description).
    Les lignes vides et celles commençant par « # » sont ignorées.
    """
    entrees: list[dict] = []
    for raw in (txt or "").split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            ip, _, desc = line.partition("|")
            ip = ip.strip()
            if ip:
                entrees.append({"ip": ip, "desc": desc.strip()})
        else:
            for tok in line.replace(",", "\n").replace(";", "\n").split("\n"):
                tok = tok.strip()
                if tok:
                    entrees.append({"ip": tok, "desc": ""})
    return entrees


def parse_liste_ips(txt: str) -> list[str]:
    """IP/CIDR autorisés (sans les descriptions), pour la comparaison d'accès."""
    return [e["ip"] for e in parse_entrees(txt)]


def nom_dns(ip: str, timeout: float = 1.5) -> str:
    """Nom DNS (PTR) associé à une IP, au mieux. Chaîne vide si indisponible.

    Note : HTTP ne transmet pas le nom de la machine cliente ; c'est le nom
    DNS inverse (quand il est configuré), pas le nom Windows du poste.
    """
    if not ip:
        return ""
    old = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""
    finally:
        socket.setdefaulttimeout(old)


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

from __future__ import annotations

import re
import unicodedata
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


MUNICIPALITIES = {
    "2929206": "São Francisco do Conde",
    "2904902": "Cachoeira",
    "2928604": "Santo Amaro",
    "2929750": "Saubara",
    # RIDE Petrolina-Juazeiro (Decreto 10.296/2020).
    "2611101": "Petrolina",
    "2608750": "Lagoa Grande",
    "2609808": "Orocó",
    "2612604": "Santa Maria da Boa Vista",
    "2918407": "Juazeiro",
    "2907202": "Casa Nova",
    "2909901": "Curaçá",
    "2930774": "Sobradinho",
}

FOCUS_RULES = json.loads((Path(__file__).with_name("focus_rules.json")).read_text(encoding="utf-8"))


POSITIVE_TERMS = {
    "fibra optica": 36,
    "link dedicado": 40,
    "acesso a internet": 34,
    "internet": 22,
    "telecomunicacao": 30,
    "telecom": 28,
    "banda larga": 32,
    "conectividade": 28,
    "rede de dados": 30,
    "cabeamento estruturado": 32,
    "cabeamento": 18,
    "lan": 15,
    "wan": 18,
    "wifi": 24,
    "wi-fi": 24,
    "wireless": 22,
    "hotspot": 22,
    "cftv": 24,
    "videomonitoramento": 25,
    "camera ip": 24,
    "switch": 20,
    "roteador": 22,
    "router": 20,
    "firewall": 18,
    "olt": 34,
    "onu": 30,
    "ont": 30,
    "ftth": 36,
    "gpon": 34,
    "sfp": 25,
    "transceiver": 25,
    "rack": 16,
    "patch panel": 20,
    "cordao optico": 25,
    "drop optico": 28,
    "fusao de fibra": 34,
    "emenda optica": 30,
    "infraestrutura de rede": 30,
    "manutencao de rede": 28,
    "ip publico": 20,
    "vpn": 20,
    "mpls": 28,
    "telefonia ip": 26,
    "voip": 26,
    "sip": 20,
    "pabx ip": 25,
    "data center": 18,
    "datacenter": 18,
    "nobreak": 14,
}


NEGATIVE_TERMS = {
    "internet para pesquisa de precos": -35,
    "publicacao em jornal": -28,
    "agencia de publicidade": -35,
    "material grafico": -30,
    "generos alimenticios": -45,
    "medicamentos": -45,
    "combustivel": -45,
    "locacao de veiculos": -35,
    "material de construcao": -35,
}


CATEGORIES = {
    "Fibra & FTTH": [
        "fibra",
        "ftth",
        "gpon",
        "olt",
        "onu",
        "ont",
        "sfp",
        "optico",
    ],
    "Links & Internet": [
        "link dedicado",
        "internet",
        "banda larga",
        "conectividade",
        "mpls",
    ],
    "Redes & Wi-Fi": [
        "rede de dados",
        "cabeamento",
        "switch",
        "roteador",
        "wifi",
        "wi-fi",
        "wireless",
        "lan",
        "wan",
    ],
    "Segurança & CFTV": [
        "cftv",
        "videomonitoramento",
        "camera ip",
    ],
    "Telefonia IP": [
        "telefonia ip",
        "voip",
        "sip",
        "pabx ip",
    ],
    "Infraestrutura TI": [
        "rack",
        "patch panel",
        "firewall",
        "vpn",
        "datacenter",
        "data center",
        "nobreak",
    ],
}


def normalize(text: Optional[str]) -> str:
    value = unicodedata.normalize("NFKD", text or "")
    value = "".join(
        char for char in value
        if not unicodedata.combining(char)
    )
    value = value.lower()
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _contains_term(text: str, term: str) -> bool:
    normalized_term = normalize(term)

    # Exige fronteira real de palavra.
    # Ex.: "ont" NÃO pode casar com "contratacao".
    pattern = (
        r"(?<![a-z0-9])"
        + re.escape(normalized_term)
        + r"(?![a-z0-9])"
    )

    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def score_relevance(
    title: str,
    description: str,
) -> Tuple[int, List[str], str]:

    text = normalize("{} {}".format(title, description))

    score = 0
    hits: List[str] = []

    for term, points in POSITIVE_TERMS.items():
        if _contains_term(text, term):
            score += points
            hits.append(term)

    for term, points in NEGATIVE_TERMS.items():
        if _contains_term(text, term):
            score += points

    score = max(0, min(100, score))

    category = "Outros serviços correlatos"
    best = 0

    for name, terms in CATEGORIES.items():
        count = sum(
            1 for term in terms
            if _contains_term(text, term)
        )

        if count > best:
            category = name
            best = count

    return score, sorted(set(hits))[:12], category


def classify_focus(title: str, description: str, municipality_code: str) -> Tuple[int, List[str], str, Optional[str]]:
    """Conservative business fit; the same rules are used by the cloud dashboard.

    A tracking tender is relevant in either region. Telecom is relevant only near
    Santo Amaro. Generic IT, CCTV and vehicle purchases are deliberately excluded.
    """
    text = normalize("{} {}".format(title, description))
    vehicle = FOCUS_RULES["vehicle"]
    vehicle_is_bundled = any(_contains_term(normalize(title), term) for term in vehicle["unrelated_primary_objects"])
    direct = sorted({normalize(term) for term in vehicle["direct"] if _contains_term(text, term)})
    context = sorted({normalize(term) for term in vehicle["context"] if _contains_term(text, term)})
    signal = sorted({normalize(term) for term in vehicle["signal"] if _contains_term(text, term)})
    if not vehicle_is_bundled and municipality_code in FOCUS_RULES["local_codes"] + FOCUS_RULES["regional_codes"] and (direct or (context and signal)):
        hits = direct or (context[:2] + signal[:2])
        return min(100, 75 + 5 * (len(hits) - 1)), hits[:12], "Monitoramento veicular", "AutoControl"

    if municipality_code in FOCUS_RULES["local_codes"]:
        matches = {
            category: sorted({normalize(term) for term in terms if _contains_term(text, term)})
            for category, terms in FOCUS_RULES["telecom"].items()
        }
        labels = {
            "fiber": "Fibra & FTTH",
            "internet": "Links & Internet",
            "network": "Redes & Wi-Fi",
            "telephony": "Telefonia IP",
        }
        strongest = max(matches, key=lambda category: len(matches[category]))
        hits = sorted({term for found in matches.values() for term in found})
        if hits:
            return min(100, 65 + 7 * (len(hits) - 1)), hits[:12], labels[strongest], "Ti.Net"

    return 0, [], "Fora do foco", None


def opportunity_status(end_date: Optional[str]) -> str:
    if not end_date:
        return "desconhecido"

    try:
        deadline = datetime.fromisoformat(
            end_date.replace("Z", "+00:00")
        ).date()

        today = datetime.now().date()

        if deadline < today:
            return "encerrada"

        return "aberta"

    except ValueError:
        return "desconhecido"

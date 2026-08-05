from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from .bll_browser import collect_detail_pages, collect_search_rows

from .domain import MUNICIPALITIES, score_relevance

BASE = "https://bllcompras.com"
SEARCH_URLS = [
    BASE + "/Process/ProcessSearchPublic?param1=0",
    BASE + "/Process/ProcessSearchPublic?param1=1",
    BASE + "/Process/ProcessSearchPublic?param1=3",
    BASE + "/Process/ProcessSearchPublic?param1=4",
    BASE + "/Process/ProcessSearchPublic?param1=5",
]

TARGETS = {
    "2929206": ["SAO FRANCISCO DO CONDE", "SÃO FRANCISCO DO CONDE"],
    "2904902": ["CACHOEIRA-BA", "MUNICIPIO DE CACHOEIRA", "MUNICÍPIO DE CACHOEIRA"],
    "2928604": ["SANTO AMARO-BA", "MUNICIPIO DE SANTO AMARO", "MUNICÍPIO DE SANTO AMARO"],
    "2929750": ["SAUBARA-BA", "MUNICIPIO DE SAUBARA", "MUNICÍPIO DE SAUBARA"],
}

# Fallback real confirmado na BLL em 08/07/2026.
# É usado somente se a página pública não retornar alguma linha durante a coleta.
KNOWN_ACTIVE = []

CLOSED_SITUATIONS = {
    "GRAVADO",
    "DESERTO",
    "CANCELADO",
    "FRACASSADO",
    "SUSPENSO",
    "REVOGADO",
    "ANULADO",
    "ADJUDICADO",
    "HOMOLOGADO",
    "RESULTADO FINAL",
}

LAST_DIAGNOSTICS: Dict[str, object] = {}


def get_last_diagnostics() -> dict:
    return dict(LAST_DIAGNOSTICS)



def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().upper()


def _dt(value: str) -> Optional[str]:
    if not value:
        return None
    value = re.sub(r"\s+", " ", value).strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).isoformat()
        except ValueError:
            pass
    return None


def _city_code(promoter: str, city: str) -> Optional[str]:
    hay = _norm(promoter + " " + city)
    for code, aliases in TARGETS.items():
        if any(_norm(alias) in hay for alias in aliases):
            return code
    return None


def _status(situation: str, end_at: Optional[str]) -> str:
    if end_at:
        try:
            if datetime.fromisoformat(end_at) < datetime.now():
                return "encerrada"
        except ValueError:
            pass

    s = _norm(situation)

    if (
        "HOMOLOGADO" in s
        or "CANCELADO" in s
        or "REVOGADO" in s
        or "ANULADO" in s
        or "ENCERRADO" in s
    ):
        return "encerrada"

    if (
        "RECEPCAO DE PROPOSTAS" in s
        or "PUBLICADO" in s
    ):
        return "aberta"

    if end_at:
        try:
            return (
                "aberta"
                if datetime.fromisoformat(end_at) >= datetime.now()
                else "encerrada"
            )
        except ValueError:
            pass

    return "desconhecido"


def _extract_object(html: str) -> Optional[str]:
    soup = BeautifulSoup(
        html or "",
        "html.parser",
    )

    field = soup.select_one(
        "textarea#ProductOrService, "
        "textarea[name='ProductOrService']"
    )

    if field is not None:
        text = re.sub(
            r"\s+",
            " ",
            field.get_text(
                " ",
                strip=True,
            )
            or field.get("value", ""),
        ).strip()

        if text:
            return text

    candidate = soup.find(
        id=re.compile(
            r"ProductOrService|Objeto|Object",
            re.I,
        )
    )

    if candidate is not None:
        text = re.sub(
            r"\s+",
            " ",
            candidate.get_text(
                " ",
                strip=True,
            )
            or candidate.get("value", ""),
        ).strip()

        if text:
            return text

    page_text = re.sub(
        r"\s+",
        " ",
        soup.get_text(
            " ",
            strip=True,
        ),
    )

    match = re.search(
        r"\bOBJETO\b\s*(.+?)"
        r"(?=\bOBSERVA(?:ÇÃO|CAO)\b|$)",
        page_text,
        re.I,
    )

    if match:
        text = match.group(1).strip()
        if text:
            return text

    return None


def _parse_brl(value: str) -> Optional[float]:
    if not value:
        return None
    text = re.sub(r"[^\d,.-]", "", value.strip())
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        parts = text.split(".")
        if len(parts) > 2:
            text = "".join(parts)
    try:
        result = float(text)
    except ValueError:
        return None
    return result if result >= 0 else None


def _extract_value(html: str) -> Optional[float]:
    soup = BeautifulSoup(html, "html.parser")

    def parse_candidate(value):
        if not value:
            return None

        text = str(value).strip()

        match = re.search(
            r"R\$\s*([\d.]+,\d{2,4})",
            text,
            re.I,
        )

        if not match:
            match = re.search(
                r"(?<!\d)([\d.]+,\d{2,4})(?!\d)",
                text,
                re.I,
            )

        if not match:
            return None

        return _parse_brl(match.group(1))

    labels = soup.find_all(
        string=re.compile(
            r"VALOR\s+TOTAL\s+DO\s+PROCESSO",
            re.I,
        )
    )

    for label_text in labels:
        label_node = label_text.parent
        current = label_node

        for _ in range(5):
            if current is None:
                break

            for field in current.find_all(
                ["input", "textarea"],
                limit=20,
            ):
                result = parse_candidate(
                    field.get("value")
                    or field.get_text(" ", strip=True)
                )

                if result is not None:
                    return result

            sibling = current.find_next_sibling()

            for _ in range(5):
                if sibling is None:
                    break

                for field in sibling.find_all(
                    ["input", "textarea"],
                    limit=20,
                ):
                    result = parse_candidate(
                        field.get("value")
                        or field.get_text(" ", strip=True)
                    )

                    if result is not None:
                        return result

                sibling = sibling.find_next_sibling()

            current = current.parent

    for field in soup.find_all("input"):
        result = parse_candidate(field.get("value"))

        if result is None:
            continue

        context_parts = []
        current = field.parent

        for _ in range(4):
            if current is None:
                break

            context_parts.append(
                current.get_text(" ", strip=True)
            )

            current = current.parent

        context = " ".join(context_parts)

        if re.search(
            r"VALOR\s+TOTAL\s+DO\s+PROCESSO",
            context,
            re.I,
        ):
            return result

    raw_patterns = [
        r"VALOR\s+TOTAL\s+DO\s+PROCESSO.{0,2500}?value=[\"']\s*R\$\s*([\d.]+,\d{2,4})",
        r"VALOR\s+TOTAL\s+DO\s+PROCESSO.{0,2500}?value=[\"']\s*([\d.]+,\d{2,4})",
    ]

    for pattern in raw_patterns:
        match = re.search(
            pattern,
            html,
            re.I | re.S,
        )

        if match:
            return _parse_brl(match.group(1))

    text = " ".join(soup.stripped_strings)

    text_patterns = [
        r"VALOR\s+TOTAL\s+DO\s+PROCESSO\s*[:\-]?\s*R\$\s*([\d.]+,\d{2,4})",
        r"VALOR\s+TOTAL\s+DO\s+PROCESSO\s*[:\-]?\s*([\d.]+,\d{2,4})",
    ]

    for pattern in text_patterns:
        match = re.search(pattern, text, re.I)

        if match:
            return _parse_brl(match.group(1))

    return None

def _request(session: requests.Session, url: str) -> requests.Response:
    last = None
    for attempt in range(3):
        try:
            response = session.get(
                url,
                timeout=(10, 45),
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/138 Safari/537.36",
                    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                },
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise last  # type: ignore[misc]


def _row_to_item(cells: List[str], href: Optional[str]) -> Optional[dict]:
    # A BLL normalmente retorna: ícone, Promotor, Número, Modalidade, Cidade,
    # Situação, Publicação, Disputa. Em algumas renderizações o ícone não vira célula.
    if len(cells) < 7:
        return None
    values = cells[-7:]
    promoter, number, modality, city, situation, published, dispute = values
    code = _city_code(promoter, city)
    if not code:
        return None
    end_at = _dt(dispute)
    url = urljoin(BASE, href) if href else SEARCH_URLS[0]
    title = "%s — %s" % (number, modality)
    return {
        "municipality_code": code,
        "agency": promoter,
        "notice_number": number,
        "modality": modality,
        "published_at": _dt(published),
        "proposal_end_at": end_at,
        "url": url,
        "situation": situation,
        "title": title,
    }


def _adapt(raw: dict, object_text: Optional[str] = None, estimated_value: Optional[float] = None) -> dict:
    code = raw["municipality_code"]
    description = object_text or raw.get("object") or raw.get("title") or raw["notice_number"]
    title = description if len(description) <= 180 else description[:177].rstrip() + "..."
    score, terms, category = score_relevance(title, description)
    ext_src = "%s|%s|%s" % (code, _norm(raw["notice_number"]), _norm(raw.get("agency") or ""))
    ext = hashlib.sha256(ext_src.encode("utf-8")).hexdigest()[:24]
    return {
        "external_id": "bll:%s" % ext,
        "source": "BLL",
        "municipality_code": code,
        "municipality": MUNICIPALITIES[code],
        "agency": raw.get("agency") or "MUNICIPIO DE %s" % MUNICIPALITIES[code].upper(),
        "title": title,
        "description": description,
        "modality": raw.get("modality") or "Licitação eletrônica",
        "notice_number": raw["notice_number"],
        "published_at": raw.get("published_at"),
        "proposal_end_at": raw.get("proposal_end_at"),
        "estimated_value": estimated_value if estimated_value is not None else raw.get("estimated_value"),
        "url": raw.get("url") or SEARCH_URLS[0],
        "score": score,
        "matched_terms": terms,
        "category": category,
        "status": _status(raw.get("situation", "RECEPÇÃO DE PROPOSTAS"), raw.get("proposal_end_at")),
        "raw": raw,
    }


def fetch_all() -> List[dict]:
    session = requests.Session()
    discovered: Dict[str, dict] = {}

    diagnostics = {
        "status": "running",
        "browser": None,
        "browser_details": None,
        "rows_received": 0,
        "target_rows": 0,
        "ignored_non_target": 0,
        "closed_or_expired": 0,
        "duplicates": 0,
        "active_rows": 0,
        "browser_detail_pages_used": 0,
        "browser_detail_object_hits": 0,
        "detail_requests_fallback": 0,
        "detail_errors": 0,
        "returned": 0,
        "error": None,
    }

    cities = [
        "Santo Amaro",
        "Saubara",
        "Cachoeira",
        "São Francisco do Conde",
    ]

    try:
        browser_rows, browser_diagnostics = (
            collect_search_rows(
                cities=cities,
                state_id="5",
                days_back=365,
                future_days=365,
                max_offsets=20,
            )
        )

        diagnostics["browser"] = (
            browser_diagnostics
        )
        diagnostics["rows_received"] = len(
            browser_rows
        )

        for browser_row in browser_rows:
            row = _row_to_item(
                browser_row.get("cells") or [],
                browser_row.get("href"),
            )

            if not row:
                diagnostics[
                    "ignored_non_target"
                ] += 1
                continue

            diagnostics["target_rows"] += 1

            normalized_situation = _norm(
                row.get("situation", "")
            )

            current_status = _status(
                row.get("situation", ""),
                row.get("proposal_end_at"),
            )

            if (
                normalized_situation in CLOSED_SITUATIONS
                or current_status == "encerrada"
            ):
                diagnostics[
                    "closed_or_expired"
                ] += 1
                continue

            key = "%s|%s" % (
                row["municipality_code"],
                _norm(
                    row["notice_number"]
                ),
            )

            if key in discovered:
                diagnostics["duplicates"] += 1
                continue

            discovered[key] = row

        diagnostics["active_rows"] = len(
            discovered
        )

        detail_urls = [
            raw.get("url")
            for raw in discovered.values()
            if raw.get("url")
            and "ProcessView" in raw.get("url", "")
        ]

        browser_details, detail_diagnostics = (
            collect_detail_pages(
                detail_urls
            )
        )

        diagnostics["browser_details"] = (
            detail_diagnostics
        )

        result: List[dict] = []

        for raw in discovered.values():
            obj = raw.get("object")
            estimated_value = raw.get(
                "estimated_value"
            )
            url = raw.get("url")

            browser_detail = (
                browser_details.get(url, {})
                if url
                else {}
            )
            detail_html = browser_detail.get(
                "html"
            )

            if detail_html:
                diagnostics[
                    "browser_detail_pages_used"
                ] += 1

                obj = (
                    _extract_object(detail_html)
                    or browser_detail.get("object")
                    or obj
                )

                estimated_value = (
                    _extract_value(detail_html)
                    or estimated_value
                )

                if obj:
                    diagnostics[
                        "browser_detail_object_hits"
                    ] += 1

            if (
                url
                and "ProcessView" in url
                and not detail_html
            ):
                diagnostics[
                    "detail_requests_fallback"
                ] += 1

                try:
                    detail = _request(
                        session,
                        url,
                    )

                    obj = (
                        _extract_object(
                            detail.text
                        )
                        or obj
                    )

                    estimated_value = (
                        _extract_value(
                            detail.text
                        )
                        or estimated_value
                    )

                except requests.RequestException:
                    diagnostics[
                        "detail_errors"
                    ] += 1

            result.append(
                _adapt(
                    raw,
                    obj,
                    estimated_value,
                )
            )

        result.sort(
            key=lambda item: (
                item.get(
                    "proposal_end_at"
                )
                or "9999",
                item.get(
                    "municipality"
                )
                or "",
                item.get(
                    "notice_number"
                )
                or "",
            )
        )

        diagnostics["returned"] = len(result)
        diagnostics["status"] = "success"

        LAST_DIAGNOSTICS.clear()
        LAST_DIAGNOSTICS.update(
            diagnostics
        )

        return result

    except Exception as exc:
        diagnostics["status"] = "error"
        diagnostics["error"] = (
            f"{type(exc).__name__}: {exc}"
        )

        LAST_DIAGNOSTICS.clear()
        LAST_DIAGNOSTICS.update(
            diagnostics
        )

        raise


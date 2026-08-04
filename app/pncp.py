from __future__ import annotations
import hashlib
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
import requests
from .domain import MUNICIPALITIES, opportunity_status, score_relevance

BASE = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
MODALITIES = list(range(1, 15))


def _pick(d: dict, *keys: str, default=None):
    for key in keys:
        value = d.get(key)
        if value not in (None, ""):
            return value
    return default


def _to_iso(value: Any) -> Optional[str]:
    if not value: return None
    text = str(value)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y%m%d", "%d/%m/%Y"):
        try: return datetime.strptime(text[:19] if "T" in text else text, fmt).isoformat()
        except ValueError: pass
    return text


def adapt(raw: dict, city_code: str) -> dict:
    title = str(_pick(raw, "objetoCompra", "objeto", "descricao", "titulo", default="Oportunidade pública"))
    description = str(_pick(raw, "informacaoComplementar", "descricao", "objetoCompra", default=title))
    org = _pick(raw, "orgaoEntidade", default={}) or {}
    unit = _pick(raw, "unidadeOrgao", default={}) or {}
    agency = _pick(unit, "nomeUnidade", default=None) or _pick(org, "razaosocial", "razaoSocial", default="Órgão público")
    notice = str(_pick(raw, "numeroCompra", "numeroControlePNCP", "numeroAviso", default=""))
    ext = str(_pick(raw, "numeroControlePNCP", "numeroCompra", default=""))
    if not ext:
        ext = hashlib.sha256(f"{city_code}|{title}|{notice}".encode()).hexdigest()[:24]
    score, terms, category = score_relevance(title, description)
    end = _to_iso(_pick(raw, "dataEncerramentoProposta", "dataFimRecebimentoProposta", "dataAberturaProposta"))
    value = _pick(raw, "valorTotalEstimado", "valorEstimadoTotal")
    try: value = float(value) if value is not None else None
    except (TypeError, ValueError): value = None
    return {
        "external_id": f"pncp:{ext}", "source": "PNCP", "municipality_code": city_code,
        "municipality": MUNICIPALITIES[city_code], "agency": agency, "title": title, "description": description,
        "modality": str(_pick(raw, "modalidadeNome", "modalidadeId", default="")), "notice_number": notice,
        "published_at": _to_iso(_pick(raw, "dataPublicacaoPncp", "dataPublicacao")), "proposal_end_at": end,
        "estimated_value": value, "url": _pick(raw, "linkSistemaOrigem", "url", "linkProcessoEletronico"),
        "score": score, "matched_terms": terms, "category": category, "status": opportunity_status(end), "raw": raw,
    }


def fetch_city(city_code: str, lookback_days: int = 45, session: Optional[requests.Session] = None) -> List[dict]:
    s = session or requests.Session()
    end = date.today(); start = end - timedelta(days=lookback_days)
    found: Dict[str, dict] = {}
    headers = {"User-Agent":"RadarLicitaISP/1.0 (monitoramento interno de oportunidades públicas)"}
    for modality in MODALITIES:
        page = 1
        while page <= 5:
            params = {
                "dataInicial": start.strftime("%Y%m%d"), "dataFinal": end.strftime("%Y%m%d"),
                "codigoModalidadeContratacao": modality, "uf": "BA", "codigoMunicipioIbge": city_code,
                "pagina": page, "tamanhoPagina": 50,
            }
            response = s.get(BASE, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            payload = response.json()
            items = payload.get("data") or payload.get("content") or payload.get("items") or []
            for raw in items:
                item = adapt(raw, city_code); found[item["external_id"]] = item
            total_pages = int(payload.get("totalPaginas") or payload.get("totalPages") or 1)
            if page >= total_pages or not items: break
            page += 1; time.sleep(0.08)
    return list(found.values())

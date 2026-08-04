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

from .domain import MUNICIPALITIES, score_relevance

BASE = "https://bllcompras.com"
SEARCH_URLS = [
    BASE + "/Process/ProcessSearchPublic?param1=0",
    BASE + "/Process/ProcessSearchPublic?param1=1",
    BASE + "/Process/ProcessSearchPublic?param1=4",
]

TARGETS = {
    "2929206": ["SAO FRANCISCO DO CONDE", "SÃO FRANCISCO DO CONDE"],
    "2904902": ["CACHOEIRA-BA", "MUNICIPIO DE CACHOEIRA", "MUNICÍPIO DE CACHOEIRA"],
    "2928604": ["SANTO AMARO-BA", "MUNICIPIO DE SANTO AMARO", "MUNICÍPIO DE SANTO AMARO"],
    "2929750": ["SAUBARA-BA", "MUNICIPIO DE SAUBARA", "MUNICÍPIO DE SAUBARA"],
}

# Fallback real confirmado na BLL em 08/07/2026.
# É usado somente se a página pública não retornar alguma linha durante a coleta.
KNOWN_ACTIVE = [
    {
        "municipality_code": "2928604",
        "notice_number": "PE0020/2026",
        "modality": "PREGÃO ELETRÔNICO",
        "published_at": "2026-07-06T06:21:00",
        "proposal_end_at": "2026-07-15T09:00:00",
        "url": "https://bllcompras.com/Process/ProcessView?param1=%5Bgkz%5DiRWAUQwjxC2qXmv0zNFnqAGyhDLs4Mn2enHyDC7hz_oOXU8hX_fzSBYPgYU96GXjAsaF5uEuGS3Ec3ThWgQgVGYJj5Z7ksDIfToJA%2FieUlU%3D",
        "object": "REGISTRO DE PREÇOS PARA AQUISIÇÃO, DE FORMA PARCELADA E CONFORME A DEMANDA, DE MATERIAIS DE PROTEÇÃO INDIVIDUAL – EPI, FERRAMENTAS MANUAIS, EQUIPAMENTOS ELÉTRICOS E MATERIAL DE SINALIZAÇÃO, DESTINADOS ÀS EQUIPES OPERACIONAIS DA SECRETARIA DE SERVIÇOS PÚBLICOS DO MUNICÍPIO DE SANTO AMARO – BAHIA.",
    },
    {
        "municipality_code": "2928604",
        "notice_number": "PE0017/2026",
        "modality": "PREGÃO ELETRÔNICO",
        "published_at": "2026-07-03T07:40:00",
        "proposal_end_at": "2026-07-14T09:00:00",
        "url": "https://bllcompras.com/Process/ProcessView?param1=%5Bgkz%5DEPGE9mcAXzRpLjDNeT5sFXT__QTPp09WW_ipczGR4Tcbb3FY2uWLRuO6YSL_hcczMab2U8UUxbyD6bHRZ0lFGCYiEhXqkdc%2FLVLr0HcGebM%3D",
        "object": "REGISTRO DE PREÇOS PARA FUTURA E EVENTUAL AQUISIÇÃO DE POSTES DE CONCRETO ARMADO CENTRIFUGADO, EM LOTE ÚNICO, DESTINADOS À IMPLANTAÇÃO E AMPLIAÇÃO DA INFRAESTRUTURA DE ILUMINAÇÃO PÚBLICA EM LOCALIDADES DO MUNICÍPIO DE SANTO AMARO – BAHIA.",
    },
    {
        "municipality_code": "2928604",
        "notice_number": "PE0014/2026",
        "modality": "PREGÃO ELETRÔNICO",
        "published_at": "2026-06-26T08:49:00",
        "proposal_end_at": "2026-07-09T09:00:00",
        "url": "https://bllcompras.com/Process/ProcessView?param1=%5Bgkz%5Dtw29I6WYYewy_uaW4fC_fgrwWsDchtGrDRFD1ATA99UqGgeiZa8Pqq2PMNYlYRlXqazsHMpBlem2qr0ZAH0LUm5SFB3oR8DtXPe5e8HemuA%3D",
        "object": "REGISTRO DE PREÇOS PARA EVENTUAL E FUTURA CONTRATAÇÃO DE EMPRESA PARA O FORNECIMENTO ADEQUADO DE EQUIPAMENTOS HOSPITALARES PERMANENTES DESTINADOS ÀS UNIDADES BÁSICAS DE SAÚDE, À SANTA CASA DE SANTO AMARO, AO HOSPITAL DE ACUPE E À SANTA CASA DE OLIVEIRA DOS CAMPINHOS.",
    },
    {
        "municipality_code": "2929750",
        "notice_number": "PE013/2026",
        "modality": "PREGÃO ELETRÔNICO",
        "published_at": "2026-07-06T08:22:00",
        "proposal_end_at": "2026-07-21T10:00:00",
        "url": "https://bllcompras.com/Process/ProcessView?param1=%5Bgkz%5DrDYelK1qo3dxXZR9wtVx6uHqRyoFdlEdRt0s5jNWPbHG_OeTgzd%2F8fva_mInyhU9P7smuIPnbQszkXXsnHYDi1rk6w0yuzJNfUXPIN4Y2DQ%3D",
        "object": "Contratação de empresa especializada na prestação de serviços de guincho para remoção, transporte e apoio a veículos leves e pesados pertencentes à frota do Município de Saubara – BA.",
    },
    {
        "municipality_code": "2929750",
        "notice_number": "PE009/2026",
        "modality": "PREGÃO ELETRÔNICO",
        "published_at": "2026-06-08T14:48:00",
        "proposal_end_at": "2026-07-16T10:00:00",
        "url": "https://bllcompras.com/Process/ProcessView?param1=%5Bgkz%5DKcAVUSAEIpSgpyJG3VTdU_1c21uUXNSPQYy6AoNCn3gW2kd48yX5ubbe8Ifd9_jRAo1Z_WOY22Cm3Cj2aQjRg6gtRNm6mfKSpKMl1iqx3p4%3D",
        "object": "Aquisição de material de construção, consistindo em tintas, solventes, pincéis, rolos e demais itens necessários à execução de serviços de pintura, destinados à manutenção preventiva e corretiva de prédios e equipamentos públicos.",
    },
    {
        "municipality_code": "2904902",
        "notice_number": "003/2026",
        "modality": "CONCORRÊNCIA ELETRÔNICA",
        "published_at": "2026-07-01T16:07:00",
        "proposal_end_at": "2026-07-22T09:00:00",
        "url": "https://bllcompras.com/Process/ProcessView?param1=%5Bgkz%5DzZDnbAbCbyvfmcBGNd1X2KJMlDQGWkm%2FKnflJxxFd4R3dUEG4MVov4dIGb1YtrGFlRKX3ICJqdZSp_x%2FKwFQYl7zpJVkt4z6n7AvBfAs0v0%3D",
        "object": "CONTRATAÇÃO DE EMPRESA NO FORNECIMENTO DE EQUIPAMENTOS, UTENSÍLIOS E CORRELATOS DE COZINHA PARA ATENDER AS NECESSIDADES DA ALIMENTAÇÃO ESCOLAR DA SECRETARIA DE EDUCAÇÃO DO MUNICÍPIO DE CACHOEIRA – BA.",
    },
    {
        "municipality_code": "2904902",
        "notice_number": "002/2026",
        "modality": "CONCORRÊNCIA ELETRÔNICA",
        "published_at": "2026-07-01T15:57:00",
        "proposal_end_at": "2026-07-21T09:00:00",
        "url": "https://bllcompras.com/Process/ProcessSearchPublic?param1=0",
        "object": "CONCORRÊNCIA ELETRÔNICA 002/2026 DO MUNICÍPIO DE CACHOEIRA – BA. O objeto será atualizado automaticamente quando o detalhe público for localizado.",
    },
    {
        "municipality_code": "2929206",
        "notice_number": "008/2026",
        "modality": "PREGÃO ELETRÔNICO",
        "published_at": "2026-06-30T09:56:00",
        "proposal_end_at": "2026-07-14T09:00:00",
        "url": "https://bllcompras.com/Process/ProcessView?param1=%5Bgkz%5D7NSPDCKG19S3PYugss05YbrTyQQJ1nPdog94lFr59pcHrgLEKVdRM06_ls5iKJ7DiTQBamk3DlLyHWbW%2FtxjCUQBLoUdJh8chlT0uk8IN8o%3D",
        "object": "Contratação de empresa especializada para FORNECIMENTO DE EQUIPAMENTOS DE INFORMÁTICA TIPO TABLET, PARA USO DAS EQUIPES DOS PROGRAMAS BOLSA FAMÍLIA E CRIANÇA FELIZ.",
    },
    {
        "municipality_code": "2929206",
        "notice_number": "007/2026",
        "modality": "PREGÃO ELETRÔNICO",
        "published_at": "2026-06-18T09:56:00",
        "proposal_end_at": "2026-07-10T09:00:00",
        "url": "https://bllcompras.com/Process/ProcessView?param1=%5Bgkz%5D8LrFplzdrPhIsPLY04TxOoDyCn7pMoUbJGzo1Ko0E7l2RM6FFiZNBMgFsTr3OEDkE9q0RD56rc1OLu1cKgESPiUaEuc2nXvdMkzsJDnSgNc%3D",
        "object": "Seleção de melhor proposta para futura e eventual contratação de empresa para prestação de serviços de manutenção preventiva e corretiva, com reposição de peças e componentes, em equipamentos de ar-condicionado, bebedouros, freezers, frigobares, refrigeradores e câmaras frigoríficas.",
    },
]


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
    s = _norm(situation)
    if "RECEPCAO DE PROPOSTAS" in s or "PUBLICADO" in s:
        return "aberta"
    if "HOMOLOGADO" in s or "CANCELADO" in s or "REVOGADO" in s or "ANULADO" in s:
        return "encerrada"
    if end_at:
        try:
            return "aberta" if datetime.fromisoformat(end_at) >= datetime.now() else "encerrada"
        except ValueError:
            pass
    return "desconhecido"


def _extract_object(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    text = " ".join(soup.stripped_strings)
    match = re.search(r"\bOBJETO\b\s*(.+?)(?:\s+OBSERVA(?:Ç|C)ÃO\b|\s+Cliente\s+Tipo de arquivo|$)", text, re.I)
    if not match:
        return None
    obj = re.sub(r"\s+", " ", match.group(1)).strip(" :-")
    return obj if len(obj) >= 20 else None



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
    ext_src = "%s|%s|%s" % (code, raw["notice_number"], raw.get("url") or "")
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

    for search_url in SEARCH_URLS:
        try:
            response = _request(session, search_url)
        except requests.RequestException:
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        for tr in soup.find_all("tr"):
            cells = [re.sub(r"\s+", " ", td.get_text(" ", strip=True)) for td in tr.find_all("td")]
            link = tr.find("a", href=re.compile(r"ProcessView", re.I))
            href = link.get("href") if link else None
            row = _row_to_item(cells, href)
            if not row:
                continue
            key = "%s|%s" % (row["municipality_code"], _norm(row["notice_number"]))
            discovered[key] = row

    # Completa o que a página pública não entregou naquele momento.
    for known in KNOWN_ACTIVE:
        key = "%s|%s" % (known["municipality_code"], _norm(known["notice_number"]))
        if key not in discovered:
            discovered[key] = dict(known)

    result = []
    for raw in discovered.values():
        obj = raw.get("object")
        estimated_value = raw.get("estimated_value")
        url = raw.get("url")
        if url and "ProcessView" in url:
            try:
                detail = _request(session, url)
                obj = _extract_object(detail.text) or obj
                estimated_value = _extract_value(detail.text) or estimated_value
            except requests.RequestException:
                pass
        result.append(_adapt(raw, obj, estimated_value))

    result.sort(key=lambda item: (item.get("proposal_end_at") or "9999", item["municipality"]))
    return result

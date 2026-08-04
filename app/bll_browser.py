from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Sequence, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


BASE_URL = "https://bllcompras.com"
SEARCH_PAGE_URL = BASE_URL + "/Process/ProcessSearchPublic?param1=0"
PAGE_SIZE = 100


class BLLBrowserError(RuntimeError):
    pass


def _parse_rows(html: str) -> List[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    rows: List[dict] = []

    for tr in soup.find_all("tr"):
        cells = [
            re.sub(r"\\s+", " ", td.get_text(" ", strip=True))
            for td in tr.find_all("td")
        ]
        link = tr.find("a", href=re.compile(r"ProcessView", re.I))

        if not cells or not link:
            continue

        rows.append(
            {
                "cells": cells,
                "href": urljoin(BASE_URL, link.get("href") or ""),
            }
        )

    return rows


def collect_search_rows(
    cities: Sequence[str],
    state_id: str = "5",
    days_back: int = 365,
    future_days: int = 365,
    max_offsets: int = 20,
    timeout_ms: int = 120_000,
) -> Tuple[List[dict], Dict[str, object]]:
    now = datetime.now()
    publication_start = now - timedelta(days=days_back)
    dispute_end = now + timedelta(days=future_days)

    all_rows: List[dict] = []
    global_seen = set()

    diagnostics: Dict[str, object] = {
        "status": "running",
        "mode": "playwright-headless",
        "search_page": SEARCH_PAGE_URL,
        "started_at": now.isoformat(),
        "cities": {},
        "total_rows": 0,
        "error": None,
    }

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)

            try:
                context = browser.new_context(
                    locale="pt-BR",
                    timezone_id="America/Sao_Paulo",
                    viewport={"width": 1440, "height": 1000},
                )

                try:
                    page = context.new_page()
                    page.set_default_timeout(timeout_ms)
                    page.goto(
                        SEARCH_PAGE_URL,
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )
                    page.wait_for_function(
                        "typeof ExecuteCaptcha === 'function' "
                        "&& typeof grecaptcha !== 'undefined'",
                        timeout=timeout_ms,
                    )

                    javascript = (
                        "async ({ parameters }) => {"
                        " const token = await ExecuteCaptcha('publicSearch');"
                        " const query = new URLSearchParams({...parameters, token: token});"
                        " const response = await fetch("
                        " '/Process/GetProcessByParams?' + query.toString(),"
                        " {method: 'POST', credentials: 'same-origin', headers: {"
                        " 'Accept': 'application/json, text/javascript, */*',"
                        " 'X-Requested-With': 'XMLHttpRequest'}});"
                        " return {status: response.status, url: response.url,"
                        " text: await response.text()};"
                        "}"
                    )

                    for city in cities:
                        city_rows: List[dict] = []
                        city_seen = set()
                        pages = []
                        stop_reason = None

                        for offset in range(max_offsets):
                            parameters = {
                                "Organization": "",
                                "Number": "",
                                "City": city,
                                "fkState": state_id,
                                "fkModality": "",
                                "fkStatus": "",
                                "fkDisputeKind": "",
                                "DateStart": publication_start.strftime("%d/%m/%Y"),
                                "DateEnd": now.strftime("%d/%m/%Y"),
                                "DateStartDispute": now.strftime("%d/%m/%Y"),
                                "DateEndDispute": dispute_end.strftime("%d/%m/%Y"),
                                "Offset": str(offset),
                            }

                            response = page.evaluate(
                                javascript,
                                {"parameters": parameters},
                            )

                            try:
                                payload = json.loads(response["text"])
                            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                                raise BLLBrowserError(
                                    f"Resposta inválida da BLL para {city}, offset {offset}."
                                ) from exc

                            html = payload.get("html") or ""

                            if payload.get("modal") == "error":
                                message = BeautifulSoup(
                                    html,
                                    "html.parser",
                                ).get_text(" ", strip=True)
                                raise BLLBrowserError(
                                    f"BLL devolveu erro para {city}, offset {offset}: "
                                    f"{message or 'erro não informado'}"
                                )

                            page_rows = _parse_rows(html)
                            pages.append(
                                {
                                    "offset": offset,
                                    "http": response.get("status"),
                                    "rows": len(page_rows),
                                }
                            )

                            new_rows = 0

                            for row in page_rows:
                                href = row["href"]

                                if href in city_seen:
                                    continue

                                city_seen.add(href)
                                item = {
                                    "query_city": city,
                                    "cells": row["cells"],
                                    "href": href,
                                }
                                city_rows.append(item)
                                new_rows += 1

                                if href not in global_seen:
                                    global_seen.add(href)
                                    all_rows.append(item)

                            if not page_rows:
                                stop_reason = "empty_page"
                                break

                            if len(page_rows) < PAGE_SIZE:
                                stop_reason = "last_partial_page"
                                break

                            if new_rows == 0:
                                stop_reason = "repeated_page"
                                break
                        else:
                            stop_reason = "max_offsets_reached"

                        diagnostics["cities"][city] = {
                            "total": len(city_rows),
                            "pages": pages,
                            "stop_reason": stop_reason,
                        }

                finally:
                    context.close()

            finally:
                browser.close()

        diagnostics["total_rows"] = len(all_rows)
        diagnostics["status"] = "success"
        diagnostics["finished_at"] = datetime.now().isoformat()
        return all_rows, diagnostics

    except Exception as exc:
        diagnostics["status"] = "error"
        diagnostics["error"] = f"{type(exc).__name__}: {exc}"
        diagnostics["finished_at"] = datetime.now().isoformat()

        if isinstance(exc, BLLBrowserError):
            raise

        raise BLLBrowserError(diagnostics["error"]) from exc

def collect_detail_pages(
    urls: Sequence[str],
    timeout_ms: int = 120_000,
) -> Tuple[Dict[str, dict], Dict[str, object]]:
    # Abre as páginas públicas de detalhe da BLL no Chromium headless.
    unique_urls = [
        url
        for url in dict.fromkeys(urls)
        if url
    ]

    details: Dict[str, dict] = {}
    diagnostics: Dict[str, object] = {
        "status": "running",
        "requested": len(unique_urls),
        "loaded": 0,
        "object_hits": 0,
        "errors": [],
        "started_at": datetime.now().isoformat(),
    }

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
            )
            context = browser.new_context(
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
                viewport={
                    "width": 1440,
                    "height": 1000,
                },
            )
            page = context.new_page()
            page.set_default_timeout(timeout_ms)

            for url in unique_urls:
                try:
                    page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )

                    try:
                        page.locator(
                            "#ProcessViewInfo"
                        ).wait_for(
                            state="attached",
                            timeout=timeout_ms,
                        )
                    except PlaywrightTimeoutError:
                        pass

                    html = page.content()
                    soup = BeautifulSoup(
                        html,
                        "html.parser",
                    )

                    field = soup.select_one(
                        "textarea#ProductOrService, "
                        "textarea[name='ProductOrService']"
                    )

                    obj = None
                    if field is not None:
                        obj = re.sub(
                            r"\s+",
                            " ",
                            field.get_text(
                                " ",
                                strip=True,
                            )
                            or field.get("value", ""),
                        ).strip()

                    details[url] = {
                        "html": html,
                        "object": obj or None,
                        "final_url": page.url,
                    }

                    diagnostics["loaded"] += 1
                    if obj:
                        diagnostics["object_hits"] += 1

                except Exception as exc:
                    diagnostics["errors"].append(
                        {
                            "url": url,
                            "error": (
                                f"{type(exc).__name__}: {exc}"
                            ),
                        }
                    )

            context.close()
            browser.close()

        diagnostics["status"] = (
            "success"
            if not diagnostics["errors"]
            else "partial"
        )
        diagnostics["finished_at"] = (
            datetime.now().isoformat()
        )
        return details, diagnostics

    except Exception as exc:
        diagnostics["status"] = "error"
        diagnostics["finished_at"] = (
            datetime.now().isoformat()
        )
        diagnostics["errors"].append(
            {
                "url": None,
                "error": (
                    f"{type(exc).__name__}: {exc}"
                ),
            }
        )
        raise BLLBrowserError(
            "Falha ao abrir detalhes da BLL: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


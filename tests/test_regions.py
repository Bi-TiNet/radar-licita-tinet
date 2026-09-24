from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.bll import SEARCH_CITIES_BY_STATE, _city_code, fetch_all
from app.domain import MUNICIPALITIES
from app.pncp import fetch_city


RIDE = {
    "2611101": "Petrolina",
    "2608750": "Lagoa Grande",
    "2609808": "Orocó",
    "2612604": "Santa Maria da Boa Vista",
    "2918407": "Juazeiro",
    "2907202": "Casa Nova",
    "2909901": "Curaçá",
    "2930774": "Sobradinho",
}


class RegionTests(unittest.TestCase):
    def test_ride_matches_official_eight_municipalities(self):
        self.assertEqual({code: MUNICIPALITIES[code] for code in RIDE}, RIDE)
        self.assertEqual(set(SEARCH_CITIES_BY_STATE["16"]), set(list(RIDE.values())[:4]))
        self.assertEqual(set(RIDE.values()) - set(SEARCH_CITIES_BY_STATE["16"]), set(SEARCH_CITIES_BY_STATE["5"][4:]))

    def test_city_mapping_recognizes_each_new_municipality(self):
        for code, city in RIDE.items():
            with self.subTest(city=city):
                self.assertEqual(_city_code("Prefeitura Municipal", city), code)
                self.assertEqual(_city_code("Prefeitura Municipal", f"{city}-{'PE' if code.startswith('26') else 'BA'}"), code)

    def test_bll_queries_bahia_and_pernambuco_separately(self):
        with patch("app.bll.collect_search_rows", side_effect=[([], {"status": "success"}), ([], {"status": "success"})]) as search, \
                patch("app.bll.collect_detail_pages", return_value=({}, {"status": "success"})):
            self.assertEqual(fetch_all(), [])
        self.assertEqual(search.call_count, 2)
        self.assertEqual([call.kwargs["state_id"] for call in search.call_args_list], ["5", "16"])
        self.assertEqual([len(call.kwargs["cities"]) for call in search.call_args_list], [8, 4])

    def test_pncp_uses_pernambuco_for_petrolina(self):
        response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"data": []})
        session = Mock()
        session.get.return_value = response
        self.assertEqual(fetch_city("2611101", session=session), [])
        self.assertTrue(all(call.kwargs["params"]["uf"] == "PE" for call in session.get.call_args_list))


if __name__ == "__main__":
    unittest.main()

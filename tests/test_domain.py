from app.domain import classify_focus, score_relevance

def test_fiber_is_high_relevance():
    score, terms, category = score_relevance("Link dedicado em fibra óptica", "Internet com IP público e SLA")
    assert score >= 70
    assert category in {"Fibra & FTTH", "Links & Internet"}

def test_noise_is_low_relevance():
    score, _, _ = score_relevance("Aquisição de gêneros alimentícios", "Merenda escolar")
    assert score == 0


def test_telecom_is_only_local():
    assert classify_focus("Link dedicado em fibra óptica", "Acesso à internet", "2928604")[3] == "Ti.Net"
    assert classify_focus("Link dedicado em fibra óptica", "Acesso à internet", "2918407")[3] is None


def test_vehicle_tracking_is_relevant_in_both_regions():
    for city in ("2928604", "2918407", "2611101"):
        score, _, category, company = classify_focus("Rastreamento e monitoramento de frota por GPS", "", city)
        assert score >= 70
        assert category == "Monitoramento veicular"
        assert company == "AutoControl"


def test_generic_vehicle_and_it_tenders_are_not_relevant():
    for title in ("Locação de veículos", "Credenciamento para exames de saúde", "Aquisição de câmeras CFTV"):
        assert classify_focus(title, "", "2918407")[3] is None
        assert classify_focus(title, "", "2928604")[3] is None
    assert classify_focus("Locação de veículos com rastreamento por GPS", "", "2918407")[3] is None

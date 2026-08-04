from app.domain import score_relevance

def test_fiber_is_high_relevance():
    score, terms, category = score_relevance("Link dedicado em fibra óptica", "Internet com IP público e SLA")
    assert score >= 70
    assert category in {"Fibra & FTTH", "Links & Internet"}

def test_noise_is_low_relevance():
    score, _, _ = score_relevance("Aquisição de gêneros alimentícios", "Merenda escolar")
    assert score == 0

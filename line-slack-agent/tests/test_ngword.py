from src.guardrails.l1_ngword import check, load_ng_words


NG = {
    "confidential": ["社内限定", "NDA"],
    "personal_info": ["マイナンバー"],
}


def test_clean_text_passes():
    r = check("案件の条件は時給1500円です", NG)
    assert r.ok


def test_ng_detected():
    r = check("この情報は社内限定です", NG)
    assert not r.ok
    assert r.hits[0].word == "社内限定"


def test_case_insensitive_and_full_width():
    r = check("nda contract", NG)  # 半角小文字
    assert not r.ok


def test_multiple_hits():
    r = check("社内限定のNDA契約です", NG)
    assert not r.ok
    assert len(r.hits) >= 2

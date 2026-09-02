from automation.matcher import Candidate, match_name

ROSTER = [
    Candidate(id="apt-1", name="ישראל ישראלי"),
    Candidate(id="apt-2", name="דוד משה כהן"),
    Candidate(id="apt-3", name="כהן דוד"),
    Candidate(id="apt-4", name="כהן דודי"),
]


def test_exact_match():
    result = match_name("ישראל ישראלי", ROSTER)
    assert result.reason == "matched"
    assert result.candidate.id == "apt-1"


def test_reordered_name_still_matches():
    # bank shows "כהן דוד משה", OXS roster has "דוד משה כהן" — same tokens
    result = match_name("כהן דוד משה", ROSTER)
    assert result.reason == "matched"
    assert result.candidate.id == "apt-2"


def test_ambiguous_name_is_not_guessed():
    # "כהן דוד" is close to both apt-3 ("כהן דוד") and apt-4 ("כהן דודי")
    result = match_name("כהן דוד", ROSTER)
    assert result.reason in ("matched", "ambiguous")
    if result.reason == "matched":
        # if it did match, it must be the exact one, not the near-duplicate
        assert result.candidate.id == "apt-3"


def test_no_match_below_threshold():
    result = match_name("שם שלא קיים בכלל", ROSTER)
    assert result.reason in ("below_threshold", "no_candidates")
    assert result.candidate is None


def test_empty_name():
    result = match_name(None, ROSTER)
    assert result.reason == "no_candidates"
    assert result.candidate is None


def test_empty_roster():
    result = match_name("ישראל ישראלי", [])
    assert result.reason == "no_candidates"
    assert result.candidate is None

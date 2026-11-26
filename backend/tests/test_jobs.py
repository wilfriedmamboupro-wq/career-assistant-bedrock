from app.jobs import JobIndex


def index(settings):
    return JobIndex.from_file(settings.jobs_file)


def test_title_match_ignores_accents_and_case(settings):
    assert [j.id for j in index(settings).search(title="developpeur")] == ["T-001"]


def test_short_keyword_matches_word_start_only():
    from app.schemas import Job

    jobs = [
        Job(id="a", title="AI Developer", city="X", language="en", url="u"),
        Job(id="b", title="Claims Adjuster", city="X", language="en", url="u"),
    ]
    assert [j.id for j in JobIndex(jobs).search(title="ai")] == ["a"]


def test_city_filter_ignores_accents(settings):
    assert [j.id for j in index(settings).search(city="montreal")] == ["T-001"]


def test_language_filter_includes_bilingual(settings):
    assert [j.id for j in index(settings).search(language="en")] == ["T-002", "T-003"]


def test_no_filter_returns_all_capped(settings):
    assert len(index(settings).search()) == 3


def test_missing_file_gives_empty_index(tmp_path):
    assert JobIndex.from_file(tmp_path / "none.json").search() == []

from bs4 import BeautifulSoup

from processors.cleaner import (
    clean_text,
    dedupe,
    deserialize_list,
    extract_section_items,
    is_valid_url,
    normalize_key,
    normalize_url,
    parse_date,
    parse_number,
    serialize_list,
    soup_to_text,
)


def test_clean_text_normalises_spaces_and_quotes():
    assert clean_text("  Big\u00a0Data \u2019 IA\n") == "Big Data ' IA"


def test_normalize_url_removes_tracking_and_fragment():
    url = normalize_url("https://IIT.tn/big-data/?utm_source=x&fbclid=abc#section")
    assert url == "https://iit.tn/big-data/"


def test_normalize_url_resolves_relative_links():
    assert normalize_url("/formation/", "https://isb.tn/program/") == "https://isb.tn/formation/"


def test_parse_number_accepts_french_formats():
    assert parse_number("667 DT / 9 mois") == 667
    assert parse_number("1 250,50€") == 1250.5


def test_parse_date_variants():
    assert parse_date("21/11/2026") == "2026-11-21"
    assert parse_date("2026-11-21T10:00:00Z") == "2026-11-21"
    assert parse_date("texte sans date") is None


def test_dedupe_and_list_serialisation():
    values = dedupe(["Data", "data", "IA", ""])
    assert values == ["Data", "IA"]
    assert deserialize_list(serialize_list(values)) == values


def test_slug_and_url_validation():
    assert normalize_key("Génie Logiciel & Systèmes") == "genie-logiciel-systemes"
    assert is_valid_url("https://isa.tn/formation/")
    assert not is_valid_url("not-a-url")


def test_soup_to_text_preserves_block_lines_and_headings():
    html = (
        "<html><body>"
        "<div class='bt_bb_accordion_item_title'>Principaux modules</div>"
        "<div><ul><li>Python</li><li>Data Engineering</li></ul></div>"
        "<div class='bt_bb_accordion_item_title'>Compétences clés</div>"
        "<div><ul><li>Machine Learning</li></ul></div>"
        "<footer>Copyright 2026</footer>"
        "</body></html>"
    )
    text = soup_to_text(BeautifulSoup(html, "lxml"))
    lines = text.splitlines()
    assert "## Principaux modules" in lines
    assert "- Python" in lines
    assert "- Data Engineering" in lines
    assert "## Compétences clés" in lines
    modules = extract_section_items(text, ["principaux modules"])
    assert modules == ["Python", "Data Engineering"]


def test_section_extraction_stops_at_next_heading_and_footer():
    text = (
        "## Principaux modules\n"
        "Python\n"
        "Data Engineering\n"
        "## Référentiel métiers\n"
        "Data Scientist\n"
        "Route de tunis km 10, Sfax\n"
        "Copyright 2026\n"
    )
    assert extract_section_items(text, ["principaux modules"]) == ["Python", "Data Engineering"]

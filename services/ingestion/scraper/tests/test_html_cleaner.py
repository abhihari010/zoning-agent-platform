from __future__ import annotations

from services.ingestion.scraper.html_cleaner import clean_html


def test_strips_scripts_styles_and_nav():
    html = (
        "<div><nav>Home About</nav><script>var x=1;</script>"
        "<style>.a{}</style><p>Real ordinance text.</p><footer>foot</footer></div>"
    )
    out = clean_html(html)
    assert "Real ordinance text." in out
    assert "var x" not in out
    assert ".a{" not in out
    assert "foot" not in out
    assert "Home About" not in out


def test_preserves_clause_breaks():
    html = (
        '<div class="chunk-content">'
        '<p class="incr0">(a)</p><p class="content1">Intent clause.</p>'
        '<p class="incr0">(b)</p><p class="content1">General standards.</p>'
        "</div>"
    )
    out = clean_html(html)
    lines = [line for line in out.split("\n") if line]
    assert "(a)" in lines
    assert "(b)" in lines
    assert "Intent clause." in lines
    # clauses are on separate lines, not concatenated
    assert "(a) Intent clause. (b)" not in out


def test_decodes_entities_and_collapses_whitespace():
    html = "<p>Section&nbsp;15.2-2280   &amp;   2281.</p>"
    out = clean_html(html)
    assert "15.2-2280 & 2281." in out
    assert "   " not in out


def test_empty_input():
    assert clean_html("") == ""

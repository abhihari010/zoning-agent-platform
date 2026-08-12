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


def test_empty_table_cells_hold_their_column():
    # Real shape of a use table row: symbols only in some district columns.
    html = (
        "<table><tr><th>Use</th><th>R1</th><th>C1</th><th>M1</th></tr>"
        "<tr><td>Antique Shop</td><td></td><td>P</td><td></td></tr></table>"
    )
    out = clean_html(html)
    row = [line for line in out.split("\n") if "Antique Shop" in line][0]
    # Three district columns after the use name, with P in the middle one.
    assert [c.strip() for c in row.split("|")][:4] == ["Antique Shop", "", "P", ""]


def test_symbol_images_resolve_to_their_filename_stem():
    html = (
        "<table><tr><td>Townhouses</td>"
        '<td><img data-image-filename="np.png" src="/x/np.png"></td>'
        '<td><img data-image-filename="P.png"></td>'
        '<td><img alt="CU" src="/x/blank.gif"></td></tr></table>'
    )
    out = clean_html(html)
    assert [c.strip() for c in out.split("|")][:4] == ["Townhouses", "np", "P", "CU"]


def test_cell_wrapped_in_block_tags_stays_on_its_row():
    # Municode wraps cell text in <p>; that must not split the row.
    html = (
        "<table><tr><td><p>Antique Shop</p></td><td><p></p></td>"
        "<td><p>P</p></td></tr>"
        "<tr><td><p>Apparel Shop</p></td><td><p>P</p></td><td><p></p></td></tr></table>"
    )
    rows = [line for line in clean_html(html).split("\n") if line.strip()]
    assert [[c.strip() for c in r.split("|")][:3] for r in rows] == [
        ["Antique Shop", "", "P"],
        ["Apparel Shop", "P", ""],
    ]


def test_non_symbol_images_are_still_dropped():
    html = '<p>Intent.<img src="/assets/city-seal-large.png" alt="City of Example seal"></p>'
    out = clean_html(html)
    assert out == "Intent."

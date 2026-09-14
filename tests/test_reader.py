from openatlas.reader import reader_document


def test_bridge_preserves_document_and_has_only_navigation_messages():
    original='<!doctype html><html><head><title>Lesson</title></head><body><h1>Test</h1></body></html>'
    result=reader_document(original)
    assert '<title>Lesson</title>' in result and '<h1>Test</h1>' in result
    assert result.count('openatlas-reader-style') == 1
    assert 'event.source !== parent' in result
    assert "type:'openatlas:outline'" in result
    assert "event.data.type === 'openatlas:section'" in result


def test_reader_hides_only_duplicate_app_masthead_and_reserves_toolbar_space():
    from playwright.sync_api import sync_playwright

    html = '''<!doctype html><html><head><title>Lesson</title></head><body>
    <header class="mast"><a href="#top">◈ OPENATLAS / FIELD NOTES</a><span>ENGINEERING & MEMORY</span></header>
    <main id="top"><header><h1>Chernobyl Atlas</h1></header><h2>Steam circuit</h2><button>Inspect the reactor</button></main>
    </body></html>'''
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        page.set_content(reader_document(html))
        assert not page.locator('body > header').is_visible()
        assert page.locator('main header').is_visible()
        assert page.get_by_role('button', name='Inspect the reactor').is_visible()
        assert page.locator('body').evaluate('(el) => getComputedStyle(el).paddingTop') == '80px'
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.locator('body').evaluate('(el) => getComputedStyle(el).paddingTop') == '70px'
        # A genuine lesson header with a heading must never be hidden.
        page.set_content(reader_document(html.replace('<span>ENGINEERING & MEMORY</span>', '<h1>A study of editorial branding</h1>')))
        assert page.locator('body > header').is_visible()
        browser.close()


def test_navigation_rule_survives_planned_custom_and_unskilled_builds():
    from openatlas.agents import CodexAdapter, READER_NAVIGATION_REQUIREMENTS
    from openatlas.planning import PlannerAdapter

    for extra in ({}, {'build_prompt': 'Create a dark reactor exhibit.'}, {'teaching_prompt': 'Use an editorial layout.'}, {'continue_job': 'old-job'}):
        result = CodexAdapter().prompt({'prompt': 'Explain reactors', 'skills': [], **extra})
        assert READER_NAVIGATION_REQUIREMENTS in result
        assert 'remove any existing duplicate application masthead' in result
    command = PlannerAdapter().command({'planner_model': 'test', 'planner_instructions': 'Use your own teaching approach.', 'skills': []})
    assert READER_NAVIGATION_REQUIREMENTS in command[-2]

from openatlas.reader import reader_document


def test_bridge_preserves_document_and_has_only_navigation_messages():
    original='<!doctype html><html><head><title>Lesson</title></head><body><h1>Test</h1></body></html>'
    result=reader_document(original)
    assert '<title>Lesson</title>' in result and '<h1>Test</h1>' in result
    assert result.count('openatlas-reader-style') == 1
    assert 'event.source !== parent' in result
    assert "type:'openatlas:outline'" in result
    assert "event.data.type === 'openatlas:section'" in result

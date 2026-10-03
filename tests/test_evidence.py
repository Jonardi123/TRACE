import hashlib
import io
import json
import pytest
from PIL import Image
from osint_workbench.core import Case
from osint_workbench.evidence import import_evidence, parse_messages, screenshot_text
from osint_workbench.storage import load_case, read_evidence, verify_evidence


def test_instagram_export_and_attachment_warnings():
    rows, warnings = parse_messages(json.dumps({'messages': [
        {'sender_name': 'Target', 'content':'Hello', 'timestamp_ms':1767225600000},
        {'sender_name': 'Target', 'photos':[]},
        {'sender_name': 'Other', 'content':'Reply', 'timestamp':'bad'}
    ]}).encode(), '.json')
    assert len(rows) == 2 and rows[0]['sender'] == 'Target'
    assert rows[0]['timestamp'].startswith('2026-01-01')
    assert rows[1]['timestamp'] is None
    assert any('Skipped 1' in w for w in warnings)
    assert any('Excluded 1' in w for w in warnings)


def test_csv_multiline_and_naive_timestamp():
    rows, warnings = parse_messages(b'sender,timestamp,text\nTarget,2026-01-01T12:00:00,"Hello\nworld"\n', '.csv')
    assert rows[0]['text'] == 'Hello\nworld' and rows[0]['timestamp'] is None
    assert warnings


def test_txt_never_invents_sender():
    rows, warnings = parse_messages(b'Hello\n\nWorld', '.txt')
    assert len(rows) == 2 and all(r['sender'] == '' and r['timestamp'] is None for r in rows)
    assert warnings


@pytest.mark.parametrize('raw,suffix', [(b'{}','.json'), (b'{bad','.json'),
    (b'[1]','.json'), (b'text\nx','.csv'), (b'[]','.json'), (b'\xff','.txt')])
def test_malformed_exports_fail(raw, suffix):
    with pytest.raises((ValueError, UnicodeError)):
        parse_messages(raw, suffix)


def test_size_limits(tmp_path):
    path = tmp_path/'big.txt'
    path.write_bytes(b'x'*11)
    with pytest.raises(ValueError):
        read_evidence(path, limit=10)
    with pytest.raises(ValueError):
        parse_messages(json.dumps([{'text':'a'}]*10001).encode(), '.json')


def test_preserve_hash_roundtrip_and_duplicate_rejection(tmp_path):
    source = tmp_path/'source.json'
    source.write_text('[{"sender":"Target", "text":"Hello"}]')
    case = Case('alice')
    directory = tmp_path/'case'
    item = import_evidence(case, directory, source, notes='Permitted sample')
    assert (directory/'evidence'/item.filename).read_bytes() == source.read_bytes()
    assert item.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert load_case(directory) == case
    assert verify_evidence(case, directory) == [(item.id,'intact')]
    with pytest.raises(ValueError, match='already imported'):
        import_evidence(case, directory, source)
    (directory/'evidence'/item.filename).write_text('changed')
    assert verify_evidence(case, directory) == [(item.id,'changed')]
    (directory/'evidence'/item.filename).unlink()
    assert verify_evidence(case, directory) == [(item.id,'missing or unreadable')]


def test_bad_capture_does_not_mutate_case(tmp_path):
    source = tmp_path/'source.txt'
    source.write_text('Hello')
    case = Case('alice')
    with pytest.raises(ValueError, match='Capture time'):
        import_evidence(case, tmp_path/'case', source, capture_at='2026-01-01T12:00:00')
    assert case.evidence == []


def test_no_ocr_and_corrupt_image():
    stream = io.BytesIO()
    Image.new('RGB', (100,100), 'white').save(stream, format='PNG')
    text, confidence, warnings = screenshot_text(stream.getvalue(), ocr=False)
    assert not text and confidence is None and any('disabled' in w for w in warnings)
    with pytest.raises(OSError):
        screenshot_text(b'not an image')


def test_ocr_line_grouping_and_confidence(monkeypatch):
    import pytesseract
    monkeypatch.setattr(pytesseract, 'image_to_data', lambda *a, **kw: {
        'text':['Hello','world','Next'], 'conf':['92','88','80'],
        'page_num':[1,1,1], 'block_num':[1,1,1], 'par_num':[1,1,1], 'line_num':[1,1,2]})
    stream = io.BytesIO()
    Image.new('RGB',(10,10),'white').save(stream,format='PNG')
    text, score, warnings = screenshot_text(stream.getvalue())
    assert text == 'Hello world\nNext' and score == 86.7
    assert any('authenticity' in w for w in warnings)


def test_ocr_failure_preserves_screenshot(monkeypatch, tmp_path):
    import pytesseract
    def fail(*a, **kw):
        raise RuntimeError('Tesseract timeout')
    monkeypatch.setattr(pytesseract, 'image_to_data', fail)
    source = tmp_path/'screen.png'
    Image.new('RGB',(20,20),'white').save(source)
    case = Case('alice')
    item = import_evidence(case, tmp_path/'case', source)
    assert item.kind == 'screenshot' and any('unavailable' in w for w in item.warnings)
    assert verify_evidence(case,tmp_path/'case')[0][1] == 'intact'


def test_symlink_and_traversal_are_not_verified(tmp_path):
    source = tmp_path/'source.txt'
    source.write_text('hello')
    case = Case('alice')
    item = import_evidence(case,tmp_path/'case',source)
    path = tmp_path/'case'/'evidence'/item.filename
    path.unlink()
    path.symlink_to(source)
    assert verify_evidence(case,tmp_path/'case')[0][1] == 'missing or unreadable'
    item.filename = '../../source.txt'
    assert verify_evidence(case,tmp_path/'case')[0][1] == 'invalid path'


def test_ocr_invalid_engine_version_does_not_exit_app(monkeypatch):
    import pytesseract
    def exit_engine(*args, **kwargs):
        raise SystemExit('Invalid tesseract version')
    monkeypatch.setattr(pytesseract,'image_to_data',exit_engine)
    raw = io.BytesIO()
    Image.new('RGB',(20,20),'white').save(raw,format='PNG')
    text,score,warnings = screenshot_text(raw.getvalue())
    assert not text and score is None
    assert any('SystemExit' in warning for warning in warnings)

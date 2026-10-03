from datetime import datetime, timedelta, timezone
import pytest
from osint_workbench.analysis import analyze
from osint_workbench.core import Case, Message, Observation
from osint_workbench.report import build_report, export_report
from osint_workbench.__main__ import demo
from osint_workbench.storage import load_case


def sample(count=12, sender='Target', gap=30, text='Repeated message', evidence='e1'):
    return [Message(sender, text, (datetime(2026,1,1,tzinfo=timezone.utc) + timedelta(seconds=gap*i)).isoformat(), evidence, i+1)
            for i in range(count)]


def test_explicit_sender_filter():
    case = Case('alice', messages=sample())
    findings = analyze(case)
    assert any(f.title == 'Sender analysis unavailable' for f in findings)
    assert not any('repetition measurement' in f.title.lower() for f in findings)
    case.target_sender = 'Other'
    assert any('Insufficient behavioral' in f.title for f in analyze(case))


def test_patterns_never_claim_bot_certainty():
    case = Case('alice', target_sender='Target', messages=sample())
    findings = analyze(case)
    possible = [f for f in findings if f.category == 'possible']
    assert any('Repeated text' in f.title for f in possible)
    assert any('Regular timing' in f.title for f in possible)
    assert all(f.confidence == 'low' for f in possible)
    assert any(f.title == 'Bot identity is not established' and f.category == 'unsupported' for f in findings)


def test_mixed_senders_dont_pollute_repetition():
    messages = [Message('Target',f'Unique message {i}',None,'e1',i) for i in range(8)] + sample(sender='Other')
    case = Case('alice',target_sender='Target',messages=messages)
    assert not any('Repeated text may' in f.title for f in analyze(case))


def test_timing_never_crosses_files_and_overlap_excluded():
    case = Case('alice',target_sender='Target',messages=sample(4,evidence='one') + sample(4,evidence='two'))
    findings = analyze(case)
    assert any('4 text messages; 4' in f.detail for f in findings)
    assert not any('Regular timing' in f.title for f in findings)
    case.messages = sample(4,evidence='one') + [Message('Target',f'Other {i}',
        (datetime(2026,1,2,tzinfo=timezone.utc)+timedelta(seconds=30*i)).isoformat(),'two',i) for i in range(4)]
    assert not any('Regular timing' in f.title for f in analyze(case))


def test_zero_gaps_burst_does_not_make_periodicity():
    findings = analyze(Case('alice',target_sender='Target',messages=sample(gap=0)))
    assert not any('Regular timing' in f.title for f in findings)
    assert any('burst' in f.title for f in findings)


def test_cross_export_overlap_keeps_same_file_multiplicity():
    first = sample(12, gap=0, evidence='one')
    second = sample(12, gap=0, evidence='two')
    findings = analyze(Case('alice',target_sender='Target',messages=first + second))
    assert any('12 text messages; 12' in f.detail for f in findings)


def test_under_threshold():
    assert any('Insufficient' in f.title for f in analyze(Case('alice',target_sender='Target',messages=sample(7))))


def test_xss_and_text_omission(tmp_path):
    payload = '<script>alert("x")</script>'
    case = Case('alice',target_sender='Target',messages=[Message('Target',payload,None,'e1',1)])
    case.observations = [Observation('Biography',payload,'javascript:alert(1)','2026-01-01T00:00:00Z')]
    report = build_report(case,tmp_path)
    assert '<script>' not in report and '&lt;script&gt;' in report
    assert 'href="javascript:' not in report
    assert 'Content-Security-Policy' in report and 'Raw message bodies' in report
    case.observations = []
    assert 'alert(' not in build_report(case,tmp_path)
    assert '&lt;script&gt;' in build_report(case,tmp_path,include_text=True)
    assert 'remote assets' in report


def test_end_to_end_demo(tmp_path):
    report = demo(tmp_path/'demo')
    case = load_case(tmp_path/'demo')
    assert len(case.messages) == 12 and report.exists()
    text = report.read_text()
    assert 'Regular timing' in text and 'Repeated text' in text
    assert 'SYNTHETIC DEMO' in text and 'Current integrity: <b>intact</b>' in text
    assert 'unsupported' in text and 'possible' in text and 'verified' in text
    with pytest.raises(ValueError):
        demo(tmp_path/'demo')


def test_report_destination_protects_evidence(tmp_path):
    case = Case('alice')
    with pytest.raises(ValueError):
        export_report(case,tmp_path,tmp_path/'case.json')
    with pytest.raises(ValueError):
        export_report(case,tmp_path,tmp_path/'evidence'/'report.html')


def test_report_warns_about_changed_original(tmp_path):
    demo(tmp_path/'case')
    case = load_case(tmp_path/'case')
    item = case.evidence[0]
    (tmp_path/'case'/'evidence'/item.filename).write_text('modified')
    report = build_report(case,tmp_path/'case')
    assert 'Evidence integrity warning' in report and 'changed' in report
    assert 'saved parsed case data' in report

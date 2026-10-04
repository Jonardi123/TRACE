import json
import zipfile
import pytest
from PIL import Image
from osint_workbench import __version__
from osint_workbench.analysis import analyze
from osint_workbench.bundle import export_bundle
from osint_workbench.core import Case
from osint_workbench.evidence import import_evidence, rerun_ocr, update_evidence
from osint_workbench.report import build_report
from osint_workbench.storage import load_case, save_case
from osint_workbench.workflow import checklist, record_observation, review_access
from osint_workbench.__main__ import demo


def screenshot(tmp_path):
    path=tmp_path/'provided.png'
    Image.new('RGB',(100,80),'white').save(path)
    return path


def test_instagram_workflow_keeps_unknowns_unknown(tmp_path):
    case=Case('alice')
    save_case(case,tmp_path/'case')
    assert all(state=='not recorded' for _,state in checklist(case))
    review_access(case,tmp_path/'case','Restricted / login required','2026-01-01T12:00:00Z','Synthetic access review')
    assert not case.observations and load_case(tmp_path/'case').instagram_review.access_status=='Restricted / login required'
    record_observation(case,tmp_path/'case','Biography','Synthetic biography','https://example.org/evidence','2026-01-01T12:00:00Z')
    assert dict(checklist(case))['Biography']=='recorded'
    assert dict(checklist(case))['Follower count']=='not recorded'
    report=build_report(case,tmp_path/'case')
    assert 'Restricted / login required' in report and 'no Instagram requests' in report


def test_transcription_requires_active_evidence_and_time(tmp_path):
    case=Case('alice')
    with pytest.raises(ValueError):
        record_observation(case,tmp_path,'Biography','x','https://example.org','2026-01-01T12:00:00Z',basis='Supplied evidence transcription')
    with pytest.raises(ValueError):
        review_access(case,tmp_path,'Public view reviewed','2026-01-01T12:00:00')
    assert not case.observations and case.instagram_review.access_status=='Not checked'


def test_unverified_notes_are_not_profile_facts(tmp_path):
    case=Case('alice')
    record_observation(case,tmp_path,'Biography','Unverified assumption','https://example.org','2026-01-01T12:00:00Z',basis='Unverified note')
    finding=next(f for f in analyze(case) if f.title=='Public observation: Biography')
    assert finding.category=='unsupported'
    assert dict(checklist(case))['Biography']=='not recorded'


def test_exclude_restore_keeps_original_and_affects_analysis(tmp_path):
    demo(tmp_path/'case');case=load_case(tmp_path/'case');item=case.evidence[0]
    original=(tmp_path/'case'/'evidence'/item.filename).read_bytes()
    update_evidence(case,tmp_path/'case',item.id,notes='Excluded duplicate sample',excluded=True)
    findings=analyze(case)
    assert not any('Repeated text may' in f.title for f in findings)
    assert (tmp_path/'case'/'evidence'/item.filename).read_bytes()==original
    assert 'excluded (original retained)' in build_report(case,tmp_path/'case')
    update_evidence(case,tmp_path/'case',item.id,notes='Restored',excluded=False)
    assert any('Repeated text may' in f.title for f in analyze(case))


def test_ocr_rerun_checks_hash_and_preserves_text_on_failure(tmp_path,monkeypatch):
    case=Case('alice');path=screenshot(tmp_path)
    item=import_evidence(case,tmp_path/'case',path,ocr=False)
    assert item.original_filename=='provided.png' and item.image_info['width']==100
    monkeypatch.setattr('osint_workbench.evidence.screenshot_text',lambda *a,**k:('Transcribed words',91,[]))
    item=rerun_ocr(case,tmp_path/'case',item.id)
    previous_time=item.ocr_at
    monkeypatch.setattr('osint_workbench.evidence.screenshot_text',lambda *a,**k:('',None,['OCR unavailable (timeout)']))
    item=rerun_ocr(case,tmp_path/'case',item.id)
    assert item.ocr_text=='Transcribed words' and item.ocr_at==previous_time
    assert case.audit_log[-1]['status']=='unavailable'
    (tmp_path/'case'/'evidence'/item.filename).write_bytes(b'altered')
    with pytest.raises(ValueError,match='changed'):
        rerun_ocr(case,tmp_path/'case',item.id)


def test_failed_import_and_annotation_save_roll_back(tmp_path,monkeypatch):
    source=tmp_path/'source.txt';source.write_text('Authorized sample')
    case=Case('alice');directory=tmp_path/'case';save_case(case,directory)
    before=case.to_dict()
    def fail(*args,**kwargs):
        raise OSError('Disk failure')
    monkeypatch.setattr('osint_workbench.storage.save_case',fail)
    with pytest.raises(OSError):
        import_evidence(case,directory,source)
    assert case.to_dict()==before and not list((directory/'evidence').iterdir())


def test_case_bundle_is_portable_and_fails_on_tampering(tmp_path):
    demo(tmp_path/'case');case=load_case(tmp_path/'case')
    path=tmp_path/'export.zip';export_bundle(case,tmp_path/'case',path)
    with zipfile.ZipFile(path) as bundle:
        assert bundle.testzip() is None
        assert {'case.json','manifest.json','report.html'}.issubset(bundle.namelist())
        manifest=json.loads(bundle.read('manifest.json'))
        assert manifest['version']==__version__
        assert manifest['files'][0]['sha256']==case.evidence[0].sha256
        bundle.extractall(tmp_path/'restored')
    restored=load_case(tmp_path/'restored')
    assert restored.messages==case.messages
    before=path.read_bytes()
    (tmp_path/'case'/'evidence'/case.evidence[0].filename).write_text('changed')
    with pytest.raises(ValueError):
        export_bundle(case,tmp_path/'case',path)
    assert path.read_bytes()==before


def test_malformed_saved_types_rejected(tmp_path):
    demo(tmp_path/'case')
    path=tmp_path/'case'/'case.json';original=json.loads(path.read_text())
    changes=[('text',42),('timestamp','bad'),('evidence_id','not-imported'),('row',False)]
    for field,value in changes:
        data=json.loads(json.dumps(original));data['messages'][0][field]=value
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError):
            load_case(tmp_path/'case')


def test_pre_trace_case_loads_without_new_fields(tmp_path):
    demo(tmp_path/'case')
    path=tmp_path/'case'/'case.json';data=json.loads(path.read_text())
    for field in ['public_results','instagram_review','audit_log']:
        data.pop(field)
    for item in data['evidence']:
        for field in ['original_filename','excluded','image_info','ocr_at']:
            item.pop(field)
    for observation in data['observations']:
        observation.pop('basis')
    path.write_text(json.dumps(data))
    loaded=load_case(tmp_path/'case')
    assert len(loaded.messages)==12 and loaded.instagram_review.access_status=='Not checked'


def test_repetition_pairs_do_not_suppress_no_signal():
    from osint_workbench.core import Message
    case=Case('alice',target_sender='Target',messages=[Message('Target',f'Pair {i//2}',None,'source',i+1) for i in range(8)])
    findings=analyze(case)
    assert not any(f.title=='Repeated text may reflect automation' for f in findings)
    assert any(f.title=='No configured signal triggered' for f in findings)


def test_failed_annotation_does_not_change_existing_metadata(tmp_path,monkeypatch):
    source=tmp_path/'source.txt';source.write_text('Authorized sample')
    case=Case('alice');item=import_evidence(case,tmp_path/'case',source)
    before=case.to_dict()
    def fail(*args,**kwargs):
        raise OSError('Disk failure')
    monkeypatch.setattr('osint_workbench.storage.save_case',fail)
    with pytest.raises(OSError):
        update_evidence(case,tmp_path/'case',item.id,notes='Not committed',excluded=True)
    assert case.to_dict()==before

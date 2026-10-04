"""Run under xvfb-run on CI/headless Kali; skipped when Tk/display is absent."""
import os
import gc
import sys
import threading
import pytest


@pytest.fixture(autouse=True)
def collect_closed_tk_objects_on_main_thread():
    yield
    # Closed Tk roots contain Python cycles. Collect them before a later test's
    # executor can trigger GC and finalize their Tcl objects on a worker thread.
    gc.collect()


def test_gui_layout_and_analysis(tmp_path):
    pytest.importorskip('tkinter')
    if sys.platform not in {'win32', 'darwin'} and not os.environ.get('DISPLAY'):
        pytest.skip('No display; run xvfb-run -a python -m pytest')
    from osint_workbench.gui import Workbench
    from osint_workbench.__main__ import demo
    from osint_workbench.storage import load_case
    demo(tmp_path/'demo')
    app = Workbench()
    try:
        app.case = load_case(tmp_path/'demo')
        app.directory = tmp_path/'demo'
        app.refresh()
        app.update()
        assert len(app.tabs.tabs()) == 4
        assert len(app.evidence_tree.get_children()) == 1
        assert app.sender.get() == 'Demo sender'
        app.run_analysis()
        assert 'Regular timing' in app.finding_text.get('1.0','end')
    finally:
        app.close()


def test_small_window_actions_are_scrollable():
    pytest.importorskip('tkinter')
    if sys.platform not in {'win32', 'darwin'} and not os.environ.get('DISPLAY'):
        pytest.skip('No display')
    from osint_workbench.gui import Workbench
    app = Workbench()
    try:
        app.geometry('1000x760')
        app.update()
        for page in [app.profile_tab,app.evidence_tab,app.search_tab,app.findings_tab]:
            app.tabs.select(page)
            app.update()
            for control in app.controls:
                if str(control).startswith(str(page)+'.'):
                    assert control.winfo_ismapped(), control.cget('text')
            region = page.canvas.bbox('all')
            assert region[3] >= page.canvas.winfo_height()
    finally:
        app.close()


def pump(app):
    import time
    deadline=time.monotonic()+5
    while app.busy and time.monotonic()<deadline:
        app.update()
        time.sleep(0.01)
    app.update()
    assert not app.busy, 'Background task did not finish'


def test_four_tab_workflows_and_background_recovery(tmp_path,monkeypatch):
    pytest.importorskip('tkinter')
    if sys.platform not in {'win32', 'darwin'} and not os.environ.get('DISPLAY'):
        pytest.skip('No display')
    import json
    from PIL import Image
    from osint_workbench.gui import TraceApp
    from osint_workbench.core import PublicResult, now
    from osint_workbench.storage import load_case
    folder=tmp_path/'case'
    errors=[];opened=[]
    monkeypatch.setattr('osint_workbench.gui.filedialog.askdirectory',lambda **kw:str(folder))
    monkeypatch.setattr('osint_workbench.gui.messagebox.showerror',lambda title,detail,**kw:errors.append(detail))
    monkeypatch.setattr('osint_workbench.gui.webbrowser.open',lambda url:opened.append(url) or True)
    app=TraceApp()
    try:
        app.handle.set('alice');app.new_case();app.update()
        assert app.title().startswith('TRACE')
        assert [app.tabs.tab(t,'text') for t in app.tabs.tabs()]==['Instagram','Evidence','Username research','Analysis & report']
        # Instagram: record access restriction without manufacturing profile values.
        app.tabs.select(app.profile_tab);app.update()
        app.review_status.set('Restricted / login required');app.review_time.set('2026-01-01T12:00:00Z');app.save_review()
        assert 'Restricted / login required' in app.profile_summary.get('1.0','end')
        assert not app.case.observations
        app.profile_source.set('https://example.org/synthetic/alice')
        app.profile_value.insert('1.0','Synthetic display name');app.add_observation()
        assert len(app.profile_tree.get_children())==1
        app.open_profile();assert opened[-1]=='https://www.instagram.com/alice/'
        # Evidence: actual file imports on the background worker; screenshot preview and OCR.
        app.tabs.select(app.evidence_tab);app.update()
        source=tmp_path/'messages.json'
        source.write_text(json.dumps([{'sender':'Fixture sender','text':'Synthetic repeated text',
            'timestamp':f'2026-01-01T12:{i:02d}:00Z'} for i in range(12)]))
        monkeypatch.setattr('osint_workbench.gui.filedialog.askopenfilename',lambda **kw:str(source))
        app.import_file();pump(app)
        assert len(app.case.messages)==12
        message_id=app.case.evidence[0].id
        image=tmp_path/'screen.png';Image.new('RGB',(100,80),'white').save(image)
        monkeypatch.setattr('osint_workbench.gui.filedialog.askopenfilename',lambda **kw:str(image))
        app.use_ocr.set(False);app.import_file();pump(app)
        image_id=app.case.evidence[-1].id
        app.evidence_tree.selection_set(image_id);app.evidence_detail()
        preview=app.view_screenshot();app.update();assert preview.photo.width()==100;preview.destroy()
        monkeypatch.setattr('osint_workbench.evidence.screenshot_text',lambda *a,**kw:('Synthetic OCR fixture',93,[]))
        app.retry_ocr();pump(app)
        assert app.case.evidence[-1].ocr_text=='Synthetic OCR fixture'
        app.evidence_note.set('Updated permitted context');app.save_annotations()
        assert app.case.evidence[-1].notes=='Updated permitted context'
        app.evidence_tree.selection_set(message_id);app.toggle_evidence()
        assert app.case.evidence[0].excluded
        app.evidence_tree.selection_set(message_id);app.toggle_evidence()
        assert not app.case.evidence[0].excluded
        # Username research: deterministic API fixture; manually supplied indexed result.
        app.tabs.select(app.search_tab);app.update()
        fixture=PublicResult('GitHub','alice','exact_public_handle',now(),'https://api.github.com/users/alice',
            profile_url='https://github.com/alice',returned_username='alice',detail='Synthetic API fixture; ownership unverified')
        monkeypatch.setattr('osint_workbench.gui.PublicResearch.research',lambda *a,**kw:[fixture])
        app.research_state_dir=tmp_path/'rate-state'
        app.public_research();pump(app)
        assert len(app.public_tree.get_children())==1
        app.public_tree.selection_set('0');app.public_detail()
        assert 'ownership unverified' in app.public_details.get('1.0','end')
        app.match_title.set('Synthetic @alice indexed mention');app.match_url.set('https://example.org/alice')
        app.match_snippet.set('Synthetic example only');app.add_match()
        assert len(app.match_tree.get_children())==1
        # Analysis/report: persistent sender selection and real report/bundle output.
        app.tabs.select(app.findings_tab);app.update();app.sender.set('Fixture sender');app.run_analysis()
        assert 'Repeated text may reflect automation' in app.finding_text.get('1.0','end')
        report=tmp_path/'report.html'
        monkeypatch.setattr('osint_workbench.gui.filedialog.asksaveasfilename',lambda **kw:str(report))
        app.export()
        assert 'TRACE / LOCAL EVIDENCE' in report.read_text() and 'Restricted / login required' in report.read_text()
        bundle=tmp_path/'case.zip'
        monkeypatch.setattr('osint_workbench.gui.filedialog.asksaveasfilename',lambda **kw:str(bundle))
        app.export_case_bundle();assert bundle.exists()
        assert load_case(folder).target_sender=='Fixture sender'
        # Worker exceptions restore controls without adding fabricated results.
        before=app.case.to_dict()
        def fail():
            raise ValueError('Synthetic worker failure')
        app.background(fail,lambda result:None,'Testing failure recovery');pump(app)
        assert errors==['Synthetic worker failure'] and app.case.to_dict()==before
        assert all(str(control.cget('state'))=='normal' for control in app.controls)
    finally:
        app.close()
        assert not any(thread.name.startswith('TRACE-worker') for thread in threading.enumerate())


def test_changed_header_handle_does_not_query_wrong_case(tmp_path):
    pytest.importorskip('tkinter')
    if sys.platform not in {'win32', 'darwin'} and not os.environ.get('DISPLAY'):
        pytest.skip('No display')
    from osint_workbench.gui import TraceApp
    from osint_workbench.core import Case
    app=TraceApp()
    try:
        app.case=Case('alice');app.directory=tmp_path;app.refresh()
        app.handle.set('bob')
        with pytest.raises(ValueError,match='differs'):
            app.public_research()
        assert not app.busy and not app.case.public_results
    finally:
        app.close()

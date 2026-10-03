from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, font as tkfont
import webbrowser

from .analysis import analyze
from .core import Case, now, public_url, username
from .bundle import export_bundle
from .evidence import import_evidence, rerun_ocr, update_evidence
from .research import PublicResearch, record_research
from .report import export_report
from .search import BraveSearch, browser_search_url, make_match
from .storage import commit_case, evidence_bytes, load_case, save_case, verify_evidence
from .workflow import ACCESS_STATUSES, OBSERVATION_BASES, checklist, profile_url, record_observation, review_access

BG = "#0b1220"
PANEL = "#152239"
TEXT = "#e6edf7"
MUTED = "#a6b5ca"
ACCENT = "#59d3c3"


class ScrollableTab(ttk.Frame):
    """Keep actions reachable on small screens and with larger system fonts."""
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(self, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self.canvas, padding=18)
        self.window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", self.resize)
        self.canvas.bind("<Configure>", self.resize)
        self.bind_all("<MouseWheel>", self.wheel, add="+")
        self.bind_all("<Button-4>", self.wheel, add="+")
        self.bind_all("<Button-5>", self.wheel, add="+")

    def resize(self, event=None):
        self.canvas.itemconfigure(self.window, width=self.canvas.winfo_width(),
                                  height=max(self.body.winfo_reqheight(), self.canvas.winfo_height()))
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def wheel(self, event):
        if self.canvas.winfo_ismapped() and not isinstance(event.widget, (tk.Text, ttk.Treeview, ttk.Combobox)):
            direction = -1 if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0 else 1
            self.canvas.yview_scroll(direction * 3, "units")


class Workbench(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TRACE • Public evidence investigation")
        self.geometry("1200x870")
        self.minsize(1000, 760)
        self.configure(bg=BG)
        self.case = None
        self.directory = None
        self.busy = False
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.events = queue.Queue()
        self.controls = []
        self.research_state_dir = None
        self._style()
        self._layout()
        self.after(100, self.poll)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        families = set(tkfont.families(self))
        self.font_family = next((f for f in ('DejaVu Sans', 'Noto Sans', 'Liberation Sans', 'Segoe UI', 'Helvetica') if f in families), tkfont.nametofont('TkDefaultFont').actual('family'))
        style.configure(".", background=PANEL, foreground=TEXT, font=(self.font_family, 11))
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG)
        style.configure("Title.TLabel", font=(self.font_family, 28, "bold"), foreground=ACCENT)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("TButton", padding=(14, 9), background="#284058", borderwidth=0)
        style.map("TButton", background=[("active", "#31556a"), ("disabled", "#1c2c40")],
                  foreground=[("disabled", "#68798f")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#102632")
        style.map("Accent.TButton", background=[("active", "#83e8db"), ("disabled", "#234940")])
        style.configure("TEntry", fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT, padding=8)
        style.configure("TCombobox", fieldbackground=PANEL, foreground=TEXT, padding=7)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", TEXT)])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(20, 12), background=PANEL, foreground=MUTED)
        style.map("TNotebook.Tab", background=[("selected", "#294459")], foreground=[("selected", ACCENT)])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=34, borderwidth=0)
        style.configure("Treeview.Heading", background="#26394e", foreground=TEXT, padding=8)
        style.map("Treeview", background=[("selected", "#31556a")])
        style.configure("TCheckbutton", background=BG, foreground=TEXT)
        style.map("TCheckbutton", background=[("active", BG)])
        style.configure('Vertical.TScrollbar', background='#304157', troughcolor=BG, arrowcolor=MUTED, borderwidth=0)
        self.option_add('*TCombobox*Listbox.background', PANEL)
        self.option_add('*TCombobox*Listbox.foreground', TEXT)
        self.option_add('*TCombobox*Listbox.selectBackground', '#31556a')
        style.configure("TProgressbar", troughcolor=PANEL, background=ACCENT)

    def button(self, parent, label, command, *, accent=False):
        button = ttk.Button(parent, text=label, command=lambda: self.safe(command),
                            style="Accent.TButton" if accent else "TButton")
        self.controls.append(button)
        return button

    def safe(self, action):
        if self.busy:
            return
        try:
            action()
        except Exception as exc:
            messagebox.showerror("Action could not be completed", str(exc), parent=self)

    def need_case(self):
        if not self.case:
            raise ValueError("Create or open a case first.")
        if username(self.handle.get()) != self.case.username:
            raise ValueError('Entered username differs from the open case. Create a new case for that username, or restore the current handle.')

    def _layout(self):
        outer = ttk.Frame(self, padding=24)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text="TRACE", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="PUBLIC EVIDENCE  /  LOCAL ANALYSIS  /  v0.2", foreground=MUTED).pack(side="right")
        ttk.Label(outer, text="Organize public observations. Review supplied evidence. Keep claims accountable.",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 20))
        bar = ttk.Frame(outer)
        bar.pack(fill="x", pady=(0, 12))
        self.handle = tk.StringVar()
        ttk.Label(bar, text="Instagram username").pack(side="left", padx=(0, 12))
        ttk.Entry(bar, textvariable=self.handle, width=24).pack(side="left", padx=(0, 10))
        self.button(bar, "New case", self.new_case, accent=True).pack(side="left", padx=4)
        self.button(bar, "Open case", self.open_case).pack(side="left", padx=4)
        self.button(bar, "Open public profile", self.open_profile).pack(side="left", padx=4)
        self.case_label = ttk.Label(outer, text="No case open · Evidence remains on this computer", style="Muted.TLabel")
        self.case_label.pack(anchor="w", pady=(0, 12))
        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill="both", expand=True)
        self.profile_tab = ScrollableTab(self.tabs)
        self.evidence_tab = ScrollableTab(self.tabs)
        self.search_tab = ScrollableTab(self.tabs)
        self.findings_tab = ScrollableTab(self.tabs)
        for frame, title in ((self.profile_tab, "Instagram"), (self.evidence_tab, "Evidence"),
                             (self.search_tab, "Username research"), (self.findings_tab, "Analysis & report")):
            self.tabs.add(frame, text=title)
        self._profile()
        self._evidence()
        self._search()
        self._findings()
        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(14, 0))
        self.status = tk.StringVar(value="Ready · No automatic network access")
        ttk.Label(footer, textvariable=self.status, style="Muted.TLabel", wraplength=850).pack(side="left")
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=140)
        self.progress.pack(side="right")

    def entry(self, parent, label, variable=None, width=50):
        ttk.Label(parent, text=label).pack(anchor="w", pady=(8, 4))
        var = variable or tk.StringVar()
        ttk.Entry(parent, textvariable=var, width=width).pack(fill="x")
        return var

    def text(self, parent, height=6, readonly=False):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, pady=6)
        text = tk.Text(frame, height=height, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                       relief="flat", padx=12, pady=10, wrap="word", font=(self.font_family, 11))
        scroll = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        if readonly:
            text.configure(state="disabled")
        return text

    def set_text(self, widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def table(self, parent, columns, height=7):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, pady=12)
        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=height)
        for key, label, width in columns:
            tree.heading(key, text=label)
            tree.column(key, width=width, minwidth=70)
        scroll = ttk.Scrollbar(frame, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        return tree

    def _profile(self):
        p = self.profile_tab.body
        ttk.Label(p, text="Record publicly visible account information with sources. Login-gated content remains unavailable.",
                  style="Muted.TLabel").pack(anchor="w")
        self.profile_summary = self.text(p, 6, readonly=True)
        row = ttk.Frame(p)
        row.pack(fill='x', pady=8)
        self.review_status = ttk.Combobox(row, state='readonly', values=ACCESS_STATUSES, width=28)
        self.review_status.set('Not checked')
        self.review_status.pack(side='left', padx=(0, 10))
        self.review_time = tk.StringVar(value=now())
        ttk.Entry(row, textvariable=self.review_time, width=30).pack(side='left', padx=8)
        self.button(row, 'Save access review', self.save_review).pack(side='right')
        self.review_notes = self.entry(p, 'Access review notes (investigator supplied)')
        row = ttk.Frame(p)
        row.pack(fill="x", pady=10)
        self.profile_field = tk.StringVar(value="Display name")
        self.field_box = ttk.Combobox(row, textvariable=self.profile_field, state="readonly", width=22,
            values=["Display name", "Biography", "Post count", "Follower count", "Following count", "Public link", "Visibility", "Public activity note"])
        self.field_box.pack(side="left", padx=(0, 12))
        self.profile_time = tk.StringVar(value=now())
        ttk.Label(row, text="Observed at (ISO time + timezone)").pack(side="left", padx=10)
        ttk.Entry(row, textvariable=self.profile_time, width=30).pack(side="left", fill="x", expand=True)
        self.profile_source = self.entry(p, "Public source URL")
        self.observation_basis = ttk.Combobox(p, state='readonly', values=OBSERVATION_BASES)
        self.observation_basis.set(OBSERVATION_BASES[0])
        self.observation_basis.pack(fill='x', pady=10)
        ttk.Label(p, text="Observation value").pack(anchor="w", pady=(12, 0))
        self.profile_value = self.text(p, 3)
        row = ttk.Frame(p)
        row.pack(fill="x")
        ttk.Label(row, text="Supporting evidence (optional)").pack(side="left", padx=(0, 12))
        self.profile_evidence = ttk.Combobox(row, state="readonly", width=24, values=[""])
        self.profile_evidence.pack(side="left")
        self.button(row, "Record observation", self.add_observation, accent=True).pack(side="right")
        self.profile_tree = self.table(p, [("field", "Field", 170), ("value", "Observation", 450), ("time", "Observed at", 250)], 5)
        self.button(p, "Remove selected observation", self.remove_observation).pack(anchor="w")

    def _evidence(self):
        p = self.evidence_tab.body
        ttk.Label(p, text="Import authorized JSON/CSV/TXT messages or screenshots. Original bytes are copied and hashed.",
                  style="Muted.TLabel", wraplength=1000).pack(anchor="w")
        self.evidence_source = self.entry(p, "Public source URL (optional)")
        self.evidence_time = self.entry(p, "Capture time (optional; ISO 8601 with timezone, otherwise unknown)")
        self.evidence_note = self.entry(p, "Evidence context / permission note (optional)")
        row = ttk.Frame(p)
        row.pack(fill="x", pady=12)
        self.use_ocr = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="Local screenshot OCR (Tesseract)", variable=self.use_ocr).pack(side="left")
        self.button(row, "Import file", self.import_file, accent=True).pack(side="right")
        self.button(row, "Verify stored hashes", self.verify).pack(side="right", padx=10)
        self.evidence_tree = self.table(p, [("kind", "Type", 120), ("id", "Evidence ID", 210),
                                          ("time", "Imported (UTC)", 250), ("hash", "SHA-256 (prefix)", 190)], 4)
        self.evidence_tree.bind("<<TreeviewSelect>>", lambda event: self.evidence_detail())
        row = ttk.Frame(p)
        row.pack(fill='x', pady=8)
        self.button(row, 'View screenshot', self.view_screenshot).pack(side='left', padx=(0, 8))
        self.button(row, 'Rerun OCR', self.retry_ocr).pack(side='left', padx=8)
        self.button(row, 'Save annotations', self.save_annotations).pack(side='left', padx=8)
        self.button(row, 'Exclude / restore', self.toggle_evidence).pack(side='left', padx=8)
        self.evidence_details = self.text(p, 7, readonly=True)
        self.set_text(self.evidence_details, "Select an evidence file to review its provenance, parsing warnings and OCR transcription.")

    def _search(self):
        p = self.search_tab.body
        ttk.Label(p, text='Direct public profile APIs · Exact handles only · No identity linkage', foreground=ACCENT).pack(anchor='w')
        row = ttk.Frame(p)
        row.pack(fill='x', pady=12)
        self.github_selected = tk.BooleanVar(value=True)
        self.gitlab_selected = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text='GitHub', variable=self.github_selected).pack(side='left', padx=(0, 12))
        ttk.Checkbutton(row, text='GitLab', variable=self.gitlab_selected).pack(side='left', padx=12)
        self.button(row, 'Research public handles (no key)', self.public_research, accent=True).pack(side='right')
        ttk.Label(p, text='Only selected providers receive the handle. One unauthenticated request per provider; '
                  '60-second local cooldown plus provider limits. Errors remain unavailable results.',
                  style='Muted.TLabel', wraplength=900).pack(anchor='w')
        self.public_tree = self.table(p, [('provider', 'Provider', 150), ('status', 'Observed status', 250),
            ('handle', 'Returned handle', 220), ('time', 'Checked (UTC)', 280)], 3)
        self.public_tree.bind('<<TreeviewSelect>>', lambda event: self.public_detail())
        self.public_details = self.text(p, 4, readonly=True)
        self.button(p, 'Open selected public profile', self.open_public_result).pack(anchor='e', pady=8)
        ttk.Label(p, text="Search public indexes for exact username tokens. Matches do not establish common ownership.",
                  style="Muted.TLabel").pack(anchor="w")
        row = ttk.Frame(p)
        row.pack(fill="x", pady=12)
        self.button(row, "Search in browser", self.browser_search, accent=True).pack(side="left", padx=(0, 10))
        self.button(row, "Search via Brave API", self.api_search).pack(side="left")
        ttk.Label(p, text="API requires BRAVE_SEARCH_API_KEY; one page / 20 results, ≥5 seconds between requests.\n"
                  "Browser search shares only the username with your search engine. API searches share it with Brave.",
                  style="Muted.TLabel", wraplength=1000).pack(anchor="w")
        self.match_title = self.entry(p, "Indexed result title")
        self.match_url = self.entry(p, "Public result URL")
        self.match_snippet = self.entry(p, "Indexed snippet (paste only a public result)")
        self.button(p, "Add exact result", self.add_match).pack(anchor="e", pady=8)
        self.match_tree = self.table(p, [("title", "Possible match", 340), ("url", "Source link", 420), ("basis", "Exact token basis", 220)], 5)
        self.match_tree.bind("<<TreeviewSelect>>", lambda event: self.match_detail())
        self.match_details = self.text(p, 3, readonly=True)
        row = ttk.Frame(p)
        row.pack(fill="x")
        self.button(row, "Open selected source", self.open_match).pack(side="left")
        self.button(row, "Remove selected result", self.remove_match).pack(side="left", padx=10)

    def _findings(self):
        p = self.findings_tab.body
        ttk.Label(p, text="Select the export's exact sender label. Linking that label to the account is your supplied attribution.",
                  style="Muted.TLabel", wraplength=1000).pack(anchor="w")
        row = ttk.Frame(p)
        row.pack(fill="x", pady=12)
        self.sender = ttk.Combobox(row, state="readonly", width=35, values=[""])
        self.sender.pack(side="left", padx=(0, 12))
        self.button(row, "Analyze sample", self.run_analysis, accent=True).pack(side="left")
        self.finding_text = self.text(p, 20, readonly=True)
        self.set_text(self.finding_text, "Create a case and import evidence to begin. Pattern findings will appear here with their thresholds and limits.")
        self.include_text = tk.BooleanVar(value=False)
        ttk.Checkbutton(p, text="Include all message bodies and OCR text in report (may contain private conversation content)",
                        variable=self.include_text).pack(anchor="w", pady=8)
        ttk.Label(p, text="Reports always include entered public observations, evidence notes and indexed snippets.",
                  style="Muted.TLabel").pack(anchor="w")
        self.button(p, "Export HTML report", self.export, accent=True).pack(anchor="e", pady=10)
        self.button(p, 'Export full case ZIP (includes originals)', self.export_case_bundle).pack(anchor='e', pady=8)

    def new_case(self):
        handle = username(self.handle.get())
        folder = filedialog.askdirectory(title="Choose a new, empty case folder", mustexist=False, parent=self)
        if not folder:
            return
        directory = Path(folder)
        if (directory / "case.json").exists():
            raise ValueError("This folder already contains a case. Use Open case.")
        case = Case(handle)
        save_case(case, directory)
        self.case, self.directory = case, directory
        self.profile_source.set(f"https://www.instagram.com/{handle}/")
        self.refresh(reset_forms=True)
        self.status.set("Case created · Changes are saved automatically")

    def open_case(self):
        folder = filedialog.askdirectory(title="Open folder containing case.json", parent=self)
        if not folder:
            return
        case = load_case(Path(folder))
        self.case, self.directory = case, Path(folder)
        self.handle.set(case.username)
        self.profile_source.set(f"https://www.instagram.com/{case.username}/")
        self.refresh(reset_forms=True)
        self.verify()

    def open_profile(self):
        self.need_case()
        self.open_url(profile_url(self.case))
        self.status.set("Profile opened in your browser · Record only publicly visible content")

    def refresh(self, reset_forms=False):
        self.handle.set(self.case.username)
        self.case_label.configure(text=f"@{self.case.username}  ·  {len(self.case.evidence)} files  ·  "
                                  f"{len(self.case.messages)} messages  ·  {self.directory}")
        for tree in (self.profile_tree, self.evidence_tree, self.match_tree, self.public_tree):
            tree.delete(*tree.get_children())
        for i, observation in enumerate(self.case.observations):
            self.profile_tree.insert("", "end", iid=str(i), values=(observation.field, observation.value, observation.observed_at))
        for item in self.case.evidence:
            self.evidence_tree.insert("", "end", iid=item.id, values=(item.kind + (' / excluded' if item.excluded else ''), item.id, item.imported_at, item.sha256[:20]))
        for i, match in enumerate(self.case.matches):
            self.match_tree.insert("", "end", iid=str(i), values=(match.title, match.url, match.match_basis))
        for i, result in enumerate(self.case.public_results):
            self.public_tree.insert('', 'end', iid=str(i), values=(result.provider, result.status, result.returned_username or 'none recorded', result.checked_at))
        self.profile_evidence.configure(values=[""] + [e.id for e in self.case.evidence if not e.excluded])
        self.profile_evidence.set("")
        self.sender.configure(values=[""] + sorted({m.sender for m in self.case.messages if m.sender}))
        self.sender.set(self.case.target_sender)
        self.show_findings()
        review = self.case.instagram_review
        self.review_status.set(review.access_status)
        self.review_time.set(review.checked_at or now())
        self.review_notes.set(review.notes)
        self.set_text(self.profile_summary, f'@{self.case.username} · {profile_url(self.case)}\n'
            f'Access: {review.access_status} · Actual review time: {review.checked_at or "not recorded"}\n'
            + '  |  '.join(f'{field}: {state}' for field, state in checklist(self.case))
            + '\nTRACE has not fetched Instagram content. Missing fields are unknown, not zero.')
        self.set_text(self.public_details, 'Select a public lookup result to see its source, status and limitations.')
        if reset_forms:
            self.profile_value.delete('1.0', 'end')
            self.profile_time.set(now())
            self.observation_basis.set(OBSERVATION_BASES[0])
            for var in (self.evidence_source, self.evidence_time, self.evidence_note, self.match_title, self.match_url, self.match_snippet):
                var.set('')
        self.set_text(self.evidence_details, "Select an evidence file to review its provenance and extracted text.")
        self.set_text(self.match_details, "Select a result to review its exact-token basis and indexed snippet.")

    def add_observation(self):
        self.need_case()
        value = self.profile_value.get("1.0", "end").strip()
        if not value:
            raise ValueError("Enter an observation value.")
        record_observation(self.case, self.directory, self.profile_field.get(), value, self.profile_source.get(),
                           self.profile_time.get(), self.profile_evidence.get(), self.observation_basis.get())
        self.profile_value.delete("1.0", "end")
        self.refresh()
        self.status.set("Public observation recorded with source and timestamp")

    def remove_observation(self):
        self.need_case()
        selection = self.profile_tree.selection()
        if selection:
            def remove(draft):
                del draft.observations[int(selection[0])]
                draft.audit_log.append({'at': now(), 'action': 'observation_removed'})
            commit_case(self.case, self.directory, remove)
            self.refresh()

    def import_file(self):
        self.need_case()
        path = filedialog.askopenfilename(title="Import evidence you have permission to examine", parent=self,
            filetypes=[("Supported evidence", "*.json *.csv *.txt *.png *.jpg *.jpeg *.webp *.tif *.tiff *.bmp"), ("All files", "*")])
        if not path:
            return
        kwargs = dict(ocr=self.use_ocr.get(), source_url=self.evidence_source.get().strip(),
                      capture_at=self.evidence_time.get().strip(), notes=self.evidence_note.get().strip())
        self.background(lambda: import_evidence(self.case, self.directory, Path(path), **kwargs),
                        lambda result: self.import_done(result), "Importing evidence / running local OCR…")

    def import_done(self, result):
        self.refresh()
        self.evidence_tree.selection_set(result.id)
        self.evidence_detail()
        self.status.set("Evidence imported and saved · Review parsing/OCR warnings")

    def evidence_detail(self):
        if not self.case or not self.evidence_tree.selection():
            return
        selected = self.evidence_tree.selection()[0]
        item = next(e for e in self.case.evidence if e.id == selected)
        self.evidence_note.set(item.notes)
        self.evidence_source.set(item.source_url)
        self.evidence_time.set(item.capture_at or '')
        detail = f"Evidence {item.id}\nStored: {item.filename}\nSHA-256: {item.sha256}\nImported: {item.imported_at}\n" \
                 f"Capture time: {item.capture_at or 'unknown'}\nPublic source: {item.source_url or 'none supplied'}\nNotes: {item.notes}\n\n"
        detail += "\n".join(item.warnings)
        detail += f'\nOriginal filename: {item.original_filename or "unknown (older case)"}\nStatus: {"excluded" if item.excluded else "active"}'
        if item.kind == "screenshot":
            detail += f"\nImage info: {item.image_info}\nLast OCR: {item.ocr_at or 'unknown / not run'}\n\nMean OCR word score: {item.ocr_confidence}\nUNVERIFIED OCR TEXT:\n{item.ocr_text or '(unavailable)'}"
        else:
            counts = {}
            for message in self.case.messages:
                if message.evidence_id == item.id:
                    key = message.sender or "(unattributed)"
                    counts[key] = counts.get(key, 0) + 1
            detail += "\n\nSender labels: " + ", ".join(f"{k}: {v}" for k, v in counts.items())
        self.set_text(self.evidence_details, detail)

    def verify(self):
        self.need_case()
        states = verify_evidence(self.case, self.directory)
        problems = [f"{id}: {state}" for id, state in states if state != "intact"]
        if problems:
            messagebox.showwarning("Evidence integrity", "\n".join(problems), parent=self)
        self.status.set(f"Hash verification: {len(states) - len(problems)}/{len(states)} evidence copies intact")

    def browser_search(self):
        self.need_case()
        query = f'"{self.case.username}"'
        self.open_url(browser_search_url(self.case.username))
        log = {"query": query, "provider": "DuckDuckGo browser", "opened_at": now(),
               "status": "Browser launched; results not automatically collected or verified."}
        commit_case(self.case, self.directory, lambda draft: draft.search_log.append(log))
        self.status.set("Search opened · Inspect exact tokens and add public indexed results")

    def api_search(self):
        self.need_case()
        self.background(lambda: BraveSearch().search(self.case.username), self.api_done, "Searching Brave's public index…")

    def api_done(self, result):
        matches, log = result
        def add(draft):
            known = {m.url for m in draft.matches}
            draft.matches.extend(m for m in matches if m.url not in known)
            draft.search_log.append(log)
        commit_case(self.case, self.directory, add)
        self.refresh()
        self.status.set(f"Search complete · {len(matches)} exact-token results returned, ownership unverified")

    def add_match(self):
        self.need_case()
        match = make_match(self.case.username, self.match_title.get(), self.match_url.get(), self.match_snippet.get(),
                           query=f'"{self.case.username}"')
        if any(m.url == match.url for m in self.case.matches):
            raise ValueError("This source URL is already recorded.")
        commit_case(self.case, self.directory, lambda draft: draft.matches.append(match))
        self.refresh()
        self.status.set("Exact indexed result recorded as a possible match")

    def match_detail(self):
        if self.case and self.match_tree.selection():
            match = self.case.matches[int(self.match_tree.selection()[0])]
            self.set_text(self.match_details, f"{match.match_basis}\n{match.provider} · {match.retrieved_at}\n{match.snippet}")

    def open_match(self):
        self.need_case()
        if self.match_tree.selection():
            self.open_url(public_url(self.case.matches[int(self.match_tree.selection()[0])].url))

    def remove_match(self):
        self.need_case()
        if self.match_tree.selection():
            index = int(self.match_tree.selection()[0])
            def remove(draft):
                del draft.matches[index]
                draft.audit_log.append({'at': now(), 'action': 'indexed_result_removed'})
            commit_case(self.case, self.directory, remove)
            self.refresh()

    def run_analysis(self):
        self.need_case()
        selected = self.sender.get()
        if selected and selected not in {m.sender for m in self.case.messages if m.sender}:
            raise ValueError('Select an existing sender label from the export.')
        commit_case(self.case, self.directory, lambda draft: setattr(draft, 'target_sender', selected))
        self.show_findings()
        self.status.set("Analysis complete · Confidence describes observations, not bot probability")

    def show_findings(self):
        content = []
        for finding in analyze(self.case):
            content.append(f"{finding.category.upper()}  /  {finding.confidence.upper()} CONFIDENCE\n{finding.title}\n"
                           f"{finding.detail}\nWhy: {finding.explanation}\nEvidence: {', '.join(finding.evidence_ids) or 'none'}\n")
        self.set_text(self.finding_text, "\n".join(content))
        for category, color in [('VERIFIED', ACCENT), ('POSSIBLE', '#f4c56b'), ('UNSUPPORTED', MUTED)]:
            self.finding_text.tag_configure(category, foreground=color, font=(self.font_family, 11, 'bold'))
            for line, text in enumerate(self.finding_text.get('1.0', 'end').splitlines(), 1):
                if text.startswith(category + '  /'):
                    self.finding_text.tag_add(category, f'{line}.0', f'{line}.end')

    def export(self):
        self.need_case()
        self.run_analysis()
        destination = filedialog.asksaveasfilename(title="Save self-contained HTML report", defaultextension=".html",
            initialdir=self.directory, initialfile=f"{self.case.username}-report.html", filetypes=[("HTML report", "*.html")], parent=self)
        if destination:
            export_report(self.case, self.directory, Path(destination), include_text=self.include_text.get())
            self.status.set(f"Report saved: {destination}")
            self.open_url(Path(destination).resolve().as_uri())

    def open_url(self, url):
        if not webbrowser.open(url):
            raise ValueError('No browser could be launched. Open the source URL or report file manually.')

    def save_review(self):
        self.need_case()
        review_access(self.case, self.directory, self.review_status.get(), self.review_time.get(), self.review_notes.get())
        self.refresh()
        self.status.set('Investigator-supplied access review saved; no Instagram retrieval claimed')

    def selected_evidence(self):
        self.need_case()
        selection = self.evidence_tree.selection()
        if not selection:
            raise ValueError('Select an imported evidence file first.')
        return next(e for e in self.case.evidence if e.id == selection[0])

    def save_annotations(self):
        item = self.selected_evidence()
        updated = update_evidence(self.case, self.directory, item.id, notes=self.evidence_note.get(),
                                  source_url=self.evidence_source.get(), capture_at=self.evidence_time.get())
        self.import_done(updated)
        self.status.set('Evidence annotations saved; original file and hash preserved')

    def toggle_evidence(self):
        item = self.selected_evidence()
        updated = update_evidence(self.case, self.directory, item.id, notes=item.notes,
            source_url=item.source_url, capture_at=item.capture_at or '', excluded=not item.excluded)
        self.import_done(updated)
        self.status.set('Evidence excluded from analysis; original retained' if updated.excluded else 'Evidence restored to analysis')

    def view_screenshot(self):
        item = self.selected_evidence()
        if item.kind != 'screenshot':
            raise ValueError('Select a screenshot, not a message export.')
        import io
        from PIL import Image, ImageOps, ImageTk
        raw = evidence_bytes(item, self.directory)
        with Image.open(io.BytesIO(raw)) as original:
            if original.width * original.height > 20_000_000:
                raise ValueError('Screenshot exceeds pixel limit.')
            image = ImageOps.exif_transpose(original).convert('RGB')
            image.thumbnail((900, 650))
        window = tk.Toplevel(self)
        window.title('TRACE • Supplied screenshot (authenticity unverified)')
        window.configure(bg=BG)
        ttk.Label(window, text=f'{item.id} · Stored bytes match recorded SHA-256 · Content remains unverified',
                  padding=12).pack(fill='x')
        window.photo = ImageTk.PhotoImage(image, master=window)
        ttk.Label(window, image=window.photo, padding=12).pack()
        return window

    def retry_ocr(self):
        item = self.selected_evidence()
        self.background(lambda: rerun_ocr(self.case, self.directory, item.id), self.ocr_done,
                        'Running local OCR on verified stored bytes…')

    def ocr_done(self, item):
        self.import_done(item)
        self.status.set('OCR attempt saved; inspect transcription and warnings')

    def public_research(self):
        self.need_case()
        providers = [name for name, selected in [('GitHub', self.github_selected), ('GitLab', self.gitlab_selected)] if selected.get()]
        if not providers:
            raise ValueError('Select at least one public provider.')
        handle = self.case.username
        self.background(lambda: PublicResearch(state_dir=self.research_state_dir).research(handle, providers),
                        self.public_done, 'Checking selected public profile APIs…')

    def public_done(self, results):
        record_research(self.case, self.directory, results)
        self.refresh()
        self.status.set('Public lookup: ' + ' · '.join(f'{r.provider}: {r.status}' for r in results))

    def public_detail(self):
        if self.case and self.public_tree.selection():
            result = self.case.public_results[int(self.public_tree.selection()[0])]
            detail = f'{result.provider} · {result.status}\nRequested: {result.requested_username}\nChecked: {result.checked_at}\n'
            detail += f'API: {result.request_url}\nPublic profile: {result.profile_url or "not retrieved"}\n{result.detail}\n'
            detail += '\n'.join(f'{key}: {value}' for key, value in result.fields.items())
            self.set_text(self.public_details, detail)

    def open_public_result(self):
        self.need_case()
        if not self.public_tree.selection():
            raise ValueError('Select a public research result.')
        result = self.case.public_results[int(self.public_tree.selection()[0])]
        if not result.profile_url:
            raise ValueError('No accessible public profile was returned; no account link can be opened.')
        self.open_url(public_url(result.profile_url))

    def export_case_bundle(self):
        self.need_case()
        destination = filedialog.asksaveasfilename(title='Save full case ZIP: includes original evidence and all conversation records',
            defaultextension='.zip', initialdir=self.directory, initialfile=f'{self.case.username}-case.zip',
            filetypes=[('Full case bundle', '*.zip')], parent=self)
        if destination:
            export_bundle(self.case, self.directory, Path(destination))
            self.status.set(f'Full case bundle saved locally: {destination}')

    def background(self, function, complete, message):
        self.busy = True
        for control in self.controls:
            control.configure(state="disabled")
        self.progress.start(12)
        self.status.set(message)
        future = self.worker.submit(function)
        future.add_done_callback(lambda result: self.events.put((result, complete)))

    def poll(self):
        try:
            future, complete = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.progress.stop()
            for control in self.controls:
                control.configure(state="normal")
            try:
                complete(future.result())
            except Exception as exc:
                self.status.set("Action failed · Existing case remains available")
                messagebox.showerror("Action could not be completed", str(exc), parent=self)
        self.after(100, self.poll)

    def close(self):
        if self.busy:
            self.status.set("Wait for the current import/search to finish before closing")
            return
        self.worker.shutdown(wait=False, cancel_futures=True)
        self.destroy()


def launch(directory=None):
    try:
        app = Workbench()
    except tk.TclError:
        raise ValueError('TRACE requires a graphical X display for the GUI. Use the CLI or run GUI tests under Xvfb.') from None
    if directory is not None:
        try:
            app.case = load_case(Path(directory))
            app.directory = Path(directory)
            app.profile_source.set(profile_url(app.case))
            app.refresh(reset_forms=True)
            app.verify()
        except Exception:
            app.close()
            raise
    app.mainloop()


TraceApp = Workbench  # Keep existing Python imports compatible.

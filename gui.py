# frontend/gui.py  — updated with JD file upload + multiple resume support
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import requests
import os

BACKEND_URL = "http://127.0.0.1:5000"


class ResumeMatcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Resume ↔ Job Description Matcher")
        self.geometry("1150x820")
        self.minsize(1000, 700)
        self.configure(bg="#F0F4F8")

        self.jd_text        = ""          # extracted JD text
        self.jd_filename    = tk.StringVar(value="No file selected")
        self.jd_meta        = tk.StringVar(value="")

        # list of dicts: {"filename": str, "text": str, "path": str}
        self.resume_list    = []

        self._build_ui()
        self._check_backend_health()

    # ══════════════════════════════════════════════════════════
    #  UI BUILD
    # ══════════════════════════════════════════════════════════

    def _build_ui(self):
        self._build_header()
        self._build_status_bar()
        self._build_main_panels()
        self._build_match_button()
        self._build_results_panel()

    def _build_header(self):
        h = tk.Frame(self, bg="#1A73E8", pady=12)
        h.pack(fill="x")
        tk.Label(h, text="📄  Resume ↔ Job Description Matcher",
                 font=("Helvetica", 18, "bold"), bg="#1A73E8", fg="white").pack()
        tk.Label(h, text="Upload resumes and a job description to get ranked match scores",
                 font=("Helvetica", 10), bg="#1A73E8", fg="#D0E4FF").pack()

    def _build_status_bar(self):
        self.status_var = tk.StringVar(value="⏳  Connecting to backend...")
        bar = tk.Frame(self, bg="#E8F0FE", pady=5)
        bar.pack(fill="x", padx=10, pady=(8, 0))
        self.status_label = tk.Label(bar, textvariable=self.status_var,
                                     font=("Helvetica", 10), bg="#E8F0FE",
                                     fg="#333333", anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True, padx=10)
        tk.Button(bar, text="↺ Retry", command=self._check_backend_health,
                  bg="#1A73E8", fg="white", font=("Helvetica", 9, "bold"),
                  relief="flat", cursor="hand2", padx=8, pady=2).pack(side="right", padx=10)

    def _build_main_panels(self):
        container = tk.Frame(self, bg="#F0F4F8")
        container.pack(fill="both", expand=True, padx=14, pady=10)

        # ── Left: Job Description ──────────────────────────────
        left = tk.Frame(container, bg="#CCCCCC")
        left.place(relx=0, rely=0, relwidth=0.48, relheight=1.0)
        left_in = tk.Frame(left, bg="white")
        left_in.pack(fill="both", expand=True, padx=1, pady=1)

        tk.Label(left_in, text="📋  Job Description", font=("Helvetica", 12, "bold"),
                 bg="white", fg="#1A73E8", anchor="w", pady=8).pack(fill="x", padx=10)
        ttk.Separator(left_in).pack(fill="x", padx=10)

        # JD file upload row
        jd_row = tk.Frame(left_in, bg="white")
        jd_row.pack(fill="x", padx=10, pady=(8, 2))
        tk.Button(jd_row, text="  📂  Upload JD File  ", command=self._browse_jd,
                  bg="#1A73E8", fg="white", font=("Helvetica", 10, "bold"),
                  relief="flat", cursor="hand2", padx=8, pady=5).pack(side="left")
        tk.Label(jd_row, textvariable=self.jd_filename, font=("Helvetica", 10),
                 bg="white", fg="#555555", wraplength=200, anchor="w").pack(side="left", padx=(8,0))

        tk.Label(left_in, textvariable=self.jd_meta, font=("Helvetica", 9),
                 bg="white", fg="#888888", anchor="w").pack(fill="x", padx=10)

        tk.Label(left_in, text="— or paste below —", font=("Helvetica", 9, "italic"),
                 bg="white", fg="#AAAAAA").pack(pady=(4, 0))

        self.jd_input = scrolledtext.ScrolledText(
            left_in, font=("Helvetica", 10), wrap=tk.WORD,
            relief="flat", bd=0, bg="#FFFFFF", fg="#AAAAAA",
            insertbackground="#1A73E8", padx=8, pady=8)
        self.jd_input.insert("1.0", "Paste job description here...")
        self.jd_input.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.jd_input.bind("<FocusIn>",  self._jd_focus_in)
        self.jd_input.bind("<FocusOut>", self._jd_focus_out)

        # ── Right: Multiple Resumes ────────────────────────────
        right = tk.Frame(container, bg="#CCCCCC")
        right.place(relx=0.50, rely=0, relwidth=0.50, relheight=1.0)
        right_in = tk.Frame(right, bg="white")
        right_in.pack(fill="both", expand=True, padx=1, pady=1)

        tk.Label(right_in, text="📎  Resumes", font=("Helvetica", 12, "bold"),
                 bg="white", fg="#1A73E8", anchor="w", pady=8).pack(fill="x", padx=10)
        ttk.Separator(right_in).pack(fill="x", padx=10)

        # Buttons row
        btn_row = tk.Frame(right_in, bg="white")
        btn_row.pack(fill="x", padx=10, pady=(8, 4))
        tk.Button(btn_row, text="  ➕  Add Resumes  ", command=self._browse_resumes,
                  bg="#1A73E8", fg="white", font=("Helvetica", 10, "bold"),
                  relief="flat", cursor="hand2", padx=8, pady=5).pack(side="left")
        tk.Button(btn_row, text="🗑 Clear All", command=self._clear_resumes,
                  bg="#EA4335", fg="white", font=("Helvetica", 9, "bold"),
                  relief="flat", cursor="hand2", padx=8, pady=5).pack(side="left", padx=(8,0))
        self.resume_count_var = tk.StringVar(value="0 resumes loaded")
        tk.Label(btn_row, textvariable=self.resume_count_var,
                 font=("Helvetica", 9), bg="white", fg="#888888").pack(side="right")

        # Resume listbox with scrollbar
        list_frame = tk.Frame(right_in, bg="white")
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        self.resume_listbox = tk.Listbox(
            list_frame, font=("Helvetica", 10), selectmode=tk.SINGLE,
            relief="flat", bd=0, bg="#F8F9FA", fg="#333333",
            selectbackground="#D0E4FF", selectforeground="#1A73E8",
            activestyle="none", yscrollcommand=scrollbar.set)
        self.resume_listbox.pack(fill="both", expand=True)
        scrollbar.config(command=self.resume_listbox.yview)

        # Remove selected button
        tk.Button(right_in, text="✖  Remove Selected",
                  command=self._remove_selected_resume,
                  bg="#F0F4F8", fg="#EA4335", font=("Helvetica", 9),
                  relief="flat", cursor="hand2").pack(pady=(0, 8))

    def _build_match_button(self):
        f = tk.Frame(self, bg="#F0F4F8")
        f.pack(pady=6)
        self.match_btn = tk.Button(f, text="  🔍  Calculate Match  ",
                                   command=self._run_match_thread,
                                   bg="#34A853", fg="white",
                                   font=("Helvetica", 13, "bold"),
                                   relief="flat", cursor="hand2",
                                   padx=20, pady=10)
        self.match_btn.pack()

    def _build_results_panel(self):
        outer = tk.Frame(self, bg="#CCCCCC")
        outer.pack(fill="both", padx=14, pady=(0, 14))
        self.results_frame = tk.Frame(outer, bg="white")
        self.results_frame.pack(fill="both", expand=True, padx=1, pady=1)

        tk.Label(self.results_frame, text="📊  Results",
                 font=("Helvetica", 12, "bold"), bg="white",
                 fg="#1A73E8", anchor="w", pady=8).pack(fill="x", padx=10)
        ttk.Separator(self.results_frame).pack(fill="x", padx=10)

        # Treeview for ranked results table
        tree_frame = tk.Frame(self.results_frame, bg="white")
        tree_frame.pack(fill="both", expand=True, padx=10, pady=8)

        cols = ("rank", "filename", "overall", "keyword", "tfidf", "semantic", "matched", "missing")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=6)

        headers = {
            "rank":     ("# ", 40),
            "filename": ("Resume File",   200),
            "overall":  ("Overall %",     90),
            "keyword":  ("Keyword %",     90),
            "tfidf":    ("TF-IDF %",      90),
            "semantic": ("Semantic %",    90),
            "matched":  ("Matched KW",    70),
            "missing":  ("Missing KW",    70),
        }
        for col, (label, width) in headers.items():
            self.tree.heading(col, text=label)
            self.tree.column(col,  width=width, anchor="center")
        self.tree.column("filename", anchor="w")

        # Colour tags
        self.tree.tag_configure("high",   background="#E8F5E9")   # green tint  ≥70%
        self.tree.tag_configure("medium", background="#FFF8E1")   # yellow tint 40-69%
        self.tree.tag_configure("low",    background="#FFEBEE")   # red tint    <40%

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        # Keyword detail panel (shown when a row is selected)
        self.kw_detail_var = tk.StringVar(value="Select a row to see matched / missing keywords.")
        tk.Label(self.results_frame, textvariable=self.kw_detail_var,
                 font=("Helvetica", 9), bg="white", fg="#555555",
                 anchor="w", wraplength=1100, justify="left",
                 pady=4).pack(fill="x", padx=12, pady=(0, 8))

        self.tree.bind("<<TreeviewSelect>>", self._on_row_select)

    # ══════════════════════════════════════════════════════════
    #  JD panel helpers
    # ══════════════════════════════════════════════════════════

    def _jd_focus_in(self, _e):
        if self.jd_input.get("1.0", "end-1c") == "Paste job description here...":
            self.jd_input.delete("1.0", tk.END)
            self.jd_input.config(fg="#333333")

    def _jd_focus_out(self, _e):
        if not self.jd_input.get("1.0", "end-1c").strip():
            self.jd_input.insert("1.0", "Paste job description here...")
            self.jd_input.config(fg="#AAAAAA")

    def _browse_jd(self):
        path = filedialog.askopenfilename(
            title="Select Job Description File",
            filetypes=[("Supported files", "*.pdf *.docx *.txt"),
                       ("PDF", "*.pdf"), ("Word", "*.docx"), ("Text", "*.txt")])
        if not path:
            return
        self.jd_filename.set(os.path.basename(path))
        self.jd_meta.set("⏳  Extracting JD text...")
        self._set_status("⏳  Uploading job description...", "#F4A900")
        threading.Thread(target=self._do_upload_jd, args=(path,), daemon=True).start()

    def _do_upload_jd(self, file_path: str):
        try:
            filename = os.path.basename(file_path)
            mime = ("application/pdf" if filename.endswith(".pdf") else
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    if filename.endswith(".docx") else "text/plain")
            with open(file_path, "rb") as f:
                resp = requests.post(f"{BACKEND_URL}/upload-jd",
                                     files={"file": (filename, f, mime)})
            if resp.status_code == 200:
                data           = resp.json()
                self.jd_text   = data.get("extracted_text", "")
                word_count     = data.get("word_count", "—")
                size_kb        = data.get("size_kb",    "—")
                # Show in text area
                self.after(0, self._set_jd_textarea, self.jd_text)
                self.after(0, lambda: self.jd_meta.set(
                    f"📄 {size_kb} KB   |   📝 {word_count} words"))
                self._set_status(f"✅  JD uploaded: {filename}", "#34A853")
            else:
                err = resp.json().get("error", "Unknown error")
                self.after(0, lambda: self.jd_meta.set(""))
                self._set_status(f"❌  JD upload failed: {err}", "#EA4335")
        except Exception as e:
            self._set_status(f"❌  Error: {e}", "#EA4335")

    def _set_jd_textarea(self, text: str):
        self.jd_input.config(fg="#333333")
        self.jd_input.delete("1.0", tk.END)
        self.jd_input.insert("1.0", text)

    # ══════════════════════════════════════════════════════════
    #  Resume list helpers
    # ══════════════════════════════════════════════════════════

    def _browse_resumes(self):
        paths = filedialog.askopenfilenames(
            title="Select Resume Files (can select multiple)",
            filetypes=[("Supported files", "*.pdf *.docx *.txt"),
                       ("PDF", "*.pdf"), ("Word", "*.docx"), ("Text", "*.txt")])
        if not paths:
            return
        new_paths = [p for p in paths
                     if p not in [r["path"] for r in self.resume_list]]
        if not new_paths:
            messagebox.showinfo("No new files", "All selected files are already in the list.")
            return
        self._set_status(f"⏳  Uploading {len(new_paths)} resume(s)...", "#F4A900")
        threading.Thread(target=self._do_upload_resumes,
                         args=(new_paths,), daemon=True).start()

    def _do_upload_resumes(self, paths: list):
        for file_path in paths:
            try:
                filename = os.path.basename(file_path)
                mime = ("application/pdf" if filename.endswith(".pdf") else
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        if filename.endswith(".docx") else "text/plain")
                with open(file_path, "rb") as f:
                    resp = requests.post(f"{BACKEND_URL}/upload-resume",
                                         files={"file": (filename, f, mime)})
                if resp.status_code == 200:
                    data = resp.json()
                    entry = {
                        "filename": filename,
                        "text":     data.get("extracted_text", ""),
                        "path":     file_path,
                        "size_kb":  data.get("size_kb", "—"),
                        "words":    data.get("word_count", "—"),
                    }
                    self.resume_list.append(entry)
                    self.after(0, self._refresh_resume_listbox)
                    self._set_status(f"✅  Added: {filename}", "#34A853")
                else:
                    err = resp.json().get("error", "Unknown")
                    self._set_status(f"❌  Failed: {filename} — {err}", "#EA4335")
            except Exception as e:
                self._set_status(f"❌  Error uploading {os.path.basename(file_path)}: {e}", "#EA4335")

    def _refresh_resume_listbox(self):
        self.resume_listbox.delete(0, tk.END)
        for i, r in enumerate(self.resume_list):
            self.resume_listbox.insert(
                tk.END,
                f"  {i+1}.  {r['filename']}   ({r['size_kb']} KB | {r['words']} words)"
            )
        self.resume_count_var.set(f"{len(self.resume_list)} resume(s) loaded")

    def _remove_selected_resume(self):
        sel = self.resume_listbox.curselection()
        if not sel:
            messagebox.showinfo("Nothing selected", "Click a resume in the list first.")
            return
        idx = sel[0]
        del self.resume_list[idx]
        self._refresh_resume_listbox()

    def _clear_resumes(self):
        self.resume_list.clear()
        self._refresh_resume_listbox()
        for row in self.tree.get_children():
            self.tree.delete(row)
        self.kw_detail_var.set("Select a row to see matched / missing keywords.")

    # ══════════════════════════════════════════════════════════
    #  Match
    # ══════════════════════════════════════════════════════════

    def _run_match_thread(self):
        # Resolve JD text — prefer uploaded file, fall back to textarea
        jd = self.jd_text.strip()
        if not jd:
            typed = self.jd_input.get("1.0", "end-1c").strip()
            if typed and typed != "Paste job description here...":
                jd = typed

        if not jd:
            messagebox.showwarning("Missing Input", "Please upload or paste a job description.")
            return
        if not self.resume_list:
            messagebox.showwarning("Missing Input", "Please add at least one resume.")
            return

        self.match_btn.config(state="disabled", text="  ⏳  Analysing...  ")
        self._set_status(f"⏳  Matching {len(self.resume_list)} resume(s)...", "#F4A900")
        threading.Thread(target=self._do_match, args=(jd,), daemon=True).start()

    def _do_match(self, jd_text: str):
        try:
            payload = {
                "jd_text": jd_text,
                "resumes": [{"filename": r["filename"], "text": r["text"]}
                            for r in self.resume_list],
            }
            resp = requests.post(f"{BACKEND_URL}/match-multiple", json=payload, timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                self.after(0, self._show_results, data["results"])
                self._set_status(
                    f"✅  Match complete! {data['total']} resume(s) ranked.", "#34A853")
            else:
                err = resp.json().get("error", "Unknown error")
                self._set_status(f"❌  Match failed: {err}", "#EA4335")
        except Exception as e:
            self._set_status(f"❌  Error: {e}", "#EA4335")
        finally:
            self.after(0, lambda: self.match_btn.config(
                state="normal", text="  🔍  Calculate Match  "))

    # ══════════════════════════════════════════════════════════
    #  Results table
    # ══════════════════════════════════════════════════════════

    def _show_results(self, results: list):
        # Clear old rows
        for row in self.tree.get_children():
            self.tree.delete(row)

        for i, r in enumerate(results):
            score = r.get("overall_score", 0)
            tag   = "high" if score >= 70 else "medium" if score >= 40 else "low"
            self.tree.insert("", tk.END, iid=str(i), values=(
                i + 1,
                r.get("filename", "—"),
                f"{score:.1f}%",
                f"{r.get('keyword_score', 0):.1f}%",
                f"{r.get('tfidf_score',   0):.1f}%",
                f"{r.get('semantic_score',0):.1f}%",
                len(r.get("matched_keywords", [])),
                len(r.get("missing_keywords", [])),
            ), tags=(tag,))

        # Store results for detail panel
        self._results_data = results

        if results:
            self.tree.selection_set("0")
            self._on_row_select(None)

    def _on_row_select(self, _event):
        sel = self.tree.selection()
        if not sel or not hasattr(self, "_results_data"):
            return
        idx = int(sel[0])
        r   = self._results_data[idx]
        matched = ", ".join(r.get("matched_keywords", [])) or "None"
        missing = ", ".join(r.get("missing_keywords", [])) or "None"
        self.kw_detail_var.set(
            f"✅ Matched:  {matched}\n❌ Missing:  {missing}"
        )

    # ══════════════════════════════════════════════════════════
    #  Backend health
    # ══════════════════════════════════════════════════════════

    def _check_backend_health(self):
        self._set_status("⏳  Connecting to backend...", "#F4A900")
        threading.Thread(target=self._do_health_check, daemon=True).start()

    def _do_health_check(self):
        try:
            r = requests.get(f"{BACKEND_URL}/health", timeout=3)
            if r.status_code == 200:
                self._set_status("✅  Backend connected and ready", "#34A853")
            else:
                self._set_status("⚠️  Backend returned an error", "#F4A900")
        except requests.exceptions.ConnectionError:
            self._set_status("❌  Cannot reach backend — run: python app.py in /backend", "#EA4335")

    def _set_status(self, message: str, color: str = "#333333"):
        self.after(0, lambda: self.status_var.set(message))
        self.after(0, lambda: self.status_label.config(fg=color))


if __name__ == "__main__":
    app = ResumeMatcher()
    app.mainloop()

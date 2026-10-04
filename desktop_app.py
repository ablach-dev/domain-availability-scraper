"""
DomainPulse - Professional Native Desktop Application.
High-speed domain availability scraper with authoritative Registry WHOIS & RDAP verification.
"""

import os
import sys
import time
import queue
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List, Dict, Any, Optional

import customtkinter as ctk

from scraper.whois_checker import (
    check_domain_registry,
    check_domain_hybrid,
    get_tld_from_domain,
)
from scraper.generator import (
    generate_letter_domains,
    generate_keyword_domains,
    generate_brandable_domains,
    parse_custom_domains,
    NICHE_PACKS,
)
from scraper.tlds import TLD_PRESETS, get_registrar_links


# Configure CustomTkinter Appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class DomainPulseApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Domain Availability Scraper")
        self.geometry("1150x760")
        self.minsize(980, 620)

        # Application State
        self.is_scanning = False
        self.stop_requested = False
        self.scan_queue = queue.Queue()
        self.results_list: List[Dict[str, Any]] = []
        self.available_domains: List[str] = []

        # TLD Checkbox variables
        self.tld_vars = {}
        self.common_tlds = [".com", ".io", ".ai", ".co", ".net", ".org", ".app", ".dev", ".xyz"]

        # Build UI
        self._setup_styles()
        self._build_layout()
        self._init_context_menu()

        # Start queue polling timer
        self.after(50, self._process_scan_queue)

    def _setup_styles(self):
        """Configure ttk styles for a clean dark table without ai-slop styling."""
        style = ttk.Style(self)
        style.theme_use("clam")

        # Treeview styling
        style.configure(
            "Custom.Treeview",
            background="#18181b",
            foreground="#e4e4e7",
            fieldbackground="#18181b",
            rowheight=28,
            borderwidth=0,
            font=("Segoe UI", 9)
        )
        style.configure(
            "Custom.Treeview.Heading",
            background="#27272a",
            foreground="#f4f4f5",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
            padding=(6, 6)
        )
        style.map(
            "Custom.Treeview",
            background=[("selected", "#2563eb")],
            foreground=[("selected", "#ffffff")]
        )
        style.map(
            "Custom.Treeview.Heading",
            background=[("active", "#3f3f46")]
        )

    def _build_layout(self):
        """Build main two-panel layout: sidebar on left, data grid on right."""
        self.grid_columnconfigure(0, weight=0, minsize=370)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # -------------------------------------------------------------
        # LEFT PANEL: Controls & Generator Sidebar
        # -------------------------------------------------------------
        self.sidebar = ctk.CTkScrollableFrame(self, width=360, corner_radius=0, fg_color="#18181b")
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.sidebar.grid_columnconfigure(0, weight=1)

        # App Header
        title_lbl = ctk.CTkLabel(
            self.sidebar,
            text="DomainPulse",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#ffffff"
        )
        title_lbl.grid(row=0, column=0, sticky="w", padx=16, pady=(16, 2))

        subtitle_lbl = ctk.CTkLabel(
            self.sidebar,
            text="Authoritative Registry & WHOIS Scraper",
            font=ctk.CTkFont(size=11),
            text_color="#a1a1aa"
        )
        subtitle_lbl.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 16))

        # Generator Mode Tabs (Segmented Button)
        mode_lbl = ctk.CTkLabel(self.sidebar, text="SEARCH MODE", font=ctk.CTkFont(size=10, weight="bold"), text_color="#71717a")
        mode_lbl.grid(row=2, column=0, sticky="w", padx=16, pady=(8, 4))

        self.mode_selector = ctk.CTkSegmentedButton(
            self.sidebar,
            values=["Batch List", "Letter Length", "Keyword", "Brandables"],
            command=self._on_mode_change,
            dynamic_resizing=False,
            height=32
        )
        self.mode_selector.set("Batch List")
        self.mode_selector.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 12))

        # Mode Dynamic Container
        self.mode_frame = ctk.CTkFrame(self.sidebar, fg_color="#27272a", corner_radius=8)
        self.mode_frame.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 14))
        self.mode_frame.grid_columnconfigure(0, weight=1)

        self._build_batch_mode_widgets()
        self._build_letter_mode_widgets()
        self._build_keyword_mode_widgets()
        self._build_brandables_mode_widgets()

        # Show initial mode widgets
        self._show_mode_widgets("Batch List")

        # -------------------------------------------------------------
        # TLD Selection Section
        # -------------------------------------------------------------
        tld_header = ctk.CTkLabel(self.sidebar, text="TLD EXTENSIONS", font=ctk.CTkFont(size=10, weight="bold"), text_color="#71717a")
        tld_header.grid(row=5, column=0, sticky="w", padx=16, pady=(6, 4))

        # TLD Presets Row
        preset_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        preset_frame.grid(row=6, column=0, sticky="ew", padx=16, pady=(0, 6))

        presets = [("Popular", "popular"), ("Tech", "tech"), ("Startup", "startup"), ("All", "all")]
        for i, (name, key) in enumerate(presets):
            btn = ctk.CTkButton(
                preset_frame,
                text=name,
                width=65,
                height=24,
                font=ctk.CTkFont(size=10),
                fg_color="#3f3f46",
                hover_color="#52525b",
                command=lambda k=key: self._apply_tld_preset(k)
            )
            btn.pack(side="left", padx=(0, 4))

        # Checkbox Grid for TLDs
        tld_grid = ctk.CTkFrame(self.sidebar, fg_color="#27272a", corner_radius=8)
        tld_grid.grid(row=7, column=0, sticky="ew", padx=16, pady=(0, 8))
        for col in range(3):
            tld_grid.grid_columnconfigure(col, weight=1)

        default_active = {".com", ".io", ".ai"}
        for idx, tld in enumerate(self.common_tlds):
            var = ctk.BooleanVar(value=(tld in default_active))
            self.tld_vars[tld] = var
            cb = ctk.CTkCheckBox(
                tld_grid,
                text=tld,
                variable=var,
                font=ctk.CTkFont(family="Consolas", size=11),
                checkbox_width=18,
                checkbox_height=18,
                border_width=2
            )
            r = idx // 3
            c = idx % 3
            cb.grid(row=r, column=c, sticky="w", padx=10, pady=6)

        # Custom TLD entry
        custom_tld_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        custom_tld_frame.grid(row=8, column=0, sticky="ew", padx=16, pady=(0, 14))
        custom_tld_frame.grid_columnconfigure(0, weight=1)

        self.custom_tld_entry = ctk.CTkEntry(
            custom_tld_frame,
            placeholder_text="Add custom TLDs (e.g. .store, .club)",
            height=28,
            font=ctk.CTkFont(size=11)
        )
        self.custom_tld_entry.grid(row=0, column=0, sticky="ew")

        # -------------------------------------------------------------
        # Engine Settings Section
        # -------------------------------------------------------------
        engine_lbl = ctk.CTkLabel(self.sidebar, text="VERIFICATION ENGINE", font=ctk.CTkFont(size=10, weight="bold"), text_color="#71717a")
        engine_lbl.grid(row=9, column=0, sticky="w", padx=16, pady=(6, 4))

        engine_frame = ctk.CTkFrame(self.sidebar, fg_color="#27272a", corner_radius=8)
        engine_frame.grid(row=10, column=0, sticky="ew", padx=16, pady=(0, 16))
        engine_frame.grid_columnconfigure(0, weight=1)

        # Mode Selection: Hybrid vs Strict
        self.engine_mode_var = ctk.StringVar(value="Hybrid (Fast DNS + Registry WHOIS)")
        mode_menu = ctk.CTkOptionMenu(
            engine_frame,
            values=[
                "Hybrid (Fast DNS + Registry WHOIS)",
                "Strict Registry WHOIS (All Domains)"
            ],
            variable=self.engine_mode_var,
            font=ctk.CTkFont(size=11),
            height=28
        )
        mode_menu.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 8))

        # Concurrency & Delay Row
        threads_lbl = ctk.CTkLabel(engine_frame, text="Concurrent Workers:", font=ctk.CTkFont(size=11), text_color="#a1a1aa")
        threads_lbl.grid(row=1, column=0, sticky="w", padx=10, pady=(2, 0))

        self.threads_slider = ctk.CTkSlider(engine_frame, from_=3, to=25, number_of_steps=22)
        self.threads_slider.set(12)
        self.threads_slider.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 6))

        delay_lbl = ctk.CTkLabel(engine_frame, text="Request Delay (ms - avoids WHOIS rate-limits):", font=ctk.CTkFont(size=11), text_color="#a1a1aa")
        delay_lbl.grid(row=3, column=0, sticky="w", padx=10, pady=(2, 0))

        self.delay_slider = ctk.CTkSlider(engine_frame, from_=0, to=500, number_of_steps=50)
        self.delay_slider.set(50)
        self.delay_slider.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))

        # -------------------------------------------------------------
        # Action Buttons
        # -------------------------------------------------------------
        btn_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        btn_frame.grid(row=11, column=0, sticky="ew", padx=16, pady=(0, 20))
        btn_frame.grid_columnconfigure(0, weight=3)
        btn_frame.grid_columnconfigure(1, weight=1)

        self.btn_start = ctk.CTkButton(
            btn_frame,
            text="Start Search",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=36,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self.start_scan
        )
        self.btn_start.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.btn_stop = ctk.CTkButton(
            btn_frame,
            text="Stop",
            font=ctk.CTkFont(size=13),
            height=36,
            fg_color="#dc2626",
            hover_color="#b91c1c",
            state="disabled",
            command=self.stop_scan
        )
        self.btn_stop.grid(row=0, column=1, sticky="ew")

        # -------------------------------------------------------------
        # RIGHT PANEL: Data Table & Results View
        # -------------------------------------------------------------
        self.main_panel = ctk.CTkFrame(self, corner_radius=0, fg_color="#09090b")
        self.main_panel.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.main_panel.grid_columnconfigure(0, weight=1)
        self.main_panel.grid_rowconfigure(2, weight=1)

        # 1. Top Metrics Bar
        self.metrics_frame = ctk.CTkFrame(self.main_panel, fg_color="#18181b", corner_radius=0, height=54)
        self.metrics_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        self.metrics_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        self.lbl_checked = ctk.CTkLabel(self.metrics_frame, text="Checked: 0 / 0", font=ctk.CTkFont(family="Segoe UI", size=12))
        self.lbl_checked.grid(row=0, column=0, pady=12)

        self.lbl_available = ctk.CTkLabel(self.metrics_frame, text="Available: 0", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color="#22c55e")
        self.lbl_available.grid(row=0, column=1, pady=12)

        self.lbl_taken = ctk.CTkLabel(self.metrics_frame, text="Taken: 0", font=ctk.CTkFont(family="Segoe UI", size=12), text_color="#a1a1aa")
        self.lbl_taken.grid(row=0, column=2, pady=12)

        self.lbl_speed = ctk.CTkLabel(self.metrics_frame, text="Speed: 0.0/s", font=ctk.CTkFont(family="Segoe UI", size=12), text_color="#38bdf8")
        self.lbl_speed.grid(row=0, column=3, pady=12)

        self.lbl_eta = ctk.CTkLabel(self.metrics_frame, text="ETA: --", font=ctk.CTkFont(family="Segoe UI", size=12), text_color="#a1a1aa")
        self.lbl_eta.grid(row=0, column=4, pady=12)

        # Progress Bar
        self.progress_bar = ctk.CTkProgressBar(self.main_panel, height=4, corner_radius=0)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=1, column=0, sticky="ew")

        # 2. Filter & Search Controls Bar
        filter_bar = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        filter_bar.grid(row=2, column=0, sticky="ew", padx=16, pady=(12, 6))
        filter_bar.grid_columnconfigure(3, weight=1)

        self.filter_var = ctk.StringVar(value="all")
        for val, label in [("all", "All"), ("available", "Available Only"), ("taken", "Taken Only")]:
            rb = ctk.CTkRadioButton(
                filter_bar,
                text=label,
                value=val,
                variable=self.filter_var,
                command=self._apply_filters,
                font=ctk.CTkFont(size=11),
                radiobutton_width=16,
                radiobutton_height=16
            )
            rb.pack(side="left", padx=(0, 14))

        # Search Entry
        self.search_entry = ctk.CTkEntry(
            filter_bar,
            placeholder_text="Filter domain list in real-time...",
            width=240,
            height=28,
            font=ctk.CTkFont(size=11)
        )
        self.search_entry.pack(side="right")
        self.search_entry.bind("<KeyRelease>", lambda e: self._apply_filters())

        # 3. Main Results Data Table (Treeview)
        table_container = ctk.CTkFrame(self.main_panel, fg_color="#18181b", corner_radius=6)
        table_container.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 10))
        table_container.grid_columnconfigure(0, weight=1)
        table_container.grid_rowconfigure(0, weight=1)
        self.main_panel.grid_rowconfigure(3, weight=1)

        columns = ("domain", "status", "length", "server", "reason", "latency")
        self.tree = ttk.Treeview(
            table_container,
            columns=columns,
            show="headings",
            style="Custom.Treeview",
            selectmode="browse"
        )

        self.tree.heading("domain", text="Domain", command=lambda: self._sort_column("domain", False))
        self.tree.heading("status", text="Status", command=lambda: self._sort_column("status", False))
        self.tree.heading("length", text="Length", command=lambda: self._sort_column("length", False))
        self.tree.heading("server", text="Registry Server")
        self.tree.heading("reason", text="WHOIS Response / Signature")
        self.tree.heading("latency", text="Latency", command=lambda: self._sort_column("latency", False))

        self.tree.column("domain", width=220, anchor="w")
        self.tree.column("status", width=110, anchor="center")
        self.tree.column("length", width=65, anchor="center")
        self.tree.column("server", width=180, anchor="w")
        self.tree.column("reason", width=260, anchor="w")
        self.tree.column("latency", width=90, anchor="center")

        # Scrollbars
        v_scroll = ttk.Scrollbar(table_container, orient="vertical", command=self.tree.yview)
        h_scroll = ttk.Scrollbar(table_container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")

        # Tags for coloring rows cleanly
        self.tree.tag_configure("available", foreground="#22c55e")
        self.tree.tag_configure("taken", foreground="#71717a")
        self.tree.tag_configure("error", foreground="#eab308")

        self.tree.bind("<Double-1>", self._on_row_double_click)
        self.tree.bind("<Button-3>", self._on_row_right_click)

        # 4. Bottom Action Bar
        bottom_bar = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        bottom_bar.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 14))

        self.btn_copy_avail = ctk.CTkButton(
            bottom_bar,
            text="Copy Available",
            width=120,
            height=30,
            font=ctk.CTkFont(size=11),
            fg_color="#15803d",
            hover_color="#166534",
            command=self.copy_available_domains
        )
        self.btn_copy_avail.pack(side="left", padx=(0, 8))

        self.btn_export_csv = ctk.CTkButton(
            bottom_bar,
            text="Export CSV",
            width=100,
            height=30,
            font=ctk.CTkFont(size=11),
            fg_color="#3f3f46",
            hover_color="#52525b",
            command=self.export_csv
        )
        self.btn_export_csv.pack(side="left", padx=(0, 8))

        self.btn_export_txt = ctk.CTkButton(
            bottom_bar,
            text="Export TXT",
            width=100,
            height=30,
            font=ctk.CTkFont(size=11),
            fg_color="#3f3f46",
            hover_color="#52525b",
            command=self.export_txt
        )
        self.btn_export_txt.pack(side="left", padx=(0, 8))

        self.btn_clear = ctk.CTkButton(
            bottom_bar,
            text="Clear",
            width=80,
            height=30,
            font=ctk.CTkFont(size=11),
            fg_color="#27272a",
            hover_color="#3f3f46",
            command=self.clear_results
        )
        self.btn_clear.pack(side="left")

        self.lbl_status_msg = ctk.CTkLabel(
            bottom_bar,
            text="Ready. Select search mode and press Start Search.",
            font=ctk.CTkFont(size=11),
            text_color="#71717a"
        )
        self.lbl_status_msg.pack(side="right")

    # -------------------------------------------------------------
    # Sub-Widgets for Each Mode
    # -------------------------------------------------------------
    def _build_batch_mode_widgets(self):
        self.w_batch = ctk.CTkFrame(self.mode_frame, fg_color="transparent")
        lbl = ctk.CTkLabel(self.w_batch, text="Enter domains or names (one per line):", font=ctk.CTkFont(size=11), text_color="#a1a1aa")
        lbl.pack(anchor="w", padx=10, pady=(8, 4))

        self.txt_batch = ctk.CTkTextbox(self.w_batch, height=120, font=ctk.CTkFont(family="Consolas", size=11))
        self.txt_batch.pack(fill="x", padx=10, pady=(0, 10))
        self.txt_batch.insert("1.0", "google.com\napple.com\nmybrandapp\nflowhub\nnexustech")

    def _build_letter_mode_widgets(self):
        self.w_letter = ctk.CTkFrame(self.mode_frame, fg_color="transparent")

        # Length row
        r1 = ctk.CTkFrame(self.w_letter, fg_color="transparent")
        r1.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(r1, text="Number of Letters:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.spin_length = ctk.CTkComboBox(r1, values=["2", "3", "4", "5", "6", "7", "8"], width=70, height=26)
        self.spin_length.set("4")
        self.spin_length.pack(side="right")

        # Pattern Style
        r2 = ctk.CTkFrame(self.w_letter, fg_color="transparent")
        r2.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(r2, text="Pattern Style:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.combo_letter_style = ctk.CTkComboBox(
            r2,
            values=["Pronounceable (CVCV)", "Letters (a-z)", "Alphanumeric", "Digits Only", "Custom Pattern"],
            width=180,
            height=26,
            command=self._on_letter_style_change
        )
        self.combo_letter_style.set("Pronounceable (CVCV)")
        self.combo_letter_style.pack(side="right")

        # Wildcard pattern input
        self.w_pattern_row = ctk.CTkFrame(self.w_letter, fg_color="transparent")
        ctk.CTkLabel(self.w_pattern_row, text="Pattern (?=letter, #=digit):", font=ctk.CTkFont(size=11)).pack(side="left")
        self.entry_pattern = ctk.CTkEntry(self.w_pattern_row, width=110, height=26, placeholder_text="e.g. ?ai")
        self.entry_pattern.pack(side="right")

        # Limit
        r3 = ctk.CTkFrame(self.w_letter, fg_color="transparent")
        r3.pack(fill="x", padx=10, pady=(4, 10))
        ctk.CTkLabel(r3, text="Generation Limit:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.spin_letter_limit = ctk.CTkComboBox(r3, values=["25", "50", "100", "200", "500"], width=80, height=26)
        self.spin_letter_limit.set("50")
        self.spin_letter_limit.pack(side="right")

    def _build_keyword_mode_widgets(self):
        self.w_keyword = ctk.CTkFrame(self.mode_frame, fg_color="transparent")

        # Keyword entry
        r1 = ctk.CTkFrame(self.w_keyword, fg_color="transparent")
        r1.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(r1, text="Base Keyword:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.entry_keyword = ctk.CTkEntry(r1, width=180, height=26, placeholder_text="e.g. cloud, pay, flow")
        self.entry_keyword.insert(0, "cloud")
        self.entry_keyword.pack(side="right")

        # Affix Mode
        r2 = ctk.CTkFrame(self.w_keyword, fg_color="transparent")
        r2.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(r2, text="Combination Mode:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.combo_kw_mode = ctk.CTkComboBox(
            r2,
            values=["Prefix & Suffix", "Prefixes Only", "Suffixes Only", "Niche Pack", "Custom Affixes"],
            width=180,
            height=26,
            command=self._on_kw_mode_change
        )
        self.combo_kw_mode.set("Prefix & Suffix")
        self.combo_kw_mode.pack(side="right")

        # Niche pack row
        self.w_niche_row = ctk.CTkFrame(self.w_keyword, fg_color="transparent")
        ctk.CTkLabel(self.w_niche_row, text="Niche Pack:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.combo_niche = ctk.CTkComboBox(
            self.w_niche_row,
            values=["tech_saas", "ai_ml", "crypto_web3", "creative_studio", "finance_fintech"],
            width=180,
            height=26
        )
        self.combo_niche.set("tech_saas")
        self.combo_niche.pack(side="right")

        # Custom Affixes row
        self.w_custom_affix_row = ctk.CTkFrame(self.w_keyword, fg_color="transparent")
        ctk.CTkLabel(self.w_custom_affix_row, text="Custom Words:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.entry_custom_affix = ctk.CTkEntry(self.w_custom_affix_row, width=180, height=26, placeholder_text="fast, smart, zone")
        self.entry_custom_affix.pack(side="right")

        # Limit
        r3 = ctk.CTkFrame(self.w_keyword, fg_color="transparent")
        r3.pack(fill="x", padx=10, pady=(4, 10))
        ctk.CTkLabel(r3, text="Max Combinations:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.spin_kw_limit = ctk.CTkComboBox(r3, values=["25", "50", "100", "200"], width=80, height=26)
        self.spin_kw_limit.set("50")
        self.spin_kw_limit.pack(side="right")

    def _build_brandables_mode_widgets(self):
        self.w_brandables = ctk.CTkFrame(self.mode_frame, fg_color="transparent")
        lbl = ctk.CTkLabel(
            self.w_brandables,
            text="Checks curated short startup roots\n(e.g. velo, koba, zira, lux, nova, apex)",
            font=ctk.CTkFont(size=11),
            text_color="#a1a1aa",
            justify="left"
        )
        lbl.pack(anchor="w", padx=10, pady=(8, 6))

        r = ctk.CTkFrame(self.w_brandables, fg_color="transparent")
        r.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(r, text="Number of Roots:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.spin_brand_limit = ctk.CTkComboBox(r, values=["20", "40", "60", "100"], width=80, height=26)
        self.spin_brand_limit.set("40")
        self.spin_brand_limit.pack(side="right")

    def _on_mode_change(self, mode_name: str):
        self._show_mode_widgets(mode_name)

    def _show_mode_widgets(self, mode_name: str):
        self.w_batch.pack_forget()
        self.w_letter.pack_forget()
        self.w_keyword.pack_forget()
        self.w_brandables.pack_forget()

        if mode_name == "Batch List":
            self.w_batch.pack(fill="both", expand=True)
        elif mode_name == "Letter Length":
            self.w_letter.pack(fill="both", expand=True)
        elif mode_name == "Keyword":
            self.w_keyword.pack(fill="both", expand=True)
        elif mode_name == "Brandables":
            self.w_brandables.pack(fill="both", expand=True)

    def _on_letter_style_change(self, choice: str):
        if choice == "Custom Pattern":
            self.w_pattern_row.pack(fill="x", padx=10, pady=4)
        else:
            self.w_pattern_row.pack_forget()

    def _on_kw_mode_change(self, choice: str):
        if choice == "Niche Pack":
            self.w_niche_row.pack(fill="x", padx=10, pady=4)
            self.w_custom_affix_row.pack_forget()
        elif choice == "Custom Affixes":
            self.w_custom_affix_row.pack(fill="x", padx=10, pady=4)
            self.w_niche_row.pack_forget()
        else:
            self.w_niche_row.pack_forget()
            self.w_custom_affix_row.pack_forget()

    def _apply_tld_preset(self, preset_key: str):
        target = TLD_PRESETS.get(preset_key, [".com", ".net", ".org"])
        if preset_key == "all":
            target = self.common_tlds

        for tld, var in self.tld_vars.items():
            var.set(tld in target)

    def _get_selected_tlds(self) -> List[str]:
        selected = [tld for tld, var in self.tld_vars.items() if var.get()]
        custom_raw = self.custom_tld_entry.get().strip()
        if custom_raw:
            for part in custom_raw.replace(",", " ").split():
                clean = part.strip().lower()
                if not clean.startswith("."):
                    clean = "." + clean
                if clean not in selected:
                    selected.append(clean)
        if not selected:
            selected = [".com"]
        return selected

    # -------------------------------------------------------------
    # Domain Gathering
    # -------------------------------------------------------------
    def _generate_candidate_domains(self) -> List[str]:
        mode = self.mode_selector.get()
        tlds = self._get_selected_tlds()

        if mode == "Batch List":
            text = self.txt_batch.get("1.0", "end")
            return parse_custom_domains(text, tlds)

        elif mode == "Letter Length":
            length = int(self.spin_length.get())
            style_map = {
                "Pronounceable (CVCV)": "pronounceable",
                "Letters (a-z)": "letters",
                "Alphanumeric": "alphanumeric",
                "Digits Only": "digits",
                "Custom Pattern": "pattern"
            }
            style = style_map.get(self.combo_letter_style.get(), "pronounceable")
            pattern = self.entry_pattern.get().strip() if style == "pattern" else ""
            limit = int(self.spin_letter_limit.get())
            return generate_letter_domains(
                length=length,
                mode=style,
                pattern=pattern,
                strategy="random",
                max_count=limit,
                tlds=tlds
            )

        elif mode == "Keyword":
            kw = self.entry_keyword.get().strip()
            kw_list = [k.strip() for k in kw.replace(",", " ").split() if k.strip()]
            if not kw_list:
                kw_list = ["cloud"]

            mode_map = {
                "Prefix & Suffix": "both",
                "Prefixes Only": "prefix",
                "Suffixes Only": "suffix",
                "Niche Pack": "niche",
                "Custom Affixes": "custom"
            }
            km = mode_map.get(self.combo_kw_mode.get(), "both")
            niche = self.combo_niche.get() if km == "niche" else ""
            affixes = [a.strip() for a in self.entry_custom_affix.get().replace(",", " ").split() if a.strip()]
            limit = int(self.spin_kw_limit.get())

            return generate_keyword_domains(
                keywords=kw_list,
                mode=km,
                custom_affixes=affixes,
                niche_pack=niche,
                tlds=tlds,
                max_count=limit
            )

        elif mode == "Brandables":
            limit = int(self.spin_brand_limit.get())
            return generate_brandable_domains(tlds=tlds, max_count=limit)

        return []

    # -------------------------------------------------------------
    # Scanning Controller (Background Thread)
    # -------------------------------------------------------------
    def start_scan(self):
        if self.is_scanning:
            return

        domains = self._generate_candidate_domains()
        if not domains:
            messagebox.showwarning("No Domains", "Please enter domain names or choose generation parameters.")
            return

        self.is_scanning = True
        self.stop_requested = False
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.lbl_status_msg.configure(text=f"Scanning {len(domains)} domains via Authoritative WHOIS/Registry...")

        self.clear_results()
        self.progress_bar.set(0)

        # Worker parameters
        max_workers = int(self.threads_slider.get())
        delay_sec = self.delay_slider.get() / 1000.0
        use_hybrid = "Hybrid" in self.engine_mode_var.get()

        threading.Thread(
            target=self._scan_worker_thread,
            args=(domains, max_workers, delay_sec, use_hybrid),
            daemon=True
        ).start()

    def stop_scan(self):
        if not self.is_scanning:
            return
        self.stop_requested = True
        self.lbl_status_msg.configure(text="Stopping scan...")

    def _scan_worker_thread(self, domains: List[str], max_workers: int, delay_sec: float, use_hybrid: bool):
        total = len(domains)
        checked = 0
        available_count = 0
        taken_count = 0
        start_time = time.time()

        from concurrent.futures import ThreadPoolExecutor

        def check_one(domain: str) -> Dict[str, Any]:
            if self.stop_requested:
                return {}
            if delay_sec > 0:
                time.sleep(delay_sec)

            if use_hybrid:
                return check_domain_hybrid(domain)
            else:
                return check_domain_registry(domain)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_domain = {executor.submit(check_one, d): d for d in domains}

            for future in future_to_domain:
                if self.stop_requested:
                    break

                try:
                    res = future.result()
                    if not res:
                        continue

                    checked += 1
                    status = res.get("status", "error")
                    if status == "available":
                        available_count += 1
                    elif status == "taken":
                        taken_count += 1

                    elapsed = max(0.001, time.time() - start_time)
                    speed = checked / elapsed
                    eta = (total - checked) / speed if speed > 0 else 0

                    self.scan_queue.put({
                        "type": "result",
                        "data": res,
                        "checked": checked,
                        "total": total,
                        "available": available_count,
                        "taken": taken_count,
                        "speed": round(speed, 1),
                        "eta": round(eta, 1),
                        "percent": checked / total if total > 0 else 1.0
                    })
                except Exception as e:
                    self.scan_queue.put({"type": "error", "message": str(e)})

        self.scan_queue.put({"type": "finished"})

    def _process_scan_queue(self):
        """Poll scan results from worker thread safely into UI."""
        try:
            while not self.scan_queue.empty():
                msg = self.scan_queue.get_nowait()
                mtype = msg.get("type")

                if mtype == "result":
                    item = msg["data"]
                    self.results_list.append(item)
                    if item.get("status") == "available":
                        self.available_domains.append(item["domain"])

                    # Update metrics
                    self.lbl_checked.configure(text=f"Checked: {msg['checked']} / {msg['total']}")
                    self.lbl_available.configure(text=f"Available: {msg['available']}")
                    self.lbl_taken.configure(text=f"Taken: {msg['taken']}")
                    self.lbl_speed.configure(text=f"Speed: {msg['speed']}/s")
                    self.lbl_eta.configure(text=f"ETA: {int(msg['eta'])}s" if msg['eta'] > 0 else "ETA: --")
                    self.progress_bar.set(msg["percent"])

                    # Insert row if matches current filter
                    if self._matches_filter(item):
                        self._insert_row(item)

                elif mtype == "finished":
                    self.is_scanning = False
                    self.btn_start.configure(state="normal")
                    self.btn_stop.configure(state="disabled")
                    self.lbl_status_msg.configure(
                        text=f"Scan complete. Found {len(self.available_domains)} available domains."
                    )
        except Exception:
            pass

        self.after(50, self._process_scan_queue)

    # -------------------------------------------------------------
    # Table & Filter Logic
    # -------------------------------------------------------------
    def _matches_filter(self, item: Dict[str, Any]) -> bool:
        filter_mode = self.filter_var.get()
        status = item.get("status", "")

        if filter_mode == "available" and status != "available":
            return False
        if filter_mode == "taken" and status != "taken":
            return False

        query = self.search_entry.get().strip().lower()
        if query:
            d = item.get("domain", "").lower()
            if query not in d:
                return False

        return True

    def _insert_row(self, item: Dict[str, Any]):
        domain = item.get("domain", "")
        status = item.get("status", "error").upper()
        server = item.get("server", "")
        reason = item.get("reason", "")
        latency = f"{item.get('elapsed_ms', 0)} ms"
        base_name = domain.split(".")[0]
        length = len(base_name)

        tag = "available" if status == "AVAILABLE" else "taken" if status == "TAKEN" else "error"
        self.tree.insert(
            "",
            "end",
            values=(domain, status, length, server, reason, latency),
            tags=(tag,)
        )

    def _apply_filters(self):
        """Re-render table based on filter radio button and search text."""
        self.tree.delete(*self.tree.get_children())
        for item in self.results_list:
            if self._matches_filter(item):
                self._insert_row(item)

    def _sort_column(self, col: str, reverse: bool):
        """Sort table column by clicking header."""
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]

        # Try numeric sort for length and latency
        try:
            items.sort(key=lambda t: float(t[0].replace(" ms", "")), reverse=reverse)
        except ValueError:
            items.sort(reverse=reverse)

        for index, (val, k) in enumerate(items):
            self.tree.move(k, "", index)

        self.tree.heading(col, command=lambda: self._sort_column(col, not reverse))

    def clear_results(self):
        self.tree.delete(*self.tree.get_children())
        self.results_list.clear()
        self.available_domains.clear()
        self.lbl_checked.configure(text="Checked: 0 / 0")
        self.lbl_available.configure(text="Available: 0")
        self.lbl_taken.configure(text="Taken: 0")
        self.lbl_speed.configure(text="Speed: 0.0/s")
        self.lbl_eta.configure(text="ETA: --")
        self.progress_bar.set(0)

    # -------------------------------------------------------------
    # Context Menu & Actions
    # -------------------------------------------------------------
    def _init_context_menu(self):
        self.menu = tk.Menu(self, tearoff=0, bg="#27272a", fg="#f4f4f5", activebackground="#2563eb", activeforeground="#ffffff", font=("Segoe UI", 9))
        self.menu.add_command(label="Copy Domain", command=self._copy_selected_domain)
        self.menu.add_separator()
        self.menu.add_command(label="Register on GoDaddy (Default)", command=lambda: self._open_registrar("godaddy"))
        self.menu.add_command(label="Register on Cloudflare", command=lambda: self._open_registrar("cloudflare"))
        self.menu.add_command(label="Register on Dynadot", command=lambda: self._open_registrar("dynadot"))
        self.menu.add_command(label="Register on Namecheap", command=lambda: self._open_registrar("namecheap"))
        self.menu.add_command(label="Register on Porkbun", command=lambda: self._open_registrar("porkbun"))
        self.menu.add_separator()
        self.menu.add_command(label="View Full WHOIS Snippet", command=self._show_whois_details)

    def _on_row_right_click(self, event):
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self.tree.selection_set(row_id)
            self.menu.tk_popup(event.x_root, event.y_root)

    def _on_row_double_click(self, event):
        self._open_registrar("godaddy")

    def _get_selected_domain(self) -> Optional[str]:
        selected = self.tree.selection()
        if not selected:
            return None
        values = self.tree.item(selected[0], "values")
        return values[0] if values else None

    def _copy_selected_domain(self):
        domain = self._get_selected_domain()
        if domain:
            self.clipboard_clear()
            self.clipboard_append(domain)
            self.lbl_status_msg.configure(text=f"Copied {domain} to clipboard.")

    def _open_registrar(self, registrar: str = "godaddy"):
        domain = self._get_selected_domain()
        if not domain:
            return
        links = get_registrar_links(domain)
        url = links.get(registrar.lower(), links["godaddy"])
        webbrowser.open(url)
        links = get_registrar_links(domain)
        url = links.get(registrar, links["porkbun"])
        webbrowser.open(url)

    def _show_whois_details(self):
        domain = self._get_selected_domain()
        if not domain:
            return
        match = next((r for r in self.results_list if r["domain"] == domain), None)
        if not match:
            return

        snippet = match.get("raw_snippet", "No raw data available.")
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"WHOIS Details - {domain}")
        dialog.geometry("600x400")

        txt = ctk.CTkTextbox(dialog, font=ctk.CTkFont(family="Consolas", size=11))
        txt.pack(fill="both", expand=True, padx=12, pady=12)
        txt.insert("1.0", snippet)

    def copy_available_domains(self):
        if not self.available_domains:
            messagebox.showinfo("None Available", "No available domains in current search.")
            return
        text = "\n".join(self.available_domains)
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Copied", f"Copied {len(self.available_domains)} available domains to clipboard.")

    def export_csv(self):
        if not self.results_list:
            messagebox.showinfo("Export", "No data to export.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            title="Save Domain Results CSV"
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("Domain,Status,Registry Server,Reason,Latency_ms\n")
                for item in self.results_list:
                    reason = item.get("reason", "").replace('"', '""')
                    f.write(f'"{item["domain"]}","{item["status"]}","{item.get("server","")}","{reason}",{item.get("elapsed_ms", 0)}\n')
            messagebox.showinfo("Saved", f"Exported {len(self.results_list)} records to CSV.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save CSV: {e}")

    def export_txt(self):
        if not self.available_domains:
            messagebox.showinfo("Export", "No available domains to export.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
            title="Save Available Domains List"
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.available_domains) + "\n")
            messagebox.showinfo("Saved", f"Exported {len(self.available_domains)} available domains to TXT.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save TXT: {e}")


def launch_desktop_app():
    """Entry point to start the native desktop GUI."""
    app = DomainPulseApp()
    app.mainloop()


if __name__ == "__main__":
    launch_desktop_app()

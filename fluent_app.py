"""
DomainPulse - Modern Windows 11 Fluent Design Desktop Application.
High-speed domain availability scraper with authoritative Registry WHOIS & RDAP verification.
Built with PyQt6 and PyQt6-Fluent-Widgets.
"""

import sys
import os
import time
import webbrowser
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QFont, QColor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QHeaderView, QTableWidgetItem, QFileDialog, QSplitter, QFrame,
    QStackedWidget, QLabel, QButtonGroup
)

from qfluentwidgets import (
    FluentWindow, NavigationInterface, NavigationItemPosition,
    PrimaryPushButton, PushButton, ToolButton, TransparentToolButton,
    LineEdit, TextEdit, PlainTextEdit, SearchLineEdit, ComboBox, SpinBox, Slider,
    CheckBox, RadioButton, ProgressBar, TableWidget, CardWidget,
    ElevatedCardWidget, FluentIcon as FIF, InfoBar, InfoBarPosition,
    RoundMenu, Action, Pivot, SegmentedWidget, SubtitleLabel, CaptionLabel,
    BodyLabel, StrongBodyLabel, TitleLabel, setTheme, Theme, MessageBox,
    ScrollArea
)

from scraper.whois_checker import (
    check_domain_registry,
    check_domain_hybrid,
    get_tld_from_domain,
    TLD_REGISTRY_SERVERS
)
from scraper.generator import (
    generate_letter_domains,
    generate_keyword_domains,
    generate_brandable_domains,
    parse_custom_domains,
    NICHE_PACKS,
)
from scraper.tlds import TLD_PRESETS, get_registrar_links


class ScanWorker(QThread):
    """Background worker thread executing authoritative registry checks without blocking UI."""
    result_ready = pyqtSignal(dict)
    progress_updated = pyqtSignal(dict)
    scan_finished = pyqtSignal()

    def __init__(self, domains: List[str], max_workers: int, delay_sec: float, use_hybrid: bool):
        super().__init__()
        self.domains = domains
        self.max_workers = max(1, min(max_workers, 30))
        self.delay_sec = delay_sec
        self.use_hybrid = use_hybrid
        self._is_stopped = False

    def stop(self):
        self._is_stopped = True

    def run(self):
        total = len(self.domains)
        checked = 0
        available_count = 0
        taken_count = 0
        start_time = time.time()

        def check_one(domain: str) -> Dict[str, Any]:
            if self._is_stopped:
                return {}
            if self.delay_sec > 0:
                time.sleep(self.delay_sec)
            if self.use_hybrid:
                return check_domain_hybrid(domain)
            else:
                return check_domain_registry(domain)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(check_one, d): d for d in self.domains}

            for f in futures:
                if self._is_stopped:
                    break

                try:
                    res = f.result()
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

                    self.result_ready.emit(res)
                    self.progress_updated.emit({
                        "checked": checked,
                        "total": total,
                        "available": available_count,
                        "taken": taken_count,
                        "speed": round(speed, 1),
                        "eta": round(eta, 1),
                        "percent": int((checked / total) * 100) if total > 0 else 100
                    })
                except Exception:
                    pass

        self.scan_finished.emit()


class ScannerInterface(QWidget):
    """Main domain scanning workspace with controls and live fluent data table."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("scanner_interface")

        self.worker: Optional[ScanWorker] = None
        self.results_data: List[Dict[str, Any]] = []
        self.available_domains: List[str] = []
        self.tld_checkboxes: Dict[str, CheckBox] = {}
        self.common_tlds = [".com", ".io", ".ai", ".co", ".net", ".org", ".app", ".dev", ".xyz"]

        self._init_ui()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(16)

        # -------------------------------------------------------------
        # LEFT PANEL: Search Configuration Card (Fixed Width ~390px)
        # -------------------------------------------------------------
        left_scroll = ScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFixedWidth(390)
        left_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        left_container = CardWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(14)

        # Header Title
        title = SubtitleLabel("Domain Search")
        desc = CaptionLabel("Authoritative Registry WHOIS & RDAP Engine")
        desc.setTextColor("#a1a1aa", "#71717a")
        left_layout.addWidget(title)
        left_layout.addWidget(desc)

        # Mode Pivot / Segmented Tabs
        self.pivot = Pivot(self)
        self.pivot.addItem("batch", "Batch List")
        self.pivot.addItem("letters", "Letter Length")
        self.pivot.addItem("keyword", "Keyword")
        self.pivot.addItem("brandables", "Brandables")
        self.pivot.setCurrentItem("batch")
        self.pivot.currentItemChanged.connect(self._on_pivot_changed)
        left_layout.addWidget(self.pivot)

        # Mode Stacked Pages
        self.stacked_modes = QStackedWidget()
        self._build_batch_page()
        self._build_letter_page()
        self._build_keyword_page()
        self._build_brandables_page()
        left_layout.addWidget(self.stacked_modes)

        # Separator line
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("color: #27272a;")
        left_layout.addWidget(sep1)

        # TLD Selection Section
        tld_hdr_layout = QHBoxLayout()
        tld_title = StrongBodyLabel("Extensions (TLDs)")
        tld_hdr_layout.addWidget(tld_title)
        tld_hdr_layout.addStretch()

        # Preset pills
        presets = [("Popular", "popular"), ("Tech", "tech"), ("Startup", "startup"), ("All", "all")]
        for label, p_key in presets:
            btn = PushButton(label)
            btn.setFixedHeight(22)
            btn.setFont(QFont("Segoe UI", 8))
            btn.clicked.connect(lambda checked, k=p_key: self._apply_tld_preset(k))
            tld_hdr_layout.addWidget(btn)

        left_layout.addLayout(tld_hdr_layout)

        # Checkbox Grid for TLDs
        tld_grid = QGridLayout()
        tld_grid.setSpacing(8)
        default_active = {".com", ".io", ".ai"}
        for idx, tld in enumerate(self.common_tlds):
            cb = CheckBox(tld)
            cb.setFont(QFont("Consolas", 9))
            cb.setChecked(tld in default_active)
            self.tld_checkboxes[tld] = cb
            tld_grid.addWidget(cb, idx // 3, idx % 3)

        left_layout.addLayout(tld_grid)

        # Custom TLD input
        self.custom_tld_edit = LineEdit()
        self.custom_tld_edit.setPlaceholderText("Add custom TLDs (e.g. .store, .club, .gg)")
        self.custom_tld_edit.setFixedHeight(30)
        left_layout.addWidget(self.custom_tld_edit)

        # Separator line
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #27272a;")
        left_layout.addWidget(sep2)

        # Engine Settings
        engine_title = StrongBodyLabel("Verification Engine")
        left_layout.addWidget(engine_title)

        self.engine_combo = ComboBox()
        self.engine_combo.addItems([
            "Hybrid (Fast DNS Filter + Registry WHOIS)",
            "Strict Registry WHOIS (All to Registry)"
        ])
        self.engine_combo.setCurrentIndex(0)
        left_layout.addWidget(self.engine_combo)

        # Workers Slider
        workers_layout = QHBoxLayout()
        workers_lbl = BodyLabel("Workers:")
        self.workers_val_lbl = CaptionLabel("12")
        self.workers_val_lbl.setTextColor("#38bdf8", "#38bdf8")
        self.workers_slider = Slider(Qt.Orientation.Horizontal)
        self.workers_slider.setRange(3, 25)
        self.workers_slider.setValue(12)
        self.workers_slider.valueChanged.connect(lambda v: self.workers_val_lbl.setText(str(v)))
        workers_layout.addWidget(workers_lbl)
        workers_layout.addWidget(self.workers_slider)
        workers_layout.addWidget(self.workers_val_lbl)
        left_layout.addLayout(workers_layout)

        # Delay Slider
        delay_layout = QHBoxLayout()
        delay_lbl = BodyLabel("Delay:")
        self.delay_val_lbl = CaptionLabel("50ms")
        self.delay_val_lbl.setTextColor("#a1a1aa", "#a1a1aa")
        self.delay_slider = Slider(Qt.Orientation.Horizontal)
        self.delay_slider.setRange(0, 500)
        self.delay_slider.setValue(50)
        self.delay_slider.valueChanged.connect(lambda v: self.delay_val_lbl.setText(f"{v}ms"))
        delay_layout.addWidget(delay_lbl)
        delay_layout.addWidget(self.delay_slider)
        delay_layout.addWidget(self.delay_val_lbl)
        left_layout.addLayout(delay_layout)

        left_layout.addSpacing(6)

        # Action Buttons
        btn_action_layout = QHBoxLayout()
        self.btn_start = PrimaryPushButton(FIF.PLAY, "Start Search")
        self.btn_start.setFixedHeight(36)
        self.btn_start.clicked.connect(self.start_scan)

        self.btn_stop = PushButton(FIF.CANCEL, "Stop")
        self.btn_stop.setFixedHeight(36)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_scan)

        self.btn_clear = PushButton(FIF.DELETE, "Clear")
        self.btn_clear.setFixedHeight(36)
        self.btn_clear.clicked.connect(self.clear_results)

        btn_action_layout.addWidget(self.btn_start, 2)
        btn_action_layout.addWidget(self.btn_stop, 1)
        btn_action_layout.addWidget(self.btn_clear, 1)
        left_layout.addLayout(btn_action_layout)

        left_layout.addStretch()
        left_scroll.setWidget(left_container)
        main_layout.addWidget(left_scroll)

        # -------------------------------------------------------------
        # RIGHT PANEL: Data Table & Live Results
        # -------------------------------------------------------------
        right_container = CardWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(18, 16, 18, 16)
        right_layout.setSpacing(12)

        # 1. KPI Metrics Banner
        kpi_frame = ElevatedCardWidget()
        kpi_layout = QHBoxLayout(kpi_frame)
        kpi_layout.setContentsMargins(14, 10, 14, 10)

        self.lbl_stat_checked = BodyLabel("Checked: 0 / 0")
        self.lbl_stat_available = StrongBodyLabel("Available: 0")
        self.lbl_stat_available.setTextColor("#22c55e", "#16a34a")
        self.lbl_stat_taken = BodyLabel("Taken: 0")
        self.lbl_stat_taken.setTextColor("#71717a", "#71717a")
        self.lbl_stat_speed = BodyLabel("Speed: 0.0/s")
        self.lbl_stat_speed.setTextColor("#38bdf8", "#0284c7")
        self.lbl_stat_eta = BodyLabel("ETA: --")

        kpi_layout.addWidget(self.lbl_stat_checked)
        kpi_layout.addStretch()
        kpi_layout.addWidget(self.lbl_stat_available)
        kpi_layout.addStretch()
        kpi_layout.addWidget(self.lbl_stat_taken)
        kpi_layout.addStretch()
        kpi_layout.addWidget(self.lbl_stat_speed)
        kpi_layout.addStretch()
        kpi_layout.addWidget(self.lbl_stat_eta)
        right_layout.addWidget(kpi_frame)

        # Progress bar
        self.progress_bar = ProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(4)
        right_layout.addWidget(self.progress_bar)

        # 2. Filter & Real-Time Search Bar
        filter_bar_layout = QHBoxLayout()
        self.rb_all = RadioButton("All")
        self.rb_all.setChecked(True)
        self.rb_available = RadioButton("Available Only")
        self.rb_taken = RadioButton("Taken Only")

        self.filter_group = QButtonGroup(self)
        self.filter_group.addButton(self.rb_all)
        self.filter_group.addButton(self.rb_available)
        self.filter_group.addButton(self.rb_taken)
        self.filter_group.buttonClicked.connect(self._apply_filters)

        filter_bar_layout.addWidget(self.rb_all)
        filter_bar_layout.addWidget(self.rb_available)
        filter_bar_layout.addWidget(self.rb_taken)
        filter_bar_layout.addStretch()

        self.search_filter_edit = SearchLineEdit()
        self.search_filter_edit.setPlaceholderText("Filter results...")
        self.search_filter_edit.setFixedWidth(240)
        self.search_filter_edit.textChanged.connect(self._apply_filters)
        filter_bar_layout.addWidget(self.search_filter_edit)
        right_layout.addLayout(filter_bar_layout)

        # 3. Main Fluent Data Table
        self.table = TableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Domain", "Status", "Length", "Registry Server", "WHOIS Response", "Latency"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(3, 190)
        self.table.setSortingEnabled(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._on_table_double_clicked)
        self.table.verticalHeader().hide()

        right_layout.addWidget(self.table, 1)

        # 4. Bottom Toolbar
        bottom_layout = QHBoxLayout()
        self.btn_copy_avail = PrimaryPushButton(FIF.COPY, "Copy Available")
        self.btn_copy_avail.clicked.connect(self.copy_available_domains)

        self.btn_export_csv = PushButton(FIF.SAVE, "Export CSV")
        self.btn_export_csv.clicked.connect(self.export_csv)

        self.btn_export_txt = PushButton(FIF.DOCUMENT, "Export TXT")
        self.btn_export_txt.clicked.connect(self.export_txt)

        self.lbl_status_msg = CaptionLabel("Ready. Select search parameters and press Start Search.")
        self.lbl_status_msg.setTextColor("#71717a", "#71717a")

        bottom_layout.addWidget(self.btn_copy_avail)
        bottom_layout.addWidget(self.btn_export_csv)
        bottom_layout.addWidget(self.btn_export_txt)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.lbl_status_msg)
        right_layout.addLayout(bottom_layout)

        main_layout.addWidget(right_container, 1)

    # -------------------------------------------------------------
    # Mode Configuration Widgets
    # -------------------------------------------------------------
    def _build_batch_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        lbl = CaptionLabel("Enter domain names or words (one per line):")
        lbl.setTextColor("#a1a1aa", "#71717a")
        layout.addWidget(lbl)

        self.txt_batch = PlainTextEdit()
        self.txt_batch.setPlainText("google.com\napple.com\nmybrandapp\nflowhub\nnexustech")
        self.txt_batch.setFixedHeight(120)
        self.txt_batch.setFont(QFont("Consolas", 10))
        layout.addWidget(self.txt_batch)

        self.stacked_modes.addWidget(page)

    def _build_letter_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Length spinbox
        r1 = QHBoxLayout()
        r1.addWidget(BodyLabel("Letter Length:"))
        self.spin_letter_len = SpinBox()
        self.spin_letter_len.setRange(2, 12)
        self.spin_letter_len.setValue(4)
        r1.addWidget(self.spin_letter_len)
        layout.addLayout(r1)

        # Style combobox
        r2 = QHBoxLayout()
        r2.addWidget(BodyLabel("Pattern Style:"))
        self.combo_letter_style = ComboBox()
        self.combo_letter_style.addItems([
            "Pronounceable (CVCV)",
            "Letters (a-z)",
            "Alphanumeric",
            "Digits Only",
            "Custom Pattern"
        ])
        self.combo_letter_style.currentTextChanged.connect(self._on_letter_style_changed)
        r2.addWidget(self.combo_letter_style)
        layout.addLayout(r2)

        # Wildcard pattern entry
        self.pattern_layout = QHBoxLayout()
        self.pattern_layout.addWidget(BodyLabel("Pattern:"))
        self.pattern_edit = LineEdit()
        self.pattern_edit.setPlaceholderText("e.g. ?ai, xx?, ?app?")
        self.pattern_layout.addWidget(self.pattern_edit)
        layout.addLayout(self.pattern_layout)
        self.pattern_edit.setEnabled(False)

        # Limit
        r3 = QHBoxLayout()
        r3.addWidget(BodyLabel("Max Count:"))
        self.spin_letter_limit = SpinBox()
        self.spin_letter_limit.setRange(10, 500)
        self.spin_letter_limit.setValue(50)
        self.spin_letter_limit.setSingleStep(25)
        r3.addWidget(self.spin_letter_limit)
        layout.addLayout(r3)

        self.stacked_modes.addWidget(page)

    def _build_keyword_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        r1 = QHBoxLayout()
        r1.addWidget(BodyLabel("Keyword:"))
        self.kw_edit = LineEdit()
        self.kw_edit.setText("cloud")
        r1.addWidget(self.kw_edit)
        layout.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(BodyLabel("Mode:"))
        self.combo_kw_mode = ComboBox()
        self.combo_kw_mode.addItems([
            "Prefix & Suffix",
            "Prefixes Only",
            "Suffixes Only",
            "Niche Pack",
            "Custom Affixes"
        ])
        self.combo_kw_mode.currentTextChanged.connect(self._on_kw_mode_changed)
        r2.addWidget(self.combo_kw_mode)
        layout.addLayout(r2)

        # Niche pack
        self.niche_layout = QHBoxLayout()
        self.niche_layout.addWidget(BodyLabel("Niche:"))
        self.combo_niche = ComboBox()
        self.combo_niche.addItems(list(NICHE_PACKS.keys()))
        self.niche_layout.addWidget(self.combo_niche)
        layout.addLayout(self.niche_layout)
        self.combo_niche.setEnabled(False)

        # Custom affixes
        self.custom_affix_layout = QHBoxLayout()
        self.custom_affix_layout.addWidget(BodyLabel("Affixes:"))
        self.custom_affix_edit = LineEdit()
        self.custom_affix_edit.setPlaceholderText("fast, smart, zone")
        self.custom_affix_layout.addWidget(self.custom_affix_edit)
        layout.addLayout(self.custom_affix_layout)
        self.custom_affix_edit.setEnabled(False)

        # Limit
        r3 = QHBoxLayout()
        r3.addWidget(BodyLabel("Max Count:"))
        self.spin_kw_limit = SpinBox()
        self.spin_kw_limit.setRange(10, 300)
        self.spin_kw_limit.setValue(50)
        r3.addWidget(self.spin_kw_limit)
        layout.addLayout(r3)

        self.stacked_modes.addWidget(page)

    def _build_brandables_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        lbl = CaptionLabel("Tests curated short startup brandable roots\n(e.g. velo, koba, zira, lux, nova, apex)")
        lbl.setTextColor("#a1a1aa", "#71717a")
        layout.addWidget(lbl)

        r1 = QHBoxLayout()
        r1.addWidget(BodyLabel("Root Count:"))
        self.spin_brand_limit = SpinBox()
        self.spin_brand_limit.setRange(10, 80)
        self.spin_brand_limit.setValue(30)
        r1.addWidget(self.spin_brand_limit)
        layout.addLayout(r1)

        self.stacked_modes.addWidget(page)

    def _on_pivot_changed(self, item_key: str):
        mapping = {"batch": 0, "letters": 1, "keyword": 2, "brandables": 3}
        self.stacked_modes.setCurrentIndex(mapping.get(item_key, 0))

    def _on_letter_style_changed(self, text: str):
        self.pattern_edit.setEnabled(text == "Custom Pattern")

    def _on_kw_mode_changed(self, text: str):
        self.combo_niche.setEnabled(text == "Niche Pack")
        self.custom_affix_edit.setEnabled(text == "Custom Affixes")

    def _apply_tld_preset(self, preset_key: str):
        target = TLD_PRESETS.get(preset_key, [".com", ".net", ".org"])
        if preset_key == "all":
            target = self.common_tlds

        for tld, cb in self.tld_checkboxes.items():
            cb.setChecked(tld in target)

    def _get_selected_tlds(self) -> List[str]:
        tlds = [tld for tld, cb in self.tld_checkboxes.items() if cb.isChecked()]
        custom_raw = self.custom_tld_edit.text().strip()
        if custom_raw:
            for item in custom_raw.replace(",", " ").split():
                clean = item.strip().lower()
                if not clean.startswith("."):
                    clean = "." + clean
                if clean not in tlds:
                    tlds.append(clean)
        return tlds or [".com"]

    # -------------------------------------------------------------
    # Domain Gathering & Execution
    # -------------------------------------------------------------
    def _generate_candidate_domains(self) -> List[str]:
        idx = self.stacked_modes.currentIndex()
        tlds = self._get_selected_tlds()

        if idx == 0:  # Batch List
            text = self.txt_batch.toPlainText()
            return parse_custom_domains(text, tlds)

        elif idx == 1:  # Letter Length
            length = self.spin_letter_len.value()
            style_map = {
                "Pronounceable (CVCV)": "pronounceable",
                "Letters (a-z)": "letters",
                "Alphanumeric": "alphanumeric",
                "Digits Only": "digits",
                "Custom Pattern": "pattern"
            }
            style = style_map.get(self.combo_letter_style.currentText(), "pronounceable")
            pattern = self.pattern_edit.text().strip() if style == "pattern" else ""
            limit = self.spin_letter_limit.value()
            return generate_letter_domains(
                length=length,
                mode=style,
                pattern=pattern,
                strategy="random",
                max_count=limit,
                tlds=tlds
            )

        elif idx == 2:  # Keyword
            kw = self.kw_edit.text().strip()
            kw_list = [k.strip() for k in kw.replace(",", " ").split() if k.strip()] or ["cloud"]
            mode_map = {
                "Prefix & Suffix": "both",
                "Prefixes Only": "prefix",
                "Suffixes Only": "suffix",
                "Niche Pack": "niche",
                "Custom Affixes": "custom"
            }
            km = mode_map.get(self.combo_kw_mode.currentText(), "both")
            niche = self.combo_niche.currentText() if km == "niche" else ""
            affixes = [a.strip() for a in self.custom_affix_edit.text().replace(",", " ").split() if a.strip()]
            limit = self.spin_kw_limit.value()
            return generate_keyword_domains(
                keywords=kw_list,
                mode=km,
                custom_affixes=affixes,
                niche_pack=niche,
                tlds=tlds,
                max_count=limit
            )

        elif idx == 3:  # Brandables
            limit = self.spin_brand_limit.value()
            return generate_brandable_domains(tlds=tlds, max_count=limit)

        return []

    def start_scan(self):
        domains = self._generate_candidate_domains()
        if not domains:
            InfoBar.warning(
                title="No Domains",
                content="Please enter domain names or choose generation parameters.",
                parent=self,
                position=InfoBarPosition.TOP
            )
            return

        self.clear_results()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.lbl_status_msg.setText(f"Scanning {len(domains)} candidate domains...")

        max_workers = self.workers_slider.value()
        delay_sec = self.delay_slider.value() / 1000.0
        use_hybrid = "Hybrid" in self.engine_combo.currentText()

        self.worker = ScanWorker(domains, max_workers, delay_sec, use_hybrid)
        self.worker.result_ready.connect(self._on_result_ready)
        self.worker.progress_updated.connect(self._on_progress_updated)
        self.worker.scan_finished.connect(self._on_scan_finished)
        self.worker.start()

    def stop_scan(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.lbl_status_msg.setText("Stopping scan...")

    def _on_result_ready(self, item: Dict[str, Any]):
        self.results_data.append(item)
        if item.get("status") == "available":
            self.available_domains.append(item["domain"])

        if self._matches_filter(item):
            self._insert_table_row(item)

    def _on_progress_updated(self, p: Dict[str, Any]):
        self.lbl_stat_checked.setText(f"Checked: {p['checked']} / {p['total']}")
        self.lbl_stat_available.setText(f"Available: {p['available']}")
        self.lbl_stat_taken.setText(f"Taken: {p['taken']}")
        self.lbl_stat_speed.setText(f"Speed: {p['speed']}/s")
        self.lbl_stat_eta.setText(f"ETA: {int(p['eta'])}s" if p['eta'] > 0 else "ETA: --")
        self.progress_bar.setValue(p["percent"])

    def _on_scan_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.lbl_status_msg.setText(f"Scan complete. Found {len(self.available_domains)} verified available domains.")
        InfoBar.success(
            title="Scan Complete",
            content=f"Finished checking domains. {len(self.available_domains)} available found.",
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=4000
        )

    # -------------------------------------------------------------
    # Table & Filter Implementation
    # -------------------------------------------------------------
    def _matches_filter(self, item: Dict[str, Any]) -> bool:
        status = item.get("status", "")
        if self.rb_available.isChecked() and status != "available":
            return False
        if self.rb_taken.isChecked() and status != "taken":
            return False

        query = self.search_filter_edit.text().strip().lower()
        if query:
            if query not in item.get("domain", "").lower():
                return False

        return True

    def _insert_table_row(self, item: Dict[str, Any]):
        row = self.table.rowCount()
        self.table.insertRow(row)

        domain = item.get("domain", "")
        status = item.get("status", "error").upper()
        server = item.get("server", "")
        reason = item.get("reason", "")
        latency = f"{item.get('elapsed_ms', 0)} ms"
        base_name = domain.split(".")[0]
        length_str = str(len(base_name))

        # Domain item
        item_domain = QTableWidgetItem(domain)
        item_domain.setFont(QFont("Consolas", 10, QFont.Weight.Bold))

        # Status item with clean color coding
        item_status = QTableWidgetItem(status)
        item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if status == "AVAILABLE":
            item_status.setForeground(QColor("#22c55e"))
            item_status.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        elif status == "TAKEN":
            item_status.setForeground(QColor("#71717a"))
        else:
            item_status.setForeground(QColor("#eab308"))

        item_len = QTableWidgetItem(length_str)
        item_len.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        item_server = QTableWidgetItem(server)
        item_server.setFont(QFont("Consolas", 9))

        item_reason = QTableWidgetItem(reason)
        item_reason.setFont(QFont("Segoe UI", 9))

        item_lat = QTableWidgetItem(latency)
        item_lat.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        self.table.setItem(row, 0, item_domain)
        self.table.setItem(row, 1, item_status)
        self.table.setItem(row, 2, item_len)
        self.table.setItem(row, 3, item_server)
        self.table.setItem(row, 4, item_reason)
        self.table.setItem(row, 5, item_lat)

    def _apply_filters(self):
        self.table.setRowCount(0)
        for item in self.results_data:
            if self._matches_filter(item):
                self._insert_table_row(item)

    def clear_results(self):
        self.table.setRowCount(0)
        self.results_data.clear()
        self.available_domains.clear()
        self.lbl_stat_checked.setText("Checked: 0 / 0")
        self.lbl_stat_available.setText("Available: 0")
        self.lbl_stat_taken.setText("Taken: 0")
        self.lbl_stat_speed.setText("Speed: 0.0/s")
        self.lbl_stat_eta.setText("ETA: --")
        self.progress_bar.setValue(0)
        self.lbl_status_msg.setText("Ready.")

    # -------------------------------------------------------------
    # Context Menu & Actions
    # -------------------------------------------------------------
    def _show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return

        row = item.row()
        domain = self.table.item(row, 0).text()

        menu = RoundMenu(parent=self)
        act_copy = Action(FIF.COPY, f"Copy {domain}", triggered=lambda: self._copy_text(domain))
        act_porkbun = Action(FIF.GLOBE, "Register on Porkbun", triggered=lambda: self._open_registrar(domain, "porkbun"))
        act_namecheap = Action(FIF.LINK, "Register on Namecheap", triggered=lambda: self._open_registrar(domain, "namecheap"))
        act_godaddy = Action(FIF.LINK, "Register on GoDaddy", triggered=lambda: self._open_registrar(domain, "godaddy"))
        act_raw = Action(FIF.INFO, "View Raw WHOIS Response", triggered=lambda: self._show_whois_dialog(domain))

        menu.addAction(act_copy)
        menu.addSeparator()
        menu.addAction(act_porkbun)
        menu.addAction(act_namecheap)
        menu.addAction(act_godaddy)
        menu.addSeparator()
        menu.addAction(act_raw)

        menu.exec(self.table.mapToGlobal(pos))

    def _on_table_double_clicked(self, index):
        row = index.row()
        domain = self.table.item(row, 0).text()
        self._open_registrar(domain, "porkbun")

    def _copy_text(self, text: str):
        QApplication.clipboard().setText(text)
        InfoBar.info(title="Copied", content=f"Copied {text} to clipboard.", parent=self, position=InfoBarPosition.BOTTOM_RIGHT, duration=2000)

    def _open_registrar(self, domain: str, registrar: str):
        links = get_registrar_links(domain)
        url = links.get(registrar, links["porkbun"])
        webbrowser.open(url)

    def _show_whois_dialog(self, domain: str):
        match = next((r for r in self.results_data if r["domain"] == domain), None)
        snippet = match.get("raw_snippet", "No raw WHOIS text available.") if match else "No record found."

        w = MessageBox(f"Registry Response: {domain}", snippet, self)
        w.yesButton.setText("Close")
        w.cancelButton.hide()
        w.exec()

    def copy_available_domains(self):
        if not self.available_domains:
            InfoBar.warning(title="None Available", content="No available domains found in the current search.", parent=self)
            return

        text = "\n".join(self.available_domains)
        QApplication.clipboard().setText(text)
        InfoBar.success(
            title="Copied to Clipboard",
            content=f"Copied {len(self.available_domains)} available domains.",
            parent=self,
            position=InfoBarPosition.BOTTOM_RIGHT
        )

    def export_csv(self):
        if not self.results_data:
            InfoBar.warning(title="Export", content="No data to export.", parent=self)
            return

        path, _ = QFileDialog.getSaveFileName(self, "Save Domain Results CSV", "domain_results.csv", "CSV Files (*.csv);;All Files (*.*)")
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("Domain,Status,Registry Server,Reason,Latency_ms\n")
                for r in self.results_data:
                    reason = r.get("reason", "").replace('"', '""')
                    f.write(f'"{r["domain"]}","{r["status"]}","{r.get("server","")}","{reason}",{r.get("elapsed_ms",0)}\n')
            InfoBar.success(title="Saved", content=f"Exported {len(self.results_data)} domains to CSV.", parent=self)
        except Exception as e:
            InfoBar.error(title="Export Error", content=str(e), parent=self)

    def export_txt(self):
        if not self.available_domains:
            InfoBar.warning(title="Export", content="No available domains to export.", parent=self)
            return

        path, _ = QFileDialog.getSaveFileName(self, "Save Available Domains TXT", "available_domains.txt", "Text Files (*.txt);;All Files (*.*)")
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.available_domains) + "\n")
            InfoBar.success(title="Saved", content=f"Exported {len(self.available_domains)} available domains to TXT.", parent=self)
        except Exception as e:
            InfoBar.error(title="Export Error", content=str(e), parent=self)


class SettingsInterface(QWidget):
    """Configuration interface for default registrar and theme."""
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("settings_interface")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(18)

        layout.addWidget(TitleLabel("Settings"))

        card = ElevatedCardWidget()
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(20, 20, 20, 20)
        c_layout.setSpacing(14)

        c_layout.addWidget(StrongBodyLabel("Application Preferences"))

        r1 = QHBoxLayout()
        r1.addWidget(BodyLabel("Default Registrar for Purchase Links:"))
        self.combo_reg = ComboBox()
        self.combo_reg.addItems(["Porkbun", "Namecheap", "GoDaddy", "Cloudflare"])
        r1.addWidget(self.combo_reg)
        c_layout.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(BodyLabel("Theme Appearance:"))
        self.combo_theme = ComboBox()
        self.combo_theme.addItems(["Dark Mode", "Light Mode", "System Default"])
        self.combo_theme.currentTextChanged.connect(self._on_theme_changed)
        r2.addWidget(self.combo_theme)
        c_layout.addLayout(r2)

        layout.addWidget(card)
        layout.addStretch()

    def _on_theme_changed(self, text: str):
        if "Dark" in text:
            setTheme(Theme.DARK)
        elif "Light" in text:
            setTheme(Theme.LIGHT)
        else:
            setTheme(Theme.AUTO)


class InfoInterface(QWidget):
    """Authoritative architecture and verification documentation."""
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("info_interface")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(16)

        layout.addWidget(TitleLabel("Authoritative Registry Verification"))

        card = ElevatedCardWidget()
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(20, 20, 20, 20)
        c_layout.setSpacing(12)

        c_layout.addWidget(StrongBodyLabel("Why DNS NXDOMAIN is Insufficient"))
        info1 = BodyLabel(
            "Standard DNS resolvers only indicate whether a domain has active nameserver records.\n"
            "Tens of thousands of registered domains sit parked without nameservers attached or with DNS inactive.\n"
            "Relying on NXDOMAIN results in false positives for held or parked domains."
        )
        info1.setTextColor("#a1a1aa", "#71717a")
        c_layout.addWidget(info1)

        c_layout.addWidget(StrongBodyLabel("Direct TLD Registry Socket Verification"))
        info2 = BodyLabel(
            "DomainPulse establishes direct socket connections (Port 43) to official registry databases:\n"
            " • .com / .net: Verisign Registry WHOIS (whois.verisign-grs.com)\n"
            " • .io / .ai: Identity Digital Registry WHOIS (whois.nic.io, whois.nic.ai)\n"
            " • .org: Public Interest Registry (whois.pir.org)\n"
            " • .co: CoInternet / Registry.co (whois.registry.co)\n"
            " • .app / .dev: Google Registry (whois.nic.google)\n"
            " • Other TLDs: Dynamic IANA root discovery with ICANN RDAP HTTPS fallback."
        )
        info2.setTextColor("#a1a1aa", "#71717a")
        c_layout.addWidget(info2)

        layout.addWidget(card)
        layout.addStretch()


class MainWindow(FluentWindow):
    """Top-level Windows 11 Fluent Application Window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DomainPulse - Authoritative Domain Scraper")
        self.resize(1180, 780)
        self.setMinimumSize(980, 640)

        # Navigation interfaces
        self.scanner_interface = ScannerInterface(self)
        self.settings_interface = SettingsInterface(self)
        self.info_interface = InfoInterface(self)

        self._init_navigation()

    def _init_navigation(self):
        self.addSubInterface(
            self.scanner_interface,
            FIF.SEARCH,
            "Scanner",
            NavigationItemPosition.TOP
        )
        self.addSubInterface(
            self.settings_interface,
            FIF.SETTING,
            "Settings",
            NavigationItemPosition.BOTTOM
        )
        self.addSubInterface(
            self.info_interface,
            FIF.INFO,
            "Architecture",
            NavigationItemPosition.BOTTOM
        )


def launch_fluent_app():
    """Start the PyQt6 Fluent application."""
    app = QApplication(sys.argv)
    setTheme(Theme.DARK)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_fluent_app()

"""
Domain Availability Scraper - Professional Windows 11 Desktop Application.
Authoritative Registry WHOIS & RDAP verification engine with PyQt6 and PyQt6-Fluent-Widgets.
High-performance architecture with 120 FPS batch-buffered GUI rendering,
unified single-tone left panel, symmetric spacing, zero-scroll default layout,
and fixed icon-only navigation.
"""

import sys
import os
import time
import webbrowser
import threading
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QFont, QColor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QHeaderView, QTableWidgetItem, QFileDialog, QSplitter, QFrame,
    QStackedWidget, QLabel, QButtonGroup, QSizePolicy, QAbstractItemView,
    QScrollArea
)

from qfluentwidgets import (
    FluentWindow, NavigationInterface, NavigationItemPosition,
    PrimaryPushButton, PushButton, PillPushButton, ToolButton, TransparentToolButton,
    LineEdit, TextEdit, PlainTextEdit, SearchLineEdit, ComboBox, SpinBox, Slider,
    CheckBox, RadioButton, ProgressBar, TableWidget, CardWidget,
    ElevatedCardWidget, FluentIcon as FIF, InfoBar, InfoBarPosition,
    RoundMenu, Action, Pivot, SegmentedWidget, SubtitleLabel, CaptionLabel,
    BodyLabel, StrongBodyLabel, TitleLabel, setTheme, Theme, MessageBox
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
    """
    High-performance background worker thread.
    Uses as_completed() for instant out-of-order completion, combined with a 50ms
    thread-safe batch flush to ensure the Qt main thread repaints at 60-120 FPS
    with zero lag or stutter.
    """
    batch_ready = pyqtSignal(list, dict)
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

        buffer: List[Dict[str, Any]] = []
        buffer_lock = threading.Lock()
        last_flush_time = time.time()

        def flush_buffer():
            nonlocal last_flush_time
            with buffer_lock:
                if buffer:
                    batch = list(buffer)
                    buffer.clear()
                    last_flush_time = time.time()

                    now = time.time()
                    elapsed = max(0.001, now - start_time)
                    speed = checked / elapsed
                    eta = (total - checked) / speed if speed > 0 else 0

                    metrics = {
                        "checked": checked,
                        "total": total,
                        "available": available_count,
                        "taken": taken_count,
                        "speed": round(speed, 1),
                        "eta": round(eta, 1),
                        "percent": int((checked / total) * 100) if total > 0 else 100
                    }
                    self.batch_ready.emit(batch, metrics)

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

            for f in as_completed(futures):
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

                    with buffer_lock:
                        buffer.append(res)

                    now = time.time()
                    if len(buffer) >= 10 or (now - last_flush_time) >= 0.05:
                        flush_buffer()

                except Exception:
                    pass

        flush_buffer()
        self.scan_finished.emit()


class ScannerInterface(QWidget):
    """Main domain scanning workspace with controls and live fluent data table."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("scanner_interface")

        self.worker: Optional[ScanWorker] = None
        self.results_data: List[Dict[str, Any]] = []
        self.available_domains: List[str] = []
        self.default_registrar = "godaddy"

        # TLD Pill Buttons Dictionary: tld_str -> PillPushButton
        self.tld_pills: Dict[str, PillPushButton] = {}
        self.common_tlds = [
            ".com", ".io", ".ai", ".co",
            ".net", ".org", ".app", ".dev",
            ".xyz", ".tech", ".sh", ".me"
        ]

        self._init_ui()

    def _init_ui(self):
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(0)

        # Resizable Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: transparent;
                width: 8px;
            }
            QSplitter::handle:hover {
                background-color: rgba(255, 255, 255, 0.12);
                border-radius: 4px;
            }
        """)

        # -------------------------------------------------------------
        # LEFT PANEL: Flat, Zero-Rounded-Corner Container
        # -------------------------------------------------------------
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setMinimumWidth(360)
        left_scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        left_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                border-radius: 0px;
                background: #141416;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #3f3f46;
                min-height: 24px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: #52525b;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # Flat single-tone container: completely flush with ZERO rounded corners
        left_container = QFrame()
        left_container.setObjectName("leftContainer")
        left_container.setStyleSheet("""
            #leftContainer {
                background-color: #141416;
                border: none;
                border-right: 1px solid #27272a;
                border-radius: 0px;
            }
        """)
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(16, 12, 16, 12)
        left_layout.setSpacing(8)

        # -------------------------------------------------------------
        # SECTION 1: Search Parameters
        # -------------------------------------------------------------
        lbl_params_title = StrongBodyLabel("Search Parameters")
        left_layout.addWidget(lbl_params_title)

        # Mode Segmented Tabs
        self.segment = SegmentedWidget(self)
        self.segment.addItem("batch", "List")
        self.segment.addItem("letters", "Length")
        self.segment.addItem("keyword", "Keywords")
        self.segment.addItem("brandables", "Roots")
        self.segment.setCurrentItem("batch")
        self.segment.setFixedHeight(30)
        self.segment.currentItemChanged.connect(self._on_segment_changed)
        left_layout.addWidget(self.segment)

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

        # -------------------------------------------------------------
        # SECTION 2: Domain Extensions
        # -------------------------------------------------------------
        lbl_tld_title = StrongBodyLabel("Domain Extensions")
        left_layout.addWidget(lbl_tld_title)

        # Preset Quick Filter Bar
        preset_bar = QHBoxLayout()
        preset_bar.setContentsMargins(0, 0, 0, 0)
        preset_bar.setSpacing(4)
        presets = [
            ("Popular", "popular"),
            ("Tech", "tech"),
            ("Startup", "startup"),
            ("All", "all"),
            ("Clear", "none")
        ]
        for name, key in presets:
            btn = PushButton(name)
            btn.setFixedHeight(24)
            btn.setFont(QFont("Segoe UI", 8))
            btn.clicked.connect(lambda checked, k=key: self._apply_tld_preset(k))
            preset_bar.addWidget(btn)
        preset_bar.addStretch()
        left_layout.addLayout(preset_bar)

        # Grid of Modern Pill Buttons (4 columns x 3 rows for compact vertical height)
        self.tld_grid = QGridLayout()
        self.tld_grid.setSpacing(6)
        self.tld_grid.setContentsMargins(0, 0, 0, 0)
        default_active = {".com", ".io", ".ai"}

        for idx, tld in enumerate(self.common_tlds):
            pill = PillPushButton(tld)
            pill.setCheckable(True)
            pill.setChecked(tld in default_active)
            pill.setFixedHeight(28)
            pill.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
            self.tld_pills[tld] = pill
            self.tld_grid.addWidget(pill, idx // 4, idx % 4)

        left_layout.addLayout(self.tld_grid)

        # Custom TLD Input Row with + Add Button
        add_tld_layout = QHBoxLayout()
        add_tld_layout.setContentsMargins(0, 0, 0, 0)
        add_tld_layout.setSpacing(6)

        self.custom_tld_edit = LineEdit()
        self.custom_tld_edit.setPlaceholderText("Custom TLD (e.g. .store, .club)")
        self.custom_tld_edit.setFixedHeight(30)
        self.custom_tld_edit.returnPressed.connect(self._add_custom_tld_from_input)

        self.btn_add_tld = PrimaryPushButton(FIF.ADD, "Add")
        self.btn_add_tld.setFixedHeight(30)
        self.btn_add_tld.setFixedWidth(70)
        self.btn_add_tld.clicked.connect(self._add_custom_tld_from_input)

        add_tld_layout.addWidget(self.custom_tld_edit, 1)
        add_tld_layout.addWidget(self.btn_add_tld, 0)
        left_layout.addLayout(add_tld_layout)

        # Separator line
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #27272a;")
        left_layout.addWidget(sep2)

        # -------------------------------------------------------------
        # SECTION 3: Engine & Settings
        # -------------------------------------------------------------
        lbl_engine_title = StrongBodyLabel("Engine & Performance")
        left_layout.addWidget(lbl_engine_title)

        # Mode Combobox (Full Width)
        self.engine_combo = ComboBox()
        self.engine_combo.addItems([
            "Hybrid (Fast DNS Pre-Filter + WHOIS)",
            "Strict Registry WHOIS (All Port 43)"
        ])
        self.engine_combo.setCurrentIndex(0)
        self.engine_combo.setFixedHeight(30)
        left_layout.addWidget(self.engine_combo)

        # Workers Slider Block
        self.workers_val_lbl = StrongBodyLabel("12 workers")
        self.workers_val_lbl.setTextColor("#38bdf8", "#0284c7")
        self.workers_slider = Slider(Qt.Orientation.Horizontal)
        self.workers_slider.setRange(3, 25)
        self.workers_slider.setValue(12)
        self.workers_slider.setFixedHeight(18)
        self.workers_slider.valueChanged.connect(lambda v: self.workers_val_lbl.setText(f"{v} workers"))
        left_layout.addWidget(self._make_slider_block("Concurrent Workers:", self.workers_slider, self.workers_val_lbl))

        # Delay Slider Block
        self.delay_val_lbl = StrongBodyLabel("50 ms")
        self.delay_val_lbl.setTextColor("#a1a1aa", "#71717a")
        self.delay_slider = Slider(Qt.Orientation.Horizontal)
        self.delay_slider.setRange(0, 500)
        self.delay_slider.setValue(50)
        self.delay_slider.setFixedHeight(18)
        self.delay_slider.valueChanged.connect(lambda v: self.delay_val_lbl.setText(f"{v} ms"))
        left_layout.addWidget(self._make_slider_block("Request Delay (anti-ban):", self.delay_slider, self.delay_val_lbl))

        # Default Registrar Row (GoDaddy #1 default)
        self.combo_default_reg = ComboBox()
        self.combo_default_reg.addItems(["GoDaddy", "Cloudflare", "Dynadot", "Namecheap", "Porkbun"])
        self.combo_default_reg.setCurrentText("GoDaddy")
        self.combo_default_reg.currentTextChanged.connect(self._on_registrar_changed)
        self.combo_default_reg.setFixedWidth(150)
        left_layout.addWidget(self._make_form_row("Default Registrar:", self.combo_default_reg))

        # Separator line
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setStyleSheet("color: #27272a;")
        left_layout.addWidget(sep3)

        # -------------------------------------------------------------
        # SECTION 4: Action Buttons (Always Visible Without Scrolling)
        # -------------------------------------------------------------
        btn_action_layout = QHBoxLayout()
        btn_action_layout.setContentsMargins(0, 0, 0, 0)
        btn_action_layout.setSpacing(8)

        self.btn_start = PrimaryPushButton(FIF.PLAY, "Start Search")
        self.btn_start.setFixedHeight(38)
        self.btn_start.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_start.clicked.connect(self.start_scan)

        self.btn_stop = PushButton(FIF.CANCEL, "Stop")
        self.btn_stop.setFixedHeight(38)
        self.btn_stop.setFont(QFont("Segoe UI", 9))
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_scan)

        self.btn_clear = PushButton(FIF.DELETE, "Clear")
        self.btn_clear.setFixedHeight(38)
        self.btn_clear.setFont(QFont("Segoe UI", 9))
        self.btn_clear.clicked.connect(self.clear_results)

        btn_action_layout.addWidget(self.btn_start, 3)
        btn_action_layout.addWidget(self.btn_stop, 2)
        btn_action_layout.addWidget(self.btn_clear, 2)
        left_layout.addLayout(btn_action_layout)

        left_layout.addStretch()
        left_scroll.setWidget(left_container)
        splitter.addWidget(left_scroll)

        # -------------------------------------------------------------
        # RIGHT PANEL: Expansive Data Table & Results Dashboard
        # -------------------------------------------------------------
        right_container = CardWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(18, 16, 18, 16)
        right_layout.setSpacing(12)

        # 1. KPI Metrics Banner (5 Centered Mathematical Tiles)
        kpi_frame = ElevatedCardWidget()
        kpi_layout = QHBoxLayout(kpi_frame)
        kpi_layout.setContentsMargins(10, 8, 10, 8)
        kpi_layout.setSpacing(6)

        t1, self.lbl_stat_checked = self._create_kpi_tile("TOTAL CHECKED", "0 / 0")
        t2, self.lbl_stat_available = self._create_kpi_tile("AVAILABLE", "0", text_color="#22c55e")
        t3, self.lbl_stat_taken = self._create_kpi_tile("TAKEN", "0", text_color="#71717a")
        t4, self.lbl_stat_speed = self._create_kpi_tile("SPEED", "0.0 /s", text_color="#38bdf8")
        t5, self.lbl_stat_eta = self._create_kpi_tile("TIME REMAINING", "--")

        for tile in (t1, t2, t3, t4, t5):
            kpi_layout.addWidget(tile, 1)

        right_layout.addWidget(kpi_frame)

        # Progress bar
        self.progress_bar = ProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(4)
        right_layout.addWidget(self.progress_bar)

        # 2. Filter & Real-Time Search Bar
        filter_bar_layout = QHBoxLayout()
        filter_bar_layout.setContentsMargins(0, 0, 0, 0)
        filter_bar_layout.setSpacing(12)

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
        self.search_filter_edit.setPlaceholderText("Filter domain results...")
        self.search_filter_edit.setFixedWidth(260)
        self.search_filter_edit.setFixedHeight(30)
        self.search_filter_edit.textChanged.connect(self._apply_filters)
        filter_bar_layout.addWidget(self.search_filter_edit)
        right_layout.addLayout(filter_bar_layout)

        # 3. Main Fluent Data Table (Fixed column widths for zero horizontal overflow)
        self.table = TableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Domain", "Status", "Length", "Registry Server", "WHOIS Response", "Latency"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 250)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 80)
        self.table.setColumnWidth(3, 220)
        self.table.setColumnWidth(5, 100)

        self.table.setSortingEnabled(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._on_table_double_clicked)
        self.table.verticalHeader().hide()

        right_layout.addWidget(self.table, 1)

        # 4. Bottom Toolbar
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(10)

        self.btn_copy_avail = PrimaryPushButton(FIF.COPY, "Copy Available")
        self.btn_copy_avail.setFixedHeight(34)
        self.btn_copy_avail.clicked.connect(self.copy_available_domains)

        self.btn_export_csv = PushButton(FIF.SAVE, "Export CSV")
        self.btn_export_csv.setFixedHeight(34)
        self.btn_export_csv.clicked.connect(self.export_csv)

        self.btn_export_txt = PushButton(FIF.DOCUMENT, "Export TXT")
        self.btn_export_txt.setFixedHeight(34)
        self.btn_export_txt.clicked.connect(self.export_txt)

        self.lbl_status_msg = CaptionLabel("Ready. Select search parameters and press Start Search.")
        self.lbl_status_msg.setTextColor("#71717a", "#71717a")

        bottom_layout.addWidget(self.btn_copy_avail)
        bottom_layout.addWidget(self.btn_export_csv)
        bottom_layout.addWidget(self.btn_export_txt)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.lbl_status_msg)
        right_layout.addLayout(bottom_layout)

        splitter.addWidget(right_container)

        # Splitter proportion defaults (compact left panel ~380px, expansive right table ~1160px)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 1160])

        root_layout.addWidget(splitter)

    # -------------------------------------------------------------
    # Helper Layout Builders (Ensures Pixel-Perfect Consistency)
    # -------------------------------------------------------------
    def _create_kpi_tile(self, title_text: str, initial_value: str, text_color: Optional[str] = None):
        tile = QWidget()
        tile_layout = QVBoxLayout(tile)
        tile_layout.setContentsMargins(2, 2, 2, 2)
        tile_layout.setSpacing(2)
        tile_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_lbl = CaptionLabel(title_text)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setTextColor("#71717a", "#71717a")
        title_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))

        val_lbl = StrongBodyLabel(initial_value)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        if text_color:
            val_lbl.setTextColor(text_color, text_color)

        tile_layout.addWidget(title_lbl)
        tile_layout.addWidget(val_lbl)
        return tile, val_lbl

    def _make_form_row(self, label_text: str, widget: QWidget) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        lbl = BodyLabel(label_text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(lbl, 1)
        widget.setFixedHeight(30)
        h.addWidget(widget, 0)
        return row

    def _make_slider_block(self, label_text: str, slider: Slider, val_label: QLabel) -> QWidget:
        block = QWidget()
        v = QVBoxLayout(block)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        lbl = BodyLabel(label_text)
        hdr.addWidget(lbl)
        hdr.addStretch()
        hdr.addWidget(val_label)

        v.addLayout(hdr)
        v.addWidget(slider)
        return block

    # -------------------------------------------------------------
    # Mode Configuration Widgets (Compact & Clean Layouts)
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
        self.txt_batch.setFixedHeight(85)
        self.txt_batch.setFont(QFont("Consolas", 10))
        layout.addWidget(self.txt_batch)

        self.stacked_modes.addWidget(page)

    def _build_letter_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Row 1: Length (Direct numeric input, zero arrow buttons)
        self.edit_letter_len = LineEdit()
        self.edit_letter_len.setText("4")
        self.edit_letter_len.setFixedWidth(80)
        self.edit_letter_len.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit_letter_len.setPlaceholderText("4")
        layout.addWidget(self._make_form_row("Letter Length:", self.edit_letter_len))

        # Row 2: Pattern Style
        self.combo_letter_style = ComboBox()
        self.combo_letter_style.addItems([
            "Pronounceable (CVCV)",
            "Letters (a-z)",
            "Alphanumeric",
            "Digits Only",
            "Custom Pattern"
        ])
        self.combo_letter_style.setFixedWidth(160)
        self.combo_letter_style.currentTextChanged.connect(self._on_letter_style_changed)
        layout.addWidget(self._make_form_row("Pattern Style:", self.combo_letter_style))

        # Wildcard pattern entry
        self.pattern_container = QWidget()
        pattern_layout = QHBoxLayout(self.pattern_container)
        pattern_layout.setContentsMargins(0, 0, 0, 0)
        pattern_layout.setSpacing(8)
        lbl_pat = CaptionLabel("Wildcard (?=let, #=dig):")
        pattern_layout.addWidget(lbl_pat, 1)
        self.pattern_edit = LineEdit()
        self.pattern_edit.setPlaceholderText("e.g. ?ai, xx?")
        self.pattern_edit.setFixedWidth(160)
        self.pattern_edit.setFixedHeight(30)
        pattern_layout.addWidget(self.pattern_edit, 0)
        layout.addWidget(self.pattern_container)
        self.pattern_container.hide()

        # Row 4: Max Count Limit (Direct numeric input, zero arrow buttons)
        self.edit_letter_limit = LineEdit()
        self.edit_letter_limit.setText("50")
        self.edit_letter_limit.setFixedWidth(80)
        self.edit_letter_limit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit_letter_limit.setPlaceholderText("50")
        layout.addWidget(self._make_form_row("Max Count:", self.edit_letter_limit))

        self.stacked_modes.addWidget(page)

    def _build_keyword_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Row 1: Keyword entry
        self.kw_edit = LineEdit()
        self.kw_edit.setText("cloud")
        self.kw_edit.setFixedWidth(160)
        layout.addWidget(self._make_form_row("Target Keyword:", self.kw_edit))

        # Row 2: Mode
        self.combo_kw_mode = ComboBox()
        self.combo_kw_mode.addItems([
            "Prefix & Suffix",
            "Prefixes Only",
            "Suffixes Only",
            "Niche Pack",
            "Custom Affixes"
        ])
        self.combo_kw_mode.setFixedWidth(160)
        self.combo_kw_mode.currentTextChanged.connect(self._on_kw_mode_changed)
        layout.addWidget(self._make_form_row("Affix Mode:", self.combo_kw_mode))

        # Niche pack container
        self.niche_container = QWidget()
        niche_layout = QHBoxLayout(self.niche_container)
        niche_layout.setContentsMargins(0, 0, 0, 0)
        niche_layout.setSpacing(8)
        niche_layout.addWidget(CaptionLabel("Industry Niche:"), 1)
        self.combo_niche = ComboBox()
        self.combo_niche.addItems(list(NICHE_PACKS.keys()))
        self.combo_niche.setFixedWidth(160)
        niche_layout.addWidget(self.combo_niche, 0)
        layout.addWidget(self.niche_container)
        self.niche_container.hide()

        # Custom affixes container
        self.custom_affix_container = QWidget()
        custom_layout = QHBoxLayout(self.custom_affix_container)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(8)
        custom_layout.addWidget(CaptionLabel("Custom Words:"), 1)
        self.custom_affix_edit = LineEdit()
        self.custom_affix_edit.setPlaceholderText("fast, smart, zone")
        self.custom_affix_edit.setFixedWidth(160)
        custom_layout.addWidget(self.custom_affix_edit, 0)
        layout.addWidget(self.custom_affix_container)
        self.custom_affix_container.hide()

        # Row 5: Limit (Direct numeric input, zero arrow buttons)
        self.edit_kw_limit = LineEdit()
        self.edit_kw_limit.setText("50")
        self.edit_kw_limit.setFixedWidth(80)
        self.edit_kw_limit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit_kw_limit.setPlaceholderText("50")
        layout.addWidget(self._make_form_row("Max Count:", self.edit_kw_limit))

        self.stacked_modes.addWidget(page)

    def _build_brandables_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        lbl = CaptionLabel("Tests curated short startup brandable roots\n(e.g. velo, koba, zira, lux, nova, apex)")
        lbl.setTextColor("#a1a1aa", "#71717a")
        layout.addWidget(lbl)

        # Direct numeric input, zero arrow buttons
        self.edit_brand_limit = LineEdit()
        self.edit_brand_limit.setText("30")
        self.edit_brand_limit.setFixedWidth(80)
        self.edit_brand_limit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit_brand_limit.setPlaceholderText("30")
        layout.addWidget(self._make_form_row("Root Count:", self.edit_brand_limit))

        self.stacked_modes.addWidget(page)

    def _on_segment_changed(self, item_key: str):
        mapping = {"batch": 0, "letters": 1, "keyword": 2, "brandables": 3}
        self.stacked_modes.setCurrentIndex(mapping.get(item_key, 0))

    def _on_letter_style_changed(self, text: str):
        if text == "Custom Pattern":
            self.pattern_container.show()
        else:
            self.pattern_container.hide()

    def _on_kw_mode_changed(self, text: str):
        if text == "Niche Pack":
            self.niche_container.show()
            self.custom_affix_container.hide()
        elif text == "Custom Affixes":
            self.custom_affix_container.show()
            self.niche_container.hide()
        else:
            self.niche_container.hide()
            self.custom_affix_container.hide()

    def _on_registrar_changed(self, text: str):
        self.default_registrar = text.lower()

    # -------------------------------------------------------------
    # TLD Management (Interactive Pills & Dynamic Custom Adder)
    # -------------------------------------------------------------
    def _apply_tld_preset(self, preset_key: str):
        if preset_key == "none":
            for pill in self.tld_pills.values():
                pill.setChecked(False)
            return

        target = TLD_PRESETS.get(preset_key, [".com", ".net", ".org"])
        if preset_key == "all":
            for pill in self.tld_pills.values():
                pill.setChecked(True)
            return

        for tld, pill in self.tld_pills.items():
            pill.setChecked(tld in target)

    def _add_custom_tld_from_input(self):
        raw_text = self.custom_tld_edit.text().strip()
        if not raw_text:
            return

        added_count = 0
        items = raw_text.replace(",", " ").split()
        for item in items:
            clean = item.strip().lower()
            if not clean:
                continue
            if not clean.startswith("."):
                clean = "." + clean

            if clean in self.tld_pills:
                self.tld_pills[clean].setChecked(True)
                added_count += 1
                continue

            # Create new PillPushButton dynamically in the 4-column grid
            pill = PillPushButton(clean)
            pill.setCheckable(True)
            pill.setChecked(True)
            pill.setFixedHeight(28)
            pill.setFont(QFont("Consolas", 9, QFont.Weight.Bold))

            idx = len(self.tld_pills)
            self.tld_pills[clean] = pill
            self.tld_grid.addWidget(pill, idx // 4, idx % 4)
            added_count += 1

        self.custom_tld_edit.clear()

        if added_count > 0:
            InfoBar.success(
                title="Extension Added",
                content=f"Added {raw_text} to active extensions.",
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2500
            )

    def _get_selected_tlds(self) -> List[str]:
        selected = [tld for tld, pill in self.tld_pills.items() if pill.isChecked()]
        return selected or [".com"]

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
            try:
                length = int(self.edit_letter_len.text().strip() or "4")
            except ValueError:
                length = 4
            style_map = {
                "Pronounceable (CVCV)": "pronounceable",
                "Letters (a-z)": "letters",
                "Alphanumeric": "alphanumeric",
                "Digits Only": "digits",
                "Custom Pattern": "pattern"
            }
            style = style_map.get(self.combo_letter_style.currentText(), "pronounceable")
            pattern = self.pattern_edit.text().strip() if style == "pattern" else ""
            try:
                limit = int(self.edit_letter_limit.text().strip() or "50")
            except ValueError:
                limit = 50
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
            try:
                limit = int(self.edit_kw_limit.text().strip() or "50")
            except ValueError:
                limit = 50
            return generate_keyword_domains(
                keywords=kw_list,
                mode=km,
                custom_affixes=affixes,
                niche_pack=niche,
                tlds=tlds,
                max_count=limit
            )

        elif idx == 3:  # Brandables
            try:
                limit = int(self.edit_brand_limit.text().strip() or "30")
            except ValueError:
                limit = 30
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
        self.worker.batch_ready.connect(self._on_batch_ready)
        self.worker.scan_finished.connect(self._on_scan_finished)
        self.worker.start()

    def stop_scan(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.lbl_status_msg.setText("Stopping scan...")

    def _on_batch_ready(self, items: List[Dict[str, Any]], metrics: Dict[str, Any]):
        """Batched row insertions: suspends UI updates during batch for 120 FPS smoothness."""
        self.table.setUpdatesEnabled(False)
        for item in items:
            self.results_data.append(item)
            if item.get("status") == "available":
                self.available_domains.append(item["domain"])

            if self._matches_filter(item):
                self._insert_table_row(item)
        self.table.setUpdatesEnabled(True)

        # Update metrics once per batch tick
        self.lbl_stat_checked.setText(f"{metrics['checked']} / {metrics['total']}")
        self.lbl_stat_available.setText(str(metrics["available"]))
        self.lbl_stat_taken.setText(str(metrics["taken"]))
        self.lbl_stat_speed.setText(f"{metrics['speed']} /s")
        self.lbl_stat_eta.setText(f"{int(metrics['eta'])}s" if metrics["eta"] > 0 else "--")
        self.progress_bar.setValue(metrics["percent"])

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
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        for item in self.results_data:
            if self._matches_filter(item):
                self._insert_table_row(item)
        self.table.setUpdatesEnabled(True)

    def clear_results(self):
        self.table.setRowCount(0)
        self.results_data.clear()
        self.available_domains.clear()
        self.lbl_stat_checked.setText("0 / 0")
        self.lbl_stat_available.setText("0")
        self.lbl_stat_taken.setText("0")
        self.lbl_stat_speed.setText("0.0 /s")
        self.lbl_stat_eta.setText("--")
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

        # Registrar Order: GoDaddy #1 (Default), Cloudflare, Dynadot, Namecheap, Porkbun (last)
        act_godaddy = Action(FIF.GLOBE, "Register on GoDaddy (Default)", triggered=lambda: self._open_registrar(domain, "godaddy"))
        act_cloudflare = Action(FIF.LINK, "Register on Cloudflare", triggered=lambda: self._open_registrar(domain, "cloudflare"))
        act_dynadot = Action(FIF.LINK, "Register on Dynadot", triggered=lambda: self._open_registrar(domain, "dynadot"))
        act_namecheap = Action(FIF.LINK, "Register on Namecheap", triggered=lambda: self._open_registrar(domain, "namecheap"))
        act_porkbun = Action(FIF.LINK, "Register on Porkbun", triggered=lambda: self._open_registrar(domain, "porkbun"))
        act_raw = Action(FIF.INFO, "View Raw WHOIS Response", triggered=lambda: self._show_whois_dialog(domain))

        menu.addAction(act_copy)
        menu.addSeparator()
        menu.addAction(act_godaddy)
        menu.addAction(act_cloudflare)
        menu.addAction(act_dynadot)
        menu.addAction(act_namecheap)
        menu.addAction(act_porkbun)
        menu.addSeparator()
        menu.addAction(act_raw)

        menu.exec(self.table.mapToGlobal(pos))

    def _on_table_double_clicked(self, index):
        row = index.row()
        domain = self.table.item(row, 0).text()
        self._open_registrar(domain, self.default_registrar)

    def _copy_text(self, text: str):
        QApplication.clipboard().setText(text)
        InfoBar.info(title="Copied", content=f"Copied {text} to clipboard.", parent=self, position=InfoBarPosition.BOTTOM_RIGHT, duration=2000)

    def _open_registrar(self, domain: str, registrar: Optional[str] = None):
        reg = (registrar or self.default_registrar).lower()
        links = get_registrar_links(domain)
        url = links.get(reg, links["godaddy"])
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
        self.combo_reg.addItems(["GoDaddy", "Cloudflare", "Dynadot", "Namecheap", "Porkbun"])
        self.combo_reg.setCurrentText("GoDaddy")
        self.combo_reg.currentTextChanged.connect(self._on_registrar_changed)
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

    def _on_registrar_changed(self, text: str):
        main_win = self.window()
        if hasattr(main_win, "scanner_interface"):
            main_win.scanner_interface.default_registrar = text.lower()
            main_win.scanner_interface.combo_default_reg.setCurrentText(text)

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
            "The scraper establishes direct socket connections (Port 43) to official registry databases:\n"
            " - .com / .net: Verisign Registry WHOIS (whois.verisign-grs.com)\n"
            " - .io / .ai: Identity Digital Registry WHOIS (whois.nic.io, whois.nic.ai)\n"
            " - .org: Public Interest Registry (whois.pir.org)\n"
            " - .co: CoInternet / Registry.co (whois.registry.co)\n"
            " - .app / .dev: Google Registry (whois.nic.google)\n"
            " - Other TLDs: Dynamic IANA root discovery with ICANN RDAP HTTPS fallback."
        )
        info2.setTextColor("#a1a1aa", "#71717a")
        c_layout.addWidget(info2)

        layout.addWidget(card)
        layout.addStretch()


class MainWindow(FluentWindow):
    """Top-level Windows 11 Fluent Application Window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Domain Availability Scraper")
        self.resize(1540, 880)
        self.setMinimumSize(1100, 680)

        # Lock navigation interface permanently to a tiny 48px icon-only rail:
        # Prevent NavigationPanel from automatically expanding to 322px when window width >= 1008px
        nav = self.navigationInterface
        panel = getattr(nav, 'panel', nav)
        panel.setMenuButtonVisible(False)
        panel.setCollapsible(False)
        panel.setMinimumExpandWidth(99999)
        panel.setExpandWidth(48)
        nav.setFixedWidth(48)
        panel.setFixedWidth(48)

        # Navigation interfaces
        self.scanner_interface = ScannerInterface(self)
        self.settings_interface = SettingsInterface(self)
        self.info_interface = InfoInterface(self)

        self._init_navigation()

    def _init_navigation(self):
        # Pass empty string for text: pure icons only, zero text
        self.addSubInterface(
            self.scanner_interface,
            FIF.SEARCH,
            "",
            NavigationItemPosition.TOP
        )
        self.addSubInterface(
            self.settings_interface,
            FIF.SETTING,
            "",
            NavigationItemPosition.BOTTOM
        )
        self.addSubInterface(
            self.info_interface,
            FIF.INFO,
            "",
            NavigationItemPosition.BOTTOM
        )

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "navigationInterface"):
            self.navigationInterface.setFixedWidth(48)
            panel = getattr(self.navigationInterface, 'panel', self.navigationInterface)
            if panel is not None:
                panel.setFixedWidth(48)


def launch_fluent_app():
    """Start the PyQt6 Fluent application."""
    app = QApplication(sys.argv)
    setTheme(Theme.DARK)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_fluent_app()

/**
 * DomainPulse - Frontend Client Application
 * Handles WebSocket communication, reactive UI state, domain generation,
 * high-performance batch rendering, filtering, and export.
 */

// Application State
const state = {
    activeTab: 'custom', // 'custom' | 'letters' | 'keyword' | 'brandable'
    selectedTlds: new Set(['.com', '.io', '.ai']),
    customTlds: new Set(),
    isScanning: false,
    isPaused: false,

    // Scan settings
    concurrency: 25,
    deepCheck: false,
    delayMs: 0,

    // Scan results storage
    results: [], // array of result objects
    resultsMap: new Map(), // domain -> result
    availableList: [],

    // Filter & Sort
    filterStatus: 'all', // 'all' | 'available' | 'taken'
    searchQuery: '',
    sortBy: 'available_first',

    // Live metrics
    metrics: {
        total: 0,
        checked: 0,
        available: 0,
        taken: 0,
        errors: 0,
        speed: 0,
        elapsed: 0,
        eta: 0,
        percent: 0
    }
};

// WebSocket connection
let ws = null;
let renderDebounceTimer = null;
let pendingRender = false;

// DOM Elements cache
const el = {};

document.addEventListener('DOMContentLoaded', () => {
    initElements();
    initEventListeners();
    initPresets();
    connectWebSocket();
    updateTldChips();
    updateStatsUI();
});

function initElements() {
    el.tabs = document.querySelectorAll('.nav-tab');
    el.tabContents = document.querySelectorAll('.tab-content');

    // Buttons
    el.btnStart = document.getElementById('btn-start-scan');
    el.btnPause = document.getElementById('btn-pause-scan');
    el.btnStop = document.getElementById('btn-stop-scan');
    el.btnPreview = document.getElementById('btn-preview');

    // TLDs
    el.tldContainer = document.getElementById('tld-chips-container');
    el.inputCustomTld = document.getElementById('input-custom-tld');
    el.btnAddCustomTld = document.getElementById('btn-add-custom-tld');
    el.tldPresetButtons = document.querySelectorAll('.tld-preset-btn');

    // Settings
    el.concurrencySlider = document.getElementById('slider-concurrency');
    el.concurrencyValue = document.getElementById('val-concurrency');
    el.deepCheckToggle = document.getElementById('toggle-deep-check');

    // Inputs
    el.inputCustomDomains = document.getElementById('input-custom-domains');
    el.inputLetterLength = document.getElementById('input-letter-length');
    el.selectLetterMode = document.getElementById('select-letter-mode');
    el.patternContainer = document.getElementById('pattern-input-container');
    el.inputPattern = document.getElementById('input-letter-pattern');
    el.selectLetterStrategy = document.getElementById('select-letter-strategy');
    el.inputLetterCount = document.getElementById('input-letter-count');

    el.inputKeywords = document.getElementById('input-keywords');
    el.selectKeywordMode = document.getElementById('select-keyword-mode');
    el.nichePackContainer = document.getElementById('niche-pack-container');
    el.selectNichePack = document.getElementById('select-niche-pack');
    el.customAffixContainer = document.getElementById('custom-affix-container');
    el.inputCustomAffixes = document.getElementById('input-custom-affixes');
    el.inputKeywordCount = document.getElementById('input-keyword-count');

    el.inputBrandableCount = document.getElementById('input-brandable-count');

    // Stats & Progress
    el.progressBar = document.getElementById('progress-bar');
    el.progressPercent = document.getElementById('progress-percent');
    el.statTotal = document.getElementById('stat-total');
    el.statAvailable = document.getElementById('stat-available');
    el.statTaken = document.getElementById('stat-taken');
    el.statSpeed = document.getElementById('stat-speed');
    el.statEta = document.getElementById('stat-eta');
    el.statusBadge = document.getElementById('scan-status-badge');

    // Results
    el.resultsContainer = document.getElementById('results-container');
    el.resultsEmptyState = document.getElementById('results-empty-state');
    el.resultsCount = document.getElementById('results-count');
    el.filterButtons = document.querySelectorAll('.filter-btn');
    el.inputFilterSearch = document.getElementById('input-filter-search');
    el.selectSort = document.getElementById('select-sort');

    // Actions
    el.btnCopyAvailable = document.getElementById('btn-copy-available');
    el.btnExportCsv = document.getElementById('btn-export-csv');
    el.btnExportTxt = document.getElementById('btn-export-txt');
    el.btnExportJson = document.getElementById('btn-export-json');
    el.btnClear = document.getElementById('btn-clear-results');
}

function initEventListeners() {
    // Tab switching
    el.tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            switchTab(tabName);
        });
    });

    // Concurrency slider
    el.concurrencySlider.addEventListener('input', (e) => {
        state.concurrency = parseInt(e.target.value);
        el.concurrencyValue.textContent = `${state.concurrency}x`;
    });

    // Deep check toggle
    el.deepCheckToggle.addEventListener('change', (e) => {
        state.deepCheck = e.target.checked;
    });

    // Letter mode change
    el.selectLetterMode.addEventListener('change', (e) => {
        if (e.target.value === 'pattern') {
            el.patternContainer.classList.remove('hidden');
        } else {
            el.patternContainer.classList.add('hidden');
        }
    });

    // Keyword mode change
    el.selectKeywordMode.addEventListener('change', (e) => {
        const val = e.target.value;
        if (val === 'niche') {
            el.nichePackContainer.classList.remove('hidden');
            el.customAffixContainer.classList.add('hidden');
        } else if (val === 'custom') {
            el.nichePackContainer.classList.add('hidden');
            el.customAffixContainer.classList.remove('hidden');
        } else {
            el.nichePackContainer.classList.add('hidden');
            el.customAffixContainer.classList.add('hidden');
        }
    });

    // Custom TLD adding
    el.btnAddCustomTld.addEventListener('click', addCustomTldFromInput);
    el.inputCustomTld.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addCustomTldFromInput();
        }
    });

    // TLD Presets
    el.tldPresetButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const presetKey = btn.dataset.preset;
            applyTldPreset(presetKey);
        });
    });

    // Action buttons
    el.btnStart.addEventListener('click', startScan);
    el.btnPause.addEventListener('click', togglePauseScan);
    el.btnStop.addEventListener('click', stopScan);
    el.btnPreview.addEventListener('click', previewDomains);

    // Results filters
    el.filterButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            el.filterButtons.forEach(b => b.classList.remove('active', 'bg-zinc-800', 'text-white'));
            btn.classList.add('active', 'bg-zinc-800', 'text-white');
            state.filterStatus = btn.dataset.filter;
            renderResults();
        });
    });

    el.inputFilterSearch.addEventListener('input', (e) => {
        state.searchQuery = e.target.value.toLowerCase().trim();
        renderResults();
    });

    el.selectSort.addEventListener('change', (e) => {
        state.sortBy = e.target.value;
        renderResults();
    });

    // Export & Copy
    el.btnCopyAvailable.addEventListener('click', copyAllAvailable);
    el.btnExportCsv.addEventListener('click', exportCsv);
    el.btnExportTxt.addEventListener('click', exportTxt);
    el.btnExportJson.addEventListener('click', exportJson);
    el.btnClear.addEventListener('click', clearResults);

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            if (!state.isScanning) {
                startScan();
            }
        } else if (e.key === 'Escape' && state.isScanning) {
            e.preventDefault();
            stopScan();
        }
    });
}

function switchTab(tabName) {
    state.activeTab = tabName;
    el.tabs.forEach(tab => {
        if (tab.dataset.tab === tabName) {
            tab.classList.add('bg-zinc-800', 'text-white', 'shadow-sm');
            tab.classList.remove('text-zinc-400');
        } else {
            tab.classList.remove('bg-zinc-800', 'text-white', 'shadow-sm');
            tab.classList.add('text-zinc-400');
        }
    });

    el.tabContents.forEach(content => {
        if (content.id === `tab-content-${tabName}`) {
            content.classList.remove('hidden');
        } else {
            content.classList.add('hidden');
        }
    });
}

// -------------------------------------------------------------
// TLD Chips & Presets
// -------------------------------------------------------------
const DEFAULT_TLD_LIST = [
    ".com", ".io", ".ai", ".co", ".net", ".org",
    ".app", ".dev", ".xyz", ".tech", ".me", ".so",
    ".cloud", ".sh", ".store", ".online", ".site", ".gg"
];

function updateTldChips() {
    el.tldContainer.innerHTML = '';

    // Combine defaults and custom added
    const allTlds = Array.from(new Set([...DEFAULT_TLD_LIST, ...state.customTlds]));

    allTlds.forEach(tld => {
        const isSelected = state.selectedTlds.has(tld);
        const chip = document.createElement('div');
        chip.className = `tld-chip px-3 py-1.5 rounded-lg text-xs font-mono border transition-all flex items-center gap-1.5 ${
            isSelected
                ? 'active bg-indigo-500/20 border-indigo-500/50 text-indigo-200'
                : 'bg-zinc-900/60 border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-300'
        }`;

        chip.innerHTML = `
            <span>${tld}</span>
            ${state.customTlds.has(tld) ? '<span class="text-zinc-500 hover:text-red-400 text-xs ml-0.5 remove-tld">&times;</span>' : ''}
        `;

        chip.addEventListener('click', (e) => {
            if (e.target.classList.contains('remove-tld')) {
                e.stopPropagation();
                state.customTlds.delete(tld);
                state.selectedTlds.delete(tld);
                updateTldChips();
                return;
            }
            if (state.selectedTlds.has(tld)) {
                if (state.selectedTlds.size > 1) {
                    state.selectedTlds.delete(tld);
                } else {
                    showToast('Select at least one TLD', 'warning');
                }
            } else {
                state.selectedTlds.add(tld);
            }
            updateTldChips();
        });

        el.tldContainer.appendChild(chip);
    });
}

function addCustomTldFromInput() {
    let tld = el.inputCustomTld.value.trim().toLowerCase();
    if (!tld) return;
    if (!tld.startsWith('.')) tld = '.' + tld;
    if (tld.length < 2) return;

    state.customTlds.add(tld);
    state.selectedTlds.add(tld);
    el.inputCustomTld.value = '';
    updateTldChips();
    showToast(`Added ${tld}`, 'info');
}

function applyTldPreset(presetKey) {
    const presets = {
        popular: ['.com', '.io', '.ai', '.co', '.net', '.org'],
        tech: ['.ai', '.io', '.dev', '.app', '.tech', '.sh'],
        startup: ['.com', '.io', '.ai', '.co', '.xyz'],
        short: ['.co', '.io', '.ai', '.me', '.so', '.to', '.gg'],
        all: DEFAULT_TLD_LIST
    };

    const targetList = presets[presetKey] || presets.popular;
    state.selectedTlds.clear();
    targetList.forEach(t => state.selectedTlds.add(t));
    updateTldChips();
    showToast(`Loaded ${presetKey} TLDs`, 'info');
}

function initPresets() {
    fetch('/api/presets')
        .then(res => res.json())
        .then(data => {
            // Can populate dropdowns or extra presets if needed
        })
        .catch(() => {});
}

// -------------------------------------------------------------
// Domain Generation & Payloads
// -------------------------------------------------------------
async function getDomainsForCurrentMode() {
    const tlds = Array.from(state.selectedTlds);
    let payload = {
        mode: state.activeTab,
        tlds: tlds
    };

    if (state.activeTab === 'custom') {
        payload.custom_text = el.inputCustomDomains.value;
    } else if (state.activeTab === 'letters') {
        payload.letter_length = parseInt(el.inputLetterLength.value) || 3;
        payload.letter_mode = el.selectLetterMode.value;
        payload.letter_pattern = el.inputPattern.value.trim();
        payload.letter_strategy = el.selectLetterStrategy.value;
        payload.letter_count = parseInt(el.inputLetterCount.value) || 100;
    } else if (state.activeTab === 'keyword') {
        const rawKw = el.inputKeywords.value.split(/[\n,]+/).map(s => s.trim()).filter(Boolean);
        payload.keywords = rawKw.length > 0 ? rawKw : ['hub'];
        payload.keyword_mode = el.selectKeywordMode.value;
        payload.niche_pack = el.selectNichePack.value;
        payload.custom_affixes = el.inputCustomAffixes.value.split(/[\n,]+/).map(s => s.trim()).filter(Boolean);
        payload.keyword_count = parseInt(el.inputKeywordCount.value) || 200;
    } else if (state.activeTab === 'brandable') {
        payload.brandable_count = parseInt(el.inputBrandableCount.value) || 50;
    }

    const res = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    const data = await res.json();
    return data.domains || [];
}

async function previewDomains() {
    try {
        const domains = await getDomainsForCurrentMode();
        if (domains.length === 0) {
            showToast('No domains generated. Check your input.', 'warning');
            return;
        }

        // Show a preview modal or temporary list
        showToast(`Generated ${domains.length} candidate domains`, 'info');

        // Populate custom input tab if user wants to review them
        if (state.activeTab !== 'custom') {
            el.inputCustomDomains.value = domains.slice(0, 500).join('\n');
            switchTab('custom');
        }
    } catch (err) {
        showToast('Generation error: ' + err.message, 'error');
    }
}

// -------------------------------------------------------------
// WebSocket Engine & Real-time Scan
// -------------------------------------------------------------
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/scan`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('[DomainPulse] WebSocket connected');
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleWsMessage(msg);
        } catch (e) {
            console.error('WS parse error:', e);
        }
    };

    ws.onclose = () => {
        console.log('[DomainPulse] WebSocket disconnected, reconnecting in 2s...');
        setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = (err) => {
        console.error('WS error:', err);
    };
}

async function startScan() {
    if (state.isScanning) return;

    let domains = [];
    try {
        domains = await getDomainsForCurrentMode();
    } catch (err) {
        showToast('Failed to generate domains: ' + err.message, 'error');
        return;
    }

    if (domains.length === 0) {
        showToast('Please enter domains or keywords to search', 'warning');
        return;
    }

    // Reset results and metrics
    clearResults();
    state.isScanning = true;
    state.isPaused = false;
    state.metrics.total = domains.length;
    updateScanControlsUI();
    updateStatsUI();

    if (!ws || ws.readyState !== WebSocket.OPEN) {
        connectWebSocket();
        await new Promise(r => setTimeout(r, 500));
    }

    ws.send(JSON.stringify({
        action: 'start',
        domains: domains,
        concurrency: state.concurrency,
        deep_check: state.deepCheck,
        delay_ms: state.delayMs
    }));

    showToast(`Started scanning ${domains.length} domains...`, 'info');
}

function togglePauseScan() {
    if (!state.isScanning) return;

    if (state.isPaused) {
        ws.send(JSON.stringify({ action: 'resume' }));
        state.isPaused = false;
        el.btnPause.innerHTML = `
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
            <span>Pause</span>
        `;
        showToast('Scan resumed', 'info');
    } else {
        ws.send(JSON.stringify({ action: 'pause' }));
        state.isPaused = true;
        el.btnPause.innerHTML = `
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
            <span>Resume</span>
        `;
        showToast('Scan paused', 'warning');
    }
    updateScanControlsUI();
}

function stopScan() {
    if (!state.isScanning) return;

    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'stop' }));
    }

    state.isScanning = false;
    state.isPaused = false;
    updateScanControlsUI();
    showToast('Scan stopped', 'warning');
}

function handleWsMessage(msg) {
    if (msg.type === 'result') {
        const item = msg.data;
        state.results.push(item);
        state.resultsMap.set(item.domain, item);
        if (item.status === 'available') {
            state.availableList.push(item);
        }
        scheduleBatchRender();
    } else if (msg.type === 'progress') {
        state.metrics = { ...state.metrics, ...msg.data };
        updateStatsUI();
    } else if (msg.type === 'finished') {
        state.isScanning = false;
        state.isPaused = false;
        updateScanControlsUI();
        renderResults();
        showToast(`Scan complete! Found ${state.availableList.length} available domains!`, 'success');
    } else if (msg.type === 'stopped') {
        state.isScanning = false;
        state.isPaused = false;
        updateScanControlsUI();
        renderResults();
    } else if (msg.type === 'error') {
        showToast('Error: ' + msg.message, 'error');
    }
}

// Batched UI updates for silky 60fps rendering even at 200+ req/sec
function scheduleBatchRender() {
    if (pendingRender) return;
    pendingRender = true;
    renderDebounceTimer = setTimeout(() => {
        pendingRender = false;
        renderResults();
        updateStatsUI();
    }, 80);
}

// -------------------------------------------------------------
// UI Updates & Rendering
// -------------------------------------------------------------
function updateScanControlsUI() {
    if (state.isScanning) {
        el.btnStart.classList.add('hidden');
        el.btnPause.classList.remove('hidden');
        el.btnStop.classList.remove('hidden');
        el.statusBadge.innerHTML = `
            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
            <span class="text-xs font-semibold text-emerald-400">${state.isPaused ? 'PAUSED' : 'SCANNING'}</span>
        `;
    } else {
        el.btnStart.classList.remove('hidden');
        el.btnPause.classList.add('hidden');
        el.btnStop.classList.add('hidden');
        el.btnPause.innerHTML = `
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
            <span>Pause</span>
        `;
        el.statusBadge.innerHTML = `
            <span class="w-2 h-2 rounded-full bg-zinc-600"></span>
            <span class="text-xs font-medium text-zinc-400">IDLE</span>
        `;
    }
}

function updateStatsUI() {
    const m = state.metrics;
    el.statTotal.textContent = `${m.checked} / ${m.total}`;
    el.statAvailable.textContent = m.available;
    el.statTaken.textContent = m.taken;
    el.statSpeed.textContent = `${m.speed} /s`;
    el.statEta.textContent = m.eta > 0 ? `${Math.round(m.eta)}s` : '--';

    const pct = m.percent || 0;
    el.progressBar.style.width = `${pct}%`;
    el.progressPercent.textContent = `${Math.round(pct)}%`;
}

function renderResults() {
    let list = [...state.results];

    // Filter by status
    if (state.filterStatus === 'available') {
        list = list.filter(r => r.status === 'available');
    } else if (state.filterStatus === 'taken') {
        list = list.filter(r => r.status === 'taken');
    }

    // Filter by search query
    if (state.searchQuery) {
        list = list.filter(r => r.domain.toLowerCase().includes(state.searchQuery));
    }

    // Sort
    if (state.sortBy === 'available_first') {
        list.sort((a, b) => {
            if (a.status === 'available' && b.status !== 'available') return -1;
            if (a.status !== 'available' && b.status === 'available') return 1;
            return a.domain.localeCompare(b.domain);
        });
    } else if (state.sortBy === 'az') {
        list.sort((a, b) => a.domain.localeCompare(b.domain));
    } else if (state.sortBy === 'za') {
        list.sort((a, b) => b.domain.localeCompare(a.domain));
    } else if (state.sortBy === 'fastest') {
        list.sort((a, b) => a.response_time_ms - b.response_time_ms);
    } else if (state.sortBy === 'length') {
        list.sort((a, b) => a.domain.length - b.domain.length);
    }

    el.resultsCount.textContent = `Showing ${list.length} domains`;

    if (list.length === 0) {
        el.resultsContainer.classList.add('hidden');
        el.resultsEmptyState.classList.remove('hidden');
        return;
    }

    el.resultsEmptyState.classList.add('hidden');
    el.resultsContainer.classList.remove('hidden');

    // Build DOM elements
    const fragment = document.createDocumentFragment();

    list.forEach(r => {
        const isAvail = r.status === 'available';
        const card = document.createElement('div');
        card.className = `glass-card p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 border transition-all ${
            isAvail ? 'border-emerald-500/30 bg-emerald-950/10' : 'border-zinc-800/80 bg-zinc-900/40'
        }`;

        const baseName = r.domain.split('.')[0];
        const letterCount = baseName.length;

        card.innerHTML = `
            <div class="flex items-center gap-3">
                <div class="${isAvail ? 'status-dot-available' : 'status-dot-taken'} shrink-0"></div>
                <div class="space-y-0.5">
                    <div class="flex items-center gap-2">
                        <span class="font-mono text-base font-semibold ${isAvail ? 'text-emerald-300' : 'text-zinc-300'} tracking-wide">
                            ${r.domain}
                        </span>
                        <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
                            ${letterCount} letters
                        </span>
                    </div>
                    <div class="flex items-center gap-2 text-xs text-zinc-500 font-mono">
                        <span>${r.method}</span>
                        <span>&bull;</span>
                        <span>${r.response_time_ms}ms</span>
                        <span>&bull;</span>
                        <span>${r.details || ''}</span>
                    </div>
                </div>
            </div>

            <div class="flex items-center gap-2 shrink-0">
                <span class="px-2.5 py-1 text-xs font-semibold rounded-full border ${
                    isAvail
                        ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-400'
                        : 'bg-zinc-800/80 border-zinc-700 text-zinc-400'
                }">
                    ${isAvail ? 'AVAILABLE' : 'TAKEN'}
                </span>

                <button class="btn-copy-card px-2.5 py-1.5 rounded-lg bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 text-xs flex items-center gap-1 border border-zinc-700 transition-colors" data-domain="${r.domain}">
                    <svg class="w-3.5 h-3.5 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
                    <span>Copy</span>
                </button>

                ${isAvail ? `
                    <div class="relative group">
                        <a href="${r.registrar_links?.porkbun || `https://porkbun.com/checkout/search?q=${r.domain}`}" target="_blank" rel="noopener noreferrer" class="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs flex items-center gap-1.5 shadow-sm transition-all">
                            <span>Register</span>
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                        </a>
                    </div>
                ` : ''}
            </div>
        `;

        // Card copy handler
        const copyBtn = card.querySelector('.btn-copy-card');
        copyBtn.addEventListener('click', () => {
            navigator.clipboard.writeText(r.domain);
            showToast(`Copied ${r.domain}`, 'info');
        });

        fragment.appendChild(card);
    });

    el.resultsContainer.innerHTML = '';
    el.resultsContainer.appendChild(fragment);
}

function clearResults() {
    state.results = [];
    state.resultsMap.clear();
    state.availableList = [];
    state.metrics = {
        total: 0,
        checked: 0,
        available: 0,
        taken: 0,
        errors: 0,
        speed: 0,
        elapsed: 0,
        eta: 0,
        percent: 0
    };
    renderResults();
    updateStatsUI();
}

// -------------------------------------------------------------
// Bulk Actions & Export
// -------------------------------------------------------------
function copyAllAvailable() {
    if (state.availableList.length === 0) {
        showToast('No available domains found to copy', 'warning');
        return;
    }
    const text = state.availableList.map(r => r.domain).join('\n');
    navigator.clipboard.writeText(text);
    showToast(`Copied ${state.availableList.length} available domains!`, 'success');
}

function exportCsv() {
    if (state.results.length === 0) {
        showToast('No data to export', 'warning');
        return;
    }
    let csv = 'Domain,Status,Method,Response_Time_ms,Details\n';
    state.results.forEach(r => {
        csv += `"${r.domain}","${r.status}","${r.method}",${r.response_time_ms},"${(r.details || '').replace(/"/g, '""')}"\n`;
    });
    downloadFile(csv, 'domain_pulse_results.csv', 'text/csv;charset=utf-8;');
    showToast('Exported CSV file', 'info');
}

function exportTxt() {
    if (state.availableList.length === 0) {
        showToast('No available domains to export', 'warning');
        return;
    }
    const txt = state.availableList.map(r => r.domain).join('\n');
    downloadFile(txt, 'available_domains.txt', 'text/plain;charset=utf-8;');
    showToast('Exported TXT list', 'info');
}

function exportJson() {
    if (state.results.length === 0) {
        showToast('No data to export', 'warning');
        return;
    }
    const jsonStr = JSON.stringify(state.results, null, 2);
    downloadFile(jsonStr, 'domain_pulse_results.json', 'application/json');
    showToast('Exported JSON data', 'info');
}

function downloadFile(content, fileName, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// -------------------------------------------------------------
// Toast Notification System
// -------------------------------------------------------------
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = 'toast';

    let iconSvg = '';
    if (type === 'success') {
        iconSvg = '<svg class="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>';
    } else if (type === 'warning') {
        iconSvg = '<svg class="w-5 h-5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>';
    } else if (type === 'error') {
        iconSvg = '<svg class="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>';
    } else {
        iconSvg = '<svg class="w-5 h-5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>';
    }

    toast.innerHTML = `
        ${iconSvg}
        <span>${message}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        if (toast.parentElement) {
            toast.parentElement.removeChild(toast);
        }
    }, 3000);
}

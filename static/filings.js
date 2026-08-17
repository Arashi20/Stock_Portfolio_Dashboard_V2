// 13F Filings Page JavaScript

// Holdings are fetched from /api/13f/<fund_key> rather than rendered server-side:
// a lookup makes several SEC round-trips, so this keeps the page responsive and
// avoids tying up a gunicorn worker for the duration.

let currentSnapshot = null;
let activeFilter = 'ALL';

function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function formatValue(value) {
    if (value >= 1e9) return '$' + (value / 1e9).toFixed(2) + 'B';
    if (value >= 1e6) return '$' + (value / 1e6).toFixed(2) + 'M';
    if (value >= 1e3) return '$' + (value / 1e3).toFixed(0) + 'K';
    return '$' + value.toLocaleString();
}

function formatQuarter(dateStr) {
    if (!dateStr) return '';
    const [year, month] = dateStr.split('-');
    const quarter = { '03': 'Q1', '06': 'Q2', '09': 'Q3', '12': 'Q4' }[month] || dateStr;
    return `${quarter} ${year}`;
}

function tickerCell(holding) {
    if (!holding.ticker) {
        // No US listing matched -- the SEC issuer name is all we can show.
        return '<span class="ticker-missing" title="No US ticker matched for this CUSIP">&mdash;</span>';
    }
    // Share classes come back from OpenFIGI slash-separated (BRK/B) while Yahoo
    // uses a hyphen (BRK-B), so the link needs converting even though the
    // filing's own spelling is what gets displayed.
    const yahooSymbol = holding.ticker.replace(/\//g, '-');
    return `<a href="https://finance.yahoo.com/quote/${encodeURIComponent(yahooSymbol)}"
               target="_blank" rel="noopener" class="ticker-link">${escapeHtml(holding.ticker)}
               <i class="fas fa-external-link-alt"></i></a>`;
}

function statusBadge(holding) {
    if (!holding.status) return '<span class="change-badge badge-held">&mdash;</span>';

    const change = holding.share_change_pct;
    const labels = {
        NEW: 'New',
        ADDED: 'Added',
        TRIMMED: 'Trimmed',
        HELD: 'Held',
        EXITED: 'Exited'
    };
    const suffix = (holding.status === 'ADDED' || holding.status === 'TRIMMED') && change !== null
        ? ` ${change > 0 ? '+' : ''}${change}%`
        : '';

    return `<span class="change-badge badge-${holding.status.toLowerCase()}">${labels[holding.status]}${suffix}</span>`;
}

function holdingsRows(holdings) {
    if (!holdings.length) {
        return '<tr><td colspan="6" class="filings-no-match">No positions match this filter.</td></tr>';
    }

    return holdings.map(holding => `
        <tr>
            <td><strong>${tickerCell(holding)}</strong></td>
            <td class="issuer-cell">${escapeHtml(holding.issuer)}
                ${holding.put_call ? `<span class="put-call-tag">${escapeHtml(holding.put_call)}</span>` : ''}
            </td>
            <td>${holding.weight_pct === null ? '&mdash;' : holding.weight_pct.toFixed(2) + '%'}</td>
            <td>${formatValue(holding.value)}</td>
            <td>${holding.shares.toLocaleString()}</td>
            <td>${statusBadge(holding)}</td>
        </tr>
    `).join('');
}

function filteredHoldings() {
    if (activeFilter === 'ALL') return currentSnapshot.holdings;
    return currentSnapshot.holdings.filter(h => h.status === activeFilter);
}

function renderTable() {
    const tbody = document.getElementById('holdingsBody');
    if (tbody) tbody.innerHTML = holdingsRows(filteredHoldings());

    document.querySelectorAll('.filings-filter').forEach(button => {
        button.classList.toggle('active', button.dataset.filter === activeFilter);
    });
}

function filterButton(label, filter, count) {
    const disabled = count === 0 && filter !== 'ALL';
    return `<button type="button" class="filings-filter ${filter === activeFilter ? 'active' : ''}"
                    data-filter="${filter}" ${disabled ? 'disabled' : ''}>
                ${label}${count === null ? '' : ` (${count})`}
            </button>`;
}

function renderSnapshot(snapshot) {
    currentSnapshot = snapshot;
    activeFilter = 'ALL';

    const counts = snapshot.counts || {};
    const hasDiff = Boolean(snapshot.prior_quarter);

    const exitedSection = snapshot.exited.length ? `
        <div class="section-card filings-exited-card">
            <h2 class="section-heading">
                <i class="fas fa-arrow-right-from-bracket"></i>
                Sold Out Completely (${snapshot.exited.length})
            </h2>
            <p class="filings-note">Held in ${formatQuarter(snapshot.prior_quarter)}, gone by ${formatQuarter(snapshot.quarter)}.</p>
            <div class="table-responsive">
                <table class="filings-table">
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>Company</th>
                            <th>Weight</th>
                            <th>Prior Value</th>
                            <th>Prior Shares</th>
                            <th>Change</th>
                        </tr>
                    </thead>
                    <tbody>${holdingsRows(snapshot.exited)}</tbody>
                </table>
            </div>
        </div>` : '';

    document.getElementById('filingsResults').innerHTML = `
        <div class="section-card filings-summary-card">
            <div class="filings-summary">
                <div class="filings-summary-main">
                    <h2 class="filings-fund-name">${escapeHtml(snapshot.name)}</h2>
                    <p class="filings-fund-meta">
                        ${formatQuarter(snapshot.quarter)} holdings &middot;
                        filed ${escapeHtml(snapshot.filed)} &middot;
                        CIK ${escapeHtml(snapshot.cik)}
                        ${snapshot.is_amendment ? ' &middot; <span class="amendment-tag">amended filing</span>' : ''}
                    </p>
                </div>
                <div class="filings-stats">
                    <div class="filings-stat">
                        <span class="filings-stat-value">${snapshot.position_count}</span>
                        <span class="filings-stat-label">Positions</span>
                    </div>
                    <div class="filings-stat">
                        <span class="filings-stat-value">${formatValue(snapshot.total_value)}</span>
                        <span class="filings-stat-label">Reported Value</span>
                    </div>
                    <div class="filings-stat">
                        <span class="filings-stat-value">${hasDiff ? counts.new : '&mdash;'}</span>
                        <span class="filings-stat-label">New Buys</span>
                    </div>
                    <div class="filings-stat">
                        <span class="filings-stat-value">${hasDiff ? counts.exited : '&mdash;'}</span>
                        <span class="filings-stat-label">Sold Out</span>
                    </div>
                </div>
            </div>
        </div>

        <div class="section-card">
            <h2 class="section-heading">
                <i class="fas fa-list"></i>
                Holdings (${snapshot.position_count})
            </h2>
            ${hasDiff
                ? `<p class="filings-note">Changes measured against ${formatQuarter(snapshot.prior_quarter)}. A company that changed CUSIP through a spin-off or merger shows up as one position exited and another bought.</p>`
                : '<p class="filings-note">No prior quarter available, so no position changes are shown.</p>'}
            <div class="filings-filters">
                ${filterButton('All', 'ALL', null)}
                ${hasDiff ? filterButton('New buys', 'NEW', counts.new) : ''}
                ${hasDiff ? filterButton('Added', 'ADDED', counts.added) : ''}
                ${hasDiff ? filterButton('Trimmed', 'TRIMMED', counts.trimmed) : ''}
            </div>
            <div class="table-responsive">
                <table class="filings-table">
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>Company</th>
                            <th>Weight</th>
                            <th>Value</th>
                            <th>Shares</th>
                            <th>vs Prior Quarter</th>
                        </tr>
                    </thead>
                    <tbody id="holdingsBody">${holdingsRows(snapshot.holdings)}</tbody>
                </table>
            </div>
        </div>

        ${exitedSection}
    `;

    document.querySelectorAll('.filings-filter').forEach(button => {
        button.addEventListener('click', function () {
            activeFilter = this.dataset.filter;
            renderTable();
        });
    });
}

async function loadFund(cik, fundLabel) {
    const results = document.getElementById('filingsResults');
    results.innerHTML = `<div class="section-card"><div class="loading">
        <i class="fas fa-spinner fa-spin"></i> Fetching ${escapeHtml(fundLabel)} filings from SEC...
    </div></div>`;

    try {
        const response = await fetch(`/api/13f/cik/${encodeURIComponent(cik)}`);
        const data = await response.json();

        if (!response.ok || data.error) {
            results.innerHTML = `<div class="section-card">
                <div class="alert alert-danger"><span>${escapeHtml(data.error || 'Could not load filings.')}</span></div>
            </div>`;
            return;
        }

        renderSnapshot(data);
    } catch (error) {
        results.innerHTML = `<div class="section-card">
            <div class="alert alert-danger"><span>Error fetching filings. Check your connection and try again.</span></div>
        </div>`;
    }
}

document.addEventListener('DOMContentLoaded', function () {
    const searchInput = document.getElementById('fundSearch');
    const searchResults = document.getElementById('searchResults');

    if (!searchInput) return;

    let searchTimer = null;
    let matches = [];

    function closeResults() {
        searchResults.innerHTML = '';
        searchResults.classList.remove('active');
    }

    function pick(index) {
        const match = matches[index];
        if (!match) return;
        searchInput.value = match.name;
        closeResults();
        loadFund(match.cik, match.name);
    }

    function renderResults() {
        if (!matches.length) {
            searchResults.innerHTML = '<div class="filings-search-empty">No funds match. They file under legal entity names &mdash; Greenlight is "DME Capital Management", for instance.</div>';
            searchResults.classList.add('active');
            return;
        }

        searchResults.innerHTML = matches.map((match, index) => `
            <button type="button" class="filings-search-item" data-index="${index}">
                <span class="filings-search-name">${escapeHtml(match.name)}</span>
                <span class="filings-search-cik">CIK ${escapeHtml(match.cik)}</span>
            </button>
        `).join('');
        searchResults.classList.add('active');

        searchResults.querySelectorAll('.filings-search-item').forEach(item => {
            item.addEventListener('click', () => pick(Number(item.dataset.index)));
        });
    }

    searchInput.addEventListener('input', function () {
        clearTimeout(searchTimer);
        const query = this.value.trim();

        if (query.length < 2) {
            closeResults();
            return;
        }

        // Debounced so typing doesn't fire a request per keystroke.
        searchTimer = setTimeout(async function () {
            try {
                const response = await fetch(`/api/13f/search?q=${encodeURIComponent(query)}`);
                const data = await response.json();
                matches = data.results || [];
                renderResults();
            } catch (error) {
                closeResults();
            }
        }, 200);
    });

    searchInput.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            pick(0);
        } else if (event.key === 'Escape') {
            closeResults();
        }
    });

    document.addEventListener('click', function (event) {
        if (!event.target.closest('.filings-search-group')) closeResults();
    });

    document.querySelectorAll('.filings-chip').forEach(chip => {
        chip.addEventListener('click', function () {
            searchInput.value = this.dataset.name;
            closeResults();
            loadFund(this.dataset.cik, this.dataset.name);
        });
    });
});

// DCF Page JavaScript

// Stock lookup functionality
document.addEventListener('DOMContentLoaded', function() {
    const lookupBtn = document.getElementById('lookupBtn');
    const resetBtn = document.getElementById('resetBtn');
    const dcfForm = document.getElementById('dcfForm');
    
    if (lookupBtn) {
        lookupBtn.addEventListener('click', async function() {
            const ticker = document.getElementById('ticker').value.toUpperCase();
            const stockInfo = document.getElementById('stockInfo');
            
            if (!ticker) {
                stockInfo.innerHTML = '<div class="alert alert-warning">Please enter a ticker symbol</div>';
                return;
            }
            
            stockInfo.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Fetching data...</div>';
            
            try {
                const response = await fetch(`/api/stock-lookup/${ticker}`);
                const data = await response.json();
                
                if (data.error) {
                    stockInfo.innerHTML = `<div class="alert alert-danger">${data.error}</div>`;
                } else {
                    // Display saved DCF analyses
                    let html = `
                        <div class="saved-analyses">
                            <h3>Saved Analyses for ${data.ticker} (${data.count})</h3>
                            <div class="analyses-list">
                    `;
                    
                    data.analyses.forEach((analysis, index) => {
                        html += `
                            <div class="analysis-card" data-index="${index}">
                                <div class="analysis-header">
                                    <span class="analysis-date">${analysis.date}</span>
                                    <span class="analysis-value">${analysis.currency}${analysis.intrinsic_value.toFixed(2)}</span>
                                </div>
                                <div class="analysis-details">
                                    <span>FCF: ${analysis.free_cash_flow.toLocaleString()}</span>
                                    <span>Shares: ${analysis.shares_outstanding.toLocaleString()}</span>
                                    <span>Growth: ${analysis.growth_rate_5yr}%/${analysis.growth_rate_6_10yr}%</span>
                                </div>
                                <button class="btn-load-analysis" onclick="loadAnalysis(${index})">
                                    <i class="fas fa-upload"></i> Load This Analysis
                                </button>
                            </div>
                        `;
                    });
                    
                    html += `
                            </div>
                        </div>
                    `;
                    
                    stockInfo.innerHTML = html;
                    
                    // Store analyses data globally for loading
                    window.savedAnalyses = data.analyses;
                }
            } catch (error) {
                stockInfo.innerHTML = '<div class="alert alert-danger">Error fetching stock data</div>';
            }
        });
    }
    
    // Reset form
    if (resetBtn) {
        resetBtn.addEventListener('click', function() {
            dcfForm.reset();
            document.getElementById('stockInfo').innerHTML = '';
        });
    }
    
    // Tooltip functionality
    document.querySelectorAll('.tooltip-icon').forEach(icon => {
        icon.addEventListener('mouseenter', function() {
            const tooltip = this.getAttribute('data-tooltip');
            const tooltipEl = document.createElement('div');
            tooltipEl.className = 'tooltip-popup';
            tooltipEl.textContent = tooltip;
            this.appendChild(tooltipEl);
        });
        
        icon.addEventListener('mouseleave', function() {
            const tooltipEl = this.querySelector('.tooltip-popup');
            if (tooltipEl) tooltipEl.remove();
        });
    });
});

// Function to load a saved analysis into the form
function loadAnalysis(index) {
    const analysis = window.savedAnalyses[index];
    
    // Fill form fields
    document.getElementById('free_cash_flow').value = analysis.free_cash_flow;
    document.getElementById('shares_outstanding').value = analysis.shares_outstanding;
    document.getElementById('growth_rate_5yr').value = analysis.growth_rate_5yr;
    document.getElementById('growth_rate_6_10yr').value = analysis.growth_rate_6_10yr;
    document.getElementById('terminal_growth_rate').value = analysis.terminal_growth_rate;
    document.getElementById('discount_rate').value = analysis.discount_rate;
    document.getElementById('share_dilution').value = analysis.share_dilution;
    document.getElementById('currency').value = analysis.currency;
    
    // Show success message
    document.getElementById('stockInfo').innerHTML = `
        <div class="alert alert-success">
            <i class="fas fa-check-circle"></i> Analysis from ${analysis.date} loaded successfully!
        </div>
    `;
}

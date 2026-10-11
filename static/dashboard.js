const money = value => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(value || 0);
const query = id => document.getElementById(id);
let chartType = 'bar';
let showInvestments = false;
let showIncome = false;
let showYearInvestments = false;
let showYearIncome = false;
let latestData = null;
let records = [];
let currentPage = 1;
const recordsPerPage = 10;

query('file').addEventListener('change', event => {
    const file = event.target.files[0];
    if (file) query('file-label').textContent = file.name;
});

function baseQuery() {
    const params = new URLSearchParams();
    ['start', 'end', 'group', 'payment'].forEach(id => { if (query(id).value) params.set(id, query(id).value); });
    if (query('year-start').value) params.set('year_start', query('year-start').value);
    if (query('year-end').value) params.set('year_end', query('year-end').value);
    return params;
}

function plot(id, data, layout) {
    const styles = getComputedStyle(document.body);
    const muted = styles.getPropertyValue('--muted').trim();
    const line = styles.getPropertyValue('--line').trim();
    const surface = styles.getPropertyValue('--white').trim();
    Plotly.react(id, data, { ...layout, responsive: true, displayModeBar: false, font: { family: 'DM Sans', color: muted }, paper_bgcolor: surface, plot_bgcolor: surface, xaxis: { ...layout.xaxis, color: muted }, yaxis: { ...layout.yaxis, color: muted, gridcolor: line } }, { responsive: true });
}

function renderYearChart(data) {
    const yearColors = { expense: '#1e7565', investment: '#d6a928', income: '#79ae85' };
    const trace = (name, values, color) => ({ x: data.years, y: values, type: 'bar', name, marker: { color }, hovertemplate: '%{x}<br><b>₹%{y:,.0f}</b><extra></extra>' });
    const chartData = [trace('Expense', data.yearly_expenses, yearColors.expense)];
    if (showYearInvestments && data.investment_available) chartData.push(trace('Investment', data.yearly_investments, yearColors.investment));
    if (showYearIncome && data.income_available) chartData.push(trace('Income', data.yearly_income, yearColors.income));
    plot('year-chart', chartData, { barmode: 'group', margin: { t: 12, r: 20, b: 45, l: 58 }, xaxis: { fixedrange: true }, yaxis: { tickprefix: '₹', fixedrange: true }, showlegend: true, legend: { orientation: 'h', y: 1.12, x: 0 } });
}

function render(data) {
    latestData = data;
    query('empty-state').classList.toggle('hidden', !data.empty || data.has_data);
    query('dashboard').classList.toggle('hidden', data.empty || !activeViewIs('overview'));
    query('transactions-view').classList.toggle('hidden', data.empty || !activeViewIs('transactions'));
    if (data.empty) return;
    query('total').textContent = money(data.total);
    query('average').textContent = money(data.average);
    query('peak-month').textContent = data.peak_month;
    query('peak-amount').textContent = `${money(data.peak_amount)} spent`;
    query('top-group').textContent = data.group_labels[0] || '—';
    query('top-group-amount').textContent = data.group_values[0] ? `${money(data.group_values[0])} spent` : 'No category data';
    query('date-caption').textContent = `${data.start} — ${data.end}`;
    records = data.records || [];
    currentPage = 1;

    const investmentToggle = query('show-investments');
    investmentToggle.disabled = !data.investment_available;
    investmentToggle.title = data.investment_available ? '' : 'No investment sheet found';
    if (!data.investment_available) showInvestments = false;
    const incomeToggle = query('show-income');
    incomeToggle.disabled = !data.income_available;
    incomeToggle.title = data.income_available ? '' : 'No income sheet found';
    if (!data.income_available) showIncome = false;
    incomeToggle.checked = showIncome;
    const yearInvestmentToggle = query('show-year-investments');
    yearInvestmentToggle.disabled = !data.investment_available;
    if (!data.investment_available) showYearInvestments = false;
    const yearIncomeToggle = query('show-year-income');
    yearIncomeToggle.disabled = !data.income_available;
    if (!data.income_available) showYearIncome = false;
    yearIncomeToggle.checked = showYearIncome;
    const trend = { x: data.months, y: data.monthly, type: chartType, mode: chartType === 'scatter' ? 'lines+markers' : undefined, name: 'Expense', marker: { color: '#1e7565', line: { color: '#1e7565', width: 1 } }, line: { color: '#1e7565', width: 3, shape: 'spline' }, hovertemplate: '%{x}<br><b>₹%{y:,.0f}</b><extra></extra>' };
    const chartData = [trend];
    if (showInvestments && data.investment_available) chartData.push({ x: data.months, y: data.investment_monthly, type: chartType, mode: chartType === 'scatter' ? 'lines+markers' : undefined, name: 'Investment', marker: { color: '#ef8354', line: { color: '#ef8354', width: 1 } }, line: { color: '#ef8354', width: 3, shape: 'spline' }, hovertemplate: '%{x}<br><b>₹%{y:,.0f}</b><extra></extra>' });
    if (showIncome && data.income_available) chartData.push({ x: data.income_months, y: data.income_monthly, type: chartType, mode: chartType === 'scatter' ? 'lines+markers' : undefined, name: 'Income', marker: { color: '#4f7cac', line: { color: '#4f7cac', width: 1 } }, line: { color: '#4f7cac', width: 3, shape: 'spline' }, hovertemplate: '%{x}<br><b>₹%{y:,.0f}</b><extra></extra>' });
    plot('trend-chart', chartData, { margin: { t: 10, r: 20, b: 40, l: 55 }, xaxis: { showgrid: false, fixedrange: true }, yaxis: { gridcolor: '#e8ece9', tickprefix: '₹', fixedrange: true }, showlegend: showInvestments || showIncome, legend: { orientation: 'h', y: 1.08, x: 0 }, paper_bgcolor: 'transparent', plot_bgcolor: 'transparent' });
    renderYearChart(data);
    plot('group-chart', [{ labels: data.group_labels, values: data.group_values, type: 'pie', hole: .68, textinfo: 'none', hovertemplate: '%{label}<br><b>₹%{value:,.0f}</b><extra></extra>', marker: { colors: ['#1e7565', '#ef8354', '#f2c14e', '#7087a1', '#b86b77', '#8cc0a8'] } }], { margin: { t: 5, r: 5, b: 5, l: 5 }, showlegend: true, legend: { orientation: 'h', y: -.05, x: 0, font: { size: 11 } }, paper_bgcolor: 'transparent' });
    plot('payment-chart', [{ x: data.payment_values, y: data.payment_labels, type: 'bar', orientation: 'h', marker: { color: '#ef8354' }, hovertemplate: '%{y}<br><b>₹%{x:,.0f}</b><extra></extra>' }], { margin: { t: 5, r: 20, b: 30, l: 90 }, xaxis: { showgrid: true, gridcolor: '#e8ece9', tickprefix: '₹', fixedrange: true }, yaxis: { fixedrange: true }, paper_bgcolor: 'transparent', plot_bgcolor: 'transparent' });
    query('ranking').innerHTML = data.group_labels.map((label, index) => `<div class="rank-row"><span class="rank-number">${String(index + 1).padStart(2, '0')}</span><span class="rank-label">${label}</span><strong>${money(data.group_values[index])}</strong></div>`).join('');
    renderRecords();
}

function activeViewIs(view) {
    return document.querySelector(`.side-item[data-view="${view}"]`)?.classList.contains('active');
}

function switchView(view) {
    document.querySelectorAll('.side-item[data-view]').forEach(item => item.classList.toggle('active', item.dataset.view === view));
    document.querySelectorAll('[data-view-panel]').forEach(panel => panel.classList.toggle('hidden', panel.dataset.viewPanel !== view));
}

function renderRecords() {
    const search = query('record-search').value.trim().toLowerCase();
    const filtered = records.filter(record => Object.values(record).join(' ').toLowerCase().includes(search));
    const filteredTotal = filtered.reduce((total, record) => total + (Number(record.Amount) || 0), 0);
    const pageCount = Math.max(1, Math.ceil(filtered.length / recordsPerPage));
    currentPage = Math.min(currentPage, pageCount);
    const page = filtered.slice((currentPage - 1) * recordsPerPage, currentPage * recordsPerPage);
    query('records-body').innerHTML = page.map(record => `<tr><td>${record.Date}</td><td><strong>${record.Expense || '—'}</strong></td><td><span class="category-tag">${record.ExpenseGroup}</span></td><td>${record.PaymentGroup}</td><td class="remark-cell">${record.Remark || '—'}</td><td class="amount-cell"><strong>${money(record.Amount)}</strong></td></tr>`).join('') || '<tr><td colspan="6" class="no-records">No matching records</td></tr>';
    query('record-count').textContent = `${filtered.length} record${filtered.length === 1 ? '' : 's'}`;
    query('records-total').textContent = money(filteredTotal);
    query('page-number').textContent = `${currentPage} / ${pageCount}`;
    query('previous-page').disabled = currentPage === 1;
    query('next-page').disabled = currentPage === pageCount;
}

async function refresh() {
    const response = await fetch(`/api/dashboard?${baseQuery()}`);
    const data = await response.json();
    if (data.error) { query('empty-state').classList.remove('hidden'); query('dashboard').classList.add('hidden'); return; }
    ['group', 'payment'].forEach((id, i) => {
        const values = i ? data.payments : data.groups;
        const current = query(id).value;
        query(id).innerHTML = `<option value="">All ${i ? 'payments' : 'categories'}</option>` + values.map(value => `<option value="${value}">${value}</option>`).join('');
        query(id).value = current;
    });
    if (!query('start').value) query('start').value = data.start;
    if (!query('end').value) query('end').value = data.end;
    const yearOptions = Array.from({ length: data.available_year_end - data.available_year_start + 1 }, (_, index) => data.available_year_start + index);
    ['year-start', 'year-end'].forEach(id => {
        const current = Number(query(id).value);
        query(id).innerHTML = yearOptions.map(year => `<option value="${year}">${year}</option>`).join('');
        query(id).value = String(current || data[id === 'year-start' ? 'year_start' : 'year_end']);
    });
    render(data);
}

['start', 'end', 'group', 'payment'].forEach(id => query(id).addEventListener('change', refresh));
['year-start', 'year-end'].forEach(id => query(id).addEventListener('change', refresh));
query('reset').addEventListener('click', () => { ['start', 'end', 'group', 'payment', 'year-start', 'year-end'].forEach(id => query(id).value = ''); refresh(); });
query('record-search').addEventListener('input', () => { currentPage = 1; renderRecords(); });
query('previous-page').addEventListener('click', () => { currentPage -= 1; renderRecords(); });
query('next-page').addEventListener('click', () => { currentPage += 1; renderRecords(); });
document.querySelectorAll('.side-item[data-view]').forEach(item => item.addEventListener('click', () => {
    switchView(item.dataset.view);
    if (item.dataset.view === 'transactions') renderRecords();
}));
document.querySelectorAll('.chart-toggle').forEach(button => button.addEventListener('click', () => { document.querySelectorAll('.chart-toggle').forEach(item => item.classList.remove('active')); button.classList.add('active'); chartType = button.dataset.type; refresh(); }));
query('show-investments').addEventListener('change', event => { showInvestments = event.target.checked; if (latestData) render(latestData); });
query('show-income').addEventListener('change', event => { showIncome = event.target.checked; if (latestData) render(latestData); });
query('show-year-investments').addEventListener('change', event => { showYearInvestments = event.target.checked; if (latestData) render(latestData); });
query('show-year-income').addEventListener('change', event => { showYearIncome = event.target.checked; if (latestData) render(latestData); });
const savedTheme = localStorage.getItem('ledgerline-theme') || 'light';
document.body.dataset.theme = savedTheme;
query('theme-toggle').textContent = savedTheme === 'dark' ? '☀' : '◐';
query('theme-toggle').addEventListener('click', () => {
    const theme = document.body.dataset.theme === 'dark' ? 'light' : 'dark';
    document.body.dataset.theme = theme;
    localStorage.setItem('ledgerline-theme', theme);
    query('theme-toggle').textContent = theme === 'dark' ? '☀' : '◐';
    if (latestData) render(latestData);
});
refresh();

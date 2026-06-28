import '../styles/main.css';

let shiftChart, hourlyChart;

function renderCharts(data) {
  const { shiftPerf, hourlyDensity, compliance, dayHits, nightHits, criticalAlerts } = data;

  // Shift Chart
  const ctxShift = document.getElementById('shiftChart')?.getContext('2d');
  if (ctxShift) {
    if (shiftChart) shiftChart.destroy();
    const compareActive = document.getElementById('compareToggle')?.checked;
    const datasets = [
      { label: 'On-Time', data: [shiftPerf.Day.onTime, shiftPerf.Night.onTime], backgroundColor: '#4caf50', borderRadius: 8 },
      { label: 'Violations', data: [shiftPerf.Day.late, shiftPerf.Night.late], backgroundColor: '#d32f2f', borderRadius: 8 }
    ];
    if (compareActive) {
      datasets.push({ label: 'Previous On-Time', data: [0, 0], backgroundColor: 'rgba(76,175,80,0.15)', borderRadius: 8 });
      datasets.push({ label: 'Previous Violations', data: [0, 0], backgroundColor: 'rgba(211,47,47,0.15)', borderRadius: 8 });
    }
    shiftChart = new Chart(ctxShift, {
      type: 'bar',
      data: { labels: ['Day Shift', 'Night Shift'], datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: { y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' } }, x: { grid: { display: false } } },
        plugins: { legend: { position: 'bottom', labels: { color: '#a0a0b0', boxWidth: 12, font: { size: 10, weight: '800' } } } }
      }
    });
  }

  // Hourly Chart
  const ctxHour = document.getElementById('hourlyChart')?.getContext('2d');
  if (ctxHour) {
    if (hourlyChart) hourlyChart.destroy();
    const labels = Array.from({ length: 24 }, (_, i) => i + ':00');
    const datasets = [{
      label: 'Scans', data: hourlyDensity, borderColor: '#ff6659', tension: 0.4,
      fill: true, backgroundColor: 'rgba(211,47,47,0.1)', pointRadius: 0
    }];
    if (document.getElementById('compareToggle')?.checked) {
      datasets.push({
        label: 'Benchmark', data: Array(24).fill(0), borderColor: 'rgba(255,255,255,0.1)',
        tension: 0.4, borderDash: [5, 5], pointRadius: 0
      });
    }
    hourlyChart = new Chart(ctxHour, {
      type: 'line', data: { labels, datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { display: false }, x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { font: { size: 8 } } } }
      }
    });
  }

  // Heatmap Grid
  const hGrid = document.getElementById('heatmapGrid');
  if (hGrid) {
    hGrid.innerHTML = Array(28).fill(0).map(() => {
      const val = Math.random();
      return `<div class="grid-cell ${val > 0.7 ? 'high' : val > 0.4 ? 'med' : ''}"></div>`;
    }).join('');
  }
}

function loadChartData() {
  const src = document.getElementById('chart-data-src');
  if (!src) return;
  const raw = src.getAttribute('data-chart');
  if (!raw) return;
  try {
    const data = JSON.parse(raw);
    renderCharts(data);
  } catch (e) {
    console.warn('Failed to parse chart data', e);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const today = new Date().toISOString().split('T')[0];
  const dateInp = document.getElementById('intelDate');
  if (dateInp) dateInp.value = today;
});

document.body.addEventListener('htmx:afterSwap', (e) => {
  if (e.detail?.target?.id === 'incidents-content') {
    loadChartData();
    // Re-enable pill active states after htmx swap
    document.querySelectorAll('.intel-pill').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.intel-pill[value="day"]').forEach(p => p.classList.add('active'));
  }
});

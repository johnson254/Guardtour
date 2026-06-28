import '../styles/main.css';
import { $ } from '../utils/dom.js';

// Reports page — filter dropdowns and table are handled by htmx.
// This module only handles PDF/CSV export which requires client-side jsPDF.

window.exportFullPDF = async function() {
  const params = new URLSearchParams();
  const startDate = $('startDate')?.value;
  const endDate = $('endDate')?.value;
  const guardId = $('filterGuard')?.value;
  const routeId = $('filterRoute')?.value;
  const status = $('filterStatus')?.value;
  if (startDate) params.append('start_date', startDate);
  if (endDate) params.append('end_date', endDate);
  if (guardId) params.append('guard_id', guardId);
  if (routeId) params.append('route_id', routeId);
  if (status) params.append('is_on_time', status);

  try {
    const res = await window.apiFetch(`/api/scans/?${params.toString()}`);
    if (!res.ok) throw new Error('Failed to fetch scan data for PDF');
    const scans = await res.json();
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF();
    const headers = [['Timestamp', 'Guard', 'Checkpoint', 'Route', 'Status']];
    const data = scans.map(s => [
      new Date(s.timestamp).toLocaleString(),
      s.user_name || 'Unknown',
      s.checkpoint_name || 'N/A',
      s.route_name || 'N/A',
      s.is_on_time ? 'On Time' : 'Late'
    ]);
    doc.autoTable({ head: headers, body: data });
    doc.save('patrol_report.pdf');
  } catch (error) {
    console.error('PDF export error:', error);
    alert('Failed to export PDF. Please try again.');
  }
};

window.exportCSV = function() {
  alert('CSV Export Feature\n\nThis would export the current filtered report data to a CSV file.');
};

// Set default date range on load
document.addEventListener('DOMContentLoaded', function() {
  const today = new Date().toISOString().split('T')[0];
  const endDate = $('endDate');
  if (endDate) endDate.value = today;
  const startDate = new Date();
  startDate.setDate(startDate.getDate() - 30);
  const startEl = $('startDate');
  if (startEl) startEl.value = startDate.toISOString().split('T')[0];
});

const $ = (s) => document.querySelector(s);
const form = $('#source-form');
let chart;

document.querySelectorAll('.tab').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  button.classList.add('active');
  const upload = button.dataset.tab === 'upload';
  $('#source-type').value = upload ? 'upload' : 'camera';
  $('#camera-fields').hidden = upload;
  $('#upload-fields').hidden = !upload;
}));

form?.addEventListener('submit', async event => {
  event.preventDefault();
  $('#status-message').textContent = 'Opening video source…';
  try {
    const response = await fetch('/api/start', {method:'POST', body:new FormData(form)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not start analysis.');
    $('#feed').src = `/video_feed?t=${Date.now()}`;
    $('.feed').classList.add('active');
  } catch (error) { $('#status-message').textContent = error.message; }
});

$('#stop')?.addEventListener('click', async () => { await fetch('/api/stop', {method:'POST'}); });

function renderChart(history) {
  if (!window.Chart || !history.length) return;
  $('#chart-empty').style.display = 'none';
  const labels = history.map(x => new Date(x.timestamp).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'}));
  const values = history.map(x => x.passed_count || 0);
  if (chart) { chart.data.labels=labels; chart.data.datasets[0].data=values; chart.update('none'); return; }
  chart = new Chart($('#chart'), {type:'line',data:{labels,datasets:[{label:'Total vehicles passed',data:values,borderColor:'#146df5',backgroundColor:'#146df51c',fill:true,tension:.25,pointRadius:2,stepped:true}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:true,position:'top'}},scales:{y:{beginAtZero:true,ticks:{precision:0},grid:{color:'#eaf0f4'}},x:{grid:{display:false}}}}});
}

async function refresh() {
  try {
    const state = await (await fetch('/api/status')).json();
    if ($('#vehicles')) $('#vehicles').textContent = state.vehicle_count;
    if ($('#vehicle-types')) {
      const types = Object.entries(state.vehicle_types || {});
      $('#vehicle-types').innerHTML = types.length
        ? types.map(([name, count]) => `<span class="vehicle-badge"><b>${name}</b><i>${count}</i></span>`).join('')
        : '<span class="empty-result">No vehicle detected</span>';
    }
    if ($('#passed-count')) $('#passed-count').textContent = state.passed_count || 0;
    if ($('#passed-types')) {
      const passedTypes = Object.entries(state.passed_vehicle_types || {});
      $('#passed-types').innerHTML = passedTypes.length
        ? passedTypes.map(([name, count]) => `<span class="vehicle-badge passed"><b>${name}</b><i>${count}</i></span>`).join('')
        : '<span class="empty-result">No vehicle crossed the line</span>';
    }
    if ($('#density')) $('#density').textContent = `${Number(state.density).toFixed(1)}%`;
    if ($('#density-bar')) $('#density-bar').style.width = `${Math.min(100,state.density)}%`;
    if ($('#risk-percentage')) {
      const risk = Number(state.risk_percentage || 0);
      const riskLevel = risk >= 70 ? 'high' : risk >= 40 ? 'medium' : 'low';
      $('#risk-percentage').textContent = `${risk.toFixed(1)}%`;
      $('#risk-percentage').className = `risk-value ${riskLevel}`;
      $('#risk-bar').style.width = `${risk}%`;
      $('#risk-label').textContent = `${riskLevel[0].toUpperCase() + riskLevel.slice(1)} risk`;
    }
    if ($('#congestion')) { $('#congestion').textContent = state.congestion; $('#congestion').className = `level ${state.congestion.toLowerCase()}`; }
    if ($('#fps')) $('#fps').textContent = `${state.fps} FPS`;
    if ($('#backend')) $('#backend').textContent = state.backend;
    if ($('#status-message')) $('#status-message').textContent = state.message;
    if ($('#peak')) $('#peak').textContent = state.summary.peak_vehicles;
    if ($('#samples')) $('#samples').textContent = state.summary.samples;
    if ($('#average')) $('#average').textContent = state.summary.average_vehicles;
    if ($('#avg-density')) $('#avg-density').textContent = `${state.summary.average_density}%`;
    if ($('#total-passed')) $('#total-passed').textContent = state.summary.total_passed || 0;
    if ($('#cars')) $('#cars').textContent = state.summary.cars || 0;
    if ($('#motorcycles')) $('#motorcycles').textContent = state.summary.motorcycles || 0;
    if ($('#buses')) $('#buses').textContent = state.summary.buses || 0;
    if ($('#trucks')) $('#trucks').textContent = state.summary.trucks || 0;
    if ($('#peak-risk')) $('#peak-risk').textContent = `${state.summary.peak_risk || 0}%`;
    $('#system-pill').className = `pill ${state.running ? 'live':'idle'}`;
    $('#system-pill').innerHTML = `<i></i> ${state.running ? 'Analyzing':'Offline'}`;
    if ($('#chart')) renderChart(state.history);
  } catch (_) {}
}
refresh(); setInterval(refresh, 1500);

$('#reset-report')?.addEventListener('click', async () => {
  if (!confirm('Clear all previous analysis records?')) return;
  const response = await fetch('/api/report/reset', {method:'POST'});
  const data = await response.json();
  if (!response.ok) return alert(data.error || 'Could not clear report.');
  location.reload();
});

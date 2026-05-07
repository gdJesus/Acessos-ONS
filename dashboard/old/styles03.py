"""CSS da aplicação."""

APP_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  --green-dark: #2D5016;
  --green-mid: #3A6B1E;
  --green-accent: #4A8C28;
  --green-light: #6DB33F;
  --green-pale: #E8F5E0;
  --bg: #F3F4F6;
  --white: #FFFFFF;
  --border: #E5E7EB;
  --border-light: #F0F0F0;
  --text: #1F2937;
  --text-mid: #4B5563;
  --text-muted: #6B7280;
  --text-dim: #9CA3AF;
  --ponta: #D97706;
  --ponta-bg: #FEF3C7;
  --ponta-text: #92400E;
  --fora-ponta: #7C3AED;
  --fora-ponta-bg: #EDE9FE;
  --fora-ponta-text: #5B21B6;
  --cyan: #0891B2;
  --radius: 8px;
  --shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.06);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

html, body {
  font-family: 'Source Sans 3', system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  overflow-x: hidden;
}

/* Remove Shiny defaults */
.container-fluid { padding: 0 !important; }
.shiny-input-container { width: 100% !important; }

/* ===== HEADER ===== */
.app-header {
  position: fixed;
  top: 0; left: 0; right: 0;
  height: 48px;
  background: linear-gradient(135deg, var(--green-dark) 0%, var(--green-mid) 100%);
  display: flex;
  align-items: center;
  padding: 0 20px;
  z-index: 100;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}

.header-logo { display: flex; align-items: center; gap: 10px; }
.header-logo svg { width: 22px; height: 22px; fill: var(--green-light); }
.header-title { font-size: 15px; font-weight: 600; color: #fff; letter-spacing: -0.01em; }
.header-subtitle { font-size: 12px; color: rgba(255,255,255,0.6); margin-left: 12px; font-weight: 400; }
.header-right { margin-left: auto; display: flex; align-items: center; gap: 16px; }
.header-badge { font-size: 11px; color: var(--green-pale); background: rgba(255,255,255,0.12); padding: 3px 10px; border-radius: 12px; font-weight: 500; }

/* ===== SIDEBAR ===== */
.app-sidebar {
  position: fixed;
  top: 48px; left: 0; bottom: 0;
  width: 220px;
  background: var(--white);
  border-right: 1px solid var(--border);
  overflow-y: auto;
  z-index: 90;
  padding-bottom: 20px;
}

.sidebar-section { padding: 16px 16px 8px; }
.sidebar-section-title {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.08em; color: var(--text-dim); margin-bottom: 10px;
}
.sidebar-divider { height: 1px; background: var(--border); margin: 4px 16px 8px; }

/* Nav buttons */
.nav-btn {
  display: flex; align-items: center; gap: 8px;
  width: 100%; padding: 9px 12px; border: none; background: transparent;
  border-radius: 6px; font-family: inherit; font-size: 13px;
  font-weight: 500; color: var(--text-mid); cursor: pointer;
  transition: all 0.15s; margin-bottom: 2px;
}
.nav-btn:hover { background: var(--bg); color: var(--text); }
.nav-btn.active { background: var(--green-pale); color: var(--green-dark); font-weight: 600; }
.nav-btn .dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--text-dim); flex-shrink: 0;
}
.nav-btn.active .dot { background: var(--green-accent); }

/* Filters */
.filter-group { margin-bottom: 12px; }
.filter-label { font-size: 11px; font-weight: 600; color: var(--text-mid); margin-bottom: 4px; }

.app-sidebar select,
.app-sidebar .selectize-input {
  width: 100% !important; padding: 6px 8px !important; border: 1px solid var(--border) !important;
  border-radius: 5px !important; font-family: inherit !important; font-size: 12px !important;
  color: var(--text) !important; background: var(--white) !important;
}
.app-sidebar .selectize-input { min-height: 30px !important; }
.app-sidebar .form-group { margin-bottom: 0 !important; }
.app-sidebar .control-label { display: none !important; }

.filter-reset {
  display: flex; align-items: center; gap: 6px; padding: 6px 0;
  border: none; background: none; font-family: inherit; font-size: 12px;
  color: var(--green-accent); cursor: pointer; font-weight: 500; margin-top: 4px;
}
.filter-reset:hover { color: var(--green-dark); }

/* ===== MAIN ===== */
.app-main {
  margin-left: 220px;
  margin-top: 48px;
  padding: 24px;
  min-height: calc(100vh - 48px);
}

.page-title { font-size: 22px; font-weight: 700; color: var(--text); margin-bottom: 2px; }
.page-subtitle { font-size: 13px; color: var(--text-muted); margin-bottom: 20px; }
.detail-nome {
  font-size: 18px; font-weight: 700; color: var(--green-dark);
  margin-bottom: 20px; line-height: 1.3;
}

/* ===== CARDS ===== */
.cards-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }
.stat-card {
  background: var(--white); border-radius: var(--radius);
  padding: 18px 20px; box-shadow: var(--shadow);
  border-left: 4px solid transparent; transition: transform 0.15s, box-shadow 0.15s;
}
.stat-card:hover { transform: translateY(-1px); box-shadow: var(--shadow-md); }
.stat-card.green { border-left-color: var(--green-accent); }
.stat-card.amber { border-left-color: var(--ponta); }
.stat-card.purple { border-left-color: var(--fora-ponta); }
.stat-icon {
  width: 32px; height: 32px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; margin-bottom: 10px;
}
.stat-card.green .stat-icon { background: var(--green-pale); color: var(--green-dark); }
.stat-card.amber .stat-icon { background: var(--ponta-bg); color: var(--ponta); }
.stat-card.purple .stat-icon { background: var(--fora-ponta-bg); color: var(--fora-ponta); }
.stat-value {
  font-family: 'JetBrains Mono', monospace; font-size: 26px;
  font-weight: 700; color: var(--text); line-height: 1;
}
.stat-label { font-size: 12px; color: var(--text-muted); margin-top: 4px; font-weight: 500; }

/* ===== PANEL / TABLE ===== */
.panel { background: var(--white); border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; }
.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px; border-bottom: 1px solid var(--border-light);
}
.panel-title { font-size: 14px; font-weight: 600; color: var(--text); }
.panel-badge {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  font-weight: 600; background: var(--green-pale); color: var(--green-dark);
}

.proto-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.proto-table thead th {
  padding: 10px 14px; text-align: left; font-weight: 600;
  color: var(--text-muted); font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.04em; background: #FAFBFC; border-bottom: 1px solid var(--border);
}
.proto-table tbody tr { cursor: pointer; transition: background 0.1s; }
.proto-table tbody tr:hover { background: #F8FAFC; }
.proto-table tbody td {
  padding: 10px 14px; border-bottom: 1px solid var(--border-light); color: var(--text);
}
.proto-num {
  font-family: 'JetBrains Mono', monospace; font-size: 12px;
  font-weight: 600; color: var(--green-dark);
}
.proto-name { max-width: 280px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; }
.badge-quebra {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600;
}
.badge-quebra.sim { background: #FEF3C7; color: #92400E; }
.badge-quebra.nao { background: #F0FDF4; color: #166534; }
.pts-badge {
  font-family: 'JetBrains Mono', monospace; font-size: 12px;
  font-weight: 600; color: var(--cyan); background: #ECFEFF;
  padding: 2px 8px; border-radius: 6px;
}

/* ===== DETAIL ===== */
.back-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 14px; border: 1px solid var(--border); border-radius: 6px;
  background: var(--white); font-family: inherit; font-size: 13px;
  color: var(--text-mid); cursor: pointer; margin-bottom: 16px;
  transition: all 0.15s;
}
.back-btn:hover { border-color: var(--green-accent); color: var(--green-dark); }

.detail-header-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
.info-card { background: var(--white); border-radius: var(--radius); padding: 12px 16px; box-shadow: var(--shadow); }
.info-card .info-label {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--text-dim); margin-bottom: 4px;
}
.info-card .info-value {
  font-size: 13px; font-weight: 600; color: var(--text);
  font-family: 'JetBrains Mono', monospace;
}

/* Connection tabs */
.conn-tabs { display: flex; gap: 6px; margin-bottom: 16px; flex-wrap: wrap; }
.conn-tab {
  padding: 7px 14px; font-size: 12px; border: 1px solid var(--border);
  border-radius: 6px; background: var(--white); color: var(--text-mid);
  cursor: pointer; font-family: inherit; font-weight: 500; transition: all 0.15s;
}
.conn-tab:hover { border-color: var(--green-accent); }
.conn-tab.active { background: var(--green-pale); border-color: var(--green-accent); color: var(--green-dark); font-weight: 600; }

.detail-grid { display: grid; grid-template-columns: 1.2fr 1fr; gap: 16px; }

/* MUST table */
.must-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.must-table thead th {
  padding: 10px 14px; text-align: right; font-weight: 600;
  color: var(--text-muted); font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.04em; background: #FAFBFC; border-bottom: 2px solid var(--border);
}
.must-table thead th:first-child { text-align: left; }
.must-table thead th.col-ponta { color: var(--ponta); background: var(--ponta-bg); }
.must-table thead th.col-fp { color: var(--fora-ponta); background: var(--fora-ponta-bg); }
.must-table tbody td {
  padding: 9px 14px; text-align: right;
  font-family: 'JetBrains Mono', monospace; font-size: 12px;
  border-bottom: 1px solid var(--border-light);
}
.must-table tbody td:first-child {
  text-align: left; font-family: 'Source Sans 3', sans-serif;
  font-weight: 600; color: var(--text-mid);
}
.must-table tbody tr:hover { background: #F8FAFC; }
.val-ponta { color: var(--ponta-text); font-weight: 600; }
.val-fp { color: var(--fora-ponta-text); font-weight: 600; }
.val-empty { color: var(--text-dim); font-weight: 400; }

.period-label {
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.05em; color: var(--text-dim);
  padding: 12px 0 6px; display: flex; align-items: center; gap: 8px;
}
.period-label::after { content: ''; flex: 1; height: 1px; background: var(--border); }

/* Single-point info */
.single-point-info {
  font-size: 12px; color: var(--text-muted); padding: 4px 0; margin-bottom: 16px;
}
.single-point-info strong { color: var(--cyan); }

/* Animations */
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
.stat-card { animation: fadeUp 0.3s ease both; }
.stat-card:nth-child(2) { animation-delay: 0.05s; }
.stat-card:nth-child(3) { animation-delay: 0.1s; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }



/* ===== DATA CENTERS — Layout Executivo ===== */
.dc-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

.dc-card-table { background: var(--white); border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; margin-bottom: 16px; }
.dc-list-table { width: 100%; border-collapse: collapse; font-size: 13px; table-layout: auto; }
.dc-list-table thead th {
  padding: 12px 14px; text-align: left; font-weight: 600;
  color: var(--text-muted); font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.04em; background: #FAFBFC; border-bottom: 2px solid var(--border);
  white-space: nowrap;
}
.dc-list-table tbody tr { cursor: pointer; transition: background 0.1s; }
.dc-list-table tbody tr:hover { background: #F8FAFC; }
.dc-list-table tbody td {
  padding: 12px 14px; border-bottom: 1px solid var(--border-light);
  color: var(--text); vertical-align: middle;
}
.dc-list-table tbody tr:last-child td { border-bottom: none; }
.dc-list-table tbody td.text-col { white-space: normal; max-width: 280px; line-height: 1.4; }
.dc-list-table tbody td.dc-empr-name { font-weight: 600; color: var(--text); }

/* Cell Empreendimento + protocolo */
.dc-empr-cell { display: flex; flex-direction: column; gap: 2px; min-width: 220px; }
.dc-empr-name { font-weight: 600; color: var(--text); font-size: 13px; line-height: 1.3; }
.dc-empr-proto {
  font-family: 'JetBrains Mono', monospace; font-size: 11px;
  color: var(--green-dark); font-weight: 500;
}

/* Status pills */
.status-pill { display:inline-flex; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:700; }
.status-ok { background:#DCFCE7; color:#166534; }
.status-warn { background:#FEF3C7; color:#92400E; }
.status-miss { background:#FEE2E2; color:#991B1B; }
.status-anulada { background:#EDE9FE; color:#5B21B6; border:1px solid #C4B5FD; }

/* Spark — mini gráfico de evolução por ano */
.dc-spark { display: flex; align-items: flex-end; gap: 2px; height: 28px; min-width: 110px; }
.dc-spark-bar {
  flex: 1; min-width: 6px; border-radius: 2px 2px 0 0;
  background: var(--green-pale); position: relative; transition: opacity 0.15s;
}
.dc-spark-bar:hover { opacity: 0.8; }
.dc-spark-bar.contractable { background: #A7F3D0; }
.dc-spark-bar.current { background: #34D399; }
.dc-spark-bar.outside { background: #FDBA74; }
.dc-spark-bar.empty { background: #F3F4F6; height: 4px !important; }
.dc-spark-label { font-size: 9px; color: var(--text-dim); text-align: center; margin-top: 2px; }

/* Pico MW */
.dc-pico {
  font-family: 'JetBrains Mono', monospace; font-weight: 700;
  color: var(--green-dark); font-size: 13px; text-align: center;
}

/* Filtros tipo chip */
.dc-quick-filters {
  display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px;
}
.dc-chip {
  padding: 6px 12px; font-size: 12px; border: 1px solid var(--border);
  border-radius: 16px; background: var(--white); color: var(--text-mid);
  cursor: pointer; font-family: inherit; font-weight: 500;
  transition: all 0.15s;
}
.dc-chip:hover { border-color: var(--green-accent); color: var(--green-dark); }
.dc-chip.active { background: var(--green-pale); border-color: var(--green-accent); color: var(--green-dark); font-weight: 600; }
.dc-chip-count { display: inline-block; margin-left: 4px; opacity: 0.7; font-size: 11px; }

/* Search box */
.dc-search-row { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.dc-search { flex: 1; min-width: 240px; }
.dc-search input {
  width: 100%; padding: 8px 12px; border: 1px solid var(--border);
  border-radius: 6px; font-family: inherit; font-size: 13px;
  background: var(--white);
}
.dc-search input:focus { outline: none; border-color: var(--green-accent); }

/* === DC DETAIL === */
.dc-detail-header {
  background: var(--white); border-radius: var(--radius); padding: 18px 20px;
  margin-bottom: 16px; box-shadow: var(--shadow);
  display: flex; gap: 24px; flex-wrap: wrap; align-items: flex-start;
}
.dc-detail-main { flex: 2; min-width: 280px; }
.dc-detail-side { flex: 1; min-width: 200px; }
.dc-detail-empresa { font-size: 18px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
.dc-detail-proto {
  font-family: 'JetBrains Mono', monospace; font-size: 13px;
  color: var(--green-dark); font-weight: 600;
}
.dc-detail-meta { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 8px; font-size: 12px; color: var(--text-mid); }
.dc-detail-meta-item { display: flex; gap: 6px; align-items: center; }
.dc-detail-meta-label { color: var(--text-dim); font-weight: 600; text-transform: uppercase; font-size: 10px; letter-spacing: 0.04em; }
.dc-detail-meta-value { font-weight: 600; color: var(--text); }

/* Horizon timeline */
.dc-horizon-wrap { background: var(--white); border-radius: var(--radius); padding: 18px 20px; box-shadow: var(--shadow); margin-bottom: 16px; }
.dc-horizon-title { font-size: 14px; font-weight: 600; color: var(--text); margin-bottom: 14px; display: flex; align-items: center; gap: 12px; }
.dc-horizon-grid {
  display: grid; gap: 8px;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
}
.dc-year-card {
  border: 1px solid var(--border); border-radius: 8px; padding: 12px;
  background: var(--white); transition: all 0.15s;
}
.dc-year-card.contractable { background: #ECFDF5; border-color: #A7F3D0; }
.dc-year-card.current { background: #D1FAE5; border-color: #6EE7B7; box-shadow: 0 0 0 2px #34D399; }
.dc-year-card.outside { background: #FFF7ED; border-color: #FDBA74; }
.dc-year-card.empty { opacity: 0.5; }
.dc-year-num { font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 14px; color: var(--text); margin-bottom: 8px; }
.dc-year-row { display: flex; justify-content: space-between; align-items: baseline; font-size: 11px; margin-top: 4px; }
.dc-year-label { color: var(--text-muted); font-weight: 500; }
.dc-year-val-p { color: var(--ponta-text); font-weight: 700; font-family: 'JetBrains Mono', monospace; font-size: 13px; }
.dc-year-val-f { color: var(--fora-ponta-text); font-weight: 700; font-family: 'JetBrains Mono', monospace; font-size: 13px; }
.dc-year-val-empty { color: var(--text-dim); font-weight: 400; }
.dc-year-tag {
  display: inline-block; font-size: 9px; padding: 1px 6px; border-radius: 8px;
  font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
}
.dc-year-card.current .dc-year-tag { background: #065F46; color: white; }

/* Sumário lateral */
.dc-summary {
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px;
}
.dc-summary-card {
  background: var(--white); border-radius: var(--radius); padding: 14px 16px;
  box-shadow: var(--shadow); border-left: 3px solid var(--green-accent);
}
.dc-summary-card .label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-dim); margin-bottom: 4px; }
.dc-summary-card .value { font-family: 'JetBrains Mono', monospace; font-size: 18px; font-weight: 700; color: var(--text); }
.dc-summary-card .sub { font-size: 11px; color: var(--text-muted); margin-top: 2px; }

/* Rede pills */
.rede-pill {
  display: inline-flex; padding: 3px 10px; border-radius: 10px;
  font-size: 11px; font-weight: 700; letter-spacing: 0.04em;
}

/* Células de data nas tabelas DC */
.date-cell {
  font-family: 'JetBrains Mono', monospace; font-size: 11px;
  color: var(--text-mid); white-space: nowrap;
}
/* Realce dinâmico baseado na proximidade do prazo (calculado a cada render) */
.date-cell.prazo-yellow {
  background: #FEF3C7 !important;
  color: #92400E !important;
  font-weight: 700;
  border-radius: 4px;
}
.date-cell.prazo-red {
  background: #FEE2E2 !important;
  color: #991B1B !important;
  font-weight: 700;
  border-radius: 4px;
}
.date-cell.prazo-blue {
  background: #DBEAFE !important;
  color: #1E40AF !important;
  font-weight: 700;
  border-radius: 4px;
}

/* CUST pills */
.cust-pill {
  display: inline-flex; padding: 3px 10px; border-radius: 10px;
  font-size: 11px; font-weight: 700; letter-spacing: 0.04em;
}
.cust-pill.cust-assinado {
  background: #D1FAE5; color: #065F46;
  font-family: 'JetBrains Mono', monospace; letter-spacing: 0;
}
.cust-pill.cust-no-prazo {
  background: #DBEAFE; color: #1E40AF;
}
.cust-pill.cust-verificar {
  background: #DBEAFE; color: #1E40AF;
}
.cust-pill.cust-nao-assinado {
  background: #FEE2E2; color: #991B1B;
}
.cust-pill.cust-inviavel {
  background: #DC2626; color: #FFFFFF; font-weight: 800;
}
.cust-pill.cust-ptdis {
  background: #DBEAFE; color: #1E40AF;
  letter-spacing: 0.04em;
}

/* Pills de Viabilidade */
.viab-pill {
  display: inline-flex; padding: 3px 10px; border-radius: 10px;
  font-size: 11px; font-weight: 700; letter-spacing: 0.04em;
  white-space: nowrap;
}
.viab-pill.viab-viavel { background: #D1FAE5; color: #065F46; border: 1px solid #6EE7B7; }
.viab-pill.viab-condicionado { background: #FEF3C7; color: #92400E; border: 1px solid #FDE68A; }
.viab-pill.viab-limitado { background: #FFEDD5; color: #9A3412; border: 1px solid #FDBA74; }
.viab-pill.viab-inviavel { background: #DC2626; color: #FFFFFF; border: 1px solid #991B1B; font-weight: 800; }
.viab-pill.viab-cancelada { background: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; font-weight: 800; }
.viab-pill.viab-anulada { background: #EDE9FE; color: #5B21B6; border: 1px solid #C4B5FD; font-weight: 800; }
.viab-pill.viab-pendente { background: #F3F4F6; color: var(--text-muted); border: 1px solid var(--border); }
.viab-pill.viab-misto { background: #EDE9FE; color: #5B21B6; border: 1px solid #C4B5FD; }

/* Label de ponto (sub-texto na célula de empreendimento) */
.dc-ponto-label {
  font-size: 10px; color: var(--text-muted); margin-top: 2px;
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* Badges de pendência */
.pend-badge {
  display: inline-flex; padding: 4px 10px; border-radius: 6px;
  font-size: 11px; font-weight: 700;
  border: 1px solid transparent;
}
.pend-badge.pend-warn { background: #FEF3C7; color: #92400E; border-color: #FDE68A; }
.pend-badge.pend-orange { background: #FFEDD5; color: #9A3412; border-color: #FDBA74; }
.pend-badge.pend-red { background: #FEE2E2; color: #991B1B; border-color: #FCA5A5; }
.rede-pill.rede-dist { background: #DBEAFE; color: #1E40AF; }
.rede-pill.rede-rb { background: #FCE7F3; color: #9D174D; }
.rede-pill.rede-dit { background: #FEF3C7; color: #92400E; }
.rede-pill.rede-empty { background: #F3F4F6; color: var(--text-dim); }

/* DC: barra de filtros (fora do output_ui — não re-renderiza) */
.dc-page-wrapper { display: block; }
.dc-filters-bar {
  display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap;
  background: var(--white); padding: 12px 16px; border-radius: var(--radius);
  box-shadow: var(--shadow); margin-bottom: 14px;
}
.dc-filter-field { display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 140px; }
.dc-filter-field .form-group { margin: 0 !important; }
.dc-filter-field .control-label { display: none !important; }
.dc-filter-field .shiny-input-container { width: 100% !important; }
.dc-filter-lbl {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--text-mid);
}
.dc-filter-field input,
.dc-filter-field .selectize-input,
.dc-filter-field select {
  width: 100% !important; padding: 6px 10px !important;
  border: 1px solid var(--border) !important; border-radius: 5px !important;
  font-size: 12px !important; min-height: 32px !important;
  background: var(--white) !important;
  box-sizing: border-box !important;
  line-height: 1.4 !important;
}
.dc-filter-field .selectize-control { width: 100% !important; }
.dc-filter-field .selectize-input {
  display: flex !important; flex-wrap: wrap !important;
  align-items: center !important; gap: 4px !important;
}
.dc-filter-field .selectize-input.has-items { padding: 4px 6px !important; }
.dc-filter-field .selectize-input > input {
  font-size: 12px !important;
  margin: 0 !important;
  padding: 0 !important;
  height: auto !important;
  min-width: 60px !important;
}
.dc-filter-field .selectize-input .item {
  font-size: 11px !important;
  padding: 1px 6px !important;
  margin: 1px !important;
  background: var(--green-pale) !important;
  color: var(--green-dark) !important;
  border-radius: 3px !important;
}
.dc-filter-field input:focus,
.dc-filter-field .selectize-input.focus { border-color: var(--green-accent) !important; }
.dc-filter-reset-btn {
  padding: 7px 14px; font-size: 12px; font-weight: 600;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--white); color: var(--text-mid);
  cursor: pointer; font-family: inherit; transition: all 0.15s;
  white-space: nowrap; height: 32px;
}
.dc-filter-reset-btn:hover { border-color: var(--green-accent); color: var(--green-dark); }

/* Botão MUST */
.dc-btn-must {
  padding: 4px 10px; font-size: 11px; font-weight: 600;
  border: 1px solid var(--green-accent); border-radius: 6px;
  background: var(--green-pale); color: var(--green-dark);
  cursor: pointer; font-family: inherit; transition: all 0.15s;
  white-space: nowrap;
}
.dc-btn-must:hover {
  background: var(--green-accent); color: white; border-color: var(--green-dark);
}
.dc-btn-must.disabled {
  background: #F3F4F6; color: var(--text-dim); border-color: var(--border);
  cursor: not-allowed; opacity: 0.5;
}
.dc-btn-must.disabled:hover {
  background: #F3F4F6; color: var(--text-dim);
}

/* Botão primário (Solicitações com todos valores) */
.dc-btn-primary {
  padding: 7px 14px; font-size: 12px; font-weight: 600;
  border: 1px solid var(--green-accent); border-radius: 6px;
  background: var(--green-accent); color: white;
  cursor: pointer; font-family: inherit; transition: all 0.15s;
  white-space: nowrap;
}
.dc-btn-primary:hover {
  background: var(--green-dark); border-color: var(--green-dark);
}

/* Matriz de valores */
.dc-matrix-wrap { overflow-x: auto; max-height: 70vh; }
.dc-matrix-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.dc-matrix-table thead th {
  position: sticky; top: 0; z-index: 5;
  padding: 8px 10px; font-weight: 600;
  color: var(--text-muted); font-size: 10px; text-transform: uppercase;
  letter-spacing: 0.04em; background: #FAFBFC; border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.dc-matrix-table thead tr:nth-child(2) th {
  top: 36px;
}
.dc-matrix-table tbody td {
  padding: 8px 10px; border-bottom: 1px solid var(--border-light);
  color: var(--text); white-space: nowrap;
}
.dc-matrix-table tbody td.matrix-cell {
  text-align: center; font-family: 'JetBrains Mono', monospace;
  font-size: 11px; font-weight: 600;
}
.dc-matrix-table tbody tr:hover { background: #F8FAFC; }

/* Cores dos anos no horizonte */
.dc-matrix-table .matrix-cell.current { background: #D1FAE5; box-shadow: inset 0 0 0 1px #6EE7B7; }
.dc-matrix-table .matrix-cell.contractable { background: #ECFDF5; }
.dc-matrix-table .matrix-cell.outside { background: #FFEDD5; }
.dc-matrix-table .matrix-cell.before { background: #F3F4F6; opacity: 0.6; }
.dc-matrix-table .matrix-cell.future-empty { background: #FAFBFC; }

/* Top toolbar */
.dc-toolbar {
  display: flex; gap: 12px; align-items: center; margin-bottom: 14px; flex-wrap: wrap;
  font-size: 12px;
}
.dc-toolbar .spacer { flex: 1; }
.dc-result-count { color: var(--text-mid); font-weight: 500; }
.dc-result-count strong { color: var(--text); }

/* Responsive */
@media (max-width: 1100px) {
  .detail-grid { grid-template-columns: 1fr; }
  .detail-header-cards { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 768px) {
  .app-sidebar { display: none; }
  .app-main { margin-left: 0; }
  .cards-row { grid-template-columns: 1fr; }
}


/* Filtro triestado: Emitido PL */
.tri-filter-btn {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 6px 10px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s;
  text-align: center;
}
.tri-filter-btn.tri-filter-none {
  background: #F9FAFB;
  color: var(--text-muted);
}
.tri-filter-btn.tri-filter-nao {
  background: #FEE2E2;
  color: #991B1B;
  border-color: #FCA5A5;
}
.tri-filter-btn.tri-filter-sim {
  background: #D1FAE5;
  color: #065F46;
  border-color: #6EE7B7;
}
.tri-filter-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 1px 2px rgba(0,0,0,0.08);
}


/* ===== SIDEBAR AUTO-HIDE =====
   A sidebar fica recolhida e reaparece ao passar o mouse na aba lateral. */
@media (min-width: 769px) {
  body:not(.no-sidebar) .app-sidebar {
    transform: translateX(calc(-100% + 38px));
    transition: transform 0.22s ease, box-shadow 0.22s ease;
    box-shadow: 2px 0 10px rgba(0,0,0,0.04);
    overflow-x: hidden;
  }

  body:not(.no-sidebar) .app-sidebar:hover,
  body:not(.no-sidebar) .app-sidebar:focus-within {
    transform: translateX(0);
    box-shadow: 4px 0 18px rgba(0,0,0,0.14);
  }

  body:not(.no-sidebar) .app-sidebar::after {
    content: "☰\A FILTROS";
    position: fixed;
    top: 0;
    right: 0;
    width: 38px;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    white-space: pre;
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    text-align: center;
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 0.12em;
    line-height: 1.5;
    color: #FFFFFF;
    background: linear-gradient(180deg, var(--green-dark) 0%, var(--green-mid) 45%, var(--green-accent) 100%);
    border-right: 1px solid rgba(255,255,255,0.24);
    box-shadow: 3px 0 12px rgba(0,0,0,0.18);
    pointer-events: none;
  }

  body:not(.no-sidebar) .app-sidebar::before {
    content: "›";
    position: fixed;
    top: 50%;
    right: 30px;
    transform: translateY(-50%);
    width: 18px;
    height: 42px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 0 10px 10px 0;
    background: var(--green-dark);
    color: #FFFFFF;
    font-size: 22px;
    font-weight: 800;
    box-shadow: 3px 0 10px rgba(0,0,0,0.20);
    pointer-events: none;
  }

  body:not(.no-sidebar) .app-sidebar:hover::after,
  body:not(.no-sidebar) .app-sidebar:focus-within::after,
  body:not(.no-sidebar) .app-sidebar:hover::before,
  body:not(.no-sidebar) .app-sidebar:focus-within::before {
    opacity: 0;
  }

  body:not(.no-sidebar) .app-main {
    margin-left: 38px;
    transition: margin-left 0.22s ease;
  }

  body:not(.no-sidebar) .app-sidebar:hover ~ .app-main,
  body:not(.no-sidebar) .app-sidebar:focus-within ~ .app-main {
    margin-left: 220px;
  }

  body:not(.no-sidebar) .app-sidebar .sidebar-section,
  body:not(.no-sidebar) .app-sidebar .sidebar-divider {
    opacity: 0;
    transition: opacity 0.12s ease;
  }

  body:not(.no-sidebar) .app-sidebar:hover .sidebar-section,
  body:not(.no-sidebar) .app-sidebar:hover .sidebar-divider,
  body:not(.no-sidebar) .app-sidebar:focus-within .sidebar-section,
  body:not(.no-sidebar) .app-sidebar:focus-within .sidebar-divider {
    opacity: 1;
    transition-delay: 0.08s;
  }
}

/* Selectize dentro da sidebar: impede chips de sair pela direita */
.app-sidebar .selectize-control,
.app-sidebar .selectize-input {
  max-width: 100% !important;
  width: 100% !important;
  box-sizing: border-box !important;
}
.app-sidebar .selectize-input {
  display: flex !important;
  flex-wrap: wrap !important;
  align-items: center !important;
  gap: 4px !important;
  overflow: hidden !important;
}
.app-sidebar .selectize-input > input {
  min-width: 40px !important;
  max-width: 100% !important;
}
.app-sidebar .selectize-input .item {
  max-width: 100% !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  white-space: nowrap !important;
}


/* =========================================================
   AJUSTE SIDEBAR RECOLHIDA — FAIXA VERDE ADAPTÁVEL
   ---------------------------------------------------------
   Na Visão Geral há mais filtros; ao rolar a sidebar, a faixa
   lateral "☰ FILTROS" não pode depender da altura do conteúdo.
   A faixa verde passa a ser o background do próprio painel
   recolhido, ficando contínua em toda a área visível.
   ========================================================= */
@media (min-width: 769px) {
  body:not(.no-sidebar) .app-sidebar {
    background:
      linear-gradient(
        90deg,
        var(--white) 0,
        var(--white) calc(100% - 38px),
        var(--green-dark) calc(100% - 38px),
        var(--green-mid) calc(100% - 18px),
        var(--green-accent) 100%
      ) !important;
    background-attachment: scroll !important;
    background-repeat: no-repeat !important;
    background-size: 100% 100% !important;
  }

  body:not(.no-sidebar) .app-sidebar:hover,
  body:not(.no-sidebar) .app-sidebar:focus-within {
    background: var(--white) !important;
  }

  body:not(.no-sidebar) .app-sidebar::after {
    background: transparent !important;
    height: calc(100vh - 48px) !important;
    min-height: calc(100vh - 48px) !important;
    box-shadow: none !important;
  }
}



/* =========================================================
   MATRIZ — AGRUPAR COLUNAS ENTRE PROTOCOLO E ANOS
   ========================================================= */
.dc-matrix-table.cols-collapsed .matrix-collapsible-col {
  display: none !important;
}

.dc-matrix-table .matrix-toggle-th {
  width: 56px !important;
  min-width: 56px !important;
  max-width: 56px !important;
  padding: 4px 5px !important;
  text-align: center !important;
  background: #F0FDF4 !important;
  border-left: 1px solid #BBF7D0 !important;
  border-right: 1px solid #BBF7D0 !important;
}

.dc-matrix-table .matrix-toggle-btn {
  width: 100%;
  min-width: 44px;
  border: 1px solid #86EFAC;
  border-radius: 999px;
  padding: 3px 5px;
  background: #DCFCE7;
  color: var(--green-dark);
  font-family: inherit;
  font-size: 9px;
  font-weight: 800;
  line-height: 1.15;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  cursor: pointer;
  white-space: nowrap;
}

.dc-matrix-table .matrix-toggle-btn:hover {
  background: var(--green-pale);
  border-color: var(--green-accent);
  color: var(--green-dark);
}

.dc-matrix-table .matrix-toggle-spacer {
  width: 56px !important;
  min-width: 56px !important;
  max-width: 56px !important;
  padding: 8px 4px !important;
  text-align: center !important;
  color: var(--text-dim) !important;
  background: #FAFBFC !important;
  font-weight: 700;
}

.dc-matrix-table:not(.cols-collapsed) .matrix-toggle-spacer {
  background: #F0FDF4 !important;
  color: var(--green-dark) !important;
}

"""

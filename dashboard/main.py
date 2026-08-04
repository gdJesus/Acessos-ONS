"""Montagem da UI principal."""

import os
from shiny import App, ui
from htmltools import HTML, tags

from .components import make_header, make_sidebar
from .data import CACHE_UPDATED_AT
from .server import server
from .styles import APP_CSS

# Lê a flag definida em app.py
SHOW_SIDEBAR = os.environ.get("DASHBOARD_SHOW_SIDEBAR", "1") == "1"

app_ui = ui.page_fluid(
    ui.tags.style(APP_CSS),
    # Quando sidebar está oculta, força o conteúdo principal a ocupar tela toda
    ui.tags.style("body.no-sidebar .app-main { margin-left: 0 !important; } body.no-sidebar .app-sidebar { display: none !important; }") if not SHOW_SIDEBAR else None,
    ui.tags.script(HTML(f"""
    $(document).on('shiny:connected', function() {{
        {"$('body').addClass('no-sidebar');" if not SHOW_SIDEBAR else ""}
        $('#nav_overview').html('<span class="dot"></span><span class="nav-label">Visão Geral (em desenvolvimento)</span>');
        $('#nav_datacenters').html('<span class="dot"></span><span class="nav-label">DataCenters</span>');
        $('#nav_datacenters_panel').html('<span class="dot"></span><span class="nav-label">Painel de Data Centers na Rede Básica</span>');

        // Row click — Visão Geral MUST
        $(document).on('click', '.proto-table tbody tr[data-proto], .overview-list-table tbody tr[data-proto]', function() {{
            Shiny.setInputValue('selected_protocol', $(this).data('proto'), {{priority:'event'}});
        }});
        // Row click — DC lista
        $(document).on('click', '.dc-list-table tbody tr[data-dc]', function(e) {{
            if ($(e.target).closest('.dc-btn-must').length) return;
            Shiny.setInputValue('selected_dc_item', String($(this).data('dc')), {{priority:'event'}});
        }});
        // Botão MUST → abre detalhe MUST
        $(document).on('click', '.dc-btn-must:not(.disabled)', function(e) {{
            e.stopPropagation();
            Shiny.setInputValue('dc_open_must', String($(this).data('dc-must')), {{priority:'event'}});
        }});
        // Expande/retrai colunas agrupadas nas matrizes de valores solicitados
        $(document).on('click', '.js-matrix-toggle', function(e) {{
            e.preventDefault();
            e.stopPropagation();
            var table = $(this).closest('table');
            table.toggleClass('cols-collapsed');
            var collapsed = table.hasClass('cols-collapsed');
            $(this)
                .text(collapsed ? '▸ Dados' : '◂ Ocultar')
                .attr('aria-expanded', collapsed ? 'false' : 'true');
        }});

        // Conn tab MUST
        $(document).on('click', '.conn-tab', function() {{
            Shiny.setInputValue('selected_point_idx', parseInt($(this).data('idx')), {{priority:'event'}});
        }});
        // Painel de Data Centers na Rede Básica — filtro por UF no mapa
        $(document).on('click', '.dcp-brazil-map .state[id]', function(e) {{
            e.stopPropagation();
            Shiny.setInputValue('dcp_state_click', String(this.id), {{priority:'event'}});
        }});
        $(document).on('click', '.dcp-brazil-map', function(e) {{
            if ($(e.target).closest('.state[id]').length) return;
            Shiny.setInputValue('dcp_state_click', '__clear__', {{priority:'event'}});
        }});
        $(document).on('click', '.dcp-map-clear', function(e) {{
            e.preventDefault();
            Shiny.setInputValue('dcp_state_click', '__clear__', {{priority:'event'}});
        }});
        $(document).on('click', '.dcp-toggle[data-metric]', function(e) {{
            e.preventDefault();
            Shiny.setInputValue('dcp_metric', String($(this).data('metric')), {{priority:'event'}});
        }});
        $(document).on('change', '.dcp-chart-select', function(e) {{
            Shiny.setInputValue('dcp_chart_type', String($(this).val()), {{priority:'event'}});
        }});
        $(document).on('click', '.dcp-chart-btn[data-chart]', function(e) {{
            e.preventDefault();
            Shiny.setInputValue('dcp_chart_type', String($(this).data('chart')), {{priority:'event'}});
        }});
        document.addEventListener('wheel', function(e) {{
            if (e.ctrlKey && e.target && e.target.closest && e.target.closest('.dcp-page')) {{
                e.preventDefault();
            }}
        }}, {{ passive: false }});
    }});
    """)),
    make_header(CACHE_UPDATED_AT),
    make_sidebar() if SHOW_SIDEBAR else None,
    tags.div(
        # Overview MUST
        ui.output_ui("overview_page"),

        # Overview matriz — todos os valores solicitados
        ui.output_ui("overview_matrix_page"),

        # DataCenters lista — filtros na sidebar + tabela renderizada
        tags.div(
            ui.output_ui("datacenters_page"),
            id="dc-list-wrapper",
            class_="dc-page-wrapper",
        ),

        # DataCenters detail
        ui.output_ui("datacenters_detail_page"),

        # DataCenters matriz — filtros na sidebar + tabela renderizada
        tags.div(
            ui.output_ui("datacenters_matrix_page"),
            id="dc-matrix-wrapper",
            class_="dc-page-wrapper",
        ),

        # Painel executivo DataCenters
        ui.output_ui("datacenters_panel_page"),

        # Detalhe MUST
        ui.output_ui("detail_page"),

        class_="app-main",
    ),
)

app = App(app_ui, server)

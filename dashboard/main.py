"""Montagem da UI principal."""

import os
from shiny import App, ui
from htmltools import HTML, tags

from .components import make_header, make_sidebar
from .data import DATACENTER_ROWS, CACHE_UPDATED_AT
from .server import server
from .styles import APP_CSS

# Lê a flag definida em app.py
SHOW_SIDEBAR = os.environ.get("DASHBOARD_SHOW_SIDEBAR", "1") == "1"

# Pré-calcular opções dos filtros DC (uma vez só, não muda)
_redes = sorted(set(r["rede"] for r in DATACENTER_ROWS if r.get("rede") and r["rede"] != "—"))
_kvs = sorted(
    set(r["tensao"] for r in DATACENTER_ROWS if r.get("tensao") and r["tensao"] != "—"),
    key=lambda x: int(str(x).split(".")[0]) if str(x).replace(".", "").isdigit() else 0,
)

_statuses = sorted(
    set((r.get("status") or "").strip() for r in DATACENTER_ROWS if (r.get("status") or "").strip() and r.get("status") != "—")
)


def _dc_filters_bar(prefix):
    """Barra de filtros para a lista (prefix='dc') ou matriz (prefix='dcm').
    Renderizada apenas uma vez, fora do output_ui — assim os inputs persistem."""
    return tags.div(
        tags.div(
            tags.label("Empreendimento", class_="dc-filter-lbl"),
            ui.input_text(f"{prefix}_empr", "", placeholder="Filtrar por nome..."),
            class_="dc-filter-field",
        ),
        tags.div(
            tags.label("Protocolo", class_="dc-filter-lbl"),
            ui.input_text(f"{prefix}_proto", "", placeholder="SGA-..."),
            class_="dc-filter-field",
        ),
        tags.div(
            tags.label("Rede", class_="dc-filter-lbl"),
            ui.input_selectize(
                f"{prefix}_rede", "",
                choices={r: r for r in _redes},
                multiple=True,
                options={"placeholder": "Todas"},
            ),
            class_="dc-filter-field",
        ),
        tags.div(
            tags.label("Tensão (kV)", class_="dc-filter-lbl"),
            ui.input_selectize(
                f"{prefix}_kv", "",
                choices={k: k for k in _kvs},
                multiple=True,
                options={"placeholder": "Todas"},
            ),
            class_="dc-filter-field",
        ),
        tags.div(
            tags.label("Conexão", class_="dc-filter-lbl"),
            ui.input_text(f"{prefix}_conexao", "", placeholder="Filtrar..."),
            class_="dc-filter-field",
        ),
        tags.div(
            tags.label("Viabilidade", class_="dc-filter-lbl"),
            ui.input_selectize(
                f"{prefix}_viab", "",
                choices={v: v for v in [
                    "Viável",
                    "Viável/Condicionado",
                    "Limitado/Viável/Condicionado",
                    "Inviável",
                    "Cancelada",
                    "Anulada",
                    "Em análise",
                    "Pendente",
                    "Misto",
                ]},
                multiple=True,
                options={"placeholder": "Todas"},
            ),
            class_="dc-filter-field",
        ),
        tags.div(
            tags.label("Status", class_="dc-filter-lbl"),
            ui.input_selectize(
                f"{prefix}_status", "",
                choices={s: s for s in _statuses},
                multiple=True,
                options={"placeholder": "Todos"},
            ),
            class_="dc-filter-field",
        ),
        tags.div(
            tags.label("Ordenar por", class_="dc-filter-lbl"),
            ui.input_select(
                f"{prefix}_sort", "",
                choices={
                    "data_desc": "Data Solic. ↓ (recente)",
                    "data_asc": "Data Solic. ↑ (antiga)",
                    "entrada_pl_desc": "Entrada PL ↓",
                    "entrada_pl_asc": "Entrada PL ↑",
                    "prazo_pl_asc": "Prazo PL ↑ (próximo)",
                    "prazo_pl_desc": "Prazo PL ↓",
                    "prazo_ons_asc": "Prazo ONS ↑ (próximo)",
                    "prazo_ons_desc": "Prazo ONS ↓",
                    "emissao_pl_desc": "Emissão PL ↓ (recente)",
                    "emissao_pl_asc": "Emissão PL ↑ (antiga)",
                    "emissao_doc_desc": "Emissão Doc. ↓ (recente)",
                    "emissao_doc_asc": "Emissão Doc. ↑ (antiga)",
                    "prazo_cust_asc": "Prazo CUST ↑ (próximo)",
                    "prazo_cust_desc": "Prazo CUST ↓",
                    "proto_desc": "Protocolo ↓",
                    "proto_asc": "Protocolo ↑",
                    "empr_asc": "Empreendimento A→Z",
                    "empr_desc": "Empreendimento Z→A",
                },
                selected="data_asc",
            ),
            class_="dc-filter-field",
        ),
        ui.input_action_button(f"{prefix}_reset", "↺ Limpar filtros", class_="dc-filter-reset-btn"),
        class_="dc-filters-bar",
        id=f"{prefix}-filters-bar",
    )


app_ui = ui.page_fluid(
    ui.tags.style(APP_CSS),
    # Quando sidebar está oculta, força o conteúdo principal a ocupar tela toda
    ui.tags.style("body.no-sidebar .app-main { margin-left: 0 !important; } body.no-sidebar .app-sidebar { display: none !important; }") if not SHOW_SIDEBAR else None,
    ui.tags.script(HTML(f"""
    $(document).on('shiny:connected', function() {{
        {"$('body').addClass('no-sidebar');" if not SHOW_SIDEBAR else ""}
        $('#nav_overview').html('<span class="dot"></span> Visão Geral');
        $('#nav_datacenters').html('<span class="dot"></span> DataCenters');
        $('#nav_datacenters_panel').html('<span class="dot"></span> Painel DataCenters');

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
        // Painel DataCenters — filtro por UF no mapa
        $(document).on('click', '.dcp-brazil-map .state[id]', function(e) {{
            Shiny.setInputValue('dcp_state_click', String(this.id), {{priority:'event'}});
        }});
        $(document).on('click', '.dcp-map-clear', function(e) {{
            e.preventDefault();
            Shiny.setInputValue('dcp_state_click', '', {{priority:'event'}});
        }});
        $(document).on('click', '.dcp-toggle[data-metric]', function(e) {{
            e.preventDefault();
            Shiny.setInputValue('dcp_metric', String($(this).data('metric')), {{priority:'event'}});
        }});
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

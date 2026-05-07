"""Componentes reutilizáveis de UI."""

from shiny import ui
from htmltools import HTML, tags


def make_header(data_atualizacao=None):
    badges = []
    if data_atualizacao:
        badges.append(tags.span(f"Data de Atualização {data_atualizacao}", class_="header-badge header-badge-update"))
    badges.append(tags.span("SGA/SAM", class_="header-badge"))

    return tags.div(
        tags.div(
            HTML('<svg viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>'),
            tags.span("DataCenters - SP", class_="header-title"),
            tags.span("Solicitações de Acesso — Transmissão", class_="header-subtitle"),
            class_="header-logo",
        ),
        tags.div(
            *badges,
            class_="header-right",
        ),
        class_="app-header",
    )


def _sort_choices_overview():
    return {
        "data_solic_asc": "Data Solic. ↑ (antiga)",
        "data_solic_desc": "Data Solic. ↓ (recente)",
        "entrada_pl_asc": "Entrada PL ↑",
        "entrada_pl_desc": "Entrada PL ↓",
        "prazo_pl_asc": "Prazo PL ↑ (próximo)",
        "prazo_pl_desc": "Prazo PL ↓",
        "prazo_ons_asc": "Prazo ONS ↑ (próximo)",
        "prazo_ons_desc": "Prazo ONS ↓",
        "emissao_pl_asc": "Emissão PL ↑ (antiga)",
        "emissao_pl_desc": "Emissão PL ↓ (recente)",
        "emissao_doc_asc": "Emissão Doc. ↑ (antiga)",
        "emissao_doc_desc": "Emissão Doc. ↓ (recente)",
        "prazo_cust_asc": "Prazo CUST ↑ (próximo)",
        "prazo_cust_desc": "Prazo CUST ↓",
        "nome_asc": "Solicitação A→Z",
        "nome_desc": "Solicitação Z→A",
        "protocolo_asc": "Protocolo A→Z",
        "protocolo_desc": "Protocolo Z→A",
    }


def _sort_choices_dc():
    return {
        "data_asc": "Data Solic. ↑ (antiga)",
        "data_desc": "Data Solic. ↓ (recente)",
        "entrada_pl_asc": "Entrada PL ↑",
        "entrada_pl_desc": "Entrada PL ↓",
        "prazo_pl_asc": "Prazo PL ↑ (próximo)",
        "prazo_pl_desc": "Prazo PL ↓",
        "prazo_ons_asc": "Prazo ONS ↑ (próximo)",
        "prazo_ons_desc": "Prazo ONS ↓",
        "emissao_pl_asc": "Emissão PL ↑ (antiga)",
        "emissao_pl_desc": "Emissão PL ↓ (recente)",
        "emissao_doc_asc": "Emissão Doc. ↑ (antiga)",
        "emissao_doc_desc": "Emissão Doc. ↓ (recente)",
        "prazo_cust_asc": "Prazo CUST ↑ (próximo)",
        "prazo_cust_desc": "Prazo CUST ↓",
        "proto_asc": "Protocolo A→Z",
        "proto_desc": "Protocolo Z→A",
        "empr_asc": "Empreendimento A→Z",
        "empr_desc": "Empreendimento Z→A",
    }


def _overview_filters_section():
    return tags.div(
        tags.div("Filtros", class_="sidebar-section-title"),
        tags.div(
            tags.div("Solicitação:", class_="filter-label"),
            ui.input_text("filter_nome", "", placeholder="Buscar por nome..."),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Protocolo:", class_="filter-label"),
            ui.input_text("filter_protocolo", "", placeholder="SGA-..."),
            class_="filter-group",
        ),
        tags.div(
            tags.div("UF:", class_="filter-label"),
            ui.input_selectize("filter_uf", "", choices={}, selected=[], multiple=True, options={"placeholder": "Todas"}),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Rede:", class_="filter-label"),
            ui.input_selectize("filter_rede", "", choices={}, selected=[], multiple=True, options={"placeholder": "Todas"}),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Tensão (kV):", class_="filter-label"),
            ui.input_selectize("filter_tensao", "", choices={}, selected=[], multiple=True, options={"placeholder": "Todas"}),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Conexão:", class_="filter-label"),
            ui.input_text("filter_conexao", "", placeholder="Buscar conexão..."),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Status:", class_="filter-label"),
            ui.input_selectize("filter_status", "", choices={}, selected=[], multiple=True, options={"placeholder": "Todos"}),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Emitido PL:", class_="filter-label"),
            ui.input_action_button("filter_emitido_pl_toggle", "Todos", class_="tri-filter-btn tri-filter-none"),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Viabilidade:", class_="filter-label"),
            ui.input_selectize("filter_viabilidade", "", choices={}, selected=[], multiple=True, options={"placeholder": "Todas"}),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Ano Data Solicitação:", class_="filter-label"),
            ui.input_selectize(
                "filter_ano_solicitacao",
                "",
                choices={str(y): str(y) for y in range(2021, 2027)},
                selected=["2026"],
                multiple=True,
                options={"placeholder": "Todos"},
            ),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Ordenar por:", class_="filter-label"),
            ui.input_select("filter_sort", "", choices=_sort_choices_overview(), selected="data_solic_asc"),
            class_="filter-group",
        ),
        ui.input_action_button("btn_reset", "↺ Limpar filtros", class_="filter-reset"),
        id="filters-overview",
        class_="sidebar-section sidebar-filters-section",
        style="display:none;",
    )


def _datacenters_filters_section(prefix="dc", section_id="filters-dc", hidden=True):
    return tags.div(
        tags.div("Filtros", class_="sidebar-section-title"),
        tags.div(
            tags.div("Empreendimento:", class_="filter-label"),
            ui.input_text(f"{prefix}_empr", "", placeholder="Filtrar por nome..."),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Protocolo:", class_="filter-label"),
            ui.input_text(f"{prefix}_proto", "", placeholder="SGA-..."),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Rede:", class_="filter-label"),
            ui.input_selectize(f"{prefix}_rede", "", choices={}, selected=[], multiple=True, options={"placeholder": "Todas"}),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Tensão (kV):", class_="filter-label"),
            ui.input_selectize(f"{prefix}_kv", "", choices={}, selected=[], multiple=True, options={"placeholder": "Todas"}),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Conexão:", class_="filter-label"),
            ui.input_text(f"{prefix}_conexao", "", placeholder="Filtrar conexão..."),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Viabilidade:", class_="filter-label"),
            ui.input_selectize(f"{prefix}_viab", "", choices={}, selected=[], multiple=True, options={"placeholder": "Todas"}),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Status:", class_="filter-label"),
            ui.input_selectize(f"{prefix}_status", "", choices={}, selected=[], multiple=True, options={"placeholder": "Todos"}),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Emitido PL:", class_="filter-label"),
            ui.input_action_button(f"{prefix}_emitido_pl_toggle", "Todos", class_="tri-filter-btn tri-filter-none"),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Ordenar por:", class_="filter-label"),
            ui.input_select(f"{prefix}_sort", "", choices=_sort_choices_dc(), selected="data_asc"),
            class_="filter-group",
        ),
        ui.input_action_button(f"{prefix}_reset", "↺ Limpar filtros", class_="filter-reset"),
        id=section_id,
        class_="sidebar-section sidebar-filters-section",
        style="display:none;" if hidden else None,
    )


def _datacenters_panel_filters_section():
    return tags.div(
        tags.div("Filtros do Painel", class_="sidebar-section-title"),
        tags.div(
            tags.div("Período:", class_="filter-label"),
            ui.input_selectize("dcp_period_years", "", choices={}, selected=[], multiple=True, options={"placeholder": "Todos"}),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Ano de referência:", class_="filter-label"),
            ui.input_select("dcp_year", "", choices={"latest": "Último ano do horizonte"}, selected="latest"),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Rede:", class_="filter-label"),
            tags.div("RB", class_="filter-static-value"),
            class_="filter-group",
        ),
        tags.div(
            tags.div("Tipo:", class_="filter-label"),
            tags.div("SPA", class_="filter-static-value"),
            class_="filter-group",
        ),
        ui.input_action_button("dcp_reset", "↺ Limpar filtros", class_="filter-reset"),
        id="filters-dcp",
        class_="sidebar-section sidebar-filters-section",
    )


def make_sidebar():
    return tags.div(
        # Navegação
        tags.div(
            tags.div("Navegação", class_="sidebar-section-title"),
            ui.input_action_button("nav_overview", "", class_="nav-btn"),
            ui.input_action_button("nav_datacenters", "", class_="nav-btn"),
            ui.input_action_button("nav_datacenters_panel", "", class_="nav-btn active"),
            class_="sidebar-section",
        ),
        tags.div(class_="sidebar-divider"),
        _overview_filters_section(),
        _datacenters_filters_section("dc", "filters-dc", hidden=True),
        _datacenters_filters_section("dcm", "filters-dcm", hidden=True),
        _datacenters_panel_filters_section(),
        class_="app-sidebar",
    )

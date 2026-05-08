"""Lógica reativa e renderizações do Shiny."""

import os
import re
import tempfile
from datetime import datetime

import pandas as pd
from shiny import Inputs, Outputs, Session, reactive, render, ui
from htmltools import HTML, Tag, tags

from .constants import UF_MAP
from .data import (
    PROTOCOLS,
    OVERVIEW_PROTOCOLS,
    DATACENTER_ROWS,
    DATACENTER_YEARS,
    ANALISE_TECNICA_BY_SOLIC,
    CUST_BY_PROTO,
    VIABILIDADES_ENTRIES,
    DOCUMENTOS_BY_SOLIC,
    DC_MUST_BY_PROTO,
)
from .utils import fmt_date, normalize_uf
from .transforms import fmt_mw, compute_rede, compute_prazo_pl, compute_prazo_emissao_ons, clean_text


def _excel_empreendimento_ponto(r):
    """Texto usado nos downloads Excel para a coluna Empreendimento / Ponto.

    Regra:
      - Para SAM, mostrar o ponto de contratação.
      - Para demais casos, usar Empreendimento quando vier preenchido.
      - Se Empreendimento vier vazio/"—", usar o ponto de contratação.
    """
    proto_text = str(r.get("main_protocol") or "").upper()
    empreendimento = str(r.get("empreendimento") or "").strip()
    ponto = str(r.get("ponto_label") or r.get("ponto_instalacao") or "").strip()
    empreendimento_vazio = empreendimento in ("", "—", "-", "None", "nan", "NULL")

    if "SAM" in proto_text:
        return ponto or ("" if empreendimento_vazio else empreendimento)

    if empreendimento_vazio:
        return ponto or ""

    return empreendimento


def _excel_clean(v):
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s in ("", "—", "-", "None", "nan", "NaT", "NULL") else v


def _year_dict_get(d, year):
    if not isinstance(d, dict):
        return {}
    return d.get(year) or d.get(str(year)) or {}


def _apply_manual_must_overrides(proto, year_values):
    """Ajustes pontuais validados manualmente."""
    if str(proto or "").strip().upper() == "SGA-SAM-0117/2026":
        out = {y: dict(vals or {}) for y, vals in (year_values or {}).items()}
        vals_2030 = dict(out.get(2030) or {})
        vals_2030["fora"] = 904.904
        out[2030] = vals_2030
        return out
    return year_values


INICIO_HORIZONTE_LABEL = "Início do horizonte"

_BRAZIL_MAP_PATH = os.path.join(os.path.dirname(__file__), "assets", "brazil_map.svg")
try:
    with open(_BRAZIL_MAP_PATH, "r", encoding="utf-8") as _map_file:
        BRAZIL_MAP_SVG = _map_file.read()
except OSError:
    BRAZIL_MAP_SVG = ""
BRAZIL_MAP_SVG = re.sub(r"<style\b[^>]*>.*?</style>", "", BRAZIL_MAP_SVG, flags=re.S)


def _svg_tag(name, *children, **attrs):
    return Tag(name, *children, **attrs)


def _display_ano_label(label):
    text = str(label or "").strip()
    if text.lower() in ("ano corrente", "inicio do horizonte", "início do horizonte") or "corrente" in text.lower():
        return INICIO_HORIZONTE_LABEL
    return label


def _horizonte_label(status):
    return {
        "current": INICIO_HORIZONTE_LABEL,
        "contractable": "Janela contratável",
        "outside": "Fora do horizonte contratável",
        "before": "Anterior à solicitação",
        "future-empty": "Futuro sem dado",
    }.get(status or "", "")


VIABILIDADE_SGA_MAP = {
    0: "Nenhum",
    1: "Viável",
    2: "Viável com Restrições",
    3: "Viável Condicionado",
    4: "Viável Parcialmente",
    5: "Negado",
}


def _sid_key(value):
    if value is None or pd.isna(value):
        return None
    try:
        return int(value)
    except Exception:
        return value


def _protocol_type(proto):
    p = str(proto or "").strip().upper()
    parts = p.split("-")
    return parts[1] if len(parts) >= 2 and parts[0] == "SGA" else ""


def _document_type_allowed_for_protocol(proto):
    tipo = _protocol_type(proto)
    if tipo == "SFX":
        return {1}
    if tipo == "SAM":
        return {3}
    if tipo in {"SPA", "RPA", "RVA"}:
        return {12}
    if tipo == "SPT":
        return {13}
    return set()


def _overview_document_date(p):
    """Data de emissão oficial via sgacesso.tb_documento; fallback BCA."""
    sid = _sid_key(p.get("id_solicitacao"))
    allowed = _document_type_allowed_for_protocol(p.get("protocolo"))
    datas = []
    if sid is not None and allowed:
        for d in DOCUMENTOS_BY_SOLIC.get(sid, []):
            if d.get("id_documento") in allowed and d.get("num_documento"):
                dt = pd.to_datetime(d.get("din_criacao"), errors="coerce")
                if pd.notna(dt):
                    datas.append(dt)
    if datas:
        return max(datas)
    return pd.to_datetime(p.get("din_emissaodocumento"), errors="coerce")


def _overview_viabilidade_label(p):
    val = p.get("id_viabilidade")
    if val is None or pd.isna(val):
        return "—"
    try:
        return VIABILIDADE_SGA_MAP.get(int(float(val)), str(val))
    except Exception:
        return str(val)


def _overview_viab_pill_class(label):
    text = str(label or "").strip().lower()
    if text in ("", "—", "nenhum"):
        return "viab-pill viab-pendente"
    if "verificar" in text:
        return "viab-pill viab-verificar"
    if "no prazo" in text:
        return "viab-pill viab-no-prazo"
    if "negado" in text:
        return "viab-pill viab-inviavel"
    if "restri" in text or "condicionado" in text or "parcial" in text:
        return "viab-pill viab-condicionado"
    if "viável" in text or "viavel" in text:
        return "viab-pill viab-viavel"
    return "viab-pill viab-pendente"


def _overview_deadline_class(date_str, kind, status="", protocol="", data_emissao_pl=""):
    if not date_str or date_str == "—":
        return ""
    sl = (status or "").lower()
    if "emit" in sl or "concl" in sl or "cancel" in sl or "anul" in sl:
        return ""
    if kind == "pl" and data_emissao_pl and data_emissao_pl != "—":
        return ""
    try:
        prazo = datetime.strptime(str(date_str), "%d/%m/%Y").date()
        hoje = datetime.now().date()
        delta = (prazo - hoje).days
    except Exception:
        return ""
    is_spt = "SPT" in (protocol or "").upper()
    if kind == "ons":
        if is_spt:
            return "blue" if delta < 0 else ""
        if delta <= 2:
            return "red"
        if delta <= 7:
            return "yellow"
        return ""
    if kind == "pl":
        return "yellow" if delta < 0 else ""
    return ""


def _overview_conexao_label(p):
    """Texto da coluna Conexão na Visão Geral.

    Para SAM, usa os pontos de contratação solicitados extraídos de
    tb_aumentomust/campos 946-947. Para os demais, mantém o ponto de
    conexão vindo dos metadados do SGA/BCA.
    """
    proto = str(p.get("protocolo") or "").upper()
    if "SAM" in proto:
        pontos = []
        for pt in p.get("pontos") or []:
            cod = clean_text(pt.get("cod"), "")
            inst = clean_text(pt.get("instalacao"), "")
            if cod and inst:
                label = f"{cod} — {inst}"
            else:
                label = cod or inst
            if label and label not in pontos:
                pontos.append(label)
        if pontos:
            return "; ".join(pontos)
    return clean_text(p.get("dsc_ptoconexao"), p.get("nome") or "—")


def _overview_row_info(p):
    proto = p.get("protocolo") or ""
    sid = _sid_key(p.get("id_solicitacao"))
    analise_pl = ANALISE_TECNICA_BY_SOLIC.get(sid) if sid is not None else None

    data_entrada_pl_dt = pd.to_datetime(analise_pl.get("din_solicitacao"), errors="coerce") if analise_pl else pd.NaT
    data_envio_pl_dt = pd.to_datetime(analise_pl.get("din_envioanalise"), errors="coerce") if analise_pl else pd.NaT
    prazo_pl_dt = compute_prazo_pl(
        analise_pl.get("din_solicitacao") if analise_pl else None,
        analise_pl.get("val_prazo") if analise_pl else None,
    )
    prazo_ons_dt = compute_prazo_emissao_ons(
        p.get("din_aceitesolicitacao"),
        p.get("val_prazoemissao"),
        p.get("val_periodointerrompida"),
    )
    emissao_doc_dt = _overview_document_date(p)

    cust_info = CUST_BY_PROTO.get(proto, {})
    cod_contrato = str(cust_info.get("cod_contrato") or "").strip()
    is_spt = "SPT" in str(proto).upper()
    prazo_cust_dt = pd.NaT
    if pd.notna(emissao_doc_dt):
        prazo_cust_dt = emissao_doc_dt + pd.Timedelta(days=90)

    if is_spt:
        cust_status = "ptdis"
        cust_label = "PTDIS"
    elif cod_contrato:
        cust_status = "assinado"
        cust_label = cod_contrato
    elif pd.notna(prazo_cust_dt):
        if prazo_cust_dt.normalize() >= pd.Timestamp.now().normalize():
            cust_status = "no_prazo"
            cust_label = "No Prazo"
        else:
            cust_status = "nao_assinado"
            cust_label = "Não assinado"
    else:
        cust_status = ""
        cust_label = "—"

    data_solicitacao_dt = pd.to_datetime(p.get("din_solicitacao"), errors="coerce")
    data_solicitacao = fmt_date(data_solicitacao_dt) if pd.notna(data_solicitacao_dt) else "—"
    data_entrada_pl = fmt_date(data_entrada_pl_dt) if pd.notna(data_entrada_pl_dt) else "—"
    data_emissao_pl = fmt_date(data_envio_pl_dt) if pd.notna(data_envio_pl_dt) else "—"
    prazo_pl = fmt_date(prazo_pl_dt) if pd.notna(pd.to_datetime(prazo_pl_dt, errors="coerce")) else "—"
    prazo_ons = fmt_date(prazo_ons_dt) if pd.notna(pd.to_datetime(prazo_ons_dt, errors="coerce")) else "—"
    data_emissao_doc = fmt_date(emissao_doc_dt) if pd.notna(pd.to_datetime(emissao_doc_dt, errors="coerce")) else "—"
    prazo_cust = fmt_date(prazo_cust_dt) if pd.notna(pd.to_datetime(prazo_cust_dt, errors="coerce")) else "—"

    tensao = p.get("tensao") or "—"
    rede = compute_rede(proto, tensao)
    uf = normalize_uf(p.get("nom_uf"))
    conexao = _overview_conexao_label(p)
    status = clean_text(p.get("dsc_status"), "—")
    viab = _overview_viabilidade_label(p)

    return {
        "protocolo": proto,
        "nome": p.get("nome") or p.get("nom_solicitacao") or "—",
        "uf": uf,
        "data_solicitacao": data_solicitacao,
        "data_solicitacao_year": int(data_solicitacao_dt.year) if pd.notna(data_solicitacao_dt) else None,
        "data_entrada_pl": data_entrada_pl,
        "prazo_analise_pl": prazo_pl,
        "prazo_emissao_ons": prazo_ons,
        "rede": rede,
        "tensao": tensao,
        "conexao": conexao,
        "status": status,
        "data_emissao_pl": data_emissao_pl,
        "data_emissao_doc": data_emissao_doc,
        "prazo_cust": prazo_cust,
        "cust_status": cust_status,
        "cust_label": cust_label,
        "viabilidade": viab,
        "n_pontos": len(p.get("pontos") or []),
        "n_periodos": len(p.get("periodos") or []),
        "quebra": len(p.get("periodos") or []) > 1,
    }


def _overview_export_row(info):
    return {
        "Solicitação": info.get("nome") or "",
        "Protocolo": info.get("protocolo") or "",
        "UF": info.get("uf") or "",
        "Data Solic.": info.get("data_solicitacao") or "",
        "Entrada PL": info.get("data_entrada_pl") or "",
        "Prazo PL": info.get("prazo_analise_pl") or "",
        "Prazo ONS": info.get("prazo_emissao_ons") or "",
        "Rede": info.get("rede") or "",
        "kV": info.get("tensao") or "",
        "Conexão": info.get("conexao") or "",
        "Status": info.get("status") or "",
        "Emissão PL": info.get("data_emissao_pl") or "",
        "Emissão Doc.": info.get("data_emissao_doc") or "",
        "Prazo CUST": info.get("prazo_cust") or "",
        "CUST": info.get("cust_label") or "",
        "Viabilidade": info.get("viabilidade") or "",
    }


def _write_overview_excel(path, rows_data):
    """Excel da Visão Geral — respeita exatamente os filtros aplicados."""
    df = pd.DataFrame([_overview_export_row(r) for r in rows_data])

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Visao Geral", index=False)
        ws = writer.sheets["Visao Geral"]
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        header_fill = PatternFill("solid", fgColor="2D5016")
        header_font = Font(color="FFFFFF", bold=True)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        for col_idx, col in enumerate(ws.iter_cols(min_row=1, max_row=ws.max_row), start=1):
            header = ws.cell(row=1, column=col_idx).value
            width = 14
            if header in ("Solicitação", "Conexão"):
                width = 34
            elif header in ("Protocolo", "Status", "CUST", "Viabilidade"):
                width = 22
            elif header in ("UF", "Rede", "kV"):
                width = 10
            ws.column_dimensions[get_column_letter(col_idx)].width = width
            for cell in col:
                cell.alignment = Alignment(vertical="top", wrap_text=True)


def _build_discretizacao_rows(rows_data, years):
    detail_rows = []
    for r in rows_data:
        viab_data = r.get("viabilidade_anos") or {}
        anos_viab = viab_data.get("anos") or {}
        year_values = r.get("year_values") or {}
        year_status = r.get("year_status") or {}
        anos = set()
        for y in years or []:
            try:
                anos.add(int(y))
            except Exception:
                pass
        for source in (year_values, anos_viab, year_status):
            for y in (source or {}).keys():
                try:
                    anos.add(int(y))
                except Exception:
                    pass
        if not anos:
            anos = {None}
        viab_geral = _excel_clean(viab_data.get("viabilidade_geral")) if isinstance(viab_data, dict) else ""
        for ano in sorted(anos, key=lambda x: 9999 if x is None else x):
            must_vals = _year_dict_get(year_values, ano) if ano is not None else {}
            viab_vals = _year_dict_get(anos_viab, ano) if ano is not None else {}
            st_ano = (year_status.get(ano) or year_status.get(str(ano))) if ano is not None else ""
            viab_ano = _excel_clean(viab_vals.get("viabilidade")) or viab_geral or _excel_clean(r.get("viabilidade_resumo"))
            detail_rows.append({
                "Empreendimento / Ponto": _excel_empreendimento_ponto(r),
                "Protocolo": r.get("main_protocol") or "",
                "Ano": ano if ano is not None else "",
                "Status Solicitação": r.get("status") or "",
                "Viabilidade Resumo": r.get("viabilidade_resumo") or "",
                "Viabilidade Ano": viab_ano,
                "Condicionantes / Obras": _excel_clean(viab_vals.get("condicionantes")),
                "SEP": _excel_clean(viab_vals.get("sep")),
                "Limitado Ponta": _excel_clean(viab_vals.get("limitado_ponta")),
                "Limitado FP": _excel_clean(viab_vals.get("limitado_fp")),
                "MUST Ponta Solicitado": must_vals.get("ponta"),
                "MUST FP Solicitado": must_vals.get("fora"),
                "Horizonte": _horizonte_label(st_ano),
                "Data Solicitação": r.get("data_solicitacao") or "",
                "Entrada PL": r.get("data_entrada_pl") or "",
                "Prazo PL": r.get("prazo_analise_pl") or "",
                "Prazo ONS": r.get("prazo_emissao_ons") or "",
                "Emissão PL": r.get("data_emissao_pl") or "",
                "Emissão Doc.": r.get("data_emissao_doc") or "",
                "Prazo CUST": r.get("prazo_cust") or "",
                "CUST": r.get("cust_label") or "",
                "Rede": r.get("rede") or "",
                "kV": r.get("tensao") or "",
                "Conexão": r.get("conexao") or "",
            })
    return detail_rows


def _write_dc_list_excel(path, rows_data):
    """Excel da página DC Lista — reflete EXATAMENTE as colunas da tabela."""
    export = []
    for r in rows_data:
        export.append({
            "Empreendimento / Ponto": _excel_empreendimento_ponto(r),
            "Protocolo": r.get("main_protocol") or "",
            "Data Solicitação": r.get("data_solicitacao") or "",
            "Entrada PL": r.get("data_entrada_pl") or "",
            "Prazo PL": r.get("prazo_analise_pl") or "",
            "Prazo ONS": r.get("prazo_emissao_ons") or "",
            "Rede": r.get("rede") or "",
            "kV": r.get("tensao") or "",
            "Conexão": r.get("conexao") or "",
            "Pico MW": r.get("potencia_max"),
            "Status": r.get("status") or "",
            "Emissão PL": r.get("data_emissao_pl") or "",
            "Emissão Doc.": r.get("data_emissao_doc") or "",
            "Prazo CUST": r.get("prazo_cust") or "",
            "CUST": r.get("cust_label") or "",
        })
    df = pd.DataFrame(export)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="DataCenters", index=False)
        ws = writer.sheets["DataCenters"]
        from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter

        header_fill = PatternFill("solid", fgColor="2D5016")
        header_font = Font(color="FFFFFF", bold=True)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for col_idx, col in enumerate(ws.iter_cols(min_row=1, max_row=ws.max_row), start=1):
            header = ws.cell(row=1, column=col_idx).value
            width = 14
            if header in ("Empreendimento", "Empreendimento / Ponto", "Conexão"):
                width = 30
            elif header in ("Protocolo", "CUST", "Status"):
                width = 18
            ws.column_dimensions[get_column_letter(col_idx)].width = width
            for cell in col:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                if header == "Pico MW":
                    cell.number_format = '#,##0.00'


def _write_dc_matrix_excel(path, rows_data, years):
    """Excel da página DC Matriz — reflete EXATAMENTE as colunas da tabela com todos os anos."""
    export = []
    for r in rows_data:
        row = {
            "Empreendimento / Ponto": _excel_empreendimento_ponto(r),
            "Protocolo": r.get("main_protocol") or "",
            "Data Solicitação": r.get("data_solicitacao") or "",
            "Entrada PL": r.get("data_entrada_pl") or "",
            "Prazo PL": r.get("prazo_analise_pl") or "",
            "Prazo ONS": r.get("prazo_emissao_ons") or "",
            "Rede": r.get("rede") or "",
            "kV": r.get("tensao") or "",
            "Status": r.get("status") or "",
            "Emissão PL": r.get("data_emissao_pl") or "",
            "Emissão Doc.": r.get("data_emissao_doc") or "",
            "Prazo CUST": r.get("prazo_cust") or "",
            "CUST": r.get("cust_label") or "",
        }
        # Anos com Ponta e Fora Ponta
        for y in years:
            vals = (r.get("year_values") or {}).get(y, {})
            row[f"{y} Ponta"] = vals.get("ponta")
            row[f"{y} Fora Ponta"] = vals.get("fora")
        export.append(row)

    df = pd.DataFrame(export)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Matriz Anual", index=False)
        ws = writer.sheets["Matriz Anual"]
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        header_fill = PatternFill("solid", fgColor="2D5016")
        header_font = Font(color="FFFFFF", bold=True)
        fill_current = PatternFill("solid", fgColor="B7E1CD")
        fill_contractable = PatternFill("solid", fgColor="E8F5E0")
        fill_outside = PatternFill("solid", fgColor="FCE4D6")

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        # Aplicar cores por status do ano
        header_to_col = {cell.value: cell.column for cell in ws[1]}
        for excel_row_idx, r in enumerate(rows_data, start=2):
            status_by_year = r.get("year_status", {}) or {}
            for y in years:
                status = status_by_year.get(y, "")
                fill = None
                if status == "current":
                    fill = fill_current
                elif status == "contractable":
                    fill = fill_contractable
                elif status == "outside":
                    fill = fill_outside
                if fill is None:
                    continue
                for suffix in ("Ponta", "Fora Ponta"):
                    col_idx = header_to_col.get(f"{y} {suffix}")
                    if col_idx:
                        ws.cell(row=excel_row_idx, column=col_idx).fill = fill

        for col_idx, col in enumerate(ws.iter_cols(min_row=1, max_row=ws.max_row), start=1):
            header = ws.cell(row=1, column=col_idx).value
            width = 12
            if header in ("Empreendimento", "Empreendimento / Ponto"):
                width = 28
            elif header in ("Protocolo", "CUST", "Status"):
                width = 18
            ws.column_dimensions[get_column_letter(col_idx)].width = width
            for cell in col:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                if isinstance(header, str) and ("Ponta" in header):
                    cell.number_format = '#,##0.00'

        # Aba complementar: discretização anual de viabilidade/condicionantes/SEP.
        # Esta aba havia sido removida por engano na última versão.
        detalhes = pd.DataFrame(_build_discretizacao_rows(rows_data, years))
        detalhes.to_excel(writer, sheet_name="Discretizacao", index=False)
        ws_det = writer.sheets["Discretizacao"]
        ws_det.freeze_panes = "A2"
        ws_det.auto_filter.ref = ws_det.dimensions

        for cell in ws_det[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        for col_idx, col in enumerate(ws_det.iter_cols(min_row=1, max_row=ws_det.max_row), start=1):
            header = ws_det.cell(row=1, column=col_idx).value
            width = 14
            if header in ("Empreendimento / Ponto", "Conexão"):
                width = 32
            elif header in ("Condicionantes / Obras", "SEP"):
                width = 55
            elif header in ("Protocolo", "Status Solicitação", "Viabilidade Resumo", "Viabilidade Ano", "Horizonte"):
                width = 22
            elif header in ("MUST Ponta Solicitado", "MUST FP Solicitado", "Limitado Ponta", "Limitado FP"):
                width = 18
            ws_det.column_dimensions[get_column_letter(col_idx)].width = width
            for cell in col:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                if header in ("MUST Ponta Solicitado", "MUST FP Solicitado", "Limitado Ponta", "Limitado FP"):
                    cell.number_format = '#,##0.00'


def _write_bd_entrada_excel(path, rows_data, viabilidades_existentes):
    """Gera o BD entrada multi-aba com aba 'Pontos' MESTRA.

    Estrutura:
      - 'Pontos' (mestra): Protocolo, Ponto, Empreendimento, Rede, Tensão (kV), Viabilidade Geral
      - Abas auxiliares por ano: Viabilidade, Condicionantes, SEP, Limitado Ponta, Limitado FP,
        MUST Ponta (PTDis), MUST FP (PTDis)
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    VIABILIDADE_VALORES = (
        "Viável", "Viável/Condicionado", "Limitado/Viável/Condicionado",
        "Inviável", "Cancelada", "Anulada", "Em análise",
    )

    all_years = set()
    for r in rows_data:
        for y, vals in (r.get("year_values") or {}).items():
            if vals.get("ponta") is not None or vals.get("fora") is not None:
                try:
                    yi = int(y)
                    if 2024 <= yi <= 2040:
                        all_years.add(yi)
                except Exception:
                    pass
    for entry in (viabilidades_existentes or []):
        for y in (entry.get("anos") or {}).keys():
            try:
                yi = int(y)
                if 2024 <= yi <= 2040:
                    all_years.add(yi)
            except Exception:
                pass
    all_years = sorted(all_years) if all_years else [2024, 2025, 2026, 2027, 2028, 2029, 2030]

    header_fill = PatternFill("solid", fgColor="2D5016")
    year_header_fill = PatternFill("solid", fgColor="4A8C28")
    ptdis_fill = PatternFill("solid", fgColor="7C3AED")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    key_fill = PatternFill("solid", fgColor="FEF3C7")

    viab_by_key = {}
    for entry in (viabilidades_existentes or []):
        key = ((entry.get("protocolo") or "").strip(), (entry.get("ponto") or "").strip())
        viab_by_key[key] = entry

    def _entry_for(r):
        proto = (r.get("main_protocol") or "").strip()
        ponto = (r.get("ponto_label") or r.get("ponto_instalacao") or "").strip()
        return viab_by_key.get((proto, ponto), {}), proto, ponto

    wb = Workbook()
    wb.remove(wb.active)

    ws_pontos = wb.create_sheet("Pontos")
    headers_pontos = ["Protocolo", "Ponto", "Empreendimento", "Rede", "Tensão (kV)", "Viabilidade Geral"]
    ws_pontos.append(headers_pontos)
    for col_idx, h in enumerate(headers_pontos, start=1):
        c = ws_pontos.cell(row=1, column=col_idx)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for r in rows_data:
        entry, proto, ponto = _entry_for(r)
        ws_pontos.append([
            proto,
            ponto,
            r.get("empreendimento", ""),
            r.get("rede", ""),
            r.get("tensao", ""),
            entry.get("viabilidade_geral", ""),
        ])

    last_row = ws_pontos.max_row
    dv_viab = DataValidation(type="list", formula1=f'"{",".join(VIABILIDADE_VALORES)}"', allow_blank=True)
    ws_pontos.add_data_validation(dv_viab)
    if last_row >= 2:
        dv_viab.add(f"F2:F{last_row}")

    dv_rede = DataValidation(type="list", formula1='"DIST,RB,DIT"', allow_blank=True)
    ws_pontos.add_data_validation(dv_rede)
    if last_row >= 2:
        dv_rede.add(f"D2:D{last_row}")

    widths_pontos = {"Protocolo": 22, "Ponto": 35, "Empreendimento": 32, "Rede": 8,
                     "Tensão (kV)": 12, "Viabilidade Geral": 24}
    for col_idx, h in enumerate(headers_pontos, start=1):
        ws_pontos.column_dimensions[get_column_letter(col_idx)].width = widths_pontos.get(h, 14)
    ws_pontos.freeze_panes = "C2"

    def _make_aux(sheet_name, kind_key, dropdown_viab=False, ptdis=False, wide=False):
        ws = wb.create_sheet(sheet_name)
        headers_aux = ["Protocolo", "Ponto"] + [f"Y{y}" for y in all_years]
        ws.append(headers_aux)
        for col_idx, h in enumerate(headers_aux, start=1):
            c = ws.cell(row=1, column=col_idx)
            c.fill = ptdis_fill if (h.startswith("Y") and ptdis) else (year_header_fill if h.startswith("Y") else header_fill)
            c.font = header_font
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        for r in rows_data:
            entry, proto, ponto = _entry_for(r)
            anos_dict = entry.get("anos") or {}
            line = [proto, ponto]
            for y in all_years:
                ano_data = anos_dict.get(y, {}) if isinstance(anos_dict, dict) else {}
                line.append(ano_data.get(kind_key, ""))
            ws.append(line)

        for row_idx in range(2, ws.max_row + 1):
            ws.cell(row=row_idx, column=1).fill = key_fill
            ws.cell(row=row_idx, column=2).fill = key_fill

        if dropdown_viab:
            dv = DataValidation(type="list", formula1=f'"{",".join(VIABILIDADE_VALORES)}"', allow_blank=True)
            ws.add_data_validation(dv)
            lr = ws.max_row
            if lr >= 2:
                for i, _y in enumerate(all_years):
                    col_idx = 3 + i
                    dv.add(f"{get_column_letter(col_idx)}2:{get_column_letter(col_idx)}{lr}")

        ws.column_dimensions["A"].width = 22
        ws.column_dimensions["B"].width = 35
        for i, _y in enumerate(all_years):
            ws.column_dimensions[get_column_letter(3 + i)].width = 35 if wide else 14
        ws.freeze_panes = "C2"

    _make_aux("Viabilidade", "viabilidade", dropdown_viab=True)
    _make_aux("Condicionantes", "condicionantes", wide=True)
    _make_aux("SEP", "sep", wide=True)
    _make_aux("Limitado Ponta", "limitado_ponta")
    _make_aux("Limitado FP", "limitado_fp")
    _make_aux("MUST Ponta (PTDis)", "must_ponta", ptdis=True)
    _make_aux("MUST FP (PTDis)", "must_fora", ptdis=True)

    ws_inst = wb.create_sheet("Instruções")
    instr = [
        ["BD Entrada — Estrutura"], [""],
        ["📌 Para CADASTRAR novo ponto, edite APENAS a aba 'Pontos'."],
        ["📌 Para SAM com vários pontos, repita o protocolo e varie 'Ponto'."],
        ["📌 Nas abas de detalhe, edite apenas as colunas Y2024, Y2025, ..."],
        [""],
        ["Valores aceitos para Viabilidade:"],
        ["  Viável | Viável/Condicionado | Limitado/Viável/Condicionado | Inviável | Cancelada | Anulada | Em análise"],
    ]
    for row in instr:
        ws_inst.append(row)
    ws_inst.column_dimensions["A"].width = 100
    for cell in ws_inst["A"]:
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws_inst.cell(row=1, column=1).font = Font(bold=True, size=14)

    wb.save(path)


def server(input: Inputs, output: Outputs, session: Session):
    # Página inicial: painel executivo de DataCenters.
    _initial_page = "datacenters_panel"
    # State
    current_page = reactive.value(_initial_page)
    selected_proto = reactive.value(None)
    point_idx = reactive.value(0)
    selected_dc = reactive.value(None)
    dc_panel_state = reactive.value("")
    dc_panel_metric = reactive.value("mw")
    dc_panel_chart_type = reactive.value("received")
    dc_status_filter = reactive.value("todos")
    overview_matrix_rows_cache = reactive.value([])
    overview_emitido_pl_filter = reactive.value("")  # "" | "nao" | "sim"
    dc_emitido_pl_filter = reactive.value("")        # "" | "nao" | "sim"
    dcm_emitido_pl_filter = reactive.value("")       # "" | "nao" | "sim"

    def _next_emitido_pl_filter(value):
        return {"": "nao", "nao": "sim", "sim": ""}.get(value or "", "")

    def _emitido_pl_state(data_emissao_pl):
        text = str(data_emissao_pl or "").strip()
        return "nao" if text in ("", "—", "-", "None", "nan", "NaT", "NULL") else "sim"

    def _sync_emitido_pl_button(input_id, value):
        label = {"": "Todos", "nao": "Não", "sim": "Sim"}.get(value or "", "Todos")
        cls = {"": "tri-filter-none", "nao": "tri-filter-nao", "sim": "tri-filter-sim"}.get(value or "", "tri-filter-none")
        script = f"""
        (function() {{
            var el = $('#{input_id}');
            el.removeClass('tri-filter-none tri-filter-nao tri-filter-sim');
            el.addClass('{cls}');
            el.text('{label}');
        }})();
        """
        ui.insert_ui(ui.tags.script(script), selector="body", where="beforeEnd")

    # --- Populate local filter choices for Visão Geral on startup ---
    @reactive.effect
    def _init_filters():
        ufs = {}
        redes = {}
        tensoes = {}
        statuses = {}
        viabilidades = {}
        anos = set()

        for p in OVERVIEW_PROTOCOLS:
            info = _overview_row_info(p)

            uf = info.get("uf")
            if uf and uf != "—":
                nome_uf = UF_MAP.get(uf, uf)
                ufs[uf] = f"{uf} — {nome_uf}"

            rede = info.get("rede")
            if rede and rede != "—":
                redes[rede] = rede

            tensao = info.get("tensao")
            if tensao and tensao != "—":
                tensoes[str(tensao)] = f"{tensao} kV"

            status = info.get("status")
            if status and status != "—":
                statuses[status] = status

            viab = info.get("viabilidade")
            if viab and viab != "—":
                viabilidades[viab] = viab

            ano = info.get("data_solicitacao_year")
            if ano:
                anos.add(int(ano))

        def _sort_kv(item):
            key, _label = item
            try:
                return float(str(key).replace(",", "."))
            except Exception:
                return 0.0

        ui.update_selectize("filter_uf", choices=dict(sorted(ufs.items())), selected=[])
        ui.update_selectize("filter_rede", choices=dict(sorted(redes.items())), selected=[])
        ui.update_selectize("filter_tensao", choices=dict(sorted(tensoes.items(), key=_sort_kv)), selected=[])
        ui.update_selectize("filter_status", choices=dict(sorted(statuses.items())), selected=[])
        ui.update_selectize("filter_viabilidade", choices=dict(sorted(viabilidades.items())), selected=[])

        anos_choices = {str(y): str(y) for y in sorted(anos) if 2021 <= int(y) <= 2026}
        if not anos_choices:
            anos_choices = {str(y): str(y) for y in range(2021, 2027)}
        selected_anos = ["2026"] if "2026" in anos_choices else []
        ui.update_selectize("filter_ano_solicitacao", choices=anos_choices, selected=selected_anos)

    # --- Filtered data: Visão Geral only ---
    @reactive.calc
    def filtered_data():
        def _as_list(value):
            if value is None:
                return []
            if isinstance(value, (list, tuple, set)):
                return [str(x) for x in value if str(x).strip()]
            text = str(value).strip()
            return [text] if text else []

        def _contains(haystack, needle):
            if not needle:
                return True
            return needle.lower() in str(haystack or "").lower()

        def _parse_dt(s):
            if not s or s == "—":
                return datetime.max
            try:
                return datetime.strptime(str(s), "%d/%m/%Y")
            except Exception:
                return datetime.max

        try:
            f_nome = (input.filter_nome() or "").strip().lower()
        except Exception:
            f_nome = ""
        try:
            f_proto = (input.filter_protocolo() or "").strip().lower()
        except Exception:
            f_proto = ""
        try:
            f_conexao = (input.filter_conexao() or "").strip().lower()
        except Exception:
            f_conexao = ""

        f_ufs = _as_list(input.filter_uf())
        f_redes = _as_list(input.filter_rede())
        f_tensoes = _as_list(input.filter_tensao())
        f_statuses = _as_list(input.filter_status())
        f_viabilidades = _as_list(input.filter_viabilidade())
        try:
            f_anos = [int(x) for x in _as_list(input.filter_ano_solicitacao())]
        except Exception:
            f_anos = []
        try:
            f_sort = input.filter_sort() or "data_solic_asc"
        except Exception:
            f_sort = "data_solic_asc"
        f_emitido_pl = overview_emitido_pl_filter.get()

        result = []
        for p in OVERVIEW_PROTOCOLS:
            info = _overview_row_info(p)

            if f_nome and not _contains(info.get("nome"), f_nome):
                continue
            if f_proto and not _contains(info.get("protocolo"), f_proto):
                continue
            if f_conexao and not _contains(info.get("conexao"), f_conexao):
                continue
            if f_ufs and info.get("uf") not in f_ufs:
                continue
            if f_redes and info.get("rede") not in f_redes:
                continue
            if f_tensoes and str(info.get("tensao", "")) not in f_tensoes:
                continue
            if f_statuses and info.get("status") not in f_statuses:
                continue
            if f_viabilidades and info.get("viabilidade") not in f_viabilidades:
                continue
            if f_anos and info.get("data_solicitacao_year") not in f_anos:
                continue
            if f_emitido_pl and _emitido_pl_state(info.get("data_emissao_pl")) != f_emitido_pl:
                continue

            result.append(info)

        sort_map = {
            "data_solic_desc": (lambda r: _parse_dt(r.get("data_solicitacao")), True),
            "data_solic_asc": (lambda r: _parse_dt(r.get("data_solicitacao")), False),
            "entrada_pl_desc": (lambda r: _parse_dt(r.get("data_entrada_pl")), True),
            "entrada_pl_asc": (lambda r: _parse_dt(r.get("data_entrada_pl")), False),
            "prazo_pl_desc": (lambda r: _parse_dt(r.get("prazo_analise_pl")), True),
            "prazo_pl_asc": (lambda r: _parse_dt(r.get("prazo_analise_pl")), False),
            "prazo_ons_desc": (lambda r: _parse_dt(r.get("prazo_emissao_ons")), True),
            "prazo_ons_asc": (lambda r: _parse_dt(r.get("prazo_emissao_ons")), False),
            "emissao_pl_desc": (lambda r: _parse_dt(r.get("data_emissao_pl")), True),
            "emissao_pl_asc": (lambda r: _parse_dt(r.get("data_emissao_pl")), False),
            "emissao_doc_desc": (lambda r: _parse_dt(r.get("data_emissao_doc")), True),
            "emissao_doc_asc": (lambda r: _parse_dt(r.get("data_emissao_doc")), False),
            "prazo_cust_desc": (lambda r: _parse_dt(r.get("prazo_cust")), True),
            "prazo_cust_asc": (lambda r: _parse_dt(r.get("prazo_cust")), False),
            "nome_asc": (lambda r: str(r.get("nome") or "").lower(), False),
            "nome_desc": (lambda r: str(r.get("nome") or "").lower(), True),
            "protocolo_asc": (lambda r: str(r.get("protocolo") or ""), False),
            "protocolo_desc": (lambda r: str(r.get("protocolo") or ""), True),
        }
        key_fn, reverse = sort_map.get(f_sort, sort_map["data_solic_asc"])
        result.sort(key=key_fn, reverse=reverse)
        return result

    # --- Navigation ---
    @reactive.effect
    @reactive.event(input.nav_overview)
    def _go_overview():
        current_page.set("overview")

    @reactive.effect
    @reactive.event(input.nav_datacenters)
    def _go_datacenters():
        current_page.set("datacenters")

    @reactive.effect
    @reactive.event(input.nav_datacenters_panel)
    def _go_datacenters_panel():
        current_page.set("datacenters_panel")

    # --- DC: row click → detail ---
    @reactive.effect
    @reactive.event(input.selected_dc_item)
    def _on_dc_row_click():
        item = input.selected_dc_item()
        if item:
            selected_dc.set(item)
            current_page.set("datacenters_detail")

    @reactive.effect
    @reactive.event(input.btn_back_dc)
    def _go_back_dc():
        current_page.set("datacenters")

    # --- DC: botão MUST → página de detalhe MUST do protocolo ---
    @reactive.effect
    @reactive.event(input.dc_open_must)
    def _open_must_from_dc():
        item = input.dc_open_must()
        if not item:
            return
        # Encontrar a linha DC e o protocolo MUST correspondente
        r = next((x for x in DATACENTER_ROWS if str(x["item"]) == str(item)), None)
        if not r:
            return
        # Tentar achar protocolo presente no PROTOCOLS (que tem dados MUST)
        proto_must = None
        for proto_candidate in [r.get("fonte_must"), r.get("main_protocol")] + (r.get("related") or "").split(","):
            proto_candidate = (proto_candidate or "").strip()
            if proto_candidate and any(p["protocolo"] == proto_candidate for p in PROTOCOLS):
                proto_must = proto_candidate
                break
        if proto_must:
            selected_proto.set(proto_must)
            point_idx.set(0)
            current_page.set("detail")

    # --- Visão Geral: botão "Solicitações com todos os valores" ---
    @reactive.effect
    @reactive.event(input.btn_overview_matrix)
    def _go_overview_matrix():
        current_page.set("overview_matrix")

    @reactive.effect
    @reactive.event(input.btn_back_overview_matrix)
    def _back_from_overview_matrix():
        current_page.set("overview")

    # --- DC: botão "Solicitações com todos os valores" ---
    @reactive.effect
    @reactive.event(input.btn_dc_matrix)
    def _go_dc_matrix():
        current_page.set("datacenters_matrix")

    @reactive.effect
    @reactive.event(input.btn_back_matrix)
    def _back_from_matrix():
        current_page.set("datacenters")

    # --- DC: chip filters por status real ---
    @reactive.effect
    @reactive.event(input.dc_filter_all)
    def _(): dc_status_filter.set("todos")

    @reactive.effect
    @reactive.event(input.dc_filter_emitidos)
    def _(): dc_status_filter.set("emitidos")

    @reactive.effect
    @reactive.event(input.dc_filter_andamento)
    def _(): dc_status_filter.set("andamento")

    @reactive.effect
    @reactive.event(input.dc_filter_interrompidos)
    def _(): dc_status_filter.set("interrompidos")

    @reactive.effect
    @reactive.event(input.dc_filter_cancelados)
    def _(): dc_status_filter.set("cancelados")

    @reactive.effect
    @reactive.event(input.dc_filter_anulados)
    def _(): dc_status_filter.set("anulados")

    # --- Filtros triestado: Emitido PL ---
    @reactive.effect
    @reactive.event(input.filter_emitido_pl_toggle)
    def _toggle_overview_emitido_pl():
        overview_emitido_pl_filter.set(_next_emitido_pl_filter(overview_emitido_pl_filter.get()))

    @reactive.effect
    @reactive.event(input.dc_emitido_pl_toggle)
    def _toggle_dc_emitido_pl():
        dc_emitido_pl_filter.set(_next_emitido_pl_filter(dc_emitido_pl_filter.get()))

    @reactive.effect
    @reactive.event(input.dcm_emitido_pl_toggle)
    def _toggle_dcm_emitido_pl():
        dcm_emitido_pl_filter.set(_next_emitido_pl_filter(dcm_emitido_pl_filter.get()))

    @reactive.effect
    def _sync_emitido_pl_filters_ui():
        _sync_emitido_pl_button("filter_emitido_pl_toggle", overview_emitido_pl_filter.get())
        _sync_emitido_pl_button("dc_emitido_pl_toggle", dc_emitido_pl_filter.get())
        _sync_emitido_pl_button("dcm_emitido_pl_toggle", dcm_emitido_pl_filter.get())

    # --- DC: botões de reset filtros ---
    @reactive.effect
    @reactive.event(input.dc_reset)
    def _():
        ui.update_text("dc_empr", value="")
        ui.update_text("dc_proto", value="")
        ui.update_text("dc_conexao", value="")
        ui.update_selectize("dc_rede", selected=[])
        ui.update_selectize("dc_kv", selected=[])
        ui.update_selectize("dc_viab", selected=[])
        ui.update_selectize("dc_status", selected=[])
        ui.update_select("dc_sort", selected="data_asc")
        dc_emitido_pl_filter.set("")

    @reactive.effect
    @reactive.event(input.dcm_reset)
    def _():
        ui.update_text("dcm_empr", value="")
        ui.update_text("dcm_proto", value="")
        ui.update_text("dcm_conexao", value="")
        ui.update_selectize("dcm_rede", selected=[])
        ui.update_selectize("dcm_kv", selected=[])
        ui.update_selectize("dcm_viab", selected=[])
        ui.update_selectize("dcm_status", selected=[])
        ui.update_select("dcm_sort", selected="data_asc")
        dcm_emitido_pl_filter.set("")

    @reactive.effect
    @reactive.event(input.dcp_reset)
    def _():
        years = _dcp_horizon_years()
        ui.update_selectize("dcp_period_years", selected=[str(y) for y in years])
        ui.update_select("dcp_year", selected="latest")
        dc_panel_state.set("")

    @reactive.effect
    @reactive.event(input.dcp_state_click)
    def _toggle_dc_panel_state():
        uf = str(input.dcp_state_click() or "").strip().upper()
        if not uf or uf == dc_panel_state.get():
            dc_panel_state.set("")
        elif uf in UF_MAP:
            dc_panel_state.set(uf)

    @reactive.effect
    @reactive.event(input.dcp_metric)
    def _toggle_dc_panel_metric():
        metric = str(input.dcp_metric() or "").strip()
        if metric in ("mw", "projects"):
            dc_panel_metric.set(metric)

    @reactive.effect
    @reactive.event(input.dcp_chart_type)
    def _toggle_dc_panel_chart_type():
        chart_type = str(input.dcp_chart_type() or "").strip()
        if chart_type in ("received", "possible"):
            dc_panel_chart_type.set(chart_type)

    @reactive.effect
    @reactive.event(input.selected_protocol)
    def _on_row_click():
        proto = input.selected_protocol()
        selected_proto.set(proto)
        point_idx.set(0)
        current_page.set("detail")

    @reactive.effect
    @reactive.event(input.btn_back)
    def _go_back():
        current_page.set("overview")

    @reactive.effect
    @reactive.event(input.btn_reset)
    def _reset_filters():
        ui.update_text("filter_nome", value="")
        ui.update_text("filter_protocolo", value="")
        ui.update_selectize("filter_uf", selected=[])
        ui.update_selectize("filter_rede", selected=[])
        ui.update_selectize("filter_tensao", selected=[])
        ui.update_text("filter_conexao", value="")
        ui.update_selectize("filter_status", selected=[])
        ui.update_selectize("filter_viabilidade", selected=[])
        ui.update_selectize("filter_ano_solicitacao", selected=["2026"])
        ui.update_select("filter_sort", selected="data_solic_asc")
        overview_emitido_pl_filter.set("")

    @reactive.effect
    @reactive.event(input.selected_point_idx)
    def _on_point_click():
        point_idx.set(input.selected_point_idx())

    # --- Update nav button styles ---
    @reactive.effect
    def _update_nav_styles():
        page = current_page.get()
        script = "$('#nav_overview,#nav_datacenters,#nav_datacenters_panel').removeClass('active');"
        if page in ("overview", "overview_matrix", "detail"):
            script += "$('#nav_overview').addClass('active');"
        elif page == "datacenters_panel":
            script += "$('#nav_datacenters_panel').addClass('active');"
        else:  # datacenters or datacenters_detail or datacenters_matrix
            script += "$('#nav_datacenters').addClass('active');"

        # Mostrar/esconder blocos de filtros da sidebar conforme a página
        script += "$('.sidebar-filters-section').css('display', 'none');"
        if page in ("overview", "overview_matrix"):
            script += "$('#filters-overview').css('display', 'block');"
        elif page == "datacenters":
            script += "$('#filters-dc').css('display', 'block');"
        elif page == "datacenters_matrix":
            script += "$('#filters-dcm').css('display', 'block');"
        elif page == "datacenters_panel":
            script += "$('#filters-dcp').css('display', 'block');"

        # Mostrar/esconder páginas DataCenters conforme a navegação
        script += "$('#dc-list-wrapper, #dc-matrix-wrapper').css('display', 'none');"
        if page == "datacenters":
            script += "$('#dc-list-wrapper').css('display', 'block');"
        elif page == "datacenters_matrix":
            script += "$('#dc-matrix-wrapper').css('display', 'block');"
        ui.insert_ui(ui.tags.script(script), selector="body", where="beforeEnd")

    # --- OVERVIEW PAGE ---
    def _build_overview_row(info):
        proto = info.get("protocolo") or ""
        status_real = (info.get("status") or "").strip()
        sl = status_real.lower()
        if not status_real or status_real == "—":
            status_class = "status-pill status-miss"; status_label = "—"
        elif "anul" in sl:
            status_class = "status-pill status-anulada"; status_label = status_real
        elif "cancel" in sl:
            status_class = "status-pill status-miss"; status_label = status_real
        elif "emit" in sl or "concl" in sl or "aprovado" in sl:
            status_class = "status-pill status-ok"; status_label = status_real
        elif "andamento" in sl or "análise" in sl or "analise" in sl:
            status_class = "status-pill status-warn"; status_label = status_real
        else:
            status_class = "status-pill status-warn"; status_label = status_real

        rede = info.get("rede") or "—"
        rede_class_map = {"DIST": "rede-dist", "RB": "rede-rb", "DIT": "rede-dit"}
        rede_class = rede_class_map.get(rede, "rede-empty")

        pl_cls = _overview_deadline_class(
            info.get("prazo_analise_pl"),
            "pl",
            status=info.get("status"),
            protocol=proto,
            data_emissao_pl=info.get("data_emissao_pl"),
        )
        ons_cls = _overview_deadline_class(
            info.get("prazo_emissao_ons"),
            "ons",
            status=info.get("status"),
            protocol=proto,
        )
        pl_full_class = "date-cell prazo-pl" + (f" prazo-{pl_cls}" if pl_cls else "")
        ons_full_class = "date-cell prazo-ons" + (f" prazo-{ons_cls}" if ons_cls else "")

        cust_label = info.get("cust_label", "—")
        cust_status_v = info.get("cust_status", "")
        cust_pill_class = {
            "assinado": "cust-pill cust-assinado",
            "no_prazo": "cust-pill cust-no-prazo",
            "nao_assinado": "cust-pill cust-nao-assinado",
            "ptdis": "cust-pill cust-ptdis",
            "inviavel": "cust-pill cust-inviavel",
            "verificar": "cust-pill cust-verificar",
        }.get(cust_status_v, "cust-pill")

        nome = info.get("nome") or "—"
        conexao = info.get("conexao") or "—"
        viab = info.get("viabilidade") or "—"

        return tags.tr(
            tags.td(tags.div(nome, class_="dc-empr-name", title=nome)),
            tags.td(proto or "—", style="font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--green-dark); font-weight:600; text-align:center;"),
            tags.td(info.get("uf") or "—", style="text-align:center; font-weight:700; color:var(--text-mid);"),
            tags.td(info.get("data_solicitacao") or "—", class_="date-cell", style="text-align:center;"),
            tags.td(info.get("data_entrada_pl") or "—", class_="date-cell", style="text-align:center;"),
            tags.td(info.get("prazo_analise_pl") or "—", class_=pl_full_class, style="text-align:center;"),
            tags.td(info.get("prazo_emissao_ons") or "—", class_=ons_full_class, style="text-align:center;"),
            tags.td(tags.span(rede, class_=f"rede-pill {rede_class}"), style="text-align:center;"),
            tags.td(info.get("tensao") or "—", style="text-align:center;"),
            tags.td(conexao[:70] + ("…" if len(conexao) > 70 else ""), class_="text-col", style="font-size:12px; color:var(--text-mid);", title=conexao),
            tags.td(tags.span(status_label, class_=status_class, title=status_real), style="text-align:center;"),
            tags.td(info.get("data_emissao_pl") or "—", class_="date-cell", style="text-align:center;"),
            tags.td(info.get("data_emissao_doc") or "—", class_="date-cell", style="text-align:center;"),
            tags.td(info.get("prazo_cust") or "—", class_="date-cell", style="text-align:center;"),
            tags.td(tags.span(cust_label, class_=cust_pill_class), style="text-align:center;"),
            tags.td(tags.span(viab, class_=_overview_viab_pill_class(viab)), style="text-align:center;"),
            **{"data-proto": proto},
        )

    @output
    @render.ui
    def overview_page():
        if current_page.get() != "overview":
            return tags.div(style="display:none")

        data = filtered_data()

        def _classify_overview_status(s):
            sl = (s or "").lower()
            if "anul" in sl:
                return "anulado"
            if "cancel" in sl:
                return "cancelado"
            if "interromp" in sl:
                return "interrompido"
            if "emit" in sl or "concl" in sl or "aprovado" in sl or "finaliz" in sl:
                return "emitido"
            return "andamento"

        total_emitidos = sum(1 for r in data if _classify_overview_status(r.get("status")) == "emitido")
        total_andamento = sum(1 for r in data if _classify_overview_status(r.get("status")) == "andamento")
        total_interrompidos = sum(1 for r in data if _classify_overview_status(r.get("status")) == "interrompido")
        total_cancelados = sum(1 for r in data if _classify_overview_status(r.get("status")) == "cancelado")
        total_anulados = sum(1 for r in data if _classify_overview_status(r.get("status")) == "anulado")

        return tags.div(
            tags.div("Visão Geral", class_="page-title"),
            tags.div("Todos os protocolos SGA — quando houver detalhamento de MUST, clique em uma linha para ver o detalhe", class_="page-subtitle"),
            tags.div(
                tags.div(
                    tags.div("🗂️", class_="stat-icon"),
                    tags.div(str(len(data)), class_="stat-value"),
                    tags.div("Nº Solicitações", class_="stat-label"),
                    class_="stat-card green",
                ),
                tags.div(
                    tags.div("✓", class_="stat-icon"),
                    tags.div(str(total_emitidos), class_="stat-value"),
                    tags.div("Emitidos", class_="stat-label"),
                    class_="stat-card green",
                ),
                tags.div(
                    tags.div("⚙", class_="stat-icon"),
                    tags.div(str(total_andamento), class_="stat-value"),
                    tags.div("Em andamento", class_="stat-label"),
                    class_="stat-card amber",
                ),
                tags.div(
                    tags.div("⏸", class_="stat-icon"),
                    tags.div(str(total_interrompidos), class_="stat-value"),
                    tags.div("Interrompidos", class_="stat-label"),
                    class_="stat-card amber",
                ),
                tags.div(
                    tags.div("✕", class_="stat-icon"),
                    tags.div(str(total_cancelados), class_="stat-value"),
                    tags.div("Cancelados", class_="stat-label"),
                    class_="stat-card purple",
                ),
                tags.div(
                    tags.div("⊘", class_="stat-icon"),
                    tags.div(str(total_anulados), class_="stat-value"),
                    tags.div("Anulados", class_="stat-label"),
                    class_="stat-card purple",
                ),
                class_="cards-row",
                style="grid-template-columns: repeat(6, 1fr);",
            ),
            tags.div(
                tags.div(
                    tags.span("Protocolos", class_="panel-title"),
                    tags.div(
                        tags.span(f"{len(data)} registros", class_="panel-badge"),
                        ui.input_action_button("btn_overview_matrix", "📊 Solicitações com todos os valores solicitados", class_="dc-btn-primary", style="margin:0; padding:4px 10px;"),
                        ui.download_button("download_overview", "⬇ Excel", class_="back-btn", style="margin:0; padding:4px 10px;"),
                        style="display:flex; align-items:center; gap:8px;",
                    ),
                    class_="panel-header",
                ),
                tags.table(
                    tags.thead(
                        tags.tr(
                            tags.th("Solicitação"),
                            tags.th("Protocolo", style="text-align:center;"),
                            tags.th("UF", style="text-align:center;"),
                            tags.th("Data Solic.", style="text-align:center; font-size:10px;", title="Data da Solicitação"),
                            tags.th("Entrada PL", style="text-align:center; font-size:10px;", title="Data de chegada na PL para análise técnica"),
                            tags.th("Prazo PL", style="text-align:center; font-size:10px;", title="Prazo Análise Técnica PL"),
                            tags.th("Prazo ONS", style="text-align:center; font-size:10px;", title="Prazo Emissão PA - ONS"),
                            tags.th("Rede", style="text-align:center;"),
                            tags.th("kV", style="text-align:center;"),
                            tags.th("Conexão"),
                            tags.th("Status", style="text-align:center;"),
                            tags.th("Emissão PL", style="text-align:center; font-size:10px;", title="Data em que a PL emitiu"),
                            tags.th("Emissão Doc.", style="text-align:center; font-size:10px;", title="Data real da emissão do documento"),
                            tags.th("Prazo CUST", style="text-align:center; font-size:10px;", title="Data limite para assinatura do CUST"),
                            tags.th("CUST", style="text-align:center; font-size:10px;"),
                            tags.th("Viabilidade", style="text-align:center;", title="inbound.sgacesso.tb_solicitacao.id_viabilidade"),
                        )
                    ),
                    tags.tbody(*[_build_overview_row(r) for r in data]),
                    class_="dc-list-table overview-list-table proto-table",
                ),
                class_="dc-card-table",
            ),
        )

    # --- DOWNLOAD VISÃO GERAL (respeita filtros aplicados) ---
    @render.download(
        filename=lambda: f"visao_geral_protocolos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    def download_overview():
        rows = filtered_data()
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp_path = tmp.name
            _write_overview_excel(tmp_path, rows)
            with open(tmp_path, "rb") as f:
                yield f.read()
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)


    # --- MATRIZ VISÃO GERAL: valores solicitados por ano ---
    def _to_overview_number(v):
        if v is None:
            return None
        s_val = str(v).strip()
        if s_val in ("", "—", "-", "None", "nan", "NULL"):
            return None
        try:
            return float(s_val.replace(".", "").replace(",", "."))
        except Exception:
            try:
                return float(s_val)
            except Exception:
                return None

    def _overview_protocol_lookup():
        return {p.get("protocolo"): p for p in PROTOCOLS}

    def _overview_year_values(info, ponto_key=None):
        proto = info.get("protocolo")
        p = _overview_protocol_lookup().get(proto, {})
        base_year = info.get("data_solicitacao_year")
        year_values = {}
        year_status = {}

        def _year_from_label(label):
            if isinstance(label, int):
                return label
            text = str(label or "")
            if text.isdigit() and len(text) == 4:
                return int(text)
            if base_year:
                if "Corrente" in text or "horizonte" in text.lower():
                    return int(base_year)
                if text.startswith("Ano "):
                    try:
                        n = int(text.split()[-1])
                        return int(base_year) + (n - 1)
                    except Exception:
                        return None
            return None

        def _iter_vals(vals, selected_key=None):
            if isinstance(vals, dict):
                if selected_key is None:
                    return vals.values()

                if selected_key in vals:
                    return [vals.get(selected_key)]

                # Fallback para compatibilidade com chaves antigas por código ou
                # eventuais tuplas reconstruídas com o mesmo código/instalação.
                sel_cod = str(selected_key[0] if isinstance(selected_key, tuple) and len(selected_key) > 0 else selected_key or "").strip()
                sel_inst = str(selected_key[1] if isinstance(selected_key, tuple) and len(selected_key) > 1 else "").strip()
                matches = []
                for key, value in vals.items():
                    if isinstance(key, tuple):
                        key_cod = str(key[0] if len(key) > 0 else "").strip()
                        key_inst = str(key[1] if len(key) > 1 else "").strip()
                        if key_cod == sel_cod and key_inst == sel_inst:
                            matches.append(value)
                    elif str(key).strip() == sel_cod:
                        matches.append(value)
                return matches

            if isinstance(vals, (list, tuple, set)):
                return vals
            return [vals]

        for per in p.get("periodos") or []:
            for label, vals in (per.get("must") or {}).items():
                year = _year_from_label(label)
                if year is None:
                    continue
                year_values.setdefault(year, {"ponta": None, "fora": None})
                for tipo in ("ponta", "fora"):
                    nums = [_to_overview_number(v) for v in _iter_vals((vals or {}).get(tipo, {}), ponto_key)]
                    nums = [n for n in nums if n is not None]
                    if nums:
                        curr = year_values[year].get(tipo)
                        year_values[year][tipo] = max(nums) if curr is None else max(curr, max(nums))

        # SPA/RPA/RVA também podem ter valores solicitados em
        # tb_mustpordisteuniconsumidora. Para a Visão Geral ampliada, usar
        # esses valores quando o protocolo não tiver modelo em tb_aumentomust.
        if not year_values:
            dc_must = DC_MUST_BY_PROTO.get(proto, {})
            for year_raw, vals in (dc_must.get("year_values") or {}).items():
                try:
                    year = int(year_raw)
                except Exception:
                    continue
                year_values.setdefault(year, {"ponta": None, "fora": None})
                for tipo in ("ponta", "fora"):
                    num = _to_overview_number((vals or {}).get(tipo))
                    if num is not None:
                        curr = year_values[year].get(tipo)
                        year_values[year][tipo] = num if curr is None else max(curr, num)

        year_values = _apply_manual_must_overrides(proto, year_values)

        if base_year:
            limit_year = int(base_year) + 3
            for y, vals in year_values.items():
                has_data = vals.get("ponta") is not None or vals.get("fora") is not None
                if y == int(base_year):
                    year_status[y] = "current"
                elif int(base_year) < y <= limit_year:
                    year_status[y] = "contractable"
                elif y > limit_year:
                    year_status[y] = "outside" if has_data else "future-empty"
                else:
                    year_status[y] = "before"
        return year_values, year_status

    def _overview_point_label(point):
        cod = clean_text((point or {}).get("cod"), "")
        inst = clean_text((point or {}).get("instalacao"), "")
        if cod and inst:
            return f"{cod} — {inst}"
        return cod or inst or "—"

    def _overview_protocol_points(p):
        points = []
        seen = set()
        for pt in (p or {}).get("pontos") or []:
            cod = clean_text(pt.get("cod"), "")
            inst = clean_text(pt.get("instalacao"), "")
            key = (cod, inst)
            if key == ("", "") or key in seen:
                continue
            seen.add(key)
            points.append({"cod": cod, "instalacao": inst, "key": key, "label": _overview_point_label({"cod": cod, "instalacao": inst})})
        return points

    def _overview_matrix_rows():
        rows = []
        lookup = _overview_protocol_lookup()
        for info in filtered_data():
            proto = info.get("protocolo")
            p = lookup.get(proto, {})
            points = _overview_protocol_points(p)

            # Na matriz da Visão Geral, protocolos com múltiplos pontos de
            # conexão precisam abrir uma linha por ponto, usando o máximo anual
            # de Ponta/Fora Ponta daquele ponto.
            if len(points) > 1:
                for point in points:
                    yv, ys = _overview_year_values(info, point["key"])
                    row = dict(info)
                    row["conexao"] = point["label"]
                    row["overview_point_key"] = point["key"]
                    row["year_values"] = yv
                    row["year_status"] = ys
                    rows.append(row)
            else:
                point_key = points[0]["key"] if points else None
                yv, ys = _overview_year_values(info, point_key)
                row = dict(info)
                if points:
                    row["conexao"] = points[0]["label"]
                    row["overview_point_key"] = point_key
                row["year_values"] = yv
                row["year_status"] = ys
                rows.append(row)
        return rows

    def _overview_matrix_all_years(rows):
        years = set()
        for r in rows:
            for y, vals in (r.get("year_values") or {}).items():
                if vals.get("ponta") is not None or vals.get("fora") is not None:
                    try:
                        years.add(int(y))
                    except Exception:
                        pass
        return sorted(years) if years else list(range(2021, 2027))

    def _build_overview_matrix_row(r, all_years):
        year_vals = r.get("year_values") or {}
        year_status = r.get("year_status") or {}
        rede = r.get("rede") or "—"
        rede_class_map = {"DIST": "rede-dist", "RB": "rede-rb", "DIT": "rede-dit"}
        rede_class = rede_class_map.get(rede, "rede-empty")

        status_real = (r.get("status") or "").strip()
        sl = status_real.lower()
        if not status_real or status_real == "—":
            status_class = "status-pill status-miss"; status_label = "—"
        elif "anul" in sl:
            status_class = "status-pill status-anulada"; status_label = status_real
        elif "cancel" in sl:
            status_class = "status-pill status-miss"; status_label = status_real
        elif "emit" in sl or "concl" in sl or "aprovado" in sl:
            status_class = "status-pill status-ok"; status_label = status_real
        elif "andamento" in sl or "análise" in sl or "analise" in sl:
            status_class = "status-pill status-warn"; status_label = status_real
        else:
            status_class = "status-pill status-warn"; status_label = status_real

        year_cells = []
        for y in all_years:
            vals = year_vals.get(y, {})
            p_val = vals.get("ponta")
            f_val = vals.get("fora")
            st = year_status.get(y, "")
            base_cls = f"matrix-cell {st}" if st else "matrix-cell"
            year_cells.append(tags.td(fmt_mw(p_val) if p_val is not None else "—", class_=f"{base_cls} {'val-ponta' if p_val is not None else 'val-empty'}"))
            year_cells.append(tags.td(fmt_mw(f_val) if f_val is not None else "—", class_=f"{base_cls} {'val-fp' if f_val is not None else 'val-empty'}"))

        viab = r.get("viabilidade") or "—"
        return tags.tr(
            tags.td(tags.div(r.get("nome") or "—", class_="dc-empr-name", title=r.get("nome") or "—")),
            tags.td(r.get("protocolo") or "—", style="font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--green-dark); font-weight:600; text-align:center;"),
            tags.td(r.get("conexao") or "—", class_="overview-matrix-conexao", title=r.get("conexao") or "—"),
            tags.td("⋯", class_="matrix-toggle-spacer", title="Colunas agrupadas"),
            tags.td(r.get("uf") or "—", class_="matrix-collapsible-col", style="text-align:center; font-weight:700; color:var(--text-mid);"),
            tags.td(r.get("data_solicitacao") or "—", class_="date-cell matrix-collapsible-col", style="text-align:center;"),
            tags.td(r.get("data_entrada_pl") or "—", class_="date-cell matrix-collapsible-col", style="text-align:center;"),
            tags.td(tags.span(rede, class_=f"rede-pill {rede_class}"), class_="matrix-collapsible-col", style="text-align:center;"),
            tags.td(r.get("tensao") or "—", class_="matrix-collapsible-col", style="text-align:center;"),
            tags.td(tags.span(status_label, class_=status_class, title=status_real), class_="matrix-collapsible-col", style="text-align:center;"),
            tags.td(r.get("data_emissao_pl") or "—", class_="date-cell matrix-collapsible-col", style="text-align:center;"),
            tags.td(r.get("data_emissao_doc") or "—", class_="date-cell matrix-collapsible-col", style="text-align:center;"),
            tags.td(tags.span(viab, class_=_overview_viab_pill_class(viab)), class_="matrix-collapsible-col", style="text-align:center;"),
            *year_cells,
        )

    def _write_overview_matrix_excel(path, rows_data, years):
        export = []
        for r in rows_data:
            row = {
                "Solicitação": r.get("nome") or "",
                "Protocolo": r.get("protocolo") or "",
                "Conexão": r.get("conexao") or "",
                "UF": r.get("uf") or "",
                "Data Solic.": r.get("data_solicitacao") or "",
                "Entrada PL": r.get("data_entrada_pl") or "",
                "Rede": r.get("rede") or "",
                "kV": r.get("tensao") or "",
                "Status": r.get("status") or "",
                "Emissão PL": r.get("data_emissao_pl") or "",
                "Emissão Doc.": r.get("data_emissao_doc") or "",
                "Viabilidade": r.get("viabilidade") or "",
            }
            for y in years:
                vals = (r.get("year_values") or {}).get(y, {})
                row[f"{y} Ponta"] = vals.get("ponta")
                row[f"{y} Fora Ponta"] = vals.get("fora")
            export.append(row)
        df = pd.DataFrame(export)
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Matriz Visao Geral", index=False)
            ws = writer.sheets["Matriz Visao Geral"]
            from openpyxl.styles import Alignment, Font, PatternFill
            from openpyxl.utils import get_column_letter
            header_fill = PatternFill("solid", fgColor="2D5016")
            header_font = Font(color="FFFFFF", bold=True)
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            for col_idx, col in enumerate(ws.iter_cols(min_row=1, max_row=ws.max_row), start=1):
                header = ws.cell(row=1, column=col_idx).value
                width = 12
                if header in ("Solicitação", "Conexão"):
                    width = 34
                elif header in ("Protocolo", "Status", "Viabilidade"):
                    width = 20
                ws.column_dimensions[get_column_letter(col_idx)].width = width
                for cell in col:
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
                    if isinstance(header, str) and ("Ponta" in header):
                        cell.number_format = '#,##0.00'

    @output
    @render.ui
    def overview_matrix_page():
        if current_page.get() != "overview_matrix":
            return tags.div(style="display:none")
        rows = _overview_matrix_rows()
        all_years = _overview_matrix_all_years(rows)
        year_group_ths = []
        year_sub_ths = []
        for y in all_years:
            year_group_ths.append(tags.th(str(y), colspan="2", style="text-align:center; background:#FAFBFC; border-bottom:2px solid var(--border);"))
            year_sub_ths.append(tags.th("P", class_="col-ponta", style="text-align:center; font-size:10px;"))
            year_sub_ths.append(tags.th("FP", class_="col-fp", style="text-align:center; font-size:10px;"))
        return tags.div(
            tags.div(
                ui.input_action_button("btn_back_overview_matrix", "← Voltar a Visão Geral", class_="back-btn"),
                ui.download_button("download_overview_matrix", "⬇ Excel", class_="back-btn", style="margin:0;"),
                style="display:flex; gap:8px; align-items:center; margin-bottom:8px;",
            ),
            tags.div("Solicitações com todos os valores solicitados", class_="page-title"),
            tags.div("Tabela com todos os anos lado a lado. Verde escuro = início do horizonte; verde claro = janela contratável; laranja = fora do horizonte.", class_="page-subtitle"),
            tags.div(
                tags.span("Legenda:", style="font-weight:700; color:var(--text); margin-right:4px; font-size:12px;"),
                tags.span(INICIO_HORIZONTE_LABEL, class_="dc-legend-item", style="background:#D1FAE5; color:#065F46; border:1px solid #6EE7B7; padding:3px 9px; border-radius:999px; font-weight:600; font-size:12px;"),
                tags.span("Janela contratável", class_="dc-legend-item", style="background:#ECFDF5; color:#047857; border:1px solid #A7F3D0; padding:3px 9px; border-radius:999px; font-weight:600; font-size:12px;"),
                tags.span("Fora do horizonte", class_="dc-legend-item", style="background:#FFEDD5; color:#9A3412; border:1px solid #FDBA74; padding:3px 9px; border-radius:999px; font-weight:600; font-size:12px;"),
                style="display:flex; gap:8px; margin-bottom:14px; align-items:center; flex-wrap:wrap;",
            ),
            tags.div(
                tags.div(
                    tags.span("Matriz de valores solicitados", class_="panel-title"),
                    tags.span(f"{len(rows)} registros", class_="panel-badge"),
                    class_="panel-header",
                ),
                tags.div(
                    tags.table(
                        tags.thead(
                            tags.tr(
                                tags.th("Solicitação", rowspan="2"),
                                tags.th("Protocolo", style="text-align:center;", rowspan="2"),
                                tags.th("Conexão", style="text-align:center;", rowspan="2"),
                                tags.th(
                                    tags.button("▸ Dados", type="button", class_="matrix-toggle-btn js-matrix-toggle", title="Expandir/retrair colunas entre Protocolo e os anos"),
                                    class_="matrix-toggle-th",
                                    rowspan="2",
                                ),
                                tags.th("UF", class_="matrix-collapsible-col", style="text-align:center;", rowspan="2"),
                                tags.th("Data Solic.", class_="matrix-collapsible-col", style="text-align:center; font-size:10px;", rowspan="2"),
                                tags.th("Entrada PL", class_="matrix-collapsible-col", style="text-align:center; font-size:10px;", rowspan="2"),
                                tags.th("Rede", class_="matrix-collapsible-col", style="text-align:center;", rowspan="2"),
                                tags.th("kV", class_="matrix-collapsible-col", style="text-align:center;", rowspan="2"),
                                tags.th("Status", class_="matrix-collapsible-col", style="text-align:center;", rowspan="2"),
                                tags.th("Emissão PL", class_="matrix-collapsible-col", style="text-align:center; font-size:10px;", rowspan="2"),
                                tags.th("Emissão Doc.", class_="matrix-collapsible-col", style="text-align:center; font-size:10px;", rowspan="2"),
                                tags.th("Viabilidade", class_="matrix-collapsible-col", style="text-align:center;", rowspan="2"),
                                *year_group_ths,
                            ),
                            tags.tr(*year_sub_ths),
                        ),
                        tags.tbody(*[_build_overview_matrix_row(r, all_years) for r in rows]),
                        class_="dc-matrix-table js-collapsible-matrix cols-collapsed",
                    ),
                    class_="dc-matrix-wrap",
                ),
                class_="dc-card-table",
            ),
        )

    @render.download(
        filename=lambda: f"visao_geral_matriz_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    def download_overview_matrix():
        rows = _overview_matrix_rows()
        all_years = _overview_matrix_all_years(rows)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp_path = tmp.name
            _write_overview_matrix_excel(tmp_path, rows, all_years)
            with open(tmp_path, "rb") as f:
                yield f.read()
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    # --- DOWNLOAD DC LISTA (respeita filtros aplicados) ---
    @render.download(
        filename=lambda: f"datacenters_lista_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    def download_dc_list():
        rows = _dc_filtered_rows()
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp_path = tmp.name
            _write_dc_list_excel(tmp_path, rows)
            with open(tmp_path, "rb") as f:
                yield f.read()
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    # --- DOWNLOAD DC MATRIZ (respeita filtros aplicados) ---
    @render.download(
        filename=lambda: f"datacenters_matriz_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    def download_dc_matrix():
        rows = _dc_matrix_filtered()
        all_years = _dc_matrix_all_years(DATACENTER_ROWS)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp_path = tmp.name
            _write_dc_matrix_excel(tmp_path, rows, all_years)
            with open(tmp_path, "rb") as f:
                yield f.read()
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    # --- DOWNLOAD BD ENTRADA (template para preencher viabilidades) ---
    @render.download(
        filename=lambda: f"BD_entrada_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    def download_bd_entrada():
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp_path = tmp.name
            _write_bd_entrada_excel(tmp_path, DATACENTER_ROWS, VIABILIDADES_ENTRIES)
            with open(tmp_path, "rb") as f:
                yield f.read()
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    # --- DOWNLOAD DC DETALHE (SGA selecionado, com Matriz + Discretizacao) ---
    @render.download(
        filename=lambda: f"datacenter_detalhe_{str((next((x for x in DATACENTER_ROWS if str(x['item']) == str(selected_dc.get())), {}) or {}).get('main_protocol', 'sga')).replace('/', '-')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    def download_dc_detail():
        item_id = selected_dc.get()
        r = next((x for x in DATACENTER_ROWS if str(x["item"]) == str(item_id)), None)
        rows = [r] if r else []
        all_years = _dc_matrix_all_years(rows) if rows else list(DATACENTER_YEARS)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp_path = tmp.name
            _write_dc_matrix_excel(tmp_path, rows, all_years)
            with open(tmp_path, "rb") as f:
                yield f.read()
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    # --- DOWNLOAD BD ENTRADA no detalhe (mesmo conteúdo do BD entrada geral) ---
    @render.download(
        filename=lambda: f"BD_entrada_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    def download_bd_entrada_detail():
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp_path = tmp.name
            _write_bd_entrada_excel(tmp_path, DATACENTER_ROWS, VIABILIDADES_ENTRIES)
            with open(tmp_path, "rb") as f:
                yield f.read()
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    # --- DATA CENTERS PAGE (shell estável; tbody renderizado em separado) ---
    # Cache de listas estáticas (não dependem do filtro)
    _dc_redes = sorted(set(r["rede"] for r in DATACENTER_ROWS if r.get("rede") and r["rede"] != "—"))
    _dc_kvs = sorted(
        set(r["tensao"] for r in DATACENTER_ROWS if r.get("tensao") and r["tensao"] != "—"),
        key=lambda x: int(str(x).split(".")[0]) if str(x).replace(".", "").isdigit() else 0,
    )
    _dc_total = len(DATACENTER_ROWS)
    _dc_encontrados = sum(1 for r in DATACENTER_ROWS if r["origem"] != "Não encontrado")
    _dc_com_must = sum(1 for r in DATACENTER_ROWS if "MUST" in r["origem"])
    _dc_sem_must = _dc_encontrados - _dc_com_must

    # Contadores por status (usado nos 5 cards)
    def _classify_status_card(s):
        sl = (s or "").lower()
        if "anul" in sl:
            return "anulado"
        if "cancel" in sl:
            return "cancelado"
        if "interromp" in sl:
            return "interrompido"
        if "emit" in sl or "concl" in sl or "aprovado" in sl or "finaliz" in sl:
            return "emitido"
        return "andamento"

    _dc_emitidos = sum(1 for r in DATACENTER_ROWS if _classify_status_card(r.get("status")) == "emitido")
    _dc_andamento = sum(1 for r in DATACENTER_ROWS if _classify_status_card(r.get("status")) == "andamento")
    _dc_interrompidos = sum(1 for r in DATACENTER_ROWS if _classify_status_card(r.get("status")) == "interrompido")
    _dc_cancelados = sum(1 for r in DATACENTER_ROWS if _classify_status_card(r.get("status")) == "cancelado")
    _dc_anulados = sum(1 for r in DATACENTER_ROWS if _classify_status_card(r.get("status")) == "anulado")

    _dc_statuses = sorted(
        set((r.get("status") or "").strip() for r in DATACENTER_ROWS if (r.get("status") or "").strip() and r.get("status") != "—")
    )
    _dc_viabilidades = sorted(
        set((r.get("viabilidade_resumo") or "Pendente") for r in DATACENTER_ROWS if (r.get("viabilidade_resumo") or "Pendente"))
    )

    @reactive.effect
    def _init_dc_sidebar_filters():
        rede_choices = {r: r for r in _dc_redes}
        kv_choices = {str(k): str(k) for k in _dc_kvs}
        viab_choices = {v: v for v in _dc_viabilidades}
        status_choices = {s: s for s in _dc_statuses}
        for prefix in ("dc", "dcm"):
            ui.update_selectize(f"{prefix}_rede", choices=rede_choices, selected=[])
            ui.update_selectize(f"{prefix}_kv", choices=kv_choices, selected=[])
            ui.update_selectize(f"{prefix}_viab", choices=viab_choices, selected=[])
            ui.update_selectize(f"{prefix}_status", choices=status_choices, selected=[])
            ui.update_select(f"{prefix}_sort", selected="data_asc")
        dcp_years = _dcp_horizon_years()
        dcp_year_choices = {"latest": "Último ano do horizonte"}
        dcp_year_choices.update({str(y): str(y) for y in dcp_years})
        ui.update_selectize("dcp_period_years", choices={str(y): str(y) for y in dcp_years}, selected=[str(y) for y in dcp_years])
        ui.update_select("dcp_year", choices=dcp_year_choices, selected="latest")

    def _dc_filtered_rows():
        """Aplica todos os filtros e ordena. Usado pela lista e pela matriz."""
        try:
            f_empr = (input.dc_empr() or "").strip().lower()
        except Exception:
            f_empr = ""
        try:
            f_conexao = (input.dc_conexao() or "").strip().lower()
        except Exception:
            f_conexao = ""
        try:
            f_proto = (input.dc_proto() or "").strip().lower()
        except Exception:
            f_proto = ""
        try:
            f_rede = list(input.dc_rede() or [])
        except Exception:
            f_rede = []
        try:
            f_kv = list(input.dc_kv() or [])
        except Exception:
            f_kv = []
        try:
            f_viab = list(input.dc_viab() or [])
        except Exception:
            f_viab = []
        try:
            f_status_select = list(input.dc_status() or [])
        except Exception:
            f_status_select = []
        f_status = dc_status_filter.get()
        f_emitido_pl = dc_emitido_pl_filter.get()
        try:
            f_sort = input.dc_sort() or "data_asc"
        except Exception:
            f_sort = "data_asc"

        from datetime import datetime
        def _parse_dt(s):
            if not s or s in ("—", ""):
                return datetime.max
            try:
                return datetime.strptime(str(s), "%d/%m/%Y")
            except Exception:
                return datetime.max

        out = []
        for r in DATACENTER_ROWS:
            if f_empr:
                proto_text = (r.get("main_protocol") or "").upper()
                if "SAM" in proto_text:
                    haystack = str(r.get("ponto_label", "") or r.get("ponto_instalacao", "") or r.get("empreendimento", "")).lower()
                else:
                    haystack = str(r.get("empreendimento", "") or r.get("ponto_label", "")).lower()
                if f_empr not in haystack:
                    continue
            if f_proto and f_proto not in str(r.get("main_protocol", "")).lower():
                continue
            if f_conexao and f_conexao not in str(r.get("conexao", "")).lower():
                continue
            if f_rede and r.get("rede") not in f_rede:
                continue
            if f_kv and str(r.get("tensao", "")) not in f_kv:
                continue
            if f_viab and (r.get("viabilidade_resumo") or "Pendente") not in f_viab:
                continue
            if f_status_select and (r.get("status") or "—") not in f_status_select:
                continue
            if f_emitido_pl and _emitido_pl_state(r.get("data_emissao_pl")) != f_emitido_pl:
                continue
            if f_status and f_status != "todos":
                cat = _classify_status_card(r.get("status"))
                if f_status == "emitidos" and cat != "emitido":
                    continue
                if f_status == "andamento" and cat != "andamento":
                    continue
                if f_status == "interrompidos" and cat != "interrompido":
                    continue
                if f_status == "cancelados" and cat != "cancelado":
                    continue
                if f_status == "anulados" and cat != "anulado":
                    continue
            out.append(r)

        sort_map = {
            "data_asc": (lambda r: _parse_dt(r.get("data_solicitacao")), False),
            "data_desc": (lambda r: _parse_dt(r.get("data_solicitacao")), True),
            "entrada_pl_asc": (lambda r: _parse_dt(r.get("data_entrada_pl")), False),
            "entrada_pl_desc": (lambda r: _parse_dt(r.get("data_entrada_pl")), True),
            "prazo_pl_asc": (lambda r: _parse_dt(r.get("prazo_analise_pl")), False),
            "prazo_pl_desc": (lambda r: _parse_dt(r.get("prazo_analise_pl")), True),
            "prazo_ons_asc": (lambda r: _parse_dt(r.get("prazo_emissao_ons")), False),
            "prazo_ons_desc": (lambda r: _parse_dt(r.get("prazo_emissao_ons")), True),
            "emissao_pl_asc": (lambda r: _parse_dt(r.get("data_emissao_pl")), False),
            "emissao_pl_desc": (lambda r: _parse_dt(r.get("data_emissao_pl")), True),
            "emissao_doc_asc": (lambda r: _parse_dt(r.get("data_emissao_doc")), False),
            "emissao_doc_desc": (lambda r: _parse_dt(r.get("data_emissao_doc")), True),
            "prazo_cust_asc": (lambda r: _parse_dt(r.get("prazo_cust")), False),
            "prazo_cust_desc": (lambda r: _parse_dt(r.get("prazo_cust")), True),
            "proto_asc": (lambda r: str(r.get("main_protocol") or ""), False),
            "proto_desc": (lambda r: str(r.get("main_protocol") or ""), True),
            "empr_asc": (lambda r: str(_excel_empreendimento_ponto(r) or "").lower(), False),
            "empr_desc": (lambda r: str(_excel_empreendimento_ponto(r) or "").lower(), True),
        }
        key_fn, rev = sort_map.get(f_sort, sort_map["data_asc"])
        out.sort(key=key_fn, reverse=rev)
        return out

    def _classify_today(date_str, kind, status="", protocol="", data_emissao_pl=""):
        """Recalcula cor com base na data ATUAL.

        Regras:
          - Se documento já foi emitido / cancelado / anulado → sem destaque
          - Para PL: se a PL já emitiu (data_emissao_pl preenchida), sem destaque
          - Para protocolos SPT → SPT não conta para indicador ONS:
              ONS: apenas azul se passou do prazo
              PL: amarelo se passou do prazo (mantém)
          - Demais protocolos:
              ONS: amarelo se ≤ 7 dias, vermelho se ≤ 2 dias ou expirado
              PL: amarelo se já expirou
        """
        if not date_str or date_str == "—":
            return ""
        # Se já foi emitido, cancelado ou anulado → sem destaque
        sl = (status or "").lower()
        if "emit" in sl or "concl" in sl or "cancel" in sl or "anul" in sl:
            return ""
        # Para PL: se a PL já emitiu, não mostrar aviso de prazo
        if kind == "pl" and data_emissao_pl and data_emissao_pl != "—":
            return ""
        try:
            from datetime import datetime
            prazo = datetime.strptime(date_str, "%d/%m/%Y").date()
            hoje = datetime.now().date()
            delta = (prazo - hoje).days
        except Exception:
            return ""

        # Detectar SPT
        is_spt = "SPT" in (protocol or "").upper()

        if kind == "ons":
            if is_spt:
                # SPT: só azul se passou
                return "blue" if delta < 0 else ""
            # Demais: amarelo perto, vermelho crítico
            if delta <= 2:
                return "red"
            if delta <= 7:
                return "yellow"
            return ""
        if kind == "pl":
            if delta < 0:
                return "yellow"
            return ""
        return ""

    def _viab_pill_class(viab):
        """Mapeia viabilidade para classe CSS de pill colorida."""
        if not viab or viab == "Pendente":
            return "viab-pill viab-pendente"
        v = str(viab).strip()
        v_low = v.lower()
        if "verificar" in v_low:
            return "viab-pill viab-verificar"
        if "no prazo" in v_low:
            return "viab-pill viab-no-prazo"
        if "Misto" in v:
            return "viab-pill viab-misto"
        if v == "Cancelada":
            return "viab-pill viab-cancelada"
        if v == "Anulada":
            return "viab-pill viab-anulada"
        if v == "Inviável":
            return "viab-pill viab-inviavel"
        if "Limitado" in v:
            return "viab-pill viab-limitado"
        if "Condicionado" in v:
            return "viab-pill viab-condicionado"
        if v == "Em análise":
            return "viab-pill viab-pendente"
        if v == "Viável":
            return "viab-pill viab-viavel"
        return "viab-pill viab-pendente"

    def _build_dc_row(r):
        pico = r.get("potencia_max")
        pico_str = fmt_mw(pico) if pico else "—"

        status_real = (r.get("status") or "").strip()
        sl = status_real.lower()
        if not status_real:
            status_class = "status-pill status-miss"; status_label = "—"
        elif "anul" in sl:
            status_class = "status-pill status-anulada"; status_label = status_real
        elif "cancel" in sl:
            status_class = "status-pill status-miss"; status_label = status_real
        elif "emit" in sl or "concl" in sl or "aprovado" in sl:
            status_class = "status-pill status-ok"; status_label = status_real
        elif "andamento" in sl or "análise" in sl or "analise" in sl:
            status_class = "status-pill status-warn"; status_label = status_real
        else:
            status_class = "status-pill status-warn"; status_label = status_real

        rede = r.get("rede") or "—"
        rede_class_map = {"DIST": "rede-dist", "RB": "rede-rb", "DIT": "rede-dit"}
        rede_class = rede_class_map.get(rede, "rede-empty")

        # Status de cor (recalculado a cada render — sempre baseado em "hoje")
        pl_cls = _classify_today(r.get("prazo_analise_pl"), "pl",
                                  status=r.get("status"), protocol=r.get("main_protocol"),
                                  data_emissao_pl=r.get("data_emissao_pl"))
        ons_cls = _classify_today(r.get("prazo_emissao_ons"), "ons",
                                  status=r.get("status"), protocol=r.get("main_protocol"))
        pl_full_class = "date-cell prazo-pl" + (f" prazo-{pl_cls}" if pl_cls else "")
        ons_full_class = "date-cell prazo-ons" + (f" prazo-{ons_cls}" if ons_cls else "")

        # Pill do CUST
        cust_label = r.get("cust_label", "—")
        cust_status_v = r.get("cust_status", "")
        cust_pill_class = {
            "assinado": "cust-pill cust-assinado",
            "no_prazo": "cust-pill cust-no-prazo",
            "nao_assinado": "cust-pill cust-nao-assinado",
            "ptdis": "cust-pill cust-ptdis",
            "inviavel": "cust-pill cust-inviavel",
            "verificar": "cust-pill cust-verificar",
        }.get(cust_status_v, "cust-pill")

        # Pill de viabilidade
        viab = r.get("viabilidade_resumo") or "Pendente"
        viab_pill_class = _viab_pill_class(viab)

        # Empreendimento + ponto (se SAM com múltiplos pontos)
        ponto_label = r.get("ponto_label") or ""
        empr_main = (r.get("empreendimento") or "").strip()
        proto_text = r.get("main_protocol") or ""
        is_sam = "SAM" in proto_text.upper()
        # Para SAM: usar APENAS o ponto de contratação (ignora empreendimento)
        if is_sam:
            display_text = ponto_label or r.get("ponto_instalacao") or empr_main or "—"
            empr_cell = tags.div(display_text, class_="dc-empr-name", title=display_text)
            cell_title = display_text
        elif empr_main and ponto_label and ponto_label != empr_main:
            empr_cell = tags.div(
                tags.div(empr_main, class_="dc-empr-name"),
                tags.div(ponto_label, class_="dc-ponto-label"),
            )
            cell_title = empr_main
        elif empr_main:
            empr_cell = tags.div(empr_main, class_="dc-empr-name", title=empr_main)
            cell_title = empr_main
        elif ponto_label:
            empr_cell = tags.div(ponto_label, class_="dc-empr-name", title=ponto_label)
            cell_title = ponto_label
        else:
            empr_cell = tags.div("—", class_="dc-empr-name")
            cell_title = ""

        return tags.tr(
            tags.td(empr_cell, title=cell_title),
            tags.td(r["main_protocol"] or "—",
                    style="font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--green-dark); font-weight:600; text-align:center;"),
            tags.td(r.get("data_solicitacao") or "—",
                    class_="date-cell", style="text-align:center;"),
            tags.td(r.get("data_entrada_pl") or "—",
                    class_="date-cell", style="text-align:center;"),
            tags.td(r.get("prazo_analise_pl") or "—",
                    class_=pl_full_class, style="text-align:center;"),
            tags.td(r.get("prazo_emissao_ons") or "—",
                    class_=ons_full_class, style="text-align:center;"),
            tags.td(tags.span(rede, class_=f"rede-pill {rede_class}"),
                    style="text-align:center;"),
            tags.td(r["tensao"] or "—", style="text-align:center;"),
            tags.td(r["conexao"][:50] + ("…" if len(r["conexao"] or "") > 50 else ""),
                    class_="text-col", style="font-size:12px; color:var(--text-mid);",
                    title=r["conexao"]),
            tags.td(pico_str, class_="dc-pico", style="text-align:center;"),
            tags.td(tags.span(status_label, class_=status_class, title=status_real),
                    style="text-align:center;"),
            tags.td(r.get("data_emissao_pl") or "—",
                    class_="date-cell", style="text-align:center;"),
            tags.td(r.get("data_emissao_doc") or "—",
                    class_="date-cell", style="text-align:center;"),
            tags.td(r.get("prazo_cust") or "—",
                    class_="date-cell", style="text-align:center;"),
            tags.td(tags.span(cust_label, class_=cust_pill_class), style="text-align:center;"),
            tags.td(tags.span(viab, class_=viab_pill_class), style="text-align:center;"),
            **{"data-dc": str(r["item"]), "data-ponto-idx": str(r.get("ponto_idx", 0))},
        )

    def _dcp_num(value):
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        try:
            if pd.isna(value):
                return 0.0
        except Exception:
            pass
        try:
            text = str(value).strip()
            if "," in text:
                text = text.replace(".", "").replace(",", ".")
            return float(text)
        except Exception:
            return 0.0

    def _dcp_fmt(value):
        value = _dcp_num(value)
        return f"{int(round(value)):,.0f}".replace(",", ".")

    def _dcp_fmt_mw(value):
        return _dcp_fmt(value)

    def _dcp_values_mw(vals):
        ponta = _dcp_num(vals.get("ponta"))
        fora = _dcp_num(vals.get("fora"))
        return max(ponta, fora)

    def _dcp_requested_year_mw(r, year):
        vals = _year_dict_get(r.get("year_values") or {}, year)
        return _dcp_values_mw(vals)

    def _dcp_contract_window_years(r):
        text = str(r.get("janela_contratavel") or "")
        match = re.search(r"(\d{4})\D+(\d{4})", text)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            if start <= end:
                return list(range(start, end + 1))
        years = []
        for raw_year, status in (r.get("year_status") or {}).items():
            if status not in ("current", "contractable"):
                continue
            try:
                years.append(int(raw_year))
            except Exception:
                continue
        return sorted(set(years))

    def _dcp_panel_value_source_year(r, year):
        if year is None:
            return None
        try:
            year_int = int(year)
        except Exception:
            return None
        window_years = _dcp_contract_window_years(r)
        if not window_years:
            return year_int if _dcp_requested_year_mw(r, year_int) else None
        if year_int <= max(window_years):
            return year_int if _dcp_requested_year_mw(r, year_int) else None

        best_year = None
        best_mw = 0.0
        for y in window_years:
            mw = _dcp_requested_year_mw(r, y)
            if mw >= best_mw:
                best_year = y
                best_mw = mw
        return best_year if best_mw else None

    def _dcp_year_mw(r, year):
        source_year = _dcp_panel_value_source_year(r, year)
        if source_year is None:
            return 0.0
        return _dcp_requested_year_mw(r, source_year)

    def _dcp_is_panel_row(r):
        return (
            r.get("rede") == "RB"
            and _protocol_type(r.get("main_protocol")) == "SPA"
            and _classify_status_card(r.get("status")) != "cancelado"
        )

    def _dcp_horizon_years():
        years = sorted({
            y
            for r in DATACENTER_ROWS
            if _dcp_is_panel_row(r)
            for y in _dcp_contract_window_years(r)
        })
        if years:
            return years
        return sorted({
            int(y)
            for r in DATACENTER_ROWS
            if _dcp_is_panel_row(r)
            for y, vals in (r.get("year_values") or {}).items()
            if _dcp_num(vals.get("ponta")) or _dcp_num(vals.get("fora"))
        })

    def _dcp_period_years():
        available = _dcp_horizon_years()
        try:
            selected = [int(y) for y in (input.dcp_period_years() or [])]
        except Exception:
            selected = []
        selected = [y for y in selected if y in available]
        return selected or available

    def _dcp_reference_year():
        years = _dcp_horizon_years()
        try:
            selected = input.dcp_year() or "latest"
        except Exception:
            selected = "latest"
        if selected != "latest":
            try:
                return int(selected)
            except Exception:
                pass
        return max(years) if years else None

    def _dcp_base_rows(include_state=True):
        selected_uf = dc_panel_state.get() if include_state else ""
        rows = [r for r in DATACENTER_ROWS if _dcp_is_panel_row(r)]
        if selected_uf:
            rows = [r for r in rows if str(r.get("uf") or "").upper() == selected_uf]
        return rows

    def _dcp_year_viab(r, year):
        source_year = _dcp_panel_value_source_year(r, year)
        if source_year is not None:
            year = source_year
        viab_data = r.get("viabilidade_anos") or {}
        anos = viab_data.get("anos") or {}
        vals = _year_dict_get(anos, year)
        return (
            str(vals.get("viabilidade") or "").strip()
            or str(viab_data.get("viabilidade_geral") or "").strip()
            or str(r.get("viabilidade_resumo") or "").strip()
            or "Em análise"
        )

    def _dcp_viab_category(viab):
        text = str(viab or "").strip().lower()
        if "invi" in text or "não vi" in text or "nao vi" in text or "negad" in text or "cancel" in text or "anul" in text:
            return "inviavel"
        if "viável" in text or "viavel" in text or "condicionado" in text or "limitado" in text:
            return "aprovado"
        return "analise"

    def _dcp_aggregate_year(rows, year):
        acc = {
            "aprovado": 0.0,
            "inviavel": 0.0,
            "analise": 0.0,
            "projetos": 0,
            "aprovado_projetos": 0,
            "inviavel_projetos": 0,
            "analise_projetos": 0,
        }
        if year is None:
            return acc
        for r in rows:
            mw = _dcp_year_mw(r, year)
            if not mw:
                continue
            category = _dcp_viab_category(_dcp_year_viab(r, year))
            acc["projetos"] += 1
            acc[category] += mw
            acc[f"{category}_projetos"] += 1
        return acc

    def _dcp_total(acc):
        return acc.get("aprovado", 0.0) + acc.get("inviavel", 0.0) + acc.get("analise", 0.0)

    def _dcp_year_series(rows, years):
        return [
            {"year": y, **_dcp_aggregate_year(rows, y)}
            for y in years
        ]

    def _dcp_aggregate_possible_year(rows, year):
        acc = {
            "aprovado": 0.0,
            "inviavel": 0.0,
            "analise": 0.0,
            "projetos": 0,
            "aprovado_projetos": 0,
            "inviavel_projetos": 0,
            "analise_projetos": 0,
        }
        if year is None:
            return acc
        for r in rows:
            mw = _dcp_year_mw(r, year)
            if not mw:
                continue
            category = _dcp_viab_category(_dcp_year_viab(r, year))
            if category == "inviavel":
                continue
            if category == "aprovado" and r.get("cust_status") != "assinado":
                continue
            acc["projetos"] += 1
            acc[category] += mw
            acc[f"{category}_projetos"] += 1
        return acc

    def _dcp_possible_year_series(rows, years):
        return [
            {"year": y, **_dcp_aggregate_possible_year(rows, y)}
            for y in years
        ]

    def _dcp_state_totals(year):
        totals = {}
        if year is None:
            return totals
        for r in _dcp_base_rows(include_state=False):
            uf = str(r.get("uf") or "").upper()
            if uf not in UF_MAP:
                continue
            totals[uf] = totals.get(uf, 0.0) + _dcp_year_mw(r, year)
        return totals

    def _dcp_state_summary(rows, year):
        acc = _dcp_aggregate_year(rows, year)
        total = _dcp_total(acc)
        cust = sum(
            _dcp_year_mw(r, year)
            for r in rows
            if year is not None and r.get("cust_status") == "assinado" and _dcp_year_mw(r, year)
        )
        return {
            "projetos": acc["projetos"],
            "total": total,
            "aprovado": acc["aprovado"],
            "inviavel": acc["inviavel"],
            "analise": acc["analise"],
            "cust": cust,
        }

    def _dcp_pct(value, total):
        return "0%" if not total else f"{round(100 * value / total):.0f}%"

    def _dcp_card(title, value, sub, tone, icon):
        return tags.div(
            tags.div(icon, class_=f"dcp-card-icon {tone}"),
            tags.div(
                tags.div(title, class_="dcp-card-title"),
                tags.div(value, class_="dcp-card-value"),
                tags.div(sub, class_="dcp-card-sub"),
                class_="dcp-card-copy",
            ),
            class_="dcp-kpi-card",
        )

    def _dcp_chart(series, selected_uf, chart_type="received", metric="mw", include_inviavel=True, include_line=False):
        width, height = 760, 260
        left, right, top, bottom = 54, 20, 24, 42
        plot_w = width - left - right
        plot_h = height - top - bottom
        years = [s["year"] for s in series]
        state_label = selected_uf or "RB"
        chart_type = chart_type if chart_type in ("received", "possible") else "received"
        title_options = [
            ("received", f"Montante Total de DCs que chegou no ONS — {state_label}"),
            ("possible", f"Evolução do montante total de possíveis DCs em {state_label}"),
        ]
        metric = metric if metric in ("mw", "projects") else "mw"
        fmt_value = _dcp_fmt_mw if metric == "mw" else _dcp_fmt
        def chart_value(item, key):
            if metric == "projects":
                return item.get(f"{key}_projetos", 0)
            return item.get(key, 0.0)
        def chart_option(value, label):
            attrs = {"value": value}
            if value == chart_type:
                attrs["selected"] = "selected"
            return tags.option(label, **attrs)
        totals = [
            chart_value(s, "aprovado") + chart_value(s, "analise") + (chart_value(s, "inviavel") if include_inviavel else 0)
            for s in series
        ]
        max_total = max(totals) if totals else 0
        max_total = max_total or 1
        step = plot_w / max(len(series), 1)
        bar_w = min(46, step * 0.45)
        colors = {"aprovado": "#16A34A", "inviavel": "#DC2626", "analise": "#2563EB"}
        labels = {"aprovado": "Aprovado", "inviavel": "Inviável", "analise": "Em análise"}

        elems = []
        bar_labels = []
        for i in range(5):
            y = top + plot_h - (plot_h * i / 4)
            val = max_total * i / 4
            elems.append(_svg_tag("line", x1=left, y1=y, x2=width - right, y2=y, class_="dcp-chart-grid"))
            elems.append(_svg_tag("text", fmt_value(val), x=left - 10, y=y + 4, class_="dcp-chart-axis", **{"text-anchor": "end"}))
        elems.append(_svg_tag("line", x1=left, y1=top + plot_h, x2=width - right, y2=top + plot_h, class_="dcp-chart-axis-line"))

        line_points = []
        keys = ["aprovado", "inviavel", "analise"] if include_inviavel else ["aprovado", "analise"]
        for idx, item in enumerate(series):
            x = left + step * idx + step / 2
            y_base = top + plot_h
            total = sum(chart_value(item, k) for k in keys)
            line_y = top + plot_h - (total / max_total * plot_h)
            line_points.append(f"{x:.1f},{line_y:.1f}")
            for key in keys:
                val = chart_value(item, key)
                h = val / max_total * plot_h
                if h <= 0:
                    continue
                y_base -= h
                elems.append(_svg_tag("rect", x=x - bar_w / 2, y=y_base, width=bar_w, height=max(h, 1), fill=colors[key], rx=2))
                if key == "inviavel":
                    bar_labels.append(_svg_tag("text", fmt_value(val), x=x, y=y_base + h / 2, class_="dcp-chart-bar-label dcp-chart-bar-label-inviavel", **{"text-anchor": "middle", "dominant-baseline": "middle"}))
                elif h > 18:
                    bar_labels.append(_svg_tag("text", fmt_value(val), x=x, y=y_base + h / 2 + 4, class_="dcp-chart-bar-label", **{"text-anchor": "middle"}))
            elems.append(_svg_tag("text", str(item["year"]), x=x, y=top + plot_h + 24, class_="dcp-chart-axis", **{"text-anchor": "middle"}))
            if total:
                elems.append(_svg_tag("text", fmt_value(total), x=x, y=max(12, line_y - 8), class_="dcp-chart-total", **{"text-anchor": "middle"}))

        if include_line and line_points:
            elems.append(_svg_tag("polyline", points=" ".join(line_points), fill="none", stroke="#111827", **{"stroke-width": "2.5"}))
            for point in line_points:
                x, y = point.split(",")
                elems.append(_svg_tag("circle", cx=x, cy=y, r=3.5, fill="#111827"))
        elems.extend(bar_labels)

        legend_items = []
        legend_keys = keys + (["total"] if include_line else [])
        legend_colors = {**colors, "total": "#111827"}
        legend_labels = {**labels, "total": "Total"}
        for key in legend_keys:
            legend_items.append(tags.span(tags.span(style=f"background:{legend_colors[key]};", class_="dcp-legend-swatch"), legend_labels[key], class_="dcp-legend-item"))

        return tags.div(
            tags.div(
                tags.div(
                    tags.select(
                        *(chart_option(value, label) for value, label in title_options),
                        class_="dcp-chart-select",
                        **{"aria-label": "Tipo de gráfico"},
                    ),
                    class_="dcp-panel-title dcp-panel-title-control",
                ),
                tags.div(
                    tags.button("Exibir: MW", class_=f"dcp-toggle {'active' if metric == 'mw' else ''}", **{"data-metric": "mw", "type": "button"}),
                    tags.button("Projetos", class_=f"dcp-toggle {'active' if metric == 'projects' else ''}", **{"data-metric": "projects", "type": "button"}),
                    class_="dcp-chart-toggle",
                ),
                class_="dcp-panel-head",
            ),
            tags.svg(*elems, viewBox=f"0 0 {width} {height}", class_="dcp-chart-svg", role="img"),
            tags.div(*legend_items, class_="dcp-chart-legend"),
            class_="dcp-panel dcp-chart-panel",
        )

    def _dcp_map_color(value, max_value):
        if not value:
            return "#E5E7EB"
        ratio = min(max(value / max_value, 0.0), 1.0) if max_value else 0.0
        if ratio >= 0.75:
            return "#166534"
        if ratio >= 0.45:
            return "#22C55E"
        if ratio >= 0.20:
            return "#86EFAC"
        return "#DCFCE7"

    def _dcp_map(state_totals, selected_uf):
        max_value = max(state_totals.values()) if state_totals else 1
        rules = []
        for uf in UF_MAP:
            rules.append(f".dcp-brazil-map #{uf} {{ fill: {_dcp_map_color(state_totals.get(uf, 0.0), max_value)} !important; }}")
        if selected_uf:
            rules.append(f".dcp-brazil-map #{selected_uf} {{ stroke: #14532D !important; stroke-width: 2.4 !important; }}")
        return tags.div(
            tags.style("\n".join(rules)),
            HTML(BRAZIL_MAP_SVG),
            class_="dcp-brazil-map",
        )

    def _dcp_ranking(state_totals, year):
        rows = sorted(state_totals.items(), key=lambda item: item[1], reverse=True)[:8]
        trs = []
        for idx, (uf, total) in enumerate(rows, start=1):
            all_rows = [r for r in _dcp_base_rows(include_state=False) if str(r.get("uf") or "").upper() == uf]
            acc = _dcp_aggregate_year(all_rows, year)
            cls = "selected" if uf == dc_panel_state.get() else ""
            trs.append(tags.tr(
                tags.td(str(idx), class_="dcp-rank-num"),
                tags.td(f"{UF_MAP.get(uf, uf)}", class_="dcp-rank-state"),
                tags.td(_dcp_fmt_mw(total), class_="dcp-rank-mw"),
                tags.td(_dcp_fmt_mw(acc["aprovado"]), class_="dcp-rank-mw"),
                tags.td(_dcp_pct(acc["aprovado"], total), class_="dcp-rank-pct"),
                class_=cls,
            ))
        return tags.div(
            tags.div("Ranking de Estados por MW solicitados", class_="dcp-panel-title"),
            tags.table(
                tags.thead(tags.tr(
                    tags.th("#"),
                    tags.th("Estado"),
                    tags.th("MW solic."),
                    tags.th("Aprov."),
                    tags.th("% aprov."),
                )),
                tags.tbody(*trs),
                class_="dcp-ranking-table",
            ),
            class_="dcp-panel dcp-ranking-panel",
        )

    @output
    @render.ui
    def datacenters_panel_page():
        if current_page.get() != "datacenters_panel":
            return tags.div(style="display:none")

        ref_year = _dcp_reference_year()
        period_years = _dcp_period_years()
        rows = _dcp_base_rows(include_state=True)
        all_rows = _dcp_base_rows(include_state=False)
        summary = _dcp_state_summary(rows, ref_year)
        total = summary["total"]
        selected_uf = dc_panel_state.get()
        metric = dc_panel_metric.get()
        chart_type = dc_panel_chart_type.get()
        state_totals = _dcp_state_totals(ref_year)
        series = _dcp_year_series(rows, period_years)
        possible_series = _dcp_possible_year_series(rows, period_years)
        chart_series = possible_series if chart_type == "possible" else series
        chart_include_inviavel = chart_type != "possible"
        chart_include_line = chart_type == "possible"
        map_rows = [r for r in all_rows if str(r.get("uf") or "").upper() == selected_uf] if selected_uf else all_rows
        map_summary = _dcp_state_summary(map_rows, ref_year)
        map_title = f"{UF_MAP[selected_uf]} ({selected_uf})" if selected_uf else "Todos os estados"

        return tags.div(
            tags.div(
                tags.div("Painel DataCenters", class_="page-title"),
                tags.div(
                    f"Rede RB | SPA | Ano de referência: {ref_year or '—'} | Período: {period_years[0] if period_years else '—'}–{period_years[-1] if period_years else '—'}",
                    class_="page-subtitle",
                ),
                class_="dcp-title-row",
            ),
            tags.div(
                _dcp_card("Projetos", _dcp_fmt(summary["projetos"]), "Total no ano de referência", "neutral", "▦"),
                _dcp_card("MW solicitados", _dcp_fmt_mw(total), "Total no ano de referência", "cyan", "⚡"),
                _dcp_card("Aprovados", _dcp_fmt_mw(summary["aprovado"]), f"{_dcp_pct(summary['aprovado'], total)} do total", "green", "✓"),
                _dcp_card("Em análise", _dcp_fmt_mw(summary["analise"]), f"{_dcp_pct(summary['analise'], total)} do total", "blue", "◷"),
                _dcp_card("Inviáveis", _dcp_fmt_mw(summary["inviavel"]), f"{_dcp_pct(summary['inviavel'], total)} do total", "red", "×"),
                _dcp_card("CUST assinados", _dcp_fmt_mw(summary["cust"]), f"{_dcp_pct(summary['cust'], total)} do total", "purple", "◇"),
                class_="dcp-kpi-row",
            ),
            tags.div(
                tags.div(
                    tags.div("Mapa de Projetos", class_="dcp-panel-title"),
                    tags.div("Selecione um estado para filtrar", class_="dcp-muted"),
                    _dcp_map(state_totals, selected_uf),
                    tags.div(
                        tags.div("Estado selecionado", class_="dcp-selected-label"),
                        tags.div(map_title, class_="dcp-selected-title"),
                        tags.div(
                            tags.div(tags.span("Projetos"), tags.strong(_dcp_fmt(map_summary["projetos"]))),
                            tags.div(tags.span("MW solic."), tags.strong(_dcp_fmt_mw(map_summary["total"]))),
                            tags.div(tags.span("Aprovados"), tags.strong(_dcp_fmt_mw(map_summary["aprovado"]))),
                            class_="dcp-selected-stats",
                        ),
                        tags.button("Limpar seleção", class_="dcp-map-clear") if selected_uf else None,
                        class_="dcp-selected-card",
                    ),
                    class_="dcp-panel dcp-map-panel",
                ),
                _dcp_chart(chart_series, selected_uf, chart_type=chart_type, metric=metric, include_inviavel=chart_include_inviavel, include_line=chart_include_line),
                _dcp_ranking(state_totals, ref_year),
                class_="dcp-main-grid",
            ),
            class_="dcp-page",
        )

    @output
    @render.ui
    def datacenters_page():
        if current_page.get() != "datacenters":
            return tags.div(style="display:none")

        f_status = dc_status_filter.get()
        f_status_local = dc_status_filter.get()
        showing = len(_dc_filtered_rows())

        return tags.div(
            tags.div("DataCenters", class_="page-title"),
            tags.div(
                "Lista de protocolos extraídos da planilha de controle. Clique em uma linha para o detalhe.",
                class_="page-subtitle",
            ),
            # Cards executivos: 5 contadores baseados em status real
            tags.div(
                tags.div(
                    tags.div("🗂️", class_="stat-icon"),
                    tags.div(str(_dc_total), class_="stat-value"),
                    tags.div("Nº Solicitações", class_="stat-label"),
                    class_="stat-card green",
                ),
                tags.div(
                    tags.div("✓", class_="stat-icon"),
                    tags.div(str(_dc_emitidos), class_="stat-value"),
                    tags.div("Emitidos", class_="stat-label"),
                    class_="stat-card green",
                ),
                tags.div(
                    tags.div("⚙", class_="stat-icon"),
                    tags.div(str(_dc_andamento), class_="stat-value"),
                    tags.div("Em andamento", class_="stat-label"),
                    class_="stat-card amber",
                ),
                tags.div(
                    tags.div("⏸", class_="stat-icon"),
                    tags.div(str(_dc_interrompidos), class_="stat-value"),
                    tags.div("Interrompidos", class_="stat-label"),
                    class_="stat-card amber",
                ),
                tags.div(
                    tags.div("✕", class_="stat-icon"),
                    tags.div(str(_dc_cancelados), class_="stat-value"),
                    tags.div("Cancelados", class_="stat-label"),
                    class_="stat-card purple",
                ),
                tags.div(
                    tags.div("⊘", class_="stat-icon"),
                    tags.div(str(_dc_anulados), class_="stat-value"),
                    tags.div("Anulados", class_="stat-label"),
                    class_="stat-card purple",
                ),
                class_="cards-row",
                style="grid-template-columns: repeat(6, 1fr);",
            ),
            # Toolbar: chips de status + botão matriz
            tags.div(
                ui.input_action_button("dc_filter_all", f"Todos ({_dc_total})", class_="dc-chip" + (" active" if f_status_local == "todos" else "")),
                ui.input_action_button("dc_filter_emitidos", f"Emitidos ({_dc_emitidos})", class_="dc-chip" + (" active" if f_status_local == "emitidos" else "")),
                ui.input_action_button("dc_filter_andamento", f"Em andamento ({_dc_andamento})", class_="dc-chip" + (" active" if f_status_local == "andamento" else "")),
                ui.input_action_button("dc_filter_interrompidos", f"Interrompidos ({_dc_interrompidos})", class_="dc-chip" + (" active" if f_status_local == "interrompidos" else "")),
                ui.input_action_button("dc_filter_cancelados", f"Cancelados ({_dc_cancelados})", class_="dc-chip" + (" active" if f_status_local == "cancelados" else "")),
                ui.input_action_button("dc_filter_anulados", f"Anulados ({_dc_anulados})", class_="dc-chip" + (" active" if f_status_local == "anulados" else "")),
                ui.input_action_button("btn_dc_matrix", "📊 Solicitações com todos os valores solicitados", class_="dc-btn-primary"),
                ui.download_button("download_dc_list", "⬇ Excel", class_="back-btn", style="margin:0;"),
                class_="dc-toolbar",
            ),
            # Tabela: renderizada inteira pelo output (evita problema de div wrapper dentro de table)
            tags.div(
                tags.div(
                    tags.span("Protocolos", class_="panel-title"),
                    ui.output_ui("dc_count_badge"),
                    class_="panel-header",
                ),
                ui.output_ui("dc_full_table"),
                class_="dc-card-table",
            ),
        )

    # Tabela completa (thead + tbody) — re-renderiza quando filtros mudam
    @output
    @render.ui
    def dc_full_table():
        rows = _dc_filtered_rows()
        return tags.table(
            tags.thead(
                tags.tr(
                    tags.th("Empreendimento / Ponto"),
                    tags.th("Protocolo", style="text-align:center;"),
                    tags.th("Data Solic.", style="text-align:center; font-size:10px;",
                            title="Data da Solicitação de Acesso (fila)"),
                    tags.th("Entrada PL", style="text-align:center; font-size:10px;",
                            title="Data de chegada na PL para análise técnica"),
                    tags.th("Prazo PL", style="text-align:center; font-size:10px;",
                            title="Prazo Análise Técnica PL"),
                    tags.th("Prazo ONS", style="text-align:center; font-size:10px;",
                            title="Prazo Emissão PA - ONS"),
                    tags.th("Rede", style="text-align:center;"),
                    tags.th("kV", style="text-align:center;"),
                    tags.th("Conexão"),
                    tags.th("Pico MW", style="text-align:right;"),
                    tags.th("Status", style="text-align:center;"),
                    tags.th("Emissão PL", style="text-align:center; font-size:10px;",
                            title="Data em que a PL emitiu (din_envioanalise)"),
                    tags.th("Emissão Doc.", style="text-align:center; font-size:10px;",
                            title="Data real da emissão do documento (din_emissaodocumento)"),
                    tags.th("Prazo CUST", style="text-align:center; font-size:10px;",
                            title="Data limite para assinatura do CUST (90 dias após emissão)"),
                    tags.th("CUST", style="text-align:center; font-size:10px;",
                            title="Código do contrato CUST se assinado"),
                    tags.th("Viabilidade", style="text-align:center;",
                            title="Status de viabilidade do BD entrada"),
                ),
            ),
            tags.tbody(*[_build_dc_row(r) for r in rows]),
            class_="dc-list-table",
        )

    @output
    @render.ui
    def dc_count_badge():
        n = len(_dc_filtered_rows())
        return tags.span(f"{n} de {_dc_total}", class_="panel-badge")

    # --- DATA CENTERS DETAIL PAGE ---
    @output
    @render.ui
    def datacenters_detail_page():
        if current_page.get() != "datacenters_detail":
            return tags.div(style="display:none")

        item_id = selected_dc.get()
        if item_id is None:
            return tags.div(style="display:none")

        # Buscar item
        r = next((x for x in DATACENTER_ROWS if str(x["item"]) == str(item_id)), None)
        if not r:
            return tags.div("Protocolo não encontrado.")

        # Pico e somas
        pico = r.get("potencia_max") or 0
        year_vals = r.get("year_values", {})
        year_status = r.get("year_status", {})

        # Header
        header = tags.div(
            tags.div(
                tags.div(r["empreendimento"] or "—", class_="dc-detail-empresa"),
                tags.div(r["main_protocol"], class_="dc-detail-proto"),
                tags.div(
                    tags.div(
                        tags.span("UF", class_="dc-detail-meta-label"),
                        tags.span(r["uf"] or "—", class_="dc-detail-meta-value"),
                        class_="dc-detail-meta-item",
                    ),
                    tags.div(
                        tags.span("Tensão", class_="dc-detail-meta-label"),
                        tags.span(f'{r["tensao"]} kV' if r["tensao"] != "—" else "—", class_="dc-detail-meta-value"),
                        class_="dc-detail-meta-item",
                    ),
                    tags.div(
                        tags.span("Tipo", class_="dc-detail-meta-label"),
                        tags.span(r["tipo"] or "—", class_="dc-detail-meta-value"),
                        class_="dc-detail-meta-item",
                    ),
                    tags.div(
                        tags.span("Status", class_="dc-detail-meta-label"),
                        tags.span(r["status"] or "—", class_="dc-detail-meta-value"),
                        class_="dc-detail-meta-item",
                    ),
                    class_="dc-detail-meta",
                ),
                class_="dc-detail-main",
            ),
            tags.div(
                tags.div(
                    tags.span("Conexão", class_="dc-detail-meta-label", style="display:block; margin-bottom:4px;"),
                    tags.div(r["conexao"] or "—", style="font-size:13px; color:var(--text); line-height:1.5;"),
                    style="margin-bottom:8px;",
                ),
                tags.div(
                    tags.span("Solicitação / Emissão", class_="dc-detail-meta-label", style="display:block; margin-bottom:4px;"),
                    tags.div(
                        f'{r.get("data_solicitacao") or "—"} → {r.get("data_emissao") or "Pendente"}',
                        style="font-size:12px; color:var(--text-mid); font-family:'JetBrains Mono',monospace;",
                    ),
                ),
                class_="dc-detail-side",
            ),
            class_="dc-detail-header",
        )

        # Sumário lateral
        contract_window = r.get("janela_contratavel", "—")
        documento = r.get("documento") or "—"
        analista = r.get("analista") or "—"
        related = r.get("related") or "—"
        sumario = tags.div(
            tags.div(
                tags.div("Janela Contratável", class_="label"),
                tags.div(contract_window, class_="value"),
                class_="dc-summary-card",
            ),
            tags.div(
                tags.div("Pico Solicitado", class_="label"),
                tags.div(f'{fmt_mw(pico)} MW' if pico else "—", class_="value"),
                tags.div("Maior valor de Ponta/FP no horizonte", class_="sub"),
                class_="dc-summary-card",
            ),
            tags.div(
                tags.div("Documento Emitido", class_="label"),
                tags.div(documento, class_="value", style="font-size:14px;"),
                class_="dc-summary-card",
            ),
            tags.div(
                tags.div("Analista", class_="label"),
                tags.div(analista, class_="value", style="font-size:13px;"),
                tags.div(f"Relacionados: {related}", class_="sub") if related != "—" else None,
                class_="dc-summary-card",
            ),
            class_="dc-summary",
        )

        # Horizon — cards por ano
        year_cards = []
        sorted_years = sorted(year_vals.keys())
        for y in sorted_years:
            v = year_vals.get(y, {})
            st = year_status.get(y, "")
            p = v.get("ponta")
            f = v.get("fora")
            has_data = p is not None or f is not None
            card_cls = f"dc-year-card {st}" if has_data else "dc-year-card empty"
            tag = tags.span("INÍCIO DO HORIZONTE", class_="dc-year-tag") if st == "current" else None
            year_cards.append(
                tags.div(
                    tags.div(str(y), class_="dc-year-num"),
                    tag,
                    tags.div(
                        tags.span("Ponta", class_="dc-year-label"),
                        tags.span(fmt_mw(p) if p else "—",
                                  class_="dc-year-val-p" if p else "dc-year-val-empty"),
                        class_="dc-year-row",
                    ),
                    tags.div(
                        tags.span("F. Ponta", class_="dc-year-label"),
                        tags.span(fmt_mw(f) if f else "—",
                                  class_="dc-year-val-f" if f else "dc-year-val-empty"),
                        class_="dc-year-row",
                    ),
                    class_=card_cls,
                )
            )

        horizon_panel = tags.div(
            tags.div(
                "Horizonte de Solicitação",
                tags.span(
                    f"Janela contratável: {contract_window}",
                    style="font-size:11px; color:var(--text-muted); font-weight:500; margin-left:auto;",
                ),
                class_="dc-horizon-title",
                style="display:flex; align-items:center;",
            ),
            tags.div(*year_cards, class_="dc-horizon-grid"),
            class_="dc-horizon-wrap",
        )

        # Origem dos dados (info técnica enxuta)
        origem_info = tags.div(
            tags.div(
                tags.span("Fonte dos dados", class_="panel-title"),
                class_="panel-header",
            ),
            tags.div(
                tags.div(
                    tags.span("Origem: ", style="color:var(--text-muted); font-size:12px;"),
                    tags.span(r["origem"], style="font-weight:600; font-size:13px;"),
                    style="margin-bottom:8px;",
                ),
                tags.div(
                    tags.span("Protocolo MUST: ", style="color:var(--text-muted); font-size:12px;"),
                    tags.span(r["fonte_must"],
                              style="font-family:'JetBrains Mono',monospace; font-weight:600; font-size:12px; color:var(--green-dark);"),
                ),
                style="padding:14px 18px;",
            ),
            class_="panel",
        )

        # ─── Bloco: Análise de Viabilidade ───
        viab_data = r.get("viabilidade_anos", {}) or {}
        viab_resumo = r.get("viabilidade_resumo", "Pendente")
        anos_viab = viab_data.get("anos", {}) if isinstance(viab_data, dict) else {}
        pendencias_list = r.get("pendencias", []) or []

        viab_pill_cls = _viab_pill_class(viab_resumo)

        # Linhas da tabela ano a ano
        viab_table_rows = []
        if anos_viab:
            for ano in sorted(anos_viab.keys()):
                v = anos_viab[ano]
                ano_viab = (v.get("viabilidade") or "").strip()
                ano_pill_cls = _viab_pill_class(ano_viab) if ano_viab else "viab-pill viab-pendente"
                viab_table_rows.append(
                    tags.tr(
                        tags.td(str(ano), style="font-weight:600; text-align:center;"),
                        tags.td(
                            tags.span(ano_viab or "—", class_=ano_pill_cls),
                            style="text-align:center;",
                        ),
                        tags.td(v.get("condicionantes") or "—",
                                class_="text-col", style="font-size:12px;"),
                        tags.td(v.get("sep") or "—",
                                class_="text-col", style="font-size:12px;"),
                        tags.td(v.get("limitado_ponta") or "—",
                                style="text-align:right; font-family:'JetBrains Mono',monospace; color:var(--ponta-text); font-weight:600;"),
                        tags.td(v.get("limitado_fp") or "—",
                                style="text-align:right; font-family:'JetBrains Mono',monospace; color:var(--fora-ponta-text); font-weight:600;"),
                    )
                )

        # Badges de pendência
        pendencia_badges = []
        for p in pendencias_list:
            cls = "pend-badge"
            if "Aguardando" in p:
                cls += " pend-warn"
            elif "condicionante" in p.lower():
                cls += " pend-orange"
            elif "limitado" in p.lower():
                cls += " pend-red"
            pendencia_badges.append(tags.span(f"⚠ {p}", class_=cls))

        viab_panel = tags.div(
            tags.div(
                tags.span("Análise de Viabilidade", class_="panel-title"),
                tags.span(viab_resumo, class_=viab_pill_cls, style="margin-left:auto;"),
                class_="panel-header", style="display:flex; align-items:center;",
            ),
            tags.div(
                # Pendências em destaque
                tags.div(*pendencia_badges,
                         style="display:flex; gap:8px; flex-wrap:wrap; padding:12px 18px 0;") if pendencia_badges else None,
                tags.table(
                    tags.thead(
                        tags.tr(
                            tags.th("Ano", style="text-align:center;"),
                            tags.th("Viabilidade", style="text-align:center;"),
                            tags.th("Condicionantes"),
                            tags.th("SEP"),
                            tags.th("Limitado P", style="text-align:right;"),
                            tags.th("Limitado FP", style="text-align:right;"),
                        )
                    ),
                    tags.tbody(*viab_table_rows) if viab_table_rows else
                    tags.tbody(tags.tr(
                        tags.td(
                            "Sem informações de viabilidade preenchidas. "
                            "Faça download do BD entrada para preencher.",
                            colspan="6",
                            style="text-align:center; padding:18px; color:var(--text-muted); font-style:italic;",
                        )
                    )),
                    class_="proto-table",
                ),
            ),
            class_="panel",
            style="margin-bottom:16px;",
        )

        return tags.div(
            tags.div(
                ui.input_action_button("btn_back_dc", "← Voltar a DataCenters", class_="back-btn", style="margin:0;"),
                tags.div(style="flex:1;"),
                ui.download_button("download_dc_detail", "⬇ Excel detalhe", class_="back-btn", style="margin:0;"),
                ui.download_button("download_bd_entrada_detail", "📥 BD entrada", class_="dc-btn-primary", style="margin:0;"),
                style="display:flex; gap:8px; align-items:center; margin-bottom:16px;",
            ),
            header,
            sumario,
            viab_panel,
            horizon_panel,
            origem_info,
        )

    # --- DATA CENTERS MATRIX PAGE (todos os anos lado a lado) ---
    def _dc_matrix_filtered():
        """Aplica filtros da matriz (separados dos filtros da lista)."""
        try:
            f_empr = (input.dcm_empr() or "").strip().lower()
        except Exception:
            f_empr = ""
        try:
            f_proto = (input.dcm_proto() or "").strip().lower()
        except Exception:
            f_proto = ""
        try:
            f_conexao = (input.dcm_conexao() or "").strip().lower()
        except Exception:
            f_conexao = ""
        try:
            f_rede = list(input.dcm_rede() or [])
        except Exception:
            f_rede = []
        try:
            f_kv = list(input.dcm_kv() or [])
        except Exception:
            f_kv = []
        try:
            f_viab = list(input.dcm_viab() or [])
        except Exception:
            f_viab = []
        try:
            f_status_select = list(input.dcm_status() or [])
        except Exception:
            f_status_select = []
        try:
            f_sort = input.dcm_sort() or "data_asc"
        except Exception:
            f_sort = "data_asc"
        f_emitido_pl = dcm_emitido_pl_filter.get()

        from datetime import datetime
        def _parse_dt(s):
            if not s or s in ("—", ""):
                return datetime.max
            try:
                return datetime.strptime(str(s), "%d/%m/%Y")
            except Exception:
                return datetime.max

        out = []
        for r in DATACENTER_ROWS:
            if f_empr:
                proto_text = (r.get("main_protocol") or "").upper()
                if "SAM" in proto_text:
                    haystack = str(r.get("ponto_label", "") or r.get("ponto_instalacao", "") or r.get("empreendimento", "")).lower()
                else:
                    haystack = str(r.get("empreendimento", "") or r.get("ponto_label", "")).lower()
                if f_empr not in haystack:
                    continue
            if f_proto and f_proto not in str(r.get("main_protocol", "")).lower():
                continue
            if f_conexao and f_conexao not in str(r.get("conexao", "")).lower():
                continue
            if f_rede and r.get("rede") not in f_rede:
                continue
            if f_kv and str(r.get("tensao", "")) not in f_kv:
                continue
            if f_viab and (r.get("viabilidade_resumo") or "Pendente") not in f_viab:
                continue
            if f_status_select and (r.get("status") or "—") not in f_status_select:
                continue
            if f_emitido_pl and _emitido_pl_state(r.get("data_emissao_pl")) != f_emitido_pl:
                continue
            out.append(r)

        sort_map = {
            "data_asc": (lambda r: _parse_dt(r.get("data_solicitacao")), False),
            "data_desc": (lambda r: _parse_dt(r.get("data_solicitacao")), True),
            "entrada_pl_asc": (lambda r: _parse_dt(r.get("data_entrada_pl")), False),
            "entrada_pl_desc": (lambda r: _parse_dt(r.get("data_entrada_pl")), True),
            "prazo_pl_asc": (lambda r: _parse_dt(r.get("prazo_analise_pl")), False),
            "prazo_pl_desc": (lambda r: _parse_dt(r.get("prazo_analise_pl")), True),
            "prazo_ons_asc": (lambda r: _parse_dt(r.get("prazo_emissao_ons")), False),
            "prazo_ons_desc": (lambda r: _parse_dt(r.get("prazo_emissao_ons")), True),
            "emissao_pl_asc": (lambda r: _parse_dt(r.get("data_emissao_pl")), False),
            "emissao_pl_desc": (lambda r: _parse_dt(r.get("data_emissao_pl")), True),
            "emissao_doc_asc": (lambda r: _parse_dt(r.get("data_emissao_doc")), False),
            "emissao_doc_desc": (lambda r: _parse_dt(r.get("data_emissao_doc")), True),
            "prazo_cust_asc": (lambda r: _parse_dt(r.get("prazo_cust")), False),
            "prazo_cust_desc": (lambda r: _parse_dt(r.get("prazo_cust")), True),
            "proto_asc": (lambda r: str(r.get("main_protocol") or ""), False),
            "proto_desc": (lambda r: str(r.get("main_protocol") or ""), True),
            "empr_asc": (lambda r: str(_excel_empreendimento_ponto(r) or "").lower(), False),
            "empr_desc": (lambda r: str(_excel_empreendimento_ponto(r) or "").lower(), True),
        }
        key_fn, rev = sort_map.get(f_sort, sort_map["data_asc"])
        out.sort(key=key_fn, reverse=rev)
        return out

    def _dc_matrix_all_years(rows):
        all_y = set()
        for r in rows:
            for y, vals in (r.get("year_values") or {}).items():
                if vals.get("ponta") is not None or vals.get("fora") is not None:
                    try:
                        all_y.add(int(y))
                    except Exception:
                        pass
        all_y = sorted(all_y)
        return all_y if all_y else list(DATACENTER_YEARS)

    def _build_matrix_row(r, all_years):
        year_vals = r.get("year_values") or {}
        year_status = r.get("year_status") or {}

        status_real = (r.get("status") or "").strip()
        sl = status_real.lower()
        if not status_real:
            status_class = "status-pill status-miss"; status_label = "—"
        elif "anul" in sl:
            status_class = "status-pill status-anulada"; status_label = status_real
        elif "cancel" in sl:
            status_class = "status-pill status-miss"; status_label = status_real
        elif "emit" in sl or "concl" in sl or "aprovado" in sl:
            status_class = "status-pill status-ok"; status_label = status_real
        elif "andamento" in sl or "análise" in sl or "analise" in sl:
            status_class = "status-pill status-warn"; status_label = status_real
        else:
            status_class = "status-pill status-warn"; status_label = status_real

        rede = r.get("rede") or "—"
        rede_class_map = {"DIST": "rede-dist", "RB": "rede-rb", "DIT": "rede-dit"}
        rede_class = rede_class_map.get(rede, "rede-empty")

        year_cells = []
        for y in all_years:
            vals = year_vals.get(y, {})
            p = vals.get("ponta")
            f_v = vals.get("fora")
            st = year_status.get(y, "")
            base_cls = f"matrix-cell {st}" if st else "matrix-cell"
            if p is not None:
                year_cells.append(tags.td(fmt_mw(p), class_=f"{base_cls} val-ponta"))
            else:
                year_cells.append(tags.td("—", class_=f"{base_cls} val-empty"))
            if f_v is not None:
                year_cells.append(tags.td(fmt_mw(f_v), class_=f"{base_cls} val-fp"))
            else:
                year_cells.append(tags.td("—", class_=f"{base_cls} val-empty"))

        # Status de cor (recalculado por render)
        pl_cls = _classify_today(r.get("prazo_analise_pl"), "pl",
                                  status=r.get("status"), protocol=r.get("main_protocol"),
                                  data_emissao_pl=r.get("data_emissao_pl"))
        ons_cls = _classify_today(r.get("prazo_emissao_ons"), "ons",
                                  status=r.get("status"), protocol=r.get("main_protocol"))
        pl_full_class = "date-cell prazo-pl" + (f" prazo-{pl_cls}" if pl_cls else "")
        ons_full_class = "date-cell prazo-ons" + (f" prazo-{ons_cls}" if ons_cls else "")

        # Pill do CUST
        cust_label = r.get("cust_label", "—")
        cust_status_v = r.get("cust_status", "")
        cust_pill_class = {
            "assinado": "cust-pill cust-assinado",
            "no_prazo": "cust-pill cust-no-prazo",
            "nao_assinado": "cust-pill cust-nao-assinado",
            "ptdis": "cust-pill cust-ptdis",
            "inviavel": "cust-pill cust-inviavel",
            "verificar": "cust-pill cust-verificar",
        }.get(cust_status_v, "cust-pill")

        # Pill viabilidade
        viab = r.get("viabilidade_resumo") or "Pendente"
        viab_pill_class = _viab_pill_class(viab)

        # Empreendimento + ponto
        ponto_label = r.get("ponto_label") or ""
        empr_main = (r.get("empreendimento") or "").strip()
        proto_text = r.get("main_protocol") or ""
        is_sam = "SAM" in proto_text.upper()
        # Para SAM: usar APENAS o ponto de contratação (ignora empreendimento)
        if is_sam:
            display_text = ponto_label or r.get("ponto_instalacao") or empr_main or "—"
            empr_cell = tags.div(display_text, class_="dc-empr-name", title=display_text)
            cell_title = display_text
        elif empr_main and ponto_label and ponto_label != empr_main:
            empr_cell = tags.div(
                tags.div(empr_main, class_="dc-empr-name"),
                tags.div(ponto_label, class_="dc-ponto-label"),
            )
            cell_title = empr_main
        elif empr_main:
            empr_cell = tags.div(empr_main, class_="dc-empr-name", title=empr_main)
            cell_title = empr_main
        elif ponto_label:
            empr_cell = tags.div(ponto_label, class_="dc-empr-name", title=ponto_label)
            cell_title = ponto_label
        else:
            empr_cell = tags.div("—", class_="dc-empr-name")
            cell_title = ""

        return tags.tr(
            tags.td(empr_cell, title=cell_title),
            tags.td(r["main_protocol"] or "—",
                    style="font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--green-dark); font-weight:600; text-align:center;"),
            tags.td("⋯", class_="matrix-toggle-spacer", title="Colunas agrupadas"),
            tags.td(r.get("data_solicitacao") or "—",
                    class_="date-cell matrix-collapsible-col", style="text-align:center;"),
            tags.td(r.get("data_entrada_pl") or "—",
                    class_="date-cell matrix-collapsible-col", style="text-align:center;"),
            tags.td(r.get("prazo_analise_pl") or "—",
                    class_=f"{pl_full_class} matrix-collapsible-col", style="text-align:center;"),
            tags.td(r.get("prazo_emissao_ons") or "—",
                    class_=f"{ons_full_class} matrix-collapsible-col", style="text-align:center;"),
            tags.td(tags.span(rede, class_=f"rede-pill {rede_class}"),
                    class_="matrix-collapsible-col", style="text-align:center;"),
            tags.td(r["tensao"] or "—", class_="matrix-collapsible-col", style="text-align:center;"),
            tags.td(tags.span(status_label, class_=status_class, title=status_real),
                    class_="matrix-collapsible-col", style="text-align:center;"),
            tags.td(r.get("data_emissao_pl") or "—",
                    class_="date-cell matrix-collapsible-col", style="text-align:center;"),
            tags.td(r.get("data_emissao_doc") or "—",
                    class_="date-cell matrix-collapsible-col", style="text-align:center;"),
            tags.td(r.get("prazo_cust") or "—",
                    class_="date-cell matrix-collapsible-col", style="text-align:center;"),
            tags.td(tags.span(cust_label, class_=cust_pill_class), class_="matrix-collapsible-col", style="text-align:center;"),
            tags.td(tags.span(viab, class_=viab_pill_class), class_="matrix-collapsible-col", style="text-align:center;"),
            *year_cells,
        )

    @output
    @render.ui
    def datacenters_matrix_page():
        if current_page.get() != "datacenters_matrix":
            return tags.div(style="display:none")

        return tags.div(
            tags.div(
                ui.input_action_button("btn_back_matrix", "← Voltar a DataCenters", class_="back-btn"),
                ui.download_button("download_dc_matrix", "⬇ Excel", class_="back-btn", style="margin:0;"),
                tags.div(
                    ui.download_button("download_bd_entrada", "📥 BD entrada", class_="dc-btn-primary", style="margin:0;"),
                    style="margin-left:auto;",
                ),
                style="display:flex; gap:8px; align-items:center; margin-bottom:8px;",
            ),
            tags.div("Solicitações com todos os valores solicitados", class_="page-title"),
            tags.div(
                "Tabela com todos os anos lado a lado. Verde claro = janela contratável (início do horizonte até 3 anos depois). Verde escuro = início do horizonte. Laranja = ano informado fora do horizonte contratável.",
                class_="page-subtitle",
            ),
            # Legenda
            tags.div(
                tags.span("Legenda:", style="font-weight:700; color:var(--text); margin-right:4px; font-size:12px;"),
                tags.span(INICIO_HORIZONTE_LABEL, class_="dc-legend-item", style="background:#D1FAE5; color:#065F46; border:1px solid #6EE7B7; padding:3px 9px; border-radius:999px; font-weight:600; font-size:12px;"),
                tags.span("Janela contratável", class_="dc-legend-item", style="background:#ECFDF5; color:#047857; border:1px solid #A7F3D0; padding:3px 9px; border-radius:999px; font-weight:600; font-size:12px;"),
                tags.span("Fora do horizonte", class_="dc-legend-item", style="background:#FFEDD5; color:#9A3412; border:1px solid #FDBA74; padding:3px 9px; border-radius:999px; font-weight:600; font-size:12px;"),
                style="display:flex; gap:8px; margin-bottom:14px; align-items:center; flex-wrap:wrap;",
            ),
            # Tabela renderizada inteira pelo output (evita problema de div wrapper dentro de table)
            tags.div(
                tags.div(
                    tags.span("Matriz de valores solicitados", class_="panel-title"),
                    ui.output_ui("dcm_count_badge"),
                    class_="panel-header",
                ),
                tags.div(
                    ui.output_ui("dcm_full_table"),
                    class_="dc-matrix-wrap",
                ),
                class_="dc-card-table",
            ),
        )

    @output
    @render.ui
    def dcm_full_table():
        rows = _dc_matrix_filtered()
        all_years = _dc_matrix_all_years(DATACENTER_ROWS)
        year_group_ths = []
        year_sub_ths = []
        for y in all_years:
            year_group_ths.append(tags.th(str(y), colspan="2",
                                          style="text-align:center; background:#FAFBFC; border-bottom:2px solid var(--border);"))
            year_sub_ths.append(tags.th("P", class_="col-ponta", style="text-align:center; font-size:10px;"))
            year_sub_ths.append(tags.th("FP", class_="col-fp", style="text-align:center; font-size:10px;"))
        return tags.table(
            tags.thead(
                tags.tr(
                    tags.th("Empreendimento / Ponto", rowspan="2"),
                    tags.th("Protocolo", style="text-align:center;", rowspan="2"),
                    tags.th(
                        tags.button("▸ Dados", type="button", class_="matrix-toggle-btn js-matrix-toggle", title="Expandir/retrair colunas entre Protocolo e os anos"),
                        class_="matrix-toggle-th",
                        rowspan="2",
                    ),
                    tags.th("Data Solic.", class_="matrix-collapsible-col", style="text-align:center; font-size:10px;", rowspan="2",
                            title="Data da Solicitação de Acesso (fila)"),
                    tags.th("Entrada PL", class_="matrix-collapsible-col", style="text-align:center; font-size:10px;", rowspan="2",
                            title="Data de chegada na PL para análise técnica"),
                    tags.th("Prazo PL", class_="matrix-collapsible-col", style="text-align:center; font-size:10px;", rowspan="2",
                            title="Prazo Análise Técnica PL"),
                    tags.th("Prazo ONS", class_="matrix-collapsible-col", style="text-align:center; font-size:10px;", rowspan="2",
                            title="Prazo Emissão PA - ONS"),
                    tags.th("Rede", class_="matrix-collapsible-col", style="text-align:center;", rowspan="2"),
                    tags.th("kV", class_="matrix-collapsible-col", style="text-align:center;", rowspan="2"),
                    tags.th("Status", class_="matrix-collapsible-col", style="text-align:center;", rowspan="2"),
                    tags.th("Emissão PL", class_="matrix-collapsible-col", style="text-align:center; font-size:10px;", rowspan="2"),
                    tags.th("Emissão Doc.", class_="matrix-collapsible-col", style="text-align:center; font-size:10px;", rowspan="2"),
                    tags.th("Prazo CUST", class_="matrix-collapsible-col", style="text-align:center; font-size:10px;", rowspan="2"),
                    tags.th("CUST", class_="matrix-collapsible-col", style="text-align:center; font-size:10px;", rowspan="2"),
                    tags.th("Viabilidade", class_="matrix-collapsible-col", style="text-align:center;", rowspan="2"),
                    *year_group_ths,
                ),
                tags.tr(*year_sub_ths),
            ),
            tags.tbody(*[_build_matrix_row(r, all_years) for r in rows]),
            class_="dc-matrix-table js-collapsible-matrix cols-collapsed",
        )

    @output
    @render.ui
    def dcm_count_badge():
        n = len(_dc_matrix_filtered())
        return tags.span(f"{n} de {_dc_total} solicitações", class_="panel-badge")

    def _same_proto(a, b):
        return str(a or "").strip().upper() == str(b or "").strip().upper()

    def _overview_protocol_detail_fallback(proto_id):
        """Detalhe para protocolos que não têm modelo em tb_aumentomust.

        A Visão Geral reúne todos os SGAs. Para SAM, o detalhe continua usando
        PROTOCOLS/tb_aumentomust. Para os demais tipos, o detalhe segue a mesma
        lógica do painel de DataCenters: usa as informações gerais do protocolo e,
        quando houver, busca valores de MUST em DATACENTER_ROWS ou em
        tb_mustpordisteuniconsumidora (DC_MUST_BY_PROTO).
        """
        ov = next((item for item in OVERVIEW_PROTOCOLS if _same_proto(item.get("protocolo"), proto_id)), None)
        dc_rows_proto = [r for r in DATACENTER_ROWS if _same_proto(r.get("main_protocol"), proto_id)]

        if ov is None and dc_rows_proto:
            first = dc_rows_proto[0]
            ov = {
                "protocolo": first.get("main_protocol"),
                "nome": first.get("empreendimento") or first.get("ponto_label") or first.get("main_protocol"),
                "nom_solicitacao": first.get("empreendimento") or first.get("ponto_label"),
                "nom_uf": first.get("uf"),
                "dsc_ptoconexao": first.get("conexao"),
                "dsc_status": first.get("status"),
                "id_solicitacao": first.get("id_solicitacao"),
                "tensao": first.get("tensao"),
            }

        if ov is None:
            return tags.div("Protocolo não encontrado.")

        info = _overview_row_info(ov)
        tipo_proto = _protocol_type(proto_id) or "—"
        nome = info.get("nome") or ov.get("nome") or ov.get("nom_solicitacao") or proto_id
        conexao = info.get("conexao") or clean_text(ov.get("dsc_ptoconexao"), "—")
        viab = info.get("viabilidade") or "—"

        info_cards = tags.div(
            tags.div(
                tags.div("Tipo SGA", class_="info-label"),
                tags.div(tipo_proto, class_="info-value"),
                class_="info-card",
            ),
            tags.div(
                tags.div("Rede", class_="info-label"),
                tags.div(info.get("rede") or "—", class_="info-value"),
                class_="info-card",
            ),
            tags.div(
                tags.div("Tensão", class_="info-label"),
                tags.div((f'{info.get("tensao")} kV' if info.get("tensao") and info.get("tensao") != "—" else "—"), class_="info-value"),
                class_="info-card",
            ),
            tags.div(
                tags.div("Viabilidade", class_="info-label"),
                tags.div(tags.span(viab, class_=_overview_viab_pill_class(viab)), class_="info-value"),
                class_="info-card",
            ),
            class_="detail-header-cards",
        )

        conexao_section = tags.div(
            tags.strong("Conexão", style="color: var(--cyan); margin-right:6px;"),
            conexao or "—",
            class_="single-point-info",
        )

        def _fmt_detail_mw(v):
            if v is None:
                return "—"
            try:
                return fmt_mw(v)
            except Exception:
                return str(v)

        rows_html = []
        if dc_rows_proto:
            for r in dc_rows_proto:
                yv = _apply_manual_must_overrides(proto_id, r.get("year_values") or {})
                ponto_label = r.get("ponto_label") or r.get("ponto_instalacao") or r.get("conexao") or "—"
                for year in sorted(yv):
                    vals = yv.get(year) or {}
                    p_val = vals.get("ponta")
                    f_val = vals.get("fora")
                    if p_val is None and f_val is None:
                        continue
                    rows_html.append(tags.tr(
                        tags.td(ponto_label, style="font-size:12px; color:var(--text-mid);"),
                        tags.td(str(year), style="text-align:center; font-weight:700;"),
                        tags.td(_fmt_detail_mw(p_val), class_=("val-empty" if p_val is None else "val-ponta")),
                        tags.td(_fmt_detail_mw(f_val), class_=("val-empty" if f_val is None else "val-fp")),
                        tags.td(r.get("fonte_must") or r.get("origem") or "—", style="font-size:11px; color:var(--text-muted);"),
                    ))
        else:
            yv, _ys = _overview_year_values(info)
            for year in sorted(yv):
                vals = yv.get(year) or {}
                p_val = vals.get("ponta")
                f_val = vals.get("fora")
                if p_val is None and f_val is None:
                    continue
                rows_html.append(tags.tr(
                    tags.td(conexao or "—", style="font-size:12px; color:var(--text-mid);"),
                    tags.td(str(year), style="text-align:center; font-weight:700;"),
                    tags.td(_fmt_detail_mw(p_val), class_=("val-empty" if p_val is None else "val-ponta")),
                    tags.td(_fmt_detail_mw(f_val), class_=("val-empty" if f_val is None else "val-fp")),
                    tags.td("tb_mustpordisteuniconsumidora" if DC_MUST_BY_PROTO.get(proto_id) else "—", style="font-size:11px; color:var(--text-muted);"),
                ))

        if rows_html:
            must_panel_body = tags.table(
                tags.thead(tags.tr(
                    tags.th("Ponto / Conexão"),
                    tags.th("Ano", style="text-align:center;"),
                    tags.th("Ponta (MW)", class_="col-ponta"),
                    tags.th("Fora Ponta (MW)", class_="col-fp"),
                    tags.th("Fonte"),
                )),
                tags.tbody(*rows_html),
                class_="must-table",
            )
        else:
            must_panel_body = tags.div(
                "Este protocolo não possui valores de MUST detalhados nas bases mapeadas para o painel.",
                style="padding:16px 18px; font-size:13px; color:var(--text-muted);",
            )

        must_panel = tags.div(
            tags.div(tags.span("Valores solicitados", class_="panel-title"), class_="panel-header"),
            must_panel_body,
            class_="panel",
            style="margin-bottom:12px",
        )

        desc_text = (
            clean_text(ov.get("dsc_solicitacao"), "")
            or clean_text(ov.get("dsc_objetivosolicitacao"), "")
            or clean_text(ov.get("nom_solicitacao"), "")
        )
        desc_panel = tags.div(
            tags.div(tags.span("Descrição da Solicitação", class_="panel-title"), class_="panel-header"),
            tags.div(
                tags.p(desc_text if desc_text else "Sem descrição disponível.",
                       style="font-size:13px; color: var(--text-mid); line-height:1.6; white-space:pre-wrap;"),
                style="padding: 16px 18px; max-height: 400px; overflow-y: auto;",
            ),
            class_="panel",
        )

        status_line = tags.div(
            tags.span("Status: ", style="font-weight:700; color:var(--text);"),
            tags.span(info.get("status") or "—", style="color:var(--text-mid);"),
            tags.span("  •  ", style="color:var(--text-dim); margin:0 6px;"),
            tags.span("Emissão Doc.: ", style="font-weight:700; color:var(--text);"),
            tags.span(info.get("data_emissao_doc") or "—", style="color:var(--text-mid);"),
            tags.span("  •  ", style="color:var(--text-dim); margin:0 6px;"),
            tags.span("Prazo ONS: ", style="font-weight:700; color:var(--text);"),
            tags.span(info.get("prazo_emissao_ons") or "—", style="color:var(--text-mid);"),
            style="font-size:13px; margin-bottom:12px;",
        )

        return tags.div(
            ui.input_action_button("btn_back", "← Voltar a Visão Geral", class_="back-btn"),
            tags.div(proto_id, class_="page-title"),
            tags.div(nome, class_="detail-nome"),
            info_cards,
            conexao_section,
            status_line,
            tags.div(
                tags.div(must_panel),
                desc_panel,
                class_="detail-grid",
            ),
        )

    # --- DETAIL PAGE ---
    @output
    @render.ui
    def detail_page():
        if current_page.get() != "detail":
            return tags.div(style="display:none")

        proto_id = selected_proto.get()
        if proto_id is None:
            return tags.div(style="display:none")

        p = None
        for item in PROTOCOLS:
            if _same_proto(item.get("protocolo"), proto_id):
                p = item
                break
        if p is None:
            return _overview_protocol_detail_fallback(proto_id)

        pi = point_idx.get()
        n_pontos = len(p["pontos"])

        # Info cards
        info_cards = tags.div(
            tags.div(
                tags.div("CUST", class_="info-label"),
                tags.div(p["cust"], class_="info-value"),
                class_="info-card",
            ),
            tags.div(
                tags.div("Data Assinatura", class_="info-label"),
                tags.div(p["data_assinatura"], class_="info-value"),
                class_="info-card",
            ),
            tags.div(
                tags.div("Tensão", class_="info-label"),
                tags.div(f'{p["tensao"]} kV', class_="info-value"),
                class_="info-card",
            ),
            tags.div(
                tags.div("Pontos de Conexão", class_="info-label"),
                tags.div(str(n_pontos), class_="info-value"),
                class_="info-card",
            ),
            class_="detail-header-cards",
        )

        # Connection tabs or single point info
        if n_pontos > 1:
            tabs = []
            for ci, pt in enumerate(p["pontos"]):
                cls = "conn-tab active" if ci == pi else "conn-tab"
                tabs.append(tags.button(pt["instalacao"], class_=cls, **{"data-idx": str(ci)}))
            conn_section = tags.div(*tabs, class_="conn-tabs")
        else:
            pt = p["pontos"][0]
            conn_section = tags.div(
                tags.strong(pt["cod"], style="color: var(--cyan)"),
                f' — {pt["instalacao"]}',
                class_="single-point-info",
            )

        # MUST tables — lógica de exibição por ponto selecionado
        tables_html = []

        def _get_val_for_point(vals_dict, cod):
            """Retorna o valor para o ponto com código cod, ou vazio se não existe."""
            if isinstance(vals_dict, dict):
                return vals_dict.get(cod, "")
            # Compatibilidade com formato antigo (lista)
            return ""

        # Chave do ponto selecionado: (codigo_ons, instalacao)
        if pi < len(p["pontos"]):
            ponto_sel = p["pontos"][pi]
            ponto_key_sel = (ponto_sel["cod"], ponto_sel["instalacao"])
        else:
            ponto_key_sel = ("", "")

        def _build_must_row(must_dict, ano, cod):
            p_vals = must_dict.get(ano, {}).get("ponta", {})
            f_vals = must_dict.get(ano, {}).get("fora", {})
            p_val = _get_val_for_point(p_vals, cod)
            f_val = _get_val_for_point(f_vals, cod)
            p_class = "val-empty" if p_val in ("", "0", "—") else "val-ponta"
            f_class = "val-empty" if f_val in ("", "0", "—") else "val-fp"
            return tags.tr(
                tags.td(_display_ano_label(ano)),
                tags.td(p_val if p_val else "—", class_=p_class),
                tags.td(f_val if f_val else "—", class_=f_class),
            )

        def _build_must_table(rows_list):
            return tags.div(
                tags.table(
                    tags.thead(tags.tr(
                        tags.th("Ano"),
                        tags.th("Ponta (MW)", class_="col-ponta"),
                        tags.th("Fora Ponta (MW)", class_="col-fp"),
                    )),
                    tags.tbody(*rows_list),
                    class_="must-table",
                ),
                class_="panel",
                style="margin-bottom:12px",
            )

        def _periodo_has_data_for_point(per, ano, cod):
            """Verifica se o período tem dado real para o ponto cod nesse ano."""
            p_vals = per["must"].get(ano, {}).get("ponta", {})
            f_vals = per["must"].get(ano, {}).get("fora", {})
            p_val = _get_val_for_point(p_vals, cod)
            f_val = _get_val_for_point(f_vals, cod)
            return bool(p_val and p_val not in ("0", "—")) or bool(f_val and f_val not in ("0", "—"))

        # Separar períodos que têm Ano Corrente para o ponto selecionado
        periodos_ac = []   # Períodos com Ano Corrente para este ponto
        periodos_hz = []   # Períodos com horizonte (Ano 2+) para este ponto

        for per in p["periodos"]:
            has_ac = _periodo_has_data_for_point(per, "Ano Corrente", ponto_key_sel)
            hz_anos = [a for a in per["must"].keys() if a != "Ano Corrente"]
            has_hz = any(_periodo_has_data_for_point(per, a, ponto_key_sel) for a in hz_anos)

            if has_ac:
                periodos_ac.append(per)
            if has_hz and not has_ac:
                # Período só de horizonte (sem Ano Corrente para este ponto)
                periodos_hz.append(per)
            elif has_hz and has_ac:
                # Período com Ano Corrente E horizonte (ex: SUMARE Jan-Dez com tudo)
                periodos_hz.append(per)

        tem_quebra = len(periodos_ac) > 1

        if tem_quebra:
            # 1) Uma tabela por período com Ano Corrente
            for per in periodos_ac:
                tables_html.append(
                    tags.div(f'Período: {per["inicio"]} — {per["fim"]}', class_="period-label")
                )
                trows = [_build_must_row(per["must"], "Ano Corrente", ponto_key_sel)]
                tables_html.append(_build_must_table(trows))

            # 2) Tabela de horizonte (Ano 2+) — priorizar período Janeiro-Dezembro
            # como fonte, pois é onde ficam os valores do horizonte completo.
            hz_source = None
            for per in periodos_hz:
                if per["inicio"] == "Janeiro" and per["fim"] == "Dezembro":
                    hz_source = per
                    break
            if hz_source is None and periodos_hz:
                hz_source = periodos_hz[0]
            if hz_source is None and periodos_ac:
                hz_source = periodos_ac[0]
            if hz_source:
                horizon_anos = [a for a in hz_source["must"].keys() if a != "Ano Corrente"
                                and _periodo_has_data_for_point(hz_source, a, ponto_key_sel)]
                if horizon_anos:
                    tables_html.append(
                        tags.div("Horizonte — Anos seguintes", class_="period-label")
                    )
                    trows = [_build_must_row(hz_source["must"], ano, ponto_key_sel) for ano in horizon_anos]
                    tables_html.append(_build_must_table(trows))
        else:
            # Sem quebra — mostrar tudo numa tabela por período
            for per in p["periodos"]:
                anos_com_dado = [a for a in per["must"].keys()
                                 if _periodo_has_data_for_point(per, a, ponto_key_sel)]
                if not anos_com_dado:
                    continue
                tables_html.append(
                    tags.div(f'Período: {per["inicio"]} — {per["fim"]}', class_="period-label")
                )
                trows = [_build_must_row(per["must"], ano, ponto_key_sel) for ano in anos_com_dado]
                tables_html.append(_build_must_table(trows))

        # Painel de descrição da solicitação (substitui o gráfico)
        dsc_text = p.get("dsc_solicitacao", "")
        desc_panel = tags.div(
            tags.div(
                tags.span("Descrição da Solicitação", class_="panel-title"),
                class_="panel-header",
            ),
            tags.div(
                tags.p(dsc_text if dsc_text else "Sem descrição disponível.",
                       style="font-size:13px; color: var(--text-mid); line-height:1.6; white-space:pre-wrap;"),
                style="padding: 16px 18px; max-height: 400px; overflow-y: auto;",
            ),
            class_="panel",
        )

        return tags.div(
            ui.input_action_button("btn_back", "← Voltar a Visão Geral", class_="back-btn"),
            tags.div(proto_id, class_="page-title"),
            tags.div(p["nome"], class_="detail-nome"),
            info_cards,
            conn_section,
            tags.div(
                tags.div(*tables_html),
                desc_panel,
                class_="detail-grid",
            ),
        )

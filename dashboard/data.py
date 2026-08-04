"""Carga inicial e preparação dos dados da aplicação.

ESTRATÉGIA OFFLINE/POSIT:
- `viabilidades.xlsx` continua sendo a FONTE DE VERDADE: cada linha = uma linha no painel.
- O SQL NÃO é acessado durante a inicialização do app.
- Os dados vindos do servidor são lidos de `dashboard_sql_cache.pkl.gz`, gerado previamente
  pelo script `atualizar_base_sql.py` em uma máquina com ODBC.
"""

import time as _time
from datetime import datetime

import pandas as pd

from .constants import YEARS_DC
from .dashboard_cache import load_sql_cache, resolve_cache_path, resolve_viabilidades_path
from .viabilidade_source import (
    load_viabilidades, get_viabilidade_resumo, compute_pendencias,
    match_ponto_to_instalacao,
)
from .transforms import (
    transform_eav_to_model,
    transform_solicitacoes_meta,
    transform_datacenter_must_model,
    compute_rede,
    compute_pico_horizonte,
    compute_prazo_pl,
    compute_prazo_emissao_ons,
    clean_text,
    pick_first_date,
    apply_cust_deadline_override,
    apply_cust_status_override,
    signed_cust_info_for_protocol,
)
from .utils import fmt_date, normalize_uf, viabilidade_sga_label

_t0 = _time.perf_counter()


def _log(msg, t_start=None):
    """Log com timestamp + duração se t_start fornecido."""
    elapsed = _time.perf_counter() - _t0
    if t_start is not None:
        dur = _time.perf_counter() - t_start
        print(f"[DC] [{elapsed:6.1f}s] {msg} (durou {dur:.1f}s)", flush=True)
    else:
        print(f"[DC] [{elapsed:6.1f}s] {msg}", flush=True)


_log("Iniciando carga offline…")


def _fmt_cache_generated_at(val, fallback_path=None):
    """Formata a data de atualização do cache para exibição na UI."""
    if val:
        try:
            dt = pd.to_datetime(val, errors="coerce")
            if pd.notna(dt):
                return dt.strftime("%d/%m/%Y %H:%M:%S")
        except Exception:
            pass
    if fallback_path is not None:
        try:
            return datetime.fromtimestamp(fallback_path.stat().st_mtime).strftime("%d/%m/%Y %H:%M:%S")
        except Exception:
            pass
    return "—"


# ─── BD Entrada (FONTE DE VERDADE) ─────────────────────────────────────
_VIAB_PATH = resolve_viabilidades_path()

_t = _time.perf_counter()
_log(f"📂 Lendo viabilidades.xlsx: {_VIAB_PATH}")
VIABILIDADES_ENTRIES = load_viabilidades(_VIAB_PATH)
_log(f"  ↳ {len(VIABILIDADES_ENTRIES)} entradas lidas", _t)

if not VIABILIDADES_ENTRIES:
    raise RuntimeError(
        f"\n\n❌ '{_VIAB_PATH}' foi encontrado mas está VAZIO ou ilegível.\n"
        f"   Verifique se a aba se chama 'Pontos' (ou 'Viabilidade') e tem dados.\n"
    )

_PROTOCOLS_NEEDED = sorted({
    (e.get("protocolo") or "").strip()
    for e in VIABILIDADES_ENTRIES
    if (e.get("protocolo") or "").strip()
})
_log(f"  ↳ Protocolos únicos no Excel: {len(_PROTOCOLS_NEEDED)}")

_com_viab = sum(1 for e in VIABILIDADES_ENTRIES if e.get("anos"))
_log(f"📊 Carregadas {len(VIABILIDADES_ENTRIES)} linhas de '{_VIAB_PATH.name}' ({_com_viab} com viabilidade)")

# ─── Dados SQL em cache, sem ODBC no Posit ──────────────────────────────
_t = _time.perf_counter()
try:
    _CACHE_PATH = resolve_cache_path(require_exists=True)
    _log(f"📦 Lendo cache SQL: {_CACHE_PATH}")
    _SQL_CACHE = load_sql_cache(_CACHE_PATH)
except FileNotFoundError as exc:
    raise FileNotFoundError(
        "\n\n❌ Cache SQL não encontrado.\n"
        "   Rode, em uma máquina com ODBC e acesso ao SQL Server:\n\n"
        "       python atualizar_base_sql.py\n\n"
        "   Depois coloque o cache gerado na mesma pasta do app ou defina DASHBOARD_DATA_DIR / DASHBOARD_CACHE_PATH.\n\n"
        f"Detalhe original:\n{exc}"
    ) from exc

_log(f"  ↳ Cache gerado em: {_SQL_CACHE.get('generated_at', 'data desconhecida')}", _t)
CACHE_UPDATED_AT = _fmt_cache_generated_at(_SQL_CACHE.get("generated_at"), _CACHE_PATH)

_cached_protocols = set(_SQL_CACHE.get("protocols_needed") or [])
missing_in_cache = sorted(set(_PROTOCOLS_NEEDED) - _cached_protocols)
if missing_in_cache:
    print(
        "[DC] ⚠ O viabilidades.xlsx tem protocolos que não estavam no cache SQL. "
        "Rode atualizar_base_sql.py novamente. Exemplos: " + ", ".join(missing_in_cache[:10]),
        flush=True,
    )

raw = _SQL_CACHE.get("raw", pd.DataFrame())
raw_full = _SQL_CACHE.get("raw_full", raw)
solicitacoes_raw = _SQL_CACHE.get("solicitacoes_raw", pd.DataFrame())
dc_must_raw = _SQL_CACHE.get("dc_must_raw", pd.DataFrame())
analise_raw = _SQL_CACHE.get("analise_raw", pd.DataFrame())
cust_raw = _SQL_CACHE.get("cust_raw", pd.DataFrame())
documentos_raw = _SQL_CACHE.get("documentos_raw", pd.DataFrame())
_log(f"🔄 Documentos no cache: {len(documentos_raw)} linhas")

# ─── Transformações a partir dos DataFrames em cache ────────────────────
_t = _time.perf_counter()
_prebuilt_protocols = _SQL_CACHE.get("model_protocols")
if isinstance(_prebuilt_protocols, list):
    _log(f"⚡ Usando modelo de protocolos pré-processado ({len(_prebuilt_protocols)} protocolos)…")
    PROTOCOLS = _prebuilt_protocols
else:
    _log(f"🔄 Transformando EAV em modelo de protocolos ({len(raw_full)} linhas)…")
    PROTOCOLS = transform_eav_to_model(raw_full) if raw_full is not None and not raw_full.empty else []
PROTOCOLS_BY_PROTO = {p["protocolo"]: p for p in PROTOCOLS}
_log(f"  ↳ {len(PROTOCOLS)} protocolos modelados", _t)

_t = _time.perf_counter()
_prebuilt_solicitacoes_meta = _SQL_CACHE.get("solicitacoes_meta")
if isinstance(_prebuilt_solicitacoes_meta, dict):
    _log(f"⚡ Usando metadados pré-processados ({len(_prebuilt_solicitacoes_meta)} protocolos)…")
    SOLICITACOES_META = _prebuilt_solicitacoes_meta
else:
    _log(f"🔄 Indexando metadados por protocolo ({len(solicitacoes_raw)} linhas)…")
    SOLICITACOES_META = transform_solicitacoes_meta(solicitacoes_raw)
_log(f"  ↳ {len(SOLICITACOES_META)} protocolos indexados", _t)

def _build_overview_protocols(solicitacoes_meta, protocols_by_proto):
    """Une todos os protocolos do cache com os modelos de MUST disponíveis.

    A Visão Geral não deve ficar limitada aos protocolos com registros em
    tb_aumentomust. Cada solicitação vinda de sgacesso.tb_solicitacao entra
    na lista, e os SAM com modelo detalhado continuam recebendo pontos,
    períodos e valores solicitados.
    """
    merged = {}

    for proto, meta in (solicitacoes_meta or {}).items():
        rec = dict(meta or {})
        rec.setdefault("protocolo", proto)
        rec.setdefault("nome", rec.get("nom_internosolicitacao") or rec.get("nom_solicitacao") or proto)
        rec.setdefault("cust", rec.get("cod_contrato") or "—")
        rec.setdefault("data_assinatura", fmt_date(rec.get("din_assinaturacontrato")) if rec.get("din_assinaturacontrato") is not None else "—")
        rec.setdefault("tensao", "")
        rec.setdefault("pontos", [])
        rec.setdefault("periodos", [])
        merged[proto] = rec

    for proto, model in (protocols_by_proto or {}).items():
        rec = dict(merged.get(proto, {}))
        rec.update(model or {})
        rec.setdefault("protocolo", proto)
        rec.setdefault("nome", rec.get("nom_internosolicitacao") or rec.get("nom_solicitacao") or proto)
        merged[proto] = rec

    def _sort_key(item):
        rec = item[1]
        dt = pd.to_datetime(rec.get("din_solicitacao") or rec.get("din_solicitacaoacesso"), errors="coerce")
        return (pd.Timestamp.max if pd.isna(dt) else dt, item[0])

    return [rec for _proto, rec in sorted(merged.items(), key=_sort_key)]


OVERVIEW_PROTOCOLS = _build_overview_protocols(SOLICITACOES_META, PROTOCOLS_BY_PROTO)
_log(f"🔄 Protocolos na Visão Geral: {len(OVERVIEW_PROTOCOLS)}")

_t = _time.perf_counter()
_prebuilt_dc_must = _SQL_CACHE.get("dc_must_by_proto")
if isinstance(_prebuilt_dc_must, dict):
    _log(f"⚡ Usando MUST SPA/RPA pré-processado ({len(_prebuilt_dc_must)} protocolos)…")
    DC_MUST_BY_PROTO = _prebuilt_dc_must
else:
    _log(f"🔄 Indexando MUST SPA/RPA por protocolo ({len(dc_must_raw)} linhas)…")
    DC_MUST_BY_PROTO = transform_datacenter_must_model(dc_must_raw)
_log(f"  ↳ {len(DC_MUST_BY_PROTO)} protocolos com MUST", _t)

# Análise técnica (apenas tipo 13 = PL) — indexada por id_solicitacao
ANALISE_TECNICA_BY_SOLIC = {}
if analise_raw is not None and not analise_raw.empty:
    for _, row in analise_raw.iterrows():
        sid = row.get("id_solicitacao")
        if sid is None or pd.isna(sid):
            continue
        ANALISE_TECNICA_BY_SOLIC[sid] = {
            "din_solicitacao": row.get("din_solicitacao"),
            "din_envioanalise": row.get("din_envioanalise"),
            "val_prazo": row.get("val_prazo"),
        }
_log(f"🔄 Análises técnicas PL indexadas: {len(ANALISE_TECNICA_BY_SOLIC)}")

# CUST assinado
CUST_BY_PROTO = {}
if cust_raw is not None and not cust_raw.empty:
    for _, row in cust_raw.iterrows():
        proto = str(row.get("num_protocolo") or "").strip()
        if not proto:
            continue
        raw_info = {
            "num_protocolo": proto,
            "id_contrato": row.get("id_contrato"),
            "cod_contrato": str(row.get("cod_contrato") or "").strip(),
            "dat_inicio_vigencia": row.get("dat_inicio_vigencia"),
            "dat_assinatura": row.get("dat_assinatura"),
        }
        meta = (
            (SOLICITACOES_META or {}).get(proto)
            or (SOLICITACOES_META or {}).get(proto.upper())
            or {}
        )
        cust_info = signed_cust_info_for_protocol(proto, meta, raw_info)
        if cust_info:
            CUST_BY_PROTO[proto] = cust_info
_log(f"🔄 Contratos CUST indexados: {len(CUST_BY_PROTO)}")


def _find_cust_info(protocols):
    for proto in protocols or []:
        key = str(proto or "").strip()
        if not key:
            continue
        for candidate in (key, key.upper()):
            info = CUST_BY_PROTO.get(candidate)
            if info:
                return info
    return None


def _set_viabilidade_display(entry, label):
    display = dict(entry)
    anos_display = {}
    for ano, vals in (entry.get("anos") or {}).items():
        vals_copy = dict(vals or {})
        vals_copy["viabilidade"] = label
        anos_display[ano] = vals_copy
    display["viabilidade_geral"] = label
    display["anos"] = anos_display
    return display


def _is_viabilidade_inviavel(label):
    text = str(label or "").strip().lower()
    return (
        "invi" in text
        or "não vi" in text
        or "nao vi" in text
        or "negad" in text
    )


def _is_viabilidade_sem_resultado(label):
    text = str(label or "").strip().lower()
    return text in ("", "—", "-", "nenhum", "pendente", "em análise", "em analise")


def _manual_viabilidade_geral(entry):
    value = str((entry or {}).get("viabilidade_geral") or "").strip()
    return "" if _is_viabilidade_sem_resultado(value) else value


def _document_type_allowed_for_protocol(proto):
    """Mapeia tipo de SGA para id_tpdocumento em sgacesso.tb_documento."""
    p = str(proto or "").strip().upper()
    parts = p.split("-")
    tipo = parts[1] if len(parts) >= 2 and parts[0] == "SGA" else (parts[0] if parts else "")
    if tipo == "SFX":
        return {1}
    if tipo == "SAM":
        return {3}
    if tipo in {"SPA", "RPA", "RVA"}:
        return {12}
    if tipo == "SPT":
        return {13}
    return set()


def _clean_doc_text(val):
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s in ("", "—", "-", "None", "nan", "NaT", "NULL") else s


def _build_documentos_by_solic(df):
    """Indexa documentos emitidos por id_solicitacao."""
    out = {}
    if df is None or df.empty:
        return out
    for _, row in df.iterrows():
        sid = row.get("id_solicitacao")
        if sid is None or pd.isna(sid):
            continue
        try:
            sid_key = int(sid)
        except Exception:
            sid_key = sid
        try:
            id_doc = int(row.get("id_documento", row.get("id_tpdocumento")))
        except Exception:
            id_doc = None
        out.setdefault(sid_key, []).append({
            "id_documento": id_doc,  # valor de tb_documento.id_tpdocumento
            "num_documento": _clean_doc_text(row.get("num_documento_emitido_doc")),
            "din_criacao": pd.to_datetime(row.get("din_emissao_documento_doc"), errors="coerce"),
        })
    return out


DOCUMENTOS_BY_SOLIC = _build_documentos_by_solic(documentos_raw)
_log(f"🔄 Documentos emitidos indexados: {len(DOCUMENTOS_BY_SOLIC)} solicitações")


def _documento_emitido_from_docs(id_solicitacao, proto, meta):
    """Retorna (documento_emitido, data_emissao_ons).

    Documento emitido: prioriza inbound.sgacesso.tb_documento, via id_solicitacao.
    Data de emissão ONS: prioriza bca.dbo.tb_solicitacaoacesso.din_emissaodocumento.
    O campo tb_documento.din_criacao é data de criação do registro e fica apenas
    como fallback quando a data oficial da BCA não existir.
    """
    fallback_doc = clean_text(meta.get("num_documento_emitido"), "")
    fallback_dt = meta.get("din_emissaodocumento")

    if id_solicitacao is None or pd.isna(id_solicitacao):
        return fallback_doc, fallback_dt
    try:
        sid_key = int(id_solicitacao)
    except Exception:
        sid_key = id_solicitacao

    allowed = _document_type_allowed_for_protocol(proto)
    if not allowed:
        return fallback_doc, fallback_dt

    docs = [
        d for d in DOCUMENTOS_BY_SOLIC.get(sid_key, [])
        if d.get("id_documento") in allowed and d.get("num_documento")
    ]
    if not docs:
        return fallback_doc, fallback_dt

    docs = sorted(docs, key=lambda d: pd.Timestamp.min if pd.isna(d.get("din_criacao")) else d.get("din_criacao"))
    nums = []
    for d in docs:
        num = d.get("num_documento")
        if num and num not in nums:
            nums.append(num)

    bca_dt = pd.to_datetime(fallback_dt, errors="coerce")
    datas = [d.get("din_criacao") for d in docs if pd.notna(d.get("din_criacao"))]
    data_doc_fallback = max(datas) if datas else fallback_dt
    data_emissao_ons = bca_dt if pd.notna(bca_dt) else data_doc_fallback
    documento_emitido = "; ".join(nums) if nums else fallback_doc
    return documento_emitido, data_emissao_ons


_log(f"📌 Com viabilidade preenchida: {_com_viab}")

# ─── Helpers ───────────────────────────────────────────────────────────
def _to_float(v):
    if v is None or v == "" or v == "—":
        return None
    try:
        return float(str(v).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _build_year_values_from_sam_ponto(model, ponto_instalacao_match, data_solicitacao_str):
    """Para um SAM com fuzzy match resolvido, monta year_values do ponto."""
    year_values = {}
    if not model or not ponto_instalacao_match:
        return year_values
    # Achar a chave (cod, instalacao) correspondente
    pk = None
    for pt in model.get("pontos", []):
        if pt.get("instalacao") == ponto_instalacao_match:
            pk = (pt.get("cod"), pt.get("instalacao"))
            break
    if not pk:
        return year_values

    # Determinar ano base
    base_year = None
    if data_solicitacao_str and data_solicitacao_str != "—":
        try:
            from datetime import datetime
            base_year = datetime.strptime(data_solicitacao_str, "%d/%m/%Y").year
        except Exception:
            pass

    for per in model.get("periodos", []):
        for ano_label, vals in (per.get("must") or {}).items():
            p_dict = vals.get("ponta", {}) if isinstance(vals.get("ponta"), dict) else {}
            f_dict = vals.get("fora", {}) if isinstance(vals.get("fora"), dict) else {}
            p_val = p_dict.get(pk)
            f_val = f_dict.get(pk)

            year_num = None
            if isinstance(ano_label, int):
                year_num = ano_label
            elif base_year:
                if "Corrente" in str(ano_label):
                    year_num = base_year
                elif str(ano_label).startswith("Ano "):
                    try:
                        n = int(str(ano_label).split()[-1])
                        year_num = base_year + (n - 1)
                    except ValueError:
                        pass
            if year_num is None:
                continue

            pf = _to_float(p_val)
            ff = _to_float(f_val)
            if pf is not None or ff is not None:
                ex = year_values.get(year_num, {})
                year_values[year_num] = {
                    "ponta": pf if pf is not None else ex.get("ponta"),
                    "fora": ff if ff is not None else ex.get("fora"),
                }
    return year_values


def _build_year_values_from_spa(dc_must_data, data_solicitacao_str):
    """Para SPA/RPA, lê year_values de tb_mustpordisteuniconsumidora.

    O dict retornado por transform_datacenter_must_model já vem com
    a chave 'year_values' pronta no formato {ano: {ponta, fora}}.
    """
    if not dc_must_data:
        return {}
    raw_year_values = dc_must_data.get("year_values") or {}
    out = {}
    for ano, vals in raw_year_values.items():
        try:
            year_num = int(ano)
        except (ValueError, TypeError):
            continue
        p = _to_float(vals.get("ponta"))
        f = _to_float(vals.get("fora"))
        if p is not None or f is not None:
            out[year_num] = {"ponta": p, "fora": f}
    return out


def _build_year_values_from_excel(entry):
    """PTDis: pega MUST P/FP direto do BD entrada."""
    year_values = {}
    for ano, vals in (entry.get("anos") or {}).items():
        p = _to_float(vals.get("must_ponta"))
        f = _to_float(vals.get("must_fora"))
        if p is not None or f is not None:
            year_values[ano] = {"ponta": p, "fora": f}
    return year_values


def _apply_manual_must_overrides(proto, year_values):
    """Ajustes pontuais validados manualmente."""
    if str(proto or "").strip().upper() == "SGA-SAM-0117/2026":
        out = {y: dict(vals or {}) for y, vals in (year_values or {}).items()}
        vals_2030 = dict(out.get(2030) or {})
        vals_2030["fora"] = 904.904
        out[2030] = vals_2030
        return out
    return year_values


# ─── Construir DATACENTER_ROWS a partir das viabilidades ──────────────
_t = _time.perf_counter()
_log(f"🏗️  Construindo {len(VIABILIDADES_ENTRIES)} linhas do painel (enriquecendo com banco)…")
DATACENTER_ROWS = []

for idx, entry in enumerate(VIABILIDADES_ENTRIES, start=1):
    proto = entry["protocolo"]
    ponto_text = entry["ponto"]

    # Metadados do banco
    meta = SOLICITACOES_META.get(proto, {})
    model = PROTOCOLS_BY_PROTO.get(proto)  # SAM
    dc_must = DC_MUST_BY_PROTO.get(proto)  # SPA/RPA

    # Análise técnica (PL)
    id_solic_meta = meta.get("id_solicitacao")
    analise_pl = ANALISE_TECNICA_BY_SOLIC.get(id_solic_meta) if id_solic_meta else None
    data_entrada_pl = analise_pl.get("din_solicitacao") if analise_pl else None
    data_envio_pl = analise_pl.get("din_envioanalise") if analise_pl else None
    prazo_pl = compute_prazo_pl(
        data_entrada_pl,
        analise_pl.get("val_prazo") if analise_pl else None,
    )

    # Prazo ONS
    prazo_ons = compute_prazo_emissao_ons(
        meta.get("din_aceitesolicitacao"),
        meta.get("val_prazoemissao"),
        meta.get("val_periodointerrompida"),
    )

    # Data solicitação (para horizonte)
    data_solic = fmt_date(pick_first_date(meta.get("din_solicitacao"), meta.get("din_solicitacaoacesso")))

    # ─── Determinar tensão e rede ───
    # Prioridade: BD entrada → banco
    tensao = entry.get("tensao") or ""
    if not tensao and model:
        tensao = model.get("tensao") or ""
    if not tensao:
        tensao = "—"

    # Rede é SEMPRE calculada pela lógica do painel.
    rede = compute_rede(proto, tensao)

    # ─── year_values: depende da fonte ───
    year_values = {}
    fonte_must = "—"

    if model and len(model.get("pontos", [])) > 0:
        # SAM: fazer fuzzy match do ponto
        instalacoes = [pt.get("instalacao") for pt in model.get("pontos", [])]
        match_inst = match_ponto_to_instalacao(ponto_text, instalacoes)
        if not match_inst and len(instalacoes) == 1:
            match_inst = instalacoes[0]
        if match_inst:
            year_values = _build_year_values_from_sam_ponto(model, match_inst, data_solic)
            fonte_must = f"SAM-banco/{match_inst}"
    elif dc_must:
        # SPA/RPA
        year_values = _build_year_values_from_spa(dc_must, data_solic)
        fonte_must = "SPA-banco"

    # PTDis: se o usuário preencheu MUST P/FP no Excel, usa
    excel_year_values = _build_year_values_from_excel(entry)
    if excel_year_values:
        for y, vals in excel_year_values.items():
            year_values[y] = vals
        if not (model or dc_must):
            fonte_must = "PTDis-manual"

    year_values = _apply_manual_must_overrides(proto, year_values)

    # ─── Status do horizonte (current/contractable/outside) ───
    year_status = {}
    contract_start_year = None
    contract_limit_year = None
    if data_solic and data_solic != "—":
        try:
            contract_start_year = datetime.strptime(data_solic, "%d/%m/%Y").year
            contract_limit_year = contract_start_year + 3
        except Exception:
            pass
    if contract_start_year and year_values:
        for y in year_values:
            if y == contract_start_year:
                year_status[y] = "current"
            elif contract_start_year < y <= contract_limit_year:
                year_status[y] = "contractable"
            elif y > contract_limit_year:
                year_status[y] = "outside"
            else:
                year_status[y] = "before"

    # Pico no horizonte
    potencia_max = compute_pico_horizonte(year_values, year_status)

    # Documento emitido / Data Emissão ONS
    # Fonte prioritária: sgacesso.tb_documento por id_solicitacao + id_tpdocumento.
    # Fallback: bca.dbo.tb_solicitacaoacesso.
    documento_emitido, din_emissao_doc = _documento_emitido_from_docs(
        id_solic_meta,
        proto,
        meta,
    )
    data_emissao_doc_fmt = fmt_date(din_emissao_doc)

    # CUST
    is_spt = "SPT" in (proto or "").upper()
    if is_spt:
        cust_status = "ptdis"
        cust_label = "PTDIS"
        cod_contrato = ""
        data_assinatura_cust = "—"
        cust_protocol = ""
        prazo_cust_dt = None
    else:
        cust_info = _find_cust_info([proto])
        cod_contrato = cust_info.get("cod_contrato", "") if cust_info else ""
        data_assinatura_cust = cust_info.get("data_assinatura_cust", "—") if cust_info else "—"
        cust_protocol = cust_info.get("num_protocolo", "") if cust_info else ""
        prazo_cust_dt = None
        if din_emissao_doc is not None and not pd.isna(din_emissao_doc):
            emissao_dt = pd.to_datetime(din_emissao_doc, errors="coerce")
            if not pd.isna(emissao_dt):
                prazo_cust_dt = emissao_dt + pd.Timedelta(days=90)
        prazo_cust_dt = apply_cust_deadline_override(proto, prazo_cust_dt)

        if cod_contrato:
            cust_status = "assinado"
            cust_label = cod_contrato
        elif prazo_cust_dt is not None:
            if prazo_cust_dt.normalize() >= pd.Timestamp.now().normalize():
                cust_status = "no_prazo"
                cust_label = "No Prazo"
            else:
                cust_status = "nao_assinado"
                cust_label = "Não assinado"
        else:
            cust_status = ""
            cust_label = "—"

    # Empreendimento: prioridade Excel → banco
    empreendimento = entry.get("empreendimento") or clean_text(meta.get("nom_empreendimento"))
    conexao = entry.get("ponto") or clean_text(meta.get("dsc_ptoconexao"))
    uf = normalize_uf(entry.get("uf"), default="") or normalize_uf(meta.get("nom_uf"), default="") or "—"

    # Status real do SGA/BCA.
    status_real = clean_text(meta.get("dsc_status"))
    status_real_lower = str(status_real or "").lower()
    # Separar Cancelada de Anulada.
    # Regra: se o status tiver "anul", a viabilidade deve aparecer como "Anulada".
    # Se tiver "cancel" ou flg_cancelada, aparece como "Cancelada".
    solicitacao_anulada = "anul" in status_real_lower
    solicitacao_cancelada = (
        "cancel" in status_real_lower
        or str(meta.get("flg_cancelada") or "").strip() in ("1", "True", "true", "S", "s")
    )
    solicitacao_cancelada_ou_anulada = solicitacao_cancelada or solicitacao_anulada

    # Viabilidade
    # Emissão PL continua vindo da tb_analisetecnica.din_envioanalise.
    # Porém, para regra de pendência, consideramos também a emissão oficial
    # do documento em sgacesso.tb_documento. Assim, se já existe PA emitido
    # e o BD entrada está vazio, a viabilidade vira Pendente.
    data_emissao_pl_fmt = fmt_date(data_envio_pl)
    pl_emitida_pela_analise = bool(
        data_emissao_pl_fmt
        and str(data_emissao_pl_fmt).strip() not in ("—", "", "None", "nan", "NaT")
    )
    pl_emitida = bool(
        pl_emitida_pela_analise
        or (data_emissao_doc_fmt and str(data_emissao_doc_fmt).strip() not in ("—", "", "None", "nan", "NaT"))
    )
    viabilidade_info = {
        "viabilidade_geral": entry.get("viabilidade_geral"),
        "anos": entry.get("anos", {}),
    }
    viabilidade_resumo = get_viabilidade_resumo(
        viabilidade_info,
        pl_emitida=pl_emitida,
    )
    pendencias = compute_pendencias(
        {"data_emissao_pl": data_emissao_pl_fmt or data_emissao_doc_fmt},
        viabilidade_info,
    )

    viabilidade_anos_display = entry
    if uf != "SP":
        viabilidade_manual_geral = _manual_viabilidade_geral(entry)
        if pl_emitida_pela_analise and viabilidade_manual_geral:
            viabilidade_resumo = viabilidade_manual_geral
            pendencias = []
            viabilidade_anos_display = _set_viabilidade_display(entry, viabilidade_resumo)
        elif _is_viabilidade_sem_resultado(viabilidade_resumo):
            viabilidade_banco = viabilidade_sga_label(meta.get("id_viabilidade"), default="")
            if viabilidade_banco and viabilidade_banco != "Nenhum":
                viabilidade_resumo = viabilidade_banco
                pendencias = []
                viabilidade_anos_display = _set_viabilidade_display(entry, viabilidade_resumo)

    if solicitacao_cancelada_ou_anulada:
        viabilidade_forcada = "Anulada" if solicitacao_anulada else "Cancelada"
        viabilidade_resumo = viabilidade_forcada
        pendencias = []
        viabilidade_anos_display = _set_viabilidade_display(entry, viabilidade_forcada)
        if solicitacao_anulada:
            cust_status = "anulado"
            cust_label = "Anulada"

    # Se viabilidade é negativa e não é PTDIS (SPT), CUST mostra "Inviável".
    if not is_spt and _is_viabilidade_inviavel(viabilidade_resumo):
        cust_status = "inviavel"
        cust_label = "Inviável"

    # SPA/RPA/RVA em DIT: manter os status protegidos e, nos demais casos,
    # mostrar "No prazo" enquanto o prazo ONS não venceu e "Verificar" após o prazo.
    viab_protegidas_spa_dit = {"Inviável", "Cancelada", "Anulada", "Pendente", "Misto"}
    proto_tipo = str(proto or "").upper().split("-")
    is_spa_dit = (
        len(proto_tipo) >= 2
        and proto_tipo[0] == "SGA"
        and proto_tipo[1] in {"SPA", "RPA", "RVA"}
        and uf == "SP"
        and rede == "DIT"
        and viabilidade_resumo not in viab_protegidas_spa_dit
    )
    if is_spa_dit:
        prazo_ons_dt = pd.to_datetime(prazo_ons, errors="coerce")
        if pd.notna(prazo_ons_dt) and prazo_ons_dt.normalize() >= pd.Timestamp.now().normalize():
            viabilidade_forcada = "No prazo"
        else:
            viabilidade_forcada = "Verificar"

        viabilidade_resumo = viabilidade_forcada
        pendencias = []
        viabilidade_anos_display = _set_viabilidade_display(entry, viabilidade_forcada)

        if cust_status == "nao_assinado":
            cust_status = "verificar"
            cust_label = "Verificar"

    cust_status, cust_label = apply_cust_status_override(proto, cust_status, cust_label)

    DATACENTER_ROWS.append({
        "item": idx,
        "main_protocol": proto,
        "ponto_label": ponto_text,
        "ponto_idx": 0,  # mantido por compat
        "ponto_codigo": "",
        "ponto_instalacao": ponto_text,
        "empreendimento": empreendimento,
        "tipo": clean_text(meta.get("nom_tpsolicitacaoacesso")),
        "uf": uf,
        "rede": rede,
        "tensao": tensao,
        "conexao": conexao,
        "status": status_real,
        "documento": clean_text(documento_emitido),
        "data_solicitacao": data_solic,
        "data_emissao": data_emissao_doc_fmt,
        "data_entrada_pl": fmt_date(data_entrada_pl),
        "data_envio_pl": data_emissao_pl_fmt,
        "prazo_analise_pl": fmt_date(prazo_pl),
        "prazo_emissao_ons": fmt_date(prazo_ons),
        "data_emissao_pl": data_emissao_pl_fmt,
        "data_emissao_doc": data_emissao_doc_fmt,
        "prazo_cust": fmt_date(prazo_cust_dt),
        "cust_status": cust_status,
        "cust_label": cust_label,
        "cod_contrato": cod_contrato,
        "data_assinatura_cust": data_assinatura_cust if cust_status == "assinado" else "—",
        "cust_protocol": cust_protocol,
        "year_values": year_values,
        "year_status": year_status,
        "potencia_max": potencia_max,
        "fonte_must": fonte_must,
        "relacao_protocolo_revisado": (entry.get("relacao_protocolo_revisado") or "").strip(),
        "origem": "BD entrada",
        "viabilidade_anos": viabilidade_anos_display,
        "viabilidade_resumo": viabilidade_resumo,
        "pendencias": pendencias,
        "analista": clean_text(meta.get("nom_analistaacessoresponsavel")),
        "janela_contratavel": (
            f"{contract_start_year}–{contract_limit_year}"
            if contract_start_year and contract_limit_year else "—"
        ),
        "outside_years": [y for y, s in year_status.items() if s == "outside"],
    })


# Anos detectados no painel
DATACENTER_YEARS = sorted({
    *YEARS_DC,
    *(
        int(year)
        for row in DATACENTER_ROWS
        for year, vals in row.get("year_values", {}).items()
        if vals.get("ponta") is not None or vals.get("fora") is not None
    ),
})

_log(f"  ↳ {len(DATACENTER_ROWS)} linhas construídas", _t)
if len(DATACENTER_ROWS) != len(VIABILIDADES_ENTRIES):
    print(f"[DC] ⚠ MISMATCH! Algo está duplicando linhas.")
_log(f"✅ Carga completa. {_time.perf_counter() - _t0:.1f}s no total. Iniciando servidor Shiny…")

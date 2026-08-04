"""Transformações dos dados brutos do banco/planilha para modelos de tela."""

from collections import Counter
import re

import pandas as pd

from .constants import (
    ANO_LABELS,
    CAMPO_MUST_PONTA,
    YEARS_DC,
    DC_FIELD_INSTALACAO,
    DC_FIELD_PERIODO_INICIO,
    DC_FIELD_PERIODO_FIM,
    DC_FIELD_MUST_PONTA,
    DC_FIELD_MUST_FORA,
    DC_FIELD_FATOR_POT_PONTA,
    DC_FIELD_FATOR_POT_FORA,
    DC_FIELD_FATOR_CARGA,
)
from .utils import normalize_uf, parse_br_number, fmt_date


CUST_DEADLINE_OVERRIDES = {}

CUST_STATUS_OVERRIDES = {}


def normalize_cust_contract_code(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    code = str(value).strip()
    if code in ("", "—", "-", "None", "nan", "NaT", "NULL"):
        return ""
    return code if code.upper().startswith("CUST") else ""


def cust_info_from_solicitacao_meta(proto, meta):
    meta = meta or {}
    cod_contrato = normalize_cust_contract_code(meta.get("cod_contrato"))
    dat_assinatura = pd.to_datetime(meta.get("din_assinaturacontrato"), errors="coerce")
    if not cod_contrato or pd.isna(dat_assinatura):
        return None
    return {
        "num_protocolo": str(proto or meta.get("protocolo") or "").strip(),
        "cod_contrato": cod_contrato,
        "dat_assinatura": dat_assinatura,
        "data_assinatura_cust": fmt_date(dat_assinatura),
        "origem_cust": "bca.dbo.tb_solicitacaoacesso",
    }


def signed_cust_info_for_protocol(proto, meta, cust_info):
    if not cust_info:
        return None

    raw_bdt_code = str(cust_info.get("cod_contrato") or "").strip()
    dat_inicio_vigencia = pd.to_datetime(cust_info.get("dat_inicio_vigencia"), errors="coerce")
    dat_assinatura_bdt = pd.to_datetime(cust_info.get("dat_assinatura"), errors="coerce")
    if not raw_bdt_code or pd.isna(dat_inicio_vigencia) or pd.isna(dat_assinatura_bdt):
        return None

    meta_info = cust_info_from_solicitacao_meta(proto, meta)
    bdt_cust_code = normalize_cust_contract_code(raw_bdt_code)
    if not meta_info and not bdt_cust_code:
        return None

    out = dict(cust_info)
    out["num_protocolo"] = str(proto or cust_info.get("num_protocolo") or "").strip()
    out["cod_contrato_bdt"] = raw_bdt_code
    out["dat_inicio_vigencia"] = dat_inicio_vigencia

    if meta_info:
        out["cod_contrato"] = meta_info["cod_contrato"]
        out["dat_assinatura"] = meta_info["dat_assinatura"]
        out["data_assinatura_cust"] = meta_info["data_assinatura_cust"]
        out["origem_cust"] = meta_info["origem_cust"]
    else:
        out["cod_contrato"] = bdt_cust_code
        out["dat_assinatura"] = dat_assinatura_bdt
        out["data_assinatura_cust"] = fmt_date(dat_assinatura_bdt)
        out["origem_cust"] = "bdt.tb_contrato"
    return out


def apply_cust_deadline_override(proto, prazo_cust_dt):
    override = CUST_DEADLINE_OVERRIDES.get(str(proto or "").strip().upper())
    return override if override is not None else prazo_cust_dt


def apply_cust_status_override(proto, cust_status, cust_label):
    override = CUST_STATUS_OVERRIDES.get(str(proto or "").strip().upper())
    if override is None:
        return cust_status, cust_label
    if cust_status in {"assinado", "anulado", "inviavel", "ptdis"}:
        return cust_status, cust_label
    return override


def transform_eav_to_model(raw_df):
    """
    Transforma o DataFrame EAV bruto (query SQL) no modelo do dashboard.

    Cada id_solicitacaoformulario é um BLOCO contendo:
      - 1 ponto de conexão (946=código ONS, 947=instalação, 948=tensão)
      - 1 período (949=início, 950=fim)
      - valores MUST (953-970)

    REGRA DE NEGÓCIO (validada com o site interno):
      - Blocos COM Ano Corrente (953 ou 954) → linhas reais, definem os períodos
        (podem ter quebra: Jan-Jun / Jul-Dez, etc.)
      - Blocos SEM Ano Corrente mas com código ONS → dados de horizonte (Ano 2+)
        desse ponto de conexão. Devem ser incorporados, não descartados.
      - Blocos sem código ONS e sem Ano Corrente → metadados ou ruído, ignorar.
    """
    raw_df = raw_df.copy()
    raw_df["num_protocolo"] = raw_df["num_protocolo"].astype(str).str.strip()
    raw_df = raw_df[raw_df["num_protocolo"].notna() & (raw_df["num_protocolo"] != "") & (raw_df["num_protocolo"] != "nan")]
    raw_df = raw_df.sort_values("id_aumentomust")
    raw_df["val_str"] = raw_df["val_dado"].apply(lambda v: str(v).strip() if pd.notna(v) else "")
    # Converter din_modificacao para datetime (pode não existir em dados de teste)
    if "din_modificacao" in raw_df.columns:
        raw_df["din_modificacao"] = pd.to_datetime(raw_df["din_modificacao"], errors='coerce')

    protocols = []
    for proto, proto_grp in raw_df.groupby("num_protocolo", sort=False):
        nome = str(proto_grp["nom_internosolicitacao"].iloc[0] or "")
        dsc = ""
        if "dsc_solicitacao" in proto_grp.columns:
            val = proto_grp["dsc_solicitacao"].iloc[0]
            dsc = str(val).strip() if pd.notna(val) and str(val).strip() not in ("", "nan", "None") else ""
        uf = ""
        if "nom_uf" in proto_grp.columns:
            val = proto_grp["nom_uf"].iloc[0]
            uf = normalize_uf(val, "")

        # --- Extrair metadados do protocolo ---
        meta = {}
        for _, row in proto_grp.sort_values("id_aumentomust").iterrows():
            campo = row["id_formularioitemcampo"]
            if campo == 944 and "cust" not in meta:
                meta["cust"] = row["val_str"]
            elif campo == 945 and "data_assinatura" not in meta:
                val = row["val_dado"]
                meta["data_assinatura"] = val.strftime("%d/%m/%Y") if hasattr(val, 'strftime') else row["val_str"]
            elif campo == 948 and "tensao" not in meta:
                meta["tensao"] = row["val_str"]

        # --- Processar cada bloco (id_solicitacaoformulario) ---
        blocos_ano_corrente = []  # Blocos com Ano Corrente (definem períodos)
        blocos_horizonte = []     # Blocos sem Ano Corrente (horizonte Ano 2+)

        for sf_id, bloco in proto_grp.groupby("id_solicitacaoformulario", sort=False):
            bloco = bloco.sort_values("id_aumentomust")
            campos = dict(zip(bloco["id_formularioitemcampo"], bloco["val_str"]))

            codigo_ons = campos.get(946, "")
            instalacao = campos.get(947, "")
            periodo_inicio = campos.get(949, "")
            periodo_fim = campos.get(950, "")

            # Capturar a data de modificação mais recente do bloco
            din_mod = pd.Timestamp.min
            if "din_modificacao" in bloco.columns:
                dm = bloco["din_modificacao"].max()
                if pd.notna(dm):
                    din_mod = dm

            # Chave composta: alguns cadastros têm o mesmo código ONS para
            # instalações diferentes (ex: SPSTCA138 para CAMPINAS e SANTA BARBARA).
            # Tratamos como pontos diferentes quando a instalação difere.
            ponto_key = (codigo_ons, instalacao)

            # Extrair valores MUST deste bloco
            must = {}
            for campo_id, ano_idx in CAMPO_MUST_PONTA.items():
                label = ANO_LABELS[ano_idx]
                p_val = campos.get(campo_id, "")
                f_val = campos.get(campo_id + 1, "")  # Par: fora ponta
                if p_val or f_val:
                    must[label] = {
                        "ponta": [p_val if p_val else "0"],
                        "fora": [f_val if f_val else "0"],
                    }

            has_ano_corrente = bool(campos.get(953, "") or campos.get(954, ""))

            if has_ano_corrente:
                blocos_ano_corrente.append({
                    "ponto_key": ponto_key,
                    "codigo_ons": codigo_ons,
                    "instalacao": instalacao,
                    "periodo_inicio": periodo_inicio,
                    "periodo_fim": periodo_fim,
                    "must": must,
                    "din_mod": din_mod,
                })
            elif codigo_ons and must:
                # Bloco de horizonte — REGRA: só aceitar se período for Janeiro–Dezembro.
                # Blocos de horizonte com período quebrado (Jan-Mar, Abr-Dez, etc.)
                # são ruído de versões antigas que o usuário pediu correção.
                if periodo_inicio == "Janeiro" and periodo_fim == "Dezembro":
                    blocos_horizonte.append({
                        "ponto_key": ponto_key,
                        "codigo_ons": codigo_ons,
                        "instalacao": instalacao,
                        "periodo_inicio": periodo_inicio,
                        "periodo_fim": periodo_fim,
                        "must": must,
                        "din_mod": din_mod,
                    })

        if not blocos_ano_corrente:
            continue

        # --- REGRA: filtrar blocos AC mantendo só os mais recentes por ponto ---
        # --- PASSO 1: associar pontos com instalação igual ---
        # Quando existe um bloco com código ONS diferente mas MESMA instalação que
        # outro ponto, considerar como o mesmo ponto (erro de cadastro no código ONS).
        # Ex: SPPCB-138-A/SANTA BARBARA deve virar SPSTCA138/SANTA BARBARA se esse
        # último já existe. Fazer ANTES do filtro de din_modificacao para que o
        # bloco "corrigido" seja comparado com os outros do mesmo ponto canônico.
        from collections import Counter
        inst_to_pks = {}
        for b in blocos_ano_corrente:
            inst_to_pks.setdefault(b["instalacao"], []).append(b["ponto_key"])
        canonical_pk_por_inst = {}
        for inst, pks in inst_to_pks.items():
            if not inst:
                continue
            canonical_pk_por_inst[inst] = Counter(pks).most_common(1)[0][0]

        for b in blocos_ano_corrente:
            if b["instalacao"] in canonical_pk_por_inst:
                b["ponto_key"] = canonical_pk_por_inst[b["instalacao"]]
                b["codigo_ons"] = b["ponto_key"][0]
        for b in blocos_horizonte:
            if b["instalacao"] in canonical_pk_por_inst:
                b["ponto_key"] = canonical_pk_por_inst[b["instalacao"]]
                b["codigo_ons"] = b["ponto_key"][0]

        # --- PASSO 2: filtrar blocos AC mantendo só os mais recentes por ponto ---
        # Quando o usuário corrige os dados (ex: altera de período quebrado para Jan-Dez),
        # os blocos antigos continuam no banco mas com din_modificacao mais antiga.
        # Para cada ponto, pegamos a data máxima de modificação e mantemos só os
        # blocos dentro de uma tolerância (60s) dessa data.
        max_din_por_ponto = {}
        for b in blocos_ano_corrente:
            pk = b["ponto_key"]
            if b["din_mod"] > max_din_por_ponto.get(pk, pd.Timestamp.min):
                max_din_por_ponto[pk] = b["din_mod"]

        def _dentro_tolerancia(b):
            pk = b["ponto_key"]
            max_din = max_din_por_ponto.get(pk, pd.Timestamp.min)
            if max_din == pd.Timestamp.min:
                return True  # Sem data — aceitar (compatibilidade)
            if b["din_mod"] == pd.Timestamp.min:
                return True
            return (max_din - b["din_mod"]).total_seconds() <= 60

        blocos_ano_corrente = [b for b in blocos_ano_corrente if _dentro_tolerancia(b)]

        # --- Identificar pontos de conexão únicos (dos blocos válidos) ---
        pontos_unicos = []
        pontos_vistos = set()
        for b in blocos_ano_corrente:
            key = b["ponto_key"]
            if key[0] and key not in pontos_vistos:
                pontos_vistos.add(key)
                pontos_unicos.append({"cod": b["codigo_ons"], "instalacao": b["instalacao"]})
        if not pontos_unicos:
            pontos_unicos = [{"cod": "", "instalacao": ""}]

        # --- Construir períodos por ponto de conexão ---
        # Estrutura: periodos é uma lista de dicts onde must[ano][ponta/fora] é
        # um DICT {codigo_ons: valor} — indexado por ponto, não por posição.
        # Isso evita confusão quando diferentes períodos têm pontos diferentes.

        # Agrupar blocos_ano_corrente por (periodo_inicio, periodo_fim)
        # Usamos ponto_key (tupla codigo_ons + instalacao) como chave dentro
        # do must para diferenciar pontos com mesmo código ONS mas instalações
        # diferentes (caso de SPSTCA138 = CAMPINAS e SANTA BARBARA).
        periodos_dict = {}

        def _add_val_to_periodo(per_key, inicio, fim, ponto_key, ano_label, p_val, f_val):
            if per_key not in periodos_dict:
                periodos_dict[per_key] = {"inicio": inicio, "fim": fim, "must": {}}
            if ano_label not in periodos_dict[per_key]["must"]:
                periodos_dict[per_key]["must"][ano_label] = {"ponta": {}, "fora": {}}
            periodos_dict[per_key]["must"][ano_label]["ponta"][ponto_key] = p_val
            periodos_dict[per_key]["must"][ano_label]["fora"][ponto_key] = f_val

        for b in blocos_ano_corrente:
            per_key = (b["periodo_inicio"], b["periodo_fim"])
            if per_key == ("", ""):
                continue
            for ano_label, vals in b["must"].items():
                p_val = vals["ponta"][0] if vals["ponta"] else ""
                f_val = vals["fora"][0] if vals["fora"] else ""
                _add_val_to_periodo(per_key, b["periodo_inicio"], b["periodo_fim"],
                                    b["ponto_key"], ano_label, p_val, f_val)

        # Incorporar blocos de horizonte.
        # Regra: se o ponto tem quebra no Ano Corrente (mais de um período AC),
        # incorporar TODOS os anos do bloco de horizonte Jan-Dez (inclusive Ano 2,
        # que pode estar repetido nos blocos AC quebrados). Caso contrário, só
        # incorporar anos que não estão nos blocos AC.
        anos_por_ponto_ac = {}
        periodos_ac_por_ponto = {}
        for b in blocos_ano_corrente:
            pk = b["ponto_key"]
            if pk not in anos_por_ponto_ac:
                anos_por_ponto_ac[pk] = set()
                periodos_ac_por_ponto[pk] = set()
            anos_por_ponto_ac[pk].update(b["must"].keys())
            periodos_ac_por_ponto[pk].add((b["periodo_inicio"], b["periodo_fim"]))

        for b in blocos_horizonte:
            pk = b["ponto_key"]
            tem_quebra_ac = len(periodos_ac_por_ponto.get(pk, set())) > 1
            if tem_quebra_ac:
                # Ponto com quebra — incorporar todos os anos do horizonte
                anos_novos = dict(b["must"])
            else:
                # Ponto sem quebra — só incorporar anos que não estão no AC
                anos_existentes = anos_por_ponto_ac.get(pk, set())
                anos_novos = {k: v for k, v in b["must"].items() if k not in anos_existentes}
            if not anos_novos:
                continue
            per_key = (b["periodo_inicio"], b["periodo_fim"])
            for ano_label, vals in anos_novos.items():
                p_val = vals["ponta"][0] if vals["ponta"] else ""
                f_val = vals["fora"][0] if vals["fora"] else ""
                _add_val_to_periodo(per_key, b["periodo_inicio"], b["periodo_fim"],
                                    pk, ano_label, p_val, f_val)

        periodos = list(periodos_dict.values())
        if not periodos:
            continue

        # UF vem exclusivamente de nom_uf (banco), sem fallback pelo código ONS/ponto.
        # Não inferir UF pelas duas primeiras letras do ponto de contratação.

        meta_sql = {}
        for col in [
            "id_solicitacao", "id_viabilidade", "nom_solicitacao", "din_solicitacao", "nom_solicitacaoacesso",
            "nom_tpsolicitacaoacesso", "nom_tipoempreendimento", "nom_analistaacessoresponsavel",
            "nom_empreendimento", "dsc_ptoconexao", "dsc_objetivosolicitacao",
            "dsc_ambientecontratacao", "cod_contrato", "num_documento_emitido", "dsc_status",
            "din_solicitacaoacesso", "din_aceitesolicitacao", "val_prazoemissao", "val_periodointerrompida", "din_emissaodocumento",
            "din_cancelamento", "din_conexao", "din_assinaturacontrato",
            "din_inicioentradaoperacao", "flg_cancelada", "flg_documentoemitido",
        ]:
            if col in proto_grp.columns:
                meta_sql[col] = proto_grp[col].iloc[0]

        protocols.append({
            "protocolo": proto.strip(),
            "nome": nome.strip(),
            "dsc_solicitacao": dsc,
            # UF original do banco (bca.dbo.tb_solicitacaoacesso.nom_uf), normalizada.
            # Sem fallback pelo código ONS / ponto de contratação.
            "nom_uf": uf,
            "uf": uf,
            "cust": meta.get("cust", ""),
            "data_assinatura": meta.get("data_assinatura", ""),
            "tensao": meta.get("tensao", ""),
            "pontos": pontos_unicos,
            "periodos": periodos,
            **meta_sql,
        })

    return protocols


def transform_solicitacoes_meta(df):
    """Indexa metadados por protocolo para cobrir protocolos sem linhas de aumento de MUST."""
    if df is None or df.empty or "num_protocolo" not in df.columns:
        return {}
    df = df.copy()
    df["num_protocolo"] = df["num_protocolo"].astype(str).str.strip()
    out = {}
    for proto, grp in df.groupby("num_protocolo", sort=False):
        if not proto or proto == "nan":
            continue
        rec = {"protocolo": proto}
        for col in grp.columns:
            if col == "num_protocolo":
                continue
            val = grp[col].iloc[0]
            rec[col] = val
        out[proto] = rec
    return out



def extract_year_from_period(val):
    """Extrai o ano de strings como 12/2025, 01/2030 ou datas completas."""
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s in ("nan", "None", "NULL", "—", "-"):
        return None
    mt = re.search(r"(20\d{2})", s)
    if mt:
        return int(mt.group(1))
    dt = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if pd.notna(dt):
        return int(dt.year)
    return None


def expand_years_from_period(inicio, fim):
    """Retorna todos os anos cobertos por um período inicial/final.

    Nos SPA/RPA da tabela tb_mustpordisteuniconsumidora, os campos 1111 e 1112
    representam um intervalo. Ex.: 1111=12/2027 e 1112=12/2031 significa que
    o valor de MUST vale para 2027, 2028, 2029, 2030 e 2031.

    Se só um dos anos existir, retorna esse ano. Se o intervalo vier invertido
    ou inválido, usa o ano disponível como fallback.
    """
    ano_inicio = extract_year_from_period(inicio)
    ano_fim = extract_year_from_period(fim)

    if ano_inicio is None and ano_fim is None:
        return []
    if ano_inicio is None:
        return [ano_fim]
    if ano_fim is None:
        return [ano_inicio]
    if ano_fim < ano_inicio:
        return [ano_fim]

    # Proteção contra intervalos absurdos por erro de preenchimento.
    if (ano_fim - ano_inicio) > 100:
        return [ano_inicio, ano_fim]

    return list(range(ano_inicio, ano_fim + 1))


def transform_datacenter_must_model(df):
    """
    Transforma os dados de tb_mustpordisteuniconsumidora em valores anuais por protocolo.

    Dicionário usado:
      1109 = Instalação / ordem
      1111 = Período inicial
      1112 = Período final
      1114 = MUST Ponta (MW)
      1115 = MUST Fora Ponta (MW)
      1117/1118 = Fator de potência
      1119 = Fator de carga
    """
    if df is None or df.empty or "num_protocolo" not in df.columns:
        return {}

    df = df.copy()
    df["num_protocolo"] = df["num_protocolo"].astype(str).str.strip()
    df = df[df["num_protocolo"].notna() & (df["num_protocolo"] != "") & (df["num_protocolo"] != "nan")]
    df["val_str"] = df["val_dado"].apply(lambda v: str(v).strip() if pd.notna(v) else "")
    df["id_formularioitemcampo"] = pd.to_numeric(df["id_formularioitemcampo"], errors="coerce").astype("Int64")

    for col in ("din_submissao", "din_modificacao", "din_alteracao", "din_inclusao"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    sort_cols = [c for c in ["din_submissao", "din_modificacao", "din_alteracao", "din_inclusao", "id_mustpordisteuniconsumidora"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols)

    # Quando há retificação do mesmo campo no mesmo id_solicitacaoformulario,
    # fica valendo o registro mais recente e, em empate, o maior id da tabela.
    df = df.drop_duplicates(
        subset=["num_protocolo", "id_solicitacaoformulario", "id_formularioitemcampo"],
        keep="last",
    )

    out = {}
    for proto, proto_grp in df.groupby("num_protocolo", sort=False):
        year_values = {}
        detalhes = []
        for sf_id, bloco in proto_grp.groupby("id_solicitacaoformulario", sort=False):
            campos = dict(zip(bloco["id_formularioitemcampo"].astype(int), bloco["val_str"]))
            inicio = campos.get(DC_FIELD_PERIODO_INICIO, "")
            fim = campos.get(DC_FIELD_PERIODO_FIM, "")
            ponta = parse_br_number(campos.get(DC_FIELD_MUST_PONTA))
            fora = parse_br_number(campos.get(DC_FIELD_MUST_FORA))
            anos = expand_years_from_period(inicio, fim)

            # Não limitar a YEARS_DC: alguns DataCenters informam anos muito além
            # da janela principal do painel e esses anos são relevantes para análise.
            # Importante: em SPA/RPA, 1111/1112 formam um INTERVALO.
            # Ex.: 12/2027 até 12/2031 deve preencher 2027, 2028, 2029, 2030 e 2031.
            for ano in anos:
                year_values.setdefault(ano, {"ponta": None, "fora": None})
                if ponta is not None:
                    curr = year_values[ano]["ponta"]
                    year_values[ano]["ponta"] = ponta if curr is None else max(curr, ponta)
                if fora is not None:
                    curr = year_values[ano]["fora"]
                    year_values[ano]["fora"] = fora if curr is None else max(curr, fora)

            if anos or ponta is not None or fora is not None:
                detalhes.append({
                    "id_solicitacaoformulario": sf_id,
                    "instalacao_ordem": campos.get(DC_FIELD_INSTALACAO, ""),
                    "periodo_inicio": inicio,
                    "periodo_fim": fim,
                    "ano_inicio": anos[0] if anos else None,
                    "ano_fim": anos[-1] if anos else None,
                    "anos": anos,
                    # Mantido por compatibilidade com trechos antigos que esperem a chave 'ano'.
                    # Quando houver intervalo, representa o ano final.
                    "ano": anos[-1] if anos else None,
                    "ponta": ponta,
                    "fora": fora,
                    "fator_pot_ponta": parse_br_number(campos.get(DC_FIELD_FATOR_POT_PONTA)),
                    "fator_pot_fora": parse_br_number(campos.get(DC_FIELD_FATOR_POT_FORA)),
                    "fator_carga": parse_br_number(campos.get(DC_FIELD_FATOR_CARGA)),
                })

        max_mw = None
        for vals in year_values.values():
            for tipo in ("ponta", "fora"):
                val = vals[tipo]
                if val is not None:
                    max_mw = val if max_mw is None else max(max_mw, val)

        out[proto] = {
            "protocolo": proto,
            "year_values": year_values,
            "potencia_max": max_mw,
            "detalhes": detalhes,
            "fonte": "tb_mustpordisteuniconsumidora",
        }
    return out


def pick_first_date(*vals):
    for val in vals:
        dt = pd.to_datetime(val, errors="coerce")
        if pd.notna(dt):
            return dt
    return None


def infer_base_year(model, meta):
    """Ano Corrente = ano da Data Solicitação."""
    for source in (meta or {}, model or {}):
        dt = pick_first_date(
            source.get("din_solicitacao"),
            source.get("din_solicitacaoacesso"),
        )
        if dt is not None:
            return int(dt.year)
    # fallback conservador para quando não houver data de solicitação disponível
    return YEARS_DC[0]


def model_year_values(model, meta=None):
    """Converte Ano Corrente/Ano 2... em anos reais usando Data Solicitação como Ano Corrente."""
    values = {year: {"ponta": None, "fora": None} for year in YEARS_DC}
    if not model:
        return values
    base_year = infer_base_year(model, meta)
    label_to_offset = {"Ano Corrente": 0, "Ano 2": 1, "Ano 3": 2, "Ano 4": 3, "Ano 5": 4, "Ano 6": 5}
    for per in model.get("periodos", []):
        for ano_label, offset in label_to_offset.items():
            target_year = base_year + offset
            if target_year not in values:
                continue
            must = per.get("must", {}).get(ano_label, {})
            for tipo in ("ponta", "fora"):
                vals = must.get(tipo, {})
                if isinstance(vals, dict):
                    iterable = vals.values()
                else:
                    iterable = vals or []
                nums = [parse_br_number(v) for v in iterable]
                nums = [n for n in nums if n is not None]
                if nums:
                    curr = values[target_year][tipo]
                    values[target_year][tipo] = max(nums) if curr is None else max(curr, max(nums))
    return values


def first_year_with_must(year_values):
    """Retorna o primeiro ano com algum valor de MUST informado."""
    years = []
    for year, vals in (year_values or {}).items():
        try:
            year_int = int(year)
        except (TypeError, ValueError):
            continue
        if vals.get("ponta") is not None or vals.get("fora") is not None:
            years.append(year_int)
    return min(years) if years else None


def classify_contract_horizon(year_values, start_year=None):
    """
    Classifica os anos para visualização do DataCenters.

    Regra correta:
      - Ano corrente = ano da Data Solicitação;
      - janela contratável = ano corrente até ano corrente + 3;
      - anos informados após essa janela ficam marcados como fora do horizonte.

    O fallback para primeiro ano com MUST só é usado quando a Data Solicitação
    não estiver disponível nos metadados.
    """
    start_year = start_year or first_year_with_must(year_values)
    if start_year is None:
        return None, None, {}, []

    limit_year = start_year + 3
    status_by_year = {}
    outside_years = []

    for year, vals in (year_values or {}).items():
        try:
            year_int = int(year)
        except (TypeError, ValueError):
            continue

        has_value = vals.get("ponta") is not None or vals.get("fora") is not None

        if year_int == start_year:
            status_by_year[year_int] = "current"
        elif start_year < year_int <= limit_year:
            status_by_year[year_int] = "contractable"
        elif year_int > limit_year:
            status_by_year[year_int] = "outside" if has_value else "future-empty"
            if has_value:
                outside_years.append(year_int)
        else:
            status_by_year[year_int] = "before"

    return start_year, limit_year, status_by_year, sorted(outside_years)

def next_business_day(d):
    """Se a data cair em sábado/domingo, retorna a próxima segunda-feira."""
    if d is None:
        return None
    # weekday(): seg=0, sex=4, sab=5, dom=6
    while d.weekday() >= 5:
        d = d + pd.Timedelta(days=1)
    return d


def compute_prazo_emissao_ons(din_aceite, val_prazoemissao, val_periodointerrompida):
    """
    Calcula o Prazo de Emissão PA - ONS:
      din_aceitesolicitacao + val_prazoemissao + val_periodointerrompida
      (ajustado para próximo dia útil se cair em sábado/domingo)
    """
    if din_aceite is None or pd.isna(din_aceite):
        return None
    try:
        prazo = int(val_prazoemissao) if val_prazoemissao and not pd.isna(val_prazoemissao) else 0
    except (ValueError, TypeError):
        return None
    try:
        interrompido = int(val_periodointerrompida) if val_periodointerrompida and not pd.isna(val_periodointerrompida) else 0
    except (ValueError, TypeError):
        interrompido = 0

    aceite = pd.to_datetime(din_aceite, errors="coerce")
    if pd.isna(aceite):
        return None
    data_limite = aceite + pd.Timedelta(days=prazo + interrompido)
    return next_business_day(data_limite)


def compute_prazo_pl(din_solicitacao_pl, val_prazo):
    """
    Calcula o Prazo Análise Técnica PL:
      din_solicitacao (na PL) + val_prazo (em dias)
      (ajustado para próximo dia útil se cair em sábado/domingo)
    """
    if din_solicitacao_pl is None or pd.isna(din_solicitacao_pl):
        return None
    try:
        prazo = int(val_prazo) if val_prazo and not pd.isna(val_prazo) else 60
    except (ValueError, TypeError):
        prazo = 60
    sol = pd.to_datetime(din_solicitacao_pl, errors="coerce")
    if pd.isna(sol):
        return None
    return next_business_day(sol + pd.Timedelta(days=prazo))


def classify_prazo_status(prazo_date, kind="ons"):
    """
    Classifica a urgência de um prazo para destaque visual.

    Regras:
      ONS:
        - Vermelho: <= 2 dias até o prazo (ou já expirou)
        - Amarelo claro: <= 7 dias até o prazo
        - Sem destaque: mais de 7 dias
      PL:
        - Amarelo claro: já expirou (passou da data)
        - Sem destaque: ainda dentro do prazo

    Retorna: 'red', 'yellow' ou '' (sem destaque)
    """
    if prazo_date is None:
        return ""
    prazo_dt = pd.to_datetime(prazo_date, errors="coerce")
    if pd.isna(prazo_dt):
        return ""
    hoje = pd.Timestamp.now().normalize()
    prazo_dt = prazo_dt.normalize() if hasattr(prazo_dt, 'normalize') else prazo_dt
    delta = (prazo_dt - hoje).days

    if kind == "ons":
        if delta <= 2:
            return "red"
        if delta <= 7:
            return "yellow"
        return ""
    elif kind == "pl":
        if delta < 0:  # já expirou
            return "yellow"
        return ""
    return ""


def parse_tensao_kv(tensao_str):
    """Extrai a maior tensão numérica de textos como '230', '230 kV' ou '440/138 kV'."""
    if tensao_str is None:
        return None
    s = str(tensao_str).strip()
    if not s or s in ("—", "-", "nan", "None", "NULL"):
        return None

    nums = re.findall(r"\d+(?:[,.]\d+)?", s)
    valores = []
    for n in nums:
        try:
            valores.append(float(n.replace(",", ".")))
        except ValueError:
            pass
    return max(valores) if valores else None


def compute_rede(main_protocol, tensao_str):
    """
    Determina a rede baseado no tipo de protocolo:
      - SGA-SPT... ou SGA-SAM... → DIST
      - SGA-SPA..., SGA-RPA... ou SGA-RVA... → RB se tensão > 138 kV, DIT se <= 138 kV
    """
    if not main_protocol:
        return "—"

    proto = str(main_protocol).upper().strip()
    parts = proto.split("-")
    if len(parts) < 2:
        return "—"
    tipo = parts[1] if parts[0] == "SGA" else parts[0]

    if tipo in ("SAM", "SPT"):
        return "DIST"

    if tipo in ("SPA", "RPA", "RVA"):
        tensao_num = parse_tensao_kv(tensao_str)
        if tensao_num is None:
            return "—"
        return "RB" if tensao_num > 138 else "DIT"

    return "—"


def compute_pico_horizonte(year_values, year_status):
    """
    Retorna o pico (maior MW) considerando apenas anos dentro do horizonte
    contratável (status 'current' ou 'contractable').
    Anos 'outside' ou 'before' são ignorados.
    """
    if not year_values:
        return None
    pico = None
    for year, vals in year_values.items():
        st = (year_status or {}).get(year, "")
        if st not in ("current", "contractable"):
            continue
        for tipo in ("ponta", "fora"):
            v = vals.get(tipo)
            if v is not None:
                pico = v if pico is None else max(pico, v)
    return pico


def fmt_mw(val):
    if val is None:
        return "—"
    if abs(val - round(val)) < 1e-9:
        return f"{int(round(val))}"
    return f"{val:.1f}".replace(".", ",")


def clean_text(val, default="—"):
    if val is None or pd.isna(val):
        return default
    s = str(val).strip()
    return s if s and s not in ("nan", "None", "NULL") else default


def build_datacenter_rows(entries, protocols_by_proto, solicitacoes_meta, dc_must_by_proto=None, analise_tecnica_by_solic=None, cust_by_proto=None):
    dc_must_by_proto = dc_must_by_proto or {}
    analise_tecnica_by_solic = analise_tecnica_by_solic or {}
    cust_by_proto = cust_by_proto or {}
    rows = []
    for idx, entry in enumerate(entries, start=1):
        protos = entry["protocols"]
        dc_proto = next((pr for pr in protos if pr in dc_must_by_proto), None)
        model_proto = next((pr for pr in protos if pr in protocols_by_proto), None)
        meta_proto = next((pr for pr in protos if pr in solicitacoes_meta), None)
        model = protocols_by_proto.get(model_proto) if model_proto else None
        dc_must = dc_must_by_proto.get(dc_proto) if dc_proto else None
        meta = solicitacoes_meta.get(meta_proto) if meta_proto else {}

        if dc_must and meta:
            origem = "MUST SPA/RPA + metadados"
        elif dc_must:
            origem = "MUST SPA/RPA"
        elif model and meta:
            origem = "MUST SAM + metadados"
        elif model:
            origem = "MUST SAM"
        elif meta:
            origem = "Metadados"
        else:
            origem = "Não encontrado"

        if dc_must:
            year_values = dict(dc_must["year_values"])
        else:
            year_values = model_year_values(model, meta)

        # Regra correta do horizonte:
        # Ano corrente = ano da Data Solicitação.
        # O primeiro ano com MUST informado é apenas fallback quando não houver data.
        start_year = infer_base_year(model, meta)
        if start_year is None:
            start_year = first_year_with_must(year_values)

        contract_start_year, contract_limit_year, year_status, outside_years = classify_contract_horizon(
            year_values,
            start_year=start_year,
        )

        pontos = model.get("pontos", []) if model else []
        conexao_model = "; ".join([pt.get("instalacao", "") for pt in pontos if pt.get("instalacao")])
        tensao = clean_text(model.get("tensao") if model else "", "")
        if not tensao:
            # tentativa simples a partir do texto do ponto de conexão
            cx = clean_text(meta.get("dsc_ptoconexao"), "")
            mt = re.search(r"(\d{2,3})\s*kV", cx, flags=re.IGNORECASE)
            tensao = mt.group(1) if mt else "—"

        # Pico considerando APENAS anos dentro do horizonte contratável
        potencia_max = compute_pico_horizonte(year_values, year_status)

        # Rede baseada no tipo de protocolo + tensão
        rede = compute_rede(entry["main_protocol"], tensao)

        # ─── Cálculo das datas de prazo ───
        # Procurar dados de análise técnica (PL) por id_solicitacao do meta
        id_solic_meta = meta.get("id_solicitacao")
        analise_pl = analise_tecnica_by_solic.get(id_solic_meta) if id_solic_meta else None

        # Data de Entrada PL = din_solicitacao da tb_analisetecnica (id_tp=13)
        data_entrada_pl = analise_pl.get("din_solicitacao") if analise_pl else None
        # Prazo Análise Técnica PL = din_solicitacao + val_prazo
        prazo_pl = compute_prazo_pl(
            data_entrada_pl,
            analise_pl.get("val_prazo") if analise_pl else None,
        )
        # Data envio análise (se já foi emitida pela PL)
        data_envio_pl = analise_pl.get("din_envioanalise") if analise_pl else None

        # Prazo Emissão PA - ONS
        prazo_ons = compute_prazo_emissao_ons(
            meta.get("din_aceitesolicitacao"),
            meta.get("val_prazoemissao"),
            meta.get("val_periodointerrompida"),
        )

        # Status de urgência (para colorir)
        prazo_pl_status = classify_prazo_status(prazo_pl, kind="pl")
        prazo_ons_status = classify_prazo_status(prazo_ons, kind="ons")

        # ─── CUST ───
        # 1) Data emissão PL = din_envioanalise da tb_analisetecnica (tipo 13)
        data_emissao_pl = analise_pl.get("din_envioanalise") if analise_pl else None

        # 2) Data da emissão = din_emissaodocumento (já vem em data_emissao)
        din_emissao_doc = meta.get("din_emissaodocumento")
        status_real = clean_text(meta.get("dsc_status"))
        solicitacao_anulada = "anul" in str(status_real or "").lower()

        # 3) Prazo CUST = din_emissaodocumento + 90 dias
        prazo_cust_dt = None
        if din_emissao_doc is not None and not pd.isna(din_emissao_doc):
            emissao_dt = pd.to_datetime(din_emissao_doc, errors="coerce")
            if not pd.isna(emissao_dt):
                prazo_cust_dt = emissao_dt + pd.Timedelta(days=90)

        # 4) Verificar se assinou CUST no proprio protocolo da linha.
        # Protocolos relacionados/revisados nao devem herdar o CUST entre si.
        cust_info = None
        main_proto = entry.get("main_protocol") or (protos[0] if protos else "")
        prazo_cust_dt = apply_cust_deadline_override(main_proto, prazo_cust_dt)
        for candidate in (main_proto, str(main_proto or "").upper()):
            if candidate in cust_by_proto:
                cust_info = cust_by_proto[candidate]
                break
        cust_info = signed_cust_info_for_protocol(main_proto, meta, cust_info)

        cod_contrato = ""
        data_assinatura_cust = "—"
        if cust_info:
            cod_contrato = normalize_cust_contract_code(cust_info.get("cod_contrato"))
            dat_assinatura = pd.to_datetime(cust_info.get("dat_assinatura"), errors="coerce")
            if cod_contrato and pd.notna(dat_assinatura):
                data_assinatura_cust = fmt_date(dat_assinatura)

        # Status do CUST: assinado / no prazo / não assinado
        if solicitacao_anulada:
            cust_status = "anulado"
            cust_label = "Anulada"
        elif cod_contrato:
            cust_status = "assinado"
            cust_label = cod_contrato
        else:
            # Sem registro em tb_associacontratopareceracesso → não assinou
            if prazo_cust_dt is not None:
                hoje = pd.Timestamp.now().normalize()
                if prazo_cust_dt.normalize() >= hoje:
                    cust_status = "no_prazo"
                    cust_label = "No Prazo"
                else:
                    cust_status = "nao_assinado"
                    cust_label = "Não assinado"
            else:
                # Sem data de emissão de documento ainda
                cust_status = ""
                cust_label = "—"
        cust_status, cust_label = apply_cust_status_override(main_proto, cust_status, cust_label)

        rows.append({
            "item": idx,
            "label": entry["label"],
            "main_protocol": entry["main_protocol"],
            "related": ", ".join(entry["related_protocols"]) if entry["related_protocols"] else "—",
            "fonte_must": dc_proto or model_proto or "—",
            "origem": origem,
            "empreendimento": clean_text(meta.get("nom_empreendimento"), clean_text(model.get("nome") if model else "")),
            "tipo": clean_text(meta.get("nom_tpsolicitacaoacesso")),
            "uf": normalize_uf(meta.get("nom_uf")),
            "rede": rede,
            "status": status_real,
            "analista": clean_text(meta.get("nom_analistaacessoresponsavel")),
            "conexao": clean_text(meta.get("dsc_ptoconexao"), conexao_model or "—"),
            "tensao": tensao,
            "documento": clean_text(meta.get("num_documento_emitido")),
            "data_solicitacao": fmt_date(pick_first_date(meta.get("din_solicitacao"), meta.get("din_solicitacaoacesso"))),
            "data_emissao": fmt_date(meta.get("din_emissaodocumento")),
            # Datas de prazo (4 cards)
            "data_entrada_pl": fmt_date(data_entrada_pl),
            "data_envio_pl": fmt_date(data_envio_pl),
            "prazo_analise_pl": fmt_date(prazo_pl),
            "prazo_emissao_ons": fmt_date(prazo_ons),
            "prazo_pl_raw": prazo_pl,
            "prazo_ons_raw": prazo_ons,
            "prazo_pl_status": prazo_pl_status,
            "prazo_ons_status": prazo_ons_status,
            # CUST
            "data_emissao_pl": fmt_date(data_emissao_pl),
            "data_emissao_doc": fmt_date(din_emissao_doc),
            "prazo_cust": fmt_date(prazo_cust_dt),
            "cust_status": cust_status,
            "cust_label": cust_label,
            "cod_contrato": cod_contrato,
            "data_assinatura_cust": data_assinatura_cust if cust_status == "assinado" else "—",
            "potencia_max": potencia_max,
            "year_values": year_values,
            "contract_start_year": contract_start_year,
            "contract_limit_year": contract_limit_year,
            "year_status": year_status,
            "outside_years": outside_years,
            "janela_contratavel": (
                f"{contract_start_year}–{contract_limit_year}"
                if contract_start_year is not None and contract_limit_year is not None
                else "—"
            ),
            "fora_horizonte": ", ".join(str(y) for y in outside_years) if outside_years else "—",
            "observacao": (
                "Valores lidos de tb_mustpordisteuniconsumidora: 1111/1112 período, 1114/1115 MUST. Horizonte visual pela Data Solicitação."
                if dc_must else
                "Valores SAM convertidos usando Data Solicitação como Ano Corrente."
            ),
        })
    return rows

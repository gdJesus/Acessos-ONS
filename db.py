"""
Conexão SQL Server — Dashboard MUST
Configure o servidor, usuário e coloque a senha em password.txt
"""

import pyodbc
import pandas as pd
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO — edite aqui
# ═══════════════════════════════════════════════════════════════════════════════
SQL_SERVER = "prd-inst-bi2\\bi"
SQL_DATABASE = "INBOUND"
SQL_DRIVER = "{ODBC Driver 17 for SQL Server}"
SQL_USER = "tableau_sql"
SQL_PASSWORD = Path("password.txt").read_text(encoding="utf-8").strip()


def get_connection():
    conn_str = (
        f"DRIVER={SQL_DRIVER};"
        f"SERVER={SQL_SERVER};"
        f"DATABASE={SQL_DATABASE};"
        f"UID={SQL_USER};"
        f"PWD={SQL_PASSWORD};"
    )
    return pyodbc.connect(conn_str)


def _quoted_protocols(protocols):
    """Monta lista SQL segura para protocolos já conhecidos pelo usuário."""
    if not protocols:
        return ""
    vals = []
    for p in protocols:
        p = str(p or "").strip()
        if not p:
            continue
        vals.append("'" + p.replace("'", "''") + "'")
    return ", ".join(vals)


# ═══════════════════════════════════════════════════════════════════════════════
# QUERIES SQL BASE
# ═══════════════════════════════════════════════════════════════════════════════
SQL_QUERY = """
SELECT
    am.id_aumentomust,
    am.id_solicitacaoformulario,
    am.id_formularioitemcampo,
    am.val_dado,
    am.din_exclusao,
    am.din_modificacao,
    s.id_solicitacao,
    s.num_protocolo,
    s.nom_internosolicitacao,
    s.nom_solicitacao,
    s.dsc_solicitacao,
    s.din_solicitacao,
    s.id_viabilidade,
    sa.nom_uf,
    sa.nom_solicitacaoacesso,
    sa.nom_tpsolicitacaoacesso,
    sa.nom_tipoempreendimento,
    sa.nom_analistaacessoresponsavel,
    sa.nom_empreendimento,
    sa.dsc_ptoconexao,
    sa.dsc_objetivosolicitacao,
    sa.dsc_ambientecontratacao,
    sa.cod_contrato,
    sa.num_documento_emitido,
    sa.dsc_status,
    sa.din_solicitacaoacesso,
    sa.din_aceitesolicitacao,
    sa.val_prazoemissao,
    sa.val_periodointerrompida,
    sa.din_emissaodocumento,
    sa.din_cancelamento,
    sa.din_conexao,
    sa.din_assinaturacontrato,
    sa.din_inicioentradaoperacao,
    sa.flg_cancelada,
    sa.flg_documentoemitido
FROM sgacesso.tb_aumentomust am
INNER JOIN sgacesso.tb_solicitacaoformulario sf
    ON am.id_solicitacaoformulario = sf.id_solicitacaoformulario
INNER JOIN sgacesso.tb_solicitacao s
    ON sf.id_solicitacao = s.id_solicitacao
LEFT JOIN bca.dbo.tb_solicitacaoacesso sa
    ON s.id_solicitacao = sa.id_solicitacao
WHERE am.val_dado IS NOT NULL
  AND LTRIM(RTRIM(CAST(am.val_dado AS NVARCHAR(MAX)))) <> ''
  AND am.din_exclusao IS NULL
  AND s.din_solicitacao >= '2021-01-01'
ORDER BY am.id_aumentomust
"""

SQL_SOLICITACOES_QUERY = """
SELECT
    s.id_solicitacao,
    LTRIM(RTRIM(s.num_protocolo)) AS num_protocolo,
    s.nom_internosolicitacao,
    s.nom_solicitacao,
    s.dsc_solicitacao,
    s.din_solicitacao,
    s.id_viabilidade,
    sa.nom_uf,
    sa.nom_solicitacaoacesso,
    sa.nom_tpsolicitacaoacesso,
    sa.nom_tipoempreendimento,
    sa.nom_analistaacessoresponsavel,
    sa.nom_empreendimento,
    sa.dsc_ptoconexao,
    sa.dsc_objetivosolicitacao,
    sa.dsc_ambientecontratacao,
    sa.cod_contrato,
    sa.num_documento_emitido,
    sa.dsc_status,
    sa.din_solicitacaoacesso,
    sa.din_aceitesolicitacao,
    sa.val_prazoemissao,
    sa.val_periodointerrompida,
    sa.din_emissaodocumento,
    sa.din_cancelamento,
    sa.din_conexao,
    sa.din_assinaturacontrato,
    sa.din_inicioentradaoperacao,
    sa.flg_cancelada,
    sa.flg_documentoemitido
FROM sgacesso.tb_solicitacao s
LEFT JOIN bca.dbo.tb_solicitacaoacesso sa
    ON s.id_solicitacao = sa.id_solicitacao
WHERE s.num_protocolo IS NOT NULL
  AND LTRIM(RTRIM(s.num_protocolo)) <> ''
  AND s.din_solicitacao >= '2021-01-01'
"""

SQL_DATACENTER_MUST_QUERY = """
SELECT
    LTRIM(RTRIM(s.num_protocolo)) AS num_protocolo,
    s.id_solicitacao,
    s.din_solicitacao,
    s.id_viabilidade,
    m.id_mustpordisteuniconsumidora,
    m.id_solicitacaoformulario,
    m.id_formularioitemcampo,
    fic.nom_campo,
    fic.nom_grupo,
    m.val_dado,
    m.din_modificacao,
    m.din_inclusao,
    m.din_alteracao,
    m.din_submissao,
    m.din_exclusao
FROM sgacesso.tb_solicitacao s
INNER JOIN sgacesso.tb_solicitacaoformulario sf
    ON s.id_solicitacao = sf.id_solicitacao
INNER JOIN sgacesso.tb_mustpordisteuniconsumidora m
    ON sf.id_solicitacaoformulario = m.id_solicitacaoformulario
LEFT JOIN sgacesso.tb_formularioitemcampo fic
    ON m.id_formularioitemcampo = fic.id_formularioitemcampo
WHERE s.num_protocolo IS NOT NULL
  AND LTRIM(RTRIM(s.num_protocolo)) <> ''
  AND s.din_solicitacao >= '2021-01-01'
  AND m.din_exclusao IS NULL
  AND m.id_formularioitemcampo IN (1109, 1111, 1112, 1114, 1115, 1117, 1118, 1119)
ORDER BY
    s.num_protocolo,
    m.id_solicitacaoformulario,
    m.id_formularioitemcampo,
    m.id_mustpordisteuniconsumidora
"""

SQL_ANALISE_TECNICA = """
SELECT
    at.id_analisetecnica,
    at.id_solicitacao,
    at.id_tpanalisetecnica,
    at.din_solicitacao,
    at.din_envioanalise,
    at.val_prazo
FROM sgacesso.tb_analisetecnica at
WHERE at.id_tpanalisetecnica = 13
  AND at.din_cancelamento IS NULL
"""

# Liga num_protocolo (parecer de acesso) ao id_contrato (CUST assinado)
SQL_CUST_ASSINADO = """
SELECT
    LTRIM(RTRIM(ap.num_protocolo)) AS num_protocolo,
    ap.id_contrato,
    c.cod_contrato
FROM bdt.tb_associacontratopareceracesso ap
LEFT JOIN bdt.tb_contrato c ON ap.id_contrato = c.id_contrato
WHERE ap.num_protocolo IS NOT NULL
  AND LTRIM(RTRIM(ap.num_protocolo)) <> ''
"""

# Documento emitido oficial: inbound.sgacesso.tb_documento.
# id_tpdocumento: 1=SFX, 3=SAM, 12=SPA/RPA/RVA, 13=SPT.
SQL_DOCUMENTOS_EMITIDOS = """
SELECT
    d.id_solicitacao,
    LTRIM(RTRIM(s.num_protocolo)) AS num_protocolo_sga,
    d.id_tpdocumento AS id_documento,
    d.num_protocolo AS num_documento_emitido_doc,
    d.din_criacao AS din_emissao_documento_doc
FROM sgacesso.tb_documento d
INNER JOIN sgacesso.tb_solicitacao s
    ON d.id_solicitacao = s.id_solicitacao
WHERE d.id_tpdocumento IN (1, 3, 12, 13)
  AND d.num_protocolo IS NOT NULL
  AND LTRIM(RTRIM(d.num_protocolo)) <> ''
  AND s.num_protocolo IS NOT NULL
  AND LTRIM(RTRIM(s.num_protocolo)) <> ''
  AND s.din_solicitacao >= '2021-01-01'
"""


def _read_sql(sql):
    conn = get_connection()
    try:
        return pd.read_sql(sql, conn)
    finally:
        conn.close()


def load_raw_data():
    return _read_sql(SQL_QUERY)


def load_raw_data_for_protocols(protocols):
    """Versão otimizada: só baixa linhas dos protocolos especificados."""
    placeholders = _quoted_protocols(protocols)
    if not placeholders:
        return pd.DataFrame()

    sql = f"""
SELECT
    am.id_aumentomust,
    am.id_solicitacaoformulario,
    am.id_formularioitemcampo,
    am.val_dado,
    am.din_exclusao,
    am.din_modificacao,
    s.id_solicitacao,
    s.num_protocolo,
    s.nom_internosolicitacao,
    s.nom_solicitacao,
    s.dsc_solicitacao,
    s.din_solicitacao,
    s.id_viabilidade,
    sa.nom_uf,
    sa.nom_solicitacaoacesso,
    sa.nom_tpsolicitacaoacesso,
    sa.nom_tipoempreendimento,
    sa.nom_analistaacessoresponsavel,
    sa.nom_empreendimento,
    sa.dsc_ptoconexao,
    sa.dsc_objetivosolicitacao,
    sa.dsc_ambientecontratacao,
    sa.cod_contrato,
    sa.num_documento_emitido,
    sa.dsc_status,
    sa.din_solicitacaoacesso,
    sa.din_aceitesolicitacao,
    sa.val_prazoemissao,
    sa.val_periodointerrompida,
    sa.din_emissaodocumento,
    sa.din_cancelamento,
    sa.din_conexao,
    sa.din_assinaturacontrato,
    sa.din_inicioentradaoperacao,
    sa.flg_cancelada,
    sa.flg_documentoemitido
FROM sgacesso.tb_solicitacao s
INNER JOIN sgacesso.tb_solicitacaoformulario sf
    ON s.id_solicitacao = sf.id_solicitacao
INNER JOIN sgacesso.tb_aumentomust am
    ON sf.id_solicitacaoformulario = am.id_solicitacaoformulario
LEFT JOIN bca.dbo.tb_solicitacaoacesso sa
    ON s.id_solicitacao = sa.id_solicitacao
WHERE LTRIM(RTRIM(s.num_protocolo)) IN ({placeholders})
  AND am.din_exclusao IS NULL
"""
    return _read_sql(sql)


def load_solicitacoes_data():
    """Carrega metadados das solicitações mesmo quando não há registros em tb_aumentomust."""
    return _read_sql(SQL_SOLICITACOES_QUERY)


def load_solicitacoes_data_for_protocols(protocols):
    """Versão otimizada: só metadados dos protocolos especificados."""
    placeholders = _quoted_protocols(protocols)
    if not placeholders:
        return pd.DataFrame()

    sql = f"""
SELECT
    s.id_solicitacao,
    s.num_protocolo,
    s.nom_internosolicitacao,
    s.nom_solicitacao,
    s.dsc_solicitacao,
    s.din_solicitacao,
    s.id_viabilidade,
    sa.nom_uf,
    sa.nom_solicitacaoacesso,
    sa.nom_tpsolicitacaoacesso,
    sa.nom_tipoempreendimento,
    sa.nom_analistaacessoresponsavel,
    sa.nom_empreendimento,
    sa.dsc_ptoconexao,
    sa.dsc_objetivosolicitacao,
    sa.dsc_ambientecontratacao,
    sa.cod_contrato,
    sa.num_documento_emitido,
    sa.dsc_status,
    sa.din_solicitacaoacesso,
    sa.din_aceitesolicitacao,
    sa.val_prazoemissao,
    sa.val_periodointerrompida,
    sa.din_emissaodocumento,
    sa.din_cancelamento,
    sa.din_conexao,
    sa.din_assinaturacontrato,
    sa.din_inicioentradaoperacao,
    sa.flg_cancelada,
    sa.flg_documentoemitido
FROM sgacesso.tb_solicitacao s
LEFT JOIN bca.dbo.tb_solicitacaoacesso sa
    ON s.id_solicitacao = sa.id_solicitacao
WHERE LTRIM(RTRIM(s.num_protocolo)) IN ({placeholders})
"""
    return _read_sql(sql)


def load_datacenter_must_data():
    """Carrega dados de MUST de SPA/RPA na tabela tb_mustpordisteuniconsumidora."""
    return _read_sql(SQL_DATACENTER_MUST_QUERY)


def load_datacenter_must_data_for_protocols(protocols):
    """Versão otimizada: só MUST SPA/RPA dos protocolos especificados."""
    placeholders = _quoted_protocols(protocols)
    if not placeholders:
        return pd.DataFrame()

    sql = f"""
SELECT
    s.num_protocolo,
    s.id_solicitacao,
    s.din_solicitacao,
    s.id_viabilidade,
    m.id_mustpordisteuniconsumidora,
    m.id_solicitacaoformulario,
    m.id_formularioitemcampo,
    fic.nom_campo,
    fic.nom_grupo,
    m.val_dado,
    m.din_modificacao,
    m.din_inclusao,
    m.din_alteracao,
    m.din_submissao,
    m.din_exclusao
FROM sgacesso.tb_solicitacao s
INNER JOIN sgacesso.tb_solicitacaoformulario sf
    ON s.id_solicitacao = sf.id_solicitacao
INNER JOIN sgacesso.tb_mustpordisteuniconsumidora m
    ON sf.id_solicitacaoformulario = m.id_solicitacaoformulario
LEFT JOIN sgacesso.tb_formularioitemcampo fic
    ON m.id_formularioitemcampo = fic.id_formularioitemcampo
WHERE LTRIM(RTRIM(s.num_protocolo)) IN ({placeholders})
  AND m.din_exclusao IS NULL
  AND m.id_formularioitemcampo IN (1109, 1111, 1112, 1114, 1115, 1117, 1118, 1119)
ORDER BY
    s.num_protocolo,
    m.id_solicitacaoformulario,
    m.id_formularioitemcampo,
    m.id_mustpordisteuniconsumidora
"""
    return _read_sql(sql)


def load_analise_tecnica_data():
    """Carrega dados de análise técnica (apenas tipo 13 = PL)."""
    return _read_sql(SQL_ANALISE_TECNICA)


def load_cust_assinado_data():
    """Carrega protocolos com CUST assinado e seus códigos de contrato."""
    return _read_sql(SQL_CUST_ASSINADO)


def load_documentos_emitidos_data():
    """Carrega documentos emitidos oficiais a partir de sgacesso.tb_documento."""
    return _read_sql(SQL_DOCUMENTOS_EMITIDOS)


def load_documentos_emitidos_data_for_protocols(protocols):
    """Versão otimizada: só documentos emitidos dos protocolos especificados."""
    placeholders = _quoted_protocols(protocols)
    if not placeholders:
        return pd.DataFrame()

    sql = f"""
SELECT
    d.id_solicitacao,
    LTRIM(RTRIM(s.num_protocolo)) AS num_protocolo_sga,
    d.id_tpdocumento AS id_documento,
    d.num_protocolo AS num_documento_emitido_doc,
    d.din_criacao AS din_emissao_documento_doc
FROM sgacesso.tb_documento d
INNER JOIN sgacesso.tb_solicitacao s
    ON d.id_solicitacao = s.id_solicitacao
WHERE LTRIM(RTRIM(s.num_protocolo)) IN ({placeholders})
  AND d.id_tpdocumento IN (1, 3, 12, 13)
  AND d.num_protocolo IS NOT NULL
  AND LTRIM(RTRIM(d.num_protocolo)) <> ''
"""
    return _read_sql(sql)

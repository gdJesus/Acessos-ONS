"""Constantes e dicionários usados nas transformações do Dashboard MUST."""

# Dicionário de campos
CAMPO_META = {
    944: "cust",
    945: "data_assinatura",
    946: "codigo_ons",
    947: "instalacao",
    948: "tensao_kv",
    949: "periodo_inicio",
    950: "periodo_fim",
}

CAMPO_MUST_PONTA = {953: 1, 955: 2, 957: 3, 959: 4, 967: 5, 969: 6}
CAMPO_MUST_FORA  = {954: 1, 956: 2, 958: 3, 960: 4, 968: 5, 970: 6}

ANO_LABELS = {1: "Ano Corrente", 2: "Ano 2", 3: "Ano 3", 4: "Ano 4", 5: "Ano 5", 6: "Ano 6"}

# Mapa UF → Nome do estado (extraído do prefixo do código ONS)
UF_MAP = {
    "AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá",
    "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo",
    "GO": "Goiás", "MA": "Maranhão", "MG": "Minas Gerais", "MS": "Mato Grosso do Sul",
    "MT": "Mato Grosso", "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco",
    "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RO": "Rondônia", "RR": "Roraima", "RS": "Rio Grande do Sul", "SC": "Santa Catarina",
    "SE": "Sergipe", "SP": "São Paulo", "TO": "Tocantins",
}

PROTO_RE_PATTERN = r"SGA-[A-Z]{3}-\d{4}/\d{4}"
YEARS_DC = list(range(2025, 2031))

# Dicionário validado para SPA/RPA em sgacesso.tb_mustpordisteuniconsumidora
DC_FIELD_INSTALACAO = 1109
DC_FIELD_PERIODO_INICIO = 1111
DC_FIELD_PERIODO_FIM = 1112
DC_FIELD_MUST_PONTA = 1114
DC_FIELD_MUST_FORA = 1115
DC_FIELD_FATOR_POT_PONTA = 1117
DC_FIELD_FATOR_POT_FORA = 1118
DC_FIELD_FATOR_CARGA = 1119

"""Funções utilitárias compartilhadas."""

import pandas as pd

from .constants import UF_MAP

def extrair_uf(codigo_ons):
    """Extrai a UF (2 letras) do código ONS. Ex: SPDES-138 → SP, RJSTNV138 → RJ."""
    if not codigo_ons or len(codigo_ons) < 2:
        return ""
    uf = codigo_ons[:2].upper()
    return uf if uf in UF_MAP else ""


def normalize_uf(val, default="—"):
    """Normaliza UF vinda do banco, sem fallback pelo ponto de contratação.

    Trata espaços digitados antes/depois ou entre as letras:
      "SP "  -> "SP"
      " SP"  -> "SP"
      " S P" -> "SP"

    Se o valor não for uma UF válida de dois caracteres, retorna o default.
    """
    if val is None:
        return default
    try:
        if pd.isna(val):
            return default
    except Exception:
        pass

    s = str(val).strip().upper()
    if not s or s in ("—", "-", "NAN", "NONE", "NULL"):
        return default

    compact = "".join(s.split())
    return compact if compact in UF_MAP else default


def parse_br_number(val):
    """Converte número brasileiro (vírgula decimal) para float."""
    if pd.isna(val) or str(val).strip() in ("", "—", "-"):
        return None
    s = str(val).strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def fmt_date(val):
    """Formata datas vindas do SQL sem quebrar quando o valor vier vazio/texto."""
    if pd.isna(val):
        return ""
    if hasattr(val, "strftime"):
        return val.strftime("%d/%m/%Y")
    return str(val).strip()


def first_non_empty(series, default=""):
    for val in series:
        if pd.notna(val) and str(val).strip() not in ("", "nan", "None", "NULL"):
            return str(val).strip()
    return default

"""Leitura do BD entrada (viabilidades.xlsx) — fonte de input do usuário."""

import re
import zipfile
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path


VIABILIDADE_VALORES = (
    "Viável",
    "Viável/Condicionado",
    "Limitado/Viável/Condicionado",
    "Inviável",
    "Em análise",
)


def _read_xlsx_rows(path, sheet_name="Solicitações"):
    """Lê todas as células de uma aba do XLSX. Retorna lista de dicts {header: valor}."""
    path = Path(path)
    if not path.exists():
        return []

    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

    with zipfile.ZipFile(path) as zf:
        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("a:si", ns):
                texts = [t.text or "" for t in si.findall(".//a:t", ns)]
                shared.append("".join(texts))

        # Encontrar id da sheet
        wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
        sheet_rid = None
        for s in wb_root.findall(".//a:sheet", ns):
            if s.attrib.get("name") == sheet_name:
                sheet_rid = s.attrib.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                )
                break
        if not sheet_rid:
            return []

        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        sheet_path = None
        for r in rels_root.findall(
            "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
        ):
            if r.attrib.get("Id") == sheet_rid:
                target = r.attrib.get("Target", "")
                # Normalizar path:
                #   "worksheets/sheet1.xml" → "xl/worksheets/sheet1.xml"
                #   "/xl/worksheets/sheet1.xml" → "xl/worksheets/sheet1.xml"
                #   "xl/worksheets/sheet1.xml" → "xl/worksheets/sheet1.xml"
                t = target.lstrip("/")
                if t.startswith("xl/"):
                    sheet_path = t
                else:
                    sheet_path = "xl/" + t
                break
        if not sheet_path or sheet_path not in zf.namelist():
            return []

        root = ET.fromstring(zf.read(sheet_path))
        rows_raw = {}
        for r in root.findall(".//a:row", ns):
            row_idx = int(r.attrib.get("r", "0"))
            for c in r.findall("a:c", ns):
                ref = c.attrib.get("r", "")
                col_letters = "".join(ch for ch in ref if ch.isalpha())
                col_idx = 0
                for ch in col_letters:
                    col_idx = col_idx * 26 + (ord(ch) - ord("A") + 1)
                cell_type = c.attrib.get("t")
                value = None

                if cell_type == "inlineStr":
                    # Inline string: <is><t>texto</t></is> (pode ter múltiplos <t> em <r>)
                    is_node = c.find("a:is", ns)
                    if is_node is not None:
                        texts = [t.text or "" for t in is_node.findall(".//a:t", ns)]
                        value = "".join(texts)
                elif cell_type == "s":
                    # Shared string
                    v = c.find("a:v", ns)
                    if v is not None and v.text is not None:
                        try:
                            value = shared[int(v.text)]
                        except Exception:
                            value = ""
                else:
                    # Numérico ou outro tipo
                    v = c.find("a:v", ns)
                    if v is not None and v.text is not None:
                        value = v.text

                if value is None or value == "":
                    continue
                rows_raw.setdefault(row_idx, {})[col_idx] = value

        if not rows_raw:
            return []

        header_row = rows_raw.get(1, {})
        if not header_row:
            return []
        max_col = max(header_row.keys())
        headers = [header_row.get(i, f"Col{i}") for i in range(1, max_col + 1)]

        out = []
        for row_idx in sorted(rows_raw.keys()):
            if row_idx == 1:
                continue
            row_data = rows_raw[row_idx]
            rec = {}
            for i, h in enumerate(headers, start=1):
                rec[h] = str(row_data.get(i, "")).strip()
            if any(v for v in rec.values()):
                out.append(rec)
        return out


def load_viabilidades(path="viabilidades.xlsx"):
    """Carrega o BD entrada multi-aba (FONTE DE VERDADE).

    Estrutura:
      - Aba 'Pontos' (MESTRA): cols Protocolo, Ponto, Empreendimento, Rede,
        Tensão (kV), Viabilidade Geral. Define quantas linhas existem.
      - Abas auxiliares (lookup por Protocolo + Ponto):
        * 'Viabilidade'         — dropdown por ano
        * 'Condicionantes'      — texto livre por ano
        * 'SEP'                 — texto livre por ano
        * 'Limitado Ponta'      — MW por ano
        * 'Limitado FP'         — MW por ano
        * 'MUST Ponta (PTDis)'  — MW manual por ano
        * 'MUST FP (PTDis)'     — MW manual por ano

    Para cadastrar novo ponto, basta editar a aba 'Pontos'.

    Retorna LISTA ordenada (preserva a ordem da aba 'Pontos'):
      [
        {
          "protocolo": "...", "ponto": "...", "empreendimento": "...",
          "rede": "...", "tensao": "...", "viabilidade_geral": "...",
          "anos": {
            2025: {"viabilidade":..., "condicionantes":..., "sep":...,
                   "limitado_ponta":..., "limitado_fp":...,
                   "must_ponta":..., "must_fora":...},
            ...
          },
        },
        ...
      ]
    """
    import re

    # 1) Aba Pontos = mestra (define linhas)
    pontos_rows = _read_xlsx_rows(path, sheet_name="Pontos")
    if not pontos_rows:
        # Compatibilidade: tentar formato antigo (aba "Viabilidade" com cols base)
        viab_with_base = _read_xlsx_rows(path, sheet_name="Viabilidade")
        if viab_with_base and "Empreendimento" in (viab_with_base[0].keys() if viab_with_base else {}):
            return _load_viabilidades_old_multi_aba(path)
        return _load_viabilidades_legacy(path)

    out = []
    by_key = {}

    for r in pontos_rows:
        proto = (r.get("Protocolo") or "").strip()
        if not proto:
            continue
        ponto = (r.get("Ponto") or "").strip()

        entry = {
            "protocolo": proto,
            "ponto": ponto,
            "empreendimento": (r.get("Empreendimento") or "").strip(),
            "rede": (r.get("Rede") or "").strip().upper(),
            "tensao": (r.get("Tensão (kV)") or r.get("Tensão") or "").strip(),
            "viabilidade_geral": (r.get("Viabilidade Geral") or "").strip(),
            "relacao_protocolo_revisado": (r.get("Relação Protocolo Revisado") or "").strip(),
            "anos": {},
        }
        out.append(entry)
        by_key[(proto, ponto)] = entry

    # 2) Abas auxiliares — lookup por (proto, ponto)
    aba_para_kind = {
        "Viabilidade": "viabilidade",
        "Condicionantes": "condicionantes",
        "SEP": "sep",
        "Limitado Ponta": "limitado_ponta",
        "Limitado FP": "limitado_fp",
        "MUST Ponta (PTDis)": "must_ponta",
        "MUST FP (PTDis)": "must_fora",
    }

    for aba, kind_key in aba_para_kind.items():
        rows = _read_xlsx_rows(path, sheet_name=aba)
        if not rows:
            continue
        for r in rows:
            proto = (r.get("Protocolo") or "").strip()
            ponto = (r.get("Ponto") or "").strip()
            if not proto:
                continue
            entry = by_key.get((proto, ponto))
            if entry is None:
                continue
            for h, v in r.items():
                if not h or not v:
                    continue
                m = re.match(r"^Y(\d{4})$", h.strip())
                if not m:
                    continue
                year = int(m.group(1))
                entry["anos"].setdefault(year, {})[kind_key] = str(v).strip()

    return out


def _load_viabilidades_old_multi_aba(path):
    """Compatibilidade: formato anterior multi-aba sem 'Pontos' (aba Viabilidade
    continha Protocolo, Ponto, Empreendimento, Rede, Tensão, Viabilidade Geral)."""
    import re
    viab_rows = _read_xlsx_rows(path, sheet_name="Viabilidade")
    if not viab_rows:
        return []

    out = []
    by_key = {}

    for r in viab_rows:
        proto = (r.get("Protocolo") or "").strip()
        if not proto:
            continue
        ponto = (r.get("Ponto") or "").strip()

        entry = {
            "protocolo": proto,
            "ponto": ponto,
            "empreendimento": (r.get("Empreendimento") or "").strip(),
            "rede": (r.get("Rede") or "").strip().upper(),
            "tensao": (r.get("Tensão (kV)") or r.get("Tensão") or "").strip(),
            "viabilidade_geral": (r.get("Viabilidade Geral") or "").strip(),
            "relacao_protocolo_revisado": (r.get("Relação Protocolo Revisado") or "").strip(),
            "anos": {},
        }
        for h, v in r.items():
            if not h or not v:
                continue
            m = re.match(r"^Y(\d{4})$", h.strip())
            if not m:
                continue
            year = int(m.group(1))
            entry["anos"].setdefault(year, {})["viabilidade"] = str(v).strip()
        out.append(entry)
        by_key[(proto, ponto)] = entry

    aba_para_kind = {
        "Condicionantes": "condicionantes",
        "SEP": "sep",
        "Limitado Ponta": "limitado_ponta",
        "Limitado FP": "limitado_fp",
        "MUST Ponta (PTDis)": "must_ponta",
        "MUST FP (PTDis)": "must_fora",
    }
    for aba, kind_key in aba_para_kind.items():
        rows = _read_xlsx_rows(path, sheet_name=aba)
        if not rows:
            continue
        for r in rows:
            proto = (r.get("Protocolo") or "").strip()
            ponto = (r.get("Ponto") or "").strip()
            entry = by_key.get((proto, ponto))
            if entry is None:
                continue
            for h, v in r.items():
                if not h or not v:
                    continue
                m = re.match(r"^Y(\d{4})$", h.strip())
                if not m:
                    continue
                year = int(m.group(1))
                entry["anos"].setdefault(year, {})[kind_key] = str(v).strip()
    return out


def _load_viabilidades_legacy(path):
    """Compatibilidade: formato antigo (aba 'Solicitações' wide)."""
    import re
    rows = _read_xlsx_rows(path, sheet_name="Solicitações")
    out = []
    for r in rows:
        proto = (r.get("Protocolo") or "").strip()
        if not proto:
            continue
        ponto = (r.get("Ponto") or "").strip()

        entry = {
            "protocolo": proto,
            "ponto": ponto,
            "empreendimento": (r.get("Empreendimento") or "").strip(),
            "rede": (r.get("Rede") or "").strip().upper(),
            "tensao": (r.get("Tensão (kV)") or r.get("Tensão") or "").strip(),
            "viabilidade_geral": (r.get("Viabilidade Geral") or "").strip(),
            "relacao_protocolo_revisado": (r.get("Relação Protocolo Revisado") or "").strip(),
            "anos": {},
        }

        for h, v in r.items():
            if not h or not v:
                continue
            if not h.startswith("Y"):
                continue
            parts = h.split(" ", 1)
            if len(parts) != 2:
                continue
            year_part, kind = parts[0], parts[1].strip()
            try:
                year = int(year_part[1:])
            except ValueError:
                continue
            ano_data = entry["anos"].setdefault(year, {})
            if kind == "Viab":
                ano_data["viabilidade"] = v
            elif kind == "Cond":
                ano_data["condicionantes"] = v
            elif kind == "SEP":
                ano_data["sep"] = v
            elif kind in ("Lim P", "LimP"):
                ano_data["limitado_ponta"] = v
            elif kind in ("Lim FP", "LimFP"):
                ano_data["limitado_fp"] = v
            elif kind in ("MUST P", "MUSTP"):
                ano_data["must_ponta"] = v
            elif kind in ("MUST FP", "MUSTFP"):
                ano_data["must_fora"] = v

        out.append(entry)
    return out


def normalize_ponto(s):
    """Normaliza string de ponto/instalação: sem acento, maiúsculo, sem 'kV'/'SE'/parênteses."""
    if not s:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")
    s = s.upper()
    # Remove parênteses e seu conteúdo
    s = re.sub(r"\([^)]*\)", " ", s)
    # Remove referências de tensão (138, 230, 440, 88 + kV)
    s = re.sub(r"\b\d{2,3}\s*KV\b", " ", s)
    s = re.sub(r"-\s*\d{2,3}\s*KV", " ", s)
    s = re.sub(r"\b\d{2,3}\b", " ", s)
    # Remove tokens auxiliares
    for token in ["LTA", "LT", "SE ", "SUBESTACAO", "BARRAMENTO DE", "BARRAMENTO",
                  "SECCIONAMENTO", "DERIVACAO", "DUPLA DERIVACAO", "C1", "C2",
                  "DA", "DE", "DO", "DAS", "DOS"]:
        s = re.sub(rf"\b{token}\b", " ", s)
    s = re.sub(r"[/\-_,;]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def match_ponto_to_instalacao(ponto_text, instalacoes_disponiveis):
    """Tenta achar a instalação correspondente comparando texto normalizado.

    ponto_text: ex: "SE Cabreúva 230 kV (C)"
    instalacoes_disponiveis: lista de strings (vindas do banco), ex: ["CABREUVA", "ANHANGUERA", ...]

    Retorna: a instalação que melhor combina, ou None.
    Estratégia: a instalação cujas palavras estão TODAS contidas no texto normalizado do ponto.
    """
    norm_ponto = normalize_ponto(ponto_text)
    if not norm_ponto:
        return None

    palavras_ponto = set(norm_ponto.split())
    melhor = None
    melhor_score = 0

    for inst in instalacoes_disponiveis:
        if not inst:
            continue
        norm_inst = normalize_ponto(inst)
        if not norm_inst:
            continue
        palavras_inst = set(norm_inst.split())
        if not palavras_inst:
            continue
        # Score = quantas palavras da instalação aparecem no ponto
        score = len(palavras_inst & palavras_ponto)
        # Bônus: se TODAS as palavras da instalação combinam
        if score == len(palavras_inst):
            score += 10
        # Bônus: substring direta
        if norm_inst in norm_ponto:
            score += 5
        if score > melhor_score:
            melhor_score = score
            melhor = inst

    return melhor if melhor_score > 0 else None


def get_viabilidade_resumo(viab_dict_for_proto, pl_emitida=False):
    """Retorna status resumido a partir do dict de viabilidade.

    Regra de negócio:
      - viabilidade_geral preenchida → usa esse valor;
      - viabilidades anuais com um único valor → usa esse valor;
      - viabilidades anuais com valores diferentes → "Misto";
      - vazio + PL emitida → "Pendente";
      - vazio + PL ainda não emitida → "Em análise".

    Observação:
      "Pendente" significa pendência de preenchimento manual no BD entrada.
      Portanto, só faz sentido quando a PL já emitiu a análise.
    """
    status_vazio = "Pendente" if pl_emitida else "Em análise"

    if not viab_dict_for_proto:
        return status_vazio

    geral = (viab_dict_for_proto.get("viabilidade_geral") or "").strip()
    if geral:
        return geral

    anos = viab_dict_for_proto.get("anos", {}) or {}
    valores = []
    for _year, vals in sorted(anos.items()):
        v = (vals.get("viabilidade") or "").strip()
        if v and v not in valores:
            valores.append(v)

    if not valores:
        return status_vazio
    if len(valores) == 1:
        return valores[0]
    return "Misto"


def compute_pendencias(row, viab_for_proto):
    """Retorna lista de pendências da linha (badges coloridos).

    Pendências:
      - Aguardando viabilidade: PL emitida + viabilidade vazia;
      - Falta condicionante: viabilidade contém 'Condicionado' + sem condicionantes;
      - Falta valor limitado: viabilidade contém 'Limitado' + sem valores.
    """
    pendencias = []
    if not row:
        return pendencias

    data_emissao_pl = row.get("data_emissao_pl")
    pl_emitida = bool(
        data_emissao_pl
        and str(data_emissao_pl).strip() not in ("—", "", "None", "nan", "NaT")
    )

    resumo = get_viabilidade_resumo(viab_for_proto or {}, pl_emitida=pl_emitida)

    if pl_emitida and resumo == "Pendente":
        pendencias.append("Aguardando viabilidade")

    has_cond = "condicionado" in resumo.lower()
    if has_cond and viab_for_proto:
        anos = viab_for_proto.get("anos", {}) or {}
        cond_alguma = any((vals.get("condicionantes") or "").strip() for vals in anos.values())
        if not cond_alguma:
            pendencias.append("Falta condicionante")

    has_lim = "limitado" in resumo.lower()
    if has_lim and viab_for_proto:
        anos = viab_for_proto.get("anos", {}) or {}
        lim_algum = any(
            (vals.get("limitado_ponta") or "").strip()
            or (vals.get("limitado_fp") or "").strip()
            for vals in anos.values()
        )
        if not lim_algum:
            pendencias.append("Falta valor limitado")

    return pendencias

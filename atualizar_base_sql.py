"""Atualiza a base offline do Dashboard DataCenters.

Padrão:
    python atualizar_base_sql.py

    Lê viabilidades.xlsx na pasta do programa e grava dashboard_sql_cache.pkl.gz
    também na pasta do programa.

Para gravar/ler na pasta compartilhada da rede:
    python atualizar_base_sql.py --usar-rede

Ou especificando caminhos:
    python atualizar_base_sql.py --data-dir "\\\\ons.org.br\\rio-arq\\_PL\\_PL_PAR\\_Dados e Projetos\\DataCenters_SP"
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from dashboard.dashboard_cache import (
    CACHE_VERSION,
    DEFAULT_CACHE_NAME,
    DEFAULT_DATA_DIR,
    DEFAULT_VIABILIDADES_NAME,
    save_sql_cache,
)
from dashboard.viabilidade_source import load_viabilidades


APP_DIR = Path(__file__).resolve().parent


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Atualiza cache SQL offline do Dashboard DataCenters.")
    parser.add_argument(
        "--usar-rede",
        action="store_true",
        help="Usa a pasta compartilhada padrão da rede para ler viabilidades.xlsx e salvar o cache.",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Pasta onde ficam viabilidades.xlsx e onde será salvo o cache. Se omitido, usa a pasta local do programa.",
    )
    parser.add_argument(
        "--viabilidades",
        default=None,
        help="Caminho completo do viabilidades.xlsx. Se omitido, usa data-dir/viabilidades.xlsx.",
    )
    parser.add_argument(
        "--saida",
        default=None,
        help="Caminho completo do cache de saída. Se omitido, usa data-dir/dashboard_sql_cache.pkl.gz.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.data_dir:
        data_dir = Path(args.data_dir)
    elif args.usar_rede:
        data_dir = Path(DEFAULT_DATA_DIR)
    else:
        data_dir = APP_DIR

    viab_path = Path(args.viabilidades) if args.viabilidades else data_dir / DEFAULT_VIABILIDADES_NAME
    out_path = Path(args.saida) if args.saida else data_dir / DEFAULT_CACHE_NAME

    if not viab_path.exists():
        raise FileNotFoundError(f"viabilidades.xlsx não encontrado em: {viab_path}")

    print(f"[CACHE] Lendo viabilidades: {viab_path}", flush=True)
    entries = load_viabilidades(viab_path)
    protocols_needed = sorted({
        (e.get("protocolo") or "").strip()
        for e in entries
        if (e.get("protocolo") or "").strip()
    })
    print(f"[CACHE] {len(entries)} linhas no Excel; {len(protocols_needed)} protocolos únicos para DataCenters.", flush=True)

    # Importa db.py somente aqui. Assim o app publicado no Posit não precisa de pyodbc.
    from db import (
        load_raw_data,
        load_raw_data_for_protocols,
        load_solicitacoes_data,
        load_datacenter_must_data,
        load_analise_tecnica_data,
        load_cust_assinado_data,
        load_documentos_emitidos_data,
    )

    print("[CACHE] Baixando tb_aumentomust completa para Visão Geral...", flush=True)
    raw_full = load_raw_data()
    print(f"[CACHE]   {len(raw_full)} linhas.", flush=True)

    print("[CACHE] Baixando tb_aumentomust filtrada para DataCenters...", flush=True)
    raw = load_raw_data_for_protocols(protocols_needed)
    print(f"[CACHE]   {len(raw)} linhas.", flush=True)

    print("[CACHE] Baixando metadados de todas as solicitações para Visão Geral...", flush=True)
    solicitacoes_raw = load_solicitacoes_data()
    print(f"[CACHE]   {len(solicitacoes_raw)} linhas.", flush=True)

    print("[CACHE] Baixando MUST SPA/RPA de todas as solicitações para Visão Geral...", flush=True)
    dc_must_raw = load_datacenter_must_data()
    print(f"[CACHE]   {len(dc_must_raw)} linhas.", flush=True)

    print("[CACHE] Baixando análise técnica PL...", flush=True)
    analise_raw = load_analise_tecnica_data()
    print(f"[CACHE]   {len(analise_raw)} linhas.", flush=True)

    print("[CACHE] Baixando CUST assinado...", flush=True)
    cust_raw = load_cust_assinado_data()
    print(f"[CACHE]   {len(cust_raw)} linhas.", flush=True)

    print("[CACHE] Baixando documentos emitidos de todas as solicitações (sgacesso.tb_documento)...", flush=True)
    documentos_raw = load_documentos_emitidos_data()
    print(f"[CACHE]   {len(documentos_raw)} linhas.", flush=True)

    # Pré-processa os trechos mais caros da inicialização. O app continua
    # aceitando caches antigos, mas caches novos evitam refazer isso no Posit.
    from dashboard.transforms import (
        transform_eav_to_model,
        transform_solicitacoes_meta,
        transform_datacenter_must_model,
    )

    print("[CACHE] Pré-processando modelos para acelerar o startup do Posit Connect...", flush=True)
    model_protocols = transform_eav_to_model(raw_full) if raw_full is not None and not raw_full.empty else []
    solicitacoes_meta = transform_solicitacoes_meta(solicitacoes_raw)
    dc_must_by_proto = transform_datacenter_must_model(dc_must_raw)
    print(
        "[CACHE]   "
        f"{len(model_protocols)} protocolos modelados; "
        f"{len(solicitacoes_meta)} metadados; "
        f"{len(dc_must_by_proto)} protocolos SPA/RPA com MUST.",
        flush=True,
    )

    payload = {
        "cache_version": CACHE_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "viabilidades_path": str(viab_path),
        "protocols_needed": protocols_needed,
        "raw_full": raw_full,
        "raw": raw,
        "solicitacoes_raw": solicitacoes_raw,
        "dc_must_raw": dc_must_raw,
        "analise_raw": analise_raw,
        "cust_raw": cust_raw,
        "documentos_raw": documentos_raw,
        "model_protocols": model_protocols,
        "solicitacoes_meta": solicitacoes_meta,
        "dc_must_by_proto": dc_must_by_proto,
    }

    saved = save_sql_cache(payload, out_path)
    print(f"[CACHE] ✅ Cache atualizado em: {saved}", flush=True)


if __name__ == "__main__":
    main()

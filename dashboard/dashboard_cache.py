"""Utilitários de cache/offline para o Dashboard DataCenters.

A ideia é separar o que precisa de ODBC do que roda no Posit Connect:
- `atualizar_base_sql.py` roda em uma máquina com ODBC e grava o cache.
- `dashboard/data.py` roda no Posit e apenas lê esse cache + viabilidades.xlsx.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import pandas as pd


DEFAULT_DATA_DIR = r"\\ons.org.br\\rio-arq\_PL\\_PL_PAR\\_Dados e Projetos\\DataCenters_SP"
DEFAULT_CACHE_NAME = "dashboard_sql_cache.pkl.gz"
DEFAULT_VIABILIDADES_NAME = "viabilidades.xlsx"
CACHE_VERSION = 6


def _as_path(value: str | os.PathLike | None) -> Optional[Path]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return Path(text)


def data_dir() -> Path:
    """Diretório padrão dos arquivos compartilhados.

    Pode ser sobrescrito por variável de ambiente:
        DASHBOARD_DATA_DIR=.../DataCenters_SP
    """
    return _as_path(os.environ.get("DASHBOARD_DATA_DIR")) or Path(DEFAULT_DATA_DIR)


def _candidate_paths(env_var: str, filename: str) -> Iterable[Path]:
    env_value = _as_path(os.environ.get(env_var))
    if env_value is not None:
        yield env_value

    # Pasta onde o app.py está rodando / deploy do Posit — preferir cache local.
    yield Path.cwd() / filename

    # Um nível acima do pacote dashboard, útil quando importado de dashboard/data.py.
    yield Path(__file__).resolve().parents[1] / filename

    # Pasta compartilhada configurada — fallback/uso explícito via --usar-rede ou env.
    yield data_dir() / filename


def resolve_existing_path(env_var: str, filename: str, friendly_name: str) -> Path:
    candidates = list(dict.fromkeys(_candidate_paths(env_var, filename)))
    for p in candidates:
        if p.exists():
            return p

    msg = [f"❌ {friendly_name} não encontrado.", "", "Locais verificados:"]
    msg += [f"  - {p}" for p in candidates]
    msg += [
        "",
        "Como corrigir:",
        f"  1) coloque '{filename}' na pasta do app; ou",
        f"  2) defina {env_var}=caminho/completo/do/arquivo; ou",
        "  3) defina DASHBOARD_DATA_DIR para a pasta compartilhada dos DataCenters.",
    ]
    raise FileNotFoundError("\n".join(msg))


def resolve_viabilidades_path() -> Path:
    return resolve_existing_path(
        "DASHBOARD_VIABILIDADES_PATH",
        DEFAULT_VIABILIDADES_NAME,
        "Arquivo viabilidades.xlsx",
    )


def resolve_cache_path(require_exists: bool = True) -> Path:
    if require_exists:
        return resolve_existing_path(
            "DASHBOARD_CACHE_PATH",
            DEFAULT_CACHE_NAME,
            "Cache SQL do dashboard",
        )

    env_value = _as_path(os.environ.get("DASHBOARD_CACHE_PATH"))
    if env_value is not None:
        return env_value
    return Path.cwd() / DEFAULT_CACHE_NAME


def load_sql_cache(path: str | os.PathLike | None = None) -> Dict[str, Any]:
    cache_path = Path(path) if path else resolve_cache_path(require_exists=True)
    payload = pd.read_pickle(cache_path)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Cache inválido em {cache_path}: conteúdo não é dict.")

    version = payload.get("cache_version")
    if version != CACHE_VERSION:
        raise RuntimeError(
            f"Cache em {cache_path} está na versão {version}; esperado {CACHE_VERSION}. "
            "Rode novamente atualizar_base_sql.py."
        )
    return payload


def save_sql_cache(payload: Dict[str, Any], path: str | os.PathLike | None = None) -> Path:
    cache_path = Path(path) if path else resolve_cache_path(require_exists=False)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    # Mantém a extensão final (.gz, .bz2 etc.) no temporário para o pandas
    # inferir a compressão corretamente. Ex.: x.pkl.gz -> x.pkl.tmp.gz.
    if cache_path.suffix:
        tmp_path = cache_path.with_suffix(".tmp" + cache_path.suffix)
    else:
        tmp_path = cache_path.with_name(cache_path.name + ".tmp")

    compression = "gzip" if cache_path.suffix == ".gz" else "infer"
    pd.to_pickle(payload, tmp_path, compression=compression)
    tmp_path.replace(cache_path)
    return cache_path

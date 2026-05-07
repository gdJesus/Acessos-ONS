"""
Dashboard MUST — Aumento de MUST
Shiny for Python • Posit Connect

Ponto de entrada da aplicação.
A lógica foi separada no pacote dashboard/ para facilitar manutenção.
"""

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO DA UI
# ═══════════════════════════════════════════════════════════════════════════════
# Mude para False para esconder a sidebar (filtros globais + navegação)
# e mostrar apenas o painel DataCenters em tela cheia.
SHOW_SIDEBAR = True

import os
os.environ["DASHBOARD_SHOW_SIDEBAR"] = "1" if SHOW_SIDEBAR else "0"

from dashboard.main import app

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, launch_browser=True)
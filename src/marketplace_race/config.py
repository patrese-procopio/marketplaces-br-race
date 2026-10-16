"""Configuração central: período, marcas e caminhos.

Tudo que é "regra de negócio" fica aqui, não espalhado pelo código.
Para adicionar um marketplace, basta incluir uma entrada em BRANDS.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

PRESS_POINTS_CSV = RAW_DIR / "press_points.csv"
PDF_POINTS_CSV = RAW_DIR / "conversion_pdf_points.csv"      # web + app (total)
APP_POINTS_CSV = RAW_DIR / "conversion_pdf_app_points.csv"  # só aplicativos

# Janela temporal do gráfico (frequência mensal).
PERIOD = pd.period_range("2024-05", "2025-12", freq="M")

MONTH_LABELS_PT = {
    1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun",
    7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez",
}


@dataclass(frozen=True)
class Brand:
    """Metadados de um marketplace usados na visualização."""

    name: str          # nome canônico (rótulo no gráfico)
    origin: str        # categoria/cor no Flourish
    domain: str        # usado para buscar o ícone
    color: str         # cor da barra (hex)
    pdf_aliases: tuple[str, ...]  # como o nome aparece nas tabelas do PDF


BRANDS: tuple[Brand, ...] = (
    Brand("Mercado Livre", "América Latina", "mercadolivre.com.br", "#FFE600", ("Mercado Livre",)),
    Brand("Shopee", "Ásia", "shopee.com.br", "#FFB4A2", ("Shopee",)),
    # "Amazon" sozinho no PDF é amazon.com (importados); só "Amazon Brasil" é o marketplace nacional.
    Brand("Amazon", "EUA", "amazon.com.br", "#232F3E", ("Amazon Brasil",)),
    Brand("Temu", "Ásia", "temu.com", "#FB7701", ("Temu",)),
    Brand("Shein", "Ásia", "shein.com", "#000000", ("Shein",)),
    Brand("Magalu", "Brasil", "magazineluiza.com.br", "#0086FF", ("Magazine Luiza",)),
    Brand("AliExpress", "Ásia", "aliexpress.com", "#E62E04", ("AliExpress",)),
)

BRANDS_BY_NAME = {b.name: b for b in BRANDS}


def icon_url(domain: str, size: int = 256) -> str:
    """Ícone quadrado do app (favicon), ideal para os círculos/quadrados do Flourish."""
    return f"https://www.google.com/s2/favicons?domain={domain}&sz={size}"


def month_label(period: pd.Period) -> str:
    """2025-07 -> 'jul/25' (formato usado nas colunas e legendas do Flourish)."""
    return f"{MONTH_LABELS_PT[period.month]}/{str(period.year)[2:]}"

"""Extrai as tabelas de ranking do PDF "Relatório Setores do E-commerce" (Conversion).

O PDF traz tabelas no formato:

    jun./25  jul./25  ...  dez./25  Trend
    📱 Mercado Livre  358.540.653  393.286.739  ...  416.091.755  -

Estratégia:
1. Em cada página, localizar a linha de cabeçalho com os meses (ex.: "jun./25").
2. Para as linhas seguintes, procurar um alias de marca conhecido e os N números
   correspondentes aos N meses do cabeçalho.
3. Cada página é classificada pelo tipo de métrica:
   - "total": acessos web + app (rankings Top 30, Marketplace, Importados)
   - "app":   só aplicativos (ranking "maiores apps de e-commerce")
   Misturar os dois seria comparar coisas diferentes (Shopee: 286 mi total x 134 mi app).
4. A mesma marca aparece em várias tabelas do mesmo tipo: valores repetidos são
   deduplicados; divergências geram erro (dado inconsistente não passa calado).

Uso:
    python -m marketplace_race.extract_pdf caminho/do/relatorio.pdf --label "dez/25"
"""
from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

import pandas as pd
import pdfplumber

from .config import APP_POINTS_CSV, BRANDS, PDF_POINTS_CSV

log = logging.getLogger(__name__)

# Páginas cujo texto casa com este padrão trazem tráfego SÓ de aplicativos.
APP_TABLE_PATTERN = re.compile(r"maiores\s+apps", re.IGNORECASE)

MONTH_TOKEN = re.compile(r"\b(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\./(\d{2})\b")
NUMBER = re.compile(r"\b\d{1,3}(?:\.\d{3})+\b")  # 358.540.653
PT_MONTH = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
            "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}


def _parse_header(line: str) -> list[pd.Period] | None:
    """Retorna os meses do cabeçalho, ou None se a linha não for um cabeçalho."""
    tokens = MONTH_TOKEN.findall(line)
    if len(tokens) < 2:
        return None
    return [pd.Period(year=2000 + int(yy), month=PT_MONTH[mm], freq="M") for mm, yy in tokens]


def _match_brand(text_before_numbers: str) -> str | None:
    """Mapeia o texto antes dos números para o nome canônico da marca."""
    for brand in BRANDS:
        for alias in brand.pdf_aliases:
            # \b + fim de string: evita casar "Amazon" dentro de "Amazon Brasil" e vice-versa.
            if re.search(rf"(?:^|\s){re.escape(alias)}\s*$", text_before_numbers):
                return brand.name
    return None


def classify_page(text: str) -> str:
    """'app' para rankings só de aplicativos; 'total' para web + app."""
    return "app" if APP_TABLE_PATTERN.search(text) else "total"


def extract_points(pdf_path: Path, source_label: str) -> dict[str, pd.DataFrame]:
    """Lê o PDF e devolve {"total": df, "app": df} no formato longo do pipeline."""
    # (métrica, marca, mês) -> (valor, página)
    records: dict[tuple[str, str, pd.Period], tuple[int, int]] = {}

    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            metric = classify_page(text)
            months: list[pd.Period] | None = None
            for line in text.splitlines():
                header = _parse_header(line)
                if header:
                    months = header
                    continue
                if not months:
                    continue

                numbers = list(NUMBER.finditer(line))
                if len(numbers) < len(months):
                    continue
                values = numbers[-len(months):]
                brand = _match_brand(line[: values[0].start()].strip())
                if brand is None:
                    continue

                for period, match in zip(months, values):
                    value = int(match.group().replace(".", ""))
                    key = (metric, brand, period)
                    if key in records and records[key][0] != value:
                        raise ValueError(
                            f"Valor divergente para {brand} {period} ({metric}): "
                            f"{records[key][0]} (p.{records[key][1]}) vs {value} (p.{page_no})"
                        )
                    records.setdefault(key, (value, page_no))

    result: dict[str, pd.DataFrame] = {}
    for metric in ("total", "app"):
        rows = [
            {
                "marketplace": brand,
                "mes": str(period),
                "acessos_mi": round(value / 1e6, 1),
                "tipo": "oficial",
                "fonte": f"Conversion PDF {source_label} (p.{page}, {metric})",
            }
            for (m, brand, period), (value, page) in sorted(records.items(), key=lambda kv: kv[0][1:])
            if m == metric
        ]
        result[metric] = pd.DataFrame(rows)
        log.info("Extraídos %d pontos '%s' de %s", len(rows), metric, pdf_path.name)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf", type=Path, help="PDF do Relatório Setores do E-commerce")
    parser.add_argument("--label", default="dez/25", help="edição do relatório (vai para a coluna fonte)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    tables = extract_points(args.pdf, args.label)
    PDF_POINTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    tables["total"].to_csv(PDF_POINTS_CSV, index=False)
    tables["app"].to_csv(APP_POINTS_CSV, index=False)
    for metric, df in tables.items():
        print(f"\n== {metric} ==")
        print(df.pivot(index="marketplace", columns="mes", values="acessos_mi").to_string())


if __name__ == "__main__":
    main()

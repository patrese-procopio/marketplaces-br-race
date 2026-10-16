"""Pipeline principal: pontos brutos -> série mensal completa -> arquivos do Flourish.

Etapas:
1. load_points      junta as fontes e aplica a precedência (fonte primária vence).
2. build_series     cria a grade marca x mês e interpola SÓ entre pontos conhecidos.
3. to_flourish_*    gera o CSV largo, as cores e as legendas no formato do Flourish.

Uso:
    python -m marketplace_race.pipeline
"""
from __future__ import annotations

import logging

import pandas as pd

from .config import (
    BRANDS,
    BRANDS_BY_NAME,
    PDF_POINTS_CSV,
    PERIOD,
    PRESS_POINTS_CSV,
    PROCESSED_DIR,
    icon_url,
    month_label,
)

log = logging.getLogger(__name__)

COLUMNS = ["marketplace", "mes", "acessos_mi", "tipo", "fonte"]

# Ordem de prioridade: quanto MAIOR, mais confiável. Em conflito no mesmo mês, vence a maior.
SOURCE_PRIORITY = {"press": 1, "pdf": 2}

# Linha do tempo narrativa (vira as legendas do vídeo).
CAPTIONS = [
    ("2024-06", "2024-07", "Temu chega ao Brasil"),
    ("2024-08", "2024-09", 'Entra em vigor a "taxa das blusinhas"'),
    ("2025-04", "2025-05", "Temu ultrapassa a Shopee"),
    ("2025-07", "2025-08", "Temu assume o 1º lugar pela primeira vez"),
    ("2025-08", "2025-09", "Mercado Livre retoma a liderança"),
    ("2025-11", "2025-12", "Temu despenca: −93% desde o pico"),
]


def load_points(sources: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Concatena as fontes e mantém, para cada (marca, mês), o ponto da fonte mais confiável."""
    frames = []
    for name, df in sources.items():
        frame = df[COLUMNS].copy()
        frame["prioridade"] = SOURCE_PRIORITY[name]
        frames.append(frame)

    points = pd.concat(frames, ignore_index=True)
    points["mes"] = pd.PeriodIndex(points["mes"], freq="M")

    unknown = set(points["marketplace"]) - set(BRANDS_BY_NAME)
    if unknown:
        raise ValueError(f"Marcas sem configuração em config.BRANDS: {sorted(unknown)}")

    return (
        points.sort_values("prioridade")
        .drop_duplicates(subset=["marketplace", "mes"], keep="last")  # maior prioridade vence
        .drop(columns="prioridade")
        .reset_index(drop=True)
    )


def build_series(points: pd.DataFrame, period: pd.PeriodIndex = PERIOD) -> pd.DataFrame:
    """Grade completa marca x mês. Interpola linearmente apenas DENTRO do intervalo conhecido.

    `limit_area="inside"` garante que nunca inventamos valores antes do primeiro
    ou depois do último ponto observado (sem extrapolação).
    """
    frames = []
    for name, group in points.groupby("marketplace"):
        series = group.set_index("mes").reindex(period)
        series["marketplace"] = name

        interpolated = series["acessos_mi"].astype(float).interpolate(limit_area="inside")
        filled = series["acessos_mi"].isna() & interpolated.notna()
        series.loc[filled, "tipo"] = "interpolado"
        series.loc[filled, "fonte"] = "linear entre vizinhos"
        series["acessos_mi"] = interpolated.round(1)

        frames.append(series.rename_axis("mes").reset_index())

    long_df = pd.concat(frames, ignore_index=True)[COLUMNS]
    missing = long_df["acessos_mi"].isna().sum()
    if missing:
        log.warning("%d células sem valor (fora do intervalo observado)", missing)
    return long_df


def to_flourish_data(long_df: pd.DataFrame) -> pd.DataFrame:
    """Formato largo: 1 linha por marca, 1 coluna por mês, + Origem e Imagem."""
    wide = long_df.pivot(index="marketplace", columns="mes", values="acessos_mi")
    wide.columns = [month_label(p) for p in wide.columns]
    wide.insert(0, "Origem", [BRANDS_BY_NAME[m].origin for m in wide.index])
    wide.insert(1, "Imagem", [icon_url(BRANDS_BY_NAME[m].domain) for m in wide.index])
    return wide.rename_axis("Marketplace").reset_index()


def to_flourish_captions() -> pd.DataFrame:
    """Aba 'Captions' do Flourish: From, To, Caption, Image."""
    rows = [
        {"From": month_label(pd.Period(a, "M")), "To": month_label(pd.Period(b, "M")),
         "Caption": text, "Image": ""}
        for a, b, text in CAPTIONS
    ]
    return pd.DataFrame(rows)


def color_overrides() -> str:
    """Texto pronto para colar em Colors > Custom overrides."""
    return "\n".join(f"{b.name}: {b.color}" for b in BRANDS)


def run() -> pd.DataFrame:
    sources = {"press": pd.read_csv(PRESS_POINTS_CSV)}
    if PDF_POINTS_CSV.exists():
        sources["pdf"] = pd.read_csv(PDF_POINTS_CSV)
    else:
        log.warning("%s não encontrado: rodando só com pontos da imprensa", PDF_POINTS_CSV.name)

    long_df = build_series(load_points(sources))

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    long_df.to_csv(PROCESSED_DIR / "series_linhagem.csv", index=False)
    to_flourish_data(long_df).to_csv(PROCESSED_DIR / "flourish_data.csv", index=False)
    to_flourish_captions().to_csv(PROCESSED_DIR / "flourish_captions.csv", index=False)
    (PROCESSED_DIR / "flourish_colors.txt").write_text(color_overrides() + "\n", encoding="utf-8")

    summary = long_df["tipo"].value_counts(dropna=False)
    log.info("Composição da série:\n%s", summary.to_string())
    return long_df


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run()


if __name__ == "__main__":
    main()

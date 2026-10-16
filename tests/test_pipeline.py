"""Testes das regras que, se quebrarem, fazem o gráfico mentir."""
import pandas as pd
import pytest

from marketplace_race.config import month_label
from marketplace_race.extract_pdf import _match_brand, _parse_header, classify_page
from marketplace_race.pipeline import build_series, load_points, to_flourish_data
from marketplace_race.validate import (
    compare_derived_vs_official,
    detect_web_collapse,
    web_app_split,
)

PERIOD = pd.period_range("2025-01", "2025-05", freq="M")


def _df(rows):
    return pd.DataFrame(rows, columns=["marketplace", "mes", "acessos_mi", "tipo", "fonte"])


def test_fonte_primaria_vence_conflito():
    press = _df([("Temu", "2025-06", 241.7, "derivado", "imprensa")])
    pdf = _df([("Temu", "2025-06", 241.9, "oficial", "pdf")])
    points = load_points({"press": press, "pdf": pdf})
    assert len(points) == 1
    assert points.iloc[0]["acessos_mi"] == 241.9
    assert points.iloc[0]["tipo"] == "oficial"


def test_interpola_somente_entre_pontos_conhecidos():
    points = load_points({"press": _df([
        ("Shein", "2025-02", 100.0, "oficial", "x"),
        ("Shein", "2025-04", 120.0, "oficial", "x"),
    ])})
    series = build_series(points, PERIOD).set_index("mes")

    assert series.loc[pd.Period("2025-03", "M"), "acessos_mi"] == 110.0
    assert series.loc[pd.Period("2025-03", "M"), "tipo"] == "interpolado"
    # Sem extrapolação nas pontas:
    assert pd.isna(series.loc[pd.Period("2025-01", "M"), "acessos_mi"])
    assert pd.isna(series.loc[pd.Period("2025-05", "M"), "acessos_mi"])


def test_marca_desconhecida_falha_alto():
    with pytest.raises(ValueError, match="sem configuração"):
        load_points({"press": _df([("Kabum", "2025-01", 10.0, "oficial", "x")])})


def test_formato_flourish_tem_colunas_esperadas():
    points = load_points({"press": _df([
        ("Temu", "2025-01", 1.0, "oficial", "x"),
        ("Temu", "2025-05", 5.0, "oficial", "x"),
    ])})
    wide = to_flourish_data(build_series(points, PERIOD))
    assert list(wide.columns[:3]) == ["Marketplace", "Origem", "Imagem"]
    assert list(wide.columns[3:]) == ["jan/25", "fev/25", "mar/25", "abr/25", "mai/25"]


def test_month_label():
    assert month_label(pd.Period("2025-07", "M")) == "jul/25"


@pytest.mark.parametrize("text, expected", [
    ("📱 Mercado Livre", "Mercado Livre"),
    ("📱 Amazon Brasil", "Amazon"),
    ("Top 10 e-commerces Amazon", None),   # amazon.com (importados), NÃO é a Amazon Brasil
    ("Mercado libre", None),               # site argentino, outra entidade
    ("Temu", "Temu"),
])
def test_match_brand(text, expected):
    assert _match_brand(text) == expected


def test_parse_header():
    months = _parse_header("jun./25 jul./25 ago./25 Trend")
    assert months == [pd.Period("2025-06", "M"), pd.Period("2025-07", "M"), pd.Period("2025-08", "M")]
    assert _parse_header("Mercado Livre 393.286.739") is None


def test_validacao_calcula_erro_percentual():
    press = _df([("Shopee", "2025-06", 258.2, "derivado", "share")])
    pdf = _df([("Shopee", "2025-06", 259.5, "oficial", "pdf")])
    report = compare_derived_vs_official(press, pdf)
    assert report.iloc[0]["erro_pct"] == pytest.approx(0.5, abs=0.01)


def test_classifica_pagina_de_apps():
    assert classify_page("🛒 Ranking dos 10 maiores apps de e-commerce") == "app"
    assert classify_page("🛒 Ranking dos 30 maiores e-commerces") == "total"


def test_detecta_colapso_de_trafego_web():
    total = _df([
        ("Temu", "2025-10", 148.6, "oficial", "pdf"),
        ("Temu", "2025-11", 30.6, "oficial", "pdf"),
    ])
    app = _df([
        ("Temu", "2025-10", 27.8, "oficial", "pdf"),
        ("Temu", "2025-11", 30.6, "oficial", "pdf"),   # total == app -> web = 0
    ])
    flagged = detect_web_collapse(web_app_split(total, app))
    assert list(flagged["mes"]) == ["2025-11"]


def test_queda_real_com_web_ativo_nao_e_sinalizada():
    total = _df([("Shopee", "2025-10", 300.0, "oficial", "p"), ("Shopee", "2025-11", 200.0, "oficial", "p")])
    app = _df([("Shopee", "2025-10", 130.0, "oficial", "p"), ("Shopee", "2025-11", 100.0, "oficial", "p")])
    assert detect_web_collapse(web_app_split(total, app)).empty

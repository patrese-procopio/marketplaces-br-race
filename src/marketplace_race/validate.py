"""Controles de qualidade dos dados.

1. Derivado x oficial: pontos que calculamos a partir de share/variação publicada
   são comparados com o valor oficial do PDF, quando os dois existem para o mesmo mês.
   Mede a confiabilidade do método usado nos meses sem dado oficial.

2. Anomalia web x app: tráfego web = total - app. Se o web cai a ~0 de um mês para
   o outro, a "queda" provavelmente é artefato de medição (domínio mudou, coleta
   falhou), não comportamento real do consumidor. O dado não é apagado: é SINALIZADO.

Uso:
    python -m marketplace_race.validate
"""
from __future__ import annotations

import pandas as pd

from .config import APP_POINTS_CSV, PDF_POINTS_CSV, PRESS_POINTS_CSV

WEB_SHARE_COLLAPSE = 0.01   # web < 1% do total...
WEB_SHARE_BEFORE = 0.20     # ...depois de ter sido > 20% no mês anterior


def compare_derived_vs_official(press: pd.DataFrame, pdf: pd.DataFrame) -> pd.DataFrame:
    derived = press[press["tipo"] == "derivado"][["marketplace", "mes", "acessos_mi", "fonte"]]
    official = pdf[["marketplace", "mes", "acessos_mi"]]

    merged = derived.merge(official, on=["marketplace", "mes"], suffixes=("_derivado", "_oficial"))
    merged["erro_pct"] = (
        (merged["acessos_mi_derivado"] - merged["acessos_mi_oficial"]).abs()
        / merged["acessos_mi_oficial"] * 100
    ).round(2)
    return merged.sort_values("erro_pct", ascending=False).reset_index(drop=True)


def web_app_split(total: pd.DataFrame, app: pd.DataFrame) -> pd.DataFrame:
    """Decompõe o total em web e app, por marca e mês."""
    split = total[["marketplace", "mes", "acessos_mi"]].merge(
        app[["marketplace", "mes", "acessos_mi"]], on=["marketplace", "mes"], suffixes=("_total", "_app")
    )
    split["acessos_mi_web"] = (split["acessos_mi_total"] - split["acessos_mi_app"]).round(1)
    split["share_web"] = (split["acessos_mi_web"] / split["acessos_mi_total"]).round(3)
    return split.sort_values(["marketplace", "mes"]).reset_index(drop=True)


def detect_web_collapse(split: pd.DataFrame) -> pd.DataFrame:
    """Meses em que o tráfego web 'zera' abruptamente: suspeita de artefato de medição."""
    s = split.copy()
    s["share_web_mes_anterior"] = s.groupby("marketplace")["share_web"].shift(1)
    flagged = s[(s["share_web"] < WEB_SHARE_COLLAPSE) & (s["share_web_mes_anterior"] > WEB_SHARE_BEFORE)]
    return flagged[["marketplace", "mes", "acessos_mi_total", "acessos_mi_app",
                    "share_web_mes_anterior", "share_web"]].reset_index(drop=True)


def main() -> None:
    pdf = pd.read_csv(PDF_POINTS_CSV)

    print("== 1. Derivado x oficial ==")
    report = compare_derived_vs_official(pd.read_csv(PRESS_POINTS_CSV), pdf)
    if report.empty:
        print("Nenhum ponto derivado coincide com meses do PDF.")
    else:
        print(report.to_string(index=False))
        print(f"Erro médio: {report['erro_pct'].mean():.2f}%  |  máximo: {report['erro_pct'].max():.2f}%")

    print("\n== 2. Anomalia web x app ==")
    if not APP_POINTS_CSV.exists():
        print("Sem tabela de apps; checagem pulada.")
        return
    flagged = detect_web_collapse(web_app_split(pdf, pd.read_csv(APP_POINTS_CSV)))
    if flagged.empty:
        print("Nenhum colapso súbito de tráfego web detectado.")
    else:
        print("ATENÇÃO: tráfego web zerou de um mês para o outro (provável artefato de medição):")
        print(flagged.to_string(index=False))


if __name__ == "__main__":
    main()

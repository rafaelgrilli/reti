import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# CONFIG
st.set_page_config(page_title="RETI DSS — SPE Ready", layout="wide")

# PARÂMETROS (mantidos)
ALIQUOTA = 0.34
PRESUNCAO = 0.32
BETA_PTF = 0.06
MULT_INDIRETO = 1.3
LAG_PTF = 3
DEPREC = 0.15
SUCESSO = 0.70

# FUNÇÕES (INALTERADAS EXCETO fator_porte)
def fator_porte(receita):
    """
    Incentivo decrescente contínuo até zero no teto do lucro presumido.
    Não há benefício marginal acima do limite estrutural.
    """

    teto_presumido = 78.0
    fator_maximo = 3.5

    if receita >= teto_presumido:
        return 0.0

    x = receita / teto_presumido

    fator = fator_maximo * (1 - x**1.7)

    return max(fator, 0.0)


def custo_relativo(incentivo):
    return incentivo / (1 + incentivo)

def adicionalidade_pd(pd_base, elasticidade, incentivo):
    return pd_base * abs(elasticidade) * custo_relativo(incentivo)

def base_reti(receita, pd_total, F, m):
    base = receita * PRESUNCAO
    base_min = base * 0.25
    base_red = max(base_min, base - (m * pd_total * F))
    return base, base_red

def difusao(n, t):
    return n / (1 + np.exp(-1.2 * (t - 3)))

# MOTOR (INALTERADO)
def simular_reti(params):

    receita = params['rec_inicial']
    intensidade_anterior = 0
    historico_pd = np.zeros(params['horizonte'] + 10)
    estoque = 0

    rows = []

    for t in range(1, params['horizonte'] + 1):

        rec_ant = receita
        receita *= (1 + params['crescimento'])
        crescimento = (receita / rec_ant) - 1

        pode = True if t <= 3 else (crescimento >= 0.10 or params['potec'] >= 0.15)

        pd_base = receita * params['intensidade_pd']
        F = fator_porte(receita)

        incentivo = params['multiplicador'] * F * ALIQUOTA

        # 🔵 transparência econômica
        subsidio_efetivo = custo_relativo(incentivo)
        fator_alavancagem = abs(params['elasticidade']) * subsidio_efetivo

        pd_extra = adicionalidade_pd(pd_base, params['elasticidade'], incentivo)
        pd_total = pd_base + pd_extra

        if pode:
            base, base_red = base_reti(receita, pd_total, F, params['multiplicador'])
            ren_unit = (base - base_red) * ALIQUOTA
        else:
            ren_unit = 0

        firmas = difusao(params['n_firmas'], t)

        ren_macro = (ren_unit * firmas) / 1000
        pd_macro = (pd_total * firmas) / 1000
        pd_extra_macro = (pd_extra * firmas) / 1000

        if t + LAG_PTF < len(historico_pd):
            historico_pd[t + LAG_PTF] = pd_extra * SUCESSO

        estoque = estoque * (1 - DEPREC) + historico_pd[t]

        intensidade = pd_total / receita
        delta_int = intensidade - intensidade_anterior
        intensidade_anterior = intensidade

        delta_ptf = BETA_PTF * delta_int

        ret_base = receita * delta_ptf * ALIQUOTA
        ret_ind = ret_base * (MULT_INDIRETO - 1)
        ret_est = estoque * 0.01

        retorno = ret_base + ret_ind + ret_est
        ret_macro = (retorno * firmas) / 1000

        rows.append({
            "Ano": t,
            "Receita": receita,
            "P&D Total": pd_total,
            "P&D Macro": pd_macro,
            "PD Extra": pd_extra,
            "PD Extra Macro": pd_extra_macro,
            "Renúncia": ren_macro,
            "Retorno": ret_macro,
            "Saldo": ret_macro - ren_macro,
            "Fator F": F,
            "Pode Usar": pode,
            "Incentivo": incentivo,
            "Subsídio Efetivo": subsidio_efetivo,
            "Fator Alavancagem": fator_alavancagem
        })

    df = pd.DataFrame(rows)
    df["Acumulado"] = df["Saldo"].cumsum()
    return df

# GOVERNANÇA (INALTERADA)
def avaliar(df, teto):
    return df["Renúncia"].max() > teto

def ajustar(params):
    novo = params.copy()
    novo["multiplicador"] *= 0.9
    novo["intensidade_pd"] *= 0.97
    return novo

def rodar_politica(params, rodadas=3):
    hist = []
    for r in range(rodadas):
        df = simular_reti(params)
        violou = avaliar(df, params["teto_lrf"])
        hist.append((r, params.copy(), df, violou))
        if violou:
            params = ajustar(params)
    return hist

def rodar_cenarios(params):
    cenarios = {
        "Conservador": {**params, "multiplicador": 1.10, "elasticidade": -0.8},
        "Base": params,
        "Agressivo": {**params, "multiplicador": 1.45, "elasticidade": -1.8}
    }
    return {k: simular_reti(v) for k, v in cenarios.items()}

# SIDEBAR
st.sidebar.title("Parâmetros RETI")

modo = st.sidebar.selectbox("Tipo de Regime", ["RETI Amplo", "RETI Deep Tech"])

params = {
    "rec_inicial": 15.0,
    "horizonte": 10,
    "n_firmas": st.sidebar.number_input("Firmas", 1000, 10000, 4500),
    "crescimento": st.sidebar.slider("Crescimento Receita", 0.05, 0.20, 0.12),
    "intensidade_pd": st.sidebar.slider("Intensidade P&D", 0.01, 0.40, 0.07),
    "elasticidade": st.sidebar.slider("Elasticidade", -2.0, -0.5, -1.2),
    "multiplicador": st.sidebar.slider("Multiplicador", 1.0, 1.5, 1.25),
    "teto_lrf": st.sidebar.slider("Envelope Fiscal do RETI", 0.5, 5.0, 2.2),
    "potec": st.sidebar.slider("PoTec", 0.0, 0.5, 0.18)
}

if modo == "RETI Deep Tech":
    params["n_firmas"] = 900
    params["intensidade_pd"] = max(params["intensidade_pd"], 0.15)
    params["elasticidade"] = max(params["elasticidade"], -1.5)

    BETA_PTF = 0.07
    DEPREC = 0.11
    SUCESSO = 0.75

hist = rodar_politica(params)
df = hist[-1][2]
cenarios = rodar_cenarios(params)

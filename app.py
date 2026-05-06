import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
st.set_page_config(page_title="RETI DSS — SPE Ready", layout="wide")

# ─────────────────────────────────────────────
# PARÂMETROS ESTRUTURAIS
# ─────────────────────────────────────────────
ALIQUOTA = 0.34
PRESUNCAO = 0.32
BETA_PTF = 0.06
MULT_INDIRETO = 1.3
LAG_PTF = 3
DEPREC = 0.15
SUCESSO = 0.70

# ─────────────────────────────────────────────
# FUNÇÕES ECONÔMICAS
# ─────────────────────────────────────────────
def fator_porte(receita):
    if receita <= 3.24:
        return 3.5
    elif receita <= 78:
        return 2.5
    elif receita <= 200:
        return 2.5 - 0.012 * (receita - 78)
    else:
        return 1.0

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

# ─────────────────────────────────────────────
# MOTOR
# ─────────────────────────────────────────────
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

        # gatilho
        if t > 3:
            pode = (crescimento >= 0.10 or params['potec'] >= 0.15)
        else:
            pode = True

        # P&D
        pd_base = receita * params['intensidade_pd']
        F = fator_porte(receita)

        incentivo = params['multiplicador'] * F * ALIQUOTA
        pd_extra = adicionalidade_pd(pd_base, params['elasticidade'], incentivo)
        pd_total = pd_base + pd_extra

        # base fiscal
        if pode:
            base, base_red = base_reti(receita, pd_total, F, params['multiplicador'])
            ren_unit = (base - base_red) * ALIQUOTA
        else:
            ren_unit = 0

        firmas = difusao(params['n_firmas'], t)
        ren_macro = (ren_unit * firmas) / 1000

        # conhecimento
        if t + LAG_PTF < len(historico_pd):
            historico_pd[t + LAG_PTF] = pd_extra * SUCESSO

        estoque = estoque * (1 - DEPREC) + historico_pd[t]

        # PTF (delta)
        intensidade = pd_total / receita
        delta_int = intensidade - intensidade_anterior
        intensidade_anterior = intensidade

        delta_ptf = BETA_PTF * delta_int

        # retorno
        ret_base = receita * delta_ptf * ALIQUOTA
        ret_ind = ret_base * (MULT_INDIRETO - 1)
        ret_est = estoque * 0.01

        retorno = ret_base + ret_ind + ret_est
        ret_macro = (retorno * firmas) / 1000

        rows.append({
            "Ano": t,
            "Renúncia": ren_macro,
            "Retorno": ret_macro,
            "Saldo": ret_macro - ren_macro,
            "F": F,
            "Pode_Usar": pode
        })

    df = pd.DataFrame(rows)
    df["Acumulado"] = df["Saldo"].cumsum()

    return df


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


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
st.sidebar.title("Parâmetros RETI")

n_firmas = st.sidebar.number_input("Firmas", 1000, 10000, 4500)
crescimento = st.sidebar.slider("Crescimento Receita", 0.05, 0.20, 0.12)
int_pd = st.sidebar.slider("Intensidade P&D", 0.01, 0.40, 0.07)
elasticidade = st.sidebar.slider("Elasticidade", -2.0, -0.5, -1.2)
multiplicador = st.sidebar.slider("Multiplicador", 1.0, 1.5, 1.25)
teto = st.sidebar.slider("Teto LRF", 0.5, 5.0, 2.2)
potec = st.sidebar.slider("PoTec", 0.0, 0.5, 0.18)

params = {
    "rec_inicial": 15.0,
    "horizonte": 10,
    "n_firmas": n_firmas,
    "crescimento": crescimento,
    "intensidade_pd": int_pd,
    "elasticidade": elasticidade,
    "multiplicador": multiplicador,
    "teto_lrf": teto,
    "potec": potec
}

# ─────────────────────────────────────────────
# EXECUÇÃO
# ─────────────────────────────────────────────
hist = rodar_politica(params)

# última rodada
df = hist[-1][2]

# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────
st.title("RETI DSS — Modelo Institucional")

k1, k2, k3 = st.columns(3)

k1.metric("Custo Total", f"{df['Renúncia'].sum():.2f} Bi")
k2.metric("Retorno Total", f"{df['Retorno'].sum():.2f} Bi")

payback = df[df["Acumulado"] > 0]
k3.metric("Payback", payback["Ano"].min() if not payback.empty else "N/A")

# gráfico
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["Ano"], y=df["Renúncia"], name="Custo"))
fig.add_trace(go.Scatter(x=df["Ano"], y=df["Retorno"], name="Retorno"))

st.plotly_chart(fig, use_container_width=True)

fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=df["Ano"], y=df["Acumulado"], fill='tozeroy'))

st.plotly_chart(fig2, use_container_width=True)

st.dataframe(df)

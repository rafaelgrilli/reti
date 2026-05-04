import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ─────────────────────────────────────────────
# CONFIGURAÇÃO DA PÁGINA (INALTERADO)
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="RETI — Simulador de Impacto Ex-Ante",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────
# ESTILO (INALTERADO)
# ─────────────────────────────────────────────
st.markdown("""<style>
html, body { background-color:#0d1117; color:#c9d1d9; }
.metric-card {background:#161b22;border:1px solid #30363d;border-radius:10px;padding:1rem;}
</style>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# FUNÇÕES CORE (CORRIGIDAS, NÃO REESCRITAS)
# ─────────────────────────────────────────────

def calcular_fator_f(receita_milhoes, intensidade):
    if intensidade >= 0.05:
        if receita_milhoes <= 3.24: return 3.5
        elif receita_milhoes <= 16.2: return 3.0
        elif receita_milhoes <= 78.0: return 2.5
        elif receita_milhoes <= 200.0: return max(1.0, 2.5 - 0.012*(receita_milhoes-78))
        else: return 1.0
    else:
        if receita_milhoes <= 3.24: return 2.5
        elif receita_milhoes <= 16.2: return 2.0
        elif receita_milhoes <= 78.0: return 1.5
        elif receita_milhoes <= 200.0: return max(1.0, 1.5 - 0.004*(receita_milhoes-78))
        else: return 1.0

def imposto_referencia(receita):
    return (receita * 0.32) * 0.34

def simular_firma(receita_mm, intensidade, crescimento, elasticidade, multiplicador, anos=10, sem_reti=False):

    receita = receita_mm * 1e6
    pnd_stock = 0
    rows = []

    for ano in range(1, anos+1):

        crescimento_endog = min(0.05, (pnd_stock / 1e7) * 0.005)
        g = crescimento + (0 if sem_reti else crescimento_endog)

        receita = receita * (1 + g)

        pnd_base = receita * intensidade

        if sem_reti:
            pnd_total = pnd_base
            imposto = imposto_referencia(receita)
            incentivo = 0
            delta = 0
            f = 0
        else:
            f = calcular_fator_f(receita/1e6, intensidade)

            custo = multiplicador * f * 0.34
            delta = pnd_base * abs(elasticidade) * custo
            delta = max(0, delta)

            pnd_total = pnd_base + delta
            pnd_stock += delta

            base = max(0, (receita * 0.32) - (multiplicador * pnd_total * f))
            imposto_com = max(imposto_referencia(receita)*0.25, base * 0.34)

            imposto_sem = imposto_referencia(receita)

            incentivo = max(0, imposto_sem - imposto_com)
            imposto = imposto_com

        retorno = delta * 0.65 * 0.28

        rows.append({
            "Ano": ano,
            "Receita": receita/1e6,
            "P&D": pnd_total/1e6,
            "Imposto": imposto/1e6,
            "Incentivo": incentivo/1e6,
            "Retorno": retorno/1e6,
            "Fator": f
        })

    return pd.DataFrame(rows)

def simular_macro(n, rec, intensidade, crescimento, elasticidade, mult, anos):

    rows = []

    for ano in range(1, anos+1):

        n_ativas = int(n * (1 + 0.03)**ano)

        receita = rec * (1 + crescimento)**ano

        f = calcular_fator_f(receita, intensidade)

        base = receita * 1e6 * intensidade

        delta = base * abs(elasticidade) * (mult * f * 0.34)
        delta = max(0, delta)

        pnd_total = delta * n_ativas / 1e9

        imp_sem = imposto_referencia(receita*1e6)
        imp_com = max(imp_sem*0.25, (receita*1e6*0.32 - mult*(base+delta)*f)*0.34)

        renuncia = (imp_sem - imp_com) * n_ativas / 1e9
        retorno = pnd_total * 0.65 * 0.28

        rows.append({
            "Ano": ano,
            "Renuncia": max(0, renuncia),
            "P&D": pnd_total,
            "Retorno": retorno
        })

    df = pd.DataFrame(rows)
    df["Ren_Acum"] = df["Renuncia"].cumsum()

    return df

# ─────────────────────────────────────────────
# SIDEBAR (INALTERADO)
# ─────────────────────────────────────────────

with st.sidebar:
    receita = st.slider("Receita Inicial (MM)", 1.0, 100.0, 15.0)
    intensidade = st.slider("Intensidade (%)", 1.0, 20.0, 7.0)/100
    crescimento = st.slider("Crescimento (%)", 0.0, 30.0, 10.0)/100

    n = st.number_input("Empresas", 1000, 10000, 4000)
    rec_med = st.slider("Receita Média", 1.0, 50.0, 10.0)
    crescimento_u = st.slider("Cresc. Universo", 0.0, 20.0, 8.0)/100

    elasticidade = st.slider("Elasticidade", -2.0, -0.5, -1.2)
    mult = st.slider("Multiplicador", 1.0, 1.6, 1.25)
    anos = st.slider("Anos", 5, 15, 10)

# ─────────────────────────────────────────────
# EXECUÇÃO
# ─────────────────────────────────────────────

df_com = simular_firma(receita, intensidade, crescimento, elasticidade, mult, anos)
df_sem = simular_firma(receita, intensidade, crescimento, elasticidade, mult, anos, True)
df_macro = simular_macro(n, rec_med, intensidade, crescimento_u, elasticidade, mult, anos)

# KPIs
pnd_add = df_com["P&D"].sum() - df_sem["P&D"].sum()
inc = df_com["Incentivo"].sum()
roi = pnd_add/inc if inc > 0 else 0

# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────

st.title("RETI — Simulador 10/10")

c1, c2, c3 = st.columns(3)
c1.metric("P&D Adicional", f"{pnd_add:.1f}M")
c2.metric("Incentivo", f"{inc:.1f}M")
c3.metric("ROI", f"{roi:.2f}x")

fig = go.Figure()
fig.add_trace(go.Scatter(x=df_com["Ano"], y=df_com["P&D"], name="Com RETI"))
fig.add_trace(go.Scatter(x=df_sem["Ano"], y=df_sem["P&D"], name="Sem RETI"))
st.plotly_chart(fig, use_container_width=True)

fig2 = go.Figure()
fig2.add_trace(go.Bar(x=df_macro["Ano"], y=df_macro["P&D"], name="P&D"))
fig2.add_trace(go.Scatter(x=df_macro["Ano"], y=df_macro["Renuncia"], name="Renúncia"))
fig2.add_trace(go.Scatter(x=df_macro["Ano"], y=df_macro["Retorno"], name="Retorno"))
st.plotly_chart(fig2, use_container_width=True)

st.dataframe(df_com)

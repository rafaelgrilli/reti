import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
st.set_page_config(page_title="RETI — Simulador", layout="wide")

# ─────────────────────────────────────────────
# CORE ECONÔMICO
# ─────────────────────────────────────────────

def fator_f(r, i):
    if i >= 0.05:
        if r <= 3.24: return 3.5
        elif r <= 16.2: return 3.0
        elif r <= 78: return 2.5
        else: return max(1, 2.5 - 0.012*(r-78))
    else:
        if r <= 3.24: return 2.5
        elif r <= 16.2: return 2.0
        elif r <= 78: return 1.5
        else: return max(1, 1.5 - 0.004*(r-78))

def imposto_ref(rec):
    return (rec * 0.32) * 0.34

# ─────────────────────────────────────────────
# FIRMA COM ESTOQUE DE CRÉDITO
# ─────────────────────────────────────────────

def sim_firma(rec0, i, g, e, m, anos, sem=False):
    rec = rec0 * 1e6
    stock_pnd = 0
    
    # NOVO: estoque de crédito (FIFO 5 anos)
    estoque_credito = [0]*5  

    out = []

    for t in range(1, anos+1):
        g_end = min(0.05, (stock_pnd/1e7)*0.005)
        rec *= (1 + g + (0 if sem else g_end))

        base = rec * i

        if sem:
            total = base
            imp = imposto_ref(rec)
            inc = 0
            delta = 0
            f = 0
            uso_credito = 0

        else:
            f = fator_f(rec/1e6, i)
            custo = m * f * 0.34
            delta = max(0, base * abs(e) * custo)

            total = base + delta
            stock_pnd += delta

            # ───────── BASE RETI
            base_reti = max(0, rec*0.32 - m*total*f)
            imposto_bruto = base_reti * 0.34
            imposto_ref_val = imposto_ref(rec)

            # ───────── CRÉDITO GERADO (diferença)
            credito_gerado = max(0, imposto_ref_val - imposto_bruto)

            # adiciona no estoque (posição 0 = mais novo)
            estoque_credito.insert(0, credito_gerado)
            estoque_credito.pop()

            # ───────── USO DE CRÉDITO (TRAVA 50%)
            imposto_devido = max(imposto_bruto, imposto_ref_val*0.25)
            limite_uso = imposto_devido * 0.5

            uso_credito = 0

            # FIFO: usa créditos mais antigos primeiro
            for idx in range(4, -1, -1):
                disponivel = estoque_credito[idx]
                usar = min(disponivel, limite_uso - uso_credito)

                estoque_credito[idx] -= usar
                uso_credito += usar

                if uso_credito >= limite_uso:
                    break

            imp = imposto_devido - uso_credito
            inc = uso_credito  # incentivo agora é o USO efetivo

        retorno = delta * 0.65 * 0.28

        out.append([
            t,
            rec/1e6,
            total/1e6,
            imp/1e6,
            inc/1e6,
            retorno/1e6,
            f,
            sum(estoque_credito)/1e6
        ])

    return pd.DataFrame(out, columns=[
        "Ano","Receita","P&D","Imposto","Incentivo","Retorno","Fator","Estoque Crédito"
    ])

# ─────────────────────────────────────────────
# MACRO (APROXIMAÇÃO COM TRAVA)
# ─────────────────────────────────────────────

def sim_macro(n, rec, i, g, e, m, anos):
    rows = []
    estoque = 0

    for t in range(1, anos+1):
        n_t = int(n * (1.03**t))
        rec_t = rec * (1+g)**t

        f = fator_f(rec_t, i)

        base = rec_t*1e6*i
        delta = max(0, base * abs(e) * (m*f*0.34))

        imp_ref_val = imposto_ref(rec_t*1e6)
        base_reti = max(0, rec_t*1e6*0.32 - m*(base+delta)*f)
        imp_bruto = base_reti * 0.34

        credito_gerado = max(0, imp_ref_val - imp_bruto)

        estoque += credito_gerado*n_t/1e9

        # uso limitado
        uso = min(estoque, imp_ref_val*n_t/1e9 * 0.5)
        estoque -= uso

        ren = uso
        pnd = delta*n_t/1e9
        ret = pnd * 0.65 * 0.28

        rows.append([t, n_t, ren, pnd, ret, estoque])

    df = pd.DataFrame(rows, columns=[
        "Ano","Firmas","Renúncia","P&D","Retorno","Estoque"
    ])

    df["Renúncia Acum"] = df["Renúncia"].cumsum()
    df["Retorno Acum"] = df["Retorno"].cumsum()

    return df

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────

with st.sidebar:
    st.header("Parâmetros da Firma")
    rec = st.slider("Receita Inicial (R$ MM)",1.0,100.0,15.0)
    i = st.slider("Intensidade P&D (%)",1.0,20.0,7.0)/100
    g = st.slider("Crescimento (%)",0.0,20.0,10.0)/100

    st.header("Macro")
    n = st.number_input("Firmas",1000,10000,4000)
    rec_m = st.slider("Receita Média",1.0,50.0,10.0)
    g_m = st.slider("Crescimento Universo",0.0,15.0,8.0)/100

    st.header("Política")
    e = st.slider("Elasticidade",-2.0,-0.5,-1.2)
    m = st.slider("Multiplicador",1.0,1.6,1.25)
    anos = st.slider("Horizonte",5,15,10)

# ─────────────────────────────────────────────
# EXECUÇÃO
# ─────────────────────────────────────────────

df_c = sim_firma(rec,i,g,e,m,anos)
df_s = sim_firma(rec,i,g,e,m,anos,True)
df_m = sim_macro(n,rec_m,i,g_m,e,m,anos)

pnd_add = df_c["P&D"].sum() - df_s["P&D"].sum()
inc = df_c["Incentivo"].sum()
roi = pnd_add/inc if inc>0 else 0

# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────

tab1, tab2 = st.tabs(["📈 Firma","🏛️ Fiscal"])

with tab1:
    st.subheader("Firma com dinâmica de crédito")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_c["Ano"], y=df_c["P&D"], name="P&D"))
    fig.add_trace(go.Scatter(x=df_c["Ano"], y=df_c["Estoque Crédito"], name="Estoque Crédito"))
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(df_c)

with tab2:
    st.subheader("Macro com dinâmica de estoque")

    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_m["Ano"], y=df_m["P&D"], name="P&D"))
    fig.add_trace(go.Scatter(x=df_m["Ano"], y=df_m["Renúncia"], name="Renúncia"))
    fig.add_trace(go.Scatter(x=df_m["Ano"], y=df_m["Estoque"], name="Passivo Fiscal"))
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(df_m)

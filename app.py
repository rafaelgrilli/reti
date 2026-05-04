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
# FIRMA (mantida)
# ─────────────────────────────────────────────

def sim_firma(rec0, i, g, e, m, anos, sem=False):
    rec = rec0 * 1e6
    stock = 0
    out = []

    for t in range(1, anos+1):
        g_end = min(0.05, (stock/1e7)*0.005)
        rec *= (1 + g + (0 if sem else g_end))

        base = rec * i

        if sem:
            total = base
            imp = imposto_ref(rec)
            inc = 0
            delta = 0
            f = 0
        else:
            f = fator_f(rec/1e6, i)
            custo = m * f * 0.34
            delta = max(0, base * abs(e) * custo)

            total = base + delta
            stock += delta

            base_reti = max(0, rec*0.32 - m*total*f)
            imp = max(imposto_ref(rec)*0.25, base_reti*0.34)
            inc = max(0, imposto_ref(rec) - imp)

        retorno = delta * 0.65 * 0.28

        out.append([t, rec/1e6, total/1e6, imp/1e6, inc/1e6, retorno/1e6, f])

    return pd.DataFrame(out, columns=[
        "Ano","Receita","P&D","Imposto","Incentivo","Retorno","Fator"
    ])

# ─────────────────────────────────────────────
# MACRO COM GOVERNANÇA (UPGRADE REAL)
# ─────────────────────────────────────────────

def sim_macro(n, rec, i, g, e, m, anos, modo="completo"):

    rows = []
    estoque_credito = 0
    retorno_lag = [0,0]  # delay de 2 anos

    teto = 2.2  # R$ bi

    for t in range(1, anos+1):

        n_t = int(n * (1.03**t))
        rec_t = rec * (1+g)**t

        f = fator_f(rec_t, i)

        base = rec_t*1e6*i
        delta = max(0, base * abs(e) * (m*f*0.34))

        imp_sem = imposto_ref(rec_t*1e6)
        imp_com = max(imp_sem*0.25, (rec_t*1e6*0.32 - m*(base+delta)*f)*0.34)

        ren_bruta = max(0, (imp_sem - imp_com)*n_t/1e9)
        pnd = delta*n_t/1e9

        # ─── GOVERNANÇA ───
        if modo == "sem":
            ren = ren_bruta
            retorno = pnd * 0.65 * 0.28

        else:
            # Condicionalidade (proxy simples)
            crescimento = g
            prob = min(1, crescimento / 0.10)

            credito_gerado = ren_bruta
            estoque_credito += credito_gerado

            credito_usado = estoque_credito * prob * 0.3
            estoque_credito -= credito_usado

            # Teto fiscal
            ren = min(ren_bruta, teto)

            # Retorno com defasagem
            retorno_lag.append(pnd * 0.65 * 0.28)
            retorno = retorno_lag.pop(0)

        rows.append([t, n_t, ren, pnd, retorno])

    df = pd.DataFrame(rows, columns=["Ano","Firmas","Renúncia","P&D","Retorno"])
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

    modo = st.radio("Cenário de Política",
        ["Sem Governança","RETI Completo"])

# ─────────────────────────────────────────────
# EXECUÇÃO
# ─────────────────────────────────────────────

df_c = sim_firma(rec,i,g,e,m,anos)
df_s = sim_firma(rec,i,g,e,m,anos,True)

modo_modelo = "sem" if modo == "Sem Governança" else "completo"
df_m = sim_macro(n,rec_m,i,g_m,e,m,anos,modo_modelo)

# KPIs
pnd_add = df_c["P&D"].sum() - df_s["P&D"].sum()
inc = df_c["Incentivo"].sum()
roi = pnd_add/inc if inc>0 else 0

# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(["📈 Firma","🏛️ Fiscal","🔍 Diagnóstico"])

# FIRMA
with tab1:
    st.subheader("Impacto Microeconômico")

    c1,c2,c3 = st.columns(3)
    c1.metric("P&D Adicional",f"{pnd_add:.1f}M")
    c2.metric("Incentivo",f"{inc:.1f}M")
    c3.metric("ROI",f"{roi:.2f}x")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_c["Ano"], y=df_c["P&D"], name="Com RETI"))
    fig.add_trace(go.Scatter(x=df_s["Ano"], y=df_s["P&D"], name="Sem RETI"))
    fig.update_layout(title="Investimento em P&D (Firma)")
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(df_c)

# MACRO
with tab2:
    st.subheader("Impacto Fiscal Agregado")

    c1,c2,c3 = st.columns(3)
    c1.metric("Renúncia Total",f"{df_m['Renúncia Acum'].iloc[-1]:.2f} Bi")
    c2.metric("P&D Induzido",f"{df_m['P&D'].sum():.2f} Bi")
    c3.metric("Retorno Fiscal",f"{df_m['Retorno'].sum():.2f} Bi")

    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_m["Ano"], y=df_m["P&D"], name="P&D"))
    fig.add_trace(go.Scatter(x=df_m["Ano"], y=df_m["Renúncia"], name="Renúncia"))
    fig.add_trace(go.Scatter(x=df_m["Ano"], y=df_m["Retorno"], name="Retorno"))
    fig.update_layout(title="Fluxo Fiscal do Programa")
    st.plotly_chart(fig, use_container_width=True)

# DIAGNÓSTICO
with tab3:

    ren_total = df_m["Renúncia"].sum()
    ret_total = df_m["Retorno"].sum()
    pnd_total = df_m["P&D"].sum()

    ratio = ret_total / ren_total if ren_total > 0 else 0

    st.subheader("Diagnóstico Estratégico")

    if modo == "Sem Governança":
        st.error("Sem mecanismos de controle, o RETI gera trajetória fiscal explosiva.")
    else:
        st.success("Com governança, o risco fiscal é limitado por construção (teto + condicionalidade).")

    if ratio > 1:
        st.success("Programa sustentável")
    elif ratio > 0.5:
        st.warning("Programa viável com ajustes")
    else:
        st.error("Baixa sustentabilidade fiscal")

    st.markdown("### Leitura Econômica")

    st.markdown(f"""
- Retorno fiscal cobre **{ratio:.2f}x** da renúncia  
- P&D total induzido: **R$ {pnd_total:.2f} bi**  
- Renúncia controlada: **R$ {ren_total:.2f} bi**
    """)

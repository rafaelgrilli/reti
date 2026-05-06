import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# 1. DESIGN SYSTEM
st.set_page_config(page_title="RETI Intelligence v12.6", layout="wide")

st.markdown("""
    <style>
        .stApp { background-color: #0A0E1A; color: #FFFFFF; }
        [data-testid="stSidebar"] { background-color: #0F1525 !important; border-right: 1px solid #1E2A45; }
        [data-testid="stSidebar"] * { color: #FFFFFF !important; }
        .stButton > button { width: 100%; background-color: #1E293B !important; border: 1px solid #3E4A67 !important; }
        .stButton > button:hover { border-color: #C9A84C !important; color: #C9A84C !important; }
        header { visibility: hidden; }
    </style>
    """, unsafe_allow_html=True)

# 2. MOTOR DE CÁLCULO
def run_reti_engine(p):
    ALIQUOTA, PRESUNCAO, MULT_INDIRETO = 0.34, 0.32, 1.3
    LAG, DEPREC, SUCESSO = 3, 0.15, 0.70
    rows = []
    estoque_conhecimento, receita = 0, p['rec_inicial']
    historico_maturacao = np.zeros(p['horizonte'] + LAG + 10)
    violation_last_year, m_dinamico, f_penalidade = False, p['mult_base'], 0

    for t in range(1, p['horizonte'] + 1):
        rec_ant, receita = receita, receita * (1 + p['crescimento'])
        if violation_last_year:
            if m_dinamico > 1.0: m_dinamico = max(1.0, m_dinamico - 0.15)
            else: f_penalidade = 0.5
        
        if receita <= 3.24: f_base = 3.5
        elif receita <= 78.0: f_base = 2.5
        elif receita <= 200.0: f_base = max(1.0, 2.5 - 0.012 * (receita - 78.0))
        else: f_base = 1.0
        f = max(1.0, f_base - f_penalidade)

        pd_original = receita * p['intensidade_pd']
        pd_adicional = pd_original * abs(p['elasticidade']) * (m_dinamico * f * ALIQUOTA)
        pd_total = pd_original + pd_adicional
        
        if t + LAG < len(historico_maturacao): historico_maturacao[t + LAG] = pd_adicional * SUCESSO
        estoque_conhecimento = estoque_conhecimento * (1 - DEPREC) + historico_maturacao[t]
        ganho_ptf = (estoque_conhecimento / receita) * p['beta_ptf'] if receita > 0 else 0
        retorno_total = (receita * ganho_ptf) * ALIQUOTA * MULT_INDIRETO

        pode_usar = True if t <= 3 else ((receita/rec_ant - 1 >= 0.10) or (p['potec'] >= 15))

        if p['regime'] == "Lucro Presumido":
            base_orig = receita * PRESUNCAO
            base_red = max(base_orig * 0.25, base_orig - (m_dinamico * pd_total * f))
            renuncia_unitaria = (base_orig - base_red) * ALIQUOTA if pode_usar else 0
        else:
            if p['intensidade_pd'] >= 0.15 and pode_usar:
                prog = min(p['intensidade_pd'], 0.30) / 0.30
                renuncia_unitaria = pd_total * 0.40 * prog * f
            else: renuncia_unitaria = 0

        firmas = p['n_firmas'] / (1 + np.exp(-1.2 * (t - 3)))
        ren_macro, ret_macro = (renuncia_unitaria * firmas) / 1000, (retorno_total * firmas) / 1000
        violation_last_year = ren_macro > p['teto_lrf']
        rows.append({"Ano": t, "Renúncia": ren_macro, "Retorno": ret_macro, "Saldo": ret_macro - ren_macro})

    return pd.DataFrame(rows)

# 3. INTERFACE
if 'm_val' not in st.session_state: st.session_state.m_val = 1.25
if 'e_val' not in st.session_state: st.session_state.e_val = -1.27

def set_params(m, e):
    st.session_state.m_val, st.session_state.e_val = m, e

with st.sidebar:
    st.title("🛡️ Parâmetros RETI")
    n_firmas = st.number_input("Universo de Firmas", value=4500, step=100)
    regime = st.selectbox("Regime Tributário", ["Lucro Presumido", "RETI-SME"])
    t_lrf = st.slider("Teto LRF (R$ Bi/ano)", 0.5, 5.0, 2.2)
    
    st.subheader("🎯 Cenários")
    c1, c2, c3 = st.columns(3)
    c1.button("🟢 Cons.", on_click=set_params, args=(1.10, -0.80))
    c2.button("🟡 Mod.", on_click=set_params, args=(1.25, -1.27))
    c3.button("🟠 Agres.", on_click=set_params, args=(1.45, -1.80))

    st.subheader("📈 Ajustes")
    m_ui = st.slider("M", 1.0, 1.5, st.session_state.m_val, key="m_s")
    e_ui = st.slider("ε", -2.0, -0.5, st.session_state.e_val, key="e_s")
    st.session_state.m_val, st.session_state.e_val = m_ui, e_ui

    i_pd = st.slider("Intensidade P&D", 0.01, 0.40, 0.07)
    p_tec = st.slider("PoTec (%)", 0, 50, 18)
    b_ptf = st.slider("β (PTF)", 0.05, 0.12, 0.06)

df = run_reti_engine({
    "regime": regime, "n_firmas": n_firmas, "rec_inicial": 15.0, "intensidade_pd": i_pd,
    "crescimento": 0.12, "beta_ptf": b_ptf, "horizonte": 10, "potec": p_tec,
    "teto_lrf": t_lrf, "mult_base": st.session_state.m_val, "elasticidade": st.session_state.e_val
})

st.title("🛡️ RETI Intelligence DSS")
st.caption(f"Configuração: M={st.session_state.m_val:.2f} | ε={st.session_state.e_val:.2f}")

k1, k2, k3, k4 = st.columns(4)
total_ren, total_ret = df["Renúncia"].sum(), df["Retorno"].sum()
pb_check = df[df["Saldo"].cumsum() > 0]
payback = pb_check["Ano"].min() if not pb_check.empty else "N/A"

k1.metric("Custo Total (10a)", f"R$ {total_ren:.2f} Bi")
k2.metric("Retorno PIB (PTF)", f"R$ {total_ret:.2f} Bi")
k3.metric("Payback Fiscal", f"Ano {payback}")
k4.metric("Status LRF", "CONFORME" if df["Renúncia"].max() <= t_lrf else "LIMITADO")

ca, cb = st.columns(2)
with ca:
    f1 = go.Figure()
    f1.add_trace(go.Scatter(x=df["Ano"], y=df["Renúncia"], name="Custo", line=dict(color='#EF4444', width=3)))
    f1.add_trace(go.Scatter(x=df["Ano"], y=df["Retorno"], name="Retorno", line=dict(color='#2BBFCE', width=3)))
    f1.update_layout(template="plotly_dark", height=350, margin=dict(l=10,r=10,t=30,b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(f1, use_container_width=True)
with cb:
    df["Acumulado"] = (df["Retorno"] - df["Renúncia"]).cumsum()
    f2 = go.Figure()
    f2.add_trace(go.Scatter(x=df["Ano"], y=df["Acumulado"], name="ROI", fill='tozeroy', line=dict(color='#10B981', width=3)))
    f2.update_layout(template="plotly_dark", height=350, margin=dict(l=10,r=10,t=30,b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(f2, use_container_width=True)

with st.expander("🔍 Memória de Cálculo Detalhada"):
    st.dataframe(df.style.format(precision=3), use_container_width=True)

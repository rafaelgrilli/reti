import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────────────────────
# 1. DESIGN SYSTEM (UX PRESERVADO v12.7)
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="RETI Intelligence v12.7", layout="wide")

st.markdown("""
    <style>
        .stApp { background-color: #0A0E1A; color: #FFFFFF; }
        [data-testid="stSidebar"] {
            background-color: #0F1525 !important;
            border-right: 1px solid #1E2A45;
        }
        [data-testid="stSidebar"] label, 
        [data-testid="stSidebar"] .stMarkdown p,
        [data-testid="stSidebar"] div[data-testid="stWidgetLabel"] p,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
            color: #FFFFFF !important;
            font-weight: 600 !important;
        }
        div[data-baseweb="select"] > div {
            background-color: #1E293B !important;
            color: #FFFFFF !important;
            border: 1px solid #3E4A67 !important;
        }
        [data-testid="stMetric"] {
            background-color: #161C2D !important;
            border: 1px solid #1E2A45 !important;
            padding: 15px !important;
            border-radius: 8px !important;
        }
        [data-testid="stMetricLabel"] { color: #94A3B8 !important; }
        [data-testid="stMetricValue"] { color: #FFFFFF !important; }
        .stButton > button {
            width: 100%;
            background-color: #1E293B !important;
            color: #FFFFFF !important;
            border: 1px solid #3E4A67 !important;
        }
        .stButton > button:hover { border-color: #C9A84C !important; }
        header { visibility: hidden; }
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# 2. MOTOR DE CÁLCULO (IMPLEMENTAÇÃO DE PENALIDADE SUAVE)
# ─────────────────────────────────────────────────────────────

def run_reti_engine(p):
    ALIQUOTA, PRESUNCAO, MULT_INDIRETO = 0.34, 0.32, 1.3
    LAG, DEPREC, SUCESSO = 3, 0.15, 0.70
    
    rows = []
    estoque_conhecimento = 0
    historico_maturacao = np.zeros(p['horizonte'] + LAG + 10)
    receita = p['rec_inicial']
    
    # Variáveis de controle de penalidade (agora contínuas)
    f_penalidade = 0
    
    for t in range(1, p['horizonte'] + 1):
        rec_ant = receita
        receita *= (1 + p['crescimento'])
        
        # Lógica de Penalidade Suave (Opção 1 do Feedback)
        # O m_efetivo agora é uma função do excesso em relação ao teto, evitando o "clamp" binário
        m_efetivo = p['mult_base'] * (1 - 0.25 * f_penalidade) 
        
        if receita <= 3.24: f_base = 3.5
        elif receita <= 78.0: f_base = 2.5
        elif receita <= 200.0: f_base = max(1.0, 2.5 - 0.012 * (receita - 78.0))
        else: f_base = 1.0
        
        f_ajustado = max(1.0, f_base - f_penalidade)

        pd_original = receita * p['intensidade_pd']
        pd_adicional = pd_original * abs(p['elasticidade']) * (m_efetivo * f_ajustado * ALIQUOTA)
        pd_total = pd_original + pd_adicional
        
        if t + LAG < len(historico_maturacao): 
            historico_maturacao[t + LAG] = pd_adicional * SUCESSO
        estoque_conhecimento = estoque_conhecimento * (1 - DEPREC) + historico_maturacao[t]
        
        ganho_ptf = (estoque_conhecimento / receita) * p['beta_ptf'] if receita > 0 else 0
        retorno_total = (receita * ganho_ptf) * ALIQUOTA * MULT_INDIRETO
        pode_usar = True if t <= 3 else ((receita/rec_ant - 1 >= 0.10) or (p['potec'] >= 15))

        if p['regime'] == "Lucro Presumido":
            base_orig = receita * PRESUNCAO
            base_red = max(base_orig * 0.25, base_orig - (m_efetivo * pd_total * f_ajustado))
            ren_unitaria = (base_orig - base_red) * ALIQUOTA if pode_usar else 0
        else:
            if p['intensidade_pd'] >= 0.15 and pode_usar:
                prog = min(p['intensidade_pd'], 0.30) / 0.30
                ren_unitaria = pd_total * 0.40 * prog * f_ajustado
            else: ren_unitaria = 0

        firmas = p['n_firmas'] / (1 + np.exp(-1.2 * (t - 3)))
        ren_macro = (ren_unitaria * firmas) / 1000
        ret_macro = (retorno_total * firmas) / 1000
        
        # Diagnóstico de Excesso LRF para o próximo ciclo
        excesso = max(0, ren_macro - p['teto_lrf'])
        f_penalidade = min(0.5, excesso / p['teto_lrf']) if p['teto_lrf'] > 0 else 0

        rows.append({
            "Ano": t, "Renúncia": ren_macro, "Retorno": ret_macro, 
            "Saldo": ret_macro - ren_macro, "M_Efetivo": m_efetivo,
            "Penalidade_LRF": f_penalidade
        })

    df_res = pd.DataFrame(rows)
    df_res["Acumulado"] = df_res["Saldo"].cumsum()
    return df_res

# ─────────────────────────────────────────────────────────────
# 3. CONTROLE DE ESTADO
# ─────────────────────────────────────────────────────────────

if 'm_val' not in st.session_state: st.session_state.m_val = 1.25
if 'e_val' not in st.session_state: st.session_state.e_val = -1.27

with st.sidebar:
    st.title("🛡️ Parâmetros RETI")
    
    st.subheader("📊 Escopo do Modelo")
    n_firmas = st.number_input("Universo de Firmas", value=4500, step=100)
    regime = st.selectbox("Regime Tributário", ["Lucro Presumido", "RETI-SME"])
    
    st.divider()
    st.subheader("🎯 Cenários de Palatabilidade")
    c1, c2, c3 = st.columns(3)
    if c1.button("🟢 Cons."): 
        st.session_state.m_val = 1.10; st.session_state.e_val = -0.80; st.rerun()
    if c2.button("🟡 Mod."): 
        st.session_state.m_val = 1.25; st.session_state.e_val = -1.27; st.rerun()
    if c3.button("🟠 Agres."): 
        st.session_state.m_val = 1.45; st.session_state.e_val = -1.80; st.rerun()

    st.divider()
    st.subheader("📈 Ajustes Técnicos")
    m_input = st.slider("Multiplicador M", 1.0, 1.5, value=st.session_state.m_val)
    e_input = st.slider("Elasticidade ε", -2.0, -0.5, value=st.session_state.e_val)
    
    st.session_state.m_val = m_input
    st.session_state.e_val = e_input

    t_lrf = st.slider("Teto LRF (R$ Bi/ano)", 0.5, 5.0, 2.2)
    i_pd = st.slider("Intensidade P&D", 0.01, 0.40, 0.07)
    p_tec = st.slider("PoTec (%)", 0, 50, 18)
    b_ptf = st.slider("β (Elasticidade PTF)", 0.05, 0.12, 0.06)

# EXECUÇÃO
df = run_reti_engine({
    "regime": regime, "n_firmas": n_firmas, "rec_inicial": 15.0, "intensidade_pd": i_pd,
    "crescimento": 0.12, "beta_ptf": b_ptf, "horizonte": 10, "potec": p_tec,
    "teto_lrf": t_lrf, "mult_base": st.session_state.m_val, "elasticidade": st.session_state.e_val
})

# ─────────────────────────────────────────────────────────────
# 4. DASHBOARD
# ─────────────────────────────────────────────────────────────
st.title("🛡️ RETI Intelligence DSS")
st.caption(f"Configuração Ativa: M={st.session_state.m_val:.2f} | ε={st.session_state.e_val:.2f}")

k1, k2, k3, k4 = st.columns(4)
total_ren = df["Renúncia"].sum()
total_ret = df["Retorno"].sum()
pb_check = df[df["Acumulado"] > 0]
payback = pb_check["Ano"].min() if not pb_check.empty else "N/A"

k1.metric("Custo Total (10a)", f"R$ {total_ren:.2f} Bi")
k2.metric("Retorno PIB (PTF)", f"R$ {total_ret:.2f} Bi")
k3.metric("Payback Fiscal", f"Ano {payback}")
k4.metric("Status LRF", "CONFORME" if df["Renúncia"].max() <= t_lrf else "LIMITADO")

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("📅 Fluxo Anual (LRF)")
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=df["Ano"], y=df["Renúncia"], name="Custo", line=dict(color='#EF4444', width=4)))
    fig1.add_trace(go.Scatter(x=df["Ano"], y=df["Retorno"], name="Retorno", line=dict(color='#2BBFCE', width=4)))
    fig1.add_hline(y=t_lrf, line_dash="dash", line_color="#C9A84C", annotation_text="Teto LRF")
    fig1.update_layout(template="plotly_dark", height=400, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig1, use_container_width=True)

with col_b:
    st.subheader("💰 Saldo Acumulado (ROI)")
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=df["Ano"], y=df["Acumulado"], name="Saldo", fill='tozeroy', line=dict(color='#10B981', width=4)))
    fig2.update_layout(template="plotly_dark", height=400, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig2, use_container_width=True)

with st.expander("🔍 Memória de Cálculo e Diagnóstico Fiscal"):
    # Diagnóstico explícito conforme Opção 3 do feedback
    st.write("Abaixo, o comportamento dos multiplicadores e as penalidades aplicadas:")
    st.dataframe(df[["Ano", "Renúncia", "Retorno", "M_Efetivo", "Penalidade_LRF"]].style.format(precision=3), use_container_width=True)

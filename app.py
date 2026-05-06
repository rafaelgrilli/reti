import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────────────────────
# 1. DESIGN SYSTEM (CONTRASTE TOTAL E CORREÇÃO DE UX)
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="RETI Intelligence v12.0", layout="wide")

# CSS para corrigir especificamente os inputs que estavam "sumindo"
st.markdown("""
    <style>
        .stApp { background-color: #0A0E1A; color: #FFFFFF; }
        
        /* BARRA LATERAL: Fundo escuro e texto branco */
        [data-testid="stSidebar"] { 
            background-color: #0F1525 !important; 
            border-right: 1px solid #1E2A45; 
        }
        
        /* Forçar cor branca em todos os labels da sidebar */
        [data-testid="stSidebar"] label p {
            color: #FFFFFF !important;
            font-weight: 600 !important;
        }

        /* CORREÇÃO DOS INPUTS (Selectbox e NumberInput) */
        div[data-baseweb="select"] > div, 
        div[data-baseweb="input"] > div {
            background-color: #1E293B !important;
            color: white !important;
            border: 1px solid #334155 !important;
        }
        
        /* Texto dentro dos inputs */
        input { color: white !important; }
        div[role="listbox"] { background-color: #1E293B !important; color: white !important; }

        /* CARDS DE MÉTRICA */
        [data-testid="stMetric"] {
            background-color: #161C2D !important;
            border: 1px solid #1E2A45 !important;
            border-left: 5px solid #C9A84C !important;
        }
        [data-testid="stMetricLabel"] { color: #94A3B8 !important; }
        [data-testid="stMetricValue"] { color: #FFFFFF !important; }

        header { visibility: hidden; }
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# 2. MOTOR DE CÁLCULO (100% FIEL À PROPOSTA)
# ─────────────────────────────────────────────────────────────

def run_reti_engine(p):
    ALIQUOTA, PRESUNCAO, MULT_INDIRETO = 0.34, 0.32, 1.3
    LAG, DEPREC, SUCESSO = 3, 0.15, 0.70
    
    rows = []
    estoque_conhecimento = 0
    historico_maturacao = np.zeros(p['horizonte'] + LAG + 10)
    receita = p['rec_inicial']
    
    violation_last_year = False
    m_dinamico = p['mult_base']
    f_penalidade = 0

    for t in range(1, p['horizonte'] + 1):
        rec_ant = receita
        receita *= (1 + p['crescimento'])
        
        # Item 7: Ajuste Paramétrico Automático
        if violation_last_year:
            if m_dinamico > 1.0: m_dinamico = max(1.0, m_dinamico - 0.15)
            else: f_penalidade = 0.5
        
        # Item 3: Fator F
        if receita <= 3.24: f_base = 3.5
        elif receita <= 78.0: f_base = 2.5
        elif receita <= 200.0: f_base = max(1.0, 2.5 - 0.012 * (receita - 78.0))
        else: f_base = 1.0
        f = max(1.0, f_base - f_penalidade)

        # Adicionalidade
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
                renuncia_unitaria = pd_total * 0.40 * (min(p['intensidade_pd'], 0.30)/0.30) * f
            else: renuncia_unitaria = 0

        firmas = p['n_firmas'] / (1 + np.exp(-1.2 * (t - 3)))
        ren_macro = (renuncia_unitaria * firmas) / 1000
        ret_macro = (retorno_total * firmas) / 1000
        violation_last_year = ren_macro > p['teto_lrf']

        rows.append({"Ano": t, "Renúncia": ren_macro, "Retorno": ret_macro, "Saldo": ret_macro - ren_macro, "M": m_dinamico})

    return pd.DataFrame(rows)

# ─────────────────────────────────────────────────────────────
# 3. INTERFACE E DASHBOARD
# ─────────────────────────────────────────────────────────────

# Inicialização correta do Session State para vincular aos Sliders
if 'm_base' not in st.session_state: st.session_state.m_base = 1.25
if 'elast' not in st.session_state: st.session_state.elast = -1.27

with st.sidebar:
    st.title("🛡️ Parâmetros RETI")
    
    st.subheader("🎯 Cenários de Palatabilidade")
    c1, c2, c3 = st.columns(3)
    # Botões agora alteram o session_state que está vinculado aos sliders via 'key'
    if c1.button("🟢 Cons."): 
        st.session_state.m_base = 1.10; st.session_state.elast = -0.80; st.rerun()
    if c2.button("🟡 Mod."): 
        st.session_state.m_base = 1.25; st.session_state.elast = -1.27; st.rerun()
    if c3.button("🟠 Agres."): 
        st.session_state.m_base = 1.45; st.session_state.elast = -1.80; st.rerun()

    st.divider()
    regime = st.selectbox("Regime Tributário", ["Lucro Presumido", "Simples Nacional (RETI-SME)"])
    n_firmas = st.number_input("Universo de Firmas", value=4500)
    t_lrf = st.slider("Teto LRF (R$ Bi/ano)", 0.5, 5.0, 2.2)
    
    st.subheader("🏢 Perfil da Firma")
    i_pd = st.slider("Intensidade P&D", 0.01, 0.40, 0.07)
    p_tec = st.slider("PoTec (%)", 0, 50, 18)
    
    st.subheader("📈 Macro SPE")
    b_ptf = st.slider("β (Elasticidade PTF)", 0.05, 0.12, 0.06)
    
    # VINCULANDO SLIDERS AO SESSION STATE VIA KEY
    m_base = st.slider("Multiplicador M", 1.0, 1.5, key="m_base")
    elast = st.slider("Elasticidade ε", -2.0, -0.5, key="elast")

# Execução do Motor
df = run_reti_engine({
    "regime": regime, "n_firmas": n_firmas, "rec_inicial": 15.0, "intensidade_pd": i_pd,
    "crescimento": 0.12, "beta_ptf": b_ptf, "horizonte": 10, "potec": p_tec,
    "teto_lrf": t_lrf, "mult_base": m_base, "elasticidade": elast
})

# KPIs
st.title("🛡️ RETI Intelligence DSS")
st.caption("Decision Support System | Protocolo SPE/MF & RFB v12.0")

k1, k2, k3, k4 = st.columns(4)
total_ren = df["Renúncia"].sum()
total_ret = df["Retorno"].sum()
payback_df = df[df["Acumulado"] > 0] if "Acumulado" not in df else pd.DataFrame()
df["Acumulado"] = (df["Retorno"] - df["Renúncia"]).cumsum()
payback_ano = df[df["Acumulado"] > 0]["Ano"].min() if not df[df["Acumulado"] > 0].empty else "N/A"

k1.metric("Custo Total (10a)", f"R$ {total_ren:.2f} Bi")
k2.metric("Retorno PIB (PTF)", f"R$ {total_ret:.2f} Bi")
k3.metric("Payback Fiscal", f"Ano {payback_ano}")
k4.metric("Status LRF", "CONFORME" if df["Renúncia"].max() <= t_lrf else "AJUSTADO")

# GRÁFICOS
col_a, col_b = st.columns(2)
with col_a:
    st.subheader("📅 Fluxo Anual (LRF)")
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=df["Ano"], y=df["Renúncia"], name="Custo", line=dict(color='#EF4444', width=4)))
    fig1.add_trace(go.Scatter(x=df["Ano"], y=df["Retorno"], name="Retorno", line=dict(color='#2BBFCE', width=4)))
    fig1.add_hline(y=t_lrf, line_dash="dash", line_color="#C9A84C", annotation_text="Teto LRF")
    fig1.update_layout(template="plotly_dark", height=350, margin=dict(l=10,r=10,t=30,b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig1, use_container_width=True)

with col_b:
    st.subheader("💰 Saldo Acumulado (ROI)")
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=df["Ano"], y=df["Acumulado"], name="Saldo", fill='tozeroy', line=dict(color='#10B981', width=4), fillcolor='rgba(16, 185, 129, 0.2)'))
    fig2.add_hline(y=0, line_color="#FFFFFF")
    fig2.update_layout(template="plotly_dark", height=350, margin=dict(l=10,r=10,t=30,b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig2, use_container_width=True)

# ANÁLISE EXECUTIVA
st.subheader("🧠 Análise de Cenário")
if df["Renúncia"].max() > t_lrf:
    st.info(f"ℹ️ **Nota:** O cenário agressivo atingiu o teto LRF. O motor reduziu o multiplicador para {df['M'].iloc[-1]:.2f} para proteger o orçamento.")

with st.expander("🔍 Memória de Cálculo Detalhada"):
    st.dataframe(df.style.format(precision=3), use_container_width=True)

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────────────────────
# 1. DESIGN SYSTEM (ALTO CONTRASTE E LEGIBILIDADE)
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="RETI Full Compliance v10.50", layout="wide")

st.markdown("""
    <style>
        .stApp { background-color: #0E1117; color: #FFFFFF; }
        [data-testid="stSidebar"] { background-color: #111827 !important; border-right: 1px solid #1F2937; }
        [data-testid="stSidebar"] label { color: #FFFFFF !important; font-weight: 600 !important; }
        [data-testid="stMetric"] {
            background-color: #1E293B !important;
            border: 1px solid #334155 !important;
            border-left: 5px solid #3B82F6 !important;
            padding: 15px !important;
            border-radius: 10px !important;
        }
        [data-testid="stMetricLabel"] { color: #94A3B8 !important; }
        [data-testid="stMetricValue"] { color: #FFFFFF !important; }
        .insight-box {
            padding: 18px; margin: 12px 0px; border-radius: 8px; border-left: 6px solid;
            background-color: #1E293B; color: #FFFFFF !important; line-height: 1.6;
        }
        .insight-red { border-color: #EF4444; }
        .insight-blue { border-color: #3B82F6; }
        .insight-green { border-color: #10B981; }
        h1, h2, h3 { color: #F8FAFC !important; }
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# 2. MOTOR DE CÁLCULO (100% FIEL À PROPOSTA EXECUTIVA)
# ─────────────────────────────────────────────────────────────

def calcular_fator_f(receita, intensidade_pd, ajuste_extra_f=0):
    """Item 3: Tapering e Efeito Notch"""
    if receita <= 3.24: f_base = 3.5
    elif receita <= 16.2: f_base = 3.0
    elif receita <= 78.0: f_base = 2.5
    elif receita <= 200.0:
        f_base = max(1.0, 2.5 - 0.012 * (receita - 78.0))
    else: f_base = 1.0
    
    f_base = max(1.0, f_base - ajuste_extra_f)
    # Módulo Anti-Arbitragem (Item 5): Trava de 5%
    if intensidade_pd < 0.05: return max(1.0, f_base - 1.0)
    return f_base

def run_reti_engine(p):
    ALIQUOTA, PRESUNCAO, LAG, DEPREC, SUCESSO = 0.34, 0.32, 3, 0.15, 0.70
    rows = []
    estoque_conhecimento = 0
    historico_maturacao = np.zeros(p['horizonte'] + LAG + 5)
    receita = p['rec_inicial']
    violation_last_year, m_dinamico, f_penalidade = False, p['mult_base'], 0

    for t in range(1, p['horizonte'] + 1):
        rec_ant = receita
        receita *= (1 + p['crescimento'])
        
        # Item 7: Hierarquia de Ajuste Paramétrico
        if violation_last_year:
            if m_dinamico > 1.0: m_dinamico = max(1.0, m_dinamico - 0.15)
            else: f_penalidade = 0.4
        
        f = calcular_fator_f(receita, p['intensidade_pd'], f_penalidade)
        
        # Item 3: Adicionalidade (Kannebley -1.27)
        pd_original = receita * p['intensidade_pd']
        beneficio_marginal = (m_dinamico * f * ALIQUOTA)
        pd_adicional = pd_original * abs(p['elasticidade']) * beneficio_marginal
        pd_total = pd_original + pd_adicional
        
        # Item 4.1: Transmissão PTF
        if t + LAG < len(historico_maturacao):
            historico_maturacao[t + LAG] = pd_adicional * SUCESSO
        estoque_conhecimento = estoque_conhecimento * (1 - DEPREC) + historico_maturacao[t]
        ganho_ptf = (estoque_conhecimento / receita) * p['beta_ptf'] if receita > 0 else 0
        retorno_indireto = (receita * ganho_ptf) * ALIQUOTA

        # Item 5: Gatilhos de Performance (após 36 meses)
        pode_usar = True
        if t > 3:
            cond_rec = (receita / rec_ant - 1) >= 0.10
            cond_pat = p['patente_ano'] <= t
            cond_potec = p['potec'] >= 15
            pode_usar = cond_rec or cond_pat or cond_potec

        # Item 3 e 6: Cálculo por Regime
        if p['regime'] == "Lucro Presumido":
            base_orig = receita * PRESUNCAO
            # Base = (Rec * 0.32) - (M * PD * F)
            base_red = max(base_orig * 0.25, base_orig - (m_dinamico * pd_total * f))
            renuncia_unitaria = (base_orig - base_red) * ALIQUOTA if pode_usar else 0
        else:
            # RETI-SME: Innovation Vouchers (Threshold 15%)
            if p['intensidade_pd'] >= 0.15 and pode_usar:
                renuncia_unitaria = pd_total * min(p['intensidade_pd'], 0.30) * f * 0.4
            else: renuncia_unitaria = 0

        firmas = p['n_firmas'] / (1 + np.exp(-1.2 * (t - 3)))
        ren_macro, ret_macro = (renuncia_unitaria * firmas) / 1000, (retorno_indireto * firmas) / 1000
        violation_last_year = ren_macro > p['teto_lrf']

        rows.append({
            "Ano": t, "Renúncia Anual": ren_macro, "Retorno Anual": ret_macro, 
            "Saldo Anual": ret_macro - ren_macro, "M": m_dinamico, "F": f
        })

    df = pd.DataFrame(rows)
    df["Saldo Acumulado"] = df["Saldo Anual"].cumsum()
    return df

# ─────────────────────────────────────────────────────────────
# 3. INTERFACE E DASHBOARD
# ─────────────────────────────────────────────────────────────

st.title("🛡️ RETI Intelligence Report")
st.caption("Protocolo SPE/MF & RFB - Full Compliance v10.50")

with st.sidebar:
    st.header("📋 Configuração do Regime")
    regime = st.selectbox("Regime Tributário", ["Lucro Presumido", "Simples Nacional (RETI-SME)"])
    n_firmas = st.number_input("Universo de Firmas", value=2500)
    t_lrf = st.slider("Teto LRF (R$ Bi/ano)", 0.5, 5.0, 1.8)
    
    st.header("🔬 Perfil Tecnológico")
    i_pd = st.slider("Intensidade P&D (P&D/Rec)", 0.01, 0.40, 0.07)
    p_tec = st.slider("PoTec (%)", 0, 50, 18)
    patente = st.number_input("Ano da 1ª Patente", value=3)
    
    st.header("📈 Parâmetros Macro")
    b_ptf = st.slider("β (Elasticidade PTF)", 0.05, 0.08, 0.06)
    m_base = st.slider("Multiplicador M", 1.0, 1.5, 1.25)

# Processamento
df = run_reti_engine({
    "regime": regime, "n_firmas": n_firmas, "mult_base": m_base, "rec_inicial": 15.0,
    "intensidade_pd": i_pd, "crescimento": 0.12, "elasticidade": -1.27, 
    "beta_ptf": b_ptf, "horizonte": 15, "potec": p_tec, "patente_ano": patente, "teto_lrf": t_lrf
})

# KPIs
c1, c2, c3, c4 = st.columns(4)
total_ren = df["Renúncia Anual"].sum()
total_ret = df["Retorno Anual"].sum()
payback_row = df[df["Saldo Acumulado"] > 0]
payback_ano = payback_row["Ano"].min() if not payback_row.empty else "Fora do Horizonte"

c1.metric("Custo Total (15a)", f"R$ {total_ren:.2f} Bi")
c2.metric("Retorno PIB (15a)", f"R$ {total_ret:.2f} Bi")
c3.metric("Payback Fiscal", f"Ano {payback_ano}")
c4.metric("Status LRF", "ESTÁVEL" if df["Renúncia Anual"].max() <= t_lrf else "AJUSTADO")

# GRÁFICOS
col_a, col_b = st.columns(2)
with col_a:
    st.subheader("📅 Fluxo Anual (LRF)")
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=df["Ano"], y=df["Renúncia Anual"], name="Custo", line=dict(color='#EF4444', width=4)))
    fig1.add_trace(go.Scatter(x=df["Ano"], y=df["Retorno Anual"], name="Retorno", line=dict(color='#3B82F6', width=4)))
    fig1.add_hline(y=t_lrf, line_dash="dash", line_color="#94A3B8", annotation_text="Teto LRF")
    fig1.update_layout(template="plotly_dark", height=350, margin=dict(l=10,r=10,t=30,b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig1, use_container_width=True)

with col_b:
    st.subheader("💰 Saldo Acumulado (ROI)")
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=df["Ano"], y=df["Saldo Acumulado"], name="Saldo", fill='tozeroy', line=dict(color='#10B981', width=4), fillcolor='rgba(16, 185, 129, 0.2)'))
    fig2.add_hline(y=0, line_color="#FFFFFF")
    fig2.update_layout(template="plotly_dark", height=350, margin=dict(l=10,r=10,t=30,b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig2, use_container_width=True)

# ANÁLISE EXECUTIVA
st.subheader("🧠 Análise de Cenário")

if regime == "Simples Nacional (RETI-SME)" and i_pd < 0.15:
    st.markdown(f"""<div class='insight-box insight-red'>
        <b>BLOQUEIO RETI-SME:</b> A intensidade de P&D ({i_pd*100:.1f}%) está abaixo do threshold de 15% exigido para o modelo de Vouchers (Item 6). O benefício foi zerado.
    </div>""", unsafe_allow_html=True)

if df["Renúncia Anual"].max() > t_lrf:
    st.markdown(f"""<div class='insight-box insight-red'>
        <b>⚠️ AJUSTE PARAMÉTRICO ATIVADO:</b> O teto de R$ {t_lrf} Bi foi atingido. Seguindo a hierarquia do Item 7, o multiplicador M foi reduzido para {df['M'].iloc[-1]:.2f} para garantir a neutralidade fiscal.
    </div>""", unsafe_allow_html=True)

if not isinstance(payback_ano, str):
    st.markdown(f"""<div class='insight-box insight-green'>
        <b>✅ VIABILIDADE ECONÔMICA:</b> O payback ocorre no <b>Ano {payback_ano}</b>. O choque de oferta na PTF (β={b_ptf}) compensa a renúncia inicial, elevando o PIB potencial conforme Item 4.2.
    </div>""", unsafe_allow_html=True)
else:
    st.markdown("""<div class='insight-box insight-blue'>
        <b>⏳ ANÁLISE DE MATURAÇÃO:</b> O retorno ainda não superou o custo. Recomenda-se revisar o multiplicador M ou focar em firmas com maior PoTec para acelerar a transmissão PTF.
    </div>""", unsafe_allow_html=True)

with st.expander("🔍 Memória de Cálculo Detalhada"):
    st.dataframe(df.style.format(precision=3), use_container_width=True)

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────────────────────
# 1. DESIGN SYSTEM (HIGH CONTRAST & SIDEBAR FIX)
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="RETI Intelligence v10.70", layout="wide")

st.markdown("""
    <style>
        .stApp { background-color: #0E1117; color: #FFFFFF; }
        
        /* SIDEBAR - Restauração de Legibilidade Total */
        [data-testid="stSidebar"] { 
            background-color: #111827 !important; 
            border-right: 1px solid #1F2937; 
            min-width: 350px !important;
        }
        [data-testid="stSidebar"] .stMarkdown p { color: #FFFFFF !important; font-weight: 600; }
        [data-testid="stSidebar"] label { color: #CBD5E1 !important; font-weight: 500 !important; }
        [data-testid="stSidebar"] .stSlider { padding-bottom: 20px; }
        
        /* CARDS DE MÉTRICA */
        [data-testid="stMetric"] {
            background-color: #1E293B !important;
            border: 1px solid #334155 !important;
            border-left: 5px solid #3B82F6 !important;
            padding: 15px !important;
            border-radius: 10px !important;
        }
        [data-testid="stMetricLabel"] { color: #94A3B8 !important; font-size: 14px !important; }
        [data-testid="stMetricValue"] { color: #FFFFFF !important; font-size: 24px !important; font-weight: 800 !important; }

        /* INSIGHTS */
        .insight-box {
            padding: 18px; margin: 12px 0px; border-radius: 8px; border-left: 6px solid;
            background-color: #161E2E; color: #FFFFFF !important; line-height: 1.6; font-size: 15px;
        }
        .insight-red { border-color: #EF4444; }
        .insight-blue { border-color: #3B82F6; }
        .insight-green { border-color: #10B981; }
        
        .comp-panel { background-color: #0F172A; padding: 20px; border-radius: 10px; border: 1px dashed #334155; }
        h1, h2, h3 { color: #F8FAFC !important; }
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# 2. MOTOR DE CÁLCULO (PROTOCOLO INTEGRAL SPE/MF)
# ─────────────────────────────────────────────────────────────

def run_reti_engine(p):
    ALIQUOTA, PRESUNCAO = 0.34, 0.32
    MULT_INDIRETO = 1.3  # Item 4.2
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
        
        # Item 7: Hierarquia de Ajuste Paramétrico
        if violation_last_year:
            if m_dinamico > 1.0: m_dinamico = max(1.0, m_dinamico - 0.15)
            else: f_penalidade = 0.5
        
        # Item 3: Fator F com Tapering Linear
        if receita <= 3.24: f_base = 3.5
        elif receita <= 16.2: f_base = 3.0
        elif receita <= 78.0: f_base = 2.5
        elif receita <= 200.0:
            f_base = max(1.0, 2.5 - 0.012 * (receita - 78.0))
        else: f_base = 1.0
        
        f = max(1.0, f_base - f_penalidade)
        if p['intensidade_pd'] < 0.05: f = max(1.0, f - 1.0) # Anti-Arbitragem

        # Item 3: Adicionalidade (Kannebley)
        pd_original = receita * p['intensidade_pd']
        beneficio_marginal = (m_dinamico * f * ALIQUOTA)
        pd_adicional = pd_original * abs(p['elasticidade']) * beneficio_marginal
        pd_total = pd_original + pd_adicional
        
        # Item 4.1: Transmissão PTF
        if t + LAG < len(historico_maturacao):
            historico_maturacao[t + LAG] = pd_adicional * SUCESSO
        estoque_conhecimento = estoque_conhecimento * (1 - DEPREC) + historico_maturacao[t]
        ganho_ptf = (estoque_conhecimento / receita) * p['beta_ptf'] if receita > 0 else 0
        
        # Item 4.2: Retorno Fiscal Total
        retorno_total = (receita * ganho_ptf) * ALIQUOTA * MULT_INDIRETO

        # Item 5: Gatilhos de Performance
        pode_usar = True
        if t > 3:
            pode_usar = (receita/rec_ant - 1 >= 0.10) or (p['potec'] >= 15) or (p['patente'] <= t)

        # Item 3 e 6: Cálculo da Renúncia
        if p['regime'] == "Lucro Presumido":
            base_orig = receita * PRESUNCAO
            base_red = max(base_orig * 0.25, base_orig - (m_dinamico * pd_total * f))
            renuncia_unitaria = (base_orig - base_red) * ALIQUOTA if pode_usar else 0
        else:
            # RETI-SME: Vouchers Progressivos
            if p['intensidade_pd'] >= 0.15 and pode_usar:
                prog = min(p['intensidade_pd'], 0.30) / 0.30
                renuncia_unitaria = pd_total * 0.40 * prog * f
            else: renuncia_unitaria = 0

        firmas = p['n_firmas'] / (1 + np.exp(-1.2 * (t - 3)))
        ren_macro = (renuncia_unitaria * firmas) / 1000
        ret_macro = (retorno_total * firmas) / 1000
        violation_last_year = ren_macro > p['teto_lrf']

        rows.append({
            "Ano": t, "Renúncia": ren_macro, "Retorno": ret_macro, 
            "Saldo": ret_macro - ren_macro, "M": m_dinamico, "F": f, "Adesão": int(firmas)
        })

    df = pd.DataFrame(rows)
    df["Acumulado"] = df["Saldo"].cumsum()
    return df

# ─────────────────────────────────────────────────────────────
# 3. INTERFACE E DASHBOARD (SIDEBAR COMPLETA)
# ─────────────────────────────────────────────────────────────

st.title("🛡️ RETI Intelligence Report")
st.caption("Protocolo SPE/MF & RFB | Termo de Referência Final v10.70")

with st.sidebar:
    st.header("📋 Configuração do Regime")
    regime = st.selectbox("Regime Tributário", ["Lucro Presumido", "Simples Nacional (RETI-SME)"])
    n_firmas = st.number_input("Universo de Firmas Elegíveis", value=3500, step=100)
    t_lrf = st.slider("Teto LRF (R$ Bi/ano)", 0.5, 5.0, 1.8)
    
    st.header("🔬 Perfil da Firma (Micro)")
    r_ini = st.number_input("Receita Inicial (R$ MM)", value=15.0)
    i_pd = st.slider("Intensidade P&D (P&D/Rec)", 0.01, 0.40, 0.08)
    cresc = st.slider("Crescimento Anual da Receita", 0.0, 0.50, 0.12)
    p_tec = st.slider("Pessoal Qualificado (PoTec %)", 0, 50, 18)
    patente = st.number_input("Ano de Depósito da Patente", value=3)
    
    st.header("📈 Parâmetros Macro (SPE)")
    b_ptf = st.slider("β (Elasticidade PTF)", 0.05, 0.12, 0.06)
    m_base = st.slider("Multiplicador M Inicial", 1.0, 1.5, 1.25)
    elast = st.slider("Elasticidade-Custo (Kannebley)", -2.0, -0.5, -1.27)

# Execução
df = run_reti_engine({
    "regime": regime, "n_firmas": n_firmas, "rec_inicial": r_ini,
    "intensidade_pd": i_pd, "crescimento": cresc, "beta_ptf": b_ptf, 
    "horizonte": 15, "potec": p_tec, "patente": patente, "teto_lrf": t_lrf,
    "mult_base": m_base, "elasticidade": elast
})

# KPIs
c1, c2, c3, c4 = st.columns(4)
total_ren = df["Renúncia"].sum()
total_ret = df["Retorno"].sum()
payback = df[df["Acumulado"] > 0]["Ano"].min()

c1.metric("Custo Total (15a)", f"R$ {total_ren:.2f} Bi")
c2.metric("Retorno PIB (Indireto)", f"R$ {total_ret:.2f} Bi")
c3.metric("Payback Fiscal", f"Ano {payback}" if not np.isnan(payback) else "Fora do Horizonte")
c4.metric("Status LRF", "CONFORME" if df["Renúncia"].max() <= t_lrf else "AJUSTADO")

# GRÁFICOS
col_a, col_b = st.columns(2)
with col_a:
    st.subheader("📅 Fluxo Anual (LRF)")
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=df["Ano"], y=df["Renúncia"], name="Custo Anual", line=dict(color='#EF4444', width=4)))
    fig1.add_trace(go.Scatter(x=df["Ano"], y=df["Retorno"], name="Retorno Anual", line=dict(color='#3B82F6', width=4)))
    fig1.add_hline(y=t_lrf, line_dash="dash", line_color="#94A3B8", annotation_text="Teto LRF")
    fig1.update_layout(template="plotly_dark", height=350, margin=dict(l=10,r=10,t=30,b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig1, use_container_width=True)

with col_b:
    st.subheader("💰 Saldo Acumulado (ROI)")
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=df["Ano"], y=df["Acumulado"], name="Saldo Líquido", fill='tozeroy', line=dict(color='#10B981', width=4), fillcolor='rgba(16, 185, 129, 0.2)'))
    fig2.add_hline(y=0, line_color="#FFFFFF")
    fig2.update_layout(template="plotly_dark", height=350, margin=dict(l=10,r=10,t=30,b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig2, use_container_width=True)

# PAINEL DE COMPENSAÇÃO (ITEM 7)
st.subheader("⚖️ Sustentabilidade Fiscal (Fontes de Custeio)")
st.markdown(f"""
<div class='comp-panel'>
    <table style='width:100%; color:white; font-size:14px;'>
        <tr><td>🎰 <b>Taxação de Apostas (Bets):</b> Incremento de GGR (12% para 15%)</td><td style='text-align:right;'>R$ 2,5 Bi/ano est.</td></tr>
        <tr><td>🏛️ <b>Reforma Administrativa:</b> Eficiência em despesas primárias correntes</td><td style='text-align:right;'>R$ 1,2 Bi/ano est.</td></tr>
        <tr><td>✂️ <b>Corte de Gastos Ineficientes:</b> Redução linear de 10% (CMAP/TCU)</td><td style='text-align:right;'>R$ 0,9 Bi/ano est.</td></tr>
    </table>
</div>
""", unsafe_allow_html=True)

# ANÁLISE EXECUTIVA
st.subheader("🧠 Análise de Cenário")
if regime == "Simples Nacional (RETI-SME)" and i_pd < 0.15:
    st.markdown(f"<div class='insight-box insight-red'><b>BLOQUEIO ITEM 6:</b> Intensidade de P&D ({i_pd*100:.1f}%) abaixo de 15%. Firma inelegível ao Voucher.</div>", unsafe_allow_html=True)

if df["Renúncia"].max() > t_lrf:
    st.markdown(f"<div class='insight-box insight-red'><b>AJUSTE ITEM 7:</b> Teto LRF atingido. Multiplicador M reduzido para {df['M'].iloc[-1]:.2f} para garantir neutralidade.</div>", unsafe_allow_html=True)

if not np.isnan(payback):
    st.markdown(f"<div class='insight-box insight-green'><b>EFICIÊNCIA ITEM 4.2:</b> Payback em {payback} anos. O incremento de produtividade (PTF) compensa o investimento público.</div>", unsafe_allow_html=True)

with st.expander("🔍 Memória de Cálculo Detalhada"):
    st.dataframe(df.style.format(precision=3), use_container_width=True)

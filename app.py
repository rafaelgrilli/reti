import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────────────────────
# 1. CONFIGURAÇÃO E DESIGN SYSTEM (UI/UX PREMIUM)
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="RETI Intelligence v10.30", layout="wide")

st.markdown("""
    <style>
        .stApp { background-color: #0E1117; }
        
        /* Cards de Métrica Estilizados */
        [data-testid="stMetric"] {
            background-color: #1A1F2C !important;
            border-left: 5px solid #3B82F6 !important; /* Barra lateral azul */
            padding: 20px !important;
            border-radius: 8px !important;
        }

        /* Texto das métricas */
        [data-testid="stMetricLabel"] { color: #94A3B8 !important; font-family: 'Inter', sans-serif; }
        [data-testid="stMetricValue"] { color: #F8FAFC !important; font-weight: 700 !important; }

        /* Estilo para os Insights */
        .insight-card {
            background-color: #1E293B;
            padding: 20px;
            border-radius: 10px;
            border: 1px solid #334155;
            margin-bottom: 10px;
        }
        
        h1, h2, h3 { font-family: 'Inter', sans-serif; color: #FFFFFF !important; }
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# 2. MOTOR DE CÁLCULO (RETI CORE)
# ─────────────────────────────────────────────────────────────

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
        
        # Ajuste Paramétrico (Item 7)
        if violation_last_year:
            if m_dinamico > 1.0: m_dinamico = max(1.0, m_dinamico - 0.10)
            else: f_penalidade = 0.4
        
        # Fator F com Tapering (Item 3)
        if receita <= 3.24: f_base = 3.5
        elif receita <= 78.0: f_base = 2.5
        elif receita <= 200.0: f_base = max(1.0, 2.5 - 0.012 * (receita - 78.0))
        else: f_base = 1.0
        f = max(1.0, f_base - f_penalidade)
        if p['intensidade_pd'] < 0.05: f = max(1.0, f - 1.0)

        # Adicionalidade e PTF
        pd_total = (receita * p['intensidade_pd']) * (1 + abs(p['elasticidade']) * (m_dinamico * f * ALIQUOTA))
        if t + LAG < len(historico_maturacao): historico_maturacao[t + LAG] = (pd_total - (receita * p['intensidade_pd'])) * SUCESSO
        
        estoque_conhecimento = estoque_conhecimento * (1 - DEPREC) + historico_maturacao[t]
        ganho_ptf = (estoque_conhecimento / receita) * p['beta_ptf'] if receita > 0 else 0
        retorno_indireto = (receita * ganho_ptf) * ALIQUOTA

        # Gatilhos e Renúncia
        pode_usar = True if t <= 3 else ((receita/rec_ant - 1) >= 0.10 or p['potec'] >= 15)
        
        if p['regime'] == "Lucro Presumido":
            base_orig = receita * PRESUNCAO
            base_red = max(base_orig * 0.25, base_orig - (m_dinamico * pd_total * f))
            renuncia = (base_orig - base_red) * ALIQUOTA if pode_usar else 0
        else:
            renuncia = pd_total * min(p['intensidade_pd'], 0.30) * f * 0.5 if (p['intensidade_pd'] >= 0.15 and pode_usar) else 0

        firmas = p['n_firmas'] / (1 + np.exp(-1.2 * (t - 3)))
        ren_macro, ret_macro = (renuncia * firmas) / 1000, (retorno_indireto * firmas) / 1000
        violation_last_year = ren_macro > p['teto_lrf']

        rows.append({"Ano": t, "Renúncia": ren_macro, "Retorno": ret_macro, "Saldo": ret_macro - ren_macro, "M": m_dinamico, "F": f})

    return pd.DataFrame(rows)

# ─────────────────────────────────────────────────────────────
# 3. MOTOR DE INTELIGÊNCIA (ANÁLISE EXECUTIVA)
# ─────────────────────────────────────────────────────────────

def gerar_analise_executiva(df, p):
    total_ren = df["Renúncia"].sum()
    total_ret = df["Retorno"].sum()
    max_ren = df["Renúncia"].max()
    
    insights = []
    
    # Insight 1: Sustentabilidade Fiscal
    if max_ren > p['teto_lrf']:
        insights.append(f"🔴 **Alerta de Teto:** A renúncia atingiu R$ {max_ren:.2f} Bi, superando o teto de R$ {p['teto_lrf']:.2f} Bi. O sistema autoajustável reduziu o multiplicador M para {df['M'].iloc[-1]:.2f} para preservar a LRF.")
    else:
        insights.append(f"🟢 **Conformidade Fiscal:** O programa operou dentro do teto de R$ {p['teto_lrf']:.2f} Bi sem necessidade de cortes paramétricos agressivos.")

    # Insight 2: Eficiência (ROI)
    roi = (total_ret / total_ren - 1) * 100 if total_ren > 0 else 0
    if roi < 0:
        insights.append(f"⏳ **Fase de Maturação:** O ROI atual é de {roi:.1f}%. Isso é esperado devido ao LAG tecnológico de 3 anos. O retorno via PTF começa a acelerar a partir do Ano 5.")
    else:
        insights.append(f"🚀 **Alta Performance:** O programa já se paga no horizonte de 15 anos, gerando um retorno líquido de R$ {total_ret - total_ren:.2f} Bi para o PIB.")

    # Insight 3: Perfil de Inovação
    if p['intensidade_pd'] > 0.15:
        insights.append("💎 **Perfil Deep Tech:** A alta intensidade de P&D declarada maximiza o Fator F, mas eleva o custo fiscal inicial. Recomendado monitorar o Risk Scoring.")
    
    return insights

# ─────────────────────────────────────────────────────────────
# 4. INTERFACE E DASHBOARD
# ─────────────────────────────────────────────────────────────

st.title("🛡️ RETI Intelligence Report")
st.caption("Protocolo de Monitoramento SPE/MF - v10.30")

with st.sidebar:
    st.header("📋 Parâmetros")
    regime = st.selectbox("Regime", ["Lucro Presumido", "Simples Nacional (RETI-SME)"])
    n_firmas = st.number_input("Universo de Firmas", value=2500)
    t_lrf = st.slider("Teto LRF (R$ Bi/ano)", 0.5, 5.0, 2.0)
    m_base = st.slider("Multiplicador M", 1.0, 1.5, 1.25)
    i_pd = st.slider("Intensidade P&D", 0.01, 0.30, 0.07)
    b_ptf = st.slider("β (Elasticidade PTF)", 0.05, 0.12, 0.07)

# Processamento
df = run_reti_engine({
    "regime": regime, "n_firmas": n_firmas, "mult_base": m_base, "rec_inicial": 15.0,
    "intensidade_pd": i_pd, "crescimento": 0.12, "elasticidade": -1.27, 
    "beta_ptf": b_ptf, "horizonte": 15, "potec": 18, "patente_ano": 3, "teto_lrf": t_lrf
})

# KPIs Superiores
c1, c2, c3, c4 = st.columns(4)
total_ren = df["Renúncia"].sum()
total_ret = df["Retorno"].sum()
df['Acumulado'] = (df['Retorno'] - df['Renúncia']).cumsum()
payback = df[df['Acumulado'] > 0]['Ano'].min()

c1.metric("Custo Total (15a)", f"R$ {total_ren:.2f} Bi")
c2.metric("Ganho PIB (PTF)", f"R$ {total_ret:.2f} Bi")
c3.metric("Payback Fiscal", f"Ano {payback}" if not np.isnan(payback) else "Fora do Horizonte")
c4.metric("Status LRF", "ESTÁVEL" if df["Renúncia"].max() <= t_lrf else "AJUSTADO")

# Gráfico Profissional
st.subheader("📊 Evolução Fiscal e Impacto Econômico")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["Ano"], y=df["Renúncia"], name="Custo Fiscal (Renúncia)", 
                         line=dict(color='#F87171', width=3), fill='tozeroy', fillcolor='rgba(248, 113, 113, 0.1)'))
fig.add_trace(go.Scatter(x=df["Ano"], y=df["Retorno"], name="Retorno Econômico (PIB)", 
                         line=dict(color='#3B82F6', width=3), fill='tozeroy', fillcolor='rgba(59, 130, 246, 0.1)'))
fig.add_hline(y=t_lrf, line_dash="dash", line_color="#FBBF24", annotation_text="Limite LRF")

fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0, r=0, t=30, b=0),
                  legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
st.plotly_chart(fig, use_container_width=True)

# Seção de Inteligência
st.subheader("🧠 Análise Executiva do Cenário")
insights = gerar_analise_executiva(df, {"teto_lrf": t_lrf, "intensidade_pd": i_pd})
for insight in insights:
    st.markdown(f"<div class='insight-card'>{insight}</div>", unsafe_allow_html=True)

with st.expander("🔍 Memória de Cálculo Detalhada"):
    st.table(df.drop(columns=['Acumulado']).head(15))

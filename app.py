import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────────────────────
# 1. CONFIGURAÇÃO DE TELA E UI (FOCO EM LEGIBILIDADE DA SIDEBAR)
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="RETI Intelligence v10.45", layout="wide")

st.markdown("""
    <style>
        /* Fundo Geral */
        .stApp { background-color: #0E1117; color: #FFFFFF; }
        
        /* --- ESTILIZAÇÃO DA BARRA LATERAL (SIDEBAR) --- */
        [data-testid="stSidebar"] {
            background-color: #111827 !important;
            border-right: 1px solid #1F2937;
        }
        /* Labels dos Sliders e Inputs na Sidebar */
        [data-testid="stSidebar"] label {
            color: #FFFFFF !important;
            font-weight: 600 !important;
            font-size: 14px !important;
        }
        /* Texto dentro dos inputs numéricos */
        [data-testid="stSidebar"] input {
            color: #FFFFFF !important;
            background-color: #1F2937 !important;
        }

        /* --- CARDS DE MÉTRICA --- */
        [data-testid="stMetric"] {
            background-color: #1E293B !important;
            border: 1px solid #334155 !important;
            border-left: 5px solid #3B82F6 !important;
            padding: 15px !important;
            border-radius: 10px !important;
        }
        [data-testid="stMetricLabel"] { color: #94A3B8 !important; font-size: 15px !important; }
        [data-testid="stMetricValue"] { color: #FFFFFF !important; font-size: 26px !important; font-weight: 800 !important; }

        /* --- CAIXAS DE INSIGHT --- */
        .insight-box {
            padding: 18px;
            margin: 12px 0px;
            border-radius: 8px;
            border-left: 6px solid;
            background-color: #1E293B; /* Fundo levemente mais claro para contraste */
            color: #FFFFFF !important;
            font-size: 15px;
            line-height: 1.6;
            box-shadow: 0 4px 6px rgba(0,0,0,0.2);
        }
        .insight-red { border-color: #EF4444; }
        .insight-blue { border-color: #3B82F6; }
        .insight-green { border-color: #10B981; }
        
        /* Títulos */
        h1, h2, h3 { color: #F8FAFC !important; font-weight: 700 !important; }
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# 2. MOTOR DE CÁLCULO (RETI CORE - 100% COMPLIANT)
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
        
        if violation_last_year:
            m_dinamico = max(1.0, m_dinamico - 0.10)
            f_penalidade = 0.3
        
        if receita <= 3.24: f_base = 3.5
        elif receita <= 78.0: f_base = 2.5
        elif receita <= 200.0: f_base = max(1.0, 2.5 - 0.012 * (receita - 78.0))
        else: f_base = 1.0
        f = max(1.0, f_base - f_penalidade)

        pd_total = (receita * p['intensidade_pd']) * (1 + abs(p['elasticidade']) * (m_dinamico * f * ALIQUOTA))
        if t + LAG < len(historico_maturacao): 
            historico_maturacao[t + LAG] = (pd_total - (receita * p['intensidade_pd'])) * SUCESSO
        
        estoque_conhecimento = estoque_conhecimento * (1 - DEPREC) + historico_maturacao[t]
        ganho_ptf = (estoque_conhecimento / receita) * p['beta_ptf'] if receita > 0 else 0
        retorno_indireto = (receita * ganho_ptf) * ALIQUOTA

        pode_usar = True if t <= 3 else ((receita/rec_ant - 1) >= 0.10 or p['potec'] >= 15)
        
        base_orig = receita * PRESUNCAO
        base_red = max(base_orig * 0.25, base_orig - (m_dinamico * pd_total * f))
        renuncia = (base_orig - base_red) * ALIQUOTA if pode_usar else 0

        firmas = p['n_firmas'] / (1 + np.exp(-1.2 * (t - 3)))
        ren_macro, ret_macro = (renuncia * firmas) / 1000, (retorno_indireto * firmas) / 1000
        violation_last_year = ren_macro > p['teto_lrf']

        rows.append({
            "Ano": t, "Renúncia Anual": ren_macro, "Retorno Anual": ret_macro, 
            "Saldo Anual": ret_macro - ren_macro, "M": m_dinamico
        })

    df = pd.DataFrame(rows)
    df["Saldo Acumulado"] = df["Saldo Anual"].cumsum()
    return df

# ─────────────────────────────────────────────────────────────
# 3. INTERFACE E DASHBOARD
# ─────────────────────────────────────────────────────────────

st.title("🛡️ RETI Intelligence Report")
st.caption("Protocolo de Monitoramento SPE/MF - v10.45")

with st.sidebar:
    st.header("⚙️ Parâmetros de Controle")
    n_firmas = st.number_input("Universo de Firmas", value=2500, step=100)
    t_lrf = st.slider("Teto LRF (R$ Bi/ano)", 0.5, 5.0, 2.0)
    i_pd = st.slider("Intensidade P&D", 0.01, 0.30, 0.07)
    b_ptf = st.slider("β (Elasticidade PTF)", 0.05, 0.12, 0.07)
    m_base = st.slider("Multiplicador M", 1.0, 1.5, 1.25)

# Processamento
df = run_reti_engine({
    "regime": "Lucro Presumido", "n_firmas": n_firmas, "mult_base": m_base, "rec_inicial": 15.0,
    "intensidade_pd": i_pd, "crescimento": 0.12, "elasticidade": -1.27, 
    "beta_ptf": b_ptf, "horizonte": 15, "potec": 18, "patente_ano": 3, "teto_lrf": t_lrf
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
    fig1.add_trace(go.Scatter(x=df["Ano"], y=df["Renúncia Anual"], name="Custo Anual", line=dict(color='#EF4444', width=4)))
    fig1.add_trace(go.Scatter(x=df["Ano"], y=df["Retorno Anual"], name="Retorno Anual", line=dict(color='#3B82F6', width=4)))
    fig1.add_hline(y=t_lrf, line_dash="dash", line_color="#94A3B8", annotation_text="Teto LRF", annotation_font_color="#94A3B8")
    fig1.update_layout(template="plotly_dark", height=350, margin=dict(l=10,r=10,t=30,b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig1, use_container_width=True)

with col_b:
    st.subheader("💰 Saldo Acumulado (ROI)")
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=df["Ano"], y=df["Saldo Acumulado"], name="Saldo Líquido", fill='tozeroy', line=dict(color='#10B981', width=4), fillcolor='rgba(16, 185, 129, 0.2)'))
    fig2.add_hline(y=0, line_color="#FFFFFF")
    fig2.update_layout(template="plotly_dark", height=350, margin=dict(l=10,r=10,t=30,b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig2, use_container_width=True)

# INSIGHTS
st.subheader("🧠 Análise de Cenário")

if df["Renúncia Anual"].max() > t_lrf:
    st.markdown(f"""<div class='insight-box insight-red'>
        <b>⚠️ ALERTA DE TETO FISCAL:</b> A renúncia anual ultrapassou o limite de R$ {t_lrf} Bi. 
        O motor autoajustável reduziu o multiplicador para {df['M'].iloc[-1]:.2f} para estabilizar a curva e garantir a neutralidade fiscal.
    </div>""", unsafe_allow_html=True)
else:
    st.markdown(f"""<div class='insight-box insight-green'>
        <b>✅ CONFORMIDADE LRF:</b> O desenho atual da política mantém o custo anual abaixo do teto estabelecido, garantindo sustentabilidade orçamentária sem necessidade de gatilhos de corte.
    </div>""", unsafe_allow_html=True)

if isinstance(payback_ano, str):
    st.markdown("""<div class='insight-box insight-blue'>
        <b>⏳ MATURAÇÃO LONGA:</b> O retorno via produtividade (PTF) ainda não superou o custo no horizonte de 15 anos. 
        Isso sugere a necessidade de calibrar a elasticidade β ou focar em setores de maior transbordamento tecnológico.
    </div>""", unsafe_allow_html=True)
else:
    st.markdown(f"""<div class='insight-box insight-green'>
        <b>📈 EFICIÊNCIA CONFIRMADA:</b> O projeto atinge o ponto de equilíbrio fiscal no <b>Ano {payback_ano}</b>. 
        A partir deste marco, o incremento de arrecadação via PIB potencial supera o investimento público realizado.
    </div>""", unsafe_allow_html=True)

with st.expander("🔍 Ver Tabela de Dados Detalhada"):
    st.dataframe(df.style.format(precision=2), use_container_width=True)

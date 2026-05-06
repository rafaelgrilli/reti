import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ─────────────────────────────────────────────────────────────
# 1. DESIGN SYSTEM & UI CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="RETI Intelligence DSS v10.90", layout="wide")

CORES = {
    "gold": "#C9A84C", "cyan": "#2BBFCE", "red": "#EF4444",
    "green": "#10B981", "amber": "#F59E0B", "bg": "#0A0E1A",
    "card": "#161C2D", "border": "#1E2A45", "text": "#FFFFFF"
}

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;700&display=swap');
    html, body, [class*="css"] {{ font-family: 'Sora', sans-serif; background-color: {CORES['bg']}; color: {CORES['text']}; }}
    .stApp {{ background-color: {CORES['bg']}; }}
    .block-container {{ padding-top: 2rem !important; }}
    header {{ visibility: hidden; }} 
    [data-testid="stSidebar"] {{ background-color: #0F1525 !important; border-right: 1px solid {CORES['border']}; min-width: 350px !important; }}
    [data-testid="stSidebar"] label {{ color: #CBD5E1 !important; font-weight: 600 !important; }}
    [data-testid="stMetric"] {{
        background-color: {CORES['card']} !important; border: 1px solid {CORES['border']} !important;
        border-left: 4px solid {CORES['gold']} !important; border-radius: 8px !important; padding: 15px !important;
    }}
    .insight-box {{ padding: 18px; margin: 12px 0px; border-radius: 8px; border-left: 6px solid; background-color: #1E293B; color: #FFFFFF !important; }}
    .insight-red {{ border-color: {CORES['red']}; }} .insight-green {{ border-color: {CORES['green']}; }}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# 2. MOTOR DE CÁLCULO (PROTOCOLO INTEGRAL SPE/MF)
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
        
        # Item 7: Ajuste Paramétrico Automático (Hierarquia de Preferência)
        if violation_last_year:
            if m_dinamico > 1.0: m_dinamico = max(1.0, m_dinamico - 0.15)
            else: f_penalidade = 0.5
        
        # Item 3: Fator F com Phasing-out Linear
        if receita <= 3.24: f_base = 3.5
        elif receita <= 78.0: f_base = 2.5
        elif receita <= 200.0: f_base = max(1.0, 2.5 - 0.012 * (receita - 78.0))
        else: f_base = 1.0
        f = max(1.0, f_base - f_penalidade)
        
        # Módulo Anti-Arbitragem (Item 5)
        if p['intensidade_pd'] < 0.05: f = max(1.0, f - 1.0)

        # Adicionalidade (Kannebley -1.27)
        pd_original = receita * p['intensidade_pd']
        pd_adicional = pd_original * abs(p['elasticidade']) * (m_dinamico * f * ALIQUOTA)
        pd_total = pd_original + pd_adicional
        
        # Transmissão PTF (Item 4.1)
        if t + LAG < len(historico_maturacao): historico_maturacao[t + LAG] = pd_adicional * SUCESSO
        estoque_conhecimento = estoque_conhecimento * (1 - DEPREC) + historico_maturacao[t]
        ganho_ptf = (estoque_conhecimento / receita) * p['beta_ptf'] if receita > 0 else 0
        
        # Retorno Fiscal Total (Item 4.2)
        retorno_total = (receita * ganho_ptf) * ALIQUOTA * MULT_INDIRETO

        # Gatilhos de Performance (Item 5)
        pode_usar = True if t <= 3 else ((receita/rec_ant - 1 >= 0.10) or (p['potec'] >= 15) or (p['patente'] <= t))

        # Cálculo da Renúncia (Item 3 e 6)
        if p['regime'] == "Lucro Presumido":
            base_orig = receita * PRESUNCAO
            base_red = max(base_orig * 0.25, base_orig - (m_dinamico * pd_total * f))
            renuncia_unitaria = (base_orig - base_red) * ALIQUOTA if pode_usar else 0
        else:
            # RETI-SME: Vouchers Progressivos
            if p['intensidade_pd'] >= 0.15 and pode_usar:
                renuncia_unitaria = pd_total * 0.40 * (min(p['intensidade_pd'], 0.30)/0.30) * f
            else: renuncia_unitaria = 0

        # Curva de Adesão Sigmóide
        firmas = p['n_firmas'] / (1 + np.exp(-1.2 * (t - 3)))
        ren_macro, ret_macro = (renuncia_unitaria * firmas) / 1000, (retorno_total * firmas) / 1000
        violation_last_year = ren_macro > p['teto_lrf']

        rows.append({
            "Ano": t, "Renúncia": ren_macro, "Retorno": ret_macro, 
            "Saldo": ret_macro - ren_macro, "M": m_dinamico, "F": f, "Adesão": int(firmas)
        })

    df = pd.DataFrame(rows)
    df["Acumulado"] = df["Saldo"].cumsum()
    return df

# ─────────────────────────────────────────────────────────────
# 3. INTERFACE SIDEBAR COMPLETA
# ─────────────────────────────────────────────────────────────

# Inicialização de Session State para Cenários
if 'm_val' not in st.session_state: st.session_state.m_val = 1.25
if 'e_val' not in st.session_state: st.session_state.e_val = -1.27

with st.sidebar:
    st.title("⚙️ Parâmetros")
    regime = st.selectbox("Regime Tributário", ["Lucro Presumido", "Simples Nacional (RETI-SME)"])
    n_firmas = st.number_input("Universo de Firmas", value=4500)
    t_lrf = st.slider("Teto LRF (R$ Bi/ano)", 0.5, 5.0, 2.2)
    
    st.subheader("🏢 Perfil da Firma")
    r_ini = st.number_input("Receita Inicial (R$ MM)", value=15.0)
    i_pd = st.slider("Intensidade P&D", 0.01, 0.40, 0.07)
    cresc = st.slider("Crescimento Anual", 0.0, 0.30, 0.12)
    p_tec = st.slider("PoTec (%)", 0, 50, 18)
    
    st.subheader("📈 Macro SPE")
    b_ptf = st.slider("β (Elasticidade PTF)", 0.05, 0.12, 0.06)
    m_base = st.slider("Multiplicador M Inicial", 1.0, 1.5, st.session_state.m_val)
    elast = st.slider("Elasticidade ε", -2.0, -0.5, st.session_state.e_val)

# Execução Base
params_base = {
    "regime": regime, "n_firmas": n_firmas, "rec_inicial": r_ini, "intensidade_pd": i_pd,
    "crescimento": cresc, "beta_ptf": b_ptf, "horizonte": 10, "potec": p_tec,
    "patente": 3, "teto_lrf": t_lrf, "mult_base": m_base, "elasticidade": elast
}
df = run_reti_engine(params_base)

# ─────────────────────────────────────────────────────────────
# 4. DASHBOARD PRINCIPAL
# ─────────────────────────────────────────────────────────────

st.title("🛡️ RETI Intelligence DSS")
st.caption("Decision Support System | Protocolo SPE/MF & RFB v10.90")

# KPIs Superiores
c1, c2, c3, c4 = st.columns(4)
total_ren = df["Renúncia"].sum()
total_ret = df["Retorno"].sum()
payback_df = df[df["Acumulado"] > 0]
payback_ano = payback_df["Ano"].min() if not payback_df.empty else "N/A"

c1.metric("Custo Total (10a)", f"R$ {total_ren:.2f} Bi")
c2.metric("Retorno PIB (PTF)", f"R$ {total_ret:.2f} Bi")
c3.metric("Payback Fiscal", f"Ano {payback_ano}")
c4.metric("Status LRF", "CONFORME" if df["Renúncia"].max() <= t_lrf else "AJUSTADO")

tabs = st.tabs(["📊 Fluxo Fiscal", "🎯 Sensibilidade", "⚖️ Compensação", "📋 Dados"])

with tabs[0]:
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Fluxo Anual (R$ Bi)")
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=df["Ano"], y=df["Renúncia"], name="Custo", line=dict(color=CORES['red'], width=4)))
        fig1.add_trace(go.Scatter(x=df["Ano"], y=df["Retorno"], name="Retorno", line=dict(color=CORES['cyan'], width=4)))
        fig1.add_hline(y=t_lrf, line_dash="dash", line_color=CORES['gold'], annotation_text="Teto LRF")
        fig1.update_layout(template="plotly_dark", height=350, margin=dict(l=10,r=10,t=30,b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig1, use_container_width=True)
    with col_b:
        st.subheader("Saldo Acumulado (R$ Bi)")
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=df["Ano"], y=df["Acumulado"], name="Saldo", fill='tozeroy', line=dict(color=CORES['green'], width=4), fillcolor='rgba(16, 185, 129, 0.2)'))
        fig2.add_hline(y=0, line_color="#FFFFFF")
        fig2.update_layout(template="plotly_dark", height=350, margin=dict(l=10,r=10,t=30,b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig2, use_container_width=True)

with tabs[1]:
    st.subheader("Matriz de Sensibilidade: ROI (%) por ε vs M")
    e_range = [-0.8, -1.0, -1.27, -1.5, -1.8]
    m_range = [1.0, 1.15, 1.25, 1.35, 1.5]
    matrix = []
    for e in e_range:
        row = []
        for m in m_range:
            p_sens = {**params_base, "elasticidade": e, "mult_base": m}
            df_s = run_reti_engine(p_sens)
            # Evita divisão por zero
            ren_sum = df_s["Renúncia"].sum()
            roi = (df_s["Retorno"].sum() / ren_sum - 1) * 100 if ren_sum > 0 else 0
            row.append(roi)
        matrix.append(row)
    
    fig_h = go.Figure(data=go.Heatmap(z=matrix, x=m_range, y=e_range, colorscale='RdYlGn', text=matrix, texttemplate="%{text:.1f}%"))
    fig_h.update_layout(template="plotly_dark", height=400, xaxis_title="Multiplicador M", yaxis_title="Elasticidade ε")
    st.plotly_chart(fig_h, use_container_width=True)

with tabs[2]:
    st.subheader("Fontes de Custeio (Item 7)")
    comp = {"Bets (GGR 12%→15%)": 850, "Reforma Administrativa": 600, "Corte Gastos Ineficientes": 450}
    fig_c = go.Figure(go.Bar(x=list(comp.keys()), y=list(comp.values()), marker_color=CORES['gold'], text=[f"R$ {v}M" for v in comp.values()], textposition='auto'))
    fig_c.add_hline(y=(total_ren/10)*1000, line_dash="dash", line_color=CORES['red'], annotation_text="Custo Médio Anual (R$ MM)")
    fig_c.update_layout(template="plotly_dark", height=350, yaxis_title="R$ Milhões")
    st.plotly_chart(fig_c, use_container_width=True)

with tabs[3]:
    st.subheader("Memória de Cálculo Detalhada")
    st.dataframe(df.style.format(precision=3), use_container_width=True)

# Cenários Estratégicos
st.markdown("---")
st.subheader("🎯 Cenários de Palatabilidade Fiscal")
c_cons, c_mod, c_agres = st.columns(3)

if c_cons.button("🟢 Conservador"):
    st.session_state.m_val = 1.10
    st.session_state.e_val = -0.9
    st.rerun()

if c_mod.button("🟡 Moderado"):
    st.session_state.m_val = 1.25
    st.session_state.e_val = -1.27
    st.rerun()

if c_agres.button("🟠 Agressivo"):
    st.session_state.m_val = 1.40
    st.session_state.e_val = -1.6
    st.rerun()

st.info("""
**Nota Metodológica:** 
1. **Adicionalidade:** Baseada em Kannebley (2016) com ε = -1,27. 
2. **PTF:** Transmissão via resíduo de Solow com β calibrado entre 0,05 e 0,08. 
3. **Neutralidade:** O sistema autoajustável (Item 7) garante que o teto LRF seja respeitado via compressão paramétrica automática.
""")

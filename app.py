import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="RETI - Simulador v3.0", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono&family=IBM+Plex+Sans:wght@300;400;600&display=swap');
    html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
    .stMetric { background: #f8f9fb; border: 1px solid #e6e9ef; padding: 15px; border-radius: 5px; }
    .mono { font-family: 'IBM Plex Mono', monospace; }
    </style>
    """, unsafe_allow_html=True)

# --- LÓGICA DE NEGÓCIO ---

def calcular_fator_f(receita_mm):
    """Implementa o Tapering Linear conforme item 3.2 da Proposta"""
    if receita_mm <= 3.24: return 3.5
    if receita_mm <= 78: return 2.5
    if receita_mm <= 200:
        # Redução linear: de 2.5 (em 78M) até 1.0 (em 200M)
        # coeficiente = (2.5 - 1.0) / (200 - 78) = 0.01229
        return max(1.0, 2.5 - 0.01229 * (receita_mm - 78))
    return 1.0

def motor_simulacao(p):
    anos = np.arange(1, p['anos'] + 1)
    rec = p['rec_inicial']
    df_lista = []
    estoque_credito = 0
    m_efetivo = p['mult_base']
    
    for t in anos:
        rec_ant = rec
        rec = rec * (1 + p['crescimento'])
        cresc_real = (rec/rec_ant) - 1
        f = calcular_fator_f(rec)
        
        # Cálculo do P&D
        pd_original = rec * p['intensidade_pd']
        # Adicionalidade baseada na elasticidade sobre o custo do benefício
        pd_adicional = pd_original * abs(p['elasticidade']) * (m_efetivo * f * 0.34)
        pd_total = pd_original + pd_adicional
        
        # Regra Tributária
        imp_referencia = (rec * 0.32) * 0.34
        limite_compensacao = imp_referencia * 0.50
        
        novo_credito = (m_efetivo * pd_total * f) * 0.34
        estoque_credito += novo_credito
        
        # Gatilho de Performance
        pode_compensar = True
        if t > 3:
            pode_compensar = (cresc_real >= 0.10) or (p['patente_ano'] <= t) or (p['potec'] > 15)
        
        uso_credito = min(estoque_credito, limite_compensacao) if pode_compensar else 0
        imp_final = max(imp_referencia * 0.25, imp_referencia - uso_credito)
        renuncia = imp_referencia - imp_final
        estoque_credito -= renuncia
        
        df_lista.append({
            'Ano': t, 'Receita': rec, 'Fator_F': f, 'PD_Total': pd_total, 
            'PD_Adicional': pd_adicional, 'Renuncia': renuncia, 
            'Estoque_Credito': estoque_credito, 'Imp_Final': imp_final,
            'Status': 'Ativo' if pode_compensar else 'Suspenso'
        })
        
    return pd.DataFrame(df_lista)

# --- SIDEBAR ---

with st.sidebar:
    st.header("🎛️ Parâmetros SPE/MF")
    
    with st.expander("📡 Universo Macro", expanded=True):
        n_firmas = st.slider("Universo de Firmas", 500, 10000, 4500)
        teto_fiscal = st.number_input("Teto Safe-Stop (R$ Bi)", value=2.2)
        mult_base = st.slider("Multiplicador M (Base)", 1.0, 1.6, 1.25)
        elast = st.slider("Elasticidade (ε)", -2.0, -0.5, -1.27)
        
    with st.expander("🏢 Firma Representativa"):
        rec_ini = st.slider("Receita Inicial (R$ MM)", 1, 300, 15)
        int_pd = st.slider("Intensidade P&D (%)", 1.0, 25.0, 7.0) / 100
        grow = st.slider("Crescimento Anual (%)", 0.0, 30.0, 12.0) / 100
        potec = st.slider("% Pessoal Científico", 5, 50, 18)
        pat_ano = st.slider("Ano do Depósito Patente", 1, 10, 2)

    anos_sim = st.slider("Horizonte (Anos)", 3, 15, 10)

# --- PROCESSAMENTO ---
p_sim = {
    'rec_inicial': rec_ini, 'intensidade_pd': int_pd, 'crescimento': grow,
    'elasticidade': elast, 'mult_base': mult_base, 'anos': anos_sim,
    'patente_ano': pat_ano, 'potec': potec
}

df_res = motor_simulacao(p_sim)
renuncia_macro = (df_res['Renuncia'].iloc[-1] * n_firmas) / 1000 

# --- DASHBOARD ---
st.title("RETI — Simulador de Política Econômica")
st.caption("v3.0 · Framework de Apoio à Decisão · Proposta Executiva SPE/MF")

# KPIs
k1, k2, k3, k4 = st.columns(4)
total_pd_adic = df_res['PD_Adicional'].sum()
total_renuncia = df_res['Renuncia'].sum()
roi_adic = total_pd_adic / total_renuncia if total_renuncia > 0 else 0

k1.metric("Renúncia Macro (Ano Final)", f"R$ {renuncia_macro:.2f} Bi")
# CORREÇÃO AQUI: de :.2x para :.2f com 'x' manual
k2.metric("Alavancagem (Invest/Renúncia)", f"{roi_adic:.2f}x")
k3.metric("M Efetivo", f"{mult_base:.2f}")
k4.metric("Status LRF", "⚠️ RISCO" if renuncia_macro > teto_fiscal else "✅ DENTRO", 
          delta=f"{((renuncia_macro/teto_fiscal)-1)*100:.1f}% vs Teto" if teto_fiscal > 0 else "0%")

# Gráficos
tab_firma, tab_macro, tab_tecnica = st.tabs(["🔍 Análise da Firma", "📊 Visão do Tesouro", "⚙️ Metodologia"])

with tab_firma:
    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        fig_pd = go.Figure()
        fig_pd.add_trace(go.Scatter(x=df_res['Ano'], y=df_res['PD_Total'], name="P&D com RETI", line=dict(color='#185FA5', width=3)))
        fig_pd.add_trace(go.Bar(x=df_res['Ano'], y=df_res['Renuncia'], name="Renúncia Fiscal", marker_color='#1D9E75', opacity=0.6))
        fig_pd.update_layout(title="Indução de P&D vs. Renúncia (R$ MM)", hovermode="x unified")
        st.plotly_chart(fig_pd, use_container_width=True)
    with col_f2:
        st.markdown("**Degressividade do Fator F**")
        fig_f = px.line(df_res, x='Ano', y='Fator_F', markers=True, color_discrete_sequence=['#BA7517'])
        st.plotly_chart(fig_f, use_container_width=True)

with tab_macro:
    st.subheader("Sustentabilidade e Impacto em Produtividade")
    df_res['Produtividade_Acum'] = (df_res['PD_Adicional'] / df_res['Receita']).cumsum() * 0.15
    fig_macro = make_subplots(specs=[[{"secondary_y": True}]])
    fig_macro.add_trace(go.Scatter(x=df_res['Ano'], y=df_res['Renuncia']*n_firmas/1000, name="Renúncia Total (Bi)", fill='tozeroy'), secondary_y=False)
    fig_macro.add_trace(go.Scatter(x=df_res['Ano'], y=df_res['Produtividade_Acum']*100, name="Ganho Produtividade (%)", line=dict(dash='dash', color='red')), secondary_y=True)
    fig_macro.update_layout(title="Projeção de Longo Prazo")
    st.plotly_chart(fig_macro, use_container_width=True)

with tab_tecnica:
    st.markdown(f"""
    ### Notas Técnicas
    1. **Tapering:** Transição suave de F=2.5 para F=1.0 para evitar o "Efeito Notch".
    2. **Gatilhos:** Bloqueio de carry-forward no Ano 4 se critérios de performance não forem atingidos.
    3. **Safe-Stop:** Mecanismo do Art. 5.2.3 para ajuste automático do multiplicador.
    """)

st.divider()
st.markdown("<center style='color:gray; font-size:10px;'>CRP Calibrado · IBGE/PINTEC · ε = -1.27</center>", unsafe_allow_html=True)

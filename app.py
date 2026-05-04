import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- CONFIGURAÇÃO DA PÁGINA (ESTILO IBM PLEX / SPE) ---
st.set_page_config(page_title="RETI - Simulador v3.0", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono&family=IBM+Plex+Sans:wght@300;400;600&display=swap');
    html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
    .stMetric { background: #f8f9fb; border: 1px solid #e6e9ef; padding: 15px; border-radius: 5px; }
    .mono { font-family: 'IBM Plex Mono', monospace; }
    </style>
    """, unsafe_allow_html=True)

# --- LÓGICA DE NEGÓCIO (RETI CORE) ---

def calcular_fator_f(receita_mm):
    """Implementa o Tapering Linear conforme item 3.2 da Proposta"""
    if receita_mm <= 3.24: return 3.5
    if receita_mm <= 78: return 2.5
    if receita_mm <= 200:
        return max(1.0, 2.5 - 0.012 * (receita_mm - 78))
    return 1.0

def motor_simulacao(p):
    """Simula o horizonte de tempo para uma firma e para o universo macro"""
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
        
        # Cálculo do P&D (Incentivado vs Original)
        pd_original = rec * p['intensidade_pd']
        # Elasticidade -1.27 aplicada sobre o custo marginal do P&D (M * F * tributação)
        pd_adicional = pd_original * abs(p['elasticidade']) * (m_efetivo * f * 0.34)
        pd_total = pd_original + pd_adicional
        
        # Regra Tributária RETI
        imp_referencia = (rec * 0.32) * 0.34
        limite_compensacao = imp_referencia * 0.50 # Trava de 50% Fluxo de Caixa
        
        novo_credito = (m_efetivo * pd_total * f) * 0.34
        estoque_credito += novo_credito
        
        # Gatilho de Performance (Item 6.3) - Ativo após ano 3
        pode_compensar = True
        if t > 3:
            pode_compensar = (cresc_real >= 0.10) or (p['patente_ano'] <= t) or (p['potec'] > 15)
        
        uso_credito = min(estoque_credito, limite_compensacao) if pode_compensar else 0
        imp_final = max(imp_referencia * 0.25, imp_referencia - uso_credito) # Cap de 25%
        renuncia = imp_referencia - imp_final
        estoque_credito -= renuncia
        
        df_lista.append({
            'Ano': t, 'Receita': rec, 'Fator_F': f, 'PD_Total': pd_total, 
            'PD_Adicional': pd_adicional, 'Renuncia': renuncia, 
            'Estoque_Credito': estoque_credito, 'Imp_Final': imp_final,
            'Status': 'Ativo' if pode_compensar else 'Suspenso'
        })
        
    return pd.DataFrame(df_lista)

# --- INTERFACE SIDEBAR (INPUTS CALIBRADOS) ---

with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/b/bb/Logo_Minist%C3%A9rio_da_Fazenda.png", width=150)
    st.header("🎛️ Parâmetros de Simulação")
    
    with st.expander("📡 Universo Macro (SPE)", expanded=True):
        n_firmas = st.slider("Universo de Firmas", 500, 10000, 4500)
        teto_fiscal = st.number_input("Teto Safe-Stop (R$ Bi)", value=2.2)
        mult_base = st.slider("Multiplicador M (Base)", 1.0, 1.5, 1.25)
        elast = st.slider("Elasticidade (ε)", -2.0, -0.5, -1.27)
        
    with st.expander("🏢 Perfil da Firma Representativa"):
        rec_ini = st.slider("Receita Inicial (R$ MM)", 1, 300, 15)
        int_pd = st.slider("Intensidade P&D (%)", 1.0, 25.0, 7.0) / 100
        grow = st.slider("Crescimento Anual (%)", 0.0, 30.0, 12.0) / 100
        potec = st.slider("% Pessoal Científico", 5, 50, 18)
        pat_ano = st.slider("Ano do Depósito Patente", 1, 10, 2)

    anos_sim = st.sidebar.slider("Horizonte Temporal (Anos)", 3, 15, 10)

# --- PROCESSAMENTO ---
p_sim = {
    'rec_inicial': rec_ini, 'intensidade_pd': int_pd, 'crescimento': grow,
    'elasticidade': elast, 'mult_base': mult_base, 'anos': anos_sim,
    'patente_ano': pat_ano, 'potec': potec
}

df_res = motor_simulacao(p_sim)
renuncia_macro = (df_res['Renuncia'].iloc[-1] * n_firmas) / 1000 # R$ Bilhões

# --- DASHBOARD PRINCIPAL ---
st.title("RETI — Simulador de Política Econômica")
st.caption("v3.0 · Framework de Apoio à Decisão · Baseado no Manual de Frascati & LRF")

# Linha 1: KPIs de Decisão
k1, k2, k3, k4 = st.columns(4)
roi_adic = df_res['PD_Adicional'].sum() / df_res['Renuncia'].sum()

k1.metric("Impacto Fiscal Macro (Ano Final)", f"R$ {renuncia_macro:.2f} Bi")
k2.metric("Alavancagem (Investimento/Renúncia)", f"{roi_adic:.2x}")
k3.metric("M Efetivo (Safe-Stop)", f"{mult_base:.2f}")
k4.metric("Status LRF", "⚠️ RISCO" if renuncia_macro > teto_fiscal else "✅ DENTRO", 
          delta=f"{((renuncia_macro/teto_fiscal)-1)*100:.1f}% vs Teto")

# Linha 2: Gráficos de Análise de Impacto
tab_firma, tab_macro, tab_tecnica = st.tabs(["🔍 Análise da Firma", "📊 Visão do Tesouro", "⚙️ Metodologia"])

with tab_firma:
    col_f1, col_f2 = st.columns([2, 1])
    
    with col_f1:
        fig_pd = go.Figure()
        fig_pd.add_trace(go.Scatter(x=df_res['Ano'], y=df_res['PD_Total'], name="P&D com RETI", line=dict(color='#185FA5', width=3)))
        fig_pd.add_trace(go.Bar(x=df_res['Ano'], y=df_res['Renuncia'], name="Incentivo Fiscal", marker_color='#1D9E75', opacity=0.6))
        fig_pd.update_layout(title="Indução de P&D vs. Renúncia (R$ MM)", hovermode="x unified", legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig_pd, use_container_width=True)
        
    with col_f2:
        st.markdown("**Comportamento do Fator F**")
        fig_f = px.line(df_res, x='Ano', y='Fator_F', markers=True, color_discrete_sequence=['#BA7517'])
        fig_f.update_layout(height=300)
        st.plotly_chart(fig_f, use_container_width=True)

with tab_macro:
    st.subheader("Projeção de Longo Prazo e Externalidade Positiva")
    
    # Cálculo de Ganho de Produtividade Acumulado
    df_res['Produtividade_Acum'] = (df_res['PD_Adicional'] / df_res['Receita']).cumsum() * 0.15
    
    fig_macro = make_subplots(specs=[[{"secondary_y": True}]])
    fig_macro.add_trace(go.Scatter(x=df_res['Ano'], y=df_res['Renuncia']*n_firmas/1000, name="Renúncia Macro (Bi)", fill='tozeroy'), secondary_y=False)
    fig_macro.add_trace(go.Scatter(x=df_res['Ano'], y=df_res['Produtividade_Acum'], name="Ganho Produtividade (%)", line=dict(dash='dash', color='red')), secondary_y=True)
    
    fig_macro.update_layout(title="Sustentabilidade: Renúncia vs. Ganhos de Eficiência", legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig_macro, use_container_width=True)

with tab_tecnica:
    st.markdown(f"""
    ### Notas Técnicas para a SPE/MF
    
    1. **Mecanismo Safe-Stop:** Se a renúncia projetada excede **R$ {teto_fiscal} Bi**, o modelo sugere a redução imediata do multiplicador M de {mult_base} para o próximo ciclo.
    2. **Gatilhos de Performance:** O simulador suspende o carry-forward no Ano 4 se a firma não atingir:
        - Crescimento de Receita > 10% aa;
        - OU Manutenção de PoTec > 15%;
        - OU Depósito de Patente (Ano {pat_ano}).
    3. **Tapering Linear:** A transição linear entre R$ 78M e R$ 200M elimina o efeito de "freio de crescimento" presente na Lei do Bem.
    4. **Elasticidade-Custo:** Baseada em Kannebley Jr. (2016), estimando adicionalidade real de R$ {abs(elast)} para cada R$ 1,00 renunciado.
    """)

# Rodapé de Auditoria
st.divider()
st.markdown(f"<div style='text-align: center; color: gray; font-size: 10px;'>Cálculo Base: Manual de Oslo/Frascati · Estresse Paramétrico: ε={elast} · Teto LRF: R$ {teto_fiscal} Bi</div>", unsafe_allow_html=True)

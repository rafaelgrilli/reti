import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- CONFIGURAÇÃO DE INTERFACE ---
st.set_page_config(page_title="RETI - Decision Support System", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono&family=IBM+Plex+Sans:wght@300;400;600&display=swap');
    html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
    .stMetric { background: #f1f3f6; border-left: 5px solid #185FA5; padding: 15px; border-radius: 4px; }
    .reportview-container { background: #fafafa; }
    </style>
    """, unsafe_allow_html=True)

# --- MOTOR DE CÁLCULO AVANÇADO ---

def calcular_fator_f(receita_mm):
    """Tapering Linear: Transição suave para evitar o efeito Notch"""
    if receita_mm <= 3.24: return 3.5
    if receita_mm <= 78: return 2.5
    if receita_mm <= 200:
        return max(1.0, 2.5 - 0.01229 * (receita_mm - 78))
    return 1.0

def motor_reti_pro(p):
    anos_total = p['anos']
    lag = 3  # Anos para o P&D virar produtividade
    deprec = 0.15 # Depreciação anual do estoque de conhecimento
    
    rec = p['rec_inicial']
    estoque_conhecimento = 0
    estoque_credito_fiscal = 0
    
    # Histórico para gerenciar o Lag de maturação
    historico_pd_adic = [0] * (anos_total + lag + 1)
    resultados = []

    for t in range(1, anos_total + 1):
        # 1. Dinâmica de Receita e Fator F
        rec_ant = rec
        rec = rec * (1 + p['crescimento'])
        f = calcular_fator_f(rec)
        
        # 2. P&D e Adicionalidade (Efeito Preço)
        pd_original = rec * p['intensidade_pd']
        # Adicionalidade baseada na elasticidade-custo (ε)
        pd_adicional = pd_original * abs(p['elasticidade']) * (p['mult_base'] * f * 0.34)
        pd_total = pd_original + pd_adicional
        
        # Armazena P&D adicional para maturação futura
        if t + lag <= anos_total:
            historico_pd_adic[t + lag] = pd_adicional
            
        # 3. Acúmulo de Produtividade (Modelo de Estoque)
        pd_maturado = historico_pd_adic[t]
        estoque_conhecimento = (estoque_conhecimento * (1 - deprec)) + pd_maturado
        
        # Ganho de produtividade (Elasticidade P&D/Produtividade estimada em 0.08)
        ganho_prod = (estoque_conhecimento / rec) * 0.08 if rec > 0 else 0
        
        # 4. Retorno Fiscal Indireto (O que volta para o cofre via lucro extra)
        retorno_indireto = (rec * ganho_prod) * 0.34
        
        # 5. Cálculo da Renúncia RETI (Fluxo de Caixa Fiscal)
        imp_ref = (rec * 0.32) * 0.34
        limite_comp = imp_ref * 0.50 # Trava de 50%
        
        novo_credito = (p['mult_base'] * pd_total * f) * 0.34
        estoque_credito_fiscal += novo_credito
        
        # Gatilho de Performance (Item 6.3)
        pode_usar = True
        if t > 3:
            pode_usar = ((rec/rec_ant - 1) >= 0.10) or (p['patente_ano'] <= t) or (p['potec'] > 15)
            
        uso_credito = min(estoque_credito_fiscal, limite_comp) if pode_usar else 0
        imp_final = max(imp_ref * 0.25, imp_ref - uso_credito) # Cap 25%
        renuncia = imp_ref - imp_final
        estoque_credito_fiscal -= renuncia
        
        resultados.append({
            'Ano': t,
            'Receita': rec,
            'Renuncia': renuncia,
            'Retorno_Indireto': retorno_indireto,
            'Saldo_Fiscal_Neto': retorno_indireto - renuncia,
            'Ganho_Prod_Pct': ganho_prod * 100,
            'PD_Total': pd_total,
            'Fator_F': f,
            'Status': 'Ativo' if pode_usar else 'Suspenso'
        })
        
    return pd.DataFrame(resultados)

# --- INTERFACE ---

st.title("🏛️ RETI: Simulador de Impacto de Longo Prazo")
st.caption("Versão 4.0 - Modelo de Maturação de P&D e Sustentabilidade Fiscal")

with st.sidebar:
    st.header("Configurações Estratégicas")
    
    with st.expander("📊 Parâmetros Macro (SPE/MF)", expanded=True):
        n_firmas = st.number_input("Universo de Firmas", value=4500)
        teto_lrf = st.slider("Teto LRF (R$ Bi)", 1.0, 5.0, 2.2)
        mult = st.slider("Multiplicador M", 1.0, 1.5, 1.25)
        elast = st.slider("Elasticidade (ε)", -2.0, -0.5, -1.27)
        
    with st.expander("🏢 Perfil da Firma"):
        rec_ini = st.number_input("Receita Inicial (R$ MM)", value=15.0)
        int_pd = st.slider("Intensidade P&D (%)", 1.0, 20.0, 7.0) / 100
        cresc = st.slider("Crescimento Anual (%)", 0.0, 25.0, 12.0) / 100
        potec = st.slider("% Pessoal Técnico", 5, 40, 18)
        patente = st.slider("Ano Depósito Patente", 1, 10, 3)

    horizonte = st.slider("Horizonte de Análise (Anos)", 5, 15, 10)

# --- PROCESSAMENTO ---
params = {
    'anos': horizonte, 'rec_inicial': rec_ini, 'crescimento': cresc,
    'intensidade_pd': int_pd, 'elasticidade': elast, 'mult_base': mult,
    'patente_ano': patente, 'potec': potec
}

df = motor_reti_pro(params)

# --- DASHBOARD ---

# KPIs Superiores
k1, k2, k3, k4 = st.columns(4)
renuncia_final = (df['Renuncia'].iloc[-1] * n_firmas) / 1000
retorno_final = (df['Retorno_Indireto'].iloc[-1] * n_firmas) / 1000
payback_ano = df[df['Saldo_Fiscal_Neto'] > 0]['Ano'].min()

k1.metric("Custo Fiscal (Ano Final)", f"R$ {renuncia_final:.2f} Bi")
k2.metric("Retorno Indireto (Ano Final)", f"R$ {retorno_final:.2f} Bi")
k3.metric("Payback Fiscal (Ano)", f"Ano {payback_ano}" if pd.notnull(payback_ano) else "N/A")
k4.metric("Status LRF", "✅ OK" if renuncia_final <= teto_lrf else "⚠️ RISCO", 
          delta=f"{renuncia_final - teto_lrf:.2f} Bi vs Teto")

t1, t2, t3 = st.tabs(["📈 Sustentabilidade Fiscal", "🏢 Visão da Firma", "📚 Metodologia"])

with t1:
    st.subheader("O 'Trade-off' Fiscal: Renúncia vs. Arrecadação por Produtividade")
    
    fig_macro = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Renúncia (Saída)
    fig_macro.add_trace(go.Bar(x=df['Ano'], y=df['Renuncia']*n_firmas/1000, 
                               name="Renúncia Fiscal (Custo)", marker_color='#E24B4A', opacity=0.7), secondary_y=False)
    
    # Retorno Indireto (Entrada)
    fig_macro.add_trace(go.Scatter(x=df['Ano'], y=df['Retorno_Indireto']*n_firmas/1000, 
                                   name="Retorno Indireto (Ganho)", line=dict(color='#1D9E75', width=4)), secondary_y=False)
    
    # Linha de Produtividade
    fig_macro.add_trace(go.Scatter(x=df['Ano'], y=df['Ganho_Prod_Pct'], 
                                   name="Ganho Produtividade (%)", line=dict(color='#BA7517', dash='dot')), secondary_y=True)
    
    fig_macro.update_layout(legend=dict(orientation="h", y=1.1), hovermode="x unified")
    fig_macro.update_yaxes(title_text="R$ Bilhões", secondary_y=False)
    fig_macro.update_yaxes(title_text="Produtividade (%)", secondary_y=True)
    
    st.plotly_chart(fig_macro, use_container_width=True)
    
    st.info(f"""
    **Análise de Sustentabilidade:** Observe que nos primeiros {lag} anos o retorno é quase nulo devido ao tempo de maturação tecnológica. 
    O 'Breakeven' fiscal ocorre quando a linha verde cruza a barra vermelha. 
    Neste cenário, o governo recupera o investimento via aumento da base tributária gerada pela eficiência das firmas.
    """)

with t2:
    c1, c2 = st.columns(2)
    with c1:
        st.write("**Fluxo de Caixa da Firma (R$ MM)**")
        fig_firma = go.Figure()
        fig_firma.add_trace(go.Scatter(x=df['Ano'], y=df['PD_Total'], name="P&D Total", fill='tozeroy'))
        fig_firma.add_trace(go.Scatter(x=df['Ano'], y=df['Renuncia'], name="Incentivo RETI", fill='tonexty'))
        st.plotly_chart(fig_firma, use_container_width=True)
    with c2:
        st.write("**Evolução do Fator F (Tapering)**")
        st.line_chart(df.set_index('Ano')['Fator_F'])
    
    st.dataframe(df[['Ano', 'Receita', 'PD_Total', 'Renuncia', 'Ganho_Prod_Pct', 'Status']].style.format(precision=2))

with t3:
    st.markdown(f"""
    ### Premissas do Modelo Avançado
    1. **Time-Lag de Maturação ({lag} anos):** O P&D investido no Ano 1 só começa a impactar a produtividade no Ano 4. Isso reflete o ciclo real de inovação (P&D -> Protótipo -> Mercado -> Eficiência).
    2. **Depreciação de Conhecimento (15% aa):** O estoque de inovação perde valor ao longo do tempo. Para manter o ganho de produtividade, a firma precisa inovar continuamente.
    3. **Transmissão Produtividade -> Fiscal:** O modelo assume que cada 1% de ganho de produtividade se traduz em aumento de lucro operacional, tributado a 34% (IRPJ/CSLL).
    4. **Safe-Stop:** O multiplicador M ({mult}) é a alavanca principal. Se o custo fiscal no Ano {horizonte} exceder R$ {teto_lrf} Bi, a política exige recalibragem.
    """)

st.divider()
st.markdown("<center style='color:gray; font-size:10px;'>Simulador RETI v4.0 | Desenvolvido para SPE/MF | Baseado em Kannebley Jr. (2016) e Manual de Frascati</center>", unsafe_allow_html=True)

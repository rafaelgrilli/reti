import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# Configuração da Página
st.set_page_config(page_title="Impacto Fiscal Consolidado RETI", layout="wide")

st.title("🏛️ Análise de Impacto Fiscal Consolidado (10 Anos)")
st.markdown("""
Esta simulação apresenta o **impacto acumulado para a União**, comparando o gasto tributário atual da 
**Lei do Bem** com a proposta do **RETI**, considerando o universo de empresas brasileiras.
""")

# --- SIDEBAR: CONFIGURAÇÃO DE ESCALA NACIONAL ---
st.sidebar.header("📊 Escala do Ecossistema")

universo_empresas = st.sidebar.number_input(
    "Número de Empresas (Universo Alvo)", 
    value=5000, 
    step=100,
    help="Estimativa de quantas empresas (Startups + Deep Techs + Maduras) utilizarão o regime no Brasil."
)

# --- PREMISSAS DETALHADAS ---
with st.sidebar.expander("Calibragem Lei do Bem (Histórico Real)", expanded=True):
    renuncia_media_anual_por_cnpj = st.number_input(
        "Renúncia Média Anual Lei do Bem (por CNPJ - R$)", 
        value=1200000.0, 
        step=50000.0,
        help="Baseado no histórico do MCTI, cada empresa no Lucro Real economiza em média este valor em impostos."
    )

with st.sidebar.expander("Parâmetros do Modelo RETI", expanded=True):
    fator_f_medio = st.slider("Fator F Médio do Ecossistema", 1.0, 3.5, 2.5,
                              help="Média do Fator F ponderada entre Startups (3.5) e Empresas Maduras (1.0).")
    tax_rate = 0.34  # IRPJ (25%) + CSLL (9%)
    lambda_pib = st.sidebar.slider("Coeficiente de Produtividade (λ)", 0.01, 0.20, 0.08,
                                   help="Retorno indireto na arrecadação via crescimento do PIB setorial.")

# --- LÓGICA DE CÁLCULO MACRO ---
anos = list(range(1, 11))
dados_macro = []

# Loop de Simulação Temporal
for t in anos:
    # 1. LEI DO BEM (Projeção Baseada em Dados Reais)
    # Valor total anual em Bilhões = (Média por CNPJ * Total Empresas * Inflação/Crescimento) / 1 Bilhão
    total_renuncia_bem_ano = (renuncia_media_anual_por_cnpj * universo_empresas * (1.045 ** t)) / 1e9
    
    # 2. RETI (Proposta Nova)
    # Considera investimento médio em P&D nacional por empresa
    investimento_pd_nacional_medio = 600000.0 * (1.10 ** t) # Cresce 10% ao ano
    
    # Impacto RETI em Bilhões = (P&D * Superdedução 1.6 * Fator F * Alíquota * Empresas) / 1 Bilhão
    total_renuncia_reti_ano = (investimento_pd_nacional_medio * 1.6 * fator_f_medio * tax_rate * universo_empresas) / 1e9
    
    # 3. RETORNO FISCAL (Efeito multiplicador)
    ganho_arrecadacao_indireta = (investimento_pd_nacional_medio * universo_empresas * lambda_pib * tax_rate) / 1e9

    dados_macro.append({
        "Ano": t,
        "Renúncia Lei do Bem (Bi R$)": total_renuncia_bem_ano,
        "Renúncia RETI (Bi R$)": total_renuncia_reti_ano,
        "Arrecadação Indireta (Bi R$)": ganho_arrecadacao_indireta
    })

df_macro = pd.DataFrame(dados_macro)

# --- DASHBOARD EXECUTIVO ---
col1, col2, col3 = st.columns(3)

total_bem_10a = df_macro["Renúncia Lei do Bem (Bi R$)"].sum()
total_reti_10a = df_macro["Renúncia RETI (Bi R$)"].sum()
total_ret_10a = df_macro["Arrecadação Indireta (Bi R$)"].sum()

col1.metric("Custo Lei do Bem (10 Anos)", f"R$ {total_bem_10a:,.2f} Bi")
col2.metric("Custo RETI (10 Anos)", f"R$ {total_reti_10a:,.2f} Bi")
col3.metric("ROI Fiscal (Retorno/Custo)", f"{(total_ret_10a/total_reti_10a):.2f}x")

# Gráficos
st.write("### Comparativo de Trajetória Fiscal (Bilhões de R$)")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df_macro["Ano"], y=df_macro["Renúncia RETI (Bi R$)"], 
                         name="RETI (Proposta)", fill='tozeroy', line=dict(color='firebrick', width=3)))
fig.add_trace(go.Scatter(x=df_macro["Ano"], y=df_macro["Renúncia Lei do Bem (Bi R$)"], 
                         name="Lei do Bem (Atual)", line=dict(color='blue', dash='dash')))
st.plotly_chart(fig, use_container_width=True)

st.write("### Tabela Consolidada (Valores em R$ Bilhões)")
st.table(df_macro.style.format("{:,.2f}"))

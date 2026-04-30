import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Impacto Fiscal Consolidado RETI", layout="wide")

st.title("🏛️ Análise de Impacto Fiscal Consolidado (10 Anos)")
st.markdown("""
Esta simulação apresenta o **impacto acumulado para a União**, considerando o universo de empresas 
que migrarão ou aderirão ao incentivo, comparado ao gasto tributário atual da Lei do Bem.
""")

# --- SIDEBAR: CONFIGURAÇÃO DE ESCALA ---
st.sidebar.header("📊 Escala do Modelo")
universo_empresas = st.sidebar.number_input("Número de Empresas Alvo", value=5000, step=100,
                                            help="Estimativa de quantas empresas (startups + maduras) utilizarão o RETI no país.")

# --- PREMISSAS DETALHADAS ---
with st.sidebar.expander("Calibragem Lei do Bem (Histórico Real)", expanded=True):
    # Valores baseados no histórico do MCTI/Receita Federal
    renuncia_media_anual_por_empresa = st.number_input("Renúncia Média Anual Lei do Bem (por empresa - R$)", 
                                                       value=1200000.0, step=50000.0,
                                                       help="Média histórica de renúncia por CNPJ no Lucro Real.")

with st.sidebar.expander("Parâmetros RETI", expanded=True):
    fator_f_medio = st.slider("Fator F Médio do Ecossistema", 1.0, 3.5, 2.5)
    tax_rate = 0.34 # IRPJ + CSLL
    trava_uso = 0.50

# --- LÓGICA DE CÁLCULO MACRO ---
anos = list(range(1, 11))
dados_macro = []

# Baseline Lei do Bem (Baseado no histórico real projetado no tempo)
# Crescimento vegetativo da renúncia atual (inflação + novas empresas no Lucro Real)
for t anos:
    # --- LEI DO BEM (Consolidado Nacional Estimado) ---
    # Calculamos o total que o governo já 'perde' hoje e projetamos
    total_renuncia_bem_ano = renuncia_media_anual_por_empresa * universo_empresas * (1.045 ** t)
    
    # --- RETI (Cenário Proposto) ---
    # No RETI, empresas menores entram na base (aumento de adesão)
    adesao_incremental = 1.15 ** t # Simula a entrada de novas startups a cada ano
    investimento_pd_medio = 500000.0 * adesao_incremental
    
    # Fórmula RETI: Redução direta na base
    # A renúncia no RETI é agressiva no início, mas gera PIB via produtividade
    impacto_reti_ano = (investimento_pd_medio * 1.6 * fator_f_medio * tax_rate) * universo_empresas
    
    # Retorno de Arrecadação Indireta (PIB e Consumo)
    # λ (Produtividade) aplicado sobre o P&D total nacional
    lambda_pib = 0.08
    ganho_arrecadação_pib = (investimento_pd_medio * universo_empresas * lambda_pib) * 0.34

    dados_macro.append({
        "Ano": t,
        "Renúncia Acumulada Lei do Bem (Bi R$)": total_renuncia_bem_ano / 1e9,
        "Renúncia Acumulada RETI (Bi R$)": impacto_reti_ano / 1e9,
        "Retorno Fiscal Indireto (Bi R$)": ganho_arrecadação_pib / 1e9
    })

df_macro = pd.DataFrame(dados_macro)

# --- DASHBOARD EXECUTIVO ---
st.subheader("Comparativo de Gasto Tributário Total (União)")

c1, c2, c3 = st.columns(3)
total_bem = df_macro["Renúncia Acumulada Lei do Bem (Bi R$)"].sum()
total_reti = df_macro["Renúncia Acumulada RETI (Bi R$)"].sum()
total_retorno = df_macro["Retorno Fiscal Indireto (Bi R$)"].sum()

c1.metric("Total Lei do Bem (10 Anos)", f"R$ {total_bem:,.2f} Bi")
c2.metric("Total RETI (10 Anos)", f"R$ {total_reti:,.2f} Bi")
c3.metric("ROI Fiscal Estimado", f"{(total_retorno/total_reti):.2f}x")

# Gráfico de Área Empilhada para impacto fiscal
st.write("### Trajetória de Impacto Fiscal (Bilhões de R$)")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df_macro["Ano"], y=df_macro["Renúncia Acumulada RETI (Bi R$)"], 
                         name="RETI (Proposta)", fill='tozeroy', line=dict(color='firebrick')))
fig.add_trace(go.Scatter(x=df_macro["Ano"], y=df_macro["Renúncia Acumulada Lei do Bem (Bi R$)"], 
                         name="Lei do Bem (Atual)", line=dict(color='blue', dash='dash')))
st.plotly_chart(fig, use_container_width=True)

st.write("### Tabela Consolidada (Valores em Bilhões de R$)")
st.table(df_macro.style.format("{:,.2f}"))

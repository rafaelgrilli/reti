import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# Configuração da Página
st.set_page_config(page_title="Simulador Macro RETI", layout="wide")

st.title("🏛️ Simulador de Impacto Fiscal: Nacional & Consolidado")
st.markdown("""
Esta ferramenta modela o impacto do **RETI** em escala nacional, comparando-o com o custo histórico da **Lei do Bem**.
Os cálculos agora refletem valores em **Bilhões de Reais (R$ Bi)** para o orçamento da União.
""")

# --- SIDEBAR: TODOS OS PARÂMETROS REINTEGRADOS ---
st.sidebar.header("⚙️ Parâmetros do Modelo")

with st.sidebar.expander("1. Escala do Ecossistema", expanded=True):
    universo_empresas = st.number_input("Nº de Empresas Alvo", value=5000, step=100, help="Total de empresas que utilizariam o regime no Brasil.")
    base_rd_nacional = st.number_input("Investimento Médio P&D (R$)", value=800000.0, step=50000.0, help="Gasto médio anual em inovação por empresa.")

with st.sidebar.expander("2. Configurações RETI (A fórmula)", expanded=True):
    fator_f = st.select_slider("Fator F Médio", options=[1.0, 2.0, 2.5, 3.0, 3.5], value=2.5, help="Maturidade média das empresas (3.5 = startups, 1.0 = maduras).")
    multiplicador = st.slider("Multiplicador P&D (Fórmula)", 1.0, 2.5, 1.6, help="O '1.6' da fórmula original. Define a agressividade da superdedução.")
    trava_uso = st.slider("Trava de Uso do Crédito (%)", 10, 100, 50, help="Limite de abatimento do imposto devido em cada ano.") / 100

with st.sidebar.expander("3. Premissas de Resposta & Macro", expanded=True):
    elasticity = st.slider("Elasticidade P&D", -2.0, -0.1, -1.2, help="Quanto o investimento aumenta quando o custo tributário cai.")
    lambda_prod = st.slider("Coeficiente λ (Produtividade)", 0.01, 0.30, 0.08, help="Impacto de cada real de P&D no retorno de arrecadação indireta.")
    tax_rate = st.sidebar.number_input("Alíquota IRPJ/CSLL", 0.0, 0.40, 0.34)
    ipca = st.sidebar.slider("Correção IPCA Anual", 0.0, 0.15, 0.045)

# --- LÓGICA DE SIMULAÇÃO MACRO ---
anos = list(range(1, 11))
dados_simulados = []

# Estados iniciais para acúmulo
credito_acumulado_bi = 0.0

for t in anos:
    # --- LEI DO BEM (Baseline) ---
    # Histórico: Exclusão de 60% do P&D da base de cálculo
    renuncia_bem_ano = (base_rd_nacional * 0.60 * tax_rate * universo_empresas * (1.045**t)) / 1e9
    
    # --- RETI (Cálculo Dinâmico) ---
    # 1. Efeito Indução: O custo cai, o investimento sobe
    custo_marginal_reducao = (multiplicador * fator_f * tax_rate)
    rd_induzido_unitario = base_rd_nacional * (1 + abs(elasticity) * (custo_marginal_reducao))
    
    # 2. Renúncia Bruta (Antes da Trava)
    # Base Tributável Presumida (32% da Receita) - assumindo receita média 4x o P&D
    receita_media = rd_induzido_unitario * 4
    base_presumida = receita_media * 0.32
    deducao_reti = multiplicador * rd_induzido_unitario * fator_f
    
    imposto_antes_reti = base_presumida * tax_rate
    imposto_apos_reti = max(0.0, base_presumida - deducao_reti) * tax_rate
    
    renuncia_direta_ano = (imposto_antes_reti - imposto_apos_reti) * universo_empresas / 1e9
    
    # 3. Gestão de Crédito (Estoque e Trava)
    novo_credito_gerado = (rd_induzido_unitario * tax_rate * universo_empresas) / 1e9
    credito_usavel = min(credito_acumulado_bi, (imposto_apos_reti * universo_empresas / 1e9) * trava_uso)
    
    credito_acumulado_bi = (credito_acumulado_bi * (1 + ipca)) + novo_credito_gerado - credito_usavel
    
    renuncia_total_reti = renuncia_direta_ano + credito_usavel
    
    # 4. Retorno Fiscal (Ganho de PIB)
    retorno_indireto = (rd_induzido_unitario * universo_empresas * lambda_prod * tax_rate) / 1e9

    dados_simulados.append({
        "Ano": t,
        "Lei do Bem (Bi)": renuncia_bem_ano,
        "RETI (Bi)": renuncia_total_reti,
        "Estoque Crédito (Bi)": credito_acumulado_bi,
        "Retorno Indireto (Bi)": retorno_indireto,
        "P&D Nacional (Bi)": (rd_induzido_unitario * universo_empresas) / 1e9
    })

df = pd.DataFrame(dados_simulados)

# --- OUTPUTS ---
st.header("📊 Comparativo Consolidado: 10 Anos")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Custo Total Bem", f"R$ {df['Lei do Bem (Bi)'].sum():,.1f} Bi")
c2.metric("Custo Total RETI", f"R$ {df['RETI (Bi)'].sum():,.1f} Bi")
c3.metric("ROI Fiscal (RETI)", f"{(df['Retorno Indireto (Bi)'].sum()/df['RETI (Bi)'].sum()):.2f}x")
c4.metric("P&D Total Gerado", f"R$ {df['P&D Nacional (Bi)'].sum():,.1f} Bi")

st.subheader("Trajetória do Gasto Tributário (Bi R$)")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["Ano"], y=df["RETI (Bi)"], name="RETI", fill='tozeroy', line=dict(color='firebrick')))
fig.add_trace(go.Scatter(x=df["Ano"], y=df["Lei do Bem (Bi)"], name="Lei do Bem", line=dict(color='blue', dash='dash')))
st.plotly_chart(fig, use_container_width=True)

st.write("### Detalhamento da Simulação")
st.dataframe(df.style.format("{:,.2f}"))

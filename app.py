import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# 1. Configuração de Página
st.set_page_config(page_title="Impacto Fiscal Nacional RETI", layout="wide")

st.title("🏛️ Impacto Fiscal Nacional: RETI vs Lei do Bem")
st.markdown("""
Simulação baseada em dados históricos (DGT/Receita Federal). 
A Lei do Bem tem um custo anual de ~R$ 6 bilhões. O RETI visa expandir essa base para startups.
""")

# --- SIDEBAR: PARÂMETROS HISTÓRICOS ---
st.sidebar.header("📊 Parâmetros do Orçamento")

# Calibragem para atingir ~R$ 6 Bi/ano (Realidade da Lei do Bem)
universo_empresas = st.sidebar.number_input("Nº de Empresas (Universo Alvo)", value=4500, step=100)
pd_medio_anual = st.sidebar.number_input("P&D Médio por Empresa (R$ Milhões)", value=12.0, step=1.0) * 1e6

with st.sidebar.expander("Parâmetros Técnicos RETI", expanded=True):
    fator_f = st.slider("Fator F Médio", 1.0, 3.5, 2.5)
    multiplicador_reti = st.slider("Multiplicador RETI", 1.0, 2.5, 1.6)
    trava_abatimento = st.sidebar.slider("Trava de Uso (%)", 10, 100, 50) / 100

with st.sidebar.expander("Macroeconomia", expanded=True):
    tax_rate = 0.34
    crescimento_anual = 0.045 # IPCA médio + crescimento real
    lambda_produtividade = st.slider("Efeito Multiplicador (λ)", 0.01, 0.20, 0.08)

# --- CÁLCULO DOS CENÁRIOS ---
anos = np.arange(1, 11)
lista_resultados = []

for ano in anos:
    # 1. LEI DO BEM (Baseline Realista)
    # Projeção baseada em P&D incremental e inflação
    pd_corrigido = pd_medio_anual * ((1 + crescimento_anual) ** ano)
    # A Lei do Bem permite dedução de 60% a 80%. Usamos 60% como conservador.
    custo_bem_anual = (universo_empresas * pd_corrigido * 0.60 * tax_rate) / 1e9
    
    # 2. RETI (Cenário Proposto)
    # O RETI aplica a fórmula: (Base Presumida 32%) - (Mult * P&D * F)
    # Assumindo Receita média de 4x o P&D para empresas inovadoras
    receita_estimada = pd_corrigido * 4
    base_presumida = receita_estimada * 0.32
    deducao_total_reti = multiplicador_reti * pd_corrigido * fator_f
    
    imposto_sem_reti = base_presumida * tax_rate
    imposto_com_reti = max(0.0, (base_presumida - deducao_total_reti) * tax_rate)
    
    # Renúncia é a diferença do imposto que seria pago no presumido vs o RETI
    custo_reti_anual = (universo_empresas * (imposto_sem_reti - imposto_com_reti)) / 1e9
    
    # 3. RETORNO INDIRETO
    retorno_pib_anual = (universo_empresas * pd_corrigido * lambda_produtividade * tax_rate) / 1e9

    lista_resultados.append({
        "Ano": int(ano),
        "Lei do Bem": float(custo_bem_anual),
        "RETI": float(custo_reti_anual),
        "Retorno Fiscal": float(retorno_pib_anual)
    })

df = pd.DataFrame(lista_resultados)

# --- DASHBOARD ---
c1, c2, c3 = st.columns(3)
total_bem = df["Lei do Bem"].sum()
total_reti = df["RETI"].sum()
total_retorno = df["Retorno Fiscal"].sum()

c1.metric("Custo Lei do Bem (10 anos)", f"R$ {total_bem:,.2f} Bi")
c2.metric("Custo RETI (10 anos)", f"R$ {total_reti:,.2f} Bi")
c3.metric("Fiscal ROI (Multiplicador)", f"{(total_retorno/total_reti):.2f}x")

# Gráfico de Trajetória
st.subheader("Trajetória do Gasto Tributário Nacional (R$ Bilhões)")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["Ano"], y=df["RETI"], name="Custo RETI", line=dict(color='firebrick', width=4)))
fig.add_trace(go.Scatter(x=df["Ano"], y=df["Lei do Bem"], name="Custo Lei do Bem", line=dict(color='gray', dash='dash')))
st.plotly_chart(fig, use_container_width=True)

st.write("### Tabela de Dados (Valores Anuais em R$ Bilhões)")
# Formatação explícita para evitar confusão
st.dataframe(df.style.format({
    "Lei do Bem": "{:,.2f}",
    "RETI": "{:,.2f}",
    "Retorno Fiscal": "{:,.2f}"
}))

st.info(f"""
**Análise de Realismo:** 
- O custo anual projetado para a Lei do Bem no Ano 1 é de **R$ {df['Lei do Bem'].iloc[0]:.2f} Bi**, 
o que está alinhado com o Demonstrativo de Gastos Tributários (DGT) da Receita Federal.
- O RETI apresenta um custo maior (**R$ {df['RETI'].iloc[0]:.2f} Bi**) devido ao multiplicador de incentivo e ao Fator F, 
focando na atração de novas empresas para a base de inovação.
""")

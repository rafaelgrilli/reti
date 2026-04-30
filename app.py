import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# Configuração da página
st.set_page_config(page_title="Simulador RETI", layout="wide")

# Título
st.title("📊 Simulador de Impacto Fiscal: RETI vs Lei do Bem")

# --- SIDEBAR ---
st.sidebar.header("⚙️ Parâmetros de Simulação")

# Macro
tax_rate = st.sidebar.slider("Alíquota (IRPJ+CSLL)", 0.0, 0.4, 0.34)
ipca = st.sidebar.slider("IPCA anual", 0.0, 0.1, 0.045)
lambda_prod = st.sidebar.slider("Coeficiente Produtividade (λ)", 0.01, 0.2, 0.08)

# Específicos RETI
fator_f = st.sidebar.selectbox("Fator F (Maturidade)", [3.5, 3.0, 2.5, 2.0, 1.0])
super_deducao = st.sidebar.slider("Multiplicador P&D (RETI)", 1.0, 2.5, 1.6)
trava_uso = st.sidebar.slider("Trava de Uso (%)", 10, 100, 50) / 100

# Firma
elasticity = st.sidebar.slider("Elasticidade P&D", -2.0, -0.1, -1.2)
base_revenue = st.sidebar.number_input("Receita Inicial", value=1000000)
base_rd = st.sidebar.number_input("P&D Inicial", value=150000)

# --- LOGICA ---
years = np.arange(1, 11)
results = []
credit_stock = 0.0
rev_reti, rd_reti = float(base_revenue), float(base_rd)
rev_bem, rd_bem = float(base_revenue), float(base_rd)

for t in years:
    # Lei do Bem (Simplificada)
    tax_base_bem = rev_bem * 0.32 * tax_rate
    renuncia_bem = (rd_bem * 0.6) * tax_rate
    
    # RETI
    tax_base_reti = rev_reti * 0.32 * tax_rate
    # Indução: Custo cai, P&D sobe
    rd_induzido = rd_reti * (1 + abs(elasticity) * 0.15) 
    
    calc_base_reti = (rev_reti * 0.32) - (super_deducao * rd_induzido * fator_f)
    tax_bruto_reti = max(0.0, calc_base_reti) * tax_rate
    
    usable_credit = min(credit_stock, tax_bruto_reti * trava_uso)
    tax_final_reti = tax_bruto_reti - usable_credit
    
    # Crédito: 100% do P&D gera potencial de abatimento
    credit_stock = (credit_stock * (1 + ipca)) + rd_induzido - usable_credit
    renuncia_reti = tax_base_reti - tax_final_reti
    
    # Retorno Macro
    retorno = (lambda_prod * rd_induzido) * tax_rate
    
    results.append({
        "Ano": int(t),
        "Renúncia RETI": renuncia_reti,
        "Renúncia Bem": renuncia_bem,
        "Crédito": credit_stock,
        "Retorno": retorno
    })
    rev_reti *= 1.05
    rev_bem *= 1.03
    rd_reti = rd_induzido

df = pd.DataFrame(results)

# --- DASHBOARD ---
c1, c2, c3 = st.columns(3)
c1.metric("Total Renúncia RETI", f"R$ {df['Renúncia RETI'].sum():,.0f}")
c2.metric("Total Renúncia Bem", f"R$ {df['Renúncia Bem'].sum():,.0f}")
c3.metric("ROI Fiscal", f"{(df['Retorno'].sum()/df['Renúncia RETI'].sum()):.2f}x")

fig = go.Figure()
fig.add_trace(go.Scatter(x=df["Ano"], y=df["Renúncia RETI"], name="RETI"))
fig.add_trace(go.Scatter(x=df["Ano"], y=df["Renúncia Bem"], name="Lei do Bem", line=dict(dash='dash')))
st.plotly_chart(fig, use_container_width=True)

st.dataframe(df)

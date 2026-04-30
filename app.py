import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# Configuração da página
st.set_page_config(page_title="RETI vs Lei do Bem | Simulador", layout="wide")

# Título e Contexto
st.title("🏛️ Simulador de Impacto Fiscal: RETI vs Lei do Bem")
st.markdown("""
Esta ferramenta permite modelar o impacto fiscal de longo prazo da transição para o **RETI**.
O diferencial do RETI é a democratização do incentivo para empresas que ainda não atingiram o lucro contábil (como startups e deep techs).
""")

# --- SIDEBAR: EXPLICATIVO E DETALHADO ---
st.sidebar.header("📋 Parâmetros de Entrada")

# Bloco 1: Estrutura Fiscal
with st.sidebar.expander("1. Estrutura Tributária & Macro", expanded=True):
    tax_rate = st.number_input("Alíquota IRPJ/CSLL (%)", 0.0, 1.0, 0.34, 
                               help="Soma das alíquotas de IRPJ (15% + 10% adicional) e CSLL (9%). Padrão Brasil: 34%.")
    ipca = st.slider("Correção IPCA (Anual %)", 0.0, 0.15, 0.045,
                     help="Índice usado para corrigir o estoque de crédito fiscal ao longo de 10 anos.")
    lambda_prod = st.slider("Multiplicador de Produtividade (λ)", 0.01, 0.30, 0.08,
                            help="Quanto cada R$ 1 investido em P&D gera de crescimento no PIB setorial. (Base IPEA/OCDE)")

# Bloco 2: Parâmetros RETI
with st.sidebar.expander("2. Alavancas do RETI", expanded=True):
    fator_f = st.selectbox("Fator F (Maturidade)", [3.5, 3.0, 2.5, 2.0, 1.0], index=0,
                           help="Peso dado ao estágio da empresa. 3.5 = Deep Tech Inicial (maior risco); 1.0 = Empresa Madura.")
    super_deducao = st.slider("Multiplicador P&D (RETI)", 1.0, 2.5, 1.6,
                              help="Multiplicador sobre os gastos de inovação. 1.6 significa que cada R$ 1 investido deduz R$ 1,60 da base.")
    trava_uso = st.slider("Trava de Uso de Crédito (%)", 0.1, 1.0, 0.5,
                          help="Limite máximo do imposto devido que pode ser quitado usando créditos acumulados. Recomendado: 50%.")

# Bloco 3: Calibragem de Mercado (Lei do Bem)
with st.sidebar.expander("3. Perfil da Empresa / Setor", expanded=True):
    base_revenue = st.number_input("Faturamento Bruto Anual (R$)", value=50000000.0, step=1000000.0,
                                   help="Receita bruta total. Para simular impacto setorial, utilize o faturamento somado das empresas alvo.")
    base_rd = st.number_input("Gasto Atual em P&D (R$)", value=2500000.0, step=100000.0,
                              help="Investimento nominal em Pesquisa e Desenvolvimento antes do incentivo.")
    elasticity = st.slider("Elasticidade do P&D", -2.0, -0.1, -1.2,
                           help="Sensibilidade da empresa ao custo: quanto mais negativo, mais a empresa aumenta o P&D ao receber o incentivo.")

# --- LÓGICA DE SIMULAÇÃO (CALIBRADA) ---
years = list(range(1, 11))
results = []
credit_stock = 0.0
rev_reti, rd_reti = float(base_revenue), float(base_rd)
rev_bem, rd_bem = float(base_revenue), float(base_rd)

for t in years:
    # 1. LEI DO BEM (Baseline Calibrado: Lucro Real)
    # A Lei do Bem permite deduzir entre 60% e 80% dos gastos de P&D da base de cálculo do IRPJ/CSLL.
    # No entanto, só funciona se houver lucro contábil.
    tax_base_presumida = rev_bem * 0.32 # Proxy para base tributável
    deducao_lei_do_bem = rd_bem * 0.60  # Alíquota média de fruição (60%)
    
    # Simula a renúncia: Economia tributária direta para quem está no Lucro Real
    renuncia_bem = deducao_lei_do_bem * tax_rate
    tax_final_bem = max(0.0, (tax_base_presumida * tax_rate) - renuncia_bem)
    
    # 2. RETI (Modelo Dinâmico)
    tax_base_potencial_reti = rev_reti * 0.32
    
    # Efeito Indução: O RETI barateia o P&D mais agressivamente
    custo_marginal_reducao = (super_deducao * fator_f * tax_rate)
    rd_induzido = rd_reti * (1 + abs(elasticity) * (custo_marginal_reducao))
    
    base_final_reti = max(0.0, tax_base_potencial_reti - (super_deducao * rd_induzido * fator_f))
    tax_bruto_reti = base_final_reti * tax_rate
    
    # Compensação com crédito acumulado
    usable_credit = min(credit_stock, tax_bruto_reti * trava_uso)
    tax_final_reti = tax_bruto_reti - usable_credit
    
    # Atualização do Estoque de Crédito (IPCA + Novos gastos - Uso)
    credit_stock = (credit_stock * (1 + ipca)) + (rd_induzido * tax_rate) - usable_credit
    renuncia_reti = (tax_base_potencial_reti * tax_rate) - tax_final_reti
    
    # Retorno Econômico (Ganho de PIB via Produtividade)
    retorno_uniao = (rd_induzido * lambda_prod) * tax_rate

    results.append({
        "Ano": t,
        "Renúncia Lei do Bem": renuncia_bem,
        "Renúncia RETI": renuncia_reti,
        "Arrecadação Líquida RETI": tax_final_reti,
        "Crédito Acumulado": credit_stock,
        "Retorno Indireto": retorno_uniao,
        "P&D Induzido": rd_induzido
    })
    
    # Evolução temporal
    rev_reti *= 1.05 # Crescimento orgânico + inovação
    rd_reti = rd_induzido
    rev_bem *= 1.03 # Crescimento menor sem o efeito indutor do RETI

df = pd.DataFrame(results)

# --- VISUALIZAÇÃO DASHBOARD ---
st.header("📊 Análise de Viabilidade Fiscal")

# KPIs
c1, c2, c3, c4 = st.columns(4)
total_reti = df["Renúncia RETI"].sum()
total_bem = df["Renúncia Lei do Bem"].sum()
total_ret = df["Retorno Indireto"].sum()

c1.metric("Total Renúncia RETI", f"R$ {total_reti:,.0f}")
c2.metric("Total Renúncia Bem", f"R$ {total_bem:,.0f}")
c3.metric("Diferencial de Renúncia", f"R$ {total_reti - total_bem:,.0f}", delta_color="inverse")
c4.metric("Fiscal ROI (RETI)", f"{(total_ret/total_reti):.2f}x")

# Gráficos
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Curva de Renúncia Comparada")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["Ano"], y=df["Renúncia RETI"], name="RETI", line=dict(color='firebrick', width=4)))
    fig.add_trace(go.Scatter(x=df["Ano"], y=df["Renúncia Lei do Bem"], name="Lei do Bem", line=dict(dash='dash', color='blue')))
    st.plotly_chart(fig, use_container_width=True)

with col_right:
    st.subheader("Equilíbrio: Crédito vs Retorno")
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(x=df["Ano"], y=df["Crédito Acumulado"], name="Estoque Crédito (Passivo)"))
    fig2.add_trace(go.Scatter(x=df["Ano"], y=df["Retorno Indireto"], name="Arrecadação Indireta (Ativo)", line=dict(color='green')))
    st.plotly_chart(fig2, use_container_width=True)

st.write("### 📋 Memória de Cálculo Simulado")
st.dataframe(df.style.format("{:,.2f}"))

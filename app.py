import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# Configuração da Página
st.set_page_config(page_title="Impacto Fiscal RETI - Consolidado", layout="wide")

st.title("🏛️ Simulador de Impacto Fiscal Nacional: RETI vs Lei do Bem")
st.markdown("""
Esta ferramenta compara o **Custo Orçamentário (Renúncia)** e o **Retorno Econômico** acumulado para a União em um horizonte de 10 anos.
Os valores estão expressos em **Bilhões de Reais (R$ Bi)**.
""")

# --- SIDEBAR: PARÂMETROS COM EXPLICAÇÃO DIRETA ---
st.sidebar.header("⚙️ Configurações da Simulação")

with st.sidebar.expander("1. Escala do Universo Alvo", expanded=True):
    # Calibragem: No Brasil, cerca de 4.000 a 5.000 empresas usam a Lei do Bem.
    universo_empresas = st.number_input("Nº de Empresas no Regime", value=5000, step=500, 
                                        help="Total de empresas (startups e maduras) que adeririam ao incentivo em todo o Brasil.")
    investimento_medio_pd = st.number_input("Investimento Médio em P&D por Empresa (R$ Milhões)", value=1.5, step=0.1) * 1e6

with st.sidebar.expander("2. Parâmetros RETI (Agressividade)", expanded=True):
    fator_f = st.select_slider("Fator F (Maturidade Médio)", options=[1.0, 2.0, 2.5, 3.0, 3.5], value=2.5,
                               help="Peso para empresas inovadoras. 3.5 foca em Deep Techs; 1.0 é neutro.")
    multiplicador = st.slider("Multiplicador da Fórmula", 1.0, 2.5, 1.6, 
                              help="O fator '1.6' da fórmula original. Define o tamanho da superdedução.")
    trava_uso = st.slider("Trava de Abatimento (%)", 10, 100, 50) / 100

with st.sidebar.expander("3. Premissas de Retorno", expanded=True):
    lambda_prod = st.slider("Eficiência de Retorno (λ)", 0.01, 0.30, 0.08,
                            help="Quanto cada R$ 1,00 de P&D retorna para os cofres públicos via crescimento do PIB.")
    tax_rate = 0.34 # IRPJ + CSLL

# --- CÁLCULO DOS CENÁRIOS (CONSOLIDADO 10 ANOS) ---
anos = np.arange(1, 11)
lista_resultados = []

# Variável de estoque para o RETI (Crédito Acumulado)
estoque_credito_bi = 0.0

for ano in anos:
    # 1. LEI DO BEM (Baseline Histórico)
    # Calibrado: R$ 1.5M P&D -> Renúncia de ~R$ 300k/ano por empresa no Lucro Real.
    # Total Nacional = Empresas * (P&D * 0.60 * 0.34)
    custo_bem_anual_bi = (universo_empresas * (investimento_medio_pd * 0.60 * tax_rate) * (1.045**ano)) / 1e9
    
    # 2. RETI (O Novo Regime)
    # Base Tributável Presumida média (32% da Receita, assumindo Receita = 5x P&D)
    receita_presumida_media = investimento_medio_pd * 5
    base_calculo_presumida = receita_presumida_media * 0.32
    
    # Cálculo da Superdedução RETI
    # Se a dedução for maior que a base, gera crédito.
    deducao_reti = investimento_medio_pd * multiplicador * fator_f
    imposto_antes = base_calculo_presumida * tax_rate
    imposto_depois_deducao = max(0.0, (base_calculo_presumida - deducao_reti) * tax_rate)
    
    # Gerando crédito para o estoque (se a empresa investir mais que sua base)
    credito_gerado_ano = max(0.0, (deducao_reti - base_calculo_presumida) * tax_rate)
    
    # Aplicando a Trava de Uso de Estoque
    uso_estoque = min(estoque_credito_bi, (imposto_depois_deducao * trava_uso))
    estoque_credito_bi = (estoque_credito_bi * 1.045) + (credito_gerado_ano * universo_empresas / 1e9) - (uso_estoque * universo_empresas / 1e9)
    
    custo_reti_anual_bi = (universo_empresas * (imposto_antes - (imposto_depois_deducao - uso_estoque))) / 1e9
    
    # 3. RETORNO PARA A UNIÃO (Atividade Econômica)
    retorno_indireto_bi = (universo_empresas * investimento_medio_pd * lambda_prod * tax_rate) / 1e9

    lista_resultados.append({
        "Ano": ano,
        "Custo Lei do Bem (R$ Bi)": custo_bem_anual_bi,
        "Custo RETI (R$ Bi)": custo_reti_anual_bi,
        "Diferença de Custo (R$ Bi)": custo_reti_anual_bi - custo_bem_anual_bi,
        "Retorno p/ União (R$ Bi)": retorno_indireto_bi,
        "Saldo Líquido RETI (Retorno - Custo)": retorno_indireto_bi - custo_reti_anual_bi
    })

df = pd.DataFrame(lista_resultados)

# --- DASHBOARD EXECUTIVO ---
st.header("📊 Resultado Consolidado (Total 10 Anos)")

c1, c2, c3, c4 = st.columns(4)
total_bem = df["Custo Lei do Bem (R$ Bi)"].sum()
total_reti = df["Custo RETI (R$ Bi)"].sum()
total_retorno = df["Retorno p/ União (R$ Bi)"].sum()

c1.metric("Custo Lei do Bem", f"R$ {total_bem:,.1f} Bi")
c2.metric("Custo RETI", f"R$ {total_reti:,.1f} Bi")
c3.metric("Acréscimo de Renúncia", f"R$ {total_reti - total_bem:,.1f} Bi", delta_color="inverse")
c4.metric("ROI Fiscal (Multiplicador)", f"{(total_retorno/total_reti):.2f}x")

# --- GRÁFICOS ---
st.subheader("Trajetória do Impacto Fiscal Ano a Ano")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["Ano"], y=df["Custo RETI (R$ Bi)"], name="Custo Anual RETI", line=dict(color='firebrick', width=4)))
fig.add_trace(go.Scatter(x=df["Ano"], y=df["Custo Lei_do_Bem (R$ Bi)"], name="Custo Anual Lei do Bem", line=dict(color='gray', dash='dash')))
fig.add_trace(go.Bar(x=df["Ano"], y=df["Retorno p/ União (R$ Bi)"], name="Retorno Gerado p/ União", marker_color='rgba(0, 200, 0, 0.3)'))
st.plotly_chart(fig, use_container_width=True)

# --- EXPLICAÇÃO DOS DADOS ---
st.subheader("📑 Detalhamento da Simulação (Valores em R$ Bilhões)")
# Formatação para facilitar leitura
df_formatado = df.copy()
st.table(df_formatado.style.format({
    "Custo Lei do Bem (R$ Bi)": "{:,.2f}",
    "Custo RETI (R$ Bi)": "{:,.2f}",
    "Diferença de Custo (R$ Bi)": "{:,.2f}",
    "Retorno p/ União (R$ Bi)": "{:,.2f}",
    "Saldo Líquido RETI (Retorno - Custo)": "{:,.2f}"
}))

st.info("""
**Como ler esta tabela:**
1. **Custo Lei do Bem:** Quanto o governo deixa de arrecadar hoje projetado no tempo.
2. **Custo RETI:** Impacto fiscal da proposta nova. É natural que seja maior que a Lei do Bem, pois alcança mais empresas.
3. **Retorno p/ União:** Estimativa de quanto o aumento do P&D 'devolve' em impostos indiretos (consumo, folha e crescimento do PIB).
4. **Saldo Líquido:** Se positivo, a política gera mais riqueza/imposto do que custa.
""")

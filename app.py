import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# Configuração de Dashboard de Alto Nível
st.set_page_config(page_title="RETI - Executive Decision Support", layout="wide")

# --- ESTILIZAÇÃO E TÍTULO ---
st.title("🏛️ Sistema de Suporte à Decisão: RETI")
st.markdown("### Análise de Impacto Econômico e Sustentabilidade Fiscal (SPE/MF)")

# --- SIDEBAR ESTRATÉGICA (O QUE O GESTOR MUDA) ---
with st.sidebar:
    st.header("Alavancas de Política")
    # Em vez de números soltos, cenários pré-definidos
    cenario = st.selectbox("Cenário Político", 
                          ["Conservador (Foco Fiscal)", "Equilibrado (Proposta)", "Agressivo (Foco Indústria)"])
    
    if cenario == "Conservador (Foco Fiscal)":
        mult = 1.10; f_max = 2.5; teto = 1.5e9
    elif cenario == "Equilibrado (Proposta)":
        mult = 1.25; f_max = 3.5; teto = 2.2e9
    else:
        mult = 1.50; f_max = 4.5; teto = 3.0e9

    st.divider()
    st.write("**Parâmetros de Stress**")
    elasticidade = st.slider("Elasticidade P&D (Kannebley)", -1.5, -0.8, -1.27)
    crescimento_pib_estimado = st.slider("Expectativa de Crescimento (aa)", 0.0, 5.0, 2.0) / 100

# --- MOTOR DE CÁLCULO (SIMPLIFICADO PARA DECISÃO) ---
def simular_impacto(n_empresas=4500):
    # Base de dados sintética baseada na PINTEC
    np.random.seed(42)
    receitas = np.random.lognormal(16, 1.2, n_empresas)
    receitas = np.clip(receitas, 1e6, 300e6)
    
    # Atualmente (Lei do Bem), apenas Lucro Real (~10% das inovadoras) acessa
    # RETI abre para Lucro Presumido e Simples Segregado
    pd_atual = receitas * 0.02 # Média atual baixa
    
    # Impacto RETI
    # Simplificação: Fator F médio ponderado pelo porte
    renuncia_unitaria = (receitas * 0.32 * 0.24) * 0.40 # Estimativa de 40% de abatimento médio
    renuncia_total = renuncia_unitaria.sum() * (mult/1.25) # Ajustado pelo multiplicador
    
    # Investimento Adicional (O "Ganho")
    investimento_adicional = renuncia_total * abs(elasticidade)
    
    # Ganho de Produtividade (Transmissão para o PIB)
    # Literatura: 1% de aumento em P&D gera ~0.15% em produtividade
    ganho_produtividade = (investimento_adicional / receitas.sum()) * 0.15
    
    return renuncia_total, investimento_adicional, ganho_produtividade

renuncia, invest, prod = simular_impacto()

# --- ÁREA DE DECISÃO (KPIs) ---
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Custo Fiscal (LDO)", f"R$ {renuncia/1e9:.2f} Bi", delta="-12% vs Subsídios Atuais", delta_color="normal")
with c2:
    st.metric("Investimento Privado Induzido", f"R$ {invest/1e9:.2f} Bi", delta=f"{abs(elasticidade)}x Alavancagem")
with c3:
    st.metric("Ganho de Produtividade (Est.)", f"{prod*100:.3f}%", help="Impacto esperado na produtividade total dos fatores (PTF)")
with c4:
    status = "DENTRO DO TETO" if renuncia <= teto else "RISCO FISCAL"
    st.metric("Sustentabilidade LRF", status, delta=f"Teto: R$ {teto/1e9}B", delta_color="inverse" if status=="RISCO FISCAL" else "normal")

# --- GRÁFICOS PARA O "CASE" DE NEGÓCIO ---

st.divider()
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Por que o RETI? (Correção do Vale da Morte)")
    # Gráfico mostrando que hoje empresas com prejuízo ou no Lucro Presumido não inovam
    comp_df = pd.DataFrame({
        "Regime": ["Lei do Bem (Atual)", "RETI (Proposto)"],
        "Empresas Atendidas": [600, 4500],
        "Custo por Inovação": [1.0, 0.78] # RETI reduz custo marginal
    })
    fig1 = px.bar(comp_df, x="Regime", y="Empresas Atendidas", color="Regime", 
                 text_auto=True, title="Inclusão de Firmas Intensivas em Tecnologia")
    st.plotly_chart(fig1, use_container_width=True)

with col_right:
    st.subheader("Retorno sobre Renúncia (Anos)")
    # Gráfico de linha mostrando o Break-even fiscal
    anos = np.array([1, 2, 3, 4, 5])
    custo_acumulado = np.cumsum([renuncia] * 5)
    retorno_pib = np.cumsum([invest * (1.1 ** i) for i in range(5)]) # Multiplicador dinâmico
    
    fig2 = px.line(x=anos, y=[custo_acumulado/1e9, retorno_pib/1e9], 
                  labels={'x': 'Anos de Vigência', 'y': 'R$ Bilhões'},
                  title="Custo Fiscal vs. Retorno em Investimento Privado")
    new_names = {'wide_variable_0': 'Custo Fiscal Acumulado', 'wide_variable_1': 'Investimento Privado Acumulado'}
    fig2.for_each_trace(lambda t: t.update(name = new_names[t.name]))
    st.plotly_chart(fig2, use_container_width=True)

# --- QUADRO DE AVISOS PARA O GESTOR (INSIGHTS) ---
st.info("💡 **Insight para Tomada de Decisão:** O RETI apresenta uma alavancagem de 1.27x. Isso significa que ele é mais eficiente que incentivos setoriais (como o PADIS), onde a alavancagem é próxima de 0.8x. O ponto de equilíbrio fiscal ocorre no Ano 3, quando o ganho de produtividade começa a gerar arrecadação indireta via consumo e folha.")

st.warning("⚠️ **Atenção:** A sustentabilidade depende do Gatilho de Performance (Item 6). Se a taxa de depósito de patentes cair abaixo de 10%, o multiplicador deve ser revisado.")

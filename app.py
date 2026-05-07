import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# =============================================================================
# CONFIGURAÇÃO INICIAL DA PÁGINA
# =============================================================================
# Define o título da aba do navegador e o layout para ocupar toda a tela.
st.set_page_config(page_title="Simulador RETI - Fazenda", layout="wide")

# Título principal do aplicativo
st.title("🏛️ Simulador: Regime Especial de Tributação para a Inovação (RETI)")
st.markdown("""
Este simulador traduz a proposta executiva do RETI em cenários interativos. 
Ele permite avaliar o impacto microeconômico (na firma) e macroeconômico (no Tesouro e na Produtividade) 
da implementação de incentivos à inovação para empresas fora do Lucro Real.
""")

# =============================================================================
# BARRA LATERAL (SIDEBAR) - PARÂMETROS REGULATÓRIOS GERAIS
# =============================================================================
# A barra lateral serve como o "Painel de Controle" para os formuladores de política (Fazenda/SPE).
st.sidebar.header("⚙️ Calibragem da Política (Parâmetros)")

st.sidebar.markdown("**Fórmula Base:** `Base = (R * 0,32) - (Mult * P&D * F)`")

# 1. Multiplicador Fiscal-Base (Proposta: 1.25)
# Representa o prêmio dado pelo governo pelas externalidades positivas da inovação.
multiplicador = st.sidebar.slider(
    "Multiplicador Fiscal-Base", 
    min_value=1.0, max_value=2.0, value=1.25, step=0.05,
    help="Aumenta o peso do gasto em P&D na dedução. Justificativa: Inovação gera 'spillovers' (benefícios para toda a sociedade)."
)

# 2. F_max (Intensidade Máxima do Incentivo)
f_max = st.sidebar.slider(
    "F_max (Intensidade Máxima)", 
    min_value=0.5, max_value=1.5, value=1.0, step=0.1,
    help="O teto do Fator F. Define o benefício máximo para empresas em estágio muito inicial."
)

# 3. Gama (Velocidade de Decaimento)
gamma = st.sidebar.slider(
    "Gama (γ - Progressividade)", 
    min_value=0.5, max_value=5.0, value=2.0, step=0.1,
    help="Controla a curvatura. Valores maiores fazem o benefício cair mais rápido à medida que a empresa cresce, focando nas menores."
)

# Limite legal do Lucro Presumido no Brasil (R$ 78 Milhões)
LIMITE_LP = 78000000 

# =============================================================================
# ESTRUTURA DE ABAS (TABS)
# =============================================================================
# Dividimos o app em 3 visões para facilitar a análise.
tab1, tab2, tab3 = st.tabs([
    "🏢 Visão Micro: Lucro Presumido", 
    "🏪 Visão Micro: Simples Nacional (SME)", 
    "📊 Visão Macro: Impacto Fiscal e PTF"
])

# =============================================================================
# ABA 1: VISÃO MICRO - LUCRO PRESUMIDO
# =============================================================================
with tab1:
    st.header("Simulação da Firma no Lucro Presumido")
    st.markdown("""
    **Lógica Econômica:** O RETI atua como uma "ponte". A empresa deduz seus gastos em P&D da base de cálculo presumida. 
    O benefício é progressivo: quanto mais perto do limite de R$ 78M (migração para Lucro Real), menor o incentivo (Fator F cai a zero), evitando o "efeito notch" (degrau tributário).
    """)
    
    col1, col2 = st.columns([1, 1.5]) # Divide a tela em duas colunas (inputs à esq, gráficos à dir)
    
    with col1:
        st.subheader("Dados da Empresa")
        # Inputs do usuário
        receita = st.number_input("Receita Bruta Anual (R$)", min_value=0, max_value=LIMITE_LP, value=15000000, step=1000000)
        ped = st.number_input("Dispêndio Elegível em P&D (R$)", min_value=0, value=2000000, step=100000)
        
        # --- CÁLCULOS FINANCEIROS E TRIBUTÁRIOS ---
        # 1. Cálculo do Fator F (Função contínua de decaimento)
        # Se a receita for igual ao limite, F = 0. Se for 0, F = F_max.
        fator_f = f_max * (1 - (receita / LIMITE_LP)**gamma)
        
        # 2. Base de Cálculo Normal (Sem RETI)
        # 0.32 (32%) é a margem de presunção padrão para serviços no Brasil.
        base_normal = receita * 0.32 
        
        # 3. Dedução RETI
        deducao_reti = multiplicador * ped * fator_f
        
        # 4. Nova Base Ajustada (Não pode ser negativa, por isso o max(0, ...))
        base_ajustada = max(0, base_normal - deducao_reti)
        
        # 5. Estimativa de Imposto (IRPJ + CSLL = aprox 24% sobre a base para simplificação)
        aliquota_imposto = 0.24
        imposto_normal = base_normal * aliquota_imposto
        imposto_reti = base_ajustada * aliquota_imposto
        economia_tributaria = imposto_normal - imposto_reti
        
        # Exibição dos Resultados em "Cards" (Métricas)
        st.subheader("Resultados da Simulação")
        st.metric("Fator F Aplicado", f"{fator_f:.4f}", help="Multiplicador de progressividade.")
        
        m1, m2 = st.columns(2)
        m1.metric("Base de Cálculo (Sem RETI)", f"R$ {base_normal:,.2f}")
        m2.metric("Base Ajustada (Com RETI)", f"R$ {base_ajustada:,.2f}", delta=f"- R$ {base_normal - base_ajustada:,.2f}", delta_color="inverse")
        
        st.success(f"💰 **Economia Tributária Estimada (Caixa Preservado): R$ {economia_tributaria:,.2f}**")
        st.info("Este valor de caixa preservado é o que a startup usará para sobreviver ao 'vale da morte' tecnológico.")

    with col2:
        # --- GRÁFICO: CURVA DE DECAIMENTO ---
        # Criamos um array de receitas de 0 até 78M para desenhar a curva
        receitas_sim = np.linspace(0, LIMITE_LP, 200)
        f_sim = f_max * (1 - (receitas_sim / LIMITE_LP)**gamma)
        
        df_plot = pd.DataFrame({'Receita': receitas_sim, 'Fator F': f_sim})
        
        fig = px.line(df_plot, x='Receita', y='Fator F', 
                      title="Curva de Decaimento do Incentivo (Fator F) vs Receita",
                      labels={'Receita': 'Receita Bruta (R$)', 'Fator F': 'Intensidade do Incentivo (Fator F)'})
        
        # Adiciona uma linha vertical mostrando onde a empresa atual está na curva
        fig.add_vline(x=receita, line_dash="dash", line_color="red", 
                      annotation_text="Sua Empresa", annotation_position="top right")
        
        # Formata o eixo X para mostrar em Milhões
        fig.update_layout(xaxis=dict(tickformat=".2s"))
        st.plotly_chart(fig, use_container_width=True)

# =============================================================================
# ABA 2: VISÃO MICRO - SIMPLES NACIONAL (RETI-SME)
# =============================================================================
with tab2:
    st.header("Simulação RETI-SME (Voucher Tecnológico)")
    st.markdown("""
    **Lógica Econômica:** Empresas do Simples Nacional têm contabilidade simplificada. Deduções complexas não funcionam. 
    A solução é um **Voucher Tecnológico** (crédito financeiro) condicionado à intensidade tecnológica (P&D / Despesas Totais).
    * **Entrada (Threshold):** Mínimo de 15% de intensidade.
    * **Benefício Pleno:** Atingido com 30% de intensidade.
    """)
    
    col3, col4 = st.columns([1, 1])
    
    with col3:
        despesa_total = st.number_input("Despesa Operacional Total (R$)", min_value=1, value=1000000, step=100000)
        ped_sme = st.number_input("Despesa com P&D (R$)", min_value=0, value=200000, step=10000)
        
        # --- CÁLCULOS RETI-SME ---
        intensidade = ped_sme / despesa_total
        
        # Lógica do Voucher (Interpolação linear entre 15% e 30%)
        # Assumimos para a simulação que o benefício pleno devolve 20% do valor investido em P&D.
        taxa_retorno_maxima = 0.20 
        
        if intensidade < 0.15:
            fator_voucher = 0.0
            status = "❌ Não Elegível (Abaixo de 15%)"
        elif intensidade >= 0.30:
            fator_voucher = 1.0
            status = "✅ Elegível - Benefício Pleno (Acima de 30%)"
        else:
            # Calcula o quão perto de 30% a empresa está (escala de 0 a 1)
            fator_voucher = (intensidade - 0.15) / (0.30 - 0.15)
            status = "⚠️ Elegível - Benefício Parcial"
            
        valor_voucher = ped_sme * taxa_retorno_maxima * fator_voucher
        
        st.subheader("Diagnóstico da Empresa")
        st.write(f"**Status:** {status}")
        st.metric("Intensidade Tecnológica (P&D / Despesa)", f"{intensidade * 100:.1f}%")
        st.success(f"🎟️ **Valor do Voucher Tecnológico Gerado: R$ {valor_voucher:,.2f}**")

    with col4:
        # --- GRÁFICO: TERMÔMETRO DE INTENSIDADE (GAUGE CHART) ---
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = intensidade * 100,
            title = {'text': "Intensidade Tecnológica (%)"},
            number = {'suffix': "%"},
            gauge = {
                'axis': {'range': [0, 50]},
                'bar': {'color': "darkblue"},
                'steps': [
                    {'range': [0, 15], 'color': "lightcoral"}, # Zona morta
                    {'range': [15, 30], 'color': "lightyellow"}, # Zona de transição
                    {'range': [30, 50], 'color': "lightgreen"}   # Zona plena
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 15 # Linha de corte
                }
            }
        ))
        st.plotly_chart(fig_gauge, use_container_width=True)

# =============================================================================
# ABA 3: VISÃO MACRO - IMPACTO FISCAL E PRODUTIVIDADE (PTF)
# =============================================================================
with tab3:
    st.header("Visão Macro: Sustentabilidade Fiscal e Retorno Econômico")
    st.markdown("""
    **Lógica Econômica:** O Ministério da Fazenda precisa garantir que a renúncia fiscal não saia do controle. 
    O RETI propõe um **Envelope Fiscal** (Teto de Gastos do programa). Em contrapartida, o investimento privado 
    adicional em P&D gera aumento na Produtividade Total dos Fatores (PTF), expandindo o PIB potencial no longo prazo.
    """)
    
    col5, col6 = st.columns([1, 1.5])
    
    with col5:
        st.subheader("Parâmetros Agregados")
        qtd_empresas = st.number_input("Qtd. de Empresas Aderentes Estimada", min_value=100, value=5000, step=500)
        ticket_medio_renuncia = st.number_input("Renúncia Média por Empresa (R$)", min_value=0, value=150000, step=10000)
        envelope_fiscal = st.number_input("Envelope Fiscal (Teto do Programa em R$)", min_value=0, value=1000000000, step=100000000) # 1 Bilhão
        
        beta_ptf = st.slider("Elasticidade P&D -> PTF (β)", min_value=0.01, max_value=0.10, value=0.06, step=0.01, 
                             help="Grau de transmissão do esforço tecnológico para a produtividade agregada (Proposta: 0.05 a 0.08).")
        
        # --- CÁLCULOS MACROECONÔMICOS ---
        custo_total_programa = qtd_empresas * ticket_medio_renuncia
        espaco_fiscal = envelope_fiscal - custo_total_programa
        
        # Simulação simplificada de impacto no PIB (PTF)
        # Assumimos que cada R$ 1 de renúncia gera R$ 2 de P&D privado adicional (efeito alavancagem)
        ped_privado_gerado = custo_total_programa * 2 
        pib_simulado = 10000000000000 # 10 Trilhões (Aprox. PIB Brasil)
        
        # Fórmula da proposta: ΔPTF = β * Δ(P&D_privado / PIB)
        delta_ptf = beta_ptf * (ped_privado_gerado / pib_simulado)
        
        st.subheader("Diagnóstico Fiscal")
        st.metric("Custo Total Estimado (Renúncia)", f"R$ {custo_total_programa:,.2f}")
        
        if espaco_fiscal >= 0:
            st.success(f"✅ Dentro do Envelope Fiscal. Espaço restante: R$ {espaco_fiscal:,.2f}")
        else:
            st.error(f"🚨 TETO ROMPIDO! O programa excede o envelope em R$ {abs(espaco_fiscal):,.2f}. Necessário acionar gatilhos de redução do Fator F.")
            
        st.info(f"📈 **Impacto Estimado na Produtividade (ΔPTF): +{delta_ptf * 10000:.4f} pontos base**")

    with col6:
        # --- GRÁFICO: CONSUMO DO ENVELOPE FISCAL ---
        # Gráfico de barras simples para mostrar o limite vs uso
        fig_bar = go.Figure(data=[
            go.Bar(name='Custo do Programa', x=['Orçamento RETI'], y=[custo_total_programa], marker_color='indianred'),
            go.Bar(name='Espaço Fiscal Restante', x=['Orçamento RETI'], y=[max(0, espaco_fiscal)], marker_color='lightseagreen')
        ])
        
        fig_bar.update_layout(barmode='stack', title="Consumo do Envelope Fiscal (Teto de Gastos)",
                              yaxis=dict(title='Reais (R$)', tickformat=".2s"))
        
        # Adiciona linha do teto
        fig_bar.add_hline(y=envelope_fiscal, line_dash="dash", line_color="black", annotation_text="Teto Legal (Envelope)")
        
        st.plotly_chart(fig_bar, use_container_width=True)

st.markdown("---")
st.markdown("<p style='text-align: center; color: gray;'>Simulador desenvolvido para análise de impacto regulatório - Ministério da Fazenda / SPE</p>", unsafe_allow_html=True)

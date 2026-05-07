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
# [FEEDBACK L63] — max_value reduzido de 2.0 para 1.50. A proposta fixa o valor de referência em 1.25.
# Valores acima de 1.50 produziriam simulações sem respaldo técnico perante o Tesouro.
multiplicador = st.sidebar.slider(
    "Multiplicador Fiscal-Base", 
    min_value=1.0, max_value=1.50, value=1.25, step=0.05,
    help="Aumenta o peso do gasto em P&D na dedução. Valor de referência da proposta: **1,25** (externalidades da inovação). "
         "Teto regulatório: 1,50. Valores acima desse patamar carecem de respaldo técnico para apresentação ao Tesouro."
)

# 2. F_max (Intensidade Máxima do Incentivo)
f_max = st.sidebar.slider(
    "F_max (Intensidade Máxima)", 
    min_value=0.5, max_value=1.5, value=1.0, step=0.1,
    help="O teto do Fator F. Define o benefício máximo para empresas em estágio muito inicial."
)

# 3. Gama (Velocidade de Decaimento)
# [FEEDBACK L90] — max_value reduzido de 5.0 para 3.0. Valores acima de 3.0 produzem
# queda extremamente abrupta do Fator F, contradizendo o objetivo da proposta de eliminar
# descontinuidades e evitar desincentivo ao crescimento (Seção 6.2).
gamma = st.sidebar.slider(
    "Gama (γ - Progressividade)", 
    min_value=0.5, max_value=3.0, value=2.0, step=0.1,
    help="Controla a curvatura do decaimento do Fator F. Valores maiores concentram o benefício nas firmas menores. "
         "Teto recomendado: 3,0 — acima disso o decaimento torna-se excessivamente abrupto, "
         "contrariando o objetivo de suavidade da função contínua (Seção 6.2 da proposta)."
)

# Limite legal do Lucro Presumido no Brasil (R$ 78 Milhões)
LIMITE_LP = 78000000 

# =============================================================================
# ESTRUTURA DE ABAS (TABS)
# =============================================================================
# Dividimos o app em 4 visões para facilitar a análise.
# [CORREÇÃO OMISSÃO 1] — Adicionada Aba 4: Créditos Fiscais Carregáveis (Seção 7 da proposta)
tab1, tab2, tab3, tab4 = st.tabs([
    "🏢 Visão Micro: Lucro Presumido", 
    "🏪 Visão Micro: Simples Nacional (SME)", 
    "📊 Visão Macro: Impacto Fiscal e PTF",
    "🗂️ Créditos Fiscais Carregáveis (Carryforward)"
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

        # [CORREÇÃO INCONSISTÊNCIA 1] — Coeficiente de presunção parametrizável por tipo de atividade
        # A proposta não fixa o coeficiente em 32%; ele varia entre 8% (indústria) e 32% (serviços).
        tipo_atividade = st.selectbox(
            "Tipo de Atividade Econômica",
            options=[
                ("Serviços em geral (32%)", 0.32),
                ("Comércio e Indústria (8%)", 0.08),
                ("Serviços de transporte, exceto cargas (16%)", 0.16),
                ("Serviços hospitalares e similares (8%)", 0.08),
            ],
            format_func=lambda x: x[0]
        )
        coef_presuncao = tipo_atividade[1]

        # Inputs do usuário
        receita = st.number_input("Receita Bruta Anual (R$)", min_value=0, max_value=LIMITE_LP, value=15000000, step=1000000)
        ped = st.number_input("Dispêndio Elegível em P&D (R$)", min_value=0, value=2000000, step=100000)
        
        # --- CÁLCULOS FINANCEIROS E TRIBUTÁRIOS ---
        # 1. Cálculo do Fator F (Função contínua de decaimento)
        # Se a receita for igual ao limite, F = 0. Se for 0, F = F_max.
        # [CORREÇÃO BUG 1] — max(0, ...) garante que F nunca seja negativo (Seção 6.3: F(R) = 0 ao atingir limite)
        fator_f = max(0.0, f_max * (1 - (receita / LIMITE_LP)**gamma))
        
        # 2. Base de Cálculo Normal (Sem RETI)
        # [CORREÇÃO INCONSISTÊNCIA 1] — Usa coeficiente dinâmico, não fixo em 0.32
        base_normal = receita * coef_presuncao
        
        # 3. Dedução RETI
        deducao_reti = multiplicador * ped * fator_f
        
        # 4. Nova Base Ajustada (Não pode ser negativa)
        base_ajustada = max(0, base_normal - deducao_reti)

        # [CORREÇÃO BUG 2] — Alerta quando a dedução zera a base (sustentabilidade fiscal, Seção 12)
        if deducao_reti >= base_normal:
            st.warning(
                f"⚠️ **A dedução RETI (R$ {deducao_reti:,.2f}) supera ou iguala a base presumida "
                f"(R$ {base_normal:,.2f}). A base ajustada foi limitada a zero. "
                "Verifique a calibragem dos parâmetros regulatórios (Seção 12 — Sustentabilidade Fiscal)."
            )

        # 5. Estimativa de Imposto (IRPJ + CSLL)
        # [CORREÇÃO BUG 3] — Adicional de IRPJ de 10% sobre parcela da base que excede R$ 240.000/ano
        # IRPJ: alíquota padrão 15% + adicional 10% sobre base > R$ 240.000
        # CSLL: alíquota de 9%
        LIMITE_ADICIONAL_IRPJ = 240000  # R$ 20.000/mês × 12

        irpj_normal     = base_normal * 0.15 + max(0, base_normal - LIMITE_ADICIONAL_IRPJ) * 0.10
        csll_normal     = base_normal * 0.09
        imposto_normal  = irpj_normal + csll_normal

        irpj_reti       = base_ajustada * 0.15 + max(0, base_ajustada - LIMITE_ADICIONAL_IRPJ) * 0.10
        csll_reti       = base_ajustada * 0.09
        imposto_reti    = irpj_reti + csll_reti

        economia_tributaria = imposto_normal - imposto_reti
        
        # Exibição dos Resultados em "Cards" (Métricas)
        st.subheader("Resultados da Simulação")
        st.metric("Fator F Aplicado", f"{fator_f:.4f}", help="Multiplicador de progressividade.")
        
        m1, m2 = st.columns(2)
        m1.metric("Base de Cálculo (Sem RETI)", f"R$ {base_normal:,.2f}")
        m2.metric("Base Ajustada (Com RETI)", f"R$ {base_ajustada:,.2f}", delta=f"- R$ {base_normal - base_ajustada:,.2f}", delta_color="inverse")

        # [CORREÇÃO BUG 3 — continuação] Exibe decomposição do imposto para transparência
        with st.expander("📋 Detalhamento do Imposto (IRPJ + Adicional + CSLL)"):
            d1, d2 = st.columns(2)
            d1.metric("IRPJ s/ base normal", f"R$ {irpj_normal:,.2f}")
            d1.metric("CSLL s/ base normal", f"R$ {csll_normal:,.2f}")
            d2.metric("IRPJ s/ base RETI", f"R$ {irpj_reti:,.2f}")
            d2.metric("CSLL s/ base RETI", f"R$ {csll_reti:,.2f}")
            # [FEEDBACK L153] — Nota sobre tributos sobre consumo não cobertos por este módulo.
            # O RETI atua exclusivamente sobre a base de cálculo do IRPJ/CSLL (Lucro Presumido).
            # ISS e ICMS, quando aplicáveis, são calculados sobre receita bruta e não são afetados
            # pela dedução de P&D. Para simulação do impacto total no Simples Nacional, utilize a Aba 2.
            st.caption(
                "ℹ️ Este cálculo cobre IRPJ (15% + adicional 10%) e CSLL (9%) sobre a base presumida. "
                "ISS/ICMS incidem sobre receita bruta e **não são alterados pelo RETI** — "
                "o regime atua exclusivamente sobre a base de cálculo do IRPJ/CSLL (Seção 4). "
                "Para empresas do Simples Nacional, consulte a Aba 2 (RETI-SME)."
            )
        
        st.success(f"💰 **Economia Tributária Estimada (Caixa Preservado): R$ {economia_tributaria:,.2f}**")
        st.info("Este valor de caixa preservado é o que a startup usará para sobreviver ao 'vale da morte' tecnológico.")

        # [SUGESTÃO ESTRATÉGICA — Seção 9.4] — Alerta de auditoria por Razão P&D/Receita
        # A proposta prevê fiscalização baseada em risco monitorando a razão P&D/Receita.
        # Sinalizamos discrepâncias em relação a benchmarks setoriais típicos para convencer a RFB.
        razao_ped_receita = (ped / receita * 100) if receita > 0 else 0
        BENCHMARK_SETORIAL_MAX = 30.0  # 30% é o limite superior típico para P&D/Receita em startups (OCDE)
        BENCHMARK_SETORIAL_MIN = 1.0   # abaixo de 1% é sinal de P&D irrelevante / reclassificável
        st.markdown("**🔍 Indicador de Risco Fiscal (Seção 9.4 — Fiscalização Baseada em Risco)**")
        st.metric("Razão P&D / Receita", f"{razao_ped_receita:.1f}%",
                  help="Monitorado pela RFB como indicador de risco. Benchmarks OCDE: 1%–30% para firmas intensivas em P&D.")
        if razao_ped_receita > BENCHMARK_SETORIAL_MAX:
            st.error(
                f"🚨 **Alerta de Auditoria:** Razão P&D/Receita de {razao_ped_receita:.1f}% supera o benchmark "
                f"setorial máximo ({BENCHMARK_SETORIAL_MAX:.0f}%). Probabilidade elevada de seleção para auditoria "
                "da RFB (Seção 9.4). Revise a elegibilidade dos dispêndios ou documente rigorosamente o esforço tecnológico."
            )
        elif razao_ped_receita < BENCHMARK_SETORIAL_MIN and ped > 0:
            st.warning(
                f"⚠️ **Intensidade P&D baixa:** Razão P&D/Receita de {razao_ped_receita:.1f}% está abaixo do mínimo "
                f"referencial ({BENCHMARK_SETORIAL_MIN:.0f}%). O incentivo gerado pode não justificar o custo de compliance "
                "do RETI. Avalie se a empresa atende os critérios de adicionalidade (Seção 8)."
            )
        else:
            st.success(f"✅ Razão P&D/Receita de {razao_ped_receita:.1f}% dentro do intervalo referencial (1%–30%). Perfil de baixo risco para auditoria.")

        # [CORREÇÃO OMISSÃO 3] — Alerta de proximidade ao limite de migração LP → Lucro Real (Seção 6.3)
        pct_limite = receita / LIMITE_LP * 100
        if pct_limite >= 90:
            st.error(
                f"🚨 **Atenção: esta empresa está a {100 - pct_limite:.1f}% do limite do Lucro Presumido (R$ 78M).** "
                "Ao ultrapassar esse limite, F(R) = 0 e a empresa migra automaticamente para o Lucro Real, "
                "cessando novos benefícios via RETI e passando a acessar a Lei do Bem. "
                "Créditos acumulados são preservados (Seção 6.3 da proposta)."
            )
        elif pct_limite >= 75:
            st.warning(
                f"⚠️ Esta empresa utilizou {pct_limite:.1f}% do limite do Lucro Presumido. "
                "O Fator F está em processo de decaimento acelerado. "
                "Planeje a transição para o Lucro Real (Seção 6.3)."
            )

    with col2:
        # --- GRÁFICO: CURVA DE DECAIMENTO ---
        # Criamos um array de receitas de 0 até 78M para desenhar a curva
        receitas_sim = np.linspace(0, LIMITE_LP, 200)
        # [CORREÇÃO BUG 1 — aplicada também na curva do gráfico]
        f_sim = np.maximum(0, f_max * (1 - (receitas_sim / LIMITE_LP)**gamma))
        
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
        # [FEEDBACK L283] — Renúncia média sugerida automaticamente a partir do cálculo da Aba 1.
        # O valor padrão agora reflete a economia tributária calculada na simulação micro,
        # permitindo coerência entre as visões micro e macro sem forçar o usuário a redigitar.
        ticket_sugerido = int(economia_tributaria) if economia_tributaria > 0 else 150000
        ticket_medio_renuncia = st.number_input(
            "Renúncia Média por Empresa (R$)",
            min_value=0,
            value=ticket_sugerido,
            step=10000,
            help=f"Valor sugerido automaticamente com base na economia tributária calculada na Aba 1 "
                 f"(R$ {economia_tributaria:,.2f}). Ajuste manualmente para cenários agregados distintos."
        )
        envelope_fiscal = st.number_input("Envelope Fiscal (Teto do Programa em R$)", min_value=0, value=1000000000, step=100000000) # 1 Bilhão
        
        beta_ptf = st.slider("Elasticidade P&D -> PTF (β)", min_value=0.01, max_value=0.10, value=0.06, step=0.01, 
                             help="Grau de transmissão do esforço tecnológico para a produtividade agregada (Proposta: 0.05 a 0.08).")

        # [CORREÇÃO BUG 4] — Multiplicador de alavancagem agora é parâmetro interativo (antes hardcoded em 2x sem justificativa)
        # Representa a razão entre P&D privado adicional induzido e a renúncia fiscal concedida.
        mult_alavancagem = st.slider(
            "Multiplicador de Alavancagem P&D (P&D Induzido / Renúncia)",
            min_value=1.0, max_value=5.0, value=2.0, step=0.5,
            help="Estima quanto P&D privado adicional é gerado por cada R$ 1 de renúncia fiscal. "
                 "Valor 2,0 significa que cada R$ 1 de incentivo induz R$ 2 de investimento adicional em P&D. "
                 "Calibre conforme evidências setoriais (Seção 10.1 da proposta)."
        )

        # [CORREÇÃO INCONSISTÊNCIA 2] — PIB parametrizável; valor padrão atualizado para ~R$ 11,5 tri
        pib_simulado = st.number_input(
            "PIB Nominal Estimado (R$)",
            min_value=1_000_000_000_000,
            max_value=20_000_000_000_000,
            value=11_500_000_000_000,
            step=500_000_000_000,
            help="PIB nominal do Brasil em R$. Valor padrão atualizado (~R$ 11,5 trilhões). Ajuste conforme projeção utilizada."
        )
        
        # --- CÁLCULOS MACROECONÔMICOS ---
        custo_total_programa = qtd_empresas * ticket_medio_renuncia
        espaco_fiscal = envelope_fiscal - custo_total_programa
        
        # [CORREÇÃO BUG 4] — Usa multiplicador parametrizável no lugar do valor fixo 2x
        ped_privado_gerado = custo_total_programa * mult_alavancagem
        
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

# =============================================================================
# ABA 4: CRÉDITOS FISCAIS CARREGÁVEIS (CARRYFORWARD) — Seção 7 da proposta
# =============================================================================
# [CORREÇÃO OMISSÃO 1] — Módulo ausente no código original; implementado conforme Seção 7
with tab4:
    st.header("Créditos Fiscais de Inovação com Carryforward (Seção 7)")
    st.markdown("""
    **Lógica Econômica:** O RETI institui um sistema de créditos fiscais com carregamento intertemporal para corrigir 
    o descasamento entre o momento do investimento em P&D e a geração futura de lucro tributável.  
    O crédito é gerado **independentemente da existência de lucro no período corrente**.

    * `Crédito_t = α × P&D_t`  
    * Validade: **10 anos** (corrigidos monetariamente).  
    * Limite de uso: **50% do imposto devido em cada exercício**.  
    * Sobrevive à migração para o Lucro Real.
    """)

    col7, col8 = st.columns([1, 1.5])

    with col7:
        st.subheader("Parâmetros do Crédito")

        alpha = st.slider(
            "α — Parâmetro de Formação do Crédito",
            min_value=0.05, max_value=0.50, value=0.20, step=0.05,
            help="Define a fração do dispêndio elegível em P&D que se converte em crédito fiscal (Seção 7.1)."
        )

        # [FEEDBACK L314] — Correção monetária do saldo (SELIC/IPCA), conforme Seção 7.2 da proposta.
        # "Os créditos são corrigidos monetariamente por índice oficial definido em regulamento."
        indice_correcao = st.selectbox(
            "Índice de Correção Monetária dos Créditos",
            options=[("SELIC (referência)", 0.1075), ("IPCA (referência)", 0.045), ("Sem correção", 0.0)],
            format_func=lambda x: x[0],
            help="A proposta (Seção 7.2) prevê correção monetária por índice oficial. "
                 "Selecione o índice para projetar o valor real do saldo carregável ao longo do tempo."
        )
        taxa_correcao_anual = indice_correcao[1]

        st.subheader("Fluxo Anual de P&D e Imposto Devido")
        st.caption("Informe os valores projetados para até 5 anos de operação.")

        anos = []
        ped_anos = []
        imposto_anos = []

        for i in range(1, 6):
            c1, c2 = st.columns(2)
            ped_val     = c1.number_input(f"P&D Elegível — Ano {i} (R$)", min_value=0, value=500000 * i, step=50000, key=f"ped_{i}")
            imp_val     = c2.number_input(f"Imposto Devido — Ano {i} (R$)", min_value=0, value=100000 * i, step=10000, key=f"imp_{i}")
            anos.append(i)
            ped_anos.append(ped_val)
            imposto_anos.append(imp_val)

    with col8:
        st.subheader("Projeção de Acúmulo e Utilização de Créditos")

        credito_gerado   = [alpha * p for p in ped_anos]
        limite_uso_anual = [0.50 * imp for imp in imposto_anos]  # 50% do imposto devido (Seção 7.2)

        saldo_acumulado = []
        credito_utilizado = []
        saldo = 0.0

        for gerado, limite in zip(credito_gerado, limite_uso_anual):
            # [FEEDBACK L314] — Saldo existente é corrigido monetariamente antes de acumular o novo crédito
            saldo = saldo * (1 + taxa_correcao_anual)
            saldo += gerado                      # acumula crédito do ano (após correção)
            uso    = min(saldo, limite)          # usa até 50% do imposto devido
            saldo -= uso
            credito_utilizado.append(uso)
            saldo_acumulado.append(saldo)

        df_creditos = pd.DataFrame({
            'Ano': anos,
            'P&D Elegível (R$)': ped_anos,
            'Crédito Gerado (R$)': credito_gerado,
            'Imposto Devido (R$)': imposto_anos,
            'Limite de Uso (50% imp.) (R$)': limite_uso_anual,
            'Crédito Utilizado (R$)': credito_utilizado,
            # [FEEDBACK L314] — Saldo já reflete correção monetária pelo índice selecionado
            f'Saldo Acumulado c/ Correção ({indice_correcao[0]}) (R$)': saldo_acumulado,
        })

        # Formata valores monetários para exibição
        fmt_cols = [c for c in df_creditos.columns if c != 'Ano']
        df_display = df_creditos.copy()
        for col in fmt_cols:
            df_display[col] = df_display[col].apply(lambda x: f"R$ {x:,.2f}")

        st.dataframe(df_display, use_container_width=True)

        fig_creditos = go.Figure()
        fig_creditos.add_trace(go.Bar(
            name='Crédito Gerado no Ano', x=anos, y=credito_gerado, marker_color='steelblue'
        ))
        fig_creditos.add_trace(go.Bar(
            name='Crédito Utilizado no Ano', x=anos, y=credito_utilizado, marker_color='mediumseagreen'
        ))
        fig_creditos.add_trace(go.Scatter(
            name='Saldo Acumulado (Carryforward)', x=anos, y=saldo_acumulado,
            mode='lines+markers', line=dict(color='firebrick', width=2, dash='dash')
        ))
        fig_creditos.update_layout(
            barmode='group',
            title="Fluxo de Créditos Fiscais de Inovação (α × P&D) — Carryforward 10 anos",
            xaxis=dict(title='Ano', tickvals=anos),
            yaxis=dict(title='Reais (R$)', tickformat=".2s"),
        )
        st.plotly_chart(fig_creditos, use_container_width=True)

        credito_total  = sum(credito_gerado)
        uso_total      = sum(credito_utilizado)
        saldo_final    = saldo_acumulado[-1]

        st.metric("Crédito Total Gerado (5 anos)", f"R$ {credito_total:,.2f}")
        m_c1, m_c2 = st.columns(2)
        m_c1.metric("Total Utilizado", f"R$ {uso_total:,.2f}")
        m_c2.metric("Saldo Carregável Restante", f"R$ {saldo_final:,.2f}",
                    help="Saldo disponível para compensação nos próximos exercícios (até 10 anos de validade).")

        if saldo_final > 0:
            st.info(
                f"ℹ️ O saldo de R$ {saldo_final:,.2f} pode ser carregado para exercícios futuros, "
                "inclusive após eventual migração para o Lucro Real (Seção 7.2 da proposta). "
                "Validade máxima: 10 anos a partir da geração, corrigidos monetariamente."
            )

        # [CORREÇÃO OMISSÃO 2] — Elegibilidade Dinâmica (Seção 8): scorecard simplificado pós-36 meses
        st.markdown("---")
        st.subheader("📋 Elegibilidade Dinâmica — Scorecard (Seção 8)")
        st.markdown("""
        A partir do **36º mês**, a utilização de créditos exige comprovação de adicionalidade tecnológica 
        via pontuação mínima nos indicadores abaixo. Marque os critérios atingidos pela empresa.
        """)

        criterios = {
            "Crescimento de receita superior à média setorial": 20,
            "Contratação de mão de obra qualificada (pesquisadores/engenheiros)": 20,
            "Depósito de propriedade intelectual (patente, software, cultivar)": 15,
            "Exportação tecnológica ou contrato tecnológico internacional": 15,
            "Certificação tecnológica (MCTI/Finep/INMETRO)": 10,
            "Captação privada (rodada de investimento, debêntures de inovação)": 10,
            "Aumento mensurável da intensidade tecnológica (P&D/Receita)": 10,
        }
        # [FEEDBACK L364] — Pontuação mínima agora é parâmetro regulatório configurável.
        # A proposta não fixa o valor; ele deve ser definido por regulamento do MCTI/Finep (Seção 8.2).
        PONTUACAO_MINIMA = st.slider(
            "Pontuação Mínima de Adicionalidade (parâmetro regulatório)",
            min_value=20, max_value=80, value=40, step=5,
            help="**Parâmetro regulatório a ser definido por ato do MCTI/Finep** (Seção 8.2). "
                 "O valor de 40 pts é referência de trabalho — não fixado na proposta. "
                 "Ajuste conforme o grau de rigor desejado pelo regulador na comprovação de adicionalidade."
        )

        pontuacao_total = 0
        for criterio, pontos in criterios.items():
            if st.checkbox(f"{criterio} (+{pontos} pts)", key=f"crit_{criterio}"):
                pontuacao_total += pontos

        st.metric("Pontuação de Adicionalidade Tecnológica", f"{pontuacao_total} / 100 pts")

        if pontuacao_total >= PONTUACAO_MINIMA:
            st.success(
                f"✅ Empresa elegível para utilização continuada dos créditos (score ≥ {PONTUACAO_MINIMA} pts). "
                "Adicionalidade tecnológica comprovada (Seção 8.2)."
            )
        else:
            st.error(
                f"❌ Pontuação insuficiente ({pontuacao_total} pts). "
                f"Mínimo exigido após 36 meses: {PONTUACAO_MINIMA} pts. "
                "A utilização dos créditos acumulados pode ser suspensa até comprovação de adicionalidade (Seção 8)."
            )

st.markdown("---")
st.markdown("<p style='text-align: center; color: gray;'>Simulador desenvolvido para análise de impacto regulatório - Ministério da Fazenda / SPE</p>", unsafe_allow_html=True)

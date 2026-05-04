import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# Configuração da Página
st.set_page_config(page_title="Simulador RETI - SPE/MF", layout="wide")

# --- TÍTULO E INTRODUÇÃO ---
st.title("🏛️ Simulador: Regime Especial de Tributação para a Inovação (RETI)")
st.markdown("""
Esta ferramenta auxilia na análise de impacto fiscal e econômico da proposta RETI, 
focada em neutralizar o 'prejuízo técnico' e induzir investimento privado em P&D.
""")

# --- SIDEBAR: PARÂMETROS DE POLÍTICA FISCAL ---
st.sidebar.header("Configurações de Política")
multiplicador_fixo = st.sidebar.slider("Multiplicador RETI (Art 3.1)", 1.0, 2.0, 1.25, 0.05)
teto_renuncia = st.sidebar.number_input("Teto de Renúncia (R$ Bilhões)", value=2.2) * 1e9
elasticidade_custo = st.sidebar.slider("Elasticidade-Custo P&D", -2.0, -0.5, -1.27)

st.sidebar.markdown("---")
st.sidebar.subheader("Parâmetros do Tapering")
f_max = st.sidebar.slider("Fator F Máximo (Startups)", 2.0, 5.0, 3.5)
f_medio = st.sidebar.slider("Fator F Médio (PMEs)", 1.5, 3.0, 2.5)

# --- FUNÇÕES DE CÁLCULO ---
def calcular_fator_f(receita):
    r_m = receita / 1e6
    if r_m <= 3.24: return f_max
    if r_m <= 78: return f_medio
    if r_m <= 200:
        # Redução linear de f_medio até 1.0
        coef = (f_medio - 1.0) / (200 - 78)
        return max(f_medio - (r_m - 78) * coef, 1.0)
    return 1.0

def simular_reti(receita, gasto_pd):
    f = calcular_fator_f(receita)
    imposto_std = (receita * 0.32) * 0.24
    
    base_reti = (receita * 0.32) - (multiplicador_fixo * gasto_pd * f)
    # Salvaguarda: Mínimo de 25% da base presumida original
    base_minima = (receita * 0.32) * 0.25
    base_final = max(base_reti, base_minima)
    
    imposto_reti = base_final * 0.24
    renuncia = imposto_std - imposto_reti
    return imposto_std, imposto_reti, renuncia, f

# --- TABS: VISÕES DIFERENTES ---
tab1, tab2, tab3 = st.tabs(["📊 Visão Macroeconômica", "🏢 Simulador por Empresa", "📜 Regras do Regime"])

with tab1:
    st.header("Impacto Orçamentário Agregado")
    
    # Gerar amostra de 4500 empresas (Baseado em PINTEC/IBGE)
    @st.cache_data
    def gerar_dados(n=4500):
        np.random.seed(42)
        recs = np.random.lognormal(mean=16, sigma=1.5, size=n)
        recs = np.clip(recs, 1e6, 300e6)
        return recs

    receitas = gerar_dados()
    resultados = []
    
    for r in receitas:
        intensidade = np.random.uniform(0.05, 0.15) if r < 50e6 else np.random.uniform(0.02, 0.08)
        g_pd = r * intensidade
        imp_s, imp_r, ren, fat_f = simular_reti(r, g_pd)
        resultados.append({
            "Receita": r, "Renúncia": ren, "P&D_Induzido": ren * abs(elasticidade_custo), 
            "Fator_F": fat_f, "Imposto_Pago": imp_r
        })

    df = pd.DataFrame(resultados)
    
    # Métricas Principais
    col1, col2, col3 = st.columns(3)
    total_ren = df['Renúncia'].sum()
    total_ind = df['P&D_Induzido'].sum()
    
    with col1:
        st.metric("Renúncia Fiscal Total", f"R$ {total_ren/1e9:.2f} Bi", 
                  delta=f"{(total_ren - teto_renuncia)/1e6:.1f}M vs Teto", delta_color="inverse")
    with col2:
        st.metric("P&D Adicional Privado", f"R$ {total_ind/1e9:.2f} Bi")
    with col3:
        st.metric("Alavancagem (ROI Social)", f"{total_ind/total_ren:.2f}x")

    if total_ren > teto_renuncia:
        st.error(f"⚠️ Alerta LRF: A renúncia estimada excede o teto de R$ {teto_renuncia/1e9} Bi!")
    else:
        st.success("✅ Proposta compatível com o teto de gastos estimado.")

    # Gráficos Macro
    c1, c2 = st.columns(2)
    
    with c1:
        # Curva de Tapering
        fig_f = px.line(df.sort_values("Receita"), x="Receita", y="Fator_F", 
                        title="Mecanismo de Tapering (Fator F por Porte)")
        st.plotly_chart(fig_f, use_container_width=True)
        
    with c2:
        # Distribuição da Renúncia
        df['Porte'] = pd.cut(df['Receita'], bins=[0, 4.8e6, 78e6, 300e6], labels=['Simples/Micro', 'Pequena/Média', 'Transição/Grande'])
        fig_dist = px.bar(df.groupby('Porte')[['Renúncia', 'P&D_Induzido']].sum().reset_index(), 
                          x='Porte', y=['Renúncia', 'P&D_Induzido'], barmode='group', title="Impacto por Porte")
        st.plotly_chart(fig_dist, use_container_width=True)

with tab2:
    st.header("Simulador de Firma Individual")
    st.info("Utilize este módulo para testar o 'Efeito Preço' em uma empresa específica.")
    
    col_a, col_b = st.columns(2)
    with col_a:
        receita_f = st.number_input("Receita Bruta Anual (R$)", value=40000000.0, step=1000000.0)
        gasto_f = st.number_input("Gasto Atual em P&D (R$)", value=4000000.0, step=100000.0)
    
    imp_s, imp_r, ren_f, f_f = simular_reti(receita_f, gasto_f)
    
    with col_b:
        st.write(f"**Fator F Aplicado:** {f_f:.2f}")
        st.write(f"**Economia Tributária:** R$ {ren_f:,.2f}")
        st.write(f"**Alíquota Efetiva (IRPJ/CSLL):** {(imp_r/receita_f)*100:.2f}%")
        
    # Gauge Chart para Alíquota Efetiva
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = (imp_r/receita_f)*100,
        title = {'text': "Alíquota Efetiva sobre Receita (%)"},
        gauge = {'axis': {'range': [0, 8]},
                 'steps' : [
                     {'range': [0, 3], 'color': "lightgreen"},
                     {'range': [3, 7.68], 'color': "gray"}],
                 'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 7.68}})) # 7.68% é o padrão do Lucro Presumido
    st.plotly_chart(fig_gauge)

with tab3:
    st.markdown(f"""
    ### Regras de Ouro do RETI (Resumo Executivo)
    
    1. **Efeito Preço:** O Fator F de **{f_max}** a **1.0** reduz o custo marginal do P&D.
    2. **Carry-forward:** Créditos acumulados prescrevem em 4 anos para evitar passivos.
    3. **Gatilho de Performance:** Após 36 meses, a empresa deve comprovar:
        - Depósito de Patente OU;
        - >15% do pessoal científico (PoTec) OU;
        - Crescimento de Receita > 10% a.a.
    4. **Ajuste Automático:** Se a renúncia anual > R$ {teto_renuncia/1e9} Bi, o multiplicador de {multiplicador_fixo} 
    é reduzido por ato do Executivo para o ano seguinte.
    """)

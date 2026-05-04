import streamlit as st
import pandas as pd
import numpy as np

# Configuração de interface
st.set_page_config(page_title="Simulador RETI 2.0", layout="wide")

# --- LÓGICA TÉCNICA REFINADA ---

class MotorRETI:
    def __init__(self, mult_fixo=1.25, teto_fiscal=2.2e9):
        self.mult_fixo = mult_fixo
        self.teto_fiscal = teto_fiscal
        self.aliquota_lp = 0.24 # IRPJ + CSLL no Lucro Presumido

    def calcular_fator_f(self, receita):
        r_m = receita / 1e6
        if r_m <= 3.24: return 3.5
        if r_m <= 16.2: return 2.5
        if r_m <= 78: return 2.5
        if r_m <= 200:
            # Conforme Proposta: Redução de 0,012 a cada R$ 1M adicional acima de 78M
            f = 2.5 - ((r_m - 78) * 0.012)
            return max(f, 1.0)
        return 1.0

    def simular_firma(self, dados):
        """
        Calcula o impacto considerando a segregação do Simples e o Carry-forward
        """
        receita = dados['receita']
        pd_gasto = dados['pd_gasto']
        fator_f = self.calcular_fator_f(receita)
        
        # 1. Base de Cálculo Presumida Original
        base_presumida = receita * 0.32
        imposto_original = base_presumida * self.aliquota_lp
        
        # 2. Cálculo do Incentivo RETI
        # Equação Fundamental: (Receita x 0,32) - (1,25 x P&D x F)
        deducao_pd = self.mult_fixo * pd_gasto * fator_f
        base_reti = base_presumida - deducao_pd
        
        # Salvaguarda 1 (Item 6.1): Cap de Exoneração (mínimo 25% da base presumida)
        base_minima = base_presumida * 0.25
        base_final = max(base_reti, base_minima)
        
        imposto_devido_reti = base_final * self.aliquota_lp
        beneficio_potencial = imposto_original - imposto_devido_reti
        
        # Salvaguarda 2 (Item 6.2): Trava de Fluxo de Caixa (Compensação limitada a 50%)
        limite_compensacao = imposto_original * 0.50
        beneficio_efetivo_ano = min(beneficio_potencial, limite_compensacao)
        credito_estoque = beneficio_potencial - beneficio_efetivo_ano
        
        return {
            'imp_original': imposto_original,
            'imp_reti': imposto_original - beneficio_efetivo_ano,
            'renuncia': beneficio_efetivo_ano,
            'credito_carry_forward': credito_estoque,
            'fator_f': fator_f,
            'migrou_simples': dados['is_simples'] and (pd_gasto/receita > 0.10)
        }

# --- INTERFACE STREAMLIT ---

st.sidebar.title("Configurações SPE/MF")
teto = st.sidebar.number_input("Teto LRF (R$ Bi)", value=2.2) * 1e9
m_fixo = st.sidebar.slider("Multiplicador Fixo (Base)", 1.0, 1.5, 1.25)

st.title("🏛️ Simulador RETI - Análise de Política Industrial")

# Abas de Análise
aba_macro, aba_performance, aba_tecnica = st.tabs(["Impacto Orçamentário", "Gatilhos de Performance", "Metodologia"])

with aba_macro:
    # Simulação de População de Empresas
    n_empresas = 4500
    np.random.seed(42)
    
    # Criando DataFrame sintético mais realista
    df_pop = pd.DataFrame({
        'receita': np.random.lognormal(16, 1.2, n_empresas),
        'pd_gasto_percent': np.random.uniform(0.02, 0.15, n_empresas),
        'is_simples': np.random.choice([True, False], n_empresas, p=[0.7, 0.3])
    })
    df_pop['receita'] = np.clip(df_pop['receita'], 5e5, 3e8)
    df_pop['pd_gasto'] = df_pop['receita'] * df_pop['pd_gasto_percent']
    
    # Rodar Motor
    motor = MotorRETI(mult_fixo=m_fixo, teto_fiscal=teto)
    resultados = df_pop.apply(motor.simular_firma, axis=1, result_type='expand')
    df_final = pd.concat([df_pop, resultados], axis=1)
    
    # Verificação do Ajuste Automático (Item 5.2.3)
    total_renuncia = df_final['renuncia'].sum()
    if total_renuncia > teto:
        ajuste = teto / total_renuncia
        m_ajustado = m_fixo * ajuste
        st.warning(f"⚠️ Teto Ultrapassado! O multiplicador automático para o próximo exercício seria: {m_ajustado:.2f}")
    
    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Renúncia Estimada", f"R$ {total_renuncia/1e9:.2f}B")
    c2.metric("Investimento P&D Privado", f"R$ {(total_renuncia * 1.27)/1e9:.2f}B")
    c3.metric("Firms no Carry-forward", len(df_final[df_final['credito_carry_forward'] > 0]))
    c4.metric("Migração Simples -> RETI", df_final['migrou_simples'].sum())

with aba_performance:
    st.subheader("Gatilhos de Performance e Perda de Créditos")
    st.markdown("""
    O RETI induz resultados. Após 36 meses, se a firma não atingir os critérios, o carry-forward é suspenso.
    """)
    
    # Slider de Performance da Indústria
    taxa_sucesso = st.slider(" % de Empresas que atingem Gatilhos (Patentes/PoTec/Crescimento)", 0, 100, 70)
    
    credito_total = df_final['credito_carry_forward'].sum()
    perda_estimada = credito_total * (1 - (taxa_sucesso/100))
    
    col_a, col_b = st.columns(2)
    col_a.info(f"Estoque total de créditos acumulados: R$ {credito_total/1e6:.2f}M")
    col_b.error(f"Renúncia evitada por falta de performance: R$ {perda_estimada/1e6:.2f}M")

with aba_tecnica:
    st.markdown(f"""
    ### Detalhamento da Modelagem
    1. **Fator F (Tapering):** Implementado com declínio de 0,012/R$1M para evitar o *Notch Effect*.
    2. **Neutralidade de Ciclo:** O carry-forward modelado permite que empresas em prejuízo contábil acumulem o benefício para quando houver receita operacional.
    3. **RETI-SME:** Identificamos `{df_final['migrou_simples'].sum()}` empresas do Simples que teriam incentivo econômico para segregar a contabilidade de P&D.
    4. **Elasticidade:** Aplicado coeficiente de -1,27 (Kannebley Jr. et al) sobre a renúncia efetiva.
    """)

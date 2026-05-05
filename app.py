import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────────────────────
# CONFIGURAÇÃO E DESIGN SYSTEM
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Simulador RETI v10.25", layout="wide")

st.markdown("""
    <style>
  .main { background-color: #0A0E1A; }
  .stMetric { 
        background-color: #0F1525; 
        border: 1px solid #1E2A45; 
        padding: 15px; 
        border-radius: 10px; 
    }
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# MOTOR DE CÁLCULO TÉCNICO (TR-SPE/Fazenda & RFB Compliant)
# ─────────────────────────────────────────────────────────────

def calcular_fator_f_bidimensional(receita, intensidade_pd, ajuste_extra_f=0):
    """
    Implementa a Matriz Bidimensional da Proposta Final.
    Aplica escalonamento por porte e trava de intensidade de 5%.
    """
    # 1. Escalonamento por Porte
    if receita <= 3.24:
        f_base = 3.5
    elif receita <= 16.2:
        f_base = 3.0
    elif receita <= 78.0:
        f_base = 2.5
    elif receita <= 200.0:
        # Tapering linear de 0,012 por R$ 1M adicional de receita
        f_base = max(1.0, 2.5 - 0.012 * (receita - 78.0))
    else:
        f_base = 1.0

    # Aplica redução se o gatilho LRF do ano anterior foi ativado
    f_base = max(1.0, f_base - ajuste_extra_f)

    # 2. Trava de Intensidade (Módulo Anti-Arbitragem) 
    if intensidade_pd < 0.05:
        return max(1.0, f_base - 1.0)
    return f_base

def run_reti_engine(p):
    # Parâmetros Estruturais
    ALIQUOTA = 0.34
    PRESUNCAO = 0.32
    LAG = 3         # Maturação P&D para PTF
    DEPREC = 0.15   # Depreciação do estoque de conhecimento
    SUCESSO = 0.70  # Taxa de sucesso técnico

    rows = # CORREÇÃO DA SINTAXE: Inicialização como lista vazia
    estoque_conhecimento = 0
    estoque_credito = 0
    historico_maturacao = np.zeros(p['horizonte'] + LAG + 5)
    receita = p['rec_inicial']
    
    # Variáveis para controle de ajuste paramétrico (Hierarquia de Preferência)
    violation_last_year = False
    m_dinamico = p['mult_base']
    f_penalidade = 0

    for t in range(1, p['horizonte'] + 1):
        rec_ant = receita
        receita *= (1 + p['crescimento'])
        
        # 1. Regra de Ajuste Automático (Art. 7.2 da Proposta)
        if violation_last_year:
            # Hierarquia: 1. Multiplicador, 2. Fator F
            m_dinamico = max(1.0, p['mult_base'] - 0.15)
            f_penalidade = 0.3
        else:
            m_dinamico = p['mult_base']
            f_penalidade = 0

        f = calcular_fator_f_bidimensional(receita, p['intensidade_pd'], f_penalidade)
        
        # 2. Adicionalidade (Kannebley, 2016): ε = -1.27
        pd_original = receita * p['intensidade_pd']
        beneficio_marginal = (m_dinamico * f * ALIQUOTA)
        pd_adicional = pd_original * abs(p['elasticidade']) * beneficio_marginal
        pd_total = pd_original + pd_adicional
        
        if t + LAG <= p['horizonte'] + LAG:
            historico_maturacao[t + LAG] = pd_adicional * SUCESSO

        # 3. Transmissão PTF (Metodologia SPE 2025)
        pd_maturado = historico_maturacao[t]
        estoque_conhecimento = estoque_conhecimento * (1 - DEPREC) + pd_maturado
        ganho_ptf = (estoque_conhecimento / receita) * p['beta_ptf'] if receita > 0 else 0
        
        # 4. Retorno Fiscal Indireto (PIB Dinâmico)
        retorno_indireto = (receita * ganho_ptf) * ALIQUOTA

        # 5. Engenharia de Créditos e Salvaguardas
        imp_ref = (receita * PRESUNCAO) * ALIQUOTA
        limite_anual_comp = imp_ref * 0.50 # Trava de 50%
        
        novo_credito = (m_dinamico * pd_total * f) * ALIQUOTA
        estoque_credito += novo_credito

        # 6. Gatilho de Performance (PoTec 15% conforme IBGE/PINTEC) [5]
        pode_usar = True
        if t > 3:
            cond_rec = (receita / rec_ant - 1) >= 0.10
            cond_pat = p['patente_ano'] <= t
            cond_potec = p['potec'] >= 15
            pode_usar = cond_rec or cond_pat or cond_potec

        uso_efetivo = min(estoque_credito, limite_anual_comp) if pode_usar else 0
        imp_final = max(imp_ref * 0.25, imp_ref - uso_efetivo) # Salvaguarda 25%
        renuncia_unitaria = imp_ref - imp_final
        estoque_credito -= renuncia_unitaria

        # 7. Agregação Macro (R$ Bilhões)
        firmas = p['n_firmas'] / (1 + np.exp(-1.2 * (t - 3))) # Adesão sigmóide
        ren_macro = (renuncia_unitaria * firmas) / 1000
        ret_macro = (retorno_indireto * firmas) / 1000
        
        # Verifica violação para disparar ajuste no ano t+1
        violation_last_year = ren_macro > p['teto_lrf']

        rows.append({
            "Ano": t, "Fator F": f, "Multiplicador": m_dinamico, 
            "Ganho PTF (%)": ganho_ptf * 100, "Renúncia (R$ Bi)": ren_macro, 
            "Retorno (R$ Bi)": ret_macro, "Saldo (R$ Bi)": ret_macro - ren_macro,
            "Adesão": int(firmas), "LRF": "✓" if not violation_last_year else "⚠"
        })

    return pd.DataFrame(rows)

# ─────────────────────────────────────────────────────────────
# INTERFACE STREAMLIT
# ─────────────────────────────────────────────────────────────

st.title("🛡️ Simulador RETI - Protocolo SPE/Fazenda")
st.caption("Fomento à Inovação com Responsabilidade Fiscal Paramétrica")

with st.sidebar:
    st.header("⚙️ Configurações de Política")
    n_firmas = st.number_input("Universo Elegível (PMEs)", value=4500)
    teto_lrf = st.slider("Teto LRF (R$ Bi/ano)", 0.5, 5.0, 2.2)
    mult_base = st.slider("Multiplicador M (Dedução)", 1.0, 1.5, 1.25)
    
    st.header("🔬 Perfil da Firma")
    rec_inicial = st.number_input("Receita Inicial (R$ MM)", value=15.0)
    intensidade_pd = st.slider("Intensidade P&D", 0.01, 0.25, 0.07)
    crescimento = st.slider("Crescimento Anual", 0.0, 0.30, 0.12)
    
    st.header("📈 Premissas Macro (SPE)")
    beta_ptf = st.slider("β (Transmissão PTF)", 0.03, 0.12, 0.06)
    potec = st.slider("Pessoal Técnico (%)", 0, 30, 18)

# Execução
df = run_reti_engine({
    "n_firmas": n_firmas, "mult_base": mult_base, "rec_inicial": rec_inicial,
    "intensidade_pd": intensidade_pd, "crescimento": crescimento,
    "elasticidade": -1.27, "beta_ptf": beta_ptf, "horizonte": 10,
    "potec": potec, "patente_ano": 3, "teto_lrf": teto_lrf
})

# KPIs
c1, c2, c3, c4 = st.columns(4)
total_ren = df.sum()
total_ret = df.sum()
roi = (total_ret / total_ren - 1) * 100 if total_ren > 0 else 0

c1.metric("Custo Fiscal Total", f"R$ {total_ren:.2f} Bi")
c2.metric("Retorno PIB (PTF)", f"R$ {total_ret:.2f} Bi")
c3.metric("ROI Líquido", f"{roi:.1f}%")
c4.metric("Consistência LRF", "CONFORME" if df.max() <= teto_lrf else "ALERTA")

# Visualização
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["Ano"], y=df, name="Custo (Renúncia)", fill='tozeroy', line_color='#E05252'))
fig.add_trace(go.Scatter(x=df["Ano"], y=df, name="Retorno (PIB Dinâmico)", fill='tozeroy', line_color='#3EC97B'))
fig.add_hline(y=teto_lrf, line_dash="dash", line_color="orange", annotation_text="Teto LRF")
fig.update_layout(template="plotly_dark", height=450)
st.plotly_chart(fig, use_container_width=True)

if st.checkbox("Exibir Memória de Cálculo Anual"):
    st.dataframe(df.style.format("{:.3f}"))

st.info("Metodologia: Fator F bidimensional $$. Adicionalidade de -1,27 $[6]$. Transmissão PTF via Resíduo de Solow SPE/2025 $[7]$.")

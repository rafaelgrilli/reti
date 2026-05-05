import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────────────────────
# CONFIGURAÇÃO E DESIGN SYSTEM
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Simulador RETI v10.20", layout="wide")

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

def calcular_fator_f_bidimensional(receita, intensidade_pd, ajuste_fator_f=0):
    """
    Implementa a Matriz Bidimensional da Proposta V17 corrigida.
    """
    # 1. Escalonamento por Porte
    if receita <= 3.24:
        f_base = 3.5
    elif receita <= 16.2:
        f_base = 3.0
    elif receita <= 78.0:
        f_base = 2.5
    elif receita <= 200.0:
        # Tapering linear de 0,012 por R$ 1M excedente (Ref. Proposta TR-SPE)
        f_base = max(1.0, 2.5 - 0.012 * (receita - 78.0))
    else:
        f_base = 1.0

    # Aplica ajuste paramétrico se houver estouro de teto LRF
    f_base = max(1.0, f_base - ajuste_fator_f)

    # 2. Trava de Intensidade (Módulo Anti-Arbitragem)
    # Threshold de 15% conforme última revisão de inclusão para SMEs
    if intensidade_pd < 0.05:
        return max(1.0, f_base - 1.0)
    return f_base

def run_reti_engine(p):
    # Parâmetros Estruturais
    ALIQUOTA = 0.34
    PRESUNCAO = 0.32
    LAG = 3
    DEPREC = 0.15
    SUCESSO = 0.70

    rows = # INICIALIZAÇÃO CORRIGIDA
    estoque_conhecimento = 0
    estoque_credito = 0
    historico_maturacao = np.zeros(p['horizonte'] + LAG + 2)
    receita = p['rec_inicial']

    for t in range(1, p['horizonte'] + 1):
        rec_ant = receita
        receita *= (1 + p['crescimento'])
        
        # Ajustes automáticos caso o teto seja ultrapassado (Hierarquia de Preferência)
        m_ajustado = p['mult_base']
        f_ajustado = 0
        if p.get('trigger_lrf') and t > 1:
            # Simulação de ajuste paramétrico: reduz M primeiro, depois F
            m_ajustado = max(1.0, p['mult_base'] - 0.05) 
            f_ajustado = 0.2

        f = calcular_fator_f_bidimensional(receita, p['intensidade_pd'], f_ajustado)
        
        # Adicionalidade (Kannebley, 2016): ε = -1.27
        pd_original = receita * p['intensidade_pd']
        beneficio_marginal = (m_ajustado * f * ALIQUOTA)
        pd_adicional = pd_original * abs(p['elasticidade']) * beneficio_marginal
        pd_total = pd_original + pd_adicional
        
        if t + LAG <= p['horizonte'] + 1:
            historico_maturacao[t + LAG] = pd_adicional * SUCESSO

        # Transmissão PTF (Metodologia SPE 2025)
        pd_maturado = historico_maturacao[t]
        estoque_conhecimento = estoque_conhecimento * (1 - DEPREC) + pd_maturado
        ganho_ptf = (estoque_conhecimento / receita) * p['beta_ptf'] if receita > 0 else 0
        
        # ROI Dinâmico
        retorno_indireto = (receita * ganho_ptf) * ALIQUOTA

        # Regras de Crédito e Salvaguardas
        imp_ref = (receita * PRESUNCAO) * ALIQUOTA
        limite_anual_comp = imp_ref * 0.50
        
        novo_credito = (m_ajustado * pd_total * f) * ALIQUOTA
        estoque_credito += novo_credito

        # Gatilhos de Performance
        pode_usar = True
        if t > 3:
            cond_rec = (receita / rec_ant - 1) >= 0.10
            cond_pat = p['patente_ano'] <= t
            cond_potec = p['potec'] >= 15
            pode_usar = cond_rec or cond_pat or cond_potec

        uso_efetivo = min(estoque_credito, limite_anual_comp) if pode_usar else 0
        imp_final = max(imp_ref * 0.25, imp_ref - uso_efetivo)
        renuncia_unitaria = imp_ref - imp_final
        estoque_credito -= renuncia_unitaria

        # Agregação Macro
        firmas = p['n_firmas'] / (1 + np.exp(-1.2 * (t - 3)))
        ren_macro = (renuncia_unitaria * firmas) / 1000
        ret_macro = (retorno_indireto * firmas) / 1000

        rows.append({
            "Ano": t, "Fator F": f, "PTF (%)": ganho_ptf * 100,
            "Renúncia (R$ Bi)": ren_macro, "Retorno (R$ Bi)": ret_macro,
            "Saldo (R$ Bi)": ret_macro - ren_macro, "Adesão": int(firmas)
        })

    return pd.DataFrame(rows)

# ─────────────────────────────────────────────────────────────
# INTERFACE
# ─────────────────────────────────────────────────────────────

st.title("🛡️ Simulador RETI - Protocolo SPE/RFB")
st.caption("v10.20 | Sistema Paramétrico de Fomento à Inovação")

with st.sidebar:
    st.header("⚙️ Política Fiscal")
    n_firmas = st.number_input("Universo Elegível", value=4500)
    teto_lrf = st.slider("Teto LRF (R$ Bi/ano)", 0.5, 5.0, 2.2)
    mult_base = st.slider("Multiplicador M", 1.0, 1.5, 1.25)
    st.header("🔬 Perfil da Firma")
    rec_inicial = st.number_input("Receita Inicial (R$ MM)", value=15.0)
    intensidade_pd = st.slider("Intensidade P&D", 0.01, 0.25, 0.07)
    crescimento = st.slider("Crescimento Anual", 0.0, 0.30, 0.12)
    st.header("📈 Premissas Macro")
    beta_ptf = st.slider("β (Transmissão PTF)", 0.03, 0.12, 0.06)
    potec = st.slider("PoTec (%)", 0, 30, 18)

# Execução
df = run_reti_engine({
    "n_firmas": n_firmas, "mult_base": mult_base, "rec_inicial": rec_inicial,
    "intensidade_pd": intensidade_pd, "crescimento": crescimento,
    "elasticidade": -1.27, "beta_ptf": beta_ptf, "horizonte": 10,
    "potec": potec, "patente_ano": 3, "trigger_lrf": df.max() > teto_lrf if 'df' in locals() else False
})

# KPIs
k1, k2, k3, k4 = st.columns(4)
total_ren = df.sum()
total_ret = df.sum()
roi = (total_ret / total_ren - 1) * 100 if total_ren > 0 else 0

k1.metric("Custo Total (10a)", f"R$ {total_ren:.2f} Bi")
k2.metric("Retorno PIB (PTF)", f"R$ {total_ret:.2f} Bi")
k3.metric("ROI Líquido", f"{roi:.1f}%")
k4.metric("Status LRF", "CONFORME" if df.max() <= teto_lrf else "ALERTA")

# Visualização
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["Ano"], y=df, name="Renúncia", fill='tozeroy', line_color='#E05252'))
fig.add_trace(go.Scatter(x=df["Ano"], y=df, name="Retorno (PTF)", fill='tozeroy', line_color='#3EC97B'))
fig.add_hline(y=teto_lrf, line_dash="dash", line_color="orange")
fig.update_layout(template="plotly_dark", height=400)
st.plotly_chart(fig, use_container_width=True)

if st.checkbox("Ver Memória de Cálculo"):
    st.write(df.style.format("{:.3f}"))

st.info("Metodologia: Fator F bidimensional $[2]$. Adicionalidade de -1,27 $[3]$. Transmissão PTF via Resíduo de Solow SPE/2025 $[1]$.")

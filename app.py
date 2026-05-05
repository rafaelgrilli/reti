import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────────────────────
# 1. CONFIGURAÇÃO E DESIGN SYSTEM (UI/UX)
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Simulador RETI v10.25 - Full Compliance", layout="wide")

st.markdown("""
    <style>
        .stApp { background-color: #0A0E1A; }
        [data-testid="stMetric"] {
            background-color: #161C2D !important;
            border: 1px solid #242D45 !important;
            padding: 20px !important;
            border-radius: 12px !important;
        }
        [data-testid="stMetricLabel"] { color: #94A3B8 !important; font-size: 14px !important; font-weight: 600 !important; }
        [data-testid="stMetricValue"] { color: #FFFFFF !important; font-size: 28px !important; }
        h1, h2, h3 { color: #F8FAFC !important; }
        .stCaption { color: #94A3B8 !important; }
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# 2. MOTOR DE CÁLCULO TÉCNICO (RETI FULL COMPLIANCE)
# ─────────────────────────────────────────────────────────────

def calcular_fator_f_bidimensional(receita, intensidade_pd, ajuste_extra_f=0):
    """Implementa o Tapering Linear (Item 3 da Proposta)"""
    if receita <= 3.24: f_base = 3.5
    elif receita <= 16.2: f_base = 3.0
    elif receita <= 78.0: f_base = 2.5
    elif receita <= 200.0:
        # Phasing-out: -0.012 por R$ 1M adicional (Item 3)
        f_base = max(1.0, 2.5 - 0.012 * (receita - 78.0))
    else: f_base = 1.0

    f_base = max(1.0, f_base - ajuste_extra_f)
    
    # Módulo Anti-Arbitragem (Item 5)
    if intensidade_pd < 0.05:
        return max(1.0, f_base - 1.0)
    return f_base

def run_reti_engine(p):
    ALIQUOTA = 0.34
    PRESUNCAO = 0.32
    LAG = 3         
    DEPREC = 0.15   
    SUCESSO = 0.70  

    rows = [] 
    estoque_conhecimento = 0
    historico_maturacao = np.zeros(p['horizonte'] + LAG + 5)
    receita = p['rec_inicial']
    
    # Estado do Sistema Autoajustável (Item 7)
    violation_last_year = False
    m_dinamico = p['mult_base']
    f_penalidade = 0

    for t in range(1, p['horizonte'] + 1):
        rec_ant = receita
        receita *= (1 + p['crescimento'])
        
        # 1. Hierarquia de Ajuste Paramétrico (Item 7)
        if violation_last_year:
            if m_dinamico > 1.0:
                m_dinamico = max(1.0, m_dinamico - 0.10) # 1ª Preferência: Reduz Multiplicador
            else:
                f_penalidade = 0.4 # 2ª Preferência: Recalibra Fator F
        
        f = calcular_fator_f_bidimensional(receita, p['intensidade_pd'], f_penalidade)
        
        # 2. Adicionalidade (Kannebley, 2016)
        pd_original = receita * p['intensidade_pd']
        beneficio_marginal = (m_dinamico * f * ALIQUOTA)
        pd_adicional = pd_original * abs(p['elasticidade']) * beneficio_marginal
        pd_total = pd_original + pd_adicional
        
        # 3. Transmissão PTF (Item 4.1)
        if t + LAG < len(historico_maturacao):
            historico_maturacao[t + LAG] = pd_adicional * SUCESSO
        
        pd_maturado = historico_maturacao[t]
        estoque_conhecimento = estoque_conhecimento * (1 - DEPREC) + pd_maturado
        ganho_ptf = (estoque_conhecimento / receita) * p['beta_ptf'] if receita > 0 else 0
        retorno_indireto = (receita * ganho_ptf) * ALIQUOTA

        # 4. Gatilhos de Performance (Item 5)
        pode_usar = True
        if t > 3:
            cond_rec = (receita / rec_ant - 1) >= 0.10
            cond_pat = p['patente_ano'] <= t
            cond_potec = p['potec'] >= 15
            pode_usar = cond_rec or cond_pat or cond_potec

        # 5. Cálculo do Benefício por Regime
        if p['regime'] == "Lucro Presumido":
            # Engenharia Fiscal (Item 3): Base = (Rec * 0.32) - (M * PD * F)
            base_original = receita * PRESUNCAO
            base_reduzida = max(base_original * 0.25, base_original - (m_dinamico * pd_total * f))
            renuncia_unitaria = (base_original - base_reduzida) * ALIQUOTA if pode_usar else 0
        else:
            # RETI-SME (Item 6): Innovation Vouchers
            # Threshold de entrada de 15% de intensidade
            if p['intensidade_pd'] >= 0.15 and pode_usar:
                # Voucher progressivo até 30% de intensidade
                intensidade_efetiva = min(p['intensidade_pd'], 0.30)
                renuncia_unitaria = pd_total * intensidade_efetiva * f * 0.5 # Simulação de crédito direto
            else:
                renuncia_unitaria = 0

        # 6. Agregação Macro
        firmas = p['n_firmas'] / (1 + np.exp(-1.2 * (t - 3))) 
        ren_macro = (renuncia_unitaria * firmas) / 1000
        ret_macro = (retorno_indireto * firmas) / 1000
        
        violation_last_year = ren_macro > p['teto_lrf']

        rows.append({
            "Ano": t, "Fator F": f, "Multiplicador": m_dinamico, 
            "Renúncia (R$ Bi)": ren_macro, "Retorno (R$ Bi)": ret_macro, 
            "Saldo Anual": ret_macro - ren_macro, "Adesão": int(firmas)
        })

    return pd.DataFrame(rows)

# ─────────────────────────────────────────────────────────────
# 3. INTERFACE STREAMLIT
# ─────────────────────────────────────────────────────────────

st.title("🛡️ Simulador RETI - Protocolo SPE/Fazenda")
st.caption("Versão 10.25 - 100% Alinhada ao Termo de Referência Final")

with st.sidebar:
    st.header("📋 Regime e Escopo")
    regime = st.selectbox("Regime Tributário", ["Lucro Presumido", "Simples Nacional (RETI-SME)"])
    n_firmas = st.number_input("Universo de Firmas", value=4500 if regime == "Lucro Presumido" else 12000)
    
    st.header("⚙️ Parâmetros de Política")
    t_lrf = st.slider("Teto LRF (R$ Bi/ano)", 0.5, 5.0, 1.8) # Default 1.8 conforme item 7
    m_base = st.slider("Multiplicador M (Item 3)", 1.0, 1.5, 1.25)
    
    st.header("🔬 Perfil da Firma")
    i_pd = st.slider("Intensidade P&D (P&D/Receita)", 0.01, 0.40, 0.08)
    p_tec = st.slider("Pessoal Qualificado - PoTec (%)", 0, 50, 18)
    
    st.header("📈 Premissas Macro")
    b_ptf = st.slider("β (Elasticidade PTF)", 0.05, 0.08, 0.06) # Range item 4.1

# Execução
df = run_reti_engine({
    "regime": regime, "n_firmas": n_firmas, "mult_base": m_base, 
    "rec_inicial": 15.0, "intensidade_pd": i_pd, "crescimento": 0.12,
    "elasticidade": -1.27, "beta_ptf": b_ptf, "horizonte": 15,
    "potec": p_tec, "patente_ano": 3, "teto_lrf": t_lrf
})

# KPIs
total_ren = df["Renúncia (R$ Bi)"].sum()
total_ret = df["Retorno (R$ Bi)"].sum()
roi = (total_ret / total_ren - 1) * 100 if total_ren > 0 else 0

# Cálculo de Payback (Ano onde o saldo acumulado vira positivo)
df['Acumulado'] = (df['Retorno (R$ Bi)'] - df['Renúncia (R$ Bi)']).cumsum()
payback_list = df[df['Acumulado'] > 0]['Ano'].values
payback_ano = payback_list[0] if len(payback_list) > 0 else " > 15"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Custo Total (15 anos)", f"R$ {total_ren:.2f} Bi")
c2.metric("Retorno PIB (PTF)", f"R$ {total_ret:.2f} Bi")
c3.metric("Payback Fiscal", f"Ano {payback_ano}")
c4.metric("Consistência LRF", "CONFORME" if df["Renúncia (R$ Bi)"].max() <= t_lrf else "AJUSTE ATIVADO")

# Gráfico
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["Ano"], y=df["Renúncia (R$ Bi)"], name="Custo Fiscal", fill='tozeroy', line_color='#E05252'))
fig.add_trace(go.Scatter(x=df["Ano"], y=df["Retorno (R$ Bi)"], name="Retorno PIB", fill='tozeroy', line_color='#3EC97B'))
fig.add_hline(y=t_lrf, line_dash="dash", line_color="orange", annotation_text="Teto LRF")
fig.update_layout(template="plotly_dark", height=400, margin=dict(l=10, r=10, t=40, b=10))
st.plotly_chart(fig, use_container_width=True)

# Alertas de Compliance
if regime == "Simples Nacional (RETI-SME)" and i_pd < 0.15:
    st.warning("⚠️ **Atenção:** Intensidade de P&D abaixo de 15%. Conforme Item 6 da proposta, a firma não é elegível ao Voucher no Simples Nacional.")

if status_lrf := df["Renúncia (R$ Bi)"].max() > t_lrf:
    st.info("🔄 **Sistema Autoajustável:** O teto LRF foi atingido. O motor aplicou a hierarquia do Item 7 (Redução de M e recalibragem do Fator F) para os anos subsequentes.")

with st.expander("Detalhamento da Memória de Cálculo"):
    st.dataframe(df.style.format(precision=3))

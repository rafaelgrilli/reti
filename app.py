import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────────────────────
# CONFIGURAÇÃO E DESIGN SYSTEM
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Simulador RETI v10.0", layout="wide")

st.markdown("""
    <style>
   .main { background-color: #0A0E1A; }
   .stMetric { background-color: #0F1525; border: 1px solid #1E2A45; padding: 15px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# MOTOR DE CÁLCULO TÉCNICO (SPE/MF & RFB Compliant)
# ─────────────────────────────────────────────────────────────

def calcular_fator_f(receita, intensidade_pd):
    """
    Implementa a Matriz Bidimensional da Proposta V17.
    O Fator F depende do porte (receita) e da intensidade (P&D/Receita).
    """
    # 1. Definição da Base por Porte
    if receita <= 3.24:
        f_base = 3.5
    elif receita <= 16.2:
        f_base = 3.0
    elif receita <= 78.0:
        f_base = 2.5
    elif receita <= 200.0:
        # Tapering linear de 0,012 por milhão excedente a 78M
        f_base = max(1.0, 2.5 - 0.012 * (receita - 78.0))
    else:
        f_base = 1.0

    # 2. Trava de Intensidade (Gatilho de 5%)
    # Se a empresa investe menos de 5% em P&D, o Fator F é reduzido em 1.0 ponto
    if intensidade_pd < 0.05:
        return max(1.0, f_base - 1.0)
    return f_base

def run_reti_engine(p):
    # Parâmetros fixos da proposta
    ALÍQUOTA_COMBINADA = 0.34
    PRESUNCAO_LP = 0.32
    LAG_MATURACAO = 3
    DEPREC_ESTOQUE = 0.15
    TAXA_SUCESSO = 0.70

    rows =
    estoque_conhecimento = 0
    estoque_credito = 0
    historico_pd_adicional = np.zeros(p['horizonte'] + LAG_MATURACAO + 1)

    receita = p['rec_inicial']

    for t in range(1, p['horizonte'] + 1):
        rec_ant = receita
        receita *= (1 + p['crescimento'])
        
        # Cálculo do Fator F Bidimensional
        f = calcular_fator_f(receita, p['intensidade_pd'])
        
        # Efeito Preço: Adicionalidade via Elasticidade (Kannebley et al., 2016)
        pd_original = receita * p['intensidade_pd']
        # Adicionalidade = Investimento induzido pela redução do user cost
        pd_adicional = pd_original * abs(p['elasticidade']) * (p['mult_base'] * f * ALÍQUOTA_COMBINADA)
        pd_total = pd_original + pd_adicional
        
        if t + LAG_MATURACAO <= p['horizonte']:
            historico_pd_adicional = pd_adicional * TAXA_SUCESSO

        # Função de Transmissão SPE: P&D -> PTF -> PIB
        pd_maturado = historico_pd_adicional[t]
        estoque_conhecimento = estoque_conhecimento * (1 - DEPREC_ESTOQUE) + pd_maturado
        ganho_prod = (estoque_conhecimento / receita) * p['beta_ptf'] if receita > 0 else 0
        
        # Retorno Fiscal Indireto (Lucro futuro + Arrecadação Dinâmica)
        retorno_indireto = (receita * ganho_prod) * ALÍQUOTA_COMBINADA

        # Regras de Compensação e Salvaguardas (Art. 6 LRF)
        imp_ref = (receita * PRESUNCAO_LP) * ALÍQUOTA_COMBINADA
        limite_anual_comp = imp_ref * 0.50 # Trava de 50%
        
        novo_credito = (p['mult_base'] * pd_total * f) * ALÍQUOTA_COMBINADA
        estoque_credito += novo_credito

        # Gatilhos de Performance (Pós-36 meses)
        pode_usar = True
        if t > 3:
            cond_rec = (receita / rec_ant - 1) >= 0.10
            cond_pat = p['patente_ano'] <= t
            cond_potec = p['potec'] >= 15
            pode_usar = cond_rec or cond_pat or cond_potec

        uso_efetivo = min(estoque_credito, limite_anual_comp) if pode_usar else 0
        
        # Contribuição Mínima de 25% (Salvaguarda SPE)
        imp_final = max(imp_ref * 0.25, imp_ref - uso_efetivo)
        renuncia = imp_ref - imp_final
        estoque_credito -= renuncia

        # Agregação Macro (em R$ Bilhões)
        firmas_aderentes = p['n_firmas'] / (1 + np.exp(-1.2 * (t - 3))) # Curva Sigmóide
        renuncia_macro = (renuncia * firmas_aderentes) / 1000
        retorno_macro = (retorno_indireto * firmas_aderentes) / 1000

        rows.append({
            "Ano": t,
            "Fator F": f,
            "P&D Total (MM)": pd_total,
            "Ganho PTF (%)": ganho_prod * 100,
            "Renúncia (R$ Bi)": renuncia_macro,
            "Retorno (R$ Bi)": retorno_macro,
            "Saldo (R$ Bi)": retorno_macro - renuncia_macro,
            "Adesão": firmas_aderentes
        })

    return pd.DataFrame(rows)

# ─────────────────────────────────────────────────────────────
# INTERFACE STREAMLIT
# ─────────────────────────────────────────────────────────────

st.title("🛡️ Simulador RETI - Protocolo SPE/Fazenda")
st.subheader("Regime Especial de Tributação para a Inovação - v10.10")

with st.sidebar:
    st.header("⚙️ Parâmetros de Política")
    n_firmas = st.number_input("Universo de Firmas (PMEs)", value=4500)
    teto_lrf = st.slider("Teto LRF (R$ Bi/ano)", 0.5, 5.0, 2.2)
    mult_base = st.slider("Multiplicador Superdedução (M)", 1.0, 1.5, 1.25)
    
    st.header("🔬 Perfil Micro (Firma)")
    rec_inicial = st.number_input("Receita Inicial (R$ MM)", value=15.0)
    intensidade_pd = st.slider("Intensidade P&D Original", 0.01, 0.20, 0.07, format="%.2f")
    crescimento = st.slider("Crescimento Anual Receita", 0.0, 0.30, 0.12)
    
    st.header("📈 Premissas Macro (SPE)")
    elasticidade = st.slider("Elasticidade-Custo (Kannebley)", -2.0, -0.5, -1.27)
    beta_ptf = st.slider("β (P&D → PTF)", 0.03, 0.12, 0.06)
    
    st.header("🚩 Gatilhos de Performance")
    potec = st.slider("Pessoal Técnico (%)", 0, 30, 18)
    patente_ano = st.slider("Ano de Depósito Patente", 1, 10, 3)

# Processamento
params = {
    "n_firmas": n_firmas, "mult_base": mult_base, "rec_inicial": rec_inicial,
    "intensidade_pd": intensidade_pd, "crescimento": crescimento,
    "elasticidade": elasticidade, "beta_ptf": beta_ptf, "horizonte": 10,
    "potec": potec, "patente_ano": patente_ano
}

df = run_reti_engine(params)

# KPIs
c1, c2, c3, c4 = st.columns(4)
total_ren = df.sum()
total_ret = df.sum()
roi_liq = (total_ret / total_ren - 1) * 100 if total_ren > 0 else 0

c1.metric("Custo Fiscal Total", f"R$ {total_ren:.2f} Bi", delta_color="inverse")
c2.metric("Retorno Indireto", f"R$ {total_ret:.2f} Bi")
c3.metric("ROI Líquido", f"{roi_liq:.1f}%")
c4.metric("Status LRF", "CONFORME" if df.max() <= teto_lrf else "ALERTA", 
          delta=f"Teto: {teto_lrf}")

# Gráficos
st.markdown("### Dinâmica Fiscal Dinâmica: Renúncia vs. Retorno via PTF")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["Ano"], y=df, name="Renúncia (Saída)", fill='tozeroy', line_color='#E05252'))
fig.add_trace(go.Scatter(x=df["Ano"], y=df, name="Retorno Indireto (Entrada)", fill='tozeroy', line_color='#3EC97B'))
fig.add_hline(y=teto_lrf, line_dash="dash", line_color="orange", annotation_text="Teto LRF")
fig.update_layout(template="plotly_dark", hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)

# Tabela Analítica
if st.checkbox("Visualizar Dados Brutos da Simulação"):
    st.dataframe(df.style.format({
        "Renúncia (R$ Bi)": "{:.3f}",
        "Retorno (R$ Bi)": "{:.3f}",
        "Saldo (R$ Bi)": "{:.3f}",
        "Ganho PTF (%)": "{:.2f}%",
        "Fator F": "{:.2f}"
    }))

st.info("""
**Nota Metodológica:**
1. **Fator F:** Bidimensional (Porte + Intensidade > 5%). [6]
2. **Adicionalidade:** Calculada via Elasticidade de User Cost (-1,27). [7]
3. **Transmissão Macro:** ΔPTF baseada no parâmetro Beta ({:.2f}) da literatura OCDE/SPE. 
4. **Mecanismo Tapering:** Redução linear de 0,012 para neutralizar notches tributários.
""".format(beta_ptf))

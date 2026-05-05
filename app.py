import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────────────────────
# 1. CONFIGURAÇÃO E DESIGN SYSTEM (UI/UX)
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Simulador RETI v10.25", layout="wide")

# CSS Customizado para Dark Mode e Contraste de Métricas
st.markdown("""
    <style>
        .stApp { background-color: #0A0E1A; }
        
        /* Estilização dos Cards de Métrica */
        [data-testid="stMetric"] {
            background-color: #161C2D !important;
            border: 1px solid #242D45 !important;
            padding: 20px !important;
            border-radius: 12px !important;
        }

        /* Cor do Título da Métrica (Label) */
        [data-testid="stMetricLabel"] {
            color: #94A3B8 !important;
            font-size: 14px !important;
            font-weight: 600 !important;
        }

        /* Cor do Valor da Métrica */
        [data-testid="stMetricValue"] {
            color: #FFFFFF !important;
            font-size: 28px !important;
        }

        h1, h2, h3 { color: #F8FAFC !important; }
        .stCaption { color: #94A3B8 !important; }
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# 2. MOTOR DE CÁLCULO TÉCNICO (TR-SPE/Fazenda)
# ─────────────────────────────────────────────────────────────

def calcular_fator_f_bidimensional(receita, intensidade_pd, ajuste_extra_f=0):
    """
    Implementa a Matriz Bidimensional. Escalonamento por porte e trava de 5%.
    """
    if receita <= 3.24:
        f_base = 3.5
    elif receita <= 16.2:
        f_base = 3.0
    elif receita <= 78.0:
        f_base = 2.5
    elif receita <= 200.0:
        f_base = max(1.0, 2.5 - 0.012 * (receita - 78.0))
    else:
        f_base = 1.0

    f_base = max(1.0, f_base - ajuste_extra_f)

    # Trava de Intensidade (Módulo Anti-Arbitragem)
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

    rows = [] 
    estoque_conhecimento = 0
    estoque_credito = 0
    historico_maturacao = np.zeros(p['horizonte'] + LAG + 5)
    receita = p['rec_inicial']
    
    violation_last_year = False
    m_dinamico = p['mult_base']
    f_penalidade = 0

    for t in range(1, p['horizonte'] + 1):
        rec_ant = receita
        receita *= (1 + p['crescimento'])
        
        # Regra de Ajuste Automático LRF
        if violation_last_year:
            m_dinamico = max(1.0, p['mult_base'] - 0.15)
            f_penalidade = 0.3
        else:
            m_dinamico = p['mult_base']
            f_penalidade = 0

        f = calcular_fator_f_bidimensional(receita, p['intensidade_pd'], f_penalidade)
        
        # Adicionalidade
        pd_original = receita * p['intensidade_pd']
        beneficio_marginal = (m_dinamico * f * ALIQUOTA)
        pd_adicional = pd_original * abs(p['elasticidade']) * beneficio_marginal
        pd_total = pd_original + pd_adicional
        
        if t + LAG < len(historico_maturacao):
            historico_maturacao[t + LAG] = pd_adicional * SUCESSO

        # Transmissão PTF
        pd_maturado = historico_maturacao[t]
        estoque_conhecimento = estoque_conhecimento * (1 - DEPREC) + pd_maturado
        ganho_ptf = (estoque_conhecimento / receita) * p['beta_ptf'] if receita > 0 else 0
        
        retorno_indireto = (receita * ganho_ptf) * ALIQUOTA

        # Engenharia de Créditos e Salvaguardas
        imp_ref = (receita * PRESUNCAO) * ALIQUOTA
        limite_anual_comp = imp_ref * 0.50 
        
        novo_credito = (m_dinamico * pd_total * f) * ALIQUOTA
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
        
        violation_last_year = ren_macro > p['teto_lrf']

        rows.append({
            "Ano": t, 
            "Fator F": f, 
            "Multiplicador": m_dinamico, 
            "Ganho PTF (%)": ganho_ptf * 100, 
            "Renúncia (R$ Bi)": ren_macro, 
            "Retorno (R$ Bi)": ret_macro, 
            "Saldo (R$ Bi)": ret_macro - ren_macro,
            "Adesão": int(firmas)
        })

    return pd.DataFrame(rows)

# ─────────────────────────────────────────────────────────────
# 3. INTERFACE E DASHBOARD
# ─────────────────────────────────────────────────────────────

st.title("🛡️ Simulador RETI - Protocolo SPE/Fazenda")
st.caption("Fomento à Inovação com Responsabilidade Fiscal Paramétrica")

with st.sidebar:
    st.header("⚙️ Configurações de Política")
    n_firmas = st.number_input("Universo Elegível (PMEs)", value=4500)
    t_lrf = st.slider("Teto LRF (R$ Bi/ano)", 0.5, 5.0, 2.2)
    m_base = st.slider("Multiplicador M (Dedução)", 1.0, 1.5, 1.25)
    
    st.header("🔬 Perfil da Firma")
    r_ini = st.number_input("Receita Inicial (R$ MM)", value=15.0)
    i_pd = st.slider("Intensidade P&D", 0.01, 0.25, 0.07)
    cresc = st.slider("Crescimento Anual", 0.0, 0.30, 0.12)
    
    st.header("📈 Premissas Macro (SPE)")
    b_ptf = st.slider("β (Transmissão PTF)", 0.03, 0.12, 0.06)
    p_tec = st.slider("PoTec (%)", 0, 30, 18)

# Execução do Motor
df = run_reti_engine({
    "n_firmas": n_firmas, "mult_base": m_base, "rec_inicial": r_ini,
    "intensidade_pd": i_pd, "crescimento": cresc,
    "elasticidade": -1.27, "beta_ptf": b_ptf, "horizonte": 12,
    "potec": p_tec, "patente_ano": 3, "teto_lrf": t_lrf
})

# Cálculo de KPIs Consolidados
total_ren = df["Renúncia (R$ Bi)"].sum()
total_ret = df["Retorno (R$ Bi)"].sum()
roi = (total_ret / total_ren - 1) * 100 if total_ren > 0 else 0
status_lrf = "CONFORME" if df["Renúncia (R$ Bi)"].max() <= t_lrf else "ALERTA"

# Exibição dos KPIs
c1, c2, c3, c4 = st.columns(4)
c1.metric("Custo Fiscal Total", f"R$ {total_ren:.2f} Bi")
c2.metric("Retorno PIB (PTF)", f"R$ {total_ret:.2f} Bi")
c3.metric("ROI Líquido", f"{roi:.1f}%")
c4.metric("Consistência LRF", status_lrf)

# Espaçamento
st.write("")

# Gráfico de Evolução
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=df["Ano"], y=df["Renúncia (R$ Bi)"], 
    name="Custo (Renúncia)", fill='tozeroy', line_color='#E05252'
))
fig.add_trace(go.Scatter(
    x=df["Ano"], y=df["Retorno (R$ Bi)"], 
    name="Retorno (PIB Dinâmico)", fill='tozeroy', line_color='#3EC97B'
))
fig.add_hline(y=t_lrf, line_dash="dash", line_color="orange", 
              annotation_text="Teto LRF", annotation_position="top right")

fig.update_layout(
    title="Curva de Maturação: Investimento vs. Retorno PTF",
    template="plotly_dark", 
    height=450, 
    margin=dict(l=20, r=20, t=60, b=20),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
st.plotly_chart(fig, use_container_width=True)

# Tabela de Memória de Cálculo
with st.expander("📄 Visualizar Memória de Cálculo Detalhada"):
    st.dataframe(df.style.format(precision=3), use_container_width=True)

st.info("Nota Metodológica: O ROI tende a ser negativo nos primeiros anos devido ao LAG de maturação tecnológica (3 anos) e ao tempo de adesão das firmas. A sustentabilidade é medida pela convergência das curvas no longo prazo.")

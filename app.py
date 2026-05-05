import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────────────────────
# CONFIGURAÇÃO E DESIGN SYSTEM
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Simulador RETI v10.15", layout="wide")

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

def calcular_fator_f(receita, intensidade_pd):
    """
    Implementa a Matriz Bidimensional da Proposta Final.
    O Fator F depende do porte (receita) e da intensidade tecnológica (P&D/Receita).
    """
    # 1. Definição da Base por Porte (Escalonamento conforme TR-SPE)
    if receita <= 3.24:
        f_base = 3.5
    elif receita <= 16.2:
        f_base = 3.0
    elif receita <= 78.0:
        f_base = 2.5
    elif receita <= 200.0:
        # Tapering linear de 0,012 por R$ 1M adicional de receita (Elimina o 'notch')
        f_base = max(1.0, 2.5 - 0.012 * (receita - 78.0))
    else:
        f_base = 1.0

    # 2. Trava de Intensidade de 5% (Módulo Anti-Arbitragem) [2]
    # Empresas com baixa intensidade (ex: SaaS maduro) sofrem redução de 1.0 ponto no fator
    if intensidade_pd < 0.05:
        return max(1.0, f_base - 1.0)
    return f_base

def run_reti_engine(p):
    """
    Motor dinâmico que simula a adicionalidade do P&D e o impacto no PIB potencial.
    """
    # Parâmetros Estruturais da Proposta
    ALÍQUOTA_COMBINADA = 0.34
    PRESUNCAO_LP = 0.32
    LAG_MATURACAO = 3      
    DEPREC_ESTOQUE = 0.15  
    TAXA_SUCESSO = 0.70    

    rows = # Inicialização corrigida
    estoque_conhecimento = 0
    estoque_credito = 0
    historico_pd_adicional = np.zeros(p['horizonte'] + LAG_MATURACAO + 2)

    receita = p['rec_inicial']

    for t in range(1, p['horizonte'] + 1):
        rec_ant = receita
        receita *= (1 + p['crescimento'])
        
        # 1. Cálculo do Fator F Bidimensional
        f = calcular_fator_f(receita, p['intensidade_pd'])
        
        # 2. Efeito Preço: Adicionalidade via Elasticidade (Kannebley et al., 2016) [3]
        pd_original = receita * p['intensidade_pd']
        # User Cost Reduction = superdedução multiplicada pela alíquota
        pd_adicional = pd_original * abs(p['elasticidade']) * (p['mult_base'] * f * ALÍQUOTA_COMBINADA)
        pd_total = pd_original + pd_adicional
        
        if t + LAG_MATURACAO <= p['horizonte'] + 1:
            historico_pd_adicional = pd_adicional * TAXA_SUCESSO

        # 3. Transmissão Macro (Metodologia SPE 2025): P&D -> PTF -> PIB Potencial [1]
        pd_maturado = historico_pd_adicional[t]
        estoque_conhecimento = estoque_conhecimento * (1 - DEPREC_ESTOQUE) + pd_maturado
        ganho_prod = (estoque_conhecimento / receita) * p['beta_ptf'] if receita > 0 else 0
        
        # 4. Retorno Fiscal Indireto (ROI Dinâmico - Efeitos base, indireto e estrutural) [4]
        retorno_indireto = (receita * ganho_prod) * ALÍQUOTA_COMBINADA

        # 5. Engenharia de Créditos e Salvaguardas 
        imp_ref = (receita * PRESUNCAO_LP) * ALÍQUOTA_COMBINADA
        limite_anual_comp = imp_ref * 0.50 # Trava de 50% de compensação
        
        novo_credito = (p['mult_base'] * pd_total * f) * ALÍQUOTA_COMBINADA
        estoque_credito += novo_credito

        # 6. Gatilhos de Performance (Pós-36 meses)
        pode_usar = True
        if t > 3:
            cond_rec = (receita / rec_ant - 1) >= 0.10
            cond_pat = p['patente_ano'] <= t
            cond_potec = p['potec'] >= 15
            pode_usar = cond_rec or cond_pat or cond_potec

        uso_efetivo = min(estoque_credito, limite_anual_comp) if pode_usar else 0
        
        # 7. Salvaguarda: Contribuição Mínima de 25% da base presumida
        imp_final = max(imp_ref * 0.25, imp_ref - uso_efetivo)
        renuncia_firma = imp_ref - imp_final
        estoque_credito -= renuncia_firma

        # 8. Agregação Macro (em R$ Bilhões) via Curva Sigmóide de Adesão
        firmas_aderentes = p['n_firmas'] / (1 + np.exp(-1.2 * (t - 3)))
        renuncia_macro = (renuncia_firma * firmas_aderentes) / 1000
        retorno_macro = (retorno_indireto * firmas_aderentes) / 1000

        rows.append({
            "Ano": t,
            "Fator F": f,
            "P&D Total (MM)": pd_total,
            "Ganho PTF (%)": ganho_prod * 100,
            "Renúncia (R$ Bi)": renuncia_macro,
            "Retorno (R$ Bi)": retorno_macro,
            "Saldo (R$ Bi)": retorno_macro - renuncia_macro,
            "Status": "Ativo" if pode_usar else "Suspenso"
        })

    return pd.DataFrame(rows)

# ─────────────────────────────────────────────────────────────
# INTERFACE STREAMLIT
# ─────────────────────────────────────────────────────────────

st.title("🛡️ Simulador RETI - Protocolo Final SPE/RFB")
st.subheader("Fomento à Inovação com Responsabilidade Fiscal - v10.15")

with st.sidebar:
    st.header("⚙️ Configurações de Política")
    n_firmas = st.number_input("Universo Alvo (PMEs Inovadoras)", value=4500)
    teto_lrf = st.slider("Teto Fiscal LRF (R$ Bi/ano)", 0.5, 5.0, 2.2)
    mult_base = st.slider("Multiplicador M (Dedução)", 1.0, 1.5, 1.25)
    
    st.header("🔬 Perfil Micro (Firma)")
    rec_inicial = st.number_input("Receita Inicial (R$ MM)", value=15.0)
    intensidade_pd = st.slider("Intensidade P&D (% Receita)", 0.01, 0.20, 0.07, format="%.2f")
    crescimento = st.slider("Crescimento Anual", 0.0, 0.30, 0.12)
    
    st.header("📈 Modelo PTF (SPE 2025)")
    elasticidade = st.slider("Elasticidade-Custo (Kannebley)", -2.0, -0.5, -1.27)
    beta_ptf = st.slider("β (Transmissão P&D → PTF)", 0.03, 0.12, 0.06)
    
    st.header("🚩 Performance")
    potec = st.slider("Pessoal Técnico (%)", 0, 30, 18)
    patente_ano = st.slider("Ano Depósito Patente", 1, 10, 3)

# Processamento
params = {
    "n_firmas": n_firmas, "mult_base": mult_base, "rec_inicial": rec_inicial,
    "intensidade_pd": intensidade_pd, "crescimento": crescimento,
    "elasticidade": elasticidade, "beta_ptf": beta_ptf, "horizonte": 10,
    "potec": potec, "patente_ano": patente_ano
}

df = run_reti_engine(params)

# KPIs Consolidados
c1, c2, c3, c4 = st.columns(4)
total_ren = df.sum()
total_ret = df.sum()
roi_liq = (total_ret / total_ren - 1) * 100 if total_ren > 0 else 0

c1.metric("Custo Fiscal Total", f"R$ {total_ren:.2f} Bi", help="Acumulado em 10 anos")
c2.metric("Retorno Indireto (PIB)", f"R$ {total_ret:.2f} Bi", help="Via ganhos de PTF")
c3.metric("ROI Líquido", f"{roi_liq:.1f}%")
c4.metric("Status LRF", "CONFORME" if df.max() <= teto_lrf else "ALERTA")

# Gráficos
st.markdown("### Fluxo de Caixa Dinâmico: Investimento Público em Inovação")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["Ano"], y=df, name="Custo (Renúncia)", fill='tozeroy', line_color='#E05252'))
fig.add_trace(go.Scatter(x=df["Ano"], y=df, name="Retorno (PIB Dinâmico)", fill='tozeroy', line_color='#3EC97B'))
fig.add_hline(y=teto_lrf, line_dash="dash", line_color="orange", annotation_text="Teto LRF")
fig.update_layout(template="plotly_dark", hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)

# Tabela Analítica
if st.checkbox("Visualizar Memória de Cálculo Anual"):
    st.dataframe(df.style.format({
        "Renúncia (R$ Bi)": "{:.3f}",
        "Retorno (R$ Bi)": "{:.3f}",
        "Saldo (R$ Bi)": "{:.3f}",
        "Ganho PTF (%)": "{:.2f}%",
        "Fator F": "{:.2f}",
        "P&D Total (MM)": "{:.1f}"
    }))

st.info(f"""
**Notas Metodológicas (Conforme Proposta V17):**
1. **Neutralidade:** Custo de R$ 1,8 bi compensado por receitas de *bets* e reforma administrativa.
2. **Adicionalidade:** Estimada via elasticidade de {elasticidade} (estudo Kannebley/De Negri). [3]
3. **Ajuste Hierárquico:** Em caso de estouro do teto, a redução ocorre primeiro no Multiplicador (1.25).
""")

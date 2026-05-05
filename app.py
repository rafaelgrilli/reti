import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────────────────────
# CONFIGURAÇÃO E DESIGN SYSTEM
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Simulador RETI v10.10", layout="wide")

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
# MOTOR DE CÁLCULO TÉCNICO (SPE/MF & RFB Compliant)
# ─────────────────────────────────────────────────────────────

def calcular_fator_f(receita, intensidade_pd):
    """
    Implementa a Matriz Bidimensional da Proposta V17.
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
        # Tapering linear de 0,012 por R$ 1M excedente a 78M (Neutraliza o 'notch')
        f_base = max(1.0, 2.5 - 0.012 * (receita - 78.0))
    else:
        f_base = 1.0

    # 2. Trava de Intensidade de 5% (Módulo Anti-Arbitragem)
    # Empresas com baixa intensidade tecnológica têm o incentivo reduzido
    if intensidade_pd < 0.05:
        return max(1.0, f_base - 1.0)
    return f_base

def run_reti_engine(p):
    """
    Motor dinâmico que simula a adicionalidade do P&D e o impacto no PIB potencial.
    """
    # Parâmetros Estruturais
    ALÍQUOTA_COMBINADA = 0.34
    PRESUNCAO_LP = 0.32
    LAG_MATURACAO = 3      # Anos para o P&D virar produtividade
    DEPREC_ESTOQUE = 0.15  # Obsolescência tecnológica anual
    TAXA_SUCESSO = 0.70    # 70% dos projetos geram resultado técnico

    rows =
    estoque_conhecimento = 0
    estoque_credito = 0
    historico_pd_adicional = np.zeros(p['horizonte'] + LAG_MATURACAO + 2)

    receita = p['rec_inicial']

    for t in range(1, p['horizonte'] + 1):
        rec_ant = receita
        receita *= (1 + p['crescimento'])
        
        # 1. Cálculo do Fator F Bidimensional
        f = calcular_fator_f(receita, p['intensidade_pd'])
        
        # 2. Efeito Preço: Adicionalidade via Elasticidade (Kannebley et al., 2016)
        # Calcula quanto a redução do 'user cost' induz de investimento privado extra
        pd_original = receita * p['intensidade_pd']
        beneficio_por_real = p['mult_base'] * f * ALÍQUOTA_COMBINADA
        pd_adicional = pd_original * abs(p['elasticidade']) * beneficio_por_real
        pd_total = pd_original + pd_adicional
        
        # Registra investimento para maturação futura (Lag)
        if t + LAG_MATURACAO <= p['horizonte'] + 1:
            historico_pd_adicional = pd_adicional * TAXA_SUCESSO

        # 3. Transmissão Macro (Metodologia SPE 2025): P&D -> PTF -> PIB
        pd_maturado = historico_pd_adicional[t]
        estoque_conhecimento = estoque_conhecimento * (1 - DEPREC_ESTOQUE) + pd_maturado
        # Delta PTF = beta * (Estoque P&D / Receita)
        ganho_prod = (estoque_conhecimento / receita) * p['beta_ptf'] if receita > 0 else 0
        
        # 4. Retorno Fiscal Indireto (ROI Dinâmico)
        retorno_indireto = (receita * ganho_prod) * ALÍQUOTA_COMBINADA

        # 5. Engenharia de Créditos e Salvaguardas
        imp_ref = (receita * PRESUNCAO_LP) * ALÍQUOTA_COMBINADA
        limite_anual_comp = imp_ref * 0.50 # Trava de 50% de uso de créditos
        
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
        
        # 7. Salvaguarda de Arrecadação: Contribuição Mínima de 25% da base
        imp_final = max(imp_ref * 0.25, imp_ref - uso_efetivo)
        renuncia_firma = imp_ref - imp_final
        estoque_credito -= renuncia_firma

        # 8. Agregação para o Universo de Firmas (em R$ Bilhões)
        # Adesão segue curva sigmoide (S-Curve) baseada no histórico da Lei do Bem
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
            "Adesão": int(firmas_aderentes)
        })

    return pd.DataFrame(rows)

# ─────────────────────────────────────────────────────────────
# INTERFACE STREAMLIT
# ─────────────────────────────────────────────────────────────

st.title("🛡️ Simulador Econômico-Fiscal RETI")
st.subheader("Fomento à Inovação com Responsabilidade Fiscal - Protocolo SPE/ Fazenda")

with st.sidebar:
    st.header("⚙️ Parâmetros de Política")
    n_firmas = st.number_input("Universo Alvo (PMEs Inovadoras)", value=4500, help="Proxy baseada na Dirbi 2024")
    teto_lrf = st.slider("Teto Fiscal LRF (R$ Bi/ano)", 0.5, 5.0, 2.2)
    mult_base = st.slider("Multiplicador M (Dedução)", 1.0, 1.5, 1.25, help="1,25 é o benchmark OCDE")
    
    st.header("🔬 Perfil da Firma (Micro)")
    rec_inicial = st.number_input("Receita Inicial (R$ MM)", value=15.0)
    intensidade_pd = st.slider("Intensidade P&D (% Receita)", 0.01, 0.20, 0.07, format="%.2f")
    crescimento = st.slider("Crescimento Real Anual", 0.0, 0.30, 0.12)
    
    st.header("📈 Premissas Macro (SPE/IPEA)")
    elasticidade = st.slider("Elasticidade-Custo (Kannebley)", -2.0, -0.5, -1.27)
    beta_ptf = st.slider("β (Transmissão PTF)", 0.03, 0.12, 0.06, help="Impacto do P&D na produtividade")
    
    st.header("🚩 Gatilhos de Performance")
    potec = st.slider("Pessoal Técnico (%)", 0, 30, 18, help="Ponto de corte PINTEC: 15%")
    patente_ano = st.slider("Ano Médio Depósito Patente", 1, 10, 3)

# Execução do Modelo
params = {
    "n_firmas": n_firmas, "mult_base": mult_base, "rec_inicial": rec_inicial,
    "intensidade_pd": intensidade_pd, "crescimento": crescimento,
    "elasticidade": elasticidade, "beta_ptf": beta_ptf, "horizonte": 10,
    "potec": potec, "patente_ano": patente_ano
}

df = run_reti_engine(params)

# Cálculo de KPIs Consolidados
total_ren = df.sum()
total_ret = df.sum()
roi_liq = (total_ret / total_ren - 1) * 100 if total_ren > 0 else 0
# Identifica o Payback (ano em que o retorno acumulado >= renúncia acumulada)
df_cum = df.cumsum()
payback_idx = np.where(df_cum >= df_cum)
payback_year = df.iloc[payback_idx]["Ano"] if len(payback_idx) > 0 else "N/A"

# Dashboard de KPIs
k1, k2, k3, k4 = st.columns(4)
k1.metric("Custo Fiscal (10 anos)", f"R$ {total_ren:.2f} Bi", delta_color="inverse")
k2.metric("Retorno Indireto (PTF)", f"R$ {total_ret:.2f} Bi")
k3.metric("ROI Líquido", f"{roi_liq:.1f}%")
k4.metric("Payback do Tesouro", f"Ano {payback_year}")

# Gráfico Principal
st.markdown("### Dinâmica Fiscal: Curva de Renúncia vs. Retorno via Produtividade")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["Ano"], y=df, name="Custo (Renúncia)", fill='tozeroy', line_color='#E05252'))
fig.add_trace(go.Scatter(x=df["Ano"], y=df, name="Retorno (PIB Dinâmico)", fill='tozeroy', line_color='#3EC97B'))
fig.add_hline(y=teto_lrf, line_dash="dash", line_color="orange", annotation_text="Teto LRF")
fig.update_layout(template="plotly_dark", height=450, margin=dict(l=20, r=20, t=40, b=20))
st.plotly_chart(fig, use_container_width=True)

# Alerta LRF
if df.max() > teto_lrf:
    st.warning(f"⚠️ Alerta: O teto LRF de R$ {teto_lrf} Bi foi ultrapassado. Acione a regra de ajuste automático (reduzir multiplicador ou fator F).")
else:
    st.success("✅ Cenário fiscalmente sustentável: Renúncia anual dentro do limite configurado.")

# Tabela Analítica
if st.checkbox("Exibir Memória de Cálculo Anual"):
    st.write(df.style.format({
        "Renúncia (R$ Bi)": "{:.3f}",
        "Retorno (R$ Bi)": "{:.3f}",
        "Saldo (R$ Bi)": "{:.3f}",
        "Ganho PTF (%)": "{:.2f}%",
        "Fator F": "{:.2f}",
        "P&D Total (MM)": "{:.1f}"
    }))

st.info(f"""
**Notas Metodológicas (Conforme Proposta V17):**
1. **P&D Adicional:** Calculado com elasticidade de {elasticidade} sobre o custo tributário marginal (crowding-in). [1]
2. **Efeito Notch:** Phasing-out linear de 0,012 garante busca por escala acima de R$ 78M. 
3. **Gatilhos:** Suspensão de créditos após 36 meses se PoTec < 15% ou receita estagnada. [3]
4. **ROI:** Baseado na função de produção SPE/2025, onde o P&D expande a oferta agregada via PTF. 
""")

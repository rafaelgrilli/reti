import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- CONSTANTES GLOBAIS (Para evitar NameError) ---
LAG_MATURACAO = 3
TAXA_DEPRECIACAO = 0.15
PROBABILIDADE_SUCESSO = 0.70 # Nem todo P&D gera ganho de produtividade

# --- CONFIGURAÇÃO DE INTERFACE ---
st.set_page_config(page_title="RETI - Decision Support System v5.0", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono&family=IBM+Plex+Sans:wght@300;400;600&display=swap');
    html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
    .stMetric { background: #f1f3f6; border-left: 5px solid #185FA5; padding: 15px; border-radius: 4px; }
    </style>
    """, unsafe_allow_html=True)

# --- MOTOR DE CÁLCULO ---

def calcular_fator_f(receita_mm):
    if receita_mm <= 3.24: return 3.5
    if receita_mm <= 78: return 2.5
    if receita_mm <= 200:
        return max(1.0, 2.5 - 0.01229 * (receita_mm - 78))
    return 1.0

def motor_reti_v5(p):
    anos_total = p['anos']
    rec = p['rec_inicial']
    estoque_conhecimento = 0
    estoque_credito_fiscal = 0
    
    historico_pd_adic = [0] * (anos_total + LAG_MATURACAO + 1)
    resultados = []

    for t in range(1, anos_total + 1):
        # 1. Dinâmica de Receita
        rec_ant = rec
        rec = rec * (1 + p['crescimento'])
        f = calcular_fator_f(rec)
        
        # 2. P&D e Adicionalidade
        pd_original = rec * p['intensidade_pd']
        pd_adicional = pd_original * abs(p['elasticidade']) * (p['mult_base'] * f * 0.34)
        pd_total = pd_original + pd_adicional
        
        # Armazena P&D adicional com fator de risco (Sucesso tecnológico)
        if t + LAG_MATURACAO <= anos_total:
            historico_pd_adic[t + LAG_MATURACAO] = pd_adicional * PROBABILIDADE_SUCESSO
            
        # 3. Acúmulo de Produtividade (Modelo de Estoque)
        pd_maturado = historico_pd_adic[t]
        estoque_conhecimento = (estoque_conhecimento * (1 - TAXA_DEPRECIACAO)) + pd_maturado
        
        # Ganho de produtividade conservador (Elasticidade 0.05)
        ganho_prod = (estoque_conhecimento / rec) * 0.05 if rec > 0 else 0
        
        # 4. Retorno Fiscal Indireto (Baseado no incremento de margem tributável)
        # Suposição: Produtividade reduz custos operacionais, aumentando o lucro tributável
        lucro_incremental = rec * ganho_prod
        retorno_indireto = lucro_incremental * 0.34 
        
        # 5. Cálculo da Renúncia RETI
        imp_ref = (rec * 0.32) * 0.34
        limite_comp = imp_ref * 0.50
        
        novo_credito = (p['mult_base'] * pd_total * f) * 0.34
        estoque_credito_fiscal += novo_credito
        
        # Gatilho de Performance
        pode_usar = True
        if t > 3:
            pode_usar = ((rec/rec_ant - 1) >= 0.10) or (p['patente_ano'] <= t) or (p['potec'] > 15)
            
        uso_credito = min(estoque_credito_fiscal, limite_comp) if pode_usar else 0
        imp_final = max(imp_ref * 0.25, imp_ref - uso_credito)
        renuncia = imp_ref - imp_final
        estoque_credito_fiscal -= renuncia
        
        resultados.append({
            'Ano': t, 'Receita': rec, 'Renuncia': renuncia,
            'Retorno_Indireto': retorno_indireto, 'Ganho_Prod_Pct': ganho_prod * 100,
            'PD_Total': pd_total, 'Fator_F': f, 'Status': 'Ativo' if pode_usar else 'Suspenso'
        })
        
    return pd.DataFrame(resultados)

# --- INTERFACE ---

st.title("🏛️ RETI: Simulador de Impacto Fiscal e Produtividade")
st.caption("Versão 5.0 - Modelo de Difusão Tecnológica e Risco de P&D")

with st.sidebar:
    st.header("Parâmetros de Política")
    n_firmas_max = st.number_input("Universo Total de Firmas", value=4500)
    teto_lrf = st.slider("Teto LRF (R$ Bi)", 1.0, 5.0, 2.2)
    mult = st.slider("Multiplicador M", 1.0, 1.5, 1.25)
    elast = st.slider("Elasticidade (ε)", -2.0, -0.5, -1.27)
    
    st.divider()
    st.header("Perfil da Firma")
    rec_ini = st.number_input("Receita Inicial (R$ MM)", value=15.0)
    int_pd = st.slider("Intensidade P&D (%)", 1.0, 20.0, 7.0) / 100
    cresc = st.slider("Crescimento Anual (%)", 0.0, 25.0, 12.0) / 100
    horizonte = st.slider("Horizonte (Anos)", 5, 15, 10)

# --- CÁLCULO MACRO COM CURVA DE ADESÃO ---
params = {
    'anos': horizonte, 'rec_inicial': rec_ini, 'crescimento': cresc,
    'intensidade_pd': int_pd, 'elasticidade': elast, 'mult_base': mult,
    'patente_ano': 3, 'potec': 18
}

df = motor_reti_v5(params)

# Curva de Difusão (Adoção gradual do regime pelas 4500 empresas)
def curva_adesao(t, total):
    # Função Sigmoide: adesão lenta no início, rápida no meio, estabiliza no fim
    return total / (1 + np.exp(-1.2 * (t - 3)))

df['Firmas_Aderentes'] = [curva_adesao(t, n_firmas_max) for t in df['Ano']]
df['Renuncia_Macro'] = (df['Renuncia'] * df['Firmas_Aderentes']) / 1000
df['Retorno_Macro'] = (df['Retorno_Indireto'] * df['Firmas_Aderentes']) / 1000

# --- DASHBOARD ---

k1, k2, k3, k4 = st.columns(4)
ren_total_acum = df['Renuncia_Macro'].sum()
ret_total_acum = df['Retorno_Macro'].sum()
gap_fiscal = ren_total_acum - ret_total_acum

k1.metric("Custo Fiscal Acumulado", f"R$ {ren_total_acum:.2f} Bi")
k2.metric("Retorno Indireto Acumulado", f"R$ {ret_total_acum:.2f} Bi")
k3.metric("Gap Fiscal Líquido", f"R$ {gap_fiscal:.2f} Bi", delta_color="inverse")
k4.metric("Status LRF (Ano Final)", "✅ OK" if df['Renuncia_Macro'].iloc[-1] <= teto_lrf else "⚠️ RISCO")

t1, t2 = st.tabs(["📊 Sustentabilidade Fiscal", "⚙️ Premissas Técnicas"])

with t1:
    st.subheader("Análise de Fluxo de Caixa do Tesouro (R$ Bilhões)")
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['Ano'], y=df['Renuncia_Macro'], name="Renúncia (Saída)", fill='tozeroy', line=dict(color='red')))
    fig.add_trace(go.Scatter(x=df['Ano'], y=df['Retorno_Macro'], name="Retorno Indireto (Entrada)", fill='tonexty', line=dict(color='green')))
    
    fig.update_layout(title="O 'Vale da Morte' da Inovação: Quando a Arrecadação Empata com o Incentivo",
                      xaxis_title="Anos", yaxis_title="R$ Bilhões", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)
    
    st.info(f"""
    **Por que este gráfico é realista?**
    1. **Maturação:** Nos primeiros {LAG_MATURACAO} anos, o retorno é quase zero porque o P&D ainda não virou produto/eficiência.
    2. **Adesão Gradual:** O custo fiscal sobe conforme mais empresas descobrem o regime (Curva de Difusão).
    3. **Risco:** Apenas {PROBABILIDADE_SUCESSO*100}% do investimento em P&D é convertido em ganho real de produtividade.
    """)

with t2:
    st.markdown(f"""
    ### Metodologia de Cálculo (Padrão SPE/MF)
    - **Time-Lag:** {LAG_MATURACAO} anos entre investimento e impacto na PTF.
    - **Depreciação:** {TAXA_DEPRECIACAO*100}% ao ano (Obsolescência tecnológica).
    - **Taxa de Sucesso:** {PROBABILIDADE_SUCESSO*100}% (Ajuste para projetos de P&D fracassados).
    - **Retorno Fiscal:** Calculado sobre o incremento de margem operacional (34% de alíquota combinada).
    - **Adesão:** Modelo Sigmoide baseado no histórico de adoção da Lei do Bem.
    """)

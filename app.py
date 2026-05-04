import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# ─────────────────────────────────────────────
# CONFIGURAÇÃO DA PÁGINA (Mantida original)
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="RETI — Simulador de Impacto Ex-Ante",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────
# ESTILO VISUAL (Mantido original)
# ─────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
    .main { background-color: #0d1117; }
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    h1, h2, h3 { font-family: 'IBM Plex Sans', sans-serif; font-weight: 700; }
    .metric-card {
        background: #161b22; border: 1px solid #30363d; border-radius: 10px;
        padding: 1.2rem 1.5rem; margin-bottom: 0.8rem;
    }
    .metric-card .label { font-size: 0.72rem; color: #8b949e; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.3rem; }
    .metric-card .value { font-family: 'IBM Plex Mono', monospace; font-size: 1.6rem; font-weight: 600; color: #f0f6fc; }
    .metric-card .delta { font-size: 0.78rem; margin-top: 0.2rem; }
    .delta-pos { color: #3fb950; }
    .delta-neg { color: #f85149; }
    .delta-neu { color: #d29922; }
    .section-header { font-size: 0.68rem; font-weight: 600; color: #58a6ff; text-transform: uppercase; letter-spacing: 0.12em; border-bottom: 1px solid #21262d; padding-bottom: 0.4rem; margin-bottom: 1rem; margin-top: 1.5rem; }
    .formula-box { background: #161b22; border-left: 3px solid #1f6feb; border-radius: 0 8px 8px 0; padding: 0.8rem 1.2rem; font-family: 'IBM Plex Mono', monospace; font-size: 0.82rem; color: #79c0ff; margin: 0.5rem 0 1rem 0; }
    .alert-box { background: #1c2128; border: 1px solid #d29922; border-radius: 8px; padding: 0.7rem 1rem; font-size: 0.78rem; color: #e3b341; margin-top: 0.5rem; }
    .tab-content { padding-top: 1rem; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# LÓGICA DO MODELO RETI (REVISÃO CIRÚRGICA)
# ─────────────────────────────────────────────

def calcular_fator_f(receita_milhoes: float, intensidade_pnd: float) -> float:
    """Retorna o Fator F conforme Matriz RETI com tapering."""
    if intensidade_pnd >= 0.05:
        if receita_milhoes <= 3.24: f = 3.5
        elif receita_milhoes <= 16.2: f = 3.0
        elif receita_milhoes <= 78.0: f = 2.5
        elif receita_milhoes <= 200.0: f = max(1.0, 2.5 - 0.012 * (receita_milhoes - 78.0))
        else: f = 1.0
    else:
        if receita_milhoes <= 3.24: f = 2.5
        elif receita_milhoes <= 16.2: f = 2.0
        elif receita_milhoes <= 78.0: f = 1.5
        elif receita_milhoes <= 200.0: f = max(1.0, 1.5 - 0.004 * (receita_milhoes - 78.0))
        else: f = 1.0
    return f

def calcular_imposto_com_salvaguarda(base_reti, receita, sem_reti=False):
    """Calcula imposto aplicando a trava de piso tributário (25% do imposto devido no lucro presumido)."""
    aliquota_cheia = 0.34
    imposto_referencia = (receita * 0.32) * aliquota_cheia
    if sem_reti:
        return imposto_referencia
    imposto_reti_bruto = base_reti * aliquota_cheia
    piso_fiscal = imposto_referencia * 0.25
    return max(imposto_reti_bruto, piso_fiscal)

def simular_firma(receita_inicial_mm, intensidade_pnd, taxa_crescimento_receita, elasticidade_pnd, multiplicador, anos=10, sem_reti=False):
    rows = []
    receita = receita_inicial_mm * 1_000_000
    pnd_adicional_acumulado = 0

    for ano in range(1, anos + 1):
        # ENDOGENEIDADE: P&D prévio induz ganho de produtividade (+0.5% de crescimento por cada R$ 10M de P&D incremental)
        crescimento_endogeno = min(0.10, (pnd_adicional_acumulado / 10_000_000) * 0.005)
        taxa_real = taxa_crescimento_receita + (0 if sem_reti else crescimento_endogeno)
        
        receita_ano = receita * ((1 + taxa_real) ** (ano - 1))
        receita_mm = receita_ano / 1_000_000
        pnd_base = receita_ano * intensidade_pnd

        if sem_reti:
            imposto_total = calcular_imposto_com_salvaguarda(0, receita_ano, sem_reti=True)
            pnd_efetivo = pnd_base
            incentivo_fiscal = 0
            fator_f = 0
            retorno_folha = 0
        else:
            fator_f = calcular_fator_f(receita_mm, intensidade_pnd)
            reducao_custo_pnd = (multiplicador * fator_f * 0.34)
            delta_pnd = pnd_base * abs(elasticidade_pnd) * reducao_custo_pnd
            pnd_efetivo = pnd_base + delta_pnd
            pnd_adicional_acumulado += delta_pnd

            base_reti = max(0, (receita_ano * 0.32) - (multiplicador * pnd_efetivo * fator_f))
            imposto_com = calcular_imposto_com_salvaguarda(base_reti, receita_ano)
            imposto_sem = calcular_imposto_com_salvaguarda(0, receita_ano, sem_reti=True)
            
            incentivo_fiscal = imposto_sem - imposto_com
            imposto_total = imposto_com
            retorno_folha = delta_pnd * 0.65 * 0.28 # Back-flow PoTec

        rows.append({
            "Ano": ano,
            "Receita (R$ MM)": receita_mm,
            "P&D Efetivo (R$ MM)": pnd_efetivo / 1_000_000,
            "Intensidade P&D (%)": (pnd_efetivo / receita_ano) * 100,
            "Fator F": fator_f,
            "Imposto Total (R$ MM)": imposto_total / 1_000_000,
            "Incentivo Fiscal (R$ MM)": incentivo_fiscal / 1_000_000,
            "Retorno Folha (R$ MM)": retorno_folha / 1_000_000
        })
    return pd.DataFrame(rows)

def simular_impacto_fiscal_macro(n_empresas, receita_media_mm, intensidade_pnd_media, taxa_crescimento_universo, elasticidade_pnd, multiplicador, anos=10):
    rows = []
    for ano in range(1, anos + 1):
        n_ativas = int(n_empresas * ((1 + 0.05) ** (ano - 1)))
        receita_mm = receita_media_mm * ((1 + taxa_crescimento_universo) ** (ano - 1))
        fator_f = calcular_fator_f(receita_mm, intensidade_pnd_media)
        pnd_base = receita_mm * 1e6 * intensidade_pnd_media
        delta_pnd = pnd_base * abs(elasticidade_pnd) * (multiplicador * fator_f * 0.34)
        pnd_efetivo = pnd_base + delta_pnd

        base_reti = max(0, (receita_mm * 1e6 * 0.32) - (multiplicador * pnd_efetivo * fator_f))
        imposto_com = calcular_imposto_com_salvaguarda(base_reti, receita_mm * 1e6)
        imposto_sem = calcular_imposto_com_salvaguarda(0, receita_mm * 1e6, sem_reti=True)

        renuncia_total = ((imposto_sem - imposto_com) / 1e9) * n_ativas
        pnd_inc_total = (delta_pnd / 1e9) * n_ativas
        retorno_indireto = pnd_inc_total * 0.65 * 0.28 

        rows.append({
            "Ano": ano,
            "Empresas Ativas": n_ativas,
            "Renúncia Fiscal (R$ Bi)": renuncia_total,
            "P&D Incremental (R$ Bi)": pnd_inc_total,
            "Retorno Tributário Indireto (R$ Bi)": retorno_indireto,
            "Renúncia Líquida (R$ Bi)": renuncia_total - retorno_indireto,
        })
    df = pd.DataFrame(rows)
    df["Renúncia Acumulada (R$ Bi)"] = df["Renúncia Fiscal (R$ Bi)"].cumsum()
    df["Renúncia Líquida Acumulada (R$ Bi)"] = df["Renúncia Líquida (R$ Bi)"].cumsum()
    return df

# ─────────────────────────────────────────────
# SIDEBAR — PARÂMETROS
# ─────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🔬 RETI Simulator v2.0")
    st.markdown('<div class="sidebar-title">📊 Perfil da Firma</div>', unsafe_allow_html=True)
    receita_inicial = st.slider("Receita Inicial (R$ MM)", 0.5, 300.0, 15.0)
    intensidade_pnd = st.slider("Intensidade P&D (%)", 1.0, 30.0, 8.0) / 100.0
    taxa_crescimento_firma = st.slider("Crescimento Anual Base (%)", 0.0, 40.0, 15.0) / 100.0

    st.markdown('<div class="sidebar-title">🏗️ Parâmetros Macro</div>', unsafe_allow_html=True)
    n_empresas = st.number_input("Firmas Elegíveis", 500, 20000, 4500)
    rec_med_univ = st.slider("Receita Média Univ. (R$ MM)", 1.0, 100.0, 12.0)
    int_med_univ = st.slider("Intensidade Média Univ. (%)", 3.0, 20.0, 7.0) / 100.0
    taxa_crescimento_universo = st.slider("Crescimento Universo (%)", 0.0, 30.0, 12.0) / 100.0

    st.markdown('<div class="sidebar-title">⚙️ Calibragem Técnica</div>', unsafe_allow_html=True)
    elasticidade = st.slider("Elasticidade-Custo", -2.0, -0.5, -1.27)
    multiplicador = st.slider("Multiplicador RETI", 1.0, 1.6, 1.25)
    anos = st.slider("Horizonte (anos)", 5, 15, 10)

# ─────────────────────────────────────────────
# PROCESSAMENTO E DASHBOARD
# ─────────────────────────────────────────────

df_firma_com = simular_firma(receita_inicial, intensidade_pnd, taxa_crescimento_firma, elasticidade, multiplicador, anos)
df_firma_sem = simular_firma(receita_inicial, intensidade_pnd, taxa_crescimento_firma, elasticidade, multiplicador, anos, sem_reti=True)
df_macro = simular_impacto_fiscal_macro(n_empresas, rec_med_univ, int_med_univ, taxa_crescimento_universo, elasticidade, multiplicador, anos)

pnd_adicional = df_firma_com["P&D Efetivo (R$ MM)"].sum() - df_firma_sem["P&D Efetivo (R$ MM)"].sum()
incentivo_total = df_firma_com["Incentivo Fiscal (R$ MM)"].sum()
roi_fiscal_firma = pnd_adicional / incentivo_total if incentivo_total > 0 else 0
renuncia_acum = df_macro["Renúncia Acumulada (R$ Bi)"].iloc[-1]
pnd_macro_total = df_macro["P&D Incremental (R$ Bi)"].sum()
retorno_ind_total = df_macro["Retorno Tributário Indireto (R$ Bi)"].sum()

st.markdown("""
<div style="border-bottom: 1px solid #21262d; padding-bottom: 1rem; margin-bottom: 1.5rem;">
    <div style="font-size:0.68rem; color:#1f6feb; text-transform:uppercase; letter-spacing:0.12em; font-weight:600; margin-bottom:0.3rem;">SPE/MF · Versão Final Simulador</div>
    <h1 style="color:#f0f6fc; margin:0; font-size:1.8rem;">RETI — Impacto Fiscal e Inovação</h1>
</div>
""", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["📈 Nível da Firma", "🏛️ Impacto Fiscal Agregado", "🔭 Fator F & Sensibilidade"])

with tab1:
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.markdown(f'<div class="metric-card"><div class="label">Fator F (Ano 1)</div><div class="value">{calcular_fator_f(receita_inicial, intensidade_pnd):.2f}</div></div>', unsafe_allow_html=True)
    with col2: st.markdown(f'<div class="metric-card"><div class="label">P&D Adicional Acum.</div><div class="value">R$ {pnd_adicional:.1f}M</div></div>', unsafe_allow_html=True)
    with col3: st.markdown(f'<div class="metric-card"><div class="label">Incentivo Total</div><div class="value">R$ {incentivo_total:.1f}M</div></div>', unsafe_allow_html=True)
    with col4: st.markdown(f'<div class="metric-card"><div class="label">ROI Fiscal (P&D/Ren)</div><div class="value">{roi_fiscal_firma:.2f}x</div></div>', unsafe_allow_html=True)

    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=df_firma_com["Ano"], y=df_firma_com["P&D Efetivo (R$ MM)"], name="Com RETI", line=dict(color="#1f6feb", width=2.5), fill="tozeroy", fillcolor="rgba(31,111,235,0.08)"))
    fig1.add_trace(go.Scatter(x=df_firma_sem["Ano"], y=df_firma_sem["P&D Efetivo (R$ MM)"], name="Sem RETI", line=dict(color="#8b949e", width=1.8, dash="dash")))
    fig1.update_layout(title="Investimento em P&D — Firma Individual", xaxis_title="Ano", yaxis_title="R$ MM", plot_bgcolor="#0d1117", paper_bgcolor="#0d1117", font=dict(color="#c9d1d9"), height=340)
    st.plotly_chart(fig1, use_container_width=True)

    st.markdown('<div class="section-header">Trajetória Anual da Firma</div>', unsafe_allow_html=True)
    st.dataframe(df_firma_com.set_index("Ano").style.format("{:.2f}"), use_container_width=True)

with tab2:
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.markdown(f'<div class="metric-card"><div class="label">Renúncia Acumulada</div><div class="value">R$ {renuncia_acum:.2f}Bi</div></div>', unsafe_allow_html=True)
    with col2: st.markdown(f'<div class="metric-card"><div class="label">P&D Incremental</div><div class="value">R$ {pnd_macro_total:.2f}Bi</div></div>', unsafe_allow_html=True)
    with col3: st.markdown(f'<div class="metric-card"><div class="label">Retorno Folha PoTec</div><div class="value">R$ {retorno_ind_total:.2f}Bi</div></div>', unsafe_allow_html=True)
    with col4: st.markdown(f'<div class="metric-card"><div class="label">Renúncia Líquida</div><div class="value">R$ {df_macro["Renúncia Líquida Acumulada (R$ Bi)"].iloc[-1]:.2f}Bi</div></div>', unsafe_allow_html=True)

    fig_macro = go.Figure()
    fig_macro.add_trace(go.Bar(x=df_macro["Ano"], y=df_macro["P&D Incremental (R$ Bi)"], name="P&D Incremental", marker_color="rgba(31,111,235,0.6)"))
    fig_macro.add_trace(go.Scatter(x=df_macro["Ano"], y=df_macro["Renúncia Fiscal (R$ Bi)"], name="Renúncia Bruta", line=dict(color="#f85149", width=2.5)))
    fig_macro.add_trace(go.Scatter(x=df_macro["Ano"], y=df_macro["Retorno Tributário Indireto (R$ Bi)"], name="Retorno Folha", line=dict(color="#3fb950", width=2)))
    fig_macro.update_layout(title="Impacto Fiscal Anual Agregado", barmode="group", plot_bgcolor="#0d1117", paper_bgcolor="#0d1117", font=dict(color="#c9d1d9"), height=400)
    st.plotly_chart(fig_macro, use_container_width=True)

with tab3:
    st.markdown('<div class="section-header">Heatmap de Sensibilidade — P&D Adicional (Ano 1)</div>', unsafe_allow_html=True)
    rec_h = [1.0, 10.0, 50.0, 100.0, 200.0]
    int_h = [0.03, 0.07, 0.12, 0.20]
    z = []
    for ih in int_h:
        row = []
        for rh in rec_h:
            f = calcular_fator_f(rh, ih)
            delta = (rh * 1e6 * ih) * abs(elasticidade) * (multiplicador * f * 0.34) / 1e6
            row.append(delta)
        z.append(row)
    
    fig_h = go.Figure(data=go.Heatmap(z=z, x=[f"R${r}M" for r in rec_h], y=[f"{int(i*100)}%" for i in int_h], colorscale="Viridis"))
    fig_h.update_layout(height=400, plot_bgcolor="#0d1117", paper_bgcolor="#0d1117", font=dict(color="#c9d1d9"))
    st.plotly_chart(fig_h, use_container_width=True)

    st.markdown('<div class="section-header">Sensibilidade da Renúncia Fiscal à Elasticidade</div>', unsafe_allow_html=True)
    e_vals = np.linspace(-2.0, -0.5, 20)
    r_vals = [simular_impacto_fiscal_macro(n_empresas, rec_med_univ, int_med_univ, taxa_crescimento_universo, e, multiplicador, anos)["Renúncia Acumulada (R$ Bi)"].iloc[-1] for e in e_vals]
    fig_sens = go.Figure(go.Scatter(x=e_vals, y=r_vals, mode='lines+markers', line_color="#f85149"))
    fig_sens.update_layout(xaxis_title="Elasticidade", yaxis_title="Renúncia Acumulada (R$ Bi)", plot_bgcolor="#0d1117", paper_bgcolor="#0d1117", font_color="#c9d1d9", height=350)
    st.plotly_chart(fig_sens, use_container_width=True)

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# ─────────────────────────────────────────────
# CONFIGURAÇÃO DA PÁGINA
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="RETI — Simulador de Impacto Ex-Ante",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────
# ESTILO VISUAL
# ─────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'IBM Plex Sans', sans-serif;
    }

    .main { background-color: #0d1117; }
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

    h1, h2, h3 { font-family: 'IBM Plex Sans', sans-serif; font-weight: 700; }

    .metric-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 10px;
        padding: 1.2rem 1.5rem;
        margin-bottom: 0.8rem;
    }
    .metric-card .label {
        font-size: 0.72rem;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 0.3rem;
    }
    .metric-card .value {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 1.6rem;
        font-weight: 600;
        color: #f0f6fc;
    }
    .metric-card .delta {
        font-size: 0.78rem;
        margin-top: 0.2rem;
    }
    .delta-pos { color: #3fb950; }
    .delta-neg { color: #f85149; }
    .delta-neu { color: #d29922; }

    .section-header {
        font-size: 0.68rem;
        font-weight: 600;
        color: #58a6ff;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        border-bottom: 1px solid #21262d;
        padding-bottom: 0.4rem;
        margin-bottom: 1rem;
        margin-top: 1.5rem;
    }

    .stSlider > div > div > div > div { background: #1f6feb !important; }

    .sidebar-title {
        font-size: 0.68rem;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 0.3rem;
        margin-top: 1rem;
    }

    div[data-testid="stSelectbox"] label,
    div[data-testid="stSlider"] label,
    div[data-testid="stNumberInput"] label {
        font-size: 0.8rem;
        color: #c9d1d9;
    }

    .formula-box {
        background: #161b22;
        border-left: 3px solid #1f6feb;
        border-radius: 0 8px 8px 0;
        padding: 0.8rem 1.2rem;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.82rem;
        color: #79c0ff;
        margin: 0.5rem 0 1rem 0;
    }

    .alert-box {
        background: #1c2128;
        border: 1px solid #d29922;
        border-radius: 8px;
        padding: 0.7rem 1rem;
        font-size: 0.78rem;
        color: #e3b341;
        margin-top: 0.5rem;
    }

    .tab-content { padding-top: 1rem; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# LÓGICA DO MODELO RETI
# ─────────────────────────────────────────────

def calcular_fator_f(receita_milhoes: float, intensidade_pnd: float) -> float:
    """Retorna o Fator F conforme Matriz RETI com tapering."""
    # Fator base por intensidade P&D
    if intensidade_pnd >= 0.05:
        if receita_milhoes <= 3.24:
            f = 3.5
        elif receita_milhoes <= 16.2:
            f = 3.0
        elif receita_milhoes <= 78.0:
            f = 2.5
        elif receita_milhoes <= 200.0:
            # Tapering: redução de 0.012 por R$1M após R$78M
            f = max(1.0, 2.5 - 0.012 * (receita_milhoes - 78.0))
        else:
            f = 1.0
    else:
        # Intensidade < 5%: fator reduzido
        if receita_milhoes <= 3.24:
            f = 2.5
        elif receita_milhoes <= 16.2:
            f = 2.0
        elif receita_milhoes <= 78.0:
            f = 1.5
        elif receita_milhoes <= 200.0:
            f = max(1.0, 1.5 - 0.004 * (receita_milhoes - 78.0))
        else:
            f = 1.0
    return f

def calcular_base_tributaria(receita: float, pnd_elegivel: float, fator_f: float,
                              multiplicador: float = 1.25, presuncao: float = 0.32) -> float:
    """Base tributária RETI."""
    base = (receita * presuncao) - (multiplicador * pnd_elegivel * fator_f)
    # Cap: base não pode ser negativa para efeito do incentivo
    return max(base, 0.0)

def calcular_imposto(base: float, aliquota_irpj: float = 0.15,
                     adicional_irpj: float = 0.10, aliquota_csll: float = 0.09,
                     limite_adicional: float = 240_000) -> dict:
    """Calcula IRPJ + CSLL sobre a base."""
    irpj = base * aliquota_irpj
    adicional = max(0, base - limite_adicional) * adicional_irpj
    csll = base * aliquota_csll
    total = irpj + adicional + csll
    return {"irpj": irpj, "adicional": adicional, "csll": csll, "total": total}

def simular_firma(
    receita_inicial_mm: float,
    intensidade_pnd: float,
    taxa_crescimento_receita: float,
    elasticidade_pnd: float,
    anos: int = 10,
    sem_reti: bool = False
) -> pd.DataFrame:
    """Simula trajetória de uma firma ao longo dos anos."""
    rows = []
    receita = receita_inicial_mm * 1_000_000

    for ano in range(1, anos + 1):
        receita_ano = receita * ((1 + taxa_crescimento_receita) ** (ano - 1))
        receita_mm = receita_ano / 1_000_000
        pnd_base = receita_ano * intensidade_pnd

        if sem_reti:
            # Sem RETI: base presumida padrão, sem superdedução
            base_tributaria = receita_ano * 0.32
            imposto = calcular_imposto(base_tributaria)
            pnd_efetivo = pnd_base
            incentivo_fiscal = 0
            fator_f = 0
        else:
            fator_f = calcular_fator_f(receita_mm, intensidade_pnd)
            # Efeito da elasticidade: redução do custo induz mais P&D
            reducao_custo_pnd = (1.25 * fator_f * 0.34)  # benefício marginal por R$ de P&D
            delta_pnd = pnd_base * abs(elasticidade_pnd) * reducao_custo_pnd
            pnd_efetivo = pnd_base + delta_pnd

            base_tributaria = calcular_base_tributaria(receita_ano, pnd_efetivo, fator_f)
            # Aplicar cap de 75% da receita bruta
            max_deducao = receita_ano * 0.75
            base_tributaria = max(receita_ano * 0.32 - max_deducao, base_tributaria)

            imposto_sem = calcular_imposto(receita_ano * 0.32)
            imposto_com = calcular_imposto(base_tributaria)
            incentivo_fiscal = imposto_sem["total"] - imposto_com["total"]
            imposto = imposto_com

        rows.append({
            "Ano": ano,
            "Receita (R$ MM)": receita_mm,
            "P&D Efetivo (R$ MM)": pnd_efetivo / 1_000_000,
            "Intensidade P&D (%)": (pnd_efetivo / receita_ano) * 100,
            "Fator F": fator_f,
            "Base Tributária (R$ MM)": base_tributaria / 1_000_000,
            "Imposto Total (R$ MM)": imposto["total"] / 1_000_000,
            "Incentivo Fiscal (R$ MM)": incentivo_fiscal / 1_000_000 if not sem_reti else 0,
        })

    return pd.DataFrame(rows)


def simular_impacto_fiscal_macro(
    n_empresas: int,
    receita_media_mm: float,
    intensidade_pnd_media: float,
    taxa_crescimento_universo: float,
    elasticidade_pnd: float,
    anos: int = 10
) -> pd.DataFrame:
    """Simula impacto fiscal agregado ao longo dos anos."""
    rows = []
    for ano in range(1, anos + 1):
        n_ativas = int(n_empresas * ((1 + 0.05) ** (ano - 1)))  # crescimento do universo elegível +5% a.a.
        receita_media = receita_media_mm * ((1 + taxa_crescimento_universo) ** (ano - 1))
        receita_mm = receita_media

        fator_f = calcular_fator_f(receita_mm, intensidade_pnd_media)
        pnd_base = receita_mm * 1e6 * intensidade_pnd_media
        reducao_custo = 1.25 * fator_f * 0.34
        delta_pnd = pnd_base * abs(elasticidade_pnd) * reducao_custo
        pnd_efetivo = pnd_base + delta_pnd

        base_sem_reti = receita_mm * 1e6 * 0.32
        base_com_reti = calcular_base_tributaria(receita_mm * 1e6, pnd_efetivo, fator_f)

        imposto_sem = calcular_imposto(base_sem_reti)
        imposto_com = calcular_imposto(base_com_reti)

        renuncia_por_firma = (imposto_sem["total"] - imposto_com["total"]) / 1e9
        renuncia_total = renuncia_por_firma * n_ativas

        # ROI fiscal: retorno via folha + consumo (estimado 1,3x sobre P&D incremental)
        pnd_incremental_total = (delta_pnd / 1e9) * n_ativas
        retorno_indireto = pnd_incremental_total * 1.3 * 0.25  # 25% retorna como tributo

        rows.append({
            "Ano": ano,
            "Empresas Ativas": n_ativas,
            "Renúncia Fiscal (R$ Bi)": renuncia_total,
            "P&D Incremental (R$ Bi)": pnd_incremental_total,
            "Retorno Tributário Indireto (R$ Bi)": retorno_indireto,
            "Renúncia Líquida (R$ Bi)": renuncia_total - retorno_indireto,
            "Renúncia Acumulada (R$ Bi)": 0,  # calculado depois
        })

    df = pd.DataFrame(rows)
    df["Renúncia Acumulada (R$ Bi)"] = df["Renúncia Fiscal (R$ Bi)"].cumsum()
    df["Renúncia Líquida Acumulada (R$ Bi)"] = df["Renúncia Líquida (R$ Bi)"].cumsum()
    return df


# ─────────────────────────────────────────────
# SIDEBAR — PARÂMETROS
# ─────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🔬 RETI Simulator")
    st.markdown("**Simulador de Impacto Ex-Ante**")
    st.markdown("---")

    st.markdown('<div class="sidebar-title">📊 Perfil da Firma</div>', unsafe_allow_html=True)

    receita_inicial = st.slider(
        "Receita Inicial (R$ MM)", min_value=0.5, max_value=300.0, value=15.0, step=0.5,
        help="Receita bruta anual da firma no Ano 1"
    )
    intensidade_pnd = st.slider(
        "Intensidade P&D (% da Receita)", min_value=1.0, max_value=30.0, value=8.0, step=0.5,
        help="Percentual da receita investido em P&D elegível"
    ) / 100.0

    taxa_crescimento_firma = st.slider(
        "Crescimento Anual da Receita (%)", min_value=0.0, max_value=40.0, value=15.0, step=1.0
    ) / 100.0

    st.markdown('<div class="sidebar-title">🏗️ Parâmetros Macro</div>', unsafe_allow_html=True)

    n_empresas = st.number_input(
        "Universo de Firmas Elegíveis", min_value=500, max_value=20000, value=4500, step=100
    )
    receita_media_universo = st.slider(
        "Receita Média do Universo (R$ MM)", min_value=1.0, max_value=100.0, value=12.0, step=1.0
    )
    intensidade_media = st.slider(
        "Intensidade P&D Média do Universo (%)", min_value=3.0, max_value=20.0, value=7.0, step=0.5
    ) / 100.0
    taxa_crescimento_universo = st.slider(
        "Crescimento Médio do Universo (%)", min_value=0.0, max_value=30.0, value=12.0, step=1.0
    ) / 100.0

    st.markdown('<div class="sidebar-title">⚙️ Calibragem do Modelo</div>', unsafe_allow_html=True)

    elasticidade = st.slider(
        "Elasticidade-Custo P&D", min_value=-2.0, max_value=-0.5, value=-1.27, step=0.01,
        help="Kannebley, Shimada & De Negri (2016): -1,27"
    )
    multiplicador = st.slider(
        "Multiplicador (superdedução)", min_value=1.0, max_value=1.6, value=1.25, step=0.05,
        help="Calibrado para benefício líquido dentro da faixa OCDE"
    )

    anos = st.slider("Horizonte de Simulação (anos)", 5, 15, 10)

    st.markdown("---")
    st.markdown(
        '<div style="font-size:0.68rem; color:#484f58; line-height:1.5">'
        'Baseado em Kannebley Jr., Shimada & De Negri (2016) | '
        'Definição P&D: Art. 2º Lei 11.196/05 + Manual Frascati (OCDE) | '
        'Limiar PoTec: IBGE/PINTEC</div>',
        unsafe_allow_html=True
    )

# ─────────────────────────────────────────────
# CÁLCULOS PRINCIPAIS
# ─────────────────────────────────────────────

df_firma_com = simular_firma(receita_inicial, intensidade_pnd, taxa_crescimento_firma, elasticidade, anos)
df_firma_sem = simular_firma(receita_inicial, intensidade_pnd, taxa_crescimento_firma, elasticidade, anos, sem_reti=True)
df_macro = simular_impacto_fiscal_macro(
    n_empresas, receita_media_universo, intensidade_media,
    taxa_crescimento_universo, elasticidade, anos
)

# Métricas síntese
pnd_total_com = df_firma_com["P&D Efetivo (R$ MM)"].sum()
pnd_total_sem = df_firma_sem["P&D Efetivo (R$ MM)"].sum()
pnd_adicional = pnd_total_com - pnd_total_sem
incentivo_total = df_firma_com["Incentivo Fiscal (R$ MM)"].sum()
roi_fiscal_firma = pnd_adicional / incentivo_total if incentivo_total > 0 else 0
renuncia_acumulada = df_macro["Renúncia Acumulada (R$ Bi)"].iloc[-1]
pnd_macro_total = df_macro["P&D Incremental (R$ Bi)"].sum()
retorno_total = df_macro["Retorno Tributário Indireto (R$ Bi)"].sum()

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────

st.markdown("""
<div style="border-bottom: 1px solid #21262d; padding-bottom: 1rem; margin-bottom: 1.5rem;">
    <div style="font-size:0.68rem; color:#1f6feb; text-transform:uppercase; letter-spacing:0.12em; font-weight:600; margin-bottom:0.3rem;">
        SPE/MF · Documento de Trabalho
    </div>
    <h1 style="color:#f0f6fc; margin:0; font-size:1.8rem; line-height:1.2;">
        RETI — Regime Especial de Tributação para a Inovação
    </h1>
    <div style="color:#8b949e; font-size:0.88rem; margin-top:0.4rem;">
        Simulador de Impacto Ex-Ante · Nível da Firma & Agregado Fiscal
    </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs([
    "📈  Nível da Firma",
    "🏛️  Impacto Fiscal Agregado",
    "🔭  Fator F & Sensibilidade"
])

# ══════════════════════════════════════════════
# TAB 1 — NÍVEL DA FIRMA
# ══════════════════════════════════════════════

with tab1:
    st.markdown('<div class="tab-content">', unsafe_allow_html=True)

    # KPIs da firma
    fator_f_ano1 = calcular_fator_f(receita_inicial, intensidade_pnd)
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="label">Fator F · Ano 1</div>
            <div class="value">{fator_f_ano1:.2f}</div>
            <div class="delta delta-neu">Intensidade P&D: {intensidade_pnd*100:.1f}%</div>
        </div>""", unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="label">P&D Adicional Acumulado</div>
            <div class="value">R$ {pnd_adicional:.1f}MM</div>
            <div class="delta delta-pos">+{(pnd_adicional/pnd_total_sem*100):.1f}% vs. sem RETI</div>
        </div>""", unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="label">Incentivo Fiscal Total</div>
            <div class="value">R$ {incentivo_total:.1f}MM</div>
            <div class="delta delta-neu">Acumulado {anos} anos</div>
        </div>""", unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="label">ROI Fiscal (P&D/Incentivo)</div>
            <div class="value">{roi_fiscal_firma:.2f}x</div>
            <div class="delta delta-pos">Adicionalidade efetiva</div>
        </div>""", unsafe_allow_html=True)

    st.markdown('<div class="formula-box">Base = (Receita × 0,32) − (1,25 × P&D_elig × F)</div>', unsafe_allow_html=True)

    # Gráfico 1: P&D com vs. sem RETI
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(
        x=df_firma_com["Ano"], y=df_firma_com["P&D Efetivo (R$ MM)"],
        name="Com RETI", line=dict(color="#1f6feb", width=2.5),
        fill="tozeroy", fillcolor="rgba(31,111,235,0.08)"
    ))
    fig1.add_trace(go.Scatter(
        x=df_firma_sem["Ano"], y=df_firma_sem["P&D Efetivo (R$ MM)"],
        name="Sem RETI", line=dict(color="#8b949e", width=1.8, dash="dash")
    ))
    fig1.update_layout(
        title="Investimento em P&D — Firma Individual",
        xaxis_title="Ano", yaxis_title="R$ MM",
        plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
        font=dict(color="#c9d1d9", size=11),
        legend=dict(bgcolor="#161b22", bordercolor="#30363d", borderwidth=1),
        xaxis=dict(gridcolor="#21262d", dtick=1),
        yaxis=dict(gridcolor="#21262d"),
        height=340
    )
    st.plotly_chart(fig1, use_container_width=True)

    col_a, col_b = st.columns(2)

    with col_a:
        # Gráfico 2: Imposto pago
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=df_firma_sem["Ano"], y=df_firma_sem["Imposto Total (R$ MM)"],
            name="Sem RETI", marker_color="#484f58"
        ))
        fig2.add_trace(go.Bar(
            x=df_firma_com["Ano"], y=df_firma_com["Imposto Total (R$ MM)"],
            name="Com RETI", marker_color="#1f6feb"
        ))
        fig2.update_layout(
            title="Carga Tributária Efetiva",
            xaxis_title="Ano", yaxis_title="R$ MM",
            barmode="group",
            plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
            font=dict(color="#c9d1d9", size=11),
            legend=dict(bgcolor="#161b22", bordercolor="#30363d", borderwidth=1),
            xaxis=dict(gridcolor="#21262d", dtick=1),
            yaxis=dict(gridcolor="#21262d"),
            height=300
        )
        st.plotly_chart(fig2, use_container_width=True)

    with col_b:
        # Gráfico 3: Incentivo fiscal por ano
        fig3 = go.Figure()
        fig3.add_trace(go.Bar(
            x=df_firma_com["Ano"], y=df_firma_com["Incentivo Fiscal (R$ MM)"],
            marker_color="#3fb950", name="Incentivo Fiscal"
        ))
        fig3.add_trace(go.Scatter(
            x=df_firma_com["Ano"],
            y=df_firma_com["Incentivo Fiscal (R$ MM)"].cumsum(),
            name="Acumulado", line=dict(color="#d29922", width=2),
            yaxis="y2"
        ))
        fig3.update_layout(
            title="Incentivo Fiscal Anual & Acumulado",
            xaxis_title="Ano", yaxis_title="R$ MM (anual)",
            yaxis2=dict(title="R$ MM (acumulado)", overlaying="y", side="right",
                        gridcolor="#21262d", color="#d29922"),
            plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
            font=dict(color="#c9d1d9", size=11),
            legend=dict(bgcolor="#161b22", bordercolor="#30363d", borderwidth=1),
            xaxis=dict(gridcolor="#21262d", dtick=1),
            yaxis=dict(gridcolor="#21262d"),
            height=300
        )
        st.plotly_chart(fig3, use_container_width=True)

    # Tabela resumo
    st.markdown('<div class="section-header">Tabela de Trajetória Anual</div>', unsafe_allow_html=True)
    display_df = df_firma_com[["Ano", "Receita (R$ MM)", "P&D Efetivo (R$ MM)",
                                "Intensidade P&D (%)", "Fator F",
                                "Imposto Total (R$ MM)", "Incentivo Fiscal (R$ MM)"]].copy()
    display_df = display_df.set_index("Ano")
    display_df = display_df.round(2)
    st.dataframe(display_df.style.format("{:.2f}"), use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════
# TAB 2 — IMPACTO FISCAL AGREGADO
# ══════════════════════════════════════════════

with tab2:
    st.markdown('<div class="tab-content">', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="label">Renúncia Acumulada {anos}a</div>
            <div class="value">R$ {renuncia_acumulada:.2f}Bi</div>
            <div class="delta delta-neg">Exposição fiscal bruta</div>
        </div>""", unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="label">P&D Incremental Total</div>
            <div class="value">R$ {pnd_macro_total:.2f}Bi</div>
            <div class="delta delta-pos">Adicionalidade agregada</div>
        </div>""", unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="label">Retorno Tributário Indireto</div>
            <div class="value">R$ {retorno_total:.2f}Bi</div>
            <div class="delta delta-pos">Via folha + consumo</div>
        </div>""", unsafe_allow_html=True)

    with col4:
        renuncia_liquida = df_macro["Renúncia Líquida Acumulada (R$ Bi)"].iloc[-1]
        st.markdown(f"""
        <div class="metric-card">
            <div class="label">Renúncia Líquida {anos}a</div>
            <div class="value">R$ {renuncia_liquida:.2f}Bi</div>
            <div class="delta delta-neu">Bruta − retorno indireto</div>
        </div>""", unsafe_allow_html=True)

    # Gráfico principal: renúncia bruta vs. líquida vs. P&D incremental
    fig_macro = go.Figure()

    fig_macro.add_trace(go.Bar(
        x=df_macro["Ano"], y=df_macro["P&D Incremental (R$ Bi)"],
        name="P&D Incremental", marker_color="rgba(31,111,235,0.6)"
    ))
    fig_macro.add_trace(go.Bar(
        x=df_macro["Ano"], y=df_macro["Retorno Tributário Indireto (R$ Bi)"],
        name="Retorno Tributário Indireto", marker_color="rgba(63,185,80,0.7)"
    ))
    fig_macro.add_trace(go.Scatter(
        x=df_macro["Ano"], y=df_macro["Renúncia Fiscal (R$ Bi)"],
        name="Renúncia Bruta", line=dict(color="#f85149", width=2.5),
        mode="lines+markers", marker=dict(size=6)
    ))
    fig_macro.add_trace(go.Scatter(
        x=df_macro["Ano"], y=df_macro["Renúncia Líquida (R$ Bi)"],
        name="Renúncia Líquida", line=dict(color="#d29922", width=2, dash="dot"),
        mode="lines+markers", marker=dict(size=5)
    ))

    fig_macro.update_layout(
        title=f"Impacto Fiscal Anual — Universo de {n_empresas:,} PMEs Inovadoras",
        xaxis_title="Ano", yaxis_title="R$ Bilhões",
        barmode="group",
        plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
        font=dict(color="#c9d1d9", size=11),
        legend=dict(bgcolor="#161b22", bordercolor="#30363d", borderwidth=1,
                    orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(gridcolor="#21262d", dtick=1),
        yaxis=dict(gridcolor="#21262d"),
        height=400
    )
    st.plotly_chart(fig_macro, use_container_width=True)

    col_x, col_y = st.columns(2)

    with col_x:
        # Curva acumulada
        fig_acum = go.Figure()
        fig_acum.add_trace(go.Scatter(
            x=df_macro["Ano"], y=df_macro["Renúncia Acumulada (R$ Bi)"],
            name="Renúncia Bruta Acumulada",
            line=dict(color="#f85149", width=2.5),
            fill="tozeroy", fillcolor="rgba(248,81,73,0.07)"
        ))
        fig_acum.add_trace(go.Scatter(
            x=df_macro["Ano"], y=df_macro["Renúncia Líquida Acumulada (R$ Bi)"],
            name="Renúncia Líquida Acumulada",
            line=dict(color="#d29922", width=2, dash="dash")
        ))
        # Linha do teto LRF
        teto_lrf = 2.2
        fig_acum.add_hline(
            y=teto_lrf * anos * 0.3,  # referência visual
            line_dash="dot", line_color="#58a6ff", opacity=0.5,
            annotation_text=f"Teto LRF: R$ {teto_lrf}Bi/ano", annotation_position="top right"
        )
        fig_acum.update_layout(
            title="Renúncia Fiscal Acumulada",
            xaxis_title="Ano", yaxis_title="R$ Bilhões",
            plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
            font=dict(color="#c9d1d9", size=11),
            legend=dict(bgcolor="#161b22", bordercolor="#30363d", borderwidth=1),
            xaxis=dict(gridcolor="#21262d", dtick=1),
            yaxis=dict(gridcolor="#21262d"),
            height=320
        )
        st.plotly_chart(fig_acum, use_container_width=True)

    with col_y:
        # Empresas ativas ao longo do tempo
        fig_emp = go.Figure()
        fig_emp.add_trace(go.Scatter(
            x=df_macro["Ano"], y=df_macro["Empresas Ativas"],
            line=dict(color="#79c0ff", width=2.5),
            fill="tozeroy", fillcolor="rgba(121,192,255,0.08)",
            name="Empresas Elegíveis"
        ))
        fig_emp.update_layout(
            title="Evolução do Universo Elegível",
            xaxis_title="Ano", yaxis_title="Nº de Empresas",
            plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
            font=dict(color="#c9d1d9", size=11),
            xaxis=dict(gridcolor="#21262d", dtick=1),
            yaxis=dict(gridcolor="#21262d"),
            showlegend=False,
            height=320
        )
        st.plotly_chart(fig_emp, use_container_width=True)

    # Tabela macro
    st.markdown('<div class="section-header">Tabela de Impacto Fiscal Anual</div>', unsafe_allow_html=True)
    df_macro_display = df_macro.set_index("Ano").round(3)
    st.dataframe(df_macro_display.style.format("{:.3f}"), use_container_width=True)

    # Alerta de teto LRF
    renuncia_ano1 = df_macro["Renúncia Fiscal (R$ Bi)"].iloc[0]
    if renuncia_ano1 > 2.2:
        st.markdown(f"""
        <div class="alert-box">
            ⚠️ <strong>Atenção:</strong> Com os parâmetros atuais, a renúncia no Ano 1 
            (R$ {renuncia_ano1:.2f}Bi) excede o teto de compensação primária de R$ 2,2Bi/ano, 
            ativando a medida secundária de majoração de CSLL para instituições financeiras.
        </div>""", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════
# TAB 3 — FATOR F & SENSIBILIDADE
# ══════════════════════════════════════════════

with tab3:
    st.markdown('<div class="tab-content">', unsafe_allow_html=True)

    st.markdown('<div class="section-header">Curva do Fator F por Faixa de Receita</div>', unsafe_allow_html=True)

    # Gerar curva do Fator F
    receitas = np.linspace(0.5, 250, 500)
    f_alta = [calcular_fator_f(r, 0.08) for r in receitas]
    f_baixa = [calcular_fator_f(r, 0.03) for r in receitas]

    fig_f = go.Figure()
    fig_f.add_trace(go.Scatter(
        x=receitas, y=f_alta,
        name="Intensidade P&D ≥ 5%", line=dict(color="#1f6feb", width=2.5),
        fill="tozeroy", fillcolor="rgba(31,111,235,0.05)"
    ))
    fig_f.add_trace(go.Scatter(
        x=receitas, y=f_baixa,
        name="Intensidade P&D < 5%", line=dict(color="#8b949e", width=1.8, dash="dash")
    ))

    # Linha do parâmetro atual
    fig_f.add_vline(
        x=receita_inicial, line_dash="dot", line_color="#3fb950",
        annotation_text=f"Firma simulada: R${receita_inicial}MM", annotation_position="top right"
    )

    # Faixas de regime
    fig_f.add_vrect(x0=0, x1=78, fillcolor="rgba(31,111,235,0.03)",
                    annotation_text="Regime Pleno", annotation_position="top left")
    fig_f.add_vrect(x0=78, x1=200, fillcolor="rgba(210,153,34,0.05)",
                    annotation_text="Tapering", annotation_position="top left")

    fig_f.update_layout(
        title="Fator F em Função da Receita (Tapering Linear após R$ 78MM)",
        xaxis_title="Receita Bruta Anual (R$ MM)",
        yaxis_title="Fator F",
        plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
        font=dict(color="#c9d1d9", size=11),
        legend=dict(bgcolor="#161b22", bordercolor="#30363d", borderwidth=1),
        xaxis=dict(gridcolor="#21262d"),
        yaxis=dict(gridcolor="#21262d", range=[0.8, 4.0]),
        height=350
    )
    st.plotly_chart(fig_f, use_container_width=True)

    # Heatmap de sensibilidade: P&D adicional por combinação receita × intensidade
    st.markdown('<div class="section-header">Heatmap de Sensibilidade — P&D Adicional (R$ MM, Ano 1)</div>', unsafe_allow_html=True)

    receitas_heat = [1.0, 3.0, 10.0, 25.0, 50.0, 80.0, 120.0, 200.0]
    intensidades_heat = [0.03, 0.05, 0.08, 0.12, 0.15, 0.20]
    z_matrix = []

    for intens in intensidades_heat:
        row = []
        for rec in receitas_heat:
            f = calcular_fator_f(rec, intens)
            pnd_b = rec * 1e6 * intens
            reducao = 1.25 * f * 0.34
            delta = pnd_b * abs(elasticidade) * reducao / 1e6
            row.append(round(delta, 2))
        z_matrix.append(row)

    fig_heat = go.Figure(data=go.Heatmap(
        z=z_matrix,
        x=[f"R${r}MM" for r in receitas_heat],
        y=[f"{int(i*100)}%" for i in intensidades_heat],
        colorscale=[[0, "#0d1117"], [0.3, "#1f4e79"], [0.7, "#1f6feb"], [1.0, "#79c0ff"]],
        text=[[f"{v:.2f}" for v in row] for row in z_matrix],
        texttemplate="%{text}",
        textfont=dict(size=10, color="white"),
        showscale=True,
        colorbar=dict(title="R$ MM", tickfont=dict(color="#c9d1d9"))
    ))

    fig_heat.update_layout(
        title="P&D Adicional Induzido (R$ MM) por Perfil de Firma",
        xaxis_title="Receita Bruta",
        yaxis_title="Intensidade P&D",
        plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
        font=dict(color="#c9d1d9", size=11),
        height=360
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    # Análise de sensibilidade da elasticidade
    st.markdown('<div class="section-header">Sensibilidade da Renúncia Fiscal ao Parâmetro de Elasticidade</div>', unsafe_allow_html=True)

    elasticidades = np.linspace(-2.0, -0.5, 30)
    renuncia_por_e = []
    pnd_por_e = []
    for e in elasticidades:
        df_e = simular_impacto_fiscal_macro(n_empresas, receita_media_universo,
                                             intensidade_media, taxa_crescimento_universo, e, anos)
        renuncia_por_e.append(df_e["Renúncia Acumulada (R$ Bi)"].iloc[-1])
        pnd_por_e.append(df_e["P&D Incremental (R$ Bi)"].sum())

    fig_sens = make_subplots(specs=[[{"secondary_y": True}]])
    fig_sens.add_trace(go.Scatter(
        x=elasticidades, y=renuncia_por_e,
        name="Renúncia Acumulada (R$ Bi)",
        line=dict(color="#f85149", width=2.5)
    ), secondary_y=False)
    fig_sens.add_trace(go.Scatter(
        x=elasticidades, y=pnd_por_e,
        name="P&D Incremental Total (R$ Bi)",
        line=dict(color="#3fb950", width=2.5)
    ), secondary_y=True)
    fig_sens.add_vline(
        x=elasticidade, line_dash="dot", line_color="#d29922",
        annotation_text=f"Parâmetro atual: {elasticidade:.2f}", annotation_position="top"
    )
    fig_sens.update_layout(
        title="Sensibilidade ao Coeficiente de Elasticidade-Custo",
        xaxis_title="Elasticidade-Custo P&D",
        plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
        font=dict(color="#c9d1d9", size=11),
        legend=dict(bgcolor="#161b22", bordercolor="#30363d", borderwidth=1),
        xaxis=dict(gridcolor="#21262d"),
        yaxis=dict(gridcolor="#21262d", title="Renúncia Acumulada (R$ Bi)", color="#f85149"),
        yaxis2=dict(gridcolor="#21262d", title="P&D Incremental (R$ Bi)", color="#3fb950"),
        height=360
    )
    st.plotly_chart(fig_sens, use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

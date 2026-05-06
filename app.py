"""
RETI — Regime Especial de Tributação para a Inovação
Decision Support System v6.0 | SPE/MF · Receita Federal
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# ─────────────────────────────────────────────────────────────
# DESIGN SYSTEM
# ─────────────────────────────────────────────────────────────
CORES = dict(
    gold   = "#C9A84C",
    cyan   = "#2BBFCE",
    red    = "#E05252",
    green  = "#3EC97B",
    amber  = "#E8A020",
    bg     = "#0A0E1A",
    card   = "#0F1525",
    panel  = "#141B2D",
    border = "#1E2A45",
    text   = "#D4DDF2",
    muted  = "#6B7A9E",
)

st.set_page_config(
    page_title="RETI — Decision Support System v6.0",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Sora:wght@300;400;600;700&display=swap');

html, body, [class*="css"] {{
    font-family: 'Sora', sans-serif;
    background-color: {CORES['bg']};
    color: {CORES['text']};
}}
.stApp {{ background-color: {CORES['bg']}; }}
section[data-testid="stSidebar"] {{
    background-color: {CORES['card']};
    border-right: 1px solid {CORES['border']};
}}
.stMetric {{
    background: {CORES['card']};
    border-left: 3px solid {CORES['gold']};
    border: 1px solid {CORES['border']};
    border-left: 3px solid {CORES['gold']};
    padding: 12px 16px !important;
    border-radius: 6px;
}}
.stMetric label {{ color: {CORES['muted']} !important; font-family: 'DM Mono', monospace !important; font-size: 11px !important; letter-spacing: 0.08em; }}
.stMetric [data-testid="stMetricValue"] {{ color: {CORES['gold']} !important; font-family: 'Sora', sans-serif !important; font-size: 22px !important; }}
.stTabs [data-baseweb="tab-list"] {{ background: {CORES['card']}; border-bottom: 1px solid {CORES['border']}; gap: 0; }}
.stTabs [data-baseweb="tab"] {{ color: {CORES['muted']}; font-family: 'DM Mono', monospace; font-size: 11px; letter-spacing: 0.1em; padding: 10px 20px; }}
.stTabs [aria-selected="true"] {{ color: {CORES['gold']} !important; border-bottom: 2px solid {CORES['gold']} !important; background: transparent !important; }}
.stSlider > div > div > div {{ background: {CORES['cyan']}; }}
div[data-testid="stExpander"] {{ background: {CORES['card']}; border: 1px solid {CORES['border']}; border-radius: 6px; }}
.block-container {{ padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1400px; }}
h1, h2, h3 {{ font-family: 'Sora', sans-serif; color: {CORES['gold']}; }}
.stDataFrame {{ background: {CORES['card']}; }}
.stAlert {{ border-radius: 6px; }}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# CONSTANTES DO MODELO
# ─────────────────────────────────────────────────────────────
LAG_MATURACAO      = 3
TAXA_DEPRECIACAO   = 0.15
PROB_SUCESSO       = 0.70
ALIQUOTA_COMBINADA = 0.34   # IRPJ 25% + CSLL 9%
MARGEM_PRESUMIDA   = 0.32   # Base tributável presumida


# ─────────────────────────────────────────────────────────────
# MOTOR DE CÁLCULO
# ─────────────────────────────────────────────────────────────
def fator_f(rec: float, f_teto: float = 3.5, f_medio: float = 2.5) -> float:
    """
    Fator de benefício progressivo com phasing-out linear.
    Neutraliza o 'efeito notch' entre R$78M e R$200M.
    """
    if rec <= 3.24:  return f_teto
    if rec <= 78:    return f_medio
    if rec <= 200:   return max(1.0, f_medio - 0.01229 * (rec - 78))
    return 1.0


def curva_adesao(t: int, total: int, velocidade: float = 1.2, ponto_inflexao: int = 3) -> float:
    """Sigmoide calibrada no histórico da Lei do Bem."""
    return total / (1 + np.exp(-velocidade * (t - ponto_inflexao)))


def motor_reti(p: dict) -> pd.DataFrame:
    """
    Motor principal de simulação.
    Retorna DataFrame com todas as variáveis micro e macro por ano.
    """
    anos    = p["anos"]
    rec     = p["rec_inicial"]
    estoque = 0.0
    credito = 0.0
    hist_pd = [0.0] * (anos + LAG_MATURACAO + 2)
    rows    = []

    for t in range(1, anos + 1):
        rec_ant = rec
        rec     = rec * (1 + p["crescimento"])
        f       = fator_f(rec, p["f_teto"], p["f_medio"])

        # P&D e adicionalidade
        pd_orig  = rec * p["int_pd"]
        pd_adic  = pd_orig * abs(p["elasticidade"]) * (p["mult"] * f * ALIQUOTA_COMBINADA)
        pd_total = pd_orig + pd_adic

        if t + LAG_MATURACAO <= anos:
            hist_pd[t + LAG_MATURACAO] = pd_adic * PROB_SUCESSO

        # Estoque de conhecimento (modelo de capital)
        pd_maturado = hist_pd[t]
        estoque     = estoque * (1 - TAXA_DEPRECIACAO) + pd_maturado
        ganho_prod  = (estoque / rec) * p["beta_ptf"] if rec > 0 else 0

        # Retorno fiscal indireto
        lucro_incremental = rec * ganho_prod
        retorno_indireto  = lucro_incremental * ALIQUOTA_COMBINADA

        # Crédito fiscal RETI
        imp_ref      = (rec * MARGEM_PRESUMIDA) * ALIQUOTA_COMBINADA
        limite_comp  = imp_ref * p["limite_compensacao"]
        novo_credito = (p["mult"] * pd_total * f) * ALIQUOTA_COMBINADA
        credito     += novo_credito

        # Gatilho de performance (após mês 36)
        if t <= 3:
            pode_usar = True
        else:
            pode_usar = (
                ((rec / rec_ant - 1) >= 0.10)
                or (p["patente_ano"] <= t)
                or (p["potec_pct"] > 15)
            )

        uso_credito = min(credito, limite_comp) if pode_usar else 0
        imp_final   = max(imp_ref * (1 - p["limite_compensacao"]), imp_ref - uso_credito)
        renuncia    = imp_ref - imp_final
        credito    -= renuncia

        # Macro
        firmas        = curva_adesao(t, p["n_firmas"])
        renuncia_macro = (renuncia * firmas) / 1e3   # R$ bi
        retorno_macro  = (retorno_indireto * firmas) / 1e3
        saldo_liquido  = retorno_macro - renuncia_macro
        lrf_ok         = renuncia_macro <= p["teto_lrf"]

        rows.append({
            "Ano":              t,
            "Receita_MM":       round(rec, 2),
            "Fator_F":          round(f, 3),
            "PD_Total_MM":      round(pd_total, 2),
            "PD_Adicional_MM":  round(pd_adic, 2),
            "Ganho_Prod_Pct":   round(ganho_prod * 100, 4),
            "Renuncia_Firma":   round(renuncia, 6),
            "Retorno_Ind_Firma":round(retorno_indireto, 6),
            "Firmas_Aderentes": int(firmas),
            "Renuncia_Bi":      round(renuncia_macro, 4),
            "Retorno_Bi":       round(retorno_macro, 4),
            "Saldo_Liquido_Bi": round(saldo_liquido, 4),
            "Estoque_Credito":  round(credito, 4),
            "LRF_OK":           lrf_ok,
            "Status_Gatilho":   "Ativo" if pode_usar else "Suspenso",
        })

    df = pd.DataFrame(rows)

    # Acumulados e payback
    df["Renuncia_Acum_Bi"] = df["Renuncia_Bi"].cumsum().round(3)
    df["Retorno_Acum_Bi"]  = df["Retorno_Bi"].cumsum().round(3)
    df["ROI_Acum_Pct"]     = ((df["Retorno_Acum_Bi"] / df["Renuncia_Acum_Bi"]) - 1) * 100

    return df


def calcular_kpis(df: pd.DataFrame, teto_lrf: float) -> dict:
    total_ren  = df["Renuncia_Bi"].sum()
    total_ret  = df["Retorno_Bi"].sum()
    roi        = ((total_ret / total_ren) - 1) * 100 if total_ren > 0 else 0
    violacoes  = (df["LRF_OK"] == False).sum()
    payback_df = df[df["Retorno_Acum_Bi"] >= df["Renuncia_Acum_Bi"]]
    payback    = int(payback_df["Ano"].iloc[0]) if len(payback_df) > 0 else None
    pico_ren   = df["Renuncia_Bi"].max()

    return dict(
        total_ren=total_ren, total_ret=total_ret,
        roi=roi, violacoes=violacoes,
        payback=payback, pico_ren=pico_ren,
    )


def matriz_sensibilidade(base_params: dict) -> pd.DataFrame:
    elasticidades = [-0.6, -0.9, -1.27, -1.6, -2.0]
    mults         = [1.0, 1.1, 1.25, 1.4, 1.5]
    rows = []
    for e in elasticidades:
        for m in mults:
            p = {**base_params, "elasticidade": e, "mult": m}
            df = motor_reti(p)
            tr = df["Renuncia_Bi"].sum()
            tt = df["Retorno_Bi"].sum()
            lrf_ok = (df["LRF_OK"] == False).sum() == 0
            rows.append({
                "Elasticidade": e, "Mult_M": m,
                "ROI_Pct":    round(((tt / tr) - 1) * 100 if tr > 0 else 0, 1),
                "Renuncia_Total": round(tr, 2),
                "LRF_OK": lrf_ok,
            })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────
# PLOTLY THEME
# ─────────────────────────────────────────────────────────────
PLOT_LAYOUT = dict(
    paper_bgcolor = CORES["bg"],
    plot_bgcolor  = CORES["panel"],
    font          = dict(family="DM Mono, monospace", color=CORES["muted"], size=11),
    xaxis         = dict(gridcolor=CORES["border"], zerolinecolor=CORES["border"]),
    yaxis         = dict(gridcolor=CORES["border"], zerolinecolor=CORES["border"]),
    legend        = dict(bgcolor=CORES["card"], bordercolor=CORES["border"],
                         borderwidth=1, font=dict(size=10)),
    margin        = dict(l=50, r=20, t=40, b=40),
    hovermode     = "x unified",
)


# ─────────────────────────────────────────────────────────────
# INTERFACE — SIDEBAR
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style='border-left:3px solid {CORES["gold"]};padding-left:12px;margin-bottom:20px'>
        <div style='color:{CORES["gold"]};font-size:16px;font-weight:700;letter-spacing:0.05em'>RETI DSS</div>
        <div style='color:{CORES["muted"]};font-size:10px;font-family:DM Mono;letter-spacing:0.1em'>
        REGIME ESPECIAL DE TRIBUTAÇÃO<br>PARA A INOVAÇÃO — v6.0
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.subheader("⚙️ Parâmetros de Política")

    n_firmas    = st.number_input("Universo de Firmas Elegíveis", value=4500, step=100)
    teto_lrf    = st.slider("Teto LRF (R$ Bi/ano)", 0.5, 5.0, 2.2, 0.1,
                             help="Limite máximo de renúncia fiscal anual — LRF Art. 14")
    mult        = st.slider("Multiplicador M", 1.00, 1.50, 1.25, 0.01,
                             help="Proposta RETI: 1,25 | Referência Lei do Bem: 1,60–1,80")
    elasticidade= st.slider("Elasticidade ε", -2.0, -0.5, -1.27, 0.01,
                             help="Kannebley, Shimada & De Negri (2016): −1,27")
    limite_comp = st.slider("Limite de Compensação (% imposto ref.)", 25, 75, 50, 5,
                             help="Quanto do imposto de referência pode ser compensado por ano") / 100

    st.divider()
    st.subheader("🏢 Perfil da Firma-Tipo")

    rec_ini    = st.number_input("Receita Inicial (R$ MM)", value=15.0, step=1.0)
    int_pd     = st.slider("Intensidade P&D (%)", 1.0, 25.0, 7.0, 0.5,
                            help="% da Receita destinada a P&D") / 100
    crescimento= st.slider("Crescimento Anual (%)", 0.0, 30.0, 12.0, 0.5) / 100
    horizonte  = st.slider("Horizonte (Anos)", 5, 15, 10)

    st.divider()
    st.subheader("🎯 Gatilhos de Performance")

    patente_ano= st.slider("Depósito de Patente (Ano)", 1, 10, 3,
                            help="Gatilho alternativo para uso de crédito pós-mês 36")
    potec_pct  = st.slider("PoTec — Pessoal Qualificado (%)", 0.0, 30.0, 18.0, 0.5,
                            help=">15% do quadro = gatilho alternativo")

    st.divider()
    st.subheader("📐 Calibração PTF")

    beta_ptf   = st.slider("β PTF/P&D", 0.030, 0.120, 0.060, 0.005,
                            help="Elasticidade PTF/P&D — OCDE/BM: 0,05–0,08")
    f_teto     = st.slider("F teto (microempresas ≤ R$3,24MM)", 2.0, 5.0, 3.5, 0.5)
    f_medio    = st.slider("F médio (MPMEs ≤ R$78MM)", 1.5, 3.5, 2.5, 0.5)


# ─────────────────────────────────────────────────────────────
# EXECUÇÃO DO MOTOR
# ─────────────────────────────────────────────────────────────
params = dict(
    anos=horizonte, rec_inicial=rec_ini, crescimento=crescimento,
    int_pd=int_pd, elasticidade=elasticidade, mult=mult,
    n_firmas=n_firmas, teto_lrf=teto_lrf, beta_ptf=beta_ptf,
    patente_ano=patente_ano, potec_pct=potec_pct,
    limite_compensacao=limite_comp,
    f_teto=f_teto, f_medio=f_medio,
)
df   = motor_reti(params)
kpis = calcular_kpis(df, teto_lrf)


# ─────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────
col_h1, col_h2, col_h3, col_h4 = st.columns([3, 1, 1, 1])
with col_h1:
    st.markdown(f"""
    <div style='padding:4px 0 16px'>
        <div style='color:{CORES["gold"]};font-size:22px;font-weight:700;letter-spacing:0.04em;font-family:Sora'>
            RETI — Decision Support System
        </div>
        <div style='color:{CORES["muted"]};font-size:11px;font-family:DM Mono;letter-spacing:0.08em;margin-top:4px'>
            SECRETARIA DE POLÍTICA ECONÔMICA / MINISTÉRIO DA FAZENDA · RECEITA FEDERAL DO BRASIL
        </div>
    </div>
    """, unsafe_allow_html=True)
with col_h2:
    lrf_status  = "✅ LRF OK" if kpis["violacoes"] == 0 else f"⚠️ LRF: {kpis['violacoes']} violações"
    lrf_color   = CORES["green"] if kpis["violacoes"] == 0 else CORES["red"]
    st.markdown(f"<div style='color:{lrf_color};font-family:DM Mono;font-size:12px;padding-top:12px;font-weight:600'>{lrf_status}</div>", unsafe_allow_html=True)
with col_h3:
    roi_color = CORES["green"] if kpis["roi"] >= 0 else CORES["red"]
    st.markdown(f"<div style='color:{roi_color};font-family:DM Mono;font-size:12px;padding-top:12px;font-weight:600'>ROI: {kpis['roi']:+.1f}%</div>", unsafe_allow_html=True)
with col_h4:
    pb = f"Payback: Ano {kpis['payback']}" if kpis["payback"] else "Payback: > horizonte"
    st.markdown(f"<div style='color:{CORES['cyan']};font-family:DM Mono;font-size:12px;padding-top:12px;font-weight:600'>{pb}</div>", unsafe_allow_html=True)

st.divider()


# ─────────────────────────────────────────────────────────────
# KPI CARDS
# ─────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Custo Fiscal Acumulado",      f"R$ {kpis['total_ren']:.2f} Bi",
          delta=f"Pico: R$ {kpis['pico_ren']:.2f}Bi/ano", delta_color="off")
k2.metric("Retorno Indireto Acumulado",  f"R$ {kpis['total_ret']:.2f} Bi",
          delta="Via PTF + lucro tributável", delta_color="off")
k3.metric("ROI Líquido Acumulado",       f"{kpis['roi']:+.1f}%",
          delta="Retorno / Renúncia − 1", delta_color="normal" if kpis["roi"] >= 0 else "inverse")
k4.metric("Payback do Tesouro",          f"Ano {kpis['payback']}" if kpis["payback"] else "> Horizonte")
k5.metric("Violações LRF",               str(kpis["violacoes"]),
          delta="anos acima do teto", delta_color="off" if kpis["violacoes"] == 0 else "inverse")

st.markdown("<br>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# ABAS
# ─────────────────────────────────────────────────────────────
tabs = st.tabs([
    "📊 FISCAL",
    "🔬 PTF & P&D",
    "🏢 FIRMAS & LRF",
    "🎯 SENSIBILIDADE",
    "📋 DADOS",
    "🏛️ ANÁLISE SPE/MF",
])


# ────────────────────────────────────────────
# TAB 0 — FISCAL
# ────────────────────────────────────────────
with tabs[0]:
    st.subheader("Fluxo de Caixa do Tesouro — O 'Vale da Morte' da Inovação")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["Ano"], y=df["Renuncia_Bi"], name="Renúncia fiscal (saída)",
        fill="tozeroy", fillcolor=f"rgba(224,82,82,0.15)",
        line=dict(color=CORES["red"], width=2),
    ))
    fig.add_trace(go.Scatter(
        x=df["Ano"], y=df["Retorno_Bi"], name="Retorno indireto (entrada)",
        fill="tonexty", fillcolor=f"rgba(62,201,123,0.12)",
        line=dict(color=CORES["green"], width=2),
    ))
    fig.add_hline(y=teto_lrf, line_dash="dot", line_color=CORES["amber"],
                  annotation_text=f"Teto LRF: R$ {teto_lrf}Bi",
                  annotation_font_color=CORES["amber"])
    if kpis["payback"]:
        fig.add_vline(x=kpis["payback"], line_dash="dash", line_color=CORES["gold"],
                      annotation_text=f"Payback Ano {kpis['payback']}",
                      annotation_font_color=CORES["gold"])
    fig.update_layout(**PLOT_LAYOUT, height=320,
                      title=dict(text="Renúncia vs. Retorno Indireto (R$ Bilhões)",
                                 font=dict(color=CORES["gold"], size=13)))
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Acumulados — Payback do Tesouro")
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=df["Ano"], y=df["Renuncia_Acum_Bi"], name="Renúncia acum.",
            line=dict(color=CORES["red"], width=2, dash="dot"),
        ))
        fig2.add_trace(go.Scatter(
            x=df["Ano"], y=df["Retorno_Acum_Bi"], name="Retorno acum.",
            line=dict(color=CORES["green"], width=2),
        ))
        if kpis["payback"]:
            fig2.add_vline(x=kpis["payback"], line_dash="dash", line_color=CORES["gold"],
                           annotation_text=f"Payback", annotation_font_color=CORES["gold"])
        fig2.update_layout(**PLOT_LAYOUT, height=260)
        st.plotly_chart(fig2, use_container_width=True)

    with c2:
        st.subheader("Saldo Líquido Anual (R$ Bi)")
        colors = [CORES["green"] if v >= 0 else CORES["red"] for v in df["Saldo_Liquido_Bi"]]
        fig3 = go.Figure(go.Bar(
            x=df["Ano"], y=df["Saldo_Liquido_Bi"],
            marker_color=colors, name="Saldo Líquido",
        ))
        fig3.add_hline(y=0, line_color=CORES["muted"], line_width=1)
        fig3.update_layout(**PLOT_LAYOUT, height=260)
        st.plotly_chart(fig3, use_container_width=True)

    st.info(f"""
    **Premissas-chave do modelo:**
    &nbsp;&nbsp;• Lag de maturação P&D → PTF: **{LAG_MATURACAO} anos** (consenso literatura de inovação)
    &nbsp;&nbsp;• Taxa de sucesso tecnológico: **{PROB_SUCESSO*100:.0f}%** (ajuste para projetos fracassados)
    &nbsp;&nbsp;• Depreciação do estoque de conhecimento: **{TAXA_DEPRECIACAO*100:.0f}%/ano** (obsolescência)
    &nbsp;&nbsp;• β PTF/P&D configurado: **{beta_ptf:.3f}** (range OCDE/BM para emergentes: 0,05–0,08)
    """)


# ────────────────────────────────────────────
# TAB 1 — PTF & P&D
# ────────────────────────────────────────────
with tabs[1]:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Dinâmica do Estoque de Conhecimento")
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(
            x=df["Ano"], y=df["PD_Total_MM"], name="P&D Total (R$MM)",
            line=dict(color=CORES["cyan"], width=2),
        ), secondary_y=False)
        fig.add_trace(go.Scatter(
            x=df["Ano"], y=df["PD_Adicional_MM"], name="P&D Adicional",
            line=dict(color=CORES["gold"], width=1.5, dash="dash"),
        ), secondary_y=False)
        fig.add_trace(go.Scatter(
            x=df["Ano"], y=df["Ganho_Prod_Pct"], name="Ganho PTF (%)",
            line=dict(color=CORES["green"], width=2),
        ), secondary_y=True)
        fig.update_layout(**PLOT_LAYOUT, height=300)
        fig.update_yaxes(title_text="R$ MM", secondary_y=False,
                         gridcolor=CORES["border"], color=CORES["muted"])
        fig.update_yaxes(title_text="Ganho PTF (%)", secondary_y=True, color=CORES["muted"])
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Receita e Fator F por Ano")
        fig2 = make_subplots(specs=[[{"secondary_y": True}]])
        fig2.add_trace(go.Scatter(
            x=df["Ano"], y=df["Receita_MM"], name="Receita (R$MM)",
            line=dict(color=CORES["cyan"], width=2),
        ), secondary_y=False)
        fig2.add_trace(go.Scatter(
            x=df["Ano"], y=df["Fator_F"], name="Fator F",
            line=dict(color=CORES["gold"], width=2),
        ), secondary_y=True)
        fig2.add_hline(y=78, line_dash="dot", line_color=CORES["muted"],
                       annotation_text="Threshold phasing-out R$78MM",
                       annotation_font_color=CORES["muted"])
        fig2.update_layout(**PLOT_LAYOUT, height=300)
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown(f"""
    <div style='background:{CORES["card"]};border:1px solid {CORES["border"]};border-left:3px solid {CORES["gold"]};
    border-radius:6px;padding:16px 20px;font-family:DM Mono,monospace;font-size:12px;color:{CORES["muted"]};line-height:2'>
    <span style='color:{CORES["gold"]};font-weight:600'>Função de Transmissão P&D → PTF</span><br>
    ΔPTFₜ = β · Δ(P&D_privado / PIB) &nbsp;|&nbsp;
    β = {beta_ptf:.3f} (range OCDE: 0,05–0,08) &nbsp;|&nbsp;
    Depreciação: {TAXA_DEPRECIACAO*100:.0f}%/ano &nbsp;|&nbsp;
    Lag: {LAG_MATURACAO} anos &nbsp;|&nbsp;
    Taxa de sucesso: {PROB_SUCESSO*100:.0f}%<br>
    <span style='color:{CORES["muted"]}'>Base Tributária = (Receita × 0,32) − (1,25 × P&D × F) &nbsp;|&nbsp;
    Fator F: {f_teto} (≤R$3,24MM) → {f_medio} (≤R$78MM) → phasing-out linear → 1,0 (≥R$200MM)</span>
    </div>
    """, unsafe_allow_html=True)


# ────────────────────────────────────────────
# TAB 2 — FIRMAS & LRF
# ────────────────────────────────────────────
with tabs[2]:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Curva de Difusão — Adesão das Firmas (Sigmoide)")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["Ano"], y=df["Firmas_Aderentes"], name="Firmas aderentes",
            fill="tozeroy", fillcolor=f"rgba(43,191,206,0.12)",
            line=dict(color=CORES["cyan"], width=2),
        ))
        fig.add_hline(y=n_firmas, line_dash="dot", line_color=CORES["gold"],
                      annotation_text=f"Universo total: {n_firmas:,}",
                      annotation_font_color=CORES["gold"])
        fig.update_layout(**PLOT_LAYOUT, height=300,
                          yaxis_title="Firmas", xaxis_title="Ano")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Renúncia Anual vs. Teto LRF")
        colors_lrf = [CORES["cyan"] if r else CORES["red"] for r in df["LRF_OK"]]
        fig2 = go.Figure(go.Bar(
            x=df["Ano"], y=df["Renuncia_Bi"], marker_color=colors_lrf,
            name="Renúncia (R$Bi)",
        ))
        fig2.add_hline(y=teto_lrf, line_dash="dash", line_color=CORES["amber"],
                       annotation_text=f"Teto LRF: R$ {teto_lrf}Bi",
                       annotation_font_color=CORES["amber"])
        fig2.update_layout(**PLOT_LAYOUT, height=300,
                           yaxis_title="R$ Bilhões", xaxis_title="Ano")
        st.plotly_chart(fig2, use_container_width=True)

    if kpis["violacoes"] > 0:
        anos_violacao = df[df["LRF_OK"] == False]["Ano"].tolist()
        st.error(f"""
        ⚠️ **{kpis['violacoes']} ano(s) violam o teto LRF de R$ {teto_lrf}Bi: Anos {anos_violacao}**

        Acione a regra de ajuste paramétrico (Art. 7 da proposta) na seguinte ordem de preferência:
        1. Redução do multiplicador M (atualmente {mult:.2f})
        2. Recalibragem dos pesos do Fator F
        3. Revisão dos limites de intensidade tecnológica elegíveis
        """)
    else:
        st.success(f"✅ Todos os {horizonte} anos dentro do teto LRF de R$ {teto_lrf}Bi — regime fiscalmente sustentável com os parâmetros atuais.")


# ────────────────────────────────────────────
# TAB 3 — SENSIBILIDADE
# ────────────────────────────────────────────
with tabs[3]:
    with st.spinner("Calculando matriz 5×5..."):
        df_sens = matriz_sensibilidade(params)

    st.subheader("Matriz de Sensibilidade — ROI Líquido (%) por (ε × M)")

    # Pivot para heatmap
    pivot_roi = df_sens.pivot(index="Elasticidade", columns="Mult_M", values="ROI_Pct")
    pivot_lrf = df_sens.pivot(index="Elasticidade", columns="Mult_M", values="LRF_OK")

    fig = go.Figure(go.Heatmap(
        z    = pivot_roi.values,
        x    = [f"M={v}" for v in pivot_roi.columns],
        y    = [f"ε={v}" for v in pivot_roi.index],
        text = np.where(
            pivot_lrf.values,
            [[f"{v:.1f}%" for v in row] for row in pivot_roi.values],
            [[f"{v:.1f}%\n⚠LRF" for v in row] for row in pivot_roi.values],
        ),
        texttemplate = "%{text}",
        colorscale   = [
            [0.0, CORES["red"]],
            [0.4, CORES["amber"]],
            [0.7, "#2a6e4e"],
            [1.0, CORES["green"]],
        ],
        showscale = True,
        colorbar  = dict(
            title=dict(text="ROI %", font=dict(color=CORES["muted"])),
            tickfont=dict(color=CORES["muted"]),
        ),
        hoverongaps = False,
    ))
    fig.update_layout(**PLOT_LAYOUT, height=340,
                      xaxis=dict(side="top", gridcolor="transparent"),
                      yaxis=dict(gridcolor="transparent"),
                      title=dict(text="ROI acumulado (%) — Retorno/Renúncia−1 | ⚠ = violação LRF",
                                 font=dict(color=CORES["gold"], size=13)))
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("ROI vs. Elasticidade (M atual)")
        sub = df_sens[df_sens["Mult_M"] == mult].sort_values("Elasticidade")
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=sub["Elasticidade"], y=sub["ROI_Pct"],
            mode="lines+markers", line=dict(color=CORES["gold"], width=2),
            marker=dict(color=[CORES["green"] if r else CORES["red"] for r in sub["LRF_OK"]], size=9),
            name="ROI (%)",
        ))
        fig2.add_hline(y=0, line_dash="dash", line_color=CORES["muted"])
        fig2.update_layout(**PLOT_LAYOUT, height=260,
                           xaxis_title="Elasticidade ε", yaxis_title="ROI (%)")
        st.plotly_chart(fig2, use_container_width=True)

    with c2:
        st.subheader("Renúncia Total vs. Multiplicador M (ε atual)")
        sub2 = df_sens[df_sens["Elasticidade"] == elasticidade].sort_values("Mult_M")
        fig3 = go.Figure()
        fig3.add_trace(go.Bar(
            x=[f"M={v}" for v in sub2["Mult_M"]], y=sub2["Renuncia_Total"],
            marker_color=[CORES["cyan"] if r else CORES["red"] for r in sub2["LRF_OK"]],
            name="Renúncia Total (R$Bi)",
        ))
        fig3.update_layout(**PLOT_LAYOUT, height=260, yaxis_title="R$ Bi")
        st.plotly_chart(fig3, use_container_width=True)

    with st.expander("📐 Fontes e Premissas Metodológicas"):
        premissas = {
            "Elasticidade P&D": "Kannebley, Shimada & De Negri (2016) — range −0,6 a −2,0",
            "β PTF/P&D": "OCDE / Banco Mundial para economias emergentes — 0,05–0,08",
            "Lag de maturação": "3 anos (consenso literatura de inovação)",
            "Depreciação do estoque": "15%/ano (obsolescência tecnológica)",
            "Taxa de sucesso P&D": "70% (ajuste para projetos fracassados)",
            "Adesão de firmas": "Sigmoide — calibrada no histórico da Lei do Bem",
            "Base tributável": "Receita × 32% (lucro presumido analítico)",
            "Alíquota combinada": "34% (IRPJ 25% + CSLL 9%)",
            "Fator F — phasing-out": "Decaimento linear −0,012/R$1MM entre R$78M e R$200M",
            "Retorno indireto": "PTF → margem operacional → lucro tributável → arrecadação",
            "Multiplicador P&D/ERIS": "Referência: HMRC UK R&D Tax Relief; Hall & Van Reenen (2000)",
        }
        df_prem = pd.DataFrame(list(premissas.items()), columns=["Parâmetro", "Fonte / Referência"])
        st.dataframe(df_prem, use_container_width=True, hide_index=True)


# ────────────────────────────────────────────
# TAB 4 — DADOS
# ────────────────────────────────────────────
with tabs[4]:
    st.subheader("Saída Analítica Completa — Todos os Anos")

    display_cols = {
        "Ano":              "Ano",
        "Receita_MM":       "Receita (R$MM)",
        "Fator_F":          "Fator F",
        "PD_Total_MM":      "P&D Total (MM)",
        "PD_Adicional_MM":  "P&D Adicional",
        "Ganho_Prod_Pct":   "Ganho PTF (%)",
        "Firmas_Aderentes": "Firmas Aderentes",
        "Renuncia_Bi":      "Renúncia (R$Bi)",
        "Retorno_Bi":       "Retorno (R$Bi)",
        "Saldo_Liquido_Bi": "Saldo Líq. (Bi)",
        "Renuncia_Acum_Bi": "Renúncia Acum.",
        "Retorno_Acum_Bi":  "Retorno Acum.",
        "ROI_Acum_Pct":     "ROI Acum. (%)",
        "LRF_OK":           "LRF ✓",
        "Status_Gatilho":   "Gatilho",
    }
    df_display = df[display_cols.keys()].rename(columns=display_cols)

    def color_row(row):
        styles = [""] * len(row)
        idx_saldo = list(display_cols.values()).index("Saldo Líq. (Bi)")
        idx_lrf   = list(display_cols.values()).index("LRF ✓")
        idx_gate  = list(display_cols.values()).index("Gatilho")
        if row.iloc[idx_saldo] < 0:
            styles[idx_saldo] = "color: #E05252"
        else:
            styles[idx_saldo] = "color: #3EC97B"
        styles[idx_lrf]  = "color: #3EC97B" if row.iloc[idx_lrf] else "color: #E05252"
        styles[idx_gate] = "color: #3EC97B" if row.iloc[idx_gate] == "Ativo" else "color: #E8A020"
        return styles

    st.dataframe(
        df_display.style.apply(color_row, axis=1).format(precision=3),
        use_container_width=True,
        height=400,
    )

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Exportar CSV completo",
        data=csv, file_name="reti_simulacao.csv", mime="text/csv",
    )


# ────────────────────────────────────────────
# TAB 5 — ANÁLISE SPE/MF
# ────────────────────────────────────────────
with tabs[5]:
    st.subheader("🏛️ Análise Estratégica — Perspectiva SPE/MF")

    st.markdown(f"""
    <div style='background:{CORES["card"]};border:1px solid {CORES["border"]};
    border-left:4px solid {CORES["gold"]};border-radius:6px;padding:16px 20px;
    margin-bottom:20px;font-size:12px;color:{CORES["muted"]};font-family:DM Mono,monospace;line-height:1.9'>
    <span style='color:{CORES["gold"]};font-weight:700;font-size:13px'>
    O que a Fazenda olha primeiro
    </span><br>
    Qualquer proposta de gasto tributário chega na SPE/MF sob quatro lentes simultâneas:
    (1) custo fiscal líquido e trajetória, (2) conformidade com a LRF (Art. 14),
    (3) comparabilidade com instrumentos existentes (Lei do Bem, Lei de Informática, Rota 2030)
    e (4) risco de captura/arbitragem. O RETI precisa vencer as quatro.
    </div>
    """, unsafe_allow_html=True)

    # ── Cenários nomeados
    st.markdown(f"#### 🎯 Cenários Pré-Configurados por Palatabilidade Fiscal")

    cenarios = {
        "🟢 Conservador (mínima resistência)": dict(
            mult=1.10, elasticidade=-0.9, limite_compensacao=0.30,
            teto_lrf=1.5, n_firmas=2000,
            descricao=(
                "Multiplicador 1,10 — abaixo de qualquer referência histórica controvertida. "
                "Limite de compensação de 30% minimiza o impacto no caixa de curto prazo. "
                "Universo restrito (2.000 firmas) facilita auditoria e controla o risco de escala. "
                "**Argumento para a Fazenda:** custo previsível, auditável e menor que qualquer "
                "linha da Lei de Informática. Payback tende a ser mais longo, mas o risco fiscal é baixo."
            ),
        ),
        "🟡 Moderado (ponto de equilíbrio)": dict(
            mult=1.25, elasticidade=-1.27, limite_compensacao=0.40,
            teto_lrf=2.2, n_firmas=4500,
            descricao=(
                "Parâmetros centrais da proposta. Multiplicador de 1,25 é defensável pela "
                "literatura brasileira (Kannebley et al., 2016: elasticidade −1,27). "
                "Limite de 40% equilibra incentivo real sem comprimir a arrecadação líquida. "
                "**Argumento para a Fazenda:** melhor razão custo/adicionalidade da série, "
                "reproduz o desenho técnico da SPE com máxima aderência ao TR. "
                "É o cenário que mais se sustenta em nota técnica."
            ),
        ),
        "🟠 Agressivo (alto ROI, alto risco político)": dict(
            mult=1.40, elasticidade=-1.6, limite_compensacao=0.50,
            teto_lrf=3.0, n_firmas=4500,
            descricao=(
                "Multiplicador 1,40 e limite de 50% maximizam o incentivo e o ROI projetado, "
                "mas aproximam o custo fiscal do threshold da Lei de Informática — o que pode "
                "acionar resistência política da indústria de TI estabelecida. "
                "**Argumento para a Fazenda:** só sustentável se acompanhado de cláusula de "
                "sunset automático (ex: revisão obrigatória em 5 anos) e sistema de risk scoring "
                "integrado à SERPRO/RFB desde o primeiro ano."
            ),
        ),
    }

    for nome, cfg in cenarios.items():
        p_cen = {**params, **{k: v for k, v in cfg.items() if k != "descricao"}}
        df_cen = motor_reti(p_cen)
        k_cen  = calcular_kpis(df_cen, cfg["teto_lrf"])
        lrf_ok = k_cen["violacoes"] == 0

        bg_cor = {"🟢": "#0d2b1a", "🟡": "#2b2400", "🟠": "#2b1600"}
        brd_cor= {"🟢": CORES["green"], "🟡": CORES["amber"], "🟠": CORES["red"]}
        emoji  = nome[0:2].strip()

        with st.expander(f"{nome}  |  ROI: {k_cen['roi']:+.1f}%  |  "
                         f"Custo: R$ {k_cen['total_ren']:.1f}Bi  |  "
                         f"Payback: {'Ano '+str(k_cen['payback']) if k_cen['payback'] else '>horizonte'}  |  "
                         f"LRF: {'✅' if lrf_ok else '⚠️'}"):
            col_desc, col_chart = st.columns([2, 3])
            with col_desc:
                st.markdown(f"""
                <div style='background:{bg_cor.get(emoji, CORES["card"])};
                border:1px solid {brd_cor.get(emoji, CORES["border"])};
                border-radius:6px;padding:14px 16px;font-size:12px;
                color:{CORES["text"]};line-height:1.8;font-family:DM Mono,monospace'>
                {cfg["descricao"]}
                </div>
                """, unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)
                m1, m2 = st.columns(2)
                m1.metric("Renúncia Total",  f"R$ {k_cen['total_ren']:.2f}Bi")
                m2.metric("Retorno Total",   f"R$ {k_cen['total_ret']:.2f}Bi")
                m3, m4 = st.columns(2)
                m3.metric("ROI Acumulado",   f"{k_cen['roi']:+.1f}%")
                m4.metric("Pico Anual",      f"R$ {k_cen['pico_ren']:.2f}Bi")

            with col_chart:
                fig_cen = go.Figure()
                fig_cen.add_trace(go.Scatter(
                    x=df_cen["Ano"], y=df_cen["Renuncia_Bi"],
                    name="Renúncia", fill="tozeroy",
                    fillcolor="rgba(224,82,82,0.12)",
                    line=dict(color=CORES["red"], width=1.5),
                ))
                fig_cen.add_trace(go.Scatter(
                    x=df_cen["Ano"], y=df_cen["Retorno_Bi"],
                    name="Retorno", fill="tonexty",
                    fillcolor="rgba(62,201,123,0.10)",
                    line=dict(color=CORES["green"], width=1.5),
                ))
                fig_cen.add_hline(y=cfg["teto_lrf"], line_dash="dot",
                                   line_color=CORES["amber"],
                                   annotation_text=f"Teto LRF: R${cfg['teto_lrf']}Bi",
                                   annotation_font_color=CORES["amber"])
                fig_cen.update_layout(**PLOT_LAYOUT, height=220,
                                      showlegend=True,
                                      margin=dict(l=40, r=10, t=20, b=30))
                st.plotly_chart(fig_cen, use_container_width=True)

    st.divider()

    # ── Hierarquia de Compensação
    st.markdown("#### 💰 Hierarquia de Compensação Fiscal (Art. 7 da Proposta)")

    compensacoes = {
        "Taxação de Bets (GGR 12%→15%)":         850,
        "Agenda CNI / Reforma Administrativa":    600,
        "Corte Gastos Tributários Ineficientes":  450,
        "Outras fontes (a mapear com equipe)":    300,
    }
    custo_anual_estimado = kpis["pico_ren"] * 1000  # em R$ MM
    total_comp  = sum(compensacoes.values())

    fig_comp = go.Figure(go.Bar(
        x=list(compensacoes.keys()),
        y=list(compensacoes.values()),
        marker_color=[CORES["gold"], CORES["cyan"], CORES["green"], CORES["amber"]],
        text=[f"R$ {v}MM" for v in compensacoes.values()],
        textposition="auto",
    ))
    fig_comp.add_hline(
        y=custo_anual_estimado,
        line_dash="dash", line_color=CORES["red"],
        annotation_text=f"Custo anual estimado: R$ {custo_anual_estimado:.0f}MM",
        annotation_font_color=CORES["red"],
    )
    fig_comp.update_layout(**PLOT_LAYOUT, height=300,
                           title=dict(text="Capacidade de Compensação (R$ Milhões/ano)",
                                      font=dict(color=CORES["gold"], size=13)),
                           xaxis=dict(tickfont=dict(size=10)),
                           yaxis_title="R$ Milhões")
    st.plotly_chart(fig_comp, use_container_width=True)

    cobertura = (total_comp / custo_anual_estimado * 100) if custo_anual_estimado > 0 else 0
    if cobertura >= 100:
        st.success(f"✅ Cobertura total: **R$ {total_comp}MM** cobre **{cobertura:.0f}%** do custo anual estimado de R$ {custo_anual_estimado:.0f}MM — LRF sustentável.")
    else:
        st.warning(f"⚠️ Cobertura parcial: R$ {total_comp}MM cobre {cobertura:.0f}% do custo anual estimado. Diferença de R$ {custo_anual_estimado-total_comp:.0f}MM precisa de fonte adicional.")

    st.divider()

    # ── Comparativo com instrumentos existentes
    st.markdown("#### 📊 Comparativo com Instrumentos Vigentes")

    comp_df = pd.DataFrame([
        {"Instrumento": "Lei do Bem (vigente)",      "Cobertura Estimada": "~5% empresas",
         "Multiplicador": "1,60–1,80", "Base": "Lucro Real",
         "Risco Arbitragem": "Médio", "Custo Fiscal/ano": "~R$3,5Bi"},
        {"Instrumento": "Lei de Informática",        "Cobertura Estimada": "Setor TIC",
         "Multiplicador": "N/A (isenção)",           "Base": "Faturamento",
         "Risco Arbitragem": "Alto",  "Custo Fiscal/ano": "~R$4,0Bi"},
        {"Instrumento": "Rota 2030",                 "Cobertura Estimada": "Automotivo",
         "Multiplicador": "N/A",                     "Base": "Faturamento",
         "Risco Arbitragem": "Baixo", "Custo Fiscal/ano": "~R$1,5Bi"},
        {"Instrumento": f"RETI (cenário moderado)",  "Cobertura Estimada": "~95% adicional",
         "Multiplicador": "1,25",     "Base": "Base presumida",
         "Risco Arbitragem": "Baixo (risk scoring)", "Custo Fiscal/ano": f"~R$ {kpis['pico_ren']:.1f}Bi"},
    ])
    st.dataframe(comp_df, use_container_width=True, hide_index=True)

    st.markdown(f"""
    <div style='background:{CORES["card"]};border:1px solid {CORES["border"]};
    border-left:4px solid {CORES["cyan"]};border-radius:6px;padding:16px 20px;
    margin-top:16px;font-size:12px;color:{CORES["muted"]};font-family:DM Mono,monospace;line-height:2'>
    <span style='color:{CORES["cyan"]};font-weight:700'>Nota para negociação:</span>
    O multiplicador de 1,25 do RETI é <b style='color:{CORES["text"]}'>intencionalmente inferior</b>
    ao da Lei do Bem (1,60–1,80), o que facilita a defesa técnica no CMAP e no TCU.
    O argumento central não é generosidade do incentivo, mas <b style='color:{CORES["text"]}'>
    amplitude de cobertura</b>: o RETI atinge o universo que a Lei do Bem
    estruturalmente exclui, sem competir com ela.
    A base presumida elimina o risco de manipulação de lucro fiscal para fins de elegibilidade —
    o principal vetor de arbitragem da Lei do Bem.
    </div>
    """, unsafe_allow_html=True)

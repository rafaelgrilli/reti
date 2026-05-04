import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

# ─────────────────────────────────────────────
# CONFIGURAÇÕES E GLOSSÁRIO
# ─────────────────────────────────────────────
st.set_page_config(page_title="RETI — Simulador de Apoio à Decisão", layout="wide")

HELP_TEXT = {
    "rec": "Receita Bruta Anual (R$ MM). Define o enquadramento nas faixas do Fator F.",
    "i": "Percentual da receita investido em P&D. Essencial para o gatilho RETI-SME.",
    "g": "Taxa de crescimento anual. Se < 10% após o Ano 3, suspende o uso de créditos.",
    "e": "Elasticidade-custo (padrão -1.27). Mede quanto o investimento privado sobe ao reduzir o custo tributário.",
    "m": "Multiplicador sobre o gasto de P&D. É a alavanca central do incentivo fiscal.",
    "n": "Número total de empresas inovadoras estimadas no universo do programa.",
    "teto": "Limite de renúncia anual estabelecido para acionar o Safe-Stop (R$ 2,2 Bi)."
}

# ─────────────────────────────────────────────
# FUNÇÕES DE CÁLCULO (O "MOTOR" DO RETI)
# ─────────────────────────────────────────────

def fator_f_oficial(r):
    """Implementa a tabela progressiva do Item 3.2 do documento executivo."""
    if r <= 3.24: return 3.5
    elif r <= 78: return 2.5
    else: return max(1.0, 2.5 - 0.012*(r-78))

def imposto_referencia(rec):
    """Calcula IRPJ/CSLL base no Lucro Presumido (32% de base, 34% de alíquota)."""
    return (rec * 0.32) * 0.34

def simular_unidade(rec0, i, g, e, m, anos, sem_reti=False):
    rec = rec0 * 1e6
    fila_creditos = [] # Controle FIFO para prescrição de 5 anos
    resultados = []

    for t in range(1, anos+1):
        rec_anterior = rec
        rec *= (1 + g)
        crescimento_obtido = (rec / rec_anterior) - 1
        base_pd_natural = rec * i
        
        if sem_reti:
            total_pd = base_pd_natural
            imp = imposto_referencia(rec)
            inc, f, uso, est = 0, 0, 0, 0
        else:
            f = fator_f_oficial(rec/1e6)
            custo_marginal = m * f * 0.34
            # Adicionalidade baseada na elasticidade
            investimento_adicional = max(0, base_pd_natural * abs(e) * custo_marginal)
            total_pd = base_pd_natural + investimento_adicional

            # Geração de crédito e controle de prescrição (Item 6.4)
            novo_credito = m * total_pd * f * 0.34
            fila_creditos.append([novo_credito, t + 5])
            fila_creditos = [c for c in fila_creditos if c[1] > t] # Remove expirados

            # Gatilho de Performance (Item 6.3)
            pode_compensar = True
            if t > 3 and crescimento_obtido < 0.10:
                pode_compensar = False

            imp_ref = imposto_referencia(rec)
            limite_anual = imp_ref * 0.5
            uso = 0

            if pode_compensar:
                saldo_total = sum(c[0] for c in fila_creditos)
                uso = min(saldo_total, limite_anual)
                # Abate FIFO do estoque
                sobra_para_abater = uso
                for c in fila_creditos:
                    if sobra_para_abater <= 0: break
                    abatimento = min(c[0], sobra_para_abater)
                    c[0] -= abatimento
                    sobra_para_abater -= abatimento

            # Cap de 25% (Item 6.1)
            imp = max(imp_ref * 0.25, imp_ref - uso)
            inc = imp_ref - imp
            est = sum(c[0] for c in fila_creditos)

        # Cálculo do retorno socioeconômico (Externalidade positiva conforme Word)
        retorno_estimado = (total_pd - base_pd_natural) * 0.18 if not sem_reti else 0

        resultados.append([
            t, rec/1e6, total_pd/1e6, imp/1e6, inc/1e6,
            retorno_estimado/1e6, f, est/1e6, crescimento_obtido
        ])

    return pd.DataFrame(resultados, columns=[
        "Ano","Receita","P&D","Imposto","Incentivo",
        "Retorno","Fator","Estoque Crédito","Crescimento"
    ])

def simular_macro_detalhado(n, rec_m, i, g_m, e, m_base, anos):
    rows = []
    m_dinamico = m_base
    teto_fiscal = 2.2 # R$ Bilhões

    for t in range(1, anos+1):
        n_atividades = int(n * (1.03**t)) # Crescimento vegetativo de firmas
        df_unidade = simular_unidade(rec_m, i, g_m, e, m_dinamico, t)
        last = df_unidade.iloc[-1]
        
        renuncia_bi = (last["Incentivo"] * n_atividades) / 1000
        
        # Mecanismo Safe-Stop Proporcional (Item 5.3) - Corrigido para ajuste suave
        if renuncia_bi > teto_fiscal:
            excesso = (renuncia_bi / teto_fiscal)
            m_dinamico = max(1.0, m_dinamico / (1 + (excesso - 1) * 0.4))

        rows.append([
            t, n_atividades, renuncia_bi, 
            (last["P&D"] * n_atividades)/1000, 
            (last["Retorno"] * n_atividades)/1000, 
            (last["Estoque Crédito"] * n_atividades)/1000,
            m_dinamico
        ])

    df = pd.DataFrame(rows, columns=["Ano","Firmas","Renúncia","P&D","Retorno","Estoque","M_Efetivo"])
    df["Renúncia Acum"] = df["Renúncia"].cumsum()
    df["Retorno Acum"] = df["Retorno"].cumsum()
    return df

# ─────────────────────────────────────────────
# INTERFACE STREAMLIT
# ─────────────────────────────────────────────

with st.sidebar:
    st.header("📋 Parâmetros da Firma")
    s_rec = st.slider("Receita Inicial (R$ MM)", 1.0, 100.0, 15.0, help=HELP_TEXT["rec"])
    s_i = st.slider("Intensidade P&D (%)", 1.0, 20.0, 7.0, help=HELP_TEXT["i"])/100
    s_g = st.slider("Crescimento Anual (%)", 0.0, 25.0, 12.0, help=HELP_TEXT["g"])/100

    st.header("🌍 Parâmetros Macro")
    s_n = st.number_input("Firmas Elegíveis", 1000, 10000, 4500, help=HELP_TEXT["n"])
    s_rec_m = st.slider("Receita Média do Universo", 1.0, 50.0, 12.0)
    s_g_m = st.slider("Crescimento do Universo (%)", 0.0, 15.0, 8.0)/100

    st.header("⚖️ Política e Governança")
    s_e = st.slider("Elasticidade-Custo", -2.0, -0.1, -1.27, help=HELP_TEXT["e"])
    s_m = st.slider("Multiplicador (M)", 1.0, 1.6, 1.25, help=HELP_TEXT["m"])
    s_anos = st.slider("Horizonte de Simulação", 5, 15, 10)

# EXECUÇÃO
df_firma_com = simular_unidade(s_rec, s_i, s_g, s_e, s_m, s_anos)
df_firma_sem = simular_unidade(s_rec, s_i, s_g, s_e, s_m, s_anos, sem_reti=True)
df_macro = simular_macro_detalhado(s_n, s_rec_m, s_i, s_g_m, s_e, s_m, s_anos)

# KPIs
pd_total_adicional = df_firma_com["P&D"].sum() - df_firma_sem["P&D"].sum()
custo_total_incentivo = df_firma_com["Incentivo"].sum()
roi_global = pd_total_adicional / custo_total_incentivo if custo_total_incentivo > 0 else 0

st.title("🚀 RETI: Dashboard de Suporte à Decisão Estratégica")

# PAINEL DE RISCOS
c1, c2, c3, c4 = st.columns(4)
c1.metric("ROI (Adicionalidade)", f"{roi_global:.2f}x", delta="Eficiente" if roi_global > 1 else "Sub-ótimo")
c2.metric("Incentivo Acumulado (Firma)", f"R$ {custo_total_incentivo:.1f}M")
c3.metric("Estoque de Crédito Final", f"R$ {df_firma_com['Estoque Crédito'].iloc[-1]:.1f}M")
c4.metric("Status Safe-Stop", "Ativo" if df_macro["M_Efetivo"].iloc[-1] < s_m else "Estável")

st.divider()

t1, t2, t3, t4 = st.tabs(["📈 Análise da Firma", "🏛️ Impacto Fiscal Macro", "🔍 Sensibilidade", "📋 Dados Brutos"])

with t1:
    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        fig_pd = go.Figure()
        fig_pd.add_trace(go.Scatter(x=df_firma_com["Ano"], y=df_firma_com["P&D"], name="Com RETI", line=dict(width=4, color="blue")))
        fig_pd.add_trace(go.Scatter(x=df_firma_sem["Ano"], y=df_firma_sem["P&D"], name="Sem RETI", line=dict(dash="dot", color="red")))
        fig_pd.update_layout(title="Indução de Investimento em P&D (R$ MM)", hovermode="x unified")
        st.plotly_chart(fig_pd, use_container_width=True)
    with col_f2:
        st.write("**Composição do Incentivo**")
        fig_inc = px.bar(df_firma_com, x="Ano", y=["Incentivo", "Estoque Crédito"], barmode="group", color_discrete_sequence=["#00CC96", "#AB63FA"])
        st.plotly_chart(fig_inc, use_container_width=True)

with t2:
    st.subheader("Controle Orçamentário Nacional")
    fig_macro = go.Figure()
    fig_macro.add_trace(go.Bar(x=df_macro["Ano"], y=df_macro["Renúncia"], name="Renúncia Total (Bi)"))
    fig_macro.add_trace(go.Scatter(x=df_macro["Ano"], y=df_macro["M_Efetivo"], name="Multiplicador (M)", yaxis="y2", line=dict(color="orange", width=3)))
    fig_macro.update_layout(title="Equilíbrio Fiscal vs Multiplicador", 
                           yaxis_title="R$ Bilhões", 
                           yaxis2=dict(title="Valor de M", overlaying="y", side="right", range=[0.9, 1.7]))
    st.plotly_chart(fig_macro, use_container_width=True)
    st.info(f"O retorno socioeconômico acumulado (externalidade) é estimado em R$ {df_macro['Retorno Acum'].iloc[-1]:.2f} Bi.")

with t3:
    st.subheader("Análise de Estresse de Elasticidade")
    curva_e = []
    for test_e in np.linspace(-0.2, -2.0, 10):
        d_c = simular_unidade(s_rec, s_i, s_g, test_e, s_m, s_anos)
        d_s = simular_unidade(s_rec, s_i, s_g, test_e, s_m, s_anos, sem_reti=True)
        r = (d_c["P&D"].sum() - d_s["P&D"].sum()) / d_c["Incentivo"].sum() if d_c["Incentivo"].sum() > 0 else 0
        curva_e.append([test_e, r])
    fig_e = px.line(pd.DataFrame(curva_e, columns=["Elasticidade", "ROI"]), x="Elasticidade", y="ROI", markers=True)
    fig_e.add_hline(y=1.0, line_dash="dash", line_color="red", annotation_text="Ponto de Equilíbrio")
    st.plotly_chart(fig_e, use_container_width=True)

with t4:
    st.dataframe(df_firma_com.style.format(precision=2))

st.caption("Simulador RETI v2.0 | Regras de Prescrição (5 anos), Gatilho de Crescimento (10%) e Safe-Stop Proporcional (Teto R$ 2.2B).")

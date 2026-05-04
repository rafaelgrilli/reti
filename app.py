import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

# ─────────────────────────────────────────────
# CONFIGURAÇÕES E GLOSSÁRIO TÉCNICO
# ─────────────────────────────────────────────
st.set_page_config(page_title="RETI — Suporte à Decisão", layout="wide")

HELP_TEXT = {
    "rec": "Receita Bruta Anual (R$ MM). Define o enquadramento nas faixas do Fator F.",
    "i": "Percentual da receita investido em P&D. Essencial para o gatilho RETI-SME.",
    "g": "Taxa de crescimento anual. Se < 10% após o Ano 3, suspende o uso de créditos.",
    "e": "Elasticidade-custo (padrão -1.27). Mede a resposta do investimento privado ao incentivo.",
    "m": "Multiplicador sobre o gasto de P&D. É a alavanca central do incentivo.",
    "teto": "Limite de renúncia anual estabelecido para acionar o Safe-Stop (R$ 2,2 Bi)."
}

# ─────────────────────────────────────────────
# MOTOR DE CÁLCULO (RETI V3.0)
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
            total_pd, imp, inc, f, uso, est = base_pd_natural, imposto_referencia(rec), 0, 0, 0, 0
        else:
            f = fator_f_oficial(rec/1e6)
            custo_marginal = m * f * 0.34
            # Adicionalidade baseada na elasticidade de -1.27
            investimento_adicional = max(0, base_pd_natural * abs(e) * custo_marginal)
            total_pd = base_pd_natural + investimento_adicional

            # Geração de crédito e controle de prescrição (Item 6.4)
            novo_credito = m * total_pd * f * 0.34
            fila_creditos.append([novo_credito, t + 5])
            fila_creditos = [c for c in fila_creditos if c[1] > t] 

            # Gatilho de Performance (Item 6.3)
            pode_compensar = not (t > 3 and crescimento_obtido < 0.10)
            
            imp_ref = imposto_referencia(rec)
            limite_anual = imp_ref * 0.5
            uso = 0

            if pode_compensar:
                saldo_total = sum(c[0] for c in fila_creditos)
                uso = min(saldo_total, limite_anual)
                # Abate FIFO do estoque
                sobra = uso
                for c in fila_creditos:
                    if sobra <= 0: break
                    abatimento = min(c[0], sobra)
                    c[0] -= abatimento
                    sobra -= abatimento

            # Cap de 25% (Item 6.1)
            imp = max(imp_ref * 0.25, imp_ref - uso)
            inc = imp_ref - imp
            est = sum(c[0] for c in fila_creditos)

        # Retorno socioeconômico indireto
        retorno = (total_pd - base_pd_natural) * 0.18 if not sem_reti else 0

        resultados.append([t, rec/1e6, total_pd/1e6, imp/1e6, inc/1e6, retorno/1e6, f, est/1e6])

    return pd.DataFrame(resultados, columns=["Ano","Receita","P&D","Imposto","Incentivo","Retorno","Fator","Estoque"])

def simular_macro_calibrado(n, rec_m, i, g_m, e, m_base, anos, teto):
    rows = []
    m_dinamico = m_base
    for t in range(1, anos+1):
        n_at = int(n * (1.03**t))
        df_u = simular_unidade(rec_m, i, g_m, e, m_dinamico, t)
        l = df_u.iloc[-1]
        ren_bi = (l["Incentivo"] * n_at) / 1000
        
        # Safe-Stop Reativo e Proporcional (Item 5.3)
        if ren_bi > teto:
            ajuste = ren_bi / teto
            m_dinamico = max(1.0, m_dinamico / (1 + (ajuste - 1) * 0.5))
        
        rows.append([t, n_at, ren_bi, (l["P&D"]*n_at)/1000, (l["Retorno"]*n_at)/1000, m_dinamico])
    return pd.DataFrame(rows, columns=["Ano","Firmas","Renúncia","P&D","Retorno","M_Efetivo"])

# ─────────────────────────────────────────────
# INTERFACE E DASHBOARD
# ─────────────────────────────────────────────

with st.sidebar:
    st.header("🎯 Parâmetros de Gestão")
    teto_in = st.number_input("Teto Anual (R$ Bi)", 0.5, 5.0, 2.2, help=HELP_TEXT["teto"])
    s_m = st.slider("Multiplicador Inicial", 1.0, 1.8, 1.4, help=HELP_TEXT["m"])
    s_e = st.slider("Elasticidade", -2.0, -0.1, -1.27, help=HELP_TEXT["e"])
    st.divider()
    s_rec = st.slider("Receita Inicial (MM)", 1.0, 100.0, 15.0)
    s_i = st.slider("Intensidade P&D (%)", 1.0, 20.0, 7.0)/100
    s_g = st.slider("Crescimento Anual (%)", 0.0, 20.0, 12.0)
    s_n = st.number_input("Firmas Macro", 1000, 10000, 4500)

# Processamento
df_c = simular_unidade(s_rec, s_i, s_g/100, s_e, s_m, 10)
df_s = simular_unidade(s_rec, s_i, s_g/100, s_e, s_m, 10, True)
df_m = simular_macro_calibrado(s_n, 12.0, s_i, 0.08, s_e, s_m, 10, teto_in)

st.title("🏛️ Dashboard RETI — Suporte à Decisão")

tab1, tab2, tab3 = st.tabs(["🏛️ Controle Macro", "📈 Análise da Firma", "🔍 Sensibilidade"])

with tab1:
    st.subheader("Equilíbrio Fiscal vs Multiplicador")
    fig_m = go.Figure()
    fig_m.add_trace(go.Bar(x=df_m["Ano"], y=df_m["Renúncia"], name="Renúncia (Bi)", marker_color='RoyalBlue'))
    fig_m.add_trace(go.Scatter(x=df_m["Ano"], y=[teto_in]*10, name="Teto LRF", line=dict(color='Red', dash='dash')))
    fig_m.add_trace(go.Scatter(x=df_m["Ano"], y=df_m["M_Efetivo"], name="Multiplicador (M)", yaxis="y2", line=dict(color='Orange', width=3)))
    
    fig_m.update_layout(yaxis_title="R$ Bilhões", yaxis2=dict(overlaying="y", side="right", range=[0.9, 2.0]),
                        legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig_m, use_container_width=True)
    st.info(f"O Multiplicador é ajustado para manter a renúncia próxima ao teto de R$ {teto_in} Bi.")

with tab2:
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(px.line(df_c, x="Ano", y="P&D", title="Indução de P&D (R$ MM)"), use_container_width=True)
    with col2:
        st.plotly_chart(px.area(df_c, x="Ano", y="Estoque", title="Estoque de Créditos (Prescrição 5 anos)"), use_container_width=True)
    st.dataframe(df_c.style.format(precision=2))

with tab3:
    st.subheader("Análise de Estresse: ROI vs Elasticidade")
    sens = []
    for te in np.linspace(-0.2, -2.2, 11):
        dc = simular_unidade(s_rec, s_i, s_g/100, te, s_m, 10)
        ds = simular_unidade(s_rec, s_i, s_g/100, te, s_m, 10, True)
        roi = (dc["P&D"].sum() - ds["P&D"].sum()) / dc["Incentivo"].sum() if dc["Incentivo"].sum() > 0 else 0
        sens.append([te, roi])
    
    fig_s = px.line(pd.DataFrame(sens, columns=["E", "ROI"]), x="E", y="ROI", markers=True)
    fig_s.add_hline(y=1.0, line_dash="dash", line_color="Red", annotation_text="Break-even")
    fig_s.update_layout(xaxis_title="Elasticidade (Capacidade de Inovação)", yaxis_title="ROI (Adicionalidade)", xaxis=dict(autorange="reversed"))
    st.plotly_chart(fig_s, use_container_width=True)
    st.write("**Legenda:** Se o ROI > 1.0, o programa gera mais investimento do que custa em renúncia.")

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────
# CONFIGURAÇÕES E DEFINIÇÕES TÉCNICAS
# ─────────────────────────────────────────────
st.set_page_config(page_title="RETI — Gestão Fiscal SPE", layout="wide")

HELP_TEXT = {
    "e": "Elasticidade-custo (-1,27): Mede quanto o setor privado investe a mais para cada redução de custo tributário.",
    "teto": "Limite orçamentário anual (LRF) para o programa (R$ 2,2 Bilhões).",
    "roi": "Adicionalidade: Valor em P&D gerado por cada R$ 1,00 de renúncia fiscal."
}

# ─────────────────────────────────────────────
# MOTOR DE CÁLCULO (LÓGICA ANUALIZADA)
# ─────────────────────────────────────────────

def fator_f_oficial(r):
    """Tabela progressiva baseada na Receita Bruta (Item 3.2)."""
    if r <= 3.24: return 3.5
    elif r <= 78: return 2.5
    else: return max(1.0, 2.5 - 0.012*(r-78))

def simular_unidade(rec0, i, g, e, m, anos, sem_reti=False):
    """Simula o comportamento de uma firma individual sob o regime RETI."""
    rec = rec0 * 1e6
    fila_creditos = [] # Controle FIFO para prescrição de 5 anos
    resultados = []

    for t in range(1, anos+1):
        rec_ant = rec
        rec *= (1 + g)
        cresc = (rec / rec_ant) - 1
        base_pd_natural = rec * i
        
        if sem_reti:
            total_pd, imp, inc, f, uso, est = base_pd_natural, (rec*0.32*0.34), 0, 0, 0, 0
        else:
            f = fator_f_oficial(rec/1e6)
            custo_marginal = m * f * 0.34
            # Adicionalidade baseada na elasticidade real observada
            pd_adicional = max(0, base_pd_natural * abs(e) * custo_marginal)
            total_pd = base_pd_natural + pd_adicional

            # Geração e Prescrição de Créditos (Item 6.4)
            fila_creditos.append([m * total_pd * f * 0.34, t + 5])
            fila_creditos = [c for c in fila_creditos if c[1] > t] 

            # Gatilho de Performance (Item 6.3): Crescimento > 10%
            pode_compensar = not (t > 3 and cresc < 0.10)
            
            imp_ref = rec * 0.32 * 0.34
            limite_anual = imp_ref * 0.5
            uso = 0

            if pode_compensar:
                saldo_total = sum(c[0] for c in fila_creditos)
                uso = min(saldo_total, limite_anual)
                # Abate FIFO
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

        resultados.append([t, rec/1e6, total_pd/1e6, imp/1e6, inc/1e6, f, est/1e6, cresc])

    return pd.DataFrame(resultados, columns=["Ano","Receita","P&D","Imposto","Incentivo","Fator","Estoque","Cresc"])

def simular_macro_anual(n, rec_m, i, g_m, e, m_base, anos, teto_anual):
    """Calcula o impacto nacional com ajuste de multiplicador ano a ano."""
    rows = []
    m_atual = m_base
    for t in range(1, anos+1):
        n_at = int(n * (1.03**t))
        # Simula apenas o ano corrente com o M ajustado
        df_u = simular_unidade(rec_m, i, g_m, e, m_atual, t)
        last = df_u.iloc[-1]
        
        renuncia_bi = (last["Incentivo"] * n_at) / 1000
        
        # Safe-Stop Reativo (Item 5.3): Ajusta M para o ano seguinte
        if renuncia_bi > teto_anual:
            ratio_excesso = renuncia_bi / teto_anual
            m_atual = max(1.0, m_atual / (1 + (ratio_excesso - 1) * 0.5))

        rows.append([t, n_at, renuncia_bi, (last["P&D"]*n_at)/1000, m_atual])
    return pd.DataFrame(rows, columns=["Ano","Firmas","Renúncia","P&D","M_Efetivo"])

# ─────────────────────────────────────────────
# INTERFACE E VISUALIZAÇÃO
# ─────────────────────────────────────────────

st.title("🏛️ RETI: Dashboard de Governança Fiscal e Inovação")

with st.sidebar:
    st.header("⚙️ Configuração da Política")
    teto_target = st.number_input("Teto de Renúncia Anual (R$ Bi)", 0.5, 5.0, 2.2, help=HELP_TEXT["teto"])
    m_start = st.slider("Multiplicador Inicial (M)", 1.0, 1.8, 1.4)
    elasticidade = st.slider("Elasticidade-Custo", -2.0, -0.1, -1.27, help=HELP_TEXT["e"])
    st.divider()
    firmas_n = st.number_input("Universo de Firmas", 1000, 10000, 4500)
    horizonte = st.slider("Horizonte (Anos)", 5, 20, 10)

# Execução
df_macro = simular_macro_anual(firmas_n, 12.0, 0.07, 0.08, elasticidade, m_start, horizonte, teto_target)

tab1, tab2 = st.tabs(["🏛️ Controle Orçamentário Nacional", "🔍 Sensibilidade e ROI"])

with tab1:
    st.subheader("Equilíbrio Fiscal: Renúncia vs. Multiplicador")
    st.markdown("O gráfico abaixo mostra como o programa reage anualmente para não ultrapassar o teto da LRF.")
    
    fig = go.Figure()
    # Renúncia Anual
    fig.add_trace(go.Bar(x=df_macro["Ano"], y=df_macro["Renúncia"], name="Renúncia Estimada (R$ Bi)", marker_color="RoyalBlue"))
    # Linha de Teto (Premissa Anual)
    fig.add_trace(go.Scatter(x=df_macro["Ano"], y=[teto_target]*horizonte, name="Teto Anual (Premissa)", line=dict(color="Red", dash="dash", width=3)))
    # Evolução do Multiplicador
    fig.add_trace(go.Scatter(x=df_macro["Ano"], y=df_macro["M_Efetivo"], name="Ajuste do Multiplicador (M)", yaxis="y2", line=dict(color="Orange", width=4)))
    
    fig.update_layout(
        xaxis_title="Ano de Vigência",
        yaxis_title="Renúncia Fiscal (R$ Bilhões)",
        yaxis2=dict(title="Valor do Multiplicador (M)", overlaying="y", side="right", range=[0.9, 2.0]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("Análise de Estresse: Resiliência da Adicionalidade")
    st.markdown("Mede a eficiência do gasto: quanto de investimento privado é gerado para cada real renunciado.")
    
    sens_res = []
    for test_e in np.linspace(-0.2, -2.2, 11):
        d_c = simular_unidade(15.0, 0.07, 0.12, test_e, m_start, horizonte)
        d_s = simular_unidade(15.0, 0.07, 0.12, test_e, m_start, horizonte, sem_reti=True)
        # ROI = (P&D Adicional) / Renúncia
        pd_add = (d_c["P&D"].sum() - d_s["P&D"].sum())
        ren_total = d_c["Incentivo"].sum()
        roi = pd_add / ren_total if ren_total > 0 else 0
        sens_res.append([test_e, roi])
    
    df_sens = pd.DataFrame(sens_res, columns=["Elasticidade", "ROI"])
    fig_s = go.Figure()
    fig_s.add_trace(go.Scatter(x=df_sens["Elasticidade"], y=df_sens["ROI"], mode="lines+markers", name="ROI (Adicionalidade)", line=dict(color="Teal", width=3)))
    fig_s.add_hline(y=1.0, line_dash="dash", line_color="Red", annotation_text="Ponto de Equilíbrio (ROI=1.0)")
    
    fig_s.update_layout(
        xaxis_title="Elasticidade-Custo (Cenários de Estresse)",
        yaxis_title="ROI (R$ P&D / R$ Renúncia)",
        xaxis=dict(autorange="reversed")
    )
    st.plotly_chart(fig_s, use_container_width=True)
    st.write("**Interpretação:** Valores acima de 1.0 indicam que a política gera mais investimento do que custa aos cofres públicos.")

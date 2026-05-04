import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
st.set_page_config(page_title="RETI — Simulador", layout="wide")

# ─────────────────────────────────────────────
# CORE ECONÔMICO (CORRIGIDO: Fator F fiel ao Word)
# ─────────────────────────────────────────────

def factor_f_corrigido(r):
    if r <= 3.24: return 3.5
    elif r <= 78: return 2.5
    else: return max(1.0, 2.5 - 0.012*(r-78))

def imposto_ref(rec):
    return (rec * 0.32) * 0.34

# ─────────────────────────────────────────────
# FIRMA (AGORA COM PRESCRIÇÃO E GATILHO DE PERFORMANCE)
# ─────────────────────────────────────────────

def sim_firma(rec0, i, g, e, m, anos, sem=False):
    rec = rec0 * 1e6
    # Fila de créditos: [valor, ano_expiracao] para controle de 5 anos
    fila_creditos = [] 
    out = []

    for t in range(1, anos+1):
        rec_ant = rec
        rec *= (1 + g)
        crescimento = (rec / rec_ant) - 1
        
        base_estimada = rec * i

        if sem:
            total_pd = base_estimada
            imp = imposto_ref(rec)
            inc = 0
            f = 0
            uso_credito = 0
            estoque_total = 0
        else:
            f = factor_f_corrigido(rec/1e6)
            custo = m * f * 0.34
            delta = max(0, base_estimada * abs(e) * custo)
            total_pd = base_estimada + delta

            # Gerar crédito e adicionar à fila com validade de 5 anos
            credito_gerado = m * total_pd * f * 0.34
            fila_creditos.append([credito_gerado, t + 5])

            # 1. Limpeza de créditos expirados (Prescrição)
            fila_creditos = [c for c in fila_creditos if c[1] > t]

            # 2. Gatilho de Performance (Item 6.3 do Word)
            pode_compensar = True
            if t > 3 and crescimento < 0.10: # Trava de 10% de crescimento
                pode_compensar = False

            imp_ref = imposto_ref(rec)
            limite_uso = imp_ref * 0.5
            uso_credito = 0

            if pode_compensar:
                # Consumo FIFO
                saldo_disponivel = sum(c[0] for c in fila_creditos)
                uso_credito = min(saldo_disponivel, limite_uso)
                
                sobra_uso = uso_credito
                for c in fila_creditos:
                    if sobra_uso <= 0: break
                    baixar = min(c[0], sobra_uso)
                    c[0] -= baixar
                    sobra_uso -= baixar

            # 3. Cap de Exoneração (25% do imposto devido)
            imp = max(imp_ref * 0.25, imp_ref - uso_credito)
            inc = imp_ref - imp
            estoque_total = sum(c[0] for c in fila_creditos)

        # Retorno social/econômico (métrica original do seu código)
        retorno = (total_pd - base_estimada) * 0.65 * 0.28 if not sem else 0

        out.append([
            t, rec/1e6, total_pd/1e6, imp/1e6, inc/1e6,
            retorno/1e6, f, estoque_total/1e6
        ])

    return pd.DataFrame(out, columns=[
        "Ano","Receita","P&D","Imposto","Incentivo",
        "Retorno","Fator","Estoque Crédito"
    ])

# ─────────────────────────────────────────────
# MACRO (COM SAFE-STOP DO MULTIPLICADOR)
# ─────────────────────────────────────────────

def sim_macro(n, rec, i, g, e, m_base, anos):
    rows = []
    m_dinamico = m_base
    teto = 2.2 # R$ Bi conforme Word

    for t in range(1, anos+1):
        n_t = int(n * (1.03**t))
        # Simulamos a média para o ano
        df_f = sim_firma(rec, i, g, e, m_dinamico, t)
        linha = df_f.iloc[-1]
        
        ren_total = (linha["Incentivo"] * n_t) / 1000
        
        # Ajuste Safe-Stop para o próximo ciclo
        if ren_total > teto:
            m_dinamico = max(1.0, m_dinamico * 0.95)

        rows.append([
            t, n_t, ren_total, 
            (linha["P&D"] * n_t)/1000, 
            (linha["Retorno"] * n_t)/1000, 
            (linha["Estoque Crédito"] * n_t)/1000,
            m_dinamico
        ])

    df = pd.DataFrame(rows, columns=["Ano","Firmas","Renúncia","P&D","Retorno","Estoque", "M_Efetivo"])
    df["Renúncia Acum"] = df["Renúncia"].cumsum()
    df["Retorno Acum"] = df["Retorno"].cumsum()
    return df

# ─────────────────────────────────────────────
# INTERFACE (RECOMPONDO SEU LAYOUT ORIGINAL)
# ─────────────────────────────────────────────

with st.sidebar:
    st.header("Parâmetros da Firma")
    rec_input = st.slider("Receita Inicial (R$ MM)", 1.0, 100.0, 15.0)
    i_input = st.slider("Intensidade P&D (%)", 1.0, 20.0, 7.0)/100
    g_input = st.slider("Crescimento (%)", 0.0, 20.0, 12.0)/100

    st.header("Macro")
    n_input = st.number_input("Firmas", 1000, 10000, 4000)
    rec_m_input = st.slider("Receita Média", 1.0, 50.0, 10.0)
    g_m_input = st.slider("Crescimento Universo", 0.0, 15.0, 8.0)/100

    st.header("Política")
    e_input = st.slider("Elasticidade", -2.0, -0.5, -1.27)
    m_input = st.slider("Multiplicador", 1.0, 1.6, 1.25)
    anos_input = st.slider("Horizonte", 5, 15, 10)

# Execução
df_c = sim_firma(rec_input, i_input, g_input, e_input, m_input, anos_input)
df_s = sim_firma(rec_input, i_input, g_input, e_input, m_input, anos_input, True)
df_m = sim_macro(n_input, rec_m_input, i_input, g_m_input, e_input, m_input, anos_input)

# KPIs
pnd_add = df_c["P&D"].sum() - df_s["P&D"].sum()
inc_total = df_c["Incentivo"].sum()
roi = pnd_add/inc_total if inc_total > 0 else 0

# DASHBOARD
st.title("Simulador RETI - Governança SPE/MF")
tab1, tab2, tab3 = st.tabs(["📈 Firma", "🏛️ Fiscal", "🔍 Diagnóstico"])

with tab1:
    st.subheader("Impacto Microeconômico")
    c1, c2, c3 = st.columns(3)
    c1.metric("P&D Adicional (Acum)", f"R$ {pnd_add:.2f}M")
    c2.metric("Incentivo Total", f"R$ {inc_total:.2f}M")
    c3.metric("ROI (Adicionalidade)", f"{roi:.2f}x")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_c["Ano"], y=df_c["P&D"], name="Com RETI"))
    fig.add_trace(go.Scatter(x=df_s["Ano"], y=df_s["P&D"], name="Sem RETI"))
    fig.update_layout(title="Investimento em P&D (Firma)", xaxis_title="Ano", yaxis_title="R$ MM")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df_c.style.format(precision=2))

with tab2:
    st.subheader("Impacto Fiscal Agregado")
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(x=df_m["Ano"], y=df_m["P&D"], name="P&D Total (Bi)"))
    fig2.add_trace(go.Scatter(x=df_m["Ano"], y=df_m["Renúncia"], name="Renúncia (Bi)"))
    fig2.add_trace(go.Scatter(x=df_m["Ano"], y=df_m["Estoque"], name="Estoque Crédito (Bi)", line=dict(dash="dot")))
    fig2.update_layout(title="Fluxo Fiscal do Programa", yaxis_title="R$ Bilhões")
    st.plotly_chart(fig2, use_container_width=True)

with tab3:
    st.subheader("Diagnóstico de Sustentabilidade")
    ren_sum = df_m["Renúncia"].sum()
    ret_sum = df_m["Retorno"].sum()
    st.markdown(f"""
- **ROI Fiscal (Retorno/Renúncia):** {ret_sum/ren_sum:.2f}x
- **Estoque Final de Créditos:** R$ {df_m["Estoque"].iloc[-1]:.2f} Bi
- **Multiplicador ao Final do Período:** {df_m["M_Efetivo"].iloc[-1]:.2f}

**Notas de Revisão:**
1. **Prescrição:** O estoque de crédito agora expira após 5 anos (Lógica FIFO).
2. **Gatilho:** O uso do crédito é travado se o crescimento for inferior a 10% (visível no Ano 4+).
3. **Safe-Stop:** O multiplicador diminuiu se a renúncia macro excedeu R$ 2,2 Bi.
4. **Fator F:** Normalizado para a tabela de faturamento do Word.
""")

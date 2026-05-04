import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
st.set_page_config(page_title="RETI — Simulador", layout="wide")

# ─────────────────────────────────────────────
# CORE ECONÔMICO
# ─────────────────────────────────────────────

def fator_f(r, i):
    if i >= 0.05:
        if r <= 3.24: return 3.5
        elif r <= 16.2: return 3.0
        elif r <= 78: return 2.5
        else: return max(1, 2.5 - 0.012*(r-78))
    else:
        if r <= 3.24: return 2.5
        elif r <= 16.2: return 2.0
        elif r <= 78: return 1.5
        else: return max(1, 1.5 - 0.004*(r-78))

def imposto_ref(rec):
    return (rec * 0.32) * 0.34

# ─────────────────────────────────────────────
# FIRMA (AGORA COM ESTOQUE + TRAVA)
# ─────────────────────────────────────────────

def sim_firma(rec0, i, g, e, m, anos, sem=False):
    rec = rec0 * 1e6
    stock_credito = 0
    out = []

    for t in range(1, anos+1):
        g_end = min(0.05, (stock_credito/1e7)*0.005)
        rec *= (1 + g + (0 if sem else g_end))

        base = rec * i

        if sem:
            total = base
            imp = imposto_ref(rec)
            inc = 0
            delta = 0
            f = 0
            uso_credito = 0
        else:
            f = fator_f(rec/1e6, i)
            custo = m * f * 0.34
            delta = max(0, base * abs(e) * custo)

            total = base + delta

            # crédito gerado
            credito_gerado = m * total * f * 0.34

            imp_ref = imposto_ref(rec)

            # uso limitado a 50% do imposto
            limite_uso = imp_ref * 0.5
            uso_credito = min(stock_credito, limite_uso)

            # imposto após uso
            imp = max(imp_ref*0.25, imp_ref - uso_credito)

            # atualização estoque
            stock_credito = stock_credito + credito_gerado - uso_credito

            inc = imp_ref - imp

        retorno = delta * 0.65 * 0.28

        out.append([
            t, rec/1e6, total/1e6, imp/1e6, inc/1e6,
            retorno/1e6, f, stock_credito/1e6
        ])

    return pd.DataFrame(out, columns=[
        "Ano","Receita","P&D","Imposto","Incentivo",
        "Retorno","Fator","Estoque Crédito"
    ])

# ─────────────────────────────────────────────
# MACRO (AGORA CONSISTENTE COM REGRAS DO RETI)
# ─────────────────────────────────────────────

def sim_macro(n, rec, i, g, e, m, anos):
    rows = []
    stock = 0

    for t in range(1, anos+1):
        n_t = int(n * (1.03**t))
        rec_t = rec * (1+g)**t

        f = fator_f(rec_t, i)

        base = rec_t*1e6*i
        delta = max(0, base * abs(e) * (m*f*0.34))

        total = base + delta

        imp_ref = imposto_ref(rec_t*1e6)

        credito = m * total * f * 0.34

        uso = min(stock, imp_ref * 0.5)

        imp = max(imp_ref*0.25, imp_ref - uso)

        stock = stock + credito*n_t - uso*n_t

        ren = (imp_ref - imp) * n_t / 1e9
        pnd = delta * n_t / 1e9
        ret = pnd * 0.65 * 0.28

        rows.append([t, n_t, ren, pnd, ret, stock/1e9])

    df = pd.DataFrame(rows, columns=[
        "Ano","Firmas","Renúncia","P&D","Retorno","Estoque"
    ])

    df["Renúncia Acum"] = df["Renúncia"].cumsum()
    df["Retorno Acum"] = df["Retorno"].cumsum()

    return df

# ─────────────────────────────────────────────
# SIDEBAR (INALTERADO)
# ─────────────────────────────────────────────

with st.sidebar:
    st.header("Parâmetros da Firma")
    rec = st.slider("Receita Inicial (R$ MM)",1.0,100.0,15.0)
    i = st.slider("Intensidade P&D (%)",1.0,20.0,7.0)/100
    g = st.slider("Crescimento (%)",0.0,20.0,10.0)/100

    st.header("Macro")
    n = st.number_input("Firmas",1000,10000,4000)
    rec_m = st.slider("Receita Média",1.0,50.0,10.0)
    g_m = st.slider("Crescimento Universo",0.0,15.0,8.0)/100

    st.header("Política")
    e = st.slider("Elasticidade",-2.0,-0.5,-1.2)
    m = st.slider("Multiplicador",1.0,1.6,1.25)
    anos = st.slider("Horizonte",5,15,10)

# ─────────────────────────────────────────────
# EXECUÇÃO
# ─────────────────────────────────────────────

df_c = sim_firma(rec,i,g,e,m,anos)
df_s = sim_firma(rec,i,g,e,m,anos,True)
df_m = sim_macro(n,rec_m,i,g_m,e,m,anos)

# KPIs
pnd_add = df_c["P&D"].sum() - df_s["P&D"].sum()
inc = df_c["Incentivo"].sum()
roi = pnd_add/inc if inc>0 else 0

# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(["📈 Firma","🏛️ Fiscal","🔍 Diagnóstico"])

# FIRMA
with tab1:
    st.subheader("Impacto Microeconômico")

    c1,c2,c3 = st.columns(3)
    c1.metric("P&D Adicional",f"{pnd_add:.1f}M")
    c2.metric("Incentivo",f"{inc:.1f}M")
    c3.metric("ROI",f"{roi:.2f}x")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_c["Ano"], y=df_c["P&D"], name="Com RETI"))
    fig.add_trace(go.Scatter(x=df_s["Ano"], y=df_s["P&D"], name="Sem RETI"))
    fig.update_layout(title="Investimento em P&D (Firma)")
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(df_c)

# MACRO
with tab2:
    st.subheader("Impacto Fiscal Agregado")

    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_m["Ano"], y=df_m["P&D"], name="P&D"))
    fig.add_trace(go.Scatter(x=df_m["Ano"], y=df_m["Renúncia"], name="Renúncia"))
    fig.add_trace(go.Scatter(x=df_m["Ano"], y=df_m["Retorno"], name="Retorno"))
    fig.add_trace(go.Scatter(x=df_m["Ano"], y=df_m["Estoque"], name="Estoque Crédito", line=dict(dash="dot")))
    fig.update_layout(title="Fluxo Fiscal do Programa (com carry-forward)")
    st.plotly_chart(fig, use_container_width=True)

# DIAGNÓSTICO (ROBUSTO)
with tab3:
    st.subheader("Diagnóstico Fiscal Estrutural")

    ren_total = df_m["Renúncia"].sum()
    ret_total = df_m["Retorno"].sum()

    ratio = ret_total / ren_total if ren_total > 0 else 0

    tendencia_ren = np.polyfit(df_m["Ano"], df_m["Renúncia"], 1)[0]
    tendencia_ret = np.polyfit(df_m["Ano"], df_m["Retorno"], 1)[0]

    st.markdown(f"""
**Leitura técnica:**

- ROI fiscal: **{ratio:.2f}x**
- Estoque final de créditos: **R$ {df_m['Estoque'].iloc[-1]:.2f} Bi**

**Interpretação:**

- O programa **não é explosivo no curto prazo** (travas funcionam)
- Mas cria um **passivo fiscal implícito crescente**
- Sustentabilidade depende de:
    - crescimento da base tributária futura
    - calibração do multiplicador
    - disciplina no uso do estoque

**Diagnóstico:**

- Não é um modelo inviável  
- É um modelo de **risco fiscal gerenciável — não automático**

**Problema real:**
→ o risco não está no fluxo  
→ está no **estoque acumulado de créditos**
""")

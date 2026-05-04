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
# FIRMA
# ─────────────────────────────────────────────

def sim_firma(rec0, i, g, e, m, anos, sem=False):
    rec = rec0 * 1e6
    stock = 0
    out = []

    for t in range(1, anos+1):
        g_end = min(0.05, (stock/1e7)*0.005)
        rec *= (1 + g + (0 if sem else g_end))

        base = rec * i

        if sem:
            total = base
            imp = imposto_ref(rec)
            inc = 0
            delta = 0
            f = 0
        else:
            f = fator_f(rec/1e6, i)
            custo = m * f * 0.34
            delta = max(0, base * abs(e) * custo)

            total = base + delta
            stock += delta

            base_reti = max(0, rec*0.32 - m*total*f)
            imp = max(imposto_ref(rec)*0.25, base_reti*0.34)

            inc = max(0, imposto_ref(rec) - imp)

        retorno = delta * 0.65 * 0.28

        out.append([t, rec/1e6, total/1e6, imp/1e6, inc/1e6, retorno/1e6, f])

    return pd.DataFrame(out, columns=[
        "Ano","Receita","P&D","Imposto","Incentivo","Retorno","Fator"
    ])

# ─────────────────────────────────────────────
# MACRO COM GOVERNANÇA (VERSÃO CORRIGIDA)
# ─────────────────────────────────────────────

def sim_macro(n, rec, i, g, e, m, anos, cap_anual=2.2, gatilho=True):
    rows = []
    ren_acum = 0

    for t in range(1, anos+1):
        n_t = int(n * (1.03**t))
        rec_t = rec * (1+g)**t

        f = fator_f(rec_t, i)

        base = rec_t*1e6*i
        delta = max(0, base * abs(e) * (m*f*0.34))

        imp_sem = imposto_ref(rec_t*1e6)
        imp_com = max(imp_sem*0.25, (rec_t*1e6*0.32 - m*(base+delta)*f)*0.34)

        ren_bruta = max(0, (imp_sem - imp_com)*n_t/1e9)
        pnd = delta*n_t/1e9
        ret = pnd * 0.65 * 0.28

        # ─── CAP FISCAL (PROPOSTA REAL)
        ren = min(ren_bruta, cap_anual)

        # ─── GATILHO AUTOMÁTICO
        if gatilho and ren_acum > cap_anual * 3:
            ren *= 0.85  # compressão do benefício

        ren_acum += ren

        rows.append([t, n_t, ren, ren_bruta, pnd, ret])

    df = pd.DataFrame(rows, columns=[
        "Ano","Firmas","Renúncia Controlada","Renúncia Bruta","P&D","Retorno"
    ])

    df["Renúncia Acum"] = df["Renúncia Controlada"].cumsum()
    df["Retorno Acum"] = df["Retorno"].cumsum()

    return df

# ─────────────────────────────────────────────
# SIDEBAR
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
    cap = st.slider("Teto anual (R$ bi)",1.0,5.0,2.2)

# ─────────────────────────────────────────────
# EXECUÇÃO
# ─────────────────────────────────────────────

df_c = sim_firma(rec,i,g,e,m,anos)
df_s = sim_firma(rec,i,g,e,m,anos,True)
df_m = sim_macro(n,rec_m,i,g_m,e,m,anos,cap)

# KPIs
pnd_add = df_c["P&D"].sum() - df_s["P&D"].sum()
inc = df_c["Incentivo"].sum()
roi = pnd_add/inc if inc>0 else 0

# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(["📈 Firma","🏛️ Fiscal","🔍 Diagnóstico"])

# ───────── FIRMA
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

# ───────── MACRO
with tab2:
    st.subheader("Impacto Fiscal com Governança")

    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_m["Ano"], y=df_m["P&D"], name="P&D"))
    fig.add_trace(go.Scatter(x=df_m["Ano"], y=df_m["Renúncia Controlada"], name="Renúncia (cap)"))
    fig.add_trace(go.Scatter(x=df_m["Ano"], y=df_m["Retorno"], name="Retorno"))
    fig.update_layout(title="Fluxo Fiscal Controlado")
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(df_m)

# ───────── DIAGNÓSTICO
with tab3:
    st.subheader("Diagnóstico Institucional (nível SPE)")

    ren = df_m["Renúncia Controlada"].sum()
    ret = df_m["Retorno"].sum()
    pnd = df_m["P&D"].sum()

    ratio = ret/ren if ren>0 else 0

    st.markdown("### Leitura Estrutural")

    st.write(f"• Retorno fiscal: {ratio:.2f}x")
    st.write(f"• P&D induzido: R$ {pnd:.1f} bi")

    st.markdown("### Interpretação Econômica")

    if ratio < 0.5:
        st.error("""
O regime não é auto-financiável.  
Isso não invalida o RETI — indica que ele opera como política industrial clássica,
com custo fiscal explícito.
""")

    st.markdown("### Leitura de Política Pública")

    st.markdown("""
O RETI não foi desenhado para se pagar via tributação direta.  
Seu objetivo é alterar a composição do crescimento.

A sustentabilidade depende de três condições:

1. Controle de fluxo (cap)
2. Recalibração periódica do multiplicador
3. Ganhos de produtividade de segunda ordem (não modelados aqui)
""")

    st.markdown("### Conclusão Realista")

    st.warning("""
Sem governança → trajetória explosiva  
Com cap + gatilhos → política fiscal controlável  

O RETI é viável como instrumento de política industrial,
não como mecanismo neutro do ponto de vista fiscal.
""")

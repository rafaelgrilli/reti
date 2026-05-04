import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
st.set_page_config(page_title="RETI — Simulador", layout="wide")

# ─────────────────────────────────────────────
# CORE ECONÔMICO (MESMA LÓGICA, MAIS ROBUSTO)
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
# MACRO
# ─────────────────────────────────────────────

def sim_macro(n, rec, i, g, e, m, anos):
    rows = []

    for t in range(1, anos+1):
        n_t = int(n * (1.03**t))
        rec_t = rec * (1+g)**t

        f = fator_f(rec_t, i)

        base = rec_t*1e6*i
        delta = max(0, base * abs(e) * (m*f*0.34))

        imp_sem = imposto_ref(rec_t*1e6)
        imp_com = max(imp_sem*0.25, (rec_t*1e6*0.32 - m*(base+delta)*f)*0.34)

        ren = max(0, (imp_sem - imp_com)*n_t/1e9)
        pnd = delta*n_t/1e9
        ret = pnd * 0.65 * 0.28

        rows.append([t, n_t, ren, pnd, ret])

    df = pd.DataFrame(rows, columns=["Ano","Firmas","Renúncia","P&D","Retorno"])
    df["Renúncia Acum"] = df["Renúncia"].cumsum()
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
# DASHBOARD COM ABAS (RESTAURADO)
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
    st.subheader("Impacto Fiscal Agregado")

    c1,c2,c3 = st.columns(3)
    c1.metric("Renúncia Total",f"{df_m['Renúncia Acum'].iloc[-1]:.2f} Bi")
    c2.metric("P&D Induzido",f"{df_m['P&D'].sum():.2f} Bi")
    c3.metric("Retorno Fiscal",f"{df_m['Retorno'].sum():.2f} Bi")

    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_m["Ano"], y=df_m["P&D"], name="P&D"))
    fig.add_trace(go.Scatter(x=df_m["Ano"], y=df_m["Renúncia"], name="Renúncia"))
    fig.add_trace(go.Scatter(x=df_m["Ano"], y=df_m["Retorno"], name="Retorno"))
    fig.update_layout(title="Fluxo Fiscal do Programa")
    st.plotly_chart(fig, use_container_width=True)

# ───────── DIAGNÓSTICO
with st.expander("🧠 Diagnóstico Econômico e Fiscal (Leitura para Decisão)"):
    ren_total = df_macro["Renúncia Fiscal (R$ Bi)"].sum()
    bf_total = df_macro["Retorno Tributário Indireto (R$ Bi)"].sum()
    pnd_total = df_macro["P&D Incremental (R$ Bi)"].sum()
    ren_liq_total = df_macro["Renúncia Líquida (R$ Bi)"].sum()

    ratio_retorno = bf_total / ren_total if ren_total > 0 else 0
    elasticidade_fiscal = pnd_total / ren_total if ren_total > 0 else 0

    tendencia_ren = np.polyfit(df_macro["Ano"], df_macro["Renúncia Fiscal (R$ Bi)"], 1)[0]
    tendencia_bf = np.polyfit(df_macro["Ano"], df_macro["Retorno Tributário Indireto (R$ Bi)"], 1)[0]

    st.markdown("### 1. Eficiência Econômica")
    if elasticidade_fiscal > 1:
        st.success(f"O programa gera adicionalidade relevante: cada R$1 de renúncia induz R${elasticidade_fiscal:.2f} em P&D.")
    else:
        st.warning(f"A adicionalidade é limitada: cada R$1 de renúncia gera apenas R${elasticidade_fiscal:.2f} em P&D.")

    st.markdown("### 2. Sustentabilidade Fiscal")
    if ratio_retorno > 1:
        st.success(f"O backflow cobre integralmente o custo fiscal (ROI = {ratio_retorno:.2f}x).")
    elif ratio_retorno > 0.5:
        st.warning(f"O programa recupera parcialmente a renúncia (ROI = {ratio_retorno:.2f}x), com custo fiscal relevante.")
    else:
        st.error(f"O programa apresenta baixa recuperação fiscal (ROI = {ratio_retorno:.2f}x).")

    st.markdown("### 3. Dinâmica Intertemporal")
    if tendencia_ren > tendencia_bf:
        st.error("A renúncia cresce mais rápido que o retorno → trajetória fiscal **não sustentável** no longo prazo.")
    else:
        st.success("O retorno cresce em linha ou acima da renúncia → trajetória potencialmente sustentável.")

    st.markdown("### 4. Diagnóstico Estrutural")
    if elasticidade_fiscal < 1:
        st.markdown("- O principal problema é **baixa resposta comportamental das firmas**.")
    if ratio_retorno < 0.5:
        st.markdown("- O desenho gera **vazamento fiscal elevado** (baixa captura tributária do benefício).")
    if tendencia_ren > tendencia_bf:
        st.markdown("- Há risco de **explosão intertemporal da renúncia** sem contrapartida.")

    st.markdown("### 5. Implicações de Política (o que fazer?)")

    if ratio_retorno < 1:
        st.markdown("""
- 🔧 **Reduzir o multiplicador RETI** → corta renúncia marginal sem eliminar incentivo  
- 🎯 **Focalizar por intensidade de P&D** → concentrar benefício em firmas com maior adicionalidade  
- ⏳ **Introduzir limite temporal ou sunset clause** → evita acumulação estrutural de passivo fiscal  
        """)

    if elasticidade_fiscal < 1:
        st.markdown("""
- 📉 **Recalibrar elasticidade implícita** (problema não é só incentivo, é capacidade de resposta)  
- 🧪 **Complementar com instrumentos não fiscais** (subvenção, crédito direcionado)  
        """)

    if tendencia_ren > tendencia_bf:
        st.markdown("""
- ⚠️ **Implementar gatilhos fiscais automáticos**  
    - redução do benefício se ROI < threshold  
    - teto de renúncia como % do PIB  
        """)

    st.markdown("### 6. Conclusão Executiva")
    if ratio_retorno > 1 and elasticidade_fiscal > 1:
        st.success("Programa eficiente e sustentável → candidato a expansão.")
    elif ratio_retorno > 0.5:
        st.warning("Programa economicamente válido, mas exige **ajustes de desenho** para sustentabilidade.")
    else:
        st.error("Programa fiscalmente frágil → requer **reformulação estrutural antes de escala**.")

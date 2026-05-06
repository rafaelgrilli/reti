import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# CONFIG
st.set_page_config(page_title="RETI DSS — SPE Ready", layout="wide")

# PARÂMETROS
ALIQUOTA = 0.34
PRESUNCAO = 0.32
BETA_PTF = 0.06
MULT_INDIRETO = 1.3
LAG_PTF = 3
DEPREC = 0.15
SUCESSO = 0.70

# FUNÇÕES
def fator_porte(receita):
    if receita <= 3.24:
        return 3.5
    elif receita <= 78:
        return 2.5
    elif receita <= 200:
        return 2.5 - 0.012 * (receita - 78)
    else:
        return 1.0

def custo_relativo(incentivo):
    return incentivo / (1 + incentivo)

def adicionalidade_pd(pd_base, elasticidade, incentivo):
    return pd_base * abs(elasticidade) * custo_relativo(incentivo)

def base_reti(receita, pd_total, F, m):
    base = receita * PRESUNCAO
    base_min = base * 0.25
    base_red = max(base_min, base - (m * pd_total * F))
    return base, base_red

def difusao(n, t):
    return n / (1 + np.exp(-1.2 * (t - 3)))

# MOTOR
def simular_reti(params):

    receita = params['rec_inicial']
    intensidade_anterior = 0
    historico_pd = np.zeros(params['horizonte'] + 10)
    estoque = 0

    rows = []

    for t in range(1, params['horizonte'] + 1):

        rec_ant = receita
        receita *= (1 + params['crescimento'])
        crescimento = (receita / rec_ant) - 1

        pode = True if t <= 3 else (crescimento >= 0.10 or params['potec'] >= 0.15)

        pd_base = receita * params['intensidade_pd']
        F = fator_porte(receita)

        incentivo = params['multiplicador'] * F * ALIQUOTA

        # 🔵 NOVO — transparência econômica
        subsidio_efetivo = custo_relativo(incentivo)
        fator_alavancagem = abs(params['elasticidade']) * subsidio_efetivo

        pd_extra = adicionalidade_pd(pd_base, params['elasticidade'], incentivo)
        pd_total = pd_base + pd_extra

        if pode:
            base, base_red = base_reti(receita, pd_total, F, params['multiplicador'])
            ren_unit = (base - base_red) * ALIQUOTA
        else:
            ren_unit = 0

        firmas = difusao(params['n_firmas'], t)

        ren_macro = (ren_unit * firmas) / 1000
        pd_macro = (pd_total * firmas) / 1000
        pd_extra_macro = (pd_extra * firmas) / 1000

        if t + LAG_PTF < len(historico_pd):
            historico_pd[t + LAG_PTF] = pd_extra * SUCESSO

        estoque = estoque * (1 - DEPREC) + historico_pd[t]

        intensidade = pd_total / receita
        delta_int = intensidade - intensidade_anterior
        intensidade_anterior = intensidade

        delta_ptf = BETA_PTF * delta_int

        ret_base = receita * delta_ptf * ALIQUOTA
        ret_ind = ret_base * (MULT_INDIRETO - 1)
        ret_est = estoque * 0.01

        retorno = ret_base + ret_ind + ret_est
        ret_macro = (retorno * firmas) / 1000

        rows.append({
            "Ano": t,
            "Receita": receita,
            "P&D Total": pd_total,
            "P&D Macro": pd_macro,
            "PD Extra": pd_extra,
            "PD Extra Macro": pd_extra_macro,
            "Renúncia": ren_macro,
            "Retorno": ret_macro,
            "Saldo": ret_macro - ren_macro,
            "Fator F": F,
            "Pode Usar": pode,

            # 🔵 NOVO — auditabilidade explícita
            "Incentivo": incentivo,
            "Subsídio Efetivo": subsidio_efetivo,
            "Fator Alavancagem": fator_alavancagem
        })

    df = pd.DataFrame(rows)
    df["Acumulado"] = df["Saldo"].cumsum()
    return df

# GOVERNANÇA
def avaliar(df, teto):
    return df["Renúncia"].max() > teto

def ajustar(params):
    novo = params.copy()
    novo["multiplicador"] *= 0.9
    novo["intensidade_pd"] *= 0.97
    return novo

def rodar_politica(params, rodadas=3):
    hist = []
    for r in range(rodadas):
        df = simular_reti(params)
        violou = avaliar(df, params["teto_lrf"])
        hist.append((r, params.copy(), df, violou))
        if violou:
            params = ajustar(params)
    return hist

def rodar_cenarios(params):
    cenarios = {
        "Conservador": {**params, "multiplicador": 1.10, "elasticidade": -0.8},
        "Base": params,
        "Agressivo": {**params, "multiplicador": 1.45, "elasticidade": -1.8}
    }
    return {k: simular_reti(v) for k, v in cenarios.items()}

# SIDEBAR
st.sidebar.title("Parâmetros RETI")

params = {
    "rec_inicial": 15.0,
    "horizonte": 10,
    "n_firmas": st.sidebar.number_input("Firmas", 1000, 10000, 4500),
    "crescimento": st.sidebar.slider("Crescimento Receita", 0.05, 0.20, 0.12),
    "intensidade_pd": st.sidebar.slider("Intensidade P&D", 0.01, 0.40, 0.07),
    "elasticidade": st.sidebar.slider("Elasticidade", -2.0, -0.5, -1.2),
    "multiplicador": st.sidebar.slider("Multiplicador", 1.0, 1.5, 1.25),
    "teto_lrf": st.sidebar.slider("Teto LRF", 0.5, 5.0, 2.2),
    "potec": st.sidebar.slider("PoTec", 0.0, 0.5, 0.18)
}

# EXECUÇÃO
hist = rodar_politica(params)
df = hist[-1][2]
cenarios = rodar_cenarios(params)

# KPI
st.title("RETI DSS — Avaliação Fiscal e Econômica")

custo_total = df["Renúncia"].sum()
pd_total_macro = df["P&D Macro"].sum()
alavancagem = pd_total_macro / custo_total if custo_total > 0 else 0

k1, k2, k3, k4 = st.columns(4)
k1.metric("Custo Total (10a)", f"R$ {custo_total:.2f} Bi")
k2.metric("Alavancagem P&D", f"{alavancagem:.2f}x")
k3.metric("Intensidade P&D", f"{(df['P&D Total'].iloc[-1]/df['Receita'].iloc[-1]):.2%}")
k4.metric("Aderência ao Envelope Fiscal do RETI",
          "NÃO ADERENTE" if df["Renúncia"].max() > params["teto_lrf"] else "ADERENTE")

st.caption("""
O indicador refere-se ao limite fiscal do programa RETI, não ao teto fiscal agregado da União.
""")

# 🔵 NOVO — explicação objetiva aprimorada
st.caption("""
Mecanismo de alavancagem:
P&D adicional = elasticidade (ε) × redução de custo do P&D (subsídio fiscal).
""")

# GRÁFICOS
st.subheader("Dinâmica Fiscal do Programa (R$ bilhões)")
st.caption("""
Comparação entre:
- Renúncia fiscal anual (custo do programa)
- Retorno fiscal estimado via produtividade e atividade econômica
""")

fig = go.Figure()
fig.add_trace(go.Scatter(x=df["Ano"], y=df["Renúncia"], name="Custo"))
fig.add_trace(go.Scatter(x=df["Ano"], y=df["Retorno"], name="Retorno"))
st.plotly_chart(fig, use_container_width=True)

st.subheader("Resultado Fiscal Líquido Acumulado (R$ bilhões)")
st.caption("""
Saldo acumulado = retorno fiscal estimado – renúncia do programa.

Indicador não representa payback direto, mas uma aproximação do impacto fiscal líquido ao longo do tempo.
""")

fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=df["Ano"], y=df["Acumulado"], fill='tozeroy'))
st.plotly_chart(fig2, use_container_width=True)

# MACRO (INALTERADO)
st.subheader("Impacto Macroeconômico")

PIB = 10000
g = 0.022
baseline = 0.0117

pib_series = []
for _ in df["Ano"]:
    PIB *= (1 + g)
    pib_series.append(PIB)

df["PIB"] = pib_series
df["P&D/PIB_incremental"] = df["PD Extra Macro"] / df["PIB"]
df["P&D/PIB_total"] = baseline + df["P&D/PIB_incremental"]

m1, m2, m3 = st.columns(3)
m1.metric("P&D / PIB (Atual)", "1.17%")
m2.metric("P&D / PIB (com RETI)", f"{df['P&D/PIB_total'].iloc[-1]:.2%}")
m3.metric("Δ P&D / PIB", f"{df['P&D/PIB_incremental'].iloc[-1]:.2%}")

# SENSIBILIDADE (INALTERADO)
st.subheader("Intervalo de Resultados")

custos = [c["Renúncia"].sum() for c in cenarios.values()]
c1, c2 = st.columns(2)

c1.metric("Custo Médio", f"R$ {np.mean(custos):.2f} Bi",
          delta=f"{min(custos):.2f} – {max(custos):.2f}")

# DIAGNÓSTICO (INALTERADO)
st.subheader("Diagnóstico")

if alavancagem > 1.5:
    st.success("Alta adicionalidade")
elif alavancagem > 1.0:
    st.info("Adicionalidade moderada")
else:
    st.warning("Baixa adicionalidade")

if df["Renúncia"].max() > params["teto_lrf"]:
    st.error("Pressão fiscal: excede envelope do programa")
else:
    st.success("Programa dentro do envelope fiscal")

# LIMITAÇÕES (INALTERADO)
st.subheader("Nota Metodológica")
st.caption("Modelo estrutural baseado em parâmetros da literatura. Resultados devem ser interpretados como cenários, não previsões pontuais.")

# TABELA
with st.expander("Dados detalhados + variáveis do modelo"):
    st.markdown("""
**Novas variáveis adicionadas para auditabilidade:**

- **Incentivo**: intensidade do benefício fiscal aplicado  
- **Subsídio Efetivo**: redução percentual do custo do P&D  
- **Fator Alavancagem**: ε × subsídio → impacto sobre investimento  

**Leitura:**
O RETI atua reduzindo o custo do P&D → empresas respondem via elasticidade → investimento adicional emerge.
""")
    st.dataframe(df)

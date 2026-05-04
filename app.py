import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# =========================================================
# 1. FUNÇÕES CORE
# =========================================================

def fator_f_unificado(r_mm, intensidade):
    if intensidade >= 0.05:
        if r_mm <= 3.24: return 3.5
        elif r_mm <= 16.2: return 3.0
        elif r_mm <= 78.0: return 2.5
        else: return max(1.0, 2.5 - 0.012 * (r_mm - 78.0))
    else:
        if r_mm <= 3.24: return 2.5
        elif r_mm <= 16.2: return 2.0
        elif r_mm <= 78.0: return 1.5
        else: return max(1.0, 1.5 - 0.004 * (r_mm - 78.0))

# =========================================================
# 2. MOTOR MICRO (COM CORREÇÃO DE SOBREVIVÊNCIA)
# =========================================================

def simular_micro(p, sem_reti=False, seed=42):

    np.random.seed(seed)

    n = p['n_empresas']

    # Inicialização
    mu = np.log(p['rec_media_mm']) - (0.8**2 / 2)
    receitas = np.random.lognormal(mu, 0.8, n) * 1e6
    intensidades = np.clip(np.random.normal(p['intensidade_pnd'], 0.03, n), 0.01, 0.4)

    estoque_pnd = np.zeros(n)
    historico_pnd = [np.zeros(n) for _ in range(3)]

    estoque_credito = [np.zeros(n) for _ in range(5)]

    anual = []

    for ano in range(1, p['anos'] + 1):

        # -------------------------------------------------
        # DEMOGRAFIA (ENTRADA + SAÍDA) — FIX DO BUG
        # -------------------------------------------------

        prob_saida = np.clip(0.05 - 0.02 * (intensidades / 0.1), 0.01, 0.08)
        sobrevivencia = np.random.rand(len(receitas)) > prob_saida

        # ✔ FIX: aplicar máscara em TODOS vetores
        receitas = receitas[sobrevivencia]
        intensidades = intensidades[sobrevivencia]
        estoque_pnd = estoque_pnd[sobrevivencia]

        historico_pnd = [h[sobrevivencia] for h in historico_pnd]
        estoque_credito = [e[sobrevivencia] for e in estoque_credito]

        # Entrada
        taxa_entrada = p['taxa_entrada_liq'] + (0 if sem_reti else p['bonus_entrada_reti'])
        n_novas = int(len(receitas) * taxa_entrada)

        if n_novas > 0:
            novas_rec = np.random.lognormal(mu, 0.8, n_novas) * 1e6
            novas_int = np.clip(np.random.normal(p['intensidade_pnd'], 0.03, n_novas), 0.01, 0.4)

            receitas = np.concatenate([receitas, novas_rec])
            intensidades = np.concatenate([intensidades, novas_int])

            estoque_pnd = np.concatenate([estoque_pnd, np.zeros(n_novas)])

            historico_pnd = [np.concatenate([h, np.zeros(n_novas)]) for h in historico_pnd]
            estoque_credito = [np.concatenate([e, np.zeros(n_novas)]) for e in estoque_credito]

        # -------------------------------------------------
        # PRODUTIVIDADE COM LAG
        # -------------------------------------------------

        est_def = historico_pnd[0]
        ajuste = p['e_ptf'] * np.log(1 + est_def / (receitas + 1))
        ajuste = np.minimum(ajuste, 0.05)

        g = p['taxa_g_base'] + (0 if sem_reti else ajuste)

        receitas *= (1 + g)

        pnd_base = receitas * intensidades

        # -------------------------------------------------
        # ELASTICIDADE
        # -------------------------------------------------

        elasticidade = p['e_custo'] * (1 + p['alpha_het'] * (np.mean(receitas)/(receitas+1)))

        # -------------------------------------------------
        # RETI
        # -------------------------------------------------

        fatores = np.array([fator_f_unificado(r/1e6, i) for r,i in zip(receitas,intensidades)])

        if sem_reti:
            pnd_total = pnd_base
            renuncia = 0
            bf_total = 0
        else:
            custo = p['multiplicador'] * fatores * 0.34

            delta = pnd_base * np.abs(elasticidade) * custo
            pnd_total = pnd_base + delta

            estoque_pnd += delta

            historico_pnd.pop(0)
            historico_pnd.append(delta.copy())

            # Fiscal
            imp_ref = receitas * 0.32 * 0.34
            ded = p['multiplicador'] * pnd_total * fatores * 0.34

            credito_max = receitas * 0.32 * 0.75 * 0.34
            inc = np.minimum(ded, credito_max)

            novos = np.maximum(0, ded - inc)

            estoque_credito.pop()
            estoque_credito.insert(0, novos)

            estoque_total = sum(estoque_credito)

            uso_limite = np.minimum(estoque_total.sum(), (imp_ref.sum() - inc.sum()) * 0.5)

            uso = 0
            for i in range(4, -1, -1):
                disponivel = estoque_credito[i].sum()
                consumir = min(disponivel, uso_limite - uso)
                if disponivel > 0:
                    estoque_credito[i] *= (1 - consumir / disponivel)
                uso += consumir

            imp_pago = max(imp_ref.sum()*0.25, imp_ref.sum() - inc.sum() - uso)
            renuncia = imp_ref.sum() - imp_pago

            bf_total = delta.sum() * (
                p['s_sal']*p['a_potec'] +
                p['s_ins']*p['a_iva'] +
                p['s_cons']*p['a_cons']
            )

        anual.append({
            "Ano": ano,
            "Renuncia_Bi": renuncia/1e9,
            "BF_Bi": bf_total/1e9,
            "PND_Bi": pnd_total.sum()/1e9,
            "Passivo_Bi": sum(estoque_credito).sum()/1e9,
            "N": len(receitas)
        })

    return pd.DataFrame(anual)

# =========================================================
# 3. SIDEBAR (TOTAL CONTROLE RESTAURADO)
# =========================================================

st.sidebar.title("🏛️ Parâmetros")

p = {
    'n_empresas': st.sidebar.number_input("Firmas",1000,10000,3000),
    'rec_media_mm': st.sidebar.slider("Receita média",1.0,150.0,15.0),
    'intensidade_pnd': st.sidebar.slider("Intensidade P&D",0.01,0.2,0.07),
    'taxa_g_base': st.sidebar.slider("Crescimento",0.0,0.05,0.02),
    'taxa_entrada_liq': st.sidebar.slider("Entrada líquida",-0.02,0.05,0.005),
    'bonus_entrada_reti': st.sidebar.slider("Bônus RETI",0.0,0.03,0.01),
    'e_ptf': st.sidebar.slider("Elasticidade PTF",0.0,0.01,0.003),
    'e_custo': st.sidebar.slider("Elasticidade custo",-2.0,-0.5,-1.27),
    'alpha_het': st.sidebar.slider("Heterogeneidade",0.0,0.5,0.2),
    'multiplicador': st.sidebar.slider("Multiplicador",1.0,1.6,1.25),
    'anos': st.sidebar.slider("Horizonte",5,20,10),
    'taxa_desc': st.sidebar.slider("Desconto",0.0,0.15,0.06),
    's_sal':0.65,'a_potec':0.28,'s_ins':0.25,'a_iva':0.18,'s_cons':0.10,'a_cons':0.10
}

# =========================================================
# 4. MONTE CARLO (SEM QUEBRAR UX)
# =========================================================

def rodar_mc(p, n_sim=20):
    sims = []
    for s in range(n_sim):
        sims.append(simular_micro(p, False, seed=s))
    return pd.concat(sims).groupby("Ano").mean().reset_index()

df_com = rodar_mc(p)
df_sem = simular_micro(p, True)

# =========================================================
# 5. KPIs SPE
# =========================================================

delta = (df_com["PND_Bi"] - df_sem["PND_Bi"]).sum()
ren = df_com["Renuncia_Bi"].sum()

df_com["desc"] = 1/(1+p['taxa_desc'])**df_com["Ano"]

npv_ren = (df_com["Renuncia_Bi"]*df_com["desc"]).sum()
npv_bf = (df_com["BF_Bi"]*df_com["desc"]).sum()

# =========================================================
# 6. DASHBOARD
# =========================================================

st.title("📊 RETI — Simulador Fiscal")

c1,c2,c3,c4 = st.columns(4)

c1.metric("Δ P&D",f"{delta:.1f} Bi")
c2.metric("Elasticidade",f"{delta/ren:.2f}x")
c3.metric("NPV Líquido",f"{npv_bf-npv_ren:.1f} Bi")
c4.metric("Passivo",f"{df_com['Passivo_Bi'].iloc[-1]:.1f} Bi")

fig = go.Figure()

fig.add_trace(go.Scatter(x=df_com["Ano"],y=df_com["Renuncia_Bi"],name="Renúncia"))
fig.add_trace(go.Scatter(x=df_com["Ano"],y=df_com["BF_Bi"],name="Backflow"))
fig.add_trace(go.Scatter(x=df_com["Ano"],y=df_com["Passivo_Bi"],name="Passivo"))

st.plotly_chart(fig, use_container_width=True)

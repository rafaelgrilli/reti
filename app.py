import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────────
# 1. FUNÇÕES BASE
# ─────────────────────────────────────────────

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

# ─────────────────────────────────────────────
# 2. MOTOR MICRO (CORRETO)
# ─────────────────────────────────────────────

def simular_micro(p, sem_reti=False, seed=0):
    np.random.seed(seed)

    n = p['n_empresas']

    # heterogeneidade inicial
    mu = np.log(p['rec_media_mm']) - (0.8**2)/2
    receitas = np.random.lognormal(mu, 0.8, n) * 1e6

    intensidades = np.clip(
        np.random.normal(p['intensidade_pnd'], 0.03, n), 0.01, 0.4
    )

    # choque idiossincrático
    shock = np.random.lognormal(0, 0.2, n)

    estoques_pnd = np.zeros(n)

    # FIFO real: lista de listas por firma
    estoque_fifo = [ [0]*5 for _ in range(n) ]

    historico_pnd = [np.zeros(n) for _ in range(3)]

    anual = []

    for ano in range(1, p['anos']+1):

        # mortalidade
        sobrevivencia = np.random.uniform(0,1,n) > p['taxa_mortalidade']
        receitas = receitas[sobrevivencia]
        intensidades = intensidades[sobrevivencia]
        shock = shock[sobrevivencia]
        estoques_pnd = estoques_pnd[sobrevivencia]
        historico_pnd = [h[sobrevivencia] for h in historico_pnd]
        estoque_fifo = [estoque_fifo[i] for i in range(len(estoque_fifo)) if sobrevivencia[i]]

        n_atual = len(receitas)

        # entrada
        taxa_entrada = p['taxa_entrada_liq'] + (0 if sem_reti else p['bonus_entrada_reti'])
        n_new = int(n_atual * taxa_entrada)

        if n_new > 0:
            novas_rec = np.random.lognormal(mu,0.8,n_new)*1e6
            novas_int = np.clip(np.random.normal(p['intensidade_pnd'],0.03,n_new),0.01,0.4)
            receitas = np.concatenate([receitas, novas_rec])
            intensidades = np.concatenate([intensidades, novas_int])
            shock = np.concatenate([shock, np.random.lognormal(0,0.2,n_new)])
            estoques_pnd = np.concatenate([estoques_pnd, np.zeros(n_new)])
            for i in range(3):
                historico_pnd[i] = np.concatenate([historico_pnd[i], np.zeros(n_new)])
            estoque_fifo += [[0]*5 for _ in range(n_new)]

        # produtividade com lag
        est_def = historico_pnd[0]
        g = p['taxa_g_base'] + (0 if sem_reti else p['e_ptf'] * np.log(1+est_def/(receitas+1)))

        receitas *= (1 + g)

        pnd_base = receitas * intensidades

        # restrição de caixa (proxy)
        limite_caixa = receitas * 0.15

        elasticidade = p['e_custo'] * shock

        fatores = np.array([fator_f_unificado(r/1e6, i) for r,i in zip(receitas,intensidades)])

        if sem_reti:
            d_pnd = np.zeros(len(receitas))
        else:
            c_marginal = p['multiplicador'] * fatores * 0.34
            d_pnd = pnd_base * np.abs(elasticidade) * c_marginal
            d_pnd = np.minimum(d_pnd, limite_caixa)

        pnd_total = pnd_base + d_pnd

        # imposto
        imp_ref = receitas * 0.32 * 0.34

        ded = p['multiplicador'] * pnd_total * fatores * 0.34
        inc = np.minimum(ded, receitas*0.32*0.75*0.34)

        novos_creditos = np.maximum(0, ded - inc)

        uso_total = np.zeros(len(receitas))

        # FIFO por firma
        for i in range(len(receitas)):
            estoque_fifo[i].insert(0, novos_creditos[i])
            estoque_fifo[i] = estoque_fifo[i][:5]

            limite = (imp_ref[i] - inc[i]) * 0.5
            uso = 0

            for idade in range(4,-1,-1):
                disponivel = estoque_fifo[i][idade]
                usar = min(disponivel, limite - uso)
                estoque_fifo[i][idade] -= usar
                uso += usar
                if uso >= limite:
                    break

            uso_total[i] = uso

        imp_pago = np.maximum(imp_ref*0.25, imp_ref - inc - uso_total)
        renuncia = imp_ref - imp_pago

        # backflow com lag (simples: 1 ano)
        bf = d_pnd * (p['s_sal']*p['a_potec'] + p['s_ins']*p['a_iva'] + p['s_cons']*p['a_cons'])

        historico_pnd.pop(0)
        historico_pnd.append(d_pnd)

        # passivo
        passivo = np.array([sum(f) for f in estoque_fifo])

        # sanity check
        receitas = np.maximum(receitas,1)
        pnd_total = np.minimum(pnd_total, receitas)

        anual.append({
            "Ano": ano,
            "Renuncia": renuncia.sum(),
            "Backflow": bf.sum(),
            "Passivo": passivo.sum(),
            "P&D": pnd_total.sum()
        })

    return pd.DataFrame(anual)

# ─────────────────────────────────────────────
# 3. MONTE CARLO CORRETO
# ─────────────────────────────────────────────

def rodar_mc(p, n_sim=20):
    results = []

    for s in range(n_sim):
        com = simular_micro(p, False, seed=s)
        sem = simular_micro(p, True, seed=s)

        df = com.copy()
        df["Delta_P&D"] = com["P&D"] - sem["P&D"]

        # NPV por simulação
        fator = 1 / ((1+p['taxa_desc']) ** df["Ano"])
        npv_ren = (df["Renuncia"]*fator).sum()
        npv_bf = (df["Backflow"]*fator).sum()

        results.append({
            "npv": npv_bf - npv_ren,
            "roi": npv_bf / npv_ren if npv_ren>0 else 0
        })

    return pd.DataFrame(results)

# ─────────────────────────────────────────────
# 4. UI
# ─────────────────────────────────────────────

st.title("RETI — Simulador 10/10 (Policy Grade)")

p = {
    'n_empresas': 2000,
    'rec_media_mm': 15,
    'intensidade_pnd': 0.07,
    'taxa_g_base': 0.02,
    'taxa_entrada_liq': 0.005,
    'bonus_entrada_reti': 0.01,
    'taxa_mortalidade': 0.02,
    'e_custo': -1.2,
    'e_ptf': 0.003,
    'multiplicador': 1.25,
    'anos': 10,
    'taxa_desc': 0.06,
    's_sal': 0.65, 'a_potec':0.28,
    's_ins':0.25,'a_iva':0.18,
    's_cons':0.10,'a_cons':0.10
}

mc = rodar_mc(p, n_sim=30)

# KPIs com distribuição
st.metric("NPV Médio", f"{mc['npv'].mean():.2f}")
st.metric("NPV P10", f"{mc['npv'].quantile(0.1):.2f}")
st.metric("NPV P90", f"{mc['npv'].quantile(0.9):.2f}")
st.metric("ROI Médio", f"{mc['roi'].mean():.2f}x")

# gráfico distribuição
fig = go.Figure()
fig.add_histogram(x=mc["npv"])
fig.update_layout(title="Distribuição do NPV")
st.plotly_chart(fig, use_container_width=True)

# export auditável
csv = mc.to_csv(index=False).encode()
st.download_button("Download Resultados (CSV)", csv, "reti_sim.csv")

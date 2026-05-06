import numpy as np
import pandas as pd

# ─────────────────────────────────────────────
# 1. PARÂMETROS ESTRUTURAIS
# ─────────────────────────────────────────────

ALIQUOTA = 0.34
PRESUNCAO = 0.32

BETA_PTF = 0.06
MULT_INDIRETO = 1.3

LAG_PTF = 3
DEPREC = 0.15
SUCESSO = 0.70


# ─────────────────────────────────────────────
# 2. FUNÇÕES ECONÔMICAS
# ─────────────────────────────────────────────

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
    # evita explosão não linear
    return incentivo / (1 + incentivo)


def adicionalidade_pd(pd_base, elasticidade, incentivo):
    return pd_base * abs(elasticidade) * custo_relativo(incentivo)


def base_reti(receita, pd_total, F, multiplicador):
    base = receita * PRESUNCAO
    
    # piso implícito (consistência tributária)
    base_min = base * 0.25
    
    base_reduzida = max(base_min, base - (multiplicador * pd_total * F))
    
    return base, base_reduzida


def difusao_firmas(n, t):
    return n / (1 + np.exp(-1.2 * (t - 3)))


# ─────────────────────────────────────────────
# 3. MOTOR PRINCIPAL (MICRO + MACRO)
# ─────────────────────────────────────────────

def simular_reti(params):

    horizonte = params['horizonte']
    receita = params['rec_inicial']

    historico_pd = np.zeros(horizonte + LAG_PTF + 5)
    estoque_conhecimento = 0

    intensidade_anterior = 0

    resultados = []

    for t in range(1, horizonte + 1):

        receita_ant = receita
        receita *= (1 + params['crescimento'])

        crescimento = (receita / receita_ant) - 1

        # ───────────────
        # GATILHO PERFORMANCE
        # ───────────────
        if t > 3:
            pode_usar = (
                crescimento >= 0.10 or
                params["potec"] >= 0.15
            )
        else:
            pode_usar = True

        # ───────────────
        # P&D
        # ───────────────
        pd_base = receita * params['intensidade_pd']

        F = fator_porte(receita)

        incentivo = params['multiplicador'] * F * ALIQUOTA

        pd_extra = adicionalidade_pd(pd_base, params['elasticidade'], incentivo)

        pd_total = pd_base + pd_extra

        # ───────────────
        # BASE RETI
        # ───────────────
        if pode_usar:
            base, base_red = base_reti(receita, pd_total, F, params['multiplicador'])
            ren_unit = (base - base_red) * ALIQUOTA
        else:
            ren_unit = 0

        # ───────────────
        # DIFUSÃO
        # ───────────────
        firmas = difusao_firmas(params['n_firmas'], t)

        ren_macro = (ren_unit * firmas) / 1000

        # ───────────────
        # ACÚMULO TECNOLÓGICO
        # ───────────────
        if t + LAG_PTF < len(historico_pd):
            historico_pd[t + LAG_PTF] = pd_extra * SUCESSO

        estoque_conhecimento = (
            estoque_conhecimento * (1 - DEPREC)
            + historico_pd[t]
        )

        # ───────────────
        # PTF (CORRETO: DELTA)
        # ───────────────
        intensidade_pd = pd_total / receita if receita > 0 else 0

        delta_intensidade = intensidade_pd - intensidade_anterior
        intensidade_anterior = intensidade_pd

        delta_ptf = BETA_PTF * delta_intensidade

        # ───────────────
        # ROI FISCAL (DECOMPOSTO)
        # ───────────────
        ret_base = receita * delta_ptf * ALIQUOTA
        ret_indireto = ret_base * (MULT_INDIRETO - 1)
        ret_estrutural = estoque_conhecimento * 0.01  # proxy conservadora

        retorno_total = ret_base + ret_indireto + ret_estrutural

        ret_macro = (retorno_total * firmas) / 1000

        resultados.append({
            "Ano": t,
            "Receita": receita,
            "P&D Base": pd_base,
            "P&D Extra": pd_extra,
            "P&D Total": pd_total,
            "Renúncia": ren_macro,
            "Retorno": ret_macro,
            "Saldo": ret_macro - ren_macro,
            "Fator_F": F,
            "Pode_Usar": pode_usar,
            "Intensidade_PD": intensidade_pd
        })

    df = pd.DataFrame(resultados)
    df["Acumulado"] = df["Saldo"].cumsum()

    return df


# ─────────────────────────────────────────────
# 4. MÓDULO FISCAL (GOVERNANÇA)
# ─────────────────────────────────────────────

def avaliar_fiscal(df, teto):

    return {
        "custo_total": df["Renúncia"].sum(),
        "custo_pico": df["Renúncia"].max(),
        "violou": df["Renúncia"].max() > teto
    }


def ajustar_politica(params, avaliacao):

    if not avaliacao["violou"]:
        return params

    novo = params.copy()

    # ORDEM DA PROPOSTA:

    # 1. multiplicador
    novo["multiplicador"] *= 0.9

    # 2. fator F (via scaling global)
    novo["ajuste_F"] = novo.get("ajuste_F", 1.0) * 0.95

    # 3. intensidade mínima
    novo["intensidade_pd"] *= 0.97

    return novo


# ─────────────────────────────────────────────
# 5. SIMULAÇÃO DE POLÍTICA (MULTI-RODADA)
# ─────────────────────────────────────────────

def simular_politica(params, rodadas=3):

    historico = []

    for r in range(rodadas):

        df = simular_reti(params)

        avaliacao = avaliar_fiscal(df, params["teto_lrf"])

        historico.append({
            "rodada": r,
            "params": params.copy(),
            "avaliacao": avaliacao,
            "df": df
        })

        params = ajustar_politica(params, avaliacao)

    return historico

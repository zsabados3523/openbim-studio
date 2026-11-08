# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T15n (parte c): caixas por pontos do face set.
Ref: docs/state/cards/F0-S06/F0-S06-T15n-caixas-rapidas.md.
"""
from __future__ import annotations

import pytest
from s06_t15n_aux import *  # noqa: F401,F403


def test_contratos_vazio_e_arquivo_divergente(tmp_path):
    f, pavs = base()
    peca(f, pavs[0], "F1", "poly", (1.0, 1.0, 0.0))
    arq, g = abrir(f, tmp_path)
    p = ped(arq, g, "F1")
    r = local.executar(dict(p, elementos=[]))
    assert r == {"ok": True, "caixas_envolventes": {}, "falhas_geometria": [], "passagens_iterator": 0, "erros_iterator": []}
    r = local.executar(dict(p, elementos=[[p["elementos"][0][0], "GUID-ERRADO"]]))
    assert r["ok"] is False and r["erro"]["tipo"] == "ArquivoDivergente"


# ---------- 7. ponto não usado nunca encolhe a caixa ----------
@pytest.mark.parametrize("tipo", ["poly", "tri"])
def test_ponto_nao_usado_nao_reduz_a_caixa(tmp_path, tipo):
    """Conservador: caixa >= iterator (que só vê pontos usados) e igual quando todos os pontos são usados. Se a implementação
    ignorar pontos órfãos (igualdade exata) o teste também passa; só proíbe caixa MENOR que a do iterator."""
    f, pavs = base()
    peca(f, pavs[0], "Todos", tipo, (1.0, 1.0, 0.0))
    peca(f, pavs[0], "Orfao", tipo, (1.0, 1.0, 0.0), extra=(9.0, 9.0, 9.0))
    arq, g = abrir(f, tmp_path)
    p = ped(arq, g, "Todos", "Orfao")
    ids = [e[0] for e in p["elementos"]]
    ref = ref_iterator(arq, ids)
    res = local.executar(p)
    assert res["ok"] is True
    iguais(res, ref, ids[:1])
    got, r = res["caixas_envolventes"][str(ids[1])], ref[ids[1]]
    assert all(got[k] <= r[k] + TOL for k in range(3)) and all(got[k] >= r[k] - TOL for k in range(3, 6)), (got, r)

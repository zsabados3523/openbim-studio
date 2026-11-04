# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ajudantes comuns dos oráculos da F0-S06-T11 (ver contrato em `test_s06_t11_reassociacao_oraculo.py`)."""


def _mod():
    import openbim_app.reassociacao as m
    return m


def el(guid, classe="IfcWall", nome="P1", tag="T1", x=0.0, y=0.0, z=0.0, caixa="auto"):
    if caixa == "auto":
        caixa = (x, y, z, x + 1.0, y + 1.0, z + 1.0)
    return {"guid": guid, "classe": classe, "nome": nome, "tag": tag, "caixa": caixa}


def antigos():
    return {"V1": [el("a1", tag="T1"), el("a2", tag="T2", nome="P2", x=5.0)], "V2": [el("a1", tag="T1")]}


def atuais_ok():
    return [el("n1", tag="T1"), el("n2", tag="T2", nome="P2", x=5.0)]


def P(vistas, atuais, **kw):
    return _mod().propor(vistas, atuais, **kw)


def ids(lista):
    return [(e["vista"], e["guid_antigo"], e.get("guid_novo")) for e in lista]

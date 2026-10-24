# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gerador do oráculo do F0-S05-T04 (`tests/s05_t04_aux.py`), validado HOJE sem o módulo novo (sem `@AINDA_NAO`; quem implementa não edita):
pisos do sorteio em 101 sementes; a régua pega uma mutação de cada um dos 12 tipos de operação (e 0 diferenças ao desfazer); a rodada inteira do
caso 1 (10.000 operações, semente 20261023) sobre o ifcopenshell cru, num pytest filho: modelo segue o plano, pisos, gravar e reabrir, desfazer
tudo = inicial, refazer tudo = final, conferência a cada 500 transações."""
import os

import pytest
import s05_t04_aux as A
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401  (fixtures)


def test_plano_pisos_em_101_sementes():  # o MESMO gerador dos casos, só o sorteio (sem ifcopenshell)
    base, piores = [f"b{i:03d}" for i in range(300)], []
    for sem in [A.SEMENTE] + list(range(1, 101)):
        cont, n_tx, mistas = A.contar(A.Plano(sem, base))
        assert min(cont[t] for t in A.TIPOS) >= A.PISO_TIPO and mistas >= A.PISO_MISTAS, f"semente {sem}: {dict(cont)}, {mistas} mistas"
        piores.append((min(cont[t] for t in A.TIPOS), mistas, cont["parede"], n_tx))
    print(f"\nMEDIDA plano (101 sementes): menor por tipo {min(p[0] for p in piores)}, menor mistas {min(p[1] for p in piores)}, paredes criadas "
          f"{min(p[2] for p in piores)} a {max(p[2] for p in piores)}, transações {min(p[3] for p in piores)} a {max(p[3] for p in piores)}")


def test_regua_pega_um_mutante_de_cada_tipo_de_operacao(base_ifc):
    f, c, plano = A.montar(base_ifc)
    d = A.Cru(f, c)
    d.tx([plano.op("pset_criar"), plano.op("lado_criar")])
    a, est = d.foto(), plano.estado()
    for t in A.TIPOS:
        d.tx([plano.op(t)])
        assert A.R.diferencas(a, d.foto()), f"mutante {t}: a régua não viu"
        d.desfazer()
        assert A.R.diferencas(a, d.foto()) == [], f"mutante {t}: desfeito e ainda diferente"
        plano.restaurar(est)


def pesado_cru_10k():  # o gerador real sobre o ifcopenshell cru: régua, pisos e desfazer nativo inteiros
    f, c, plano = A.montar(os.environ["OBIM_S05_T04_BASE"])
    A.dez_mil(A.Cru(f, c), plano)


PESADOS = sorted(k for k in list(globals()) if k.startswith("pesado_"))
if A.DENTRO:
    for _k in PESADOS:
        globals()["test_" + _k] = (lambda fn: lambda: fn())(globals()[_k])
else:
    @pytest.mark.parametrize("caso", [pytest.param(k, marks=getattr(globals()[k], "pytestmark", [])) for k in PESADOS])
    def test_pesado_em_subprocesso(caso, base_ifc):  # noqa: F811
        A.rodar_filho(__file__, caso, base_ifc)

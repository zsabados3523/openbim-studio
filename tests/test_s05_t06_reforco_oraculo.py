# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reforço do oráculo do F0-S05-T06 (achados do lote Opus 80). Mesmo contrato de `test_s05_t06_gravacao_atomica_oraculo.py`,
cujos utilitários este arquivo usa; quem implementa não edita este arquivo. Acréscimos ao contrato (ADR-002 §4.5, sem nome novo):
5. A espera entre tentativas da troca é `time.sleep` do módulo `time`, chamado na hora: 0,05 s antes da 2a tentativa, dobrando
   (0,05; 0,1; 0,2; 0,4; 0,8 = cerca de 1,55 s), nenhuma espera depois da última. O oráculo troca `time.sleep` e não espera de verdade.
6. A cópia do `.bak` (quando `os.link` falha) passa por `shutil` (`copy2`, `copy` ou `copyfile`); se ela falhar, a etapa `bak`
   falha e o `.bak` antigo, o destino e a pasta ficam como estavam (nada de apagar o `.bak` antes de ter a cópia nova pronta).
Mutantes que estes casos matam (lote 80): `fsync` no destino antigo em vez do temporário (R1); tentativas sem espera (R2); `.bak`
antigo apagado antes da cópia (R3)."""
import errno
import os
import shutil
import time

import pytest
from test_s05_t06_gravacao_atomica_oraculo import A, B, C, Registro, TrocaRecusada, confere_falha, esc, ga, link_quebrado, problemas


@pytest.fixture(autouse=True)
def _sem_injecao(monkeypatch):
    monkeypatch.delenv("OBIM_S05_FALHA_EM", raising=False)
    monkeypatch.delenv("OBIM_S05_MORRER_EM", raising=False)


@pytest.fixture
def casa(tmp_path):
    (tmp_path / "Casa.ifc").write_bytes(B), (tmp_path / "Casa.ifc.bak").write_bytes(A)  # estado depois de gravar A e depois B
    return tmp_path / "Casa.ifc"


@pytest.fixture
def esperas(monkeypatch):
    feitas = []
    monkeypatch.setattr(time, "sleep", feitas.append)
    return feitas


def copia_quebrada(*a, **k):
    raise OSError(errno.EIO, "cópia recusada (teste)")


def test_r1_fsync_e_do_temporario_antes_da_troca(casa, monkeypatch):
    """G1: o arquivo que vira o destino (o temporário, mesmo inodo depois de `os.replace`) passou por `fsync` antes da troca."""
    m = ga()
    r = Registro(casa, monkeypatch)
    m.gravar_atomico(casa, esc(C))
    pos = r.inodos.get(os.stat(casa).st_ino)
    assert pos is not None and pos < r.eventos.index("troca"), f"G1: temporário sem fsync antes da troca: {r.eventos}"
    assert problemas(casa.parent, destino=C, bak=B) == []


@pytest.mark.parametrize("recusas", [3, 10**6], ids=["recusada_3_vezes", "sempre_recusada"])
def test_r2_espera_entre_tentativas(casa, monkeypatch, esperas, recusas):
    m = ga()
    falso = TrocaRecusada(casa, recusas)
    monkeypatch.setattr(os, "replace", falso)
    if recusas == 3:
        m.gravar_atomico(casa, esc(C))
        esperado = [0.05, 0.1, 0.2]
    else:
        with pytest.raises(m.FalhaGravacao) as ei:
            m.gravar_atomico(casa, esc(C))
        confere_falha(ei.value, "trocar", "arquivo_em_uso")
        esperado = [0.05, 0.1, 0.2, 0.4, 0.8]
    assert esperas == pytest.approx(esperado), f"esperas {esperas}, tentativas {falso.tentativas}"
    assert sum(esperas) >= sum(esperado) - 1e-9


def test_r3_copia_do_bak_falha_e_bak_antigo_fica(casa, monkeypatch):
    m = ga()
    monkeypatch.setattr(os, "link", link_quebrado)
    for nome in ("copy2", "copy", "copyfile"):
        monkeypatch.setattr(shutil, nome, copia_quebrada)
    with pytest.raises(m.FalhaGravacao) as ei:
        m.gravar_atomico(casa, esc(C))
    confere_falha(ei.value, "bak", "outro")
    assert problemas(casa.parent, destino=B, bak=A) == []

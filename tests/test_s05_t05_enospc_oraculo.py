# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S05-T05, parte 3: disco cheio de verdade no `anotar` (achado ALTO do lote Opus 82; quem implementa não edita). CONTRATO: o de
`test_s05_t05_diario_oraculo.py` (item 8: o diário fica sem resto do registro que falhou e o próximo `anotar` segue com o `seq` seguinte), com o
objeto de arquivo REAL do Python (`io.FileIO`, sob `io.BufferedWriter` como `open(..., "wb")` devolve), sem ponto de teste do módulo. Disco cheio
= a escrita aceita só os CABE primeiros bytes (escrita curta) e depois levanta `OSError(ENOSPC)`. Registro pequeno (cabe no buffer de 8 KB) e
grande. Corte do resto que também falha: diário QUEBRADO, aquele `anotar` levanta e todo `anotar` seguinte recusa com `transacao.HistoricoQuebrado`
sem escrever. O oráculo troca na hora `open` (binário), `io.FileIO`, `os.write` e `os.ftruncate` só para o diário; o diário escreve e corta por
um deles. `@AINDA_NAO` (xfail estrito, como nas partes 1 a 3): o autor do oráculo tira depois do conserto do `diario.py`."""
import builtins
import errno
import io
import os

import pytest
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401  (fixtures)
from s05_t05_aux import caminho_diario, igual, mod, recuperar
from test_s05_t05_diario_oraculo import _sem_injecao, casa, local, sessoes  # noqa: F401  (fixtures)

CABE = 7


class Disco:  # livre: None = sem limite; n = bytes que ainda cabem. corte_falha: truncate e ftruncate do diário recusam
    livre, corte_falha, caminhos = None, False, []


def _escrever(real, b):
    if Disco.livre is None: return real(b)  # noqa: E701
    if Disco.livre <= 0: raise OSError(errno.ENOSPC, "No space left on device (ensaio)")  # noqa: E701
    n = real(bytes(memoryview(b)[:Disco.livre]))
    Disco.livre -= n
    return n


def _cortar(real, *a):
    if Disco.corte_falha: raise OSError(errno.EIO, "corte recusado (ensaio)")  # noqa: E701
    return real(*a)


class Raw(io.FileIO):
    def write(self, b):
        return _escrever(super().write, b) if str(self.name).endswith("diario.obimlog") else super().write(b)

    def truncate(self, size=None):
        return _cortar(super().truncate, size) if str(self.name).endswith("diario.obimlog") else super().truncate(size)


@pytest.fixture
def disco(monkeypatch, local):
    abrir, wr, ftr, Disco.caminhos = builtins.open, os.write, os.ftruncate, [str(caminho_diario(local))]

    def open_(f, mode="r", buffering=-1, *a, **k):
        if not (str(f).endswith("diario.obimlog") and "b" in mode and set(mode) & set("wax+")):
            return abrir(f, mode, buffering, *a, **k)
        raw = Raw(f, mode.replace("b", ""))
        return raw if buffering == 0 else (io.BufferedRandom if "+" in mode else io.BufferedWriter)(raw)

    def eh(fd):
        return any(os.path.exists(c) and os.path.samestat(os.fstat(fd), os.stat(c)) for c in Disco.caminhos)
    for alvo, nome, v in ((builtins, "open", open_), (io, "open", open_), (io, "FileIO", Raw),
                          (os, "write", lambda fd, b: _escrever(lambda x: wr(fd, x), b) if eh(fd) else wr(fd, b)),
                          (os, "ftruncate", lambda fd, n: _cortar(ftr, fd, n) if eh(fd) else ftr(fd, n))):
        monkeypatch.setattr(alvo, nome, v)
    yield Disco
    Disco.livre, Disco.corte_falha = None, False


def _tx(s, tipo):  # transação de uma operação: "nome" = registro pequeno, "parede" = grande (mais que o buffer)
    s.pilha.append(s.plano.estado())
    try:
        s.r.tx([s.plano.op(tipo)])
    except BaseException:
        s.plano.restaurar(s.pilha.pop())
        raise
    s.fut.clear()


@pytest.mark.parametrize("tipo, cabe", [("nome", CABE), ("parede", CABE), ("parede", 5000)])  # 5000: resto maior que a linha seguinte
def test_8a_disco_cheio_no_anotar_nao_suja_o_diario(local, casa, sessoes, disco, tipo, cabe):
    D = mod()
    s, cam = sessoes(casa), caminho_diario(local)
    s.passo("transacao"), s.passo("transacao")
    f0, disco.livre = s.foto(), cabe
    with pytest.raises(OSError) as e:
        _tx(s, tipo)
    assert disco.livre == 0, "o registro que falhou era menor que o pedaço que cabia"
    assert e.value.errno == errno.ENOSPC, e.value
    igual(s.foto(), f0, "disco cheio no anotar: o passo não voltou")
    disco.livre = None  # o usuário liberou espaço e segue trabalhando
    _tx(s, "nome")
    assert D.ler_diario(str(cam))[1] == [], "sobrou resto do registro que falhou depois da linha seguinte"
    s.passo("transacao"), s.passo("desfazer")
    regs, av = D.ler_diario(str(cam))
    seqs = [r["seq"] for r in regs]
    assert av == [] and [r["tipo"] for r in regs] == ["base"] + ["transacao"] * 4 + ["desfazer"], ([r["tipo"] for r in regs], av)
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs))), f"seq repetido ou com buraco: {seqs}"
    f, av2, _, _ = recuperar(casa, cam)
    igual(f, s.foto(), "recuperar depois do disco cheio: só os passos confirmados")
    assert av2 == []


def test_8b_corte_que_falha_quebra_o_diario(local, casa, sessoes, disco):
    D = mod()
    import openbim_app.transacao as T
    s, cam = sessoes(casa), caminho_diario(local)
    s.passo("transacao"), s.passo("transacao")
    f0, disco.livre, disco.corte_falha = s.foto(), CABE, True
    with pytest.raises((OSError, T.HistoricoQuebrado)):
        _tx(s, "nome")
    igual(s.foto(), f0, "disco cheio e corte recusado: o passo não voltou")
    disco.livre, disco.corte_falha = None, False
    tam = cam.stat().st_size
    for k in ("transacao", "desfazer"):
        with pytest.raises(T.HistoricoQuebrado):
            s.passo(k)
        igual(s.foto(), f0, f"diário quebrado: {k} mudou o modelo")
    assert cam.stat().st_size == tam, "diário quebrado: um anotar seguinte escreveu"
    f, _, _, _ = recuperar(casa, cam)
    igual(f, f0, "recuperar do diário quebrado: só o que foi confirmado antes")
    assert [r["tipo"] for r in D.ler_diario(str(cam))[0]] == ["base", "transacao", "transacao"]

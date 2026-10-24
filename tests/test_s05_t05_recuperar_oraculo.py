# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S05-T05, parte 2: morte e recuperação (cartão F0-S05-T05, itens 2 a 6; ADR-002 §4.4 e §4.7). CONTRATO: o cabeçalho de
`test_s05_t05_diario_oraculo.py` (quem implementa não edita nenhum dos dois). "Igual" = foto por conteúdo da régua do T04 (`s05_conteudo_aux`),
modelo e lateral, sem tolerância; toda recuperação passa por `s05_t05_aux.recuperar`, que confere P5 (nada gravado na pasta do Casa.ifc) e o
desfazer vazio. Processos filhos (`s05_t05_aux.filho`): morte em ponto fixo (`OBIM_S05_MORRER_EM`, código 86) em transacao, desfazer e refazer;
e N_MORTES = 50 mortes por `kill` do pai em hora sorteada (semente SEMENTE + 5), em cada sistema (Linux e Windows). Cada ação que o filho
confirmou (linha "ok") está no diário; no máximo uma a mais (a que morreu entre o registro e o "ok"). A morte sorteada é `kill` do pai (mais
forte que o `os._exit` do item 2 do cartão: cai em qualquer instrução). Achados do lote 80 (cartão): 6c exige corrigir o `_mover` do T04 (o
`KeyError` do `_repor` hoje esconde o erro e o IFC não é refeito; a "ligação mínima" em `transacao.py` que o cartão permite); 6d, o `file.add`
fora da transação, se recupera pelo diário. Os testes `test_regua_*` provam os utilitários e valem já (sem `@AINDA_NAO`)."""
import collections
import random
import re
import threading
import time

import pytest
import s05_t05_aux as X
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401  (fixtures)
from s05_t05_aux import M_ACOES, N_MORTES, PONTOS, SEMENTE, acoes, caminho_diario, igual, mod, recuperar
from test_s05_t05_diario_oraculo import _sem_injecao, casa, local, sessoes  # noqa: F401  (fixtures)

KINDS = ("transacao", "desfazer", "refazer")


def primeira(kinds, kind):  # índice (1 a n) da primeira ação `kind` a partir da 3a (já há registros antes)
    return next(i for i, k in enumerate(kinds, 1) if i >= 3 and k == kind)


def test_regua_acoes():
    a = acoes(M_ACOES)
    assert a == acoes(M_ACOES) and set(a) == set(KINDS) and all(primeira(a, k) for k in KINDS)
    h = u = 0
    for k in a:
        assert (k != "desfazer" or h) and (k != "refazer" or u), "ação impossível na sequência"
        h, u = (h + 1, 0) if k == "transacao" else (h - 1, u + 1) if k == "desfazer" else (h + 1, u - 1)


def test_regua_filho_chega_ao_mesmo_modelo(casa, tmp_path):  # sem diário: o filho e o pai fazem o MESMO modelo (GlobalId e sorteios)
    p = X.abrir_filho(casa, tmp_path / "f", M_ACOES, modo="sem_diario")
    cod, n_ok, out, _ = X.saida_filho(p, tmp_path / "f")
    assert (cod, n_ok) == (0, M_ACOES) and out[-1] == "fim " + X.digest(X.esperadas(casa, acoes(M_ACOES))[-1]), out[-1:]


def test_3_recupera_cada_tipo_e_sequencia_longa(local, casa, sessoes):
    D = mod()
    from openbim_app.sessao_modelo import SessaoModelo
    from openbim_app.transacao import Historico
    s = sessoes(casa)
    for t in X.A.TIPOS:
        s.pilha.append(s.plano.estado())
        s.r.tx([s.plano.op(t), s.plano.op("nome" if t.startswith("lado") else "lado_criar")])
        s.fut.clear()
    s.pilha.append(s.plano.estado())  # o mesmo objeto do lateral duas vezes num passo: o desfazer reaplicado volta em ordem inversa
    with s.r.s.escrever() as esc, s.r.h.transacao(esc) as t:
        X.A.aplicar(s.plano.op("nome"), t.ifc, t.lado, s.r.c)
        t.lado.criar("notas", "dupla", {"n": 1})
        t.lado.alterar("notas", "dupla", {"n": 2})
    for k in ["desfazer"] * 3 + ["refazer"] * 2 + acoes(150, SEMENTE + 6):
        s.passo(k)
    foto, avisos, arq, lat = recuperar(casa, caminho_diario(local))
    igual(foto, s.foto(), "recuperar depois dos 12 tipos e de 155 ações")
    assert avisos == [] and D.ler_diario(str(caminho_diario(local)))[1] == []
    sm = SessaoModelo(arq)
    h = Historico(sm, lat)  # o modelo recuperado aceita um histórico novo, que começa vazio
    assert not h.pode_desfazer and not h.pode_refazer
    with sm.escrever() as esc, h.transacao(esc) as t:
        t.lado.criar("notas", "depois", {"n": 1})
    assert h.pode_desfazer
    h.encerrar()


def _hora_trocada(linha):  # mesmo JSON válido, um dígito da hora trocado: o crc32 deixa de conferir
    m = re.search(rb'"hora":"(\d)', linha)
    return linha[:m.start(1)] + (b"3" if m[1] != b"3" else b"4") + linha[m.end(1):]


def test_2c_registro_cortado_ou_ruim_nunca_aplicado(local, casa, sessoes, tmp_path):
    D = mod()
    s, kinds = sessoes(casa), acoes(8)
    fotos = [s.foto()]
    for k in kinds:
        s.passo(k)
        fotos.append(s.foto())
    bruto = caminho_diario(local).read_bytes()
    ls = bruto[:-1].split(b"\n")
    ini = [sum(len(x) + 1 for x in ls[:i]) for i in range(len(ls))]
    falso = tmp_path / "falso" / "diario.obimlog"
    falso.parent.mkdir()

    def caso(dados, n_regs, foto, com_aviso, onde):
        falso.write_bytes(dados)
        regs, av = D.ler_diario(str(falso))
        assert len(regs) == n_regs and bool(av) == com_aviso, f"{onde}: {len(regs)} registros, avisos {av}"
        f, av2, _, _ = recuperar(casa, falso)
        igual(f, foto, onde)
        assert bool(av2) == com_aviso, f"{onde}: avisos de recuperar {av2}"
    for i, linha in enumerate(ls):
        caso(bruto[:ini[i]], i, fotos[max(i - 1, 0)], i == 0, f"corte no começo da linha {i}")
        for c in sorted({1, 8, 9, len(linha) // 2, len(linha)}):  # len(linha) = linha inteira sem o \n
            caso(bruto[:ini[i] + c], i, fotos[max(i - 1, 0)], True, f"linha {i} cortada em {c} de {len(linha) + 1} bytes")
    n = len(ls) - 1
    caso(bruto[:ini[n]] + _hora_trocada(ls[n]) + b"\n", n, fotos[n - 1], True, "última linha com crc errado")
    j = 4
    caso(bruto[:ini[j]] + _hora_trocada(ls[j]) + b"\n" + bruto[ini[j + 1]:], j, fotos[j - 1], True, f"linha {j} (meio) com crc errado")
    caso(bruto[:ini[j]] + b"lixo\n" + bruto[ini[j]:], j, fotos[j - 1], True, f"linha ruim antes da linha {j}")
    caso(bruto[:ini[j]] + bruto[ini[j + 1]:], j, fotos[j - 1], True, f"buraco no seq (sem a linha {j})")


def test_4_base_de_outro_arquivo_nao_aplica(local, casa, sessoes, tmp_path):
    D = mod()
    from openbim_app.lateral import Lateral
    s = sessoes(casa)
    for k in ("transacao", "transacao", "desfazer", "transacao"):
        s.passo(k)
    outra = tmp_path / "outra" / "Casa.ifc"
    outra.parent.mkdir()
    g = X.R.ifcopenshell.open(str(casa))
    g.by_type("IfcWall")[0].Name = "outro programa mexeu"  # aplicar o diário daria certo e mudaria o conteúdo
    g.write(str(outra))
    f, av, _, _ = recuperar(outra, caminho_diario(local))
    igual(f, X.R.foto(X.R.ifcopenshell.open(str(outra)), Lateral()), "base de outro sha256 foi aplicada")
    assert av, "base de outro sha256: sem aviso"
    f, av, _, _ = recuperar(casa, caminho_diario(local))
    igual(f, s.foto(), "a mesma base")
    assert av == [] and D.ler_diario(str(caminho_diario(local)))[1] == []


@pytest.mark.parametrize("ponto", PONTOS)
@pytest.mark.parametrize("kind", KINDS)
def test_2_morte_em_ponto_fixo(casa, tmp_path, ponto, kind):
    D = mod()
    kinds = acoes(M_ACOES)
    k = primeira(kinds, kind)
    fotos, pasta = X.esperadas(casa, kinds[:k]), tmp_path / "local"
    cod, n_ok, _, err = X.saida_filho(X.abrir_filho(casa, pasta, k, k, ponto), pasta)
    assert (cod, n_ok) == (86, k - 1), f"{ponto} em {kind} (ação {k}): código {cod}, {n_ok} confirmadas; {err[-1500:]}"
    feitas, cam = k if ponto == "anotar_depois" else k - 1, caminho_diario(pasta)
    regs, av = D.ler_diario(str(cam))
    assert [r["tipo"] for r in regs] == ["base"] + kinds[:feitas], f"{ponto} em {kind}: registros {[r['tipo'] for r in regs]}"
    cortado = ponto == "anotar_meio"
    assert cam.read_bytes().endswith(b"\n") != cortado, f"{ponto}: o fim do diário não é o esperado (cortado = {cortado})"
    f, av2, _, _ = recuperar(casa, cam)
    igual(f, fotos[feitas], f"morte {ponto} em {kind} (ação {k})")
    assert bool(av) == bool(av2) == cortado, f"{ponto}: avisos {av} / {av2}"


def test_2b_morte_em_hora_aleatoria(casa, tmp_path):
    D = mod()
    t0, kinds = time.monotonic(), acoes(M_ACOES)
    fotos, r, vistos = X.esperadas(casa, kinds), random.Random(SEMENTE + 5), collections.Counter()

    def rodar(i, espera):
        pasta = tmp_path / f"m{i}"
        p = X.abrir_filho(casa, pasta, M_ACOES, modo="esperar")
        cao = threading.Timer(120, p.kill)  # filho travado antes do "pronto" ou do "fim": morre e o caso falha, nunca trava o CI
        cao.start()
        assert p.stdout.readline().strip() == "pronto", f"volta {i}: o filho não abriu"
        t, lidas = time.monotonic(), []
        while espera is None and (x := p.stdout.readline()) and not x.startswith("fim"):
            lidas.append(x)
        t = time.monotonic() - t
        espera is None or time.sleep(espera)
        p.kill()
        cao.cancel()
        _, n_ok, _, _ = X.saida_filho(p, pasta)
        n_ok += sum(x.startswith("ok ") for x in lidas)
        regs, _ = D.ler_diario(str(caminho_diario(pasta)))
        k = len(regs) - 1
        assert n_ok <= k <= n_ok + 1 and [x["tipo"] for x in regs[1:]] == kinds[:k], f"volta {i}: {n_ok} confirmadas, {k} no diário"
        f, _, _, _ = recuperar(casa, caminho_diario(pasta))
        igual(f, fotos[k], f"volta {i} (semente {SEMENTE + 5}), espera {espera}, {k} registros")
        return t if espera is None else k
    dur = rodar(0, None)  # volta inteira: mede quanto o filho leva nas M_ACOES
    for i in range(1, N_MORTES + 1):
        vistos[rodar(i, r.uniform(0, dur * 1.1))] += 1
    print(f"\nMEDIDA morte aleatória: {N_MORTES} mortes, volta {dur:.2f} s, total {time.monotonic() - t0:.0f} s, registros: {sorted(vistos.items())}")
    assert len(vistos) >= 5 and any(0 < k < M_ACOES for k in vistos), f"as mortes não se espalharam: {sorted(vistos.items())}"


@pytest.mark.parametrize("ponto", PONTOS[:2])
@pytest.mark.parametrize("kind", KINDS)
def test_6_falha_do_anotar_volta_e_nao_suja_o_diario(local, casa, sessoes, monkeypatch, ponto, kind):
    D = mod()
    s, kinds = sessoes(casa), acoes(M_ACOES)
    k = primeira(kinds, kind)
    for x in kinds[:k - 1]:
        s.passo(x)
    f0 = s.foto()
    monkeypatch.setenv("OBIM_S05_FALHA_EM", ponto)
    with pytest.raises(OSError):
        s.passo(kind)
    monkeypatch.delenv("OBIM_S05_FALHA_EM")
    igual(s.foto(), f0, f"falha {ponto} em {kind}: o passo não voltou nos dois lados")
    assert not s.r.h.quebrado
    cam = caminho_diario(local)
    assert cam.read_bytes().endswith(b"\n"), f"falha {ponto}: sobrou pedaço do registro no diário"
    f, av, _, _ = recuperar(casa, cam)
    igual(f, f0, f"falha {ponto} em {kind}: recuperar")
    s.passo("transacao")
    regs, av = D.ler_diario(str(cam))
    assert av == [] and len(regs) == k + 1 and [x["seq"] for x in regs] == list(range(regs[0]["seq"], regs[0]["seq"] + k + 1))
    f, av, _, _ = recuperar(casa, cam)
    igual(f, s.foto(), f"falha {ponto} em {kind}: a transação seguinte")
    assert av == []


class _Erro(Exception):
    pass


def test_6c_lateral_falha_no_meio_do_desfazer(local, casa, sessoes):  # achado do lote 80: o KeyError do `_repor` não pode esconder o erro
    D = mod()
    s = sessoes(casa)
    s.passo("transacao")
    with s.r.s.escrever() as esc, s.r.h.transacao(esc) as t:
        t.lado.criar("notas", "b", {"n": 0})
    with s.r.s.escrever() as esc, s.r.h.transacao(esc) as t:
        X.A.aplicar(s.plano.op("nome"), t.ifc, t.lado, s.r.c)
        t.lado.criar("notas", "a", {"n": 1})
        t.lado.apagar("notas", "b")
    f0, p0, n0 = s.foto(), X.pilhas(s.r), len(D.ler_diario(str(caminho_diario(local)))[0])
    real, chamadas = s.r.lat._repor, []

    def repor(*a):
        chamadas.append(a)
        if len(chamadas) == 1:
            raise _Erro("lateral falhou no meio do desfazer (ensaio)")
        return real(*a)
    s.r.lat._repor = repor
    with pytest.raises(_Erro):
        s.r.desfazer()
    s.r.lat._repor = real
    igual(s.foto(), f0, "lateral falhou no desfazer: o IFC não foi refeito ou o lateral não voltou")
    assert X.pilhas(s.r) == p0 and not s.r.h.quebrado and len(D.ler_diario(str(caminho_diario(local)))[0]) == n0
    f, av, _, _ = recuperar(casa, caminho_diario(local))
    igual(f, f0, "recuperar depois da falha do lateral no desfazer")
    assert av == []


def test_6d_add_fora_da_transacao_recupera_pelo_diario(local, casa, sessoes):  # achado do lote 80: `file.add` deixa sobra; o diário refaz
    D = mod()
    import openbim_app.transacao as T
    s = sessoes(casa)
    for k in ("transacao", "transacao", "desfazer", "transacao"):
        s.passo(k)
    f0 = s.foto()
    with s.r.s.escrever() as esc:
        o = X.R.ifcopenshell.file(schema=esc.arquivo.schema_identifier)
        w = o.createIfcWall(X.R.ifcopenshell.guid.new(), None, "de fora", None, None,
                            o.createIfcLocalPlacement(None, o.createIfcAxis2Placement3D(o.createIfcCartesianPoint((1.0, 2.0, 3.0)))))
        with pytest.raises((T.EdicaoForaDeTransacao, T.HistoricoQuebrado)):
            esc.arquivo.add(w)
    assert s.r.h.quebrado and D.ler_diario(str(caminho_diario(local)))[1] == []
    f, av, _, _ = recuperar(casa, caminho_diario(local))
    igual(f, f0, "recuperar depois do add fora da transação (sem sobra)")
    assert av == []

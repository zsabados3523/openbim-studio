# SPDX-License-Identifier: AGPL-3.0-or-later
"""Utilitários do oráculo do F0-S05-T05 (autor do oráculo; quem implementa não edita). Contrato: `test_s05_t05_diario_oraculo.py`.
`fazer_casa` (modelo montado do T04 gravado em `<tmp>/proj/Casa.ifc`); `preparar` (reabre o Casa.ifc com GlobalId novos em sequência fixa e o
contexto do gerador refeito: o pai e o processo filho chegam ao MESMO modelo); `acoes(n)` (sequência fixa de transacao/desfazer/refazer, semente
SEMENTE + 4); `Sessao` (Historico real do T04 + Diario, um passo por ação); `esperadas` (fotos depois de cada ação, sem diário); `recuperar`
(chama `diario.recuperar` e confere P5: nada gravado na pasta do Casa.ifc); `abrir_filho` (o processo filho, que roda `filho()`)."""
import hashlib
import itertools
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

import s05_t04_aux as A
from s05_t04_aux import SEMENTE

R = A.R
AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
LADO = "lado-t04"  # o LadoId que `montar` põe no pset OBIM_Projeto
M_ACOES, N_MORTES, PONTOS = 40, 50, ("anotar_antes", "anotar_meio", "anotar_depois")


def mod():
    import openbim_app.diario as D  # primeira linha de cada caso @AINDA_NAO: hoje é ela que dá o xfail
    return D


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def caminho_diario(pasta_local, lado=LADO):
    return Path(pasta_local) / "projetos" / lado / "diario" / "diario.obimlog"


def fazer_casa(base, pasta):
    f, _, _ = A.montar(base)
    casa = Path(pasta) / "proj" / "Casa.ifc"
    casa.parent.mkdir(parents=True)
    f.write(str(casa))
    return casa


def preparar(casa):
    import ifcopenshell.guid
    import ifcopenshell.util.representation as UR
    f = R.ifcopenshell.open(str(casa))
    cont = itertools.count(10**6)
    ifcopenshell.guid.new = lambda: ifcopenshell.guid.compress("%032x" % next(cont))  # o caso restaura (`_limpa`)
    c = {"P": random.Random(SEMENTE + 1), "corpo": UR.get_context(f, "Model", "Body", "MODEL_VIEW").id(),
         "camadas": next(m.id() for m in f.by_type("IfcMaterialLayerSet") if m.LayerSetName == "T04"),
         "obim": next(p.GlobalId for p in f.by_type("IfcPropertySet") if p.Name == "OBIM_Projeto"),
         "andares": sorted(a.GlobalId for a in f.by_type("IfcBuildingStorey")),
         "g": {t.Name[5:]: t.GlobalId for t in f.by_type("IfcWallType") if re.fullmatch(r"Tipo t\d+", t.Name or "")}}
    return f, c, A.Plano(SEMENTE, [w.GlobalId for w in f.by_type("IfcWall")])


def acoes(n, semente=SEMENTE + 4):  # sempre possível: desfazer só com histórico, refazer só com refazer
    r, h, u, out = random.Random(semente), 0, 0, []
    for _ in range(n):
        x = r.random()
        k = "transacao" if x < 0.6 or h == 0 else "desfazer" if x < 0.85 else "refazer" if u else "transacao"
        h, u = (h + 1, 0) if k == "transacao" else (h - 1, u + 1) if k == "desfazer" else (h + 1, u - 1)
        out.append(k)
    return out


class Sessao:
    def __init__(s, casa, diario=True):
        from test_s05_t04_transacao_oraculo import Real
        f, c, s.plano = preparar(casa)
        s.d, kw, s.pilha, s.fut = None, {}, [], []
        if diario:
            D = mod()
            s.d = D.Diario.abrir(D.lado_id_de(f, sha(casa)), str(casa))
            kw = {"codificar": D.codificar_ifc, "anotar": s.d.anotar}
        s.r = Real(f, c, **kw)

    def passo(s, k):
        p, guarda = s.plano, (s.plano.estado(), list(s.pilha), list(s.fut))
        try:
            if k == "transacao":
                s.pilha.append(p.estado())
                s.r.tx(p.transacao(3))
                s.fut.clear()
            else:
                de, para, fn = (s.pilha, s.fut, s.r.desfazer) if k == "desfazer" else (s.fut, s.pilha, s.r.refazer)
                para.append(p.estado())
                p.restaurar(de.pop())
                assert fn() is not None, f"{k} sem nada a fazer"
        except BaseException:
            p.restaurar(guarda[0])
            s.pilha[:], s.fut[:] = guarda[1], guarda[2]
            raise

    def foto(s):
        return s.r.foto()

    def fechar(s):
        if s.d is not None:
            s.d, d = None, s.d
            d.fechar()
        s.r.h.encerrar()


def esperadas(casa, kinds):  # foto antes (0) e depois de cada ação, sem diário (o Historico do T04 sozinho)
    s = Sessao(casa, diario=False)
    fotos = [s.foto()]
    for k in kinds:
        s.passo(k)
        fotos.append(s.foto())
    s.fechar()
    return fotos


def pilhas(real):
    with real.ler() as f:
        return len(f.history), len(f.future), real.h.pode_desfazer, real.h.pode_refazer


def digest(foto):
    return hashlib.sha256(repr((sorted(foto["com"].items()), sorted(foto["sem"].items()), foto["lado"])).encode()).hexdigest()


def recuperar(casa, diario, **kw):  # devolve (foto, avisos, arquivo, lateral) e confere P5 e o histórico vazio
    D = mod()
    from openbim_app.lateral import Lateral
    pasta = Path(casa).parent
    antes = {p.name: p.read_bytes() for p in pasta.iterdir()}
    arq, lat, avisos = D.recuperar(str(casa), str(diario), **kw)
    assert {p.name: p.read_bytes() for p in pasta.iterdir()} == antes, "recuperar gravou na pasta do Casa.ifc (P5)"
    assert isinstance(avisos, list) and all(isinstance(a, str) and a.strip() for a in avisos), avisos
    assert isinstance(lat, Lateral) and arq.transaction is None and not list(arq.history) and not list(arq.future), "histórico não começou vazio"
    return R.foto(arq, lat), avisos, arq, lat


def igual(a, b, onde):
    dif = R.diferencas(a, b)
    assert not dif, f"semente {SEMENTE}, {onde}: {len(dif)} diferenças, primeiras: {dif[:6]}"


def linhas(caminho):
    return Path(caminho).read_bytes().split(b"\n")


def abrir_filho(casa, pasta_local, n, k=0, ponto="", modo="normal"):  # modo: normal, esperar (dorme depois do fim), sem_diario
    env = {x: v for x, v in os.environ.items() if x not in ("OBIM_S05_FALHA_EM", "OBIM_S05_MORRER_EM")}
    env.update(OBIM_PASTA_LOCAL=str(pasta_local), LC_ALL="C", PYTHONPATH=os.pathsep.join([str(RAIZ / "app"), str(AQUI)]))
    erro = open(Path(pasta_local).with_suffix(".err"), "w")  # arquivo, não pipe: o filho nunca trava escrevendo
    cod = f"import sys; sys.path[:0] = [{str(RAIZ / 'app')!r}, {str(AQUI)!r}]; import s05_t05_aux as X; X.filho()"
    p = subprocess.Popen([sys.executable, "-c", cod, str(casa), str(n), str(k), ponto, modo], env=env, stdout=subprocess.PIPE,
                         stderr=erro, text=True)
    erro.close()
    return p


def saida_filho(p, pasta_local, timeout=120):  # (código, ações confirmadas, linhas do stdout, stderr)
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        raise AssertionError(f"filho passou de {timeout} s")
    err = Path(pasta_local).with_suffix(".err").read_text(errors="replace")
    oks = [int(x.split()[1]) for x in out.splitlines() if x.startswith("ok ")]
    assert oks == list(range(1, len(oks) + 1)) and "Traceback" not in err, err[-3000:]
    return p.returncode, len(oks), out.splitlines(), err


def filho():  # o processo filho: abre o Casa.ifc, roda as ações e, na ação k, liga OBIM_S05_MORRER_EM=<ponto> antes do passo
    casa, n, k, ponto, modo = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5]
    s = Sessao(casa, diario=modo != "sem_diario")
    print("pronto", flush=True)
    for i, kind in enumerate(acoes(n), 1):
        if i == k:
            os.environ["OBIM_S05_MORRER_EM"] = ponto
        s.passo(kind)
        print("ok", i, flush=True)
    print("fim", digest(s.foto()) if modo == "sem_diario" else "-", flush=True)
    if modo == "esperar":
        time.sleep(600)
    s.fechar()

# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S05-T07, parte 2: morte do processo filho durante a gravação do par e reabertura (estados E1 a E10 do ADR-002 §4.5).
Mesmo contrato de `test_s05_t07_par_oraculo.py` (quem implementa não edita). O filho (`s05_t07_aux.FILHO`) abre o par, faz uma transação e grava;
morre (`os._exit(86)`) ANTES do evento k do próprio traço (`_etapa` do T06, `ifcopenshell.file.write`, `os.replace`, `os.unlink`, `ao_concluir`),
num ponto com nome ou numa hora sorteada (o pai mata). O pai então "reabre": `resolver_gravacao_pendente` e a régua do par.
Regra fixa: morreu antes do `os.replace` que põe o `gravacao.json` = par antigo (ou nada, na primeira gravação); depois = par novo, e o
resolvedor chama `ao_concluir(seq)` uma vez. Nunca misturado, nenhum temporário nem `gravacao*` sobrando, resolver de novo não muda nada.
Laço: N = 50 por sistema, semente 20261023 (atrasos de `random.Random`), Linux e Windows."""
import random
import shutil
import time

import pytest
import s05_t07_aux as X
from s05_conteudo_aux import _limpa, base_ifc, exigir  # noqa: F401  (fixtures)
from s05_t07_aux import SEQ, SEMENTE, gp

N_LACO = 50
NOMEADOS = {  # cartão T07 item 1 (lista mínima), com o estado do ADR-002 §4.5 e o par esperado
    "E1_antes_dos_temporarios": (["etapa", "escrever", "Casa.ifc.tmp"], "antigo"),
    "E2_ifc_tmp_escrito": (["etapa", "escrever", "Casa.obim.tmp"], "antigo"),
    "E2_ifc_tmp_cortado": ("ifc_cortado", "antigo"),
    "E3_lado_tmp_escrito": (["replace", "gravacao.json"], "antigo"),
    "E4_diario_escrito": (["replace", "gravacao.json", "depois"], "novo"),
    "E5_bak_do_ifc_feito": (["etapa", "trocar", "Casa.ifc"], "novo"),
    "E6_ifc_trocado_lado_nao": (["etapa", "bak", "Casa.obim"], "novo"),
    "E6_ifc_trocado_bak_do_lado": (["etapa", "trocar", "Casa.obim"], "novo"),
    "E7_os_dois_trocados_diario_la": (["ao_concluir", SEQ], "novo"),
}


class Cena:
    """Pasta da obra (com acento e espaço) e pasta do projeto; o par antigo (Revisao 1) é gravado por um filho sem morte; `voltar()` repõe."""
    def __init__(s, tmp, base, primeira):
        s.tmp, s.base, s.primeira = tmp, base, primeira
        s.destino, s.pasta = tmp / "obra ã" / "Casa.ifc", tmp / "local" / "projetos" / X.LADO
        s.destino.parent.mkdir(parents=True), s.pasta.mkdir(parents=True)
        if primeira:
            s.antigo, s.novo, s.tag = None, X.esperado(base, {}, 1, 1), 1
        else:
            assert X.rodar(s.destino, s.pasta, tag=1, base=base)[0] == 0
            s.antigo = X.Antigo(s.destino.read_bytes(), s.destino.with_suffix(".obim").read_bytes())
            s.novo, s.tag = X.esperado(s.destino, X.ler_obim(s.destino.with_suffix(".obim"))[1], 2, 2), 2
        s.guardar()

    def guardar(s):
        X.copiar(s.destino.parent, s.tmp / "guarda" / "obra"), X.copiar(s.pasta, s.tmp / "guarda" / "projeto")

    def voltar(s):
        X.copiar(s.tmp / "guarda" / "obra", s.destino.parent), X.copiar(s.tmp / "guarda" / "projeto", s.pasta)

    def gravar(s, morte=None):
        return X.rodar(s.destino, s.pasta, morte=morte, tag=s.tag, base=s.base)

    def resolver(s, destino=None):
        chamadas = []
        gp().resolver_gravacao_pendente(pasta_projeto=s.pasta, destino=destino or s.destino, ao_concluir=chamadas.append)
        return chamadas

    def conferir(s, esperado, chamadas, msg):
        esperado = "nada" if esperado == "antigo" and s.primeira else esperado
        assert X.estado_par(s.destino, s.antigo, s.novo, s.pasta) == (esperado, []), msg
        assert chamadas == ([SEQ] if esperado == "novo" else []), f"{msg}: ao_concluir {chamadas}"
        antes = X.foto_pastas(s.destino.parent, s.pasta)
        assert s.resolver() == [] and X.foto_pastas(s.destino.parent, s.pasta) == antes, f"{msg}: resolver de novo mudou algo"


@pytest.fixture(params=[False, True], ids=["segunda", "primeira"])
def cena(request, tmp_path, base_ifc):  # noqa: F811
    exigir()
    gp()
    return Cena(tmp_path, base_ifc, request.param)


@pytest.fixture
def segunda(tmp_path, base_ifc):  # noqa: F811
    exigir()
    gp()
    return Cena(tmp_path, base_ifc, False)


def virar(c, nome):
    p = c.destino.with_name(nome)
    b = bytearray(p.read_bytes())
    b[len(b) // 2] ^= 1
    p.write_bytes(bytes(b))


def test_q1_morte_antes_de_cada_evento(cena):
    gp()
    cod, traco = cena.gravar()
    assert cod == 0 and ["replace", "gravacao.json"] in traco and ["ao_concluir", SEQ] in traco, f"traço sem o diário ou o gancho: {traco}"
    for k in range(len(traco)):
        cena.voltar()
        cod, _ = cena.gravar(morte=k)
        assert cod == 86, f"morte {k} ({traco[k]}) não aconteceu"
        esperado = "novo" if ["replace", "gravacao.json"] in traco[:k] else "antigo"
        cena.conferir(esperado, cena.resolver(), f"morte antes do evento {k} {traco[k]}")


@pytest.mark.parametrize("nome", NOMEADOS)
def test_q2_estados_com_nome(cena, nome):
    gp()
    morte, esperado = NOMEADOS[nome]
    assert cena.gravar(morte=morte)[0] == 86, f"{nome}: o ponto {morte} não aconteceu"
    cena.conferir(esperado, cena.resolver(), nome)


RUINS = {  # (morte, mexida depois da morte, esperado): temporário que não confere com o sha256 do diário (byte trocado, mesmo tamanho)
    "E4_ifc_tmp_ruim": ("E4_diario_escrito", lambda c: virar(c, "Casa.ifc.tmp"), "antigo"),
    "E4_lado_tmp_sumiu": ("E4_diario_escrito", lambda c: c.destino.with_name("Casa.obim.tmp").unlink(), "antigo"),
    "E5_lado_tmp_ruim": ("E5_bak_do_ifc_feito", lambda c: virar(c, "Casa.obim.tmp"), "antigo"),
    "E6_lado_tmp_ruim": ("E6_ifc_trocado_lado_nao", lambda c: virar(c, "Casa.obim.tmp"), "antigo"),
}


@pytest.mark.parametrize("nome", RUINS)
def test_q3_temporario_que_nao_confere_desfaz(cena, nome):
    gp()
    ponto, mexer, esperado = RUINS[nome]
    assert cena.gravar(morte=NOMEADOS[ponto][0])[0] == 86
    mexer(cena)
    cena.conferir(esperado, cena.resolver(), f"{nome} ({'primeira' if cena.primeira else 'segunda'} gravação)")
    if nome.startswith("E6") and not cena.primeira:
        assert cena.destino.with_name("Casa.ifc.bak").read_bytes() == cena.antigo.ifc, "E6: o .bak tem de ficar"


E9 = {
    "E4_ifc_de_outro_programa": ("E4_diario_escrito", "Casa.ifc"),
    "E4_lado_de_outro_programa": ("E4_diario_escrito", "Casa.obim"),
    "E6_ifc_de_outro_programa": ("E6_ifc_trocado_lado_nao", "Casa.ifc"),
}


@pytest.mark.parametrize("nome", E9)
@pytest.mark.parametrize("lado_ruim", [False, True], ids=["lado_tmp_bom", "lado_tmp_ruim"])
def test_q4_e9_destino_mudado_por_outro_programa(cena, nome, lado_ruim):
    gp()
    ponto, arq = E9[nome]
    assert cena.gravar(morte=NOMEADOS[ponto][0])[0] == 86
    alvo = cena.destino.with_name(arq)
    alvo.write_bytes(b"ISO-10303-21;\n/* gravado por outro programa */\nEND-ISO-10303-21;\n")
    lado_ruim and virar(cena, "Casa.obim.tmp")
    antes = X.foto_pastas(cena.destino.parent, cena.pasta)
    for _ in range(2):
        assert cena.resolver() == [], f"{nome}: E9 chamou ao_concluir"
        assert X.foto_pastas(cena.destino.parent, cena.pasta) == antes, f"{nome}: E9 mexeu em algo (tem de manter tudo e o gravacao.json)"


def test_q5_e10_gravacao_json_de_outro_caminho(cena):
    gp()
    assert cena.gravar(morte=NOMEADOS["E6_ifc_trocado_lado_nao"][0])[0] == 86
    copia = cena.tmp / "copia do projeto" / "Casa.ifc"
    shutil.copytree(cena.destino.parent, copia.parent)
    antes = X.foto_pastas(cena.destino.parent, copia.parent, cena.pasta)
    assert cena.resolver(destino=copia) == [] and X.foto_pastas(cena.destino.parent, copia.parent, cena.pasta) == antes, "E10 aplicou"
    cena.conferir("novo", cena.resolver(), "E10: o caminho certo depois resolve")


PARA_RESOLVER = {"E5_conclui": ("E5_bak_do_ifc_feito", None, "novo"), "E6_desfaz": ("E6_ifc_trocado_lado_nao", "Casa.obim.tmp", "antigo")}


@pytest.mark.parametrize("nome", PARA_RESOLVER)
def test_q6_morte_dentro_do_resolvedor(cena, nome):
    """Recuperar é idempotente: o resolvedor morto antes de cada evento dele; a reabertura seguinte termina igual."""
    gp()
    ponto, ruim, esperado = PARA_RESOLVER[nome]
    assert cena.gravar(morte=NOMEADOS[ponto][0])[0] == 86
    ruim and virar(cena, ruim)
    cena.guardar()
    cena.voltar()  # o traço sai da cópia (sem os links do .bak), igual às voltas abaixo
    cod, traco = X.rodar(cena.destino, cena.pasta, modo="resolver")
    assert cod == 0 and traco, f"{nome}: o resolvedor não mexeu em nada: {traco}"
    for k in range(len(traco)):
        cena.voltar()
        assert X.rodar(cena.destino, cena.pasta, modo="resolver", morte=k)[0] == 86, f"{nome}: morte {k} ({traco[k]}) não aconteceu"
        cena.conferir(esperado, cena.resolver(), f"{nome}: resolvedor morto antes de {k} {traco[k]}")


def test_q7_morte_em_hora_sorteada(segunda):
    gp()
    c, rng, medidas, contagem = segunda, random.Random(SEMENTE), [], {}

    def uma(atraso=None):
        c.voltar()
        p, _ = X.rodar(c.destino, c.pasta, tag=c.tag, base=c.base, popen=True)
        assert p.stdout.readline().strip() == "pronto", p.stderr.read()[-2000:]
        t0 = time.perf_counter()
        if atraso is None:
            p.wait(60)
            return time.perf_counter() - t0
        time.sleep(atraso)
        p.kill()
        p.wait(60)
        return p.returncode
    for _ in range(3):
        medidas.append(uma())
    total = sorted(medidas)[1]
    for i in range(N_LACO):
        atraso = rng.uniform(0, 1.25 * total)
        cod = uma(atraso)
        chamadas = c.resolver()
        e, prob = X.estado_par(c.destino, c.antigo, c.novo, c.pasta)
        assert e in ("antigo", "novo") and prob == [], f"semente {SEMENTE}, volta {i}, atraso {atraso:.4f} s, código {cod}: {e} {prob}"
        assert chamadas in ([], [SEQ]) and (e == "novo" or chamadas == []), f"volta {i}: ao_concluir {chamadas} com par {e}"
        contagem[(e, cod == 0)] = contagem.get((e, cod == 0), 0) + 1
    print(f"\nlaço T07: gravação {total * 1000:.1f} ms; (par, terminou sozinho) -> vezes: {contagem}")
    assert contagem.get(("antigo", False)) and contagem.get(("novo", False)), f"o laço não matou dos dois lados do diário: {contagem}"

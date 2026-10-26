# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reforço do teste de gravação do par (achados 1 a 6 de revisão). Mesmo contrato de `test_s05_t07_par_oraculo.py` (não
edita este arquivo; o autor do teste tira os `@AINDA_NAO` depois, ), com estes acréscimos, todos do ADR-002 §4.5 e da
decisão da revisão:
7. Desfazer volta o destino só por um `.bak` cujo sha256 é o `antigo` desta gravação; antigo nulo (primeira gravação): apaga o destino só se o
   sha256 é o novo. Qualquer outro caso (`.bak` velho, `.bak` sumido com antigo não nulo): não mexe em nada e mantém o `gravacao.json` (como E9).
8. Destino que sumiu quando o antigo existia = E9: não mexe, mantém o `gravacao.json`, não chama `ao_concluir`.
9. `gravar_par` com `gravacao.json` pendente: resolve antes (com o `ao_concluir` dado, que recebe o `seq` da pendência) e só então grava; se a
   pendência não sai (também quando o resolvedor levanta erro), levanta erro em português que cita o `gravacao.json`, sem mexer em nada
   no disco (achado D3 do lote 80).
10. O `LadoId` que já está no pset vence o `lado_id` dado (no IFC e no manifesto); a `Revisao` sobe 1.
11. Carimbo: se o resolvedor desfaz a gravação com o programa vivo, a `Revisao` da memória volta à de antes (ADR §4.5: "se ela falhar, o
    carimbo volta").
12. O temporário do `gravacao.json` e a cópia do `.bak` ao desfazer passam por `os.fsync` antes do `os.replace` (mesmo inodo).
Mutantes que estes casos matam (lote 82): C01, C08, C19, C24, C26; e os defeitos dos achados 1, 2 e 6."""
import os
import time

import pytest
import s05_t07_aux as X
from s05_conteudo_aux import _limpa, base_ifc, exigir  # noqa: F401  (fixtures)
from s05_t07_aux import LADO, SEQ, gp
from test_s05_t06_gravacao_atomica_oraculo import TrocaRecusada
from test_s05_t07_par_oraculo import Proj, Traco, proj, virar_byte  # noqa: F401  (fixture proj)
from test_s05_t07_queda_oraculo import NOMEADOS, Cena, segunda, virar  # noqa: F401  (fixture segunda)

E4, E6 = NOMEADOS["E4_diario_escrito"][0], NOMEADOS["E6_ifc_trocado_lado_nao"][0]


@pytest.fixture
def primeira(tmp_path, base_ifc):  # noqa: F811
    exigir()
    gp()
    return Cena(tmp_path, base_ifc, True)


def parado(c, msg):
    """E9 e afins: o resolvedor (duas vezes) não mexe em nada, mantém o `gravacao.json` e não chama `ao_concluir`."""
    assert (c.pasta / "gravacao.json").exists(), f"{msg}: sem gravacao.json antes de resolver"
    antes = X.foto_pastas(c.destino.parent, c.pasta)
    for _ in range(2):
        assert c.resolver() == [], f"{msg}: chamou ao_concluir"
        assert X.foto_pastas(c.destino.parent, c.pasta) == antes, f"{msg}: mexeu no disco (tem de manter tudo e o gravacao.json)"


def test_r1_primeira_gravacao_com_bak_velho_na_pasta(primeira):
    """Achado 1: `.bak` de outra época não é o par antigo; primeira gravação morta em E6 com o lateral ruim apaga o IFC novo."""
    gp()
    c = primeira
    velhos = {n: f"sobra de outra época {n}\n".encode() for n in ("Casa.ifc.bak", "Casa.obim.bak")}
    for n, b in velhos.items():
        c.destino.with_name(n).write_bytes(b)
    c.guardar()
    assert c.gravar(morte=E6)[0] == 86
    virar(c, "Casa.obim.tmp")
    assert c.resolver() == []
    assert not c.destino.exists() and not c.destino.with_suffix(".obim").exists(), "ADR §4.5 E6 (primeira): o IFC novo tem de sair"
    assert {n: c.destino.with_name(n).read_bytes() for n in velhos} == velhos, "o .bak velho foi mexido"
    assert X.sobras(c.destino, c.pasta) == []


@pytest.mark.parametrize("bak", ["velho", "sumiu"])
def test_r2_bak_que_nao_e_o_antigo(segunda, bak):
    """Achados 1 e 4 (C08): segunda gravação em E6 com o lateral ruim; `.bak` com outro sha256 ou sem `.bak`: nada muda, `gravacao.json` fica."""
    gp()
    c = segunda
    assert c.gravar(morte=E6)[0] == 86
    virar(c, "Casa.obim.tmp")
    b = c.destino.with_name("Casa.ifc.bak")
    b.write_bytes(b"outro conteudo\n") if bak == "velho" else b.unlink()
    parado(c, f"E6 com .bak {bak}")


@pytest.mark.parametrize("arq", ["Casa.ifc", "Casa.obim"])
@pytest.mark.parametrize("morte", ["E4", "E6"])
def test_r3_destino_sumido_com_antigo_e_e9(segunda, arq, morte):
    """Achado 5 (C24): o destino que tinha versão antiga sumiu: E9."""
    gp()
    c = segunda
    assert c.gravar(morte=E4 if morte == "E4" else E6)[0] == 86
    c.destino.with_name(arq).unlink()
    parado(c, f"{morte} com {arq} sumido")


def test_r4_lado_id_do_pset_vence_o_dado(tmp_path, base_ifc):  # noqa: F811
    """Achado 3 (C26): pset com LadoId X (outro programa ou cópia do projeto) e lado_id Y dado: X no IFC e no manifesto, Revisao + 1."""
    exigir()
    gp()
    import ifcopenshell
    import ifcopenshell.api
    f = ifcopenshell.open(base_ifc)
    ps = ifcopenshell.api.run("pset.add_pset", f, product=f.by_type("IfcProject")[0], name="OBIM_Projeto")
    ifcopenshell.api.run("pset.edit_pset", f, pset=ps, properties={"LadoId": "lado-que-ja-estava", "Revisao": 5})
    f.write(str(tmp_path / "com_pset.ifc"))
    p = Proj(tmp_path, str(tmp_path / "com_pset.ifc"))
    novo = p.novo(6)._replace(lado_id="lado-que-ja-estava")
    p.gravar()
    assert p.pset() == ("lado-que-ja-estava", 6), f"carimbo {p.pset()}: o LadoId do pset tem de ficar (lado_id dado = {LADO})"
    assert X.estado_par(p.destino, None, novo, p.pasta) == ("novo", [])
    assert X.ler_obim(p.destino.with_suffix(".obim"))[0]["LadoId"] == "lado-que-ja-estava"
    p.h.encerrar()


def _pendente(proj, monkeypatch):
    """Segunda gravação com a troca do lateral sempre recusada: fica IFC novo (Revisao 2), lateral antigo, `Casa.obim.tmp` e `gravacao.json`."""
    proj.gravar()
    um = proj.antigo()
    proj.tx(2)
    dois = proj.novo(2)
    proj.chamadas.clear()
    monkeypatch.setattr(time, "sleep", lambda s: None)
    with pytest.MonkeyPatch.context() as mp, pytest.raises(Exception):
        mp.setattr(os, "replace", TrocaRecusada(proj.destino.with_suffix(".obim"), 10**6))
        proj.gravar()
    assert (proj.pasta / "gravacao.json").exists() and proj.chamadas == []
    return um, dois


def test_r5_pendencia_e_resolvida_antes_de_gravar(proj, monkeypatch):
    """Achado 2 (D3): com a troca liberada, a gravação seguinte conclui a pendência (ao_concluir com o seq dela), depois grava a sua."""
    gp()
    um, dois = _pendente(proj, monkeypatch)
    proj.tx(3)
    tres = proj.novo(3)
    seqs = []
    proj.gravar(seq=SEQ + 1, ao_concluir=seqs.append)
    assert seqs == [SEQ, SEQ + 1], f"ao_concluir {seqs}: a pendência (seq {SEQ}) tem de ser concluída antes da gravação nova"
    assert X.estado_par(proj.destino, um, tres, proj.pasta) == ("novo", [])
    bak = proj.destino.parent / "bak"
    bak.mkdir()
    for n in ("Casa.ifc", "Casa.obim"):
        (bak / n).write_bytes(proj.destino.with_name(n + ".bak").read_bytes())
    assert X.estado_par(bak / "Casa.ifc", um, dois) == ("novo", []), "o .bak ficou com um par misturado (IFC de uma revisão, lateral de outra)"


def test_r6_pendencia_que_nao_sai_recusa_sem_mexer(proj, monkeypatch):
    """Achado 2 (D3), caso do Windows: a troca do lateral segue recusada; a gravação nova recusa, cita o gravacao.json e não mexe no disco."""
    gp()
    _pendente(proj, monkeypatch)
    proj.tx(3)
    antes = X.foto_pastas(proj.destino.parent, proj.pasta)
    with pytest.MonkeyPatch.context() as mp, pytest.raises(Exception) as ei:
        mp.setattr(os, "replace", TrocaRecusada(proj.destino.with_suffix(".obim"), 10**6))
        proj.gravar(seq=SEQ + 1)
    assert "gravacao.json" in str(ei.value), f"a mensagem não diz onde está a pendência: {ei.value}"
    assert X.foto_pastas(proj.destino.parent, proj.pasta) == antes, "gravou por cima de uma pendência (apagou temporário ou misturou o .bak)"
    assert proj.chamadas == []


@pytest.mark.parametrize("quando,alvo", [(("replace", "gravacao.json", "depois"), "Casa.ifc.tmp"), (("etapa", "trocar", "Casa.ifc"), "Casa.obim.tmp")],
                         ids=["ifc_depois_do_diario", "lado_depois_do_bak"])
def test_r7_carimbo_volta_quando_o_resolvedor_desfaz(proj, quando, alvo):
    """Achado 6: falha depois do `gravacao.json`, o resolvedor desfaz na hora: par antigo no disco e Revisao de antes na memória."""
    gp()
    proj.gravar()
    um = proj.antigo()
    proj.tx(2)
    with pytest.MonkeyPatch.context() as mp, pytest.raises(Exception):
        Traco(mp, proj.s, {quando: lambda: virar_byte(proj.destino.with_name(alvo))})
        proj.gravar()
    assert proj.antigo() == um and not (proj.pasta / "gravacao.json").exists()
    assert proj.pset() == (LADO, 1), f"ADR §4.5: a gravação foi desfeita e o carimbo ficou {proj.pset()}"


class Fsyncs:
    """Inodos que passaram por `os.fsync` e, para cada `os.replace` com destino em `alvos`, se o inodo da origem já tinha passado."""
    def __init__(s, mp, alvos):
        s.feitos, s.trocas, fs, rp = set(), [], os.fsync, os.replace
        mp.setattr(os, "fsync", lambda fd: (s.feitos.add(os.fstat(fd).st_ino), fs(fd))[1])

        def replace(src, dst, *a, **k):
            if os.path.basename(str(dst)) in alvos:
                s.trocas.append((os.path.basename(str(dst)), os.stat(src).st_ino in s.feitos))
            return rp(src, dst, *a, **k)
        mp.setattr(os, "replace", replace)


def test_r8_fsync_do_temporario_do_diario(proj):
    """C01: o `gravacao.json.tmp` vai ao disco antes da troca."""
    gp()
    with pytest.MonkeyPatch.context() as mp:
        r = Fsyncs(mp, {"gravacao.json"})
        proj.gravar()
    assert r.trocas == [("gravacao.json", True)], f"C01: gravacao.json trocado sem fsync do temporário: {r.trocas}"


def test_r9_fsync_da_copia_do_bak_ao_desfazer(segunda):
    """C19: a cópia do `.bak` que volta o `Casa.ifc` vai ao disco antes da troca."""
    gp()
    c = segunda
    assert c.gravar(morte=E6)[0] == 86
    virar(c, "Casa.obim.tmp")
    with pytest.MonkeyPatch.context() as mp:
        r = Fsyncs(mp, {"Casa.ifc"})
        c.resolver()
    assert r.trocas == [("Casa.ifc", True)], f"C19: Casa.ifc voltado do .bak sem fsync da cópia: {r.trocas}"
    assert X.estado_par(c.destino, c.antigo, c.novo, c.pasta) == ("antigo", [])


import errno
import shutil


@pytest.mark.parametrize("variante", ["outro_caminho", "destino_alterado", "gravacao_ilegivel", "bak_sumido"])
def test_r10_pendencia_que_nao_se_resolve_recusa(proj, monkeypatch, variante):
    """Caso 2: pendência que não sai recusa a gravação sem mexer em nada (mutante N2a)."""
    gp()
    _pendente(proj, monkeypatch)
    destino = proj.destino
    if variante == "outro_caminho":
        copia_dir = proj.destino.parent.parent / "obra_copia"
        copia_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(proj.destino.parent, copia_dir, dirs_exist_ok=True)
        destino = copia_dir / "Casa.ifc"
    elif variante == "destino_alterado":
        proj.destino.with_suffix(".obim").write_bytes(b"corrompido")
    elif variante == "gravacao_ilegivel":
        (proj.pasta / "gravacao.json").write_text("{lixo", encoding="utf-8")
    elif variante == "bak_sumido":
        virar_byte(proj.destino.with_name("Casa.obim.tmp"))
        proj.destino.with_name("Casa.ifc.bak").unlink()

    antes_pset = proj.pset()
    pastas = (destino.parent, proj.pasta) if destino == proj.destino else (destino.parent, proj.destino.parent, proj.pasta)
    antes_disco = X.foto_pastas(*pastas)
    chamadas_antes = list(proj.chamadas)

    with pytest.raises(Exception) as ei:
        proj.gravar(destino=destino, seq=SEQ + 1)
    assert "gravacao.json" in str(ei.value), f"erro não cita gravacao.json: {ei.value}"
    assert proj.chamadas == chamadas_antes, "chamou ao_concluir"
    assert proj.pset() == antes_pset, f"revisão mudou: antes {antes_pset}, depois {proj.pset()}"
    assert X.foto_pastas(*pastas) == antes_disco, "mudou bytes no disco"


@pytest.mark.parametrize("falha", ["unlink_final", "troca_obim"])
def test_r11_unlink_final_recusado_uma_vez_conclui_e_o_carimbo_fica(proj, monkeypatch, falha):
    """Caso 3: resolvedor conclui na hora e o carimbo fica (mutante N3)."""
    gp()
    proj.gravar()
    um = proj.antigo()
    proj.tx(2)
    novo2 = proj.novo(2)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    if falha == "unlink_final":
        unlink_real = os.unlink
        falhou = []

        def unlink_uma_vez(p, *a, **k):
            if os.path.basename(str(p)) == "gravacao.json" and not falhou:
                falhou.append(True)
                raise OSError(errno.EIO, "falha simulada no unlink final")
            return unlink_real(p, *a, **k)

        monkeypatch.setattr(os, "unlink", unlink_uma_vez)
    else:
        recusa = TrocaRecusada(proj.destino.with_suffix(".obim"), 6)
        monkeypatch.setattr(os, "replace", recusa)

    proj.chamadas.clear()
    with pytest.raises(Exception):
        proj.gravar()

    if falha == "unlink_final":
        assert falhou == [True]
        assert [c[0] for c in proj.chamadas] == [SEQ, SEQ]
    else:
        assert recusa.tentativas >= 6
        assert [c[0] for c in proj.chamadas] == [SEQ]

    assert not (proj.pasta / "gravacao.json").exists(), "gravacao.json não sumiu"
    assert X.estado_par(proj.destino, um, novo2, proj.pasta) == ("novo", [])
    assert proj.pset() == (LADO, 2), f"ADR §4.5: carimbo na memória voltou: {proj.pset()}"

    dois = proj.antigo()
    proj.tx(3)
    novo3 = proj.novo(3)
    proj.gravar()
    assert proj.pset() == (LADO, 3)
    assert X.estado_par(proj.destino, dois, novo3, proj.pasta) == ("novo", [])
    man, _ = X.ler_obim(proj.destino.with_suffix(".obim"))
    assert man["Revisao"] == 3


def test_r12_recusa_por_pendencia_nao_pula_revisao(proj, monkeypatch):
    """Caso 4: recusa por pendência que não sai não mexe na Revisao da memória (mutante N7)."""
    gp()
    um, dois = _pendente(proj, monkeypatch)
    antes = proj.pset()
    proj.tx(3)
    tres = proj.novo(3)
    with pytest.MonkeyPatch.context() as mp, pytest.raises(Exception) as ei:
        mp.setattr(os, "replace", TrocaRecusada(proj.destino.with_suffix(".obim"), 10**6))
        proj.gravar(seq=SEQ + 1)
    assert "gravacao.json" in str(ei.value), f"a mensagem não cita gravacao.json: {ei.value}"
    assert proj.pset() == antes, f"recusa por pendência alterou a revisão na memória: {proj.pset()} != {antes}"

    proj.gravar(seq=SEQ + 1)
    assert proj.pset() == (LADO, 3), f"revisão pulou ou não avançou: {proj.pset()}"
    assert X.estado_par(proj.destino, um, tres, proj.pasta) == ("novo", [])


@pytest.mark.parametrize("variante", ["autosave_novo", "autosave_antigo"])
def test_r13_falha_depois_do_gravacao_json_sem_carimbo(proj, monkeypatch, variante):
    """Caso 5: autosave que falha depois do gravacao.json sem carimbo e sem histórico (mutante N11)."""
    gp()
    proj.gravar()
    um_usuario = proj.antigo()
    pset_antes = proj.pset()

    auto = proj.pasta / "autosave" / "Casa.ifc"
    auto.parent.mkdir(parents=True, exist_ok=True)
    antigo_auto = None
    if variante == "autosave_antigo":
        proj.gravar(historico=None, carimbo=False, destino=auto)
        antigo_auto = (auto.read_bytes(), auto.with_suffix(".obim").read_bytes())

    proj.tx(2)
    pset_apos_tx = proj.pset()

    monkeypatch.setattr(proj.s, "escrever", lambda *a, **k: pytest.fail("sem carimbo abriu escrever()"))

    t = None
    with pytest.MonkeyPatch.context() as mp, pytest.raises(Exception) as ei:
        t = Traco(mp, proj.s, {(("replace", "gravacao.json", "depois")): lambda: virar_byte(auto.with_name("Casa.ifc.tmp"))})
        proj.gravar(historico=None, carimbo=False, destino=auto)

    assert t is not None and ("replace", "gravacao.json") in t.ev
    assert "Casa.ifc" in str(ei.value)
    assert not isinstance(ei.value, (AttributeError, TypeError)), f"erro indevido com historico=None: {ei.value!r}"
    assert proj.pset() == pset_apos_tx == pset_antes
    assert proj.antigo() == um_usuario, "par do usuário foi afetado"
    assert not (proj.pasta / "gravacao.json").exists()
    assert X.sobras(auto, proj.pasta) == []

    if variante == "autosave_novo":
        assert not auto.exists() and not auto.with_suffix(".obim").exists()
    else:
        assert (auto.read_bytes(), auto.with_suffix(".obim").read_bytes()) == antigo_auto


def test_r14_pendencia_que_o_resolvedor_desfaz_deixa_gravar(proj, monkeypatch):
    """Caso 6: pendência desfeita antes de gravar não impede a gravação nova (mutante N12)."""
    gp()
    um, dois = _pendente(proj, monkeypatch)
    virar_byte(proj.destino.with_name("Casa.obim.tmp"))
    seqs = []
    proj.gravar(seq=SEQ + 1, ao_concluir=seqs.append)
    assert seqs == [SEQ + 1], f"ao_concluir inesperado: {seqs}"
    assert not list(proj.pasta.glob("gravacao*")), "sobrou gravacao* em pasta_projeto"
    assert proj.pset() == (LADO, 3), f"revisão inesperada: {proj.pset()}"
    novo = proj.novo(3)
    assert X.estado_par(proj.destino, um, novo) == ("novo", [])
    assert (proj.destino.with_name("Casa.ifc.bak").read_bytes(), proj.destino.with_name("Casa.obim.bak").read_bytes()) == tuple(um)
    man, _ = X.ler_obim(proj.destino.with_suffix(".obim"))
    assert man["Revisao"] == 3


@pytest.mark.parametrize("variante", ["autosave_novo", "autosave_antigo"])
def test_r15_falha_antes_do_gravacao_json_sem_carimbo(proj, monkeypatch, variante):
    """Mutante N11a: falha antes de gravacao.json sem carimbo e com historico=None não tenta reverter carimbo."""
    gp()
    proj.gravar()
    um_usuario = proj.antigo()
    pset_antes = proj.pset()

    auto = proj.pasta / "autosave" / "Casa.ifc"
    auto.parent.mkdir(parents=True, exist_ok=True)
    antigo_auto = None
    if variante == "autosave_antigo":
        proj.gravar(historico=None, carimbo=False, destino=auto)
        antigo_auto = (auto.read_bytes(), auto.with_suffix(".obim").read_bytes())

    proj.tx(2)
    pset_apos_tx = proj.pset()

    monkeypatch.setattr(proj.s, "escrever", lambda *a, **k: pytest.fail("sem carimbo abriu escrever()"))

    real_replace = os.replace

    def replace_recusa(src, dst, *a, **k):
        if os.path.basename(str(dst)) == "gravacao.json":
            raise OSError(errno.EIO, "falha simulada no replace de gravacao.json.tmp")
        return real_replace(src, dst, *a, **k)

    with pytest.MonkeyPatch.context() as mp, pytest.raises(OSError) as ei:
        mp.setattr(os, "replace", replace_recusa)
        proj.gravar(historico=None, carimbo=False, destino=auto)

    assert not isinstance(ei.value, (AttributeError, TypeError)), f"erro indevido com historico=None: {ei.value!r}"
    assert "falha simulada no replace de gravacao.json.tmp" in str(ei.value)
    assert not (proj.pasta / "gravacao.json").exists(), "gravacao.json não deve existir"
    assert proj.pset() == pset_apos_tx == pset_antes
    assert proj.antigo() == um_usuario, "par do usuário foi afetado"
    assert X.sobras(auto, proj.pasta) == []

    if variante == "autosave_novo":
        assert not auto.exists() and not auto.with_suffix(".obim").exists()
    else:
        assert (auto.read_bytes(), auto.with_suffix(".obim").read_bytes()) == antigo_auto



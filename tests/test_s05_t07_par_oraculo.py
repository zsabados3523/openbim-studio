# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S05-T07, parte 1: gravação do par no mesmo processo (cartão F0-S05-T07; ADR-002 §4.3, §4.5 e §4.8; T00 G4 a G6; v2/02 §6.1,
§6.2 e §6.5). Quem implementa não edita `tests/`; o autor do oráculo tira os `@AINDA_NAO` (xfail estrito por falta do módulo) depois, em commit
próprio. A parte 2 (morte do processo filho em cada estado, E1 a E10, laço aleatório) está em `test_s05_t07_queda_oraculo.py`.
CONTRATO de `app/openbim_app/gravacao_par.py` (sem Qt, sem obimcore). O ADR-002 §4.8 nomeia só `resolver_gravacao_pendente` e o gancho
`ao_concluir(seq)`; o nome `gravar_par` e os nomes dos parâmetros são PROPOSTOS PELO ORÁCULO (pendentes do líder). O oráculo chama tudo POR NOME:
1. `gravar_par(sessao=, historico=, lateral=, destino=, pasta_projeto=, lado_id=, seq=, carimbo=True, ao_concluir=None)`: `destino` = `Casa.ifc`;
   o lateral vai em `Casa.obim` (mesmo nome-base, mesma pasta); `pasta_projeto` = `projetos/<LadoId>` (já existe; dada pelo chamador, o módulo
   não importa `diario.py` nem lê `OBIM_PASTA_LOCAL`); o diário de gravação é `pasta_projeto/gravacao.json`. O valor devolvido não é conferido.
2. Carimbo (`carimbo=True`): UMA `sessao.escrever()` curta com `historico.fora_do_historico(esc)` põe no `IfcProject` o pset único
   `OBIM_Projeto` com `LadoId` (texto; o que já está no pset ou, sem pset, o `lado_id` dado: o definitivo = o provisório) e `Revisao` (inteiro;
   a de antes + 1; sem pset, 1). Não entra no histórico nem no `anotar`. Sem carimbo (autosave): não abre `escrever()`, `historico` pode ser
   None e o pset fica como está.
3. O resto roda dentro de UMA `sessao.ler()`, nesta ordem: `gravacao_atomica.preparar` do `Casa.ifc` (o IFC é escrito por
   `ifcopenshell.file.write`; `conferir=conferir_ifc`) e do `Casa.obim`; `gravacao.json` gravado por troca (`os.replace`); `confirmar` do IFC e
   depois do lateral, cada um só depois de conferir de novo o sha256 do temporário contra o do `Preparado` (achado D4); `ao_concluir(seq)` com
   os dois já trocados e o `gravacao.json` ainda lá; o `gravacao.json` apagado por último. `os.replace`/`os.unlink` pelo módulo `os`, na hora.
4. `Casa.obim` = ZIP com `manifest.json` (`formato` "obim-lateral", `versao_formato` "0.1.0", `provisorio` true, `LadoId`, `Revisao`, `ifc_nome`,
   `ifc_sha256`, `ifc_tamanho`, `ifc_projeto_globalid`, `programa_versao`, `data`) e um `<coleção>/<id>.json` por objeto, nada mais.
5. Falha: sobe uma exceção com `str` em português que cita o arquivo. Antes do `gravacao.json`: temporários apagados, par de antes intacto,
   carimbo de volta ao valor anterior, `ao_concluir` não é chamado. Depois dele: o resolvedor roda na hora (ADR-002 §4.5); se não conseguir, o
   `gravacao.json` fica e a mensagem diz onde está o temporário.
6. `resolver_gravacao_pendente(pasta_projeto=, destino=, ao_concluir=None)`: estados E1 a E10 do ADR-002 §4.5 (parte 2). O valor devolvido não é
   conferido (o "avisa" do E9/E10 está em PERGUNTA_LIDER); o oráculo confere o disco e as chamadas de `ao_concluir`. Depois de concluir ou
   desfazer não sobra `Casa.*.tmp`, `Casa.*.bak.tmp` nem `gravacao*` (o resolvedor limpa com `limpar_temporarios`; `confirmar` de novo com o
   `.bak` já ligado ao destino por `os.link` deixa `Casa.ifc.bak.tmp`, porque `os.replace` entre dois nomes do mesmo arquivo não faz nada).
GUARDA: sem ifcopenshell, pula; com OBIM_S05_OBRIGATORIO=1 todo pulo vira falha. Régua: `s05_t07_aux.py` (provada em `test_s05_t07_regua_oraculo.py`)."""
import ast
import errno
import os
import time

import pytest
import s05_conteudo_aux as R
import s05_t07_aux as X
from s05_conteudo_aux import _limpa, base_ifc, exigir  # noqa: F401  (fixtures)
from s05_t07_aux import LADO, SEQ, gp



class Proj:
    """Modelo base (300 paredes) aberto, lateral com um objeto, `Historico` com `anotar` contado; `gravar(**kw)` chama `gravar_par`."""
    def __init__(s, tmp, base, destino=None, pasta=None):
        import ifcopenshell
        from openbim_app.lateral import Lateral
        from openbim_app.sessao_modelo import SessaoModelo
        from openbim_app.transacao import Historico
        s.destino = destino or tmp / "obra" / "Casa.ifc"
        s.pasta = pasta or tmp / "local" / "projetos" / LADO
        s.destino.parent.mkdir(parents=True, exist_ok=True), s.pasta.mkdir(parents=True, exist_ok=True)
        s.f, s.anot, s.chamadas = ifcopenshell.open(base), [], []
        s.s, s.lat = SessaoModelo(s.f), Lateral({"notas": {"n0": {"texto": "primeira"}}})
        s.h = Historico(s.s, s.lat, anotar=lambda *a, **k: s.anot.append(a))
        s.tx(1)

    def tx(s, tag):
        with s.s.escrever() as esc, s.h.transacao(esc) as t:
            X.mudar(t.ifc, t.lado.criar, tag)

    def ao(s, seq):  # o gancho: anota o seq, se o gravacao.json ainda existe, a porta e os bytes do par naquela hora
        o = s.destino.with_suffix(".obim")
        s.chamadas.append((seq, (s.pasta / "gravacao.json").exists(), s.s.estado(), s.destino.read_bytes(), o.read_bytes()))

    def gravar(s, **kw):
        a = dict(sessao=s.s, historico=s.h, lateral=s.lat, destino=s.destino, pasta_projeto=s.pasta, lado_id=LADO, seq=SEQ, ao_concluir=s.ao)
        return gp().gravar_par(**{**a, **kw})

    def novo(s, rev):
        return X.Novo(rev, LADO, R.foto(s.f, sem_pset_obim=True), bytes(s.lat.canonico()))

    def antigo(s):
        return X.Antigo(s.destino.read_bytes(), s.destino.with_suffix(".obim").read_bytes())

    def pset(s):
        with s.s.ler() as a:
            return X.pset_obim(a)


@pytest.fixture
def proj(tmp_path, base_ifc, monkeypatch):  # noqa: F811
    exigir()
    for v in ("OBIM_S05_FALHA_EM", "OBIM_S05_MORRER_EM"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("OBIM_PASTA_LOCAL", str(tmp_path / "isca"))  # o módulo não pode escrever aqui (a pasta vem por parâmetro)
    p = Proj(tmp_path, base_ifc)
    yield p
    assert not (tmp_path / "isca").exists(), "o par escreveu na pasta de OBIM_PASTA_LOCAL (ADR-002 §4.5: pasta do projeto por parâmetro)"
    p.h.encerrar()


class Traco:
    """Anota (em ordem) `_etapa` do T06, `ifcopenshell.file.write`, `os.replace`, `os.unlink`/`os.remove` e o estado da porta em cada um;
    `gatilhos[evento]` (evento = tupla; com "depois" no fim, roda depois do real) é chamado naquele ponto."""
    def __init__(s, mp, sessao, gatilhos=None):
        import ifcopenshell
        import openbim_app.gravacao_atomica as GA
        s.ev, s.portas, s.g = [], [], gatilhos or {}
        etapa, escrever = GA._etapa, ifcopenshell.file.write

        def anota(e, depois=False):
            e = tuple(e) + (("depois",) if depois else ())
            if not depois:
                s.ev.append(e), s.portas.append(sessao.estado())
            s.g.get(e, lambda: None)()

        def emb(tipo, real, pos):
            def f(*a, **k):
                alvo = os.path.basename(str(a[pos]))
                anota((tipo, alvo))
                r = real(*a, **k)
                anota((tipo, alvo), True)
                return r
            return f
        mp.setattr(GA, "_etapa", lambda n, c: (anota(("etapa", n, os.path.basename(str(c)))), etapa(n, c))[1])
        mp.setattr(ifcopenshell.file, "write", lambda self, c, *a, **k: (anota(("ifc_write", os.path.basename(str(c)))), escrever(self, c, *a, **k))[1])
        mp.setattr(os, "replace", emb("replace", os.replace, 1))
        mp.setattr(os, "unlink", emb("unlink", os.unlink, 0)), mp.setattr(os, "remove", emb("unlink", os.remove, 0))

    def pos(s, e):
        assert e in s.ev, f"evento {e} não aconteceu: {s.ev}"
        return s.ev.index(e)


def virar_byte(caminho):  # mesmo tamanho, um byte diferente (conferir só o tamanho não basta)
    b = bytearray(caminho.read_bytes())
    b[len(b) // 2] ^= 1
    caminho.write_bytes(bytes(b))


def test_01_primeira_gravacao(proj):
    novo = proj.novo(1)
    proj.gravar()
    assert X.estado_par(proj.destino, None, novo, proj.pasta) == ("novo", [])
    assert proj.pset() == (LADO, 1), "G4/ADR §4.4: na primeira gravação o LadoId é o provisório dado e a Revisao é 1"
    assert (proj.h.pode_desfazer, len(proj.f.history), len(proj.anot)) == (True, 1, 1), "carimbo entrou no histórico ou no diário"
    assert not any(proj.destino.with_name(n).exists() for n in ("Casa.ifc.bak", "Casa.obim.bak")), "sem destino antigo não há .bak"
    assert [c[:2] for c in proj.chamadas] == [(SEQ, True)], f"ao_concluir: {[c[:2] for c in proj.chamadas]}"
    assert proj.chamadas[0][3:] == tuple(proj.antigo()), "ao_concluir chamado antes de trocar os dois"
    import ifcopenshell
    assert R.diferencas(R.foto(ifcopenshell.open(str(proj.destino))), R.foto(proj.f)) == [], "reaberto difere do modelo em memória"


def test_02_segunda_gravacao_bak_e_desfazer(proj):
    proj.gravar()
    um = proj.antigo()
    proj.tx(2)
    novo = proj.novo(2)
    proj.gravar()
    assert X.estado_par(proj.destino, um, novo, proj.pasta) == ("novo", [])
    assert proj.destino.with_name("Casa.ifc.bak").read_bytes() == um.ifc and proj.destino.with_name("Casa.obim.bak").read_bytes() == um.obim
    with proj.s.escrever() as esc:
        proj.h.desfazer(esc)
    with proj.s.ler() as a:
        assert a.by_type("IfcWall")[0].Name == "parede alterada 1", "desfazer não voltou a última transação"
    assert proj.pset() == (LADO, 2), "desfazer voltou o carimbo (ele é fora do histórico)"


def test_03_desenho_portas_e_ordem(proj, monkeypatch):
    portas, fora = [], []
    esc_real, fora_real = proj.s.escrever, proj.h.fora_do_historico
    monkeypatch.setattr(proj.s, "escrever", lambda *a, **k: (portas.append("escrever"), esc_real(*a, **k))[1])
    monkeypatch.setattr(proj.h, "fora_do_historico", lambda esc: (fora.append(proj.s.estado()["escritor"]), fora_real(esc))[1])
    t = Traco(monkeypatch, proj.s)
    proj.gravar()
    assert portas == ["escrever"] and len(fora) == 1 and fora[0] is not None, f"carimbo: escrever {portas}, fora_do_historico {fora}"
    ruins = [(e, p) for e, p in zip(t.ev, t.portas) if p["leitores"] != 1 or p["escritor"] is not None]
    assert not ruins, f"ADR §4.5: a gravação roda dentro de ler(): {ruins[:3]}"
    assert proj.chamadas[0][2]["leitores"] == 1, "ao_concluir fora do ler()"
    assert ("ifc_write", "Casa.ifc.tmp") in t.ev
    j = t.pos(("replace", "gravacao.json"))
    assert max(t.pos(("etapa", "conferir", "Casa.ifc.tmp")), t.pos(("etapa", "conferir", "Casa.obim.tmp"))) < j, "gravacao.json antes dos temporários"
    assert j < t.pos(("etapa", "bak", "Casa.ifc")) < t.pos(("replace", "Casa.ifc")) < t.pos(("etapa", "bak", "Casa.obim")), f"ordem: {t.ev}"
    assert t.pos(("replace", "Casa.ifc")) < t.pos(("replace", "Casa.obim")), "G4: IFC primeiro, depois o lateral"
    mexe = [e for e in t.ev if e[0] in ("replace", "unlink")]
    assert mexe[-1] == ("unlink", "gravacao.json"), f"gravacao.json não foi o último a sair: {mexe[-4:]}"


def test_04_sem_carimbo_autosave(proj, monkeypatch):
    proj.gravar()
    um, rev = proj.antigo(), proj.pset()
    proj.tx(2)
    novo = proj.novo(1)
    monkeypatch.setattr(proj.s, "escrever", lambda *a, **k: pytest.fail("sem carimbo abriu escrever()"))
    auto = proj.pasta / "autosave" / "Casa.ifc"
    auto.parent.mkdir()
    proj.chamadas.clear()
    proj.gravar(historico=None, carimbo=False, destino=auto, ao_concluir=lambda seq: proj.chamadas.append(seq))
    assert X.estado_par(auto, None, novo) == ("novo", []) and proj.pset() == rev == (LADO, 1)
    assert proj.antigo() == um, "o autosave mexeu no par do usuário"
    assert proj.chamadas == [SEQ] and not (proj.pasta / "gravacao.json").exists()
    import ifcopenshell
    assert R.diferencas(R.foto(ifcopenshell.open(str(auto))), R.foto(proj.f)) == []


def test_05_nao_importa_diario():
    m = gp()
    arvore = ast.parse(open(m.__file__, encoding="utf-8").read())
    nomes = [a.name for n in ast.walk(arvore) if isinstance(n, ast.Import) for a in n.names]
    nomes += [f"{n.module}.{a.name}" for n in ast.walk(arvore) if isinstance(n, ast.ImportFrom) for a in n.names]
    assert not [x for x in nomes if "diario" in x or "autosave" in x], f"ADR §4.5: o par não importa diario.py: {nomes}"


def test_06_acento_e_espaco_e_conteudo(tmp_path, base_ifc, monkeypatch):  # noqa: F811
    exigir()
    gp()
    p = Proj(tmp_path, base_ifc, tmp_path / "Residência Nova" / "João" / "Casa.ifc", tmp_path / "Dados Locais" / "projetos ç" / LADO)
    antes = R.foto(p.f, sem_pset_obim=True)
    p.gravar()
    import ifcopenshell
    reaberto = ifcopenshell.open(str(p.destino))
    assert R.diferencas(R.foto(reaberto, sem_pset_obim=True), antes) == [], "o carimbo mexeu em algo além do pset OBIM_Projeto"
    assert R.diferencas(R.foto(reaberto), R.foto(p.f)) == []
    assert X.estado_par(p.destino, None, p.novo(1), p.pasta) == ("novo", [])
    p.h.encerrar()


@pytest.mark.parametrize("ponto", [("escrever", "Casa.ifc.tmp"), ("conferir", "Casa.ifc.tmp"), ("escrever", "Casa.obim.tmp"), ("fsync", "Casa.obim.tmp")])
def test_07_falha_antes_do_diario(proj, monkeypatch, ponto):
    proj.gravar()
    proj.tx(2)
    antes, hist = X.foto_pastas(proj.destino.parent, proj.pasta), len(proj.f.history)
    proj.chamadas.clear()

    def falha():
        raise OSError(errno.EIO, "falha injetada (teste)")
    with pytest.MonkeyPatch.context() as mp, pytest.raises(Exception) as ei:
        Traco(mp, proj.s, {("etapa", *ponto): falha})
        proj.gravar()
    assert "Casa" in str(ei.value), str(ei.value)
    assert X.foto_pastas(proj.destino.parent, proj.pasta) == antes, "falha antes do gravacao.json mudou a pasta ou deixou temporário"
    assert proj.pset() == (LADO, 1), "ADR §4.5: a gravação falhou e o carimbo não voltou"
    assert (proj.chamadas, len(proj.f.history)) == ([], hist)


@pytest.mark.parametrize("quando,alvo", [(("etapa", "escrever", "Casa.obim.tmp"), "Casa.ifc.tmp"), (("replace", "gravacao.json", "depois"), "Casa.ifc.tmp"),
                                         (("etapa", "trocar", "Casa.ifc"), "Casa.obim.tmp")], ids=["ifc_antes_do_diario", "ifc_depois_do_diario", "lado_depois_do_bak"])
def test_08_d4_temporario_mudado_antes_de_confirmar(proj, monkeypatch, quando, alvo):
    proj.gravar()
    um = proj.antigo()
    proj.tx(2)
    novo = proj.novo(2)
    proj.chamadas.clear()
    with pytest.MonkeyPatch.context() as mp, pytest.raises(Exception):
        Traco(mp, proj.s, {quando: lambda: virar_byte(proj.destino.with_name(alvo))})
        proj.gravar()
    assert X.estado_par(proj.destino, um, novo)[0:2] == ("antigo", []), "ADR §4.5: com o programa vivo o resolvedor desfaz na hora"
    assert not (proj.pasta / "gravacao.json").exists(), "o resolvedor desfez e deixou o gravacao.json"
    gp().resolver_gravacao_pendente(pasta_projeto=proj.pasta, destino=proj.destino, ao_concluir=proj.ao)
    assert X.estado_par(proj.destino, um, novo, proj.pasta) == ("antigo", []), "D4: temporário mudado foi confirmado"
    assert proj.chamadas == []


def test_09_troca_do_lateral_recusada_com_o_programa_vivo(proj, monkeypatch):
    from test_s05_t06_gravacao_atomica_oraculo import TrocaRecusada
    proj.gravar()
    um = proj.antigo()
    proj.tx(2)
    novo = proj.novo(2)
    proj.chamadas.clear()
    monkeypatch.setattr(time, "sleep", lambda s: None)
    with pytest.MonkeyPatch.context() as mp, pytest.raises(Exception) as ei:
        mp.setattr(os, "replace", TrocaRecusada(proj.destino.with_suffix(".obim"), 10**6))
        proj.gravar()
    assert "Casa.obim.tmp" in str(ei.value), f"G2: a mensagem não diz onde está o temporário: {ei.value}"
    assert (proj.pasta / "gravacao.json").exists() and proj.destino.with_name("Casa.obim.tmp").exists() and proj.chamadas == []
    t = Traco(monkeypatch, proj.s)
    gp().resolver_gravacao_pendente(pasta_projeto=proj.pasta, destino=proj.destino, ao_concluir=proj.ao)
    assert X.estado_par(proj.destino, um, novo, proj.pasta) == ("novo", [])
    assert [c[:2] for c in proj.chamadas] == [(SEQ, True)]
    assert [e for e in t.ev if e[0] in ("replace", "unlink")][-1] == ("unlink", "gravacao.json"), t.ev


def test_10_ao_concluir_que_falha_deixa_o_diario(proj):
    gp()

    def quebra(seq):
        raise OSError(errno.ENOSPC, "disco cheio (teste)")
    novo = proj.novo(1)
    try:
        proj.gravar(ao_concluir=quebra)
    except Exception:  # noqa: BLE001  (subir ou não o erro não está decidido; o disco é que conta)
        pass
    assert (proj.pasta / "gravacao.json").exists(), "E7: ao_concluir não terminou e o gravacao.json sumiu"
    assert X.estado_par(proj.destino, None, novo)[0:2] == ("novo", [])
    gp().resolver_gravacao_pendente(pasta_projeto=proj.pasta, destino=proj.destino, ao_concluir=proj.ao)
    assert [c[0] for c in proj.chamadas] == [SEQ] and X.estado_par(proj.destino, None, novo, proj.pasta) == ("novo", [])


def test_11_resolver_sem_pendencia_nao_mexe(proj):
    proj.gravar()
    antes = X.foto_pastas(proj.destino.parent, proj.pasta)
    proj.chamadas.clear()
    for _ in range(2):
        gp().resolver_gravacao_pendente(pasta_projeto=proj.pasta, destino=proj.destino, ao_concluir=proj.ao)
    assert X.foto_pastas(proj.destino.parent, proj.pasta) == antes and proj.chamadas == [], "E8: sem gravacao.json o resolvedor mexeu"

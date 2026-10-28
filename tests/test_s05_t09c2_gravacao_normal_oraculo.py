# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S05-T09c2, gravação normal ligada ao diário e ao autosave (ADR-002 §4.5, §4.7; herança da revisão do T09b, lote
Opus 84). Quem tira os `@AINDA_NAO` é o autor.
CONTRATO (`openbim_app.autosave.Autosave`):
- `gravar_normal() -> (Gravado, Gravado)`: grava o par do usuário em `ifc_origem` (+ `.obim`) com `gravar_par(..., carimbo=True,
  pasta_projeto=pasta_projeto(lado_id))`; o seq e o sha256 do lateral (`canonico()`) são os do RETRATO (o `ler()` que escreve o IFC);
  `ao_concluir(seq) = diario.zerar(seq, ifc_caminho=ifc_origem, obim_sha256=<sha do retrato>)`. Depois, fora do `ler()`, chama
  `self.apos_gravacao_normal(seq_do_retrato)`; o erro dele sobe (o par já está gravado e o diário já zerado).
- `apos_gravacao_normal(seq=None)`: marca salvo até `seq` (None = o último anotado, como no T09b), ANTES de apagar; apaga o conteúdo
  de `autosave/`; erro ao apagar (ex.: arquivo em uso no Windows) sobe, não é engolido.
- `parar()` chamado por uma thread que segura `sessao.escrever()` ou `sessao.ler()`: levanta `RuntimeError` na hora (não espera a
  thread do autosave, que pode estar presa no `ler()`), sem parar nada; fora da sessão, `parar()` segue como no T09b.
- A pendência de sessão morta no par do usuário é resolvida no `abrir_projeto` (T09c1), nunca pelo `ao_concluir` desta sessão."""
import hashlib, os, shutil, threading  # noqa: E401
from pathlib import Path
import pytest, openbim_app.diario as D  # noqa: E401
from openbim_app.lateral import Lateral
import s05_t05_aux as X5, s05_t07_aux as X7  # noqa: E401
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401
from s05_t05_aux import igual, sha
from test_s05_t05_diario_oraculo import local  # noqa: F401
from test_s05_t09b_autosave_oraculo import _vazia, fabrica  # noqa: F401



def _base(c):
    regs, av = D.ler_diario(str(c.diario.caminho))
    assert av == [] and regs, av
    return regs[0], [r["seq"] for r in regs[1:]]


_lat_obim = lambda c: Lateral(X7.ler_obim(c.obim)[1])  # noqa: E731


def test_01_gravar_normal_zera_com_base_no_casa_e_recupera_depois(fabrica):  # noqa: F811
    # o defeito do cartão: gravar, fazer transação e cair dava "outro arquivo" e nada era recuperado
    # M: zerar sem ifc_caminho/obim_sha256; sha do lateral atual (não o gravado); não apagar o autosave; não limpar o sujo; sem carimbo
    c = fabrica()
    c.tx(1)
    assert c.auto.salvar() is True and c.auto_ifc.exists()
    c.tx(2)
    g_ifc, g_obim = c.auto.gravar_normal()
    assert Path(g_ifc.caminho) == c.casa and sha(c.casa) == g_ifc.sha256 and c.pset() == (c.lado_id, 2)
    base, resto = _base(c)
    assert resto == [] and base["seq"] == 2 and os.path.samefile(base["ifc_caminho"], c.casa)
    assert (base["ifc_sha256"], base["obim_sha256"]) == (sha(c.casa), hashlib.sha256(_lat_obim(c).canonico()).hexdigest())
    assert _vazia(c.pasta_auto) and not (c.pasta_proj / "gravacao.json").exists() and c.auto.salvar() is False
    c.tx(3)
    esperado = c.foto()
    c.diario.fechar()
    foto, avisos = X5.recuperar(c.casa, c.diario.caminho, lateral=_lat_obim(c))[:2]
    assert avisos == []
    igual(foto, esperado, "gravar, transação, cair")


def test_02_apos_gravacao_normal_marca_o_seq_dado(fabrica):  # noqa: F811
    # M: marcar o último anotado em vez do seq dado (perde o "sujo" da transação que entrou depois)
    c = fabrica()
    c.tx(1), c.tx(2)
    c.auto.apos_gravacao_normal(1)
    assert c.auto.salvar() is True
    c.tx(3)
    c.auto.apos_gravacao_normal(3)
    assert c.auto.salvar() is False


def test_03_gravar_normal_passa_o_seq_do_retrato(fabrica, monkeypatch):  # noqa: F811
    # M: seq lido depois da gravação; apos_gravacao_normal dentro do ler(); zerar levando a transação que entrou depois
    c = fabrica()
    c.tx(1), c.tx(2)
    real, vistos = c.auto.apos_gravacao_normal, []

    def espia(seq=None):
        vistos.append(seq)
        c.tx(9)  # entra entre a gravação e a marcação; ReentradaProibida se ainda estiver dentro do ler()
        return real(seq)
    monkeypatch.setattr(c.auto, "apos_gravacao_normal", espia)
    c.auto.gravar_normal()
    assert vistos == [2] and _base(c)[1] == [3] and c.auto.salvar() is True


def test_04_erro_ao_apagar_o_autosave_sobe_e_nada_se_perde(fabrica, monkeypatch):  # noqa: F811
    # M: engolir o OSError; marcar o salvo só depois de apagar; desfazer a gravação por causa do erro
    c = fabrica()
    c.tx(1)
    assert c.auto.salvar() is True
    c.tx(2)
    pasta = os.path.normcase(os.path.abspath(c.pasta_auto))
    reais = {n: getattr(os, n) for n in ("unlink", "remove", "rmdir")}

    def em_uso(nome):
        def f(caminho, *a, dir_fd=None, **k):
            alvo = os.path.normcase(os.path.abspath(os.fspath(caminho)))
            if dir_fd is not None or alvo.startswith(pasta):
                raise PermissionError(13, "arquivo em uso (simulado)", os.fspath(caminho))
            return reais[nome](caminho, *a, **k)
        return f
    with monkeypatch.context() as mp:
        for n in reais:
            mp.setattr(os, n, em_uso(n))
        mp.setattr(shutil, "rmtree", lambda p, *a, **k: em_uso("rmdir")(p))
        with pytest.raises(OSError):
            c.auto.gravar_normal()
        with pytest.raises(OSError):
            c.auto.apos_gravacao_normal()
    base, resto = _base(c)
    assert c.pset() == (c.lado_id, 2) and resto == [] and base["ifc_sha256"] == sha(c.casa)
    assert c.auto_ifc.exists() and c.auto.salvar() is False


@pytest.mark.parametrize("modo", ["escrever", "ler"])
def test_05_parar_dentro_da_sessao_levanta_e_nao_trava(fabrica, modo):  # noqa: F811
    # M: parar() que espera a thread presa no ler() (trava para sempre); parar() que para mesmo assim
    c = fabrica(intervalo_s=3600)
    c.auto.iniciar()
    erro = []

    def dentro():
        with getattr(c.sessao, modo)():
            try:
                c.auto.parar()
                erro.append(None)
            except BaseException as e:  # noqa: BLE001
                erro.append(e)
    t = threading.Thread(target=dentro, daemon=True)
    t.start()
    t.join(10)
    assert not t.is_alive(), "parar() dentro da sessão travou"
    assert len(erro) == 1 and isinstance(erro[0], RuntimeError), f"parar() dentro de {modo}() não levantou: {erro}"
    c.auto.parar()

# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S05-T09c3, acréscimos da revisão da implementação do T09c (lote Opus 84). Quem tira os `@AINDA_NAO` é o autor.
CONTRATO (soma-se ao de `test_s05_t09c_abrir_projeto_oraculo.py` e `test_s05_t09c2_gravacao_normal_oraculo.py`):
- Diário com linha final rasgada ou linha ruim: valem os registros inteiros que `ler_diario` aceita (com aviso). Ao seguir anotando nesse
  diário (Sim), o arquivo é cortado no fim do último registro aceito antes do próximo `anotar`: a transação nova sobrevive a outra queda.
- Pendência do par do usuário concluída na abertura com diário de cauda rasgada: o zerar se faz sobre os registros inteiros (avisa, não
  descarta) e o trabalho seguinte é perguntado e recuperado.
- `gravar_normal()` grava o par do usuário mesmo com erro antigo guardado da thread do autosave; esse erro sai uma vez só (depois da
  gravação, ou no `salvar()`/`parar()` seguinte), nunca impede a gravação.
- Não (recusar a recuperação): o `autosave/` antigo vai para `autosave-descartado/` (uma geração), como o diário vai para o descartado."""
import threading
import pytest, openbim_app.diario as D  # noqa: E401
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401
from s05_t05_aux import igual, sha
from test_s05_t05_diario_oraculo import local  # noqa: F401
from test_s05_t09b_autosave_oraculo import esperar_ate, fabrica  # noqa: F401
from test_s05_t09c_abrir_projeto_oraculo import _avisou, _cair, _foto, _morrer, _morrer_gravando, _texto, _tx, abre  # noqa: F401



def _rasgar(c, onde):  # "cauda": meia linha sem \n no fim (queda no meio de um anotar); "meio": a última linha inteira com CRC errado
    cam = c.diario.caminho
    if onde == "cauda":
        with open(cam, "ab") as f:
            f.write(b'0badc0de {"v":1,"seq":99,"tipo":"transa')
    else:
        b = cam.read_bytes()
        i = b.rstrip(b"\n").rfind(b"\n") + 1
        cam.write_bytes(b[:i] + (b"0" if b[i:i + 1] != b"0" else b"1") + b[i + 1:])
    regs, av = D.ler_diario(str(cam))
    assert av, "a régua não rasgou o diário"
    return regs


@pytest.mark.parametrize("onde", ["cauda", "meio"])
def test_01_linha_rasgada_sim_transacao_e_nova_queda(fabrica, abre, onde):  # noqa: F811
    # defeito 1 da revisão: o registro novo colado na linha rasgada some na queda seguinte
    # M: continuar o diário no fim do arquivo sem cortar a cauda; regravar sem os registros aceitos
    c = fabrica()
    c.tx(1), c.tx(2)
    esperado = c.foto()
    _morrer(c)
    regs = _rasgar(c, onde)
    p, perg = abre(c, True)
    assert perg == [_texto(regs)] and p.recuperado is True
    _avisou(p)
    if onde == "cauda":
        igual(_foto(p), esperado, "cauda rasgada: recuperar os registros inteiros")
    _tx(p, 3)
    depois = _foto(p)
    _cair(p)
    p2, perg2 = abre(c, True)
    assert len(perg2) == 1 and p2.recuperado is True
    igual(_foto(p2), depois, f"linha rasgada ({onde}) + Sim + transação 3 + nova queda")


def test_02_e7_e_cauda_rasgada_conclui_zera_e_recupera(fabrica, abre, monkeypatch):  # noqa: F811
    # defeito 2 da revisão: com aviso de cauda o zerar era pulado e o diário inteiro descartado sem pergunta
    # M: zerar só com o diário sem avisos; descartar o diário por causa da cauda
    c = fabrica()
    c.tx(1), c.tx(2)
    _morrer_gravando(c, monkeypatch, "E7")
    c.tx(3)
    esperado = c.foto()
    _morrer(c)
    regs = _rasgar(c, "cauda")
    p, perg = abre(c, True)
    assert p.pendencia == "concluido" and not (c.pasta_proj / "gravacao.json").exists()
    assert perg == [_texto(regs)] and p.recuperado is True
    _avisou(p)
    igual(_foto(p), esperado, "E7 + cauda rasgada")


def test_03_erro_velho_do_autosave_nao_impede_gravar_normal(fabrica):  # noqa: F811
    # defeito 3 da revisão: gravar_normal levantava o erro antigo da thread antes de gravar o par
    # M: levantar o erro velho antes de gravar; perder o erro velho; devolvê-lo duas vezes
    c = fabrica(intervalo_s=0.01)
    c.tx(1)
    chamadas, pronto = [0], threading.Event()

    def salvar_da_thread():
        chamadas[0] += 1
        if chamadas[0] >= 2:
            pronto.set()  # a 2ª chamada só vem depois de o erro da 1ª ficar guardado
            return False
        raise OSError(5, "erro velho do autosave")
    c.auto.salvar = salvar_da_thread
    c.auto.iniciar()
    assert pronto.wait(10), "a thread do autosave não rodou"
    erros = []
    try:
        c.auto.gravar_normal()
    except OSError as e:
        erros.append(e)
    try:
        c.auto.parar()
    except OSError as e:
        erros.append(e)
    assert c.pset() == (c.lado_id, 2), "o par do usuário não foi gravado"
    base = D.ler_diario(str(c.diario.caminho))[0][0]
    assert base["ifc_sha256"] == sha(c.casa)
    assert len(erros) == 1 and "erro velho" in str(erros[0]), erros


def test_04_nao_move_o_autosave_para_o_descartado(fabrica, abre):  # noqa: F811
    # defeito 4 da revisão: o Não deixava o autosave/ antigo (com .bak de mesma origem) no caminho
    # M: deixar o autosave/; apagar sem guardar
    c = fabrica()
    c.tx(1)
    assert c.auto.salvar() is True
    velho = c.auto_ifc.read_bytes()
    _morrer(c)
    p, perg = abre(c, False)
    assert len(perg) == 1 and p.recuperado is False
    assert not c.auto_ifc.exists() and (c.pasta_proj / "autosave-descartado" / c.casa.name).read_bytes() == velho


def test_05_hora_da_pergunta_e_a_do_ultimo_registro_inteiro(fabrica, abre, monkeypatch):  # noqa: F811
    # mutante M8 da revisão: hora do primeiro registro (ou da base) em vez da do último registro inteiro
    horas = iter(["2026-10-28T03:05:00+00:00", "2026-10-28T08:15:00+00:00", "2026-10-28T14:40:00+00:00"])
    real = D._hora
    monkeypatch.setattr(D, "_hora", lambda: next(horas, None) or real())
    c = fabrica()  # base às 03:05
    c.tx(1), c.tx(2)  # registros às 08:15 e às 14:40 (UTC)
    _morrer(c)
    regs = _rasgar(c, "cauda")
    assert [r["hora"][11:16] for r in regs] == ["03:05", "08:15", "14:40"]
    local = lambda h: D.datetime.datetime.fromisoformat(h).astimezone().strftime("%H:%M")  # noqa: E731
    p, perg = abre(c, True)
    assert perg == [f"Recuperar o trabalho de {local('2026-10-28T14:40:00+00:00')}?"], perg

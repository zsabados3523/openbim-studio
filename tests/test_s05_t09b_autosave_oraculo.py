# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S05-T09b, autosave (`autosave.py`, `diario.py`, `gravacao_par.py`; ADR-002 §4.5, §4.7, §4.8). Quem tira os `@AINDA_NAO` é o autor.
CONTRATO: `openbim_app.autosave`: `INTERVALO_AUTOSAVE_S = 300`; `Autosave(sessao, historico, lateral, diario, lado_id, ifc_origem, intervalo_s=...)`.
- `anotar(tipo, ifc, lado)` delega a `diario.anotar` (é o `anotar` do `Historico`). `salvar() -> bool`, síncrono: False sem transação anotada desde a
  última gravação normal ou autosave (não toca no disco); senão grava o par em `pasta_projeto(lado_id)/"autosave"/<nome de ifc_origem>` (+ `.obim`) com
  `gravar_par(..., carimbo=False, pasta_projeto=<autosave/>, autosave=True, origem_ifc_sha256=<sha256 de ifc_origem lido NESTE salvar()>)`, True.
  Serializado por trava própria (nunca a de `anotar()`): um 2º `salvar()` simultâneo espera o 1º. Não toca no par do usuário, não abre `escrever()`, o
  histórico não ganha passo. `gravar_par(..., autosave=False, origem_ifc_sha256=None)`: `"autosave": true` e `"origem_ifc_sha256"` no manifesto só com
  `autosave=True`. `Diario.ultimo_seq`: seq do último registro (0 só com a base).
- A: `Diario.zerar(seq, *, ifc_caminho=None, obim_sha256=None)`: com os opcionais, a base nova traz `ifc_caminho`, `ifc_sha256`, `ifc_tamanho` do arquivo e
  o `obim_sha256` dados; sem eles, mantém os da base; `seq` até a base: nada muda. O autosave zera com o `.ifc` dele e o sha do lateral.
- B: antes de gravar, `salvar` resolve a pendência herdada em `autosave/` com `resolver_gravacao_pendente(<autosave/>, destino, ao_concluir=None)`.
- C: o seq zerado, o passado ao `ao_concluir` e o do `gravacao.json` é o do RETRATO (o `ler()` que escreve o IFC): transação anterior ao retrato sai do
  diário, a posterior fica e mantém o "sujo"; `anotar()` de outra thread durante `salvar()` nunca trava.
- `apos_gravacao_normal()` apaga só o conteúdo de `autosave/` e limpa o "sujo". `iniciar()`/`parar()`: UMA thread daemon (iniciar 2x = 1) que chama
  `self.salvar()` a cada `intervalo_s` e segue depois de erro; o erro fica guardado (ciclo seguinte sem erro não o apaga) e sai UMA vez no próximo
  `salvar()` de fora da thread (que levanta e NÃO grava) ou em `parar()` (para, faz `join` e só então levanta); `parar()` sem iniciar é inofensivo e
  idempotente; depois dele, nenhuma thread dele viva. Sincronização: `Event`, `join` e `esperar_ate`, com prazo; sleep não decide ordem."""
from contextlib import contextmanager
import errno, hashlib, json, os, subprocess, sys, threading, time  # noqa: E401
from pathlib import Path
import pytest, openbim_app.diario as D, openbim_app.gravacao_atomica as GA, openbim_app.gravacao_par as GP  # noqa: E401
from openbim_app.lateral import Lateral; from openbim_app.sessao_modelo import SessaoModelo; from openbim_app.transacao import Historico  # noqa: E702
import s05_conteudo_aux as R, s05_t05_aux as X5, s05_t07_aux as X7  # noqa: E401
from s05_conteudo_aux import _limpa, base_ifc, exigir  # noqa: F401
from s05_t05_aux import LADO, igual, sha; from test_s05_t06_gravacao_atomica_oraculo import TrocaRecusada  # noqa: E702
from test_s05_t05_diario_oraculo import _sem_injecao, local  # noqa: F401

AINDA_NAO = pytest.mark.xfail(strict=True, reason="T09b: autosave ainda não implementado")

def mod():  # primeira linha dos casos @AINDA_NAO: falha aqui enquanto o módulo não existir
    import openbim_app.autosave as A; return A  # noqa: E702

def esperar_ate(cond, onde, prazo=10.0):  # espera por condição (não por tempo); falha se o prazo estourar
    fim = time.monotonic() + prazo
    while not cond():
        assert time.monotonic() < fim, f"prazo estourado esperando: {onde}"; time.sleep(0.001)  # noqa: E702

class CenaAuto:
    def __init__(s, tmp, base, com_obim=True, com_pset=True, criar_auto=True, intervalo_s=None):
        s.casa, objs_ini = Path(tmp) / "proj" / "Casa.ifc", ({"notas": {"n0": {"texto": "inicial"}}} if com_obim else {})
        if com_pset and not com_obim:
            s.casa = X5.fazer_casa(base, tmp)  # ela mesma cria <tmp>/proj (sem exist_ok): nada de mkdir antes
        else:
            s.casa.parent.mkdir(parents=True)
            X7.escrever_par_falso(s.casa, base, objs_ini, revisao=1, lado_id=LADO) if com_pset else R.ifcopenshell.open(base).write(str(s.casa))
        s.obim, s.f = s.casa.with_suffix(".obim"), R.ifcopenshell.open(str(s.casa))
        s.sessao, s.lat, s.lado_id = SessaoModelo(s.f), Lateral(objs_ini), LADO
        s.diario, s.auto = D.Diario.abrir(s.lado_id, str(s.casa), obim_sha256=s.sha_lat() if com_obim else None), None
        s.h = Historico(s.sessao, s.lat, codificar=D.codificar_ifc,
                        anotar=(lambda tipo, ifc, lado: s.auto.anotar(tipo, ifc, lado)) if criar_auto else s.diario.anotar)
        if criar_auto:
            kw = dict(sessao=s.sessao, historico=s.h, lateral=s.lat, diario=s.diario, lado_id=s.lado_id, ifc_origem=s.casa)
            s.auto = mod().Autosave(**kw, **({} if intervalo_s is None else {"intervalo_s": intervalo_s}))
    pasta_proj = property(lambda s: D.pasta_projeto(s.lado_id))
    pasta_auto = property(lambda s: s.pasta_proj / "autosave")
    auto_ifc = property(lambda s: s.pasta_auto / s.casa.name)
    auto_obim = property(lambda s: s.auto_ifc.with_suffix(".obim"))
    foto = lambda s: R.foto(s.f, s.lat)  # noqa: E731
    pset = lambda s: X7.pset_obim(s.f)  # noqa: E731
    pilhas = lambda s: (len(s.f.history), len(s.f.future), s.h.pode_desfazer, s.h.pode_refazer, s.h.descartados)  # noqa: E731
    sha_lat = lambda s: hashlib.sha256(s.lat.canonico()).hexdigest()  # noqa: E731
    def tx(s, tag, dentro=None):
        with s.sessao.escrever() as esc, s.h.transacao(esc) as t:
            dentro and dentro(); X7.mudar(t.ifc, t.lado.criar, tag)  # noqa: E702
    def passo(s, refazer=False):
        with s.sessao.escrever() as esc: return (s.h.refazer if refazer else s.h.desfazer)(esc)  # noqa: E701
    def fechar(s):
        if s.auto is not None:
            try: s.auto.parar()  # noqa: E701
            except Exception: pass  # noqa: BLE001, E701
        s.diario.fechar(), s.h.encerrar()

@pytest.fixture
def fabrica(tmp_path, base_ifc, local):  # noqa: F811
    exigir(); cenas = []  # noqa: E702
    yield lambda **kw: (cenas.append(CenaAuto(tmp_path / f"c_{len(cenas)}", base_ifc, **kw)), cenas[-1])[1]
    [c.fechar() for c in cenas]

def _rec_auto(c):  # (foto, avisos) de recuperar(autosave + diário), com o lateral lido do autosave
    return X5.recuperar(c.auto_ifc, c.diario.caminho, lateral=Lateral(X7.ler_obim(c.auto_obim)[1]))[:2]

def _base(c):  # (registro base, registros seguintes) do diário atual
    regs, av = D.ler_diario(str(c.diario.caminho))
    assert av == [] and regs and regs[0]["tipo"] == "base", av
    return regs[0], regs[1:]

_foto_auto = lambda ifc, obim: R.foto(R.ifcopenshell.open(str(ifc)), Lateral(X7.ler_obim(obim)[1]))  # noqa: E731
_vazia = lambda p: not p.exists() or list(p.iterdir()) == []  # noqa: E731

@pytest.mark.parametrize("com_obim", [True, False])
def test_regua_auxiliares_e_montagem(fabrica, com_obim):  # a montagem não depende do autosave (sem o FileExistsError da revisão)
    c = fabrica(criar_auto=False, com_obim=com_obim)
    assert c.casa.exists() and c.obim.exists() is com_obim and c.diario.caminho.exists()
    c.tx(1); assert [r["tipo"] for r in _base(c)[1]] == ["transacao"]  # noqa: E702

@AINDA_NAO
def test_01_sem_transacao_salvar_false_e_constante(fabrica, monkeypatch):  # M: constante != 300; sujo inicial; sujo antes de diario.anotar dar certo
    assert mod().INTERVALO_AUTOSAVE_S == 300
    c = fabrica(); sha_par = (sha(c.casa), sha(c.obim))  # noqa: E702
    assert c.diario.ultimo_seq == 0 and c.auto.salvar() is False and _vazia(c.pasta_auto)
    with pytest.raises(RuntimeError), c.sessao.escrever() as esc, c.h.transacao(esc) as t:
        X7.mudar(t.ifc, t.lado.criar, 99); raise RuntimeError("abortada")  # noqa: E702
    assert c.diario.ultimo_seq == 0 and c.auto.salvar() is False
    monkeypatch.setenv("OBIM_S05_FALHA_EM", "anotar_antes")
    with pytest.raises(OSError): c.tx(98)  # noqa: E701
    monkeypatch.delenv("OBIM_S05_FALHA_EM")
    assert c.diario.ultimo_seq == 0 and c.auto.salvar() is False and (sha(c.casa), sha(c.obim)) == sha_par and _vazia(c.pasta_auto)

@AINDA_NAO
def test_02_com_transacao_grava_autosave_manifesto_zera_diario_e_recupera(fabrica):
    # M: destino fora de autosave/; manifesto sem autosave/origem; zerar(seq errado); zerar sem ifc_caminho/obim_sha256 (A); ultimo_seq errado
    c = fabrica(); sha_origem = sha(c.casa); c.tx(1), c.tx(2), c.passo()  # noqa: E702
    assert c.diario.ultimo_seq == 3
    foto_final, novo_esp = c.foto(), X7.Novo(1, c.lado_id, R.foto(c.f, sem_pset_obim=True), bytes(c.lat.canonico()))
    assert c.auto.salvar() is True and X7.estado_par(c.auto_ifc, None, novo_esp, c.pasta_auto) == ("novo", [])
    man, _ = X7.ler_obim(c.auto_obim)
    assert man.get("autosave") is True and man.get("origem_ifc_sha256") == sha_origem
    foto_rec, avisos = _rec_auto(c); assert avisos == []  # noqa: E702
    igual(foto_rec, foto_final, "Caso 2: recuperar de autosave + diário zerado")
    base, resto = _base(c)
    assert resto == [] and base["seq"] == 3 and c.diario.ultimo_seq == 3 and os.path.samefile(base["ifc_caminho"], c.auto_ifc)
    assert (base["ifc_sha256"], base["ifc_tamanho"], base["obim_sha256"]) == (sha(c.auto_ifc), c.auto_ifc.stat().st_size, c.sha_lat())
    c.diario.zerar(1); assert c.diario.ultimo_seq == 3 and c.auto.salvar() is False  # noqa: E702

@AINDA_NAO
def test_03_segunda_transacao_depois_do_autosave_diario_e_recuperacao(fabrica):  # M: zerar apaga a 2ª tx; autosave muda sem salvar(); 2º não zera
    c = fabrica(); c.tx(1), c.tx(2)  # noqa: E702
    assert c.auto.salvar() is True and c.diario.ultimo_seq == 2
    bytes_auto_1 = (c.auto_ifc.read_bytes(), c.auto_obim.read_bytes())
    c.tx(3)
    assert c.diario.ultimo_seq == 3 and (c.auto_ifc.read_bytes(), c.auto_obim.read_bytes()) == bytes_auto_1
    base, resto = _base(c)
    assert base["seq"] == 2 and [(r["tipo"], r["seq"]) for r in resto] == [("transacao", 3)]
    foto_rec, av_rec = _rec_auto(c); assert av_rec == []  # noqa: E702
    igual(foto_rec, c.foto(), "Caso 3: recuperar de autosave + 2ª transação no diário")
    assert c.auto.salvar() is True
    base, resto = _base(c)
    assert resto == [] and base["seq"] == 3 and base["ifc_sha256"] == sha(c.auto_ifc)
    foto_rec2, av_rec2 = _rec_auto(c); assert av_rec2 == []  # noqa: E702
    igual(foto_rec2, c.foto(), "Caso 3: recuperar após 2º autosave")

@AINDA_NAO
@pytest.mark.parametrize("com_obim", [True, False], ids=["com_obim_usuario", "sem_obim_usuario"])
def test_04_arquivos_do_usuario_nunca_mudam(fabrica, com_obim):  # M: destino = ifc_origem; .obim do usuário criado/gravado; origem_ifc_sha256 errado
    c = fabrica(com_obim=com_obim)
    sha_ifc, sha_obim, pasta_antes = sha(c.casa), (sha(c.obim) if com_obim else None), X7.foto_pastas(c.casa.parent)
    for tag in (1, 2):
        c.tx(tag); assert c.auto.salvar() is True  # noqa: E702
        assert sha(c.casa) == sha_ifc and (sha(c.obim) if com_obim else None) == sha_obim and c.obim.exists() is com_obim
        assert X7.foto_pastas(c.casa.parent) == pasta_antes
        man, _ = X7.ler_obim(c.auto_obim)
        assert man.get("autosave") is True and man.get("origem_ifc_sha256") == sha_ifc

@AINDA_NAO
@pytest.mark.parametrize("com_pset", [True, False], ids=["com_pset", "sem_pset"])
def test_05_historico_revisao_e_lado_id_inalterados(fabrica, com_pset):  # M: carimbo=True; salvar abre escrever(); passo novo no histórico
    c = fabrica(com_pset=com_pset, com_obim=com_pset); c.tx(1), c.tx(2), c.passo()  # noqa: E702
    pset_antes, pilhas_antes, foto_antes = c.pset(), c.pilhas(), c.foto()
    assert pilhas_antes == (1, 1, True, True, 0)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(c.sessao, "escrever", lambda *a, **k: pytest.fail("autosave abriu sessao.escrever()"))
        assert c.auto.salvar() is True
    assert c.pset() == pset_antes and X7.pset_obim(R.ifcopenshell.open(str(c.auto_ifc))) == pset_antes and c.pilhas() == pilhas_antes
    igual(c.foto(), foto_antes, "Caso 5: modelo em memória após autosave")
    assert c.passo(refazer=True) is not None and c.pilhas()[:4] == (2, 0, True, False)

FILHO_MORTE_AUTOSAVE = """import json, os, sys
from pathlib import Path
cfg = json.loads(sys.argv[1]); sys.path[:0] = [cfg["app"], cfg["tests"]]; os.environ["OBIM_PASTA_LOCAL"] = cfg["local"]
import ifcopenshell, s05_t07_aux as X7, openbim_app.autosave as A, openbim_app.diario as D
from openbim_app.lateral import Lateral; from openbim_app.sessao_modelo import SessaoModelo; from openbim_app.transacao import Historico
casa = Path(cfg["casa"]); f = ifcopenshell.open(str(casa)); s, lat = SessaoModelo(f), Lateral(X7.ler_obim(casa.with_suffix(".obim"))[1])
d = D.Diario.abrir(cfg["lado"], str(casa), obim_sha256=cfg["obim_sha"]); auto = None
h = Historico(s, lat, codificar=D.codificar_ifc, anotar=lambda t, i, l: auto.anotar(t, i, l)); auto = A.Autosave(s, h, lat, d, cfg["lado"], casa)
with s.escrever() as esc, h.transacao(esc) as t: X7.mudar(t.ifc, t.lado.criar, 1)
assert auto.salvar() is True
with s.escrever() as esc, h.transacao(esc) as t: X7.mudar(t.ifc, t.lado.criar, 2)
os.environ["OBIM_S05_MORRER_EM"] = cfg["ponto"]; auto.salvar()
"""

@AINDA_NAO
@pytest.mark.parametrize("ponto", ["conferir", "bak"])
def test_06_morte_no_meio_do_autosave_preserva_anterior_e_recupera(tmp_path, base_ifc, local, ponto):  # noqa: F811
    # M: gravar direto no destino (sem .tmp); pendência herdada resolvida com o ao_concluir da sessão nova (B: seq órfão vai ao diário novo)
    A, c = mod(), CenaAuto(tmp_path / "obra", base_ifc, criar_auto=False)  # fotos esperadas no MESMO par do usuário (o pset tem GlobalId próprio)
    obim_sha, casa = c.sha_lat(), c.casa
    c.tx(1); f1 = c.foto(); c.tx(2); f2 = c.foto(); c.fechar()  # noqa: E702
    cfg = {"app": str(X5.RAIZ / "app"), "tests": str(X5.AQUI), "local": str(local), "casa": str(casa), "lado": LADO, "obim_sha": obim_sha, "ponto": ponto}
    env = {k: v for k, v in os.environ.items() if k not in ("OBIM_S05_FALHA_EM", "OBIM_S05_MORRER_EM")}
    r = subprocess.run([sys.executable, "-c", FILHO_MORTE_AUTOSAVE, json.dumps(cfg)], capture_output=True, text=True, timeout=120, env=env)
    assert r.returncode == 86, f"filho morreu com {r.returncode}: {r.stderr[-2000:]}"
    pasta_auto = D.pasta_projeto(LADO) / "autosave"
    auto_ifc, auto_obim, cam_diario = pasta_auto / "Casa.ifc", pasta_auto / "Casa.obim", D.pasta_projeto(LADO) / "diario" / "diario.obimlog"
    igual(_foto_auto(auto_ifc, auto_obim), f1, "Caso 6: autosave anterior (auto_1) preservado")
    regs, av = D.ler_diario(str(cam_diario))
    assert av == [] and [x["seq"] for x in regs] == [1, 2] and regs[0]["ifc_sha256"] == sha(auto_ifc)
    foto_rec, av_rec, arq_rec, lat_rec = X5.recuperar(auto_ifc, cam_diario, lateral=Lateral(X7.ler_obim(auto_obim)[1]))
    assert av_rec == [] and (ponto != "bak" or (pasta_auto / "gravacao.json").exists())
    igual(foto_rec, f2, "Caso 6: recuperar auto_1 + diário após morte no 2º autosave")
    s2, d2, auto2 = SessaoModelo(arq_rec), D.Diario.abrir(LADO, str(casa), obim_sha256=obim_sha), None  # sessão nova, diário novo (seq 0)
    h2 = Historico(s2, lat_rec, codificar=D.codificar_ifc, anotar=lambda t, i, l: auto2.anotar(t, i, l)); auto2 = A.Autosave(s2, h2, lat_rec, d2, LADO, casa)  # noqa: E702
    try:
        with s2.escrever() as esc, h2.transacao(esc) as t: X7.mudar(t.ifc, t.lado.criar, 3)  # noqa: E701
        f3 = R.foto(arq_rec, lat_rec)
        assert auto2.salvar() is True and X7.sobras(auto_ifc, pasta_auto) == []
        igual(_foto_auto(auto_ifc, auto_obim), f3, "Caso 6: autosave final é o da nova transação")
        regs3, av_d3 = D.ler_diario(str(d2.caminho))
        assert av_d3 == [] and len(regs3) == 1 and regs3[0]["seq"] == 1 and regs3[0]["ifc_sha256"] == sha(auto_ifc) and d2.ultimo_seq == 1
        foto_rec3, av3, _, _ = X5.recuperar(auto_ifc, d2.caminho, lateral=Lateral(X7.ler_obim(auto_obim)[1]))
        assert av3 == [] and auto2.salvar() is False
        igual(foto_rec3, f3, "Caso 6: novo salvar() resolveu a pendência e gravou o estado novo")
    finally:
        auto2.parar(), d2.fechar(), h2.encerrar()

@AINDA_NAO
def test_07_falha_enospc_em_salvar_propaga_e_mantem_sujo(fabrica):  # M: engolir o erro; zerar antes de gravar; limpar sujo no erro
    c = fabrica(); sha_par = (sha(c.casa), sha(c.obim)); c.tx(1)  # noqa: E702
    regs_antes, _ = D.ler_diario(str(c.diario.caminho))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(R.ifcopenshell.file, "write", lambda self, cam, *a, **k: (_ for _ in ()).throw(OSError(errno.ENOSPC, "disco cheio")))
        with pytest.raises((GA.FalhaGravacao, OSError)) as exc: c.auto.salvar()  # noqa: E701
    assert (exc.value.motivo == "disco_cheio") if isinstance(exc.value, GA.FalhaGravacao) else (exc.value.errno == errno.ENOSPC)
    assert (sha(c.casa), sha(c.obim)) == sha_par and not c.auto_ifc.exists() and not c.auto_obim.exists()
    assert D.ler_diario(str(c.diario.caminho)) == (regs_antes, [])
    assert c.auto.salvar() is True and c.auto_ifc.exists() and c.auto_obim.exists()
    base, resto = _base(c)
    assert resto == [] and base["seq"] == 1 and c.auto.salvar() is False

@AINDA_NAO
def test_08_apos_gravacao_normal_apaga_so_autosave_e_limpa_sujo(fabrica):  # M: apagar pasta_projeto inteira; não limpar sujo; mexer no diário
    c = fabrica(); c.tx(1); assert c.auto.salvar() is True  # noqa: E702
    c.tx(2); assert c.auto.salvar() is True  # noqa: E702
    assert c.auto_ifc.with_name("Casa.ifc.bak").exists() and c.auto_obim.with_name("Casa.obim.bak").exists()
    c.tx(3); sentinela = c.pasta_proj / "outro_arquivo.txt"; sentinela.write_text("preservar", encoding="utf-8")  # noqa: E702  (sujo antes)
    sha_par, bytes_diario = (sha(c.casa), sha(c.obim)), c.diario.caminho.read_bytes()
    c.auto.apos_gravacao_normal(); assert _vazia(c.pasta_auto) and (sha(c.casa), sha(c.obim)) == sha_par
    assert c.diario.caminho.read_bytes() == bytes_diario and sentinela.read_text(encoding="utf-8") == "preservar" and c.auto.salvar() is False
    c.auto.apos_gravacao_normal(); c.tx(4); assert c.auto.salvar() is True  # noqa: E702  (idempotente com a pasta vazia)

@AINDA_NAO
def test_09_retrato_em_ler_seq_do_retrato_e_sem_deadlock(fabrica):  # Caso 9 + C
    # M: retrato fora de ler(); seq (zerar ou gravacao.json) lido antes do retrato (tx anterior ao retrato duplicada); sujo=False no fim de salvar()
    #    (perde a tx pós-retrato); trava própria segurada em salvar() e pedida em anotar() (deadlock: o join com prazo reprova)
    c = fabrica(); c.tx(1)  # noqa: E702
    ler_real, write_real, ordem, erros, no_retrato, esc = c.sessao.ler, R.ifcopenshell.file.write, [], [], {}, []
    def fio(tag, **kw):  # transação em outra thread; daemon para um deadlock reprovar sem prender o pytest
        def alvo():
            try: c.tx(tag, **kw)  # noqa: E701
            except BaseException as e: erros.append(e)  # noqa: BLE001, E701
        t = threading.Thread(target=alvo, daemon=True); t.start(); return t  # noqa: E702
    def juntar(t, onde):
        t.join(timeout=20); assert not t.is_alive(), f"deadlock: anotar() de outra thread {onde} do retrato, durante salvar()"
    @contextmanager
    def ler_sinc(espera=None):  # cada ler() que salvar() pede sem segurar nenhum: antes dele entra uma transação (janela antes do retrato)
        livre = threading.current_thread() is threading.main_thread() and c.sessao.estado()["leitores"] == 0
        if livre and not no_retrato and ordem.count("antes") < 3:
            ordem.append("antes"); juntar(fio(10 + len(ordem)), "antes")  # noqa: E702
        with ler_real(espera=espera) as arq:
            yield arq
        if livre and esc:
            juntar(esc[0], "depois")
    def write_sinc(self, caminho, *a, **k):
        if threading.current_thread() is threading.main_thread() and not no_retrato:
            no_retrato.update(estado=c.sessao.estado(), seq=c.diario.ultimo_seq, foto=c.foto()); ordem.append("retrato")  # noqa: E702
            esc.append(fio(20, dentro=lambda: ordem.append("escrita_entrou")))
            esperar_ate(lambda: c.sessao.estado()["esperando_escrever"] == 1, "escritor parado na porta durante o retrato")
            r = write_real(self, caminho, *a, **k); ordem.append("retrato_fim"); return r  # noqa: E702
        return write_real(self, caminho, *a, **k)
    def replace_espia(src, dst, *a, **k):  # o seq do gravacao.json do autosave, lido na troca atômica dele
        Path(dst) == c.pasta_auto / "gravacao.json" and seq_gj.append(json.loads(Path(src).read_text(encoding="utf-8"))["seq"])
        return replace_real(src, dst, *a, **k)
    replace_real, seq_gj = os.replace, []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(c.sessao, "ler", ler_sinc); mp.setattr(R.ifcopenshell.file, "write", write_sinc); mp.setattr(os, "replace", replace_espia)  # noqa: E702
        assert c.auto.salvar() is True
    n = ordem.count("antes")
    assert seq_gj == [1 + n], f"C: gravacao.json com seq {seq_gj}, retrato {1 + n}"
    assert not erros and n >= 1 and ordem == ["antes"] * n + ["retrato", "retrato_fim", "escrita_entrou"], (erros, ordem)
    assert no_retrato["estado"]["leitores"] == 1 and no_retrato["estado"]["escritor"] is None and no_retrato["seq"] == 1 + n
    igual(_foto_auto(c.auto_ifc, c.auto_obim), no_retrato["foto"], "Caso 9: autosave = retrato")
    base, resto = _base(c)
    assert (base["seq"], [(r["tipo"], r["seq"]) for r in resto]) == (1 + n, [("transacao", 2 + n)]), "C: o diário não parte do retrato"
    foto_rec, av_rec = _rec_auto(c); assert av_rec == []  # noqa: E702
    igual(foto_rec, c.foto(), "Caso 9: recuperar do autosave + transação pós-retrato, sem duplicar")
    assert c.auto.salvar() is True and c.auto.salvar() is False  # a transação pós-retrato manteve o sujo
    base, resto = _base(c)
    assert resto == [] and base["seq"] == 2 + n

@AINDA_NAO
def test_10_thread_iniciar_parar_erro_guardado_e_idempotencia(fabrica, monkeypatch):
    # M: thread não daemon; iniciar 2x = 2 threads; erro da thread perdido (ou apagado por ciclo seguinte sem erro); erro levantado 2x;
    #    parar() sem join (thread residual); parar() sem iniciar levanta; thread para de rodar depois do erro
    c = fabrica(intervalo_s=0.01)
    c.auto.parar(), c.auto.parar()  # parar() sem iniciar é inofensivo e idempotente
    real, fase, ev, chamadores = type(c.auto).salvar, ["ok"], {k: threading.Event() for k in ("ok", "guardado", "erro_parar")}, set()
    def espiao(*a, **k):  # o salvar() que a thread chama; de fora da thread vai direto ao real
        if threading.current_thread() is threading.main_thread():
            return real(c.auto, *a, **k)
        chamadores.add(threading.current_thread())
        if fase[0] == "ok":
            r = real(c.auto)
            r and (fase.__setitem__(0, "segura"), ev["ok"].set())
            return r
        if fase[0] in ("erro_salvar", "erro_parar"):
            qual = fase[0]; fase[0] = "apos_" + qual; qual == "erro_parar" and ev["erro_parar"].set()  # noqa: E702
            raise OSError(errno.ENOSPC if qual == "erro_salvar" else errno.EIO, f"falha na thread ({qual})")
        fase[0] == "apos_erro_salvar" and ev["guardado"].set()  # a thread voltou a chamar salvar(): o erro anterior já foi guardado
        return False  # "segura": a thread roda, mas não mexe em nada até o caso pedir
    def do_autosave():  # threads novas, fora o Timer do fsync do diário
        return {t for t in threading.enumerate() if getattr(getattr(t, "function", None), "__self__", None) is not c.diario} - fios_antes
    monkeypatch.setattr(c.auto, "salvar", espiao); c.tx(1); fios_antes = set(threading.enumerate())  # noqa: E702
    c.auto.iniciar(), c.auto.iniciar()
    assert ev["ok"].wait(timeout=20), "a thread não chamou salvar()"; novos = do_autosave()  # noqa: E702
    assert len(novos) == 1 and all(t.daemon for t in novos) and chamadores == novos and c.auto_ifc.exists() and c.auto.salvar() is False
    c.tx(2); fase[0] = "erro_salvar"  # noqa: E702
    assert ev["guardado"].wait(timeout=20), "a thread parou depois do erro"
    with pytest.raises(OSError) as exc_s: c.auto.salvar()  # noqa: E701
    assert exc_s.value.errno == errno.ENOSPC and c.auto.salvar() is True and c.auto.salvar() is False
    c.tx(3); fase[0] = "erro_parar"; assert ev["erro_parar"].wait(timeout=20)  # noqa: E702
    with pytest.raises(OSError) as exc_p: c.auto.parar()  # noqa: E701
    assert exc_p.value.errno == errno.EIO; c.auto.parar()  # noqa: E702  (idempotente: não levanta o erro uma 2ª vez)
    assert not do_autosave(), f"thread residual após parar(): {do_autosave()}"
    assert c.auto.salvar() is True and c.auto.salvar() is False

def _gravar_normal(c):
    GP.gravar_par(sessao=c.sessao, historico=c.h, lateral=c.lat, destino=c.casa, pasta_projeto=c.pasta_proj, lado_id=c.lado_id,
                  seq=c.diario.ultimo_seq, carimbo=True, ao_concluir=c.diario.zerar)

@AINDA_NAO
def test_11_pendencia_isolada_entre_autosave_e_gravacao_normal(fabrica, monkeypatch):  # M: pasta_projeto = pasta do projeto; origem do __init__
    monkeypatch.setattr(time, "sleep", lambda s: None)  # só encurta as novas tentativas da troca recusada
    c = fabrica(); c.tx(1); sha_origem_1 = sha(c.casa)  # noqa: E702
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(os, "replace", TrocaRecusada(c.auto_obim, 10**6))
        with pytest.raises(Exception): c.auto.salvar()  # noqa: E701
        assert (c.pasta_auto / "gravacao.json").exists() and not (c.pasta_proj / "gravacao.json").exists()
        _gravar_normal(c)
        assert c.pset() == (c.lado_id, 2) and (c.pasta_auto / "gravacao.json").exists()
    c.tx(2); assert c.auto.salvar() is True and not (c.pasta_auto / "gravacao.json").exists()  # noqa: E702
    assert X7.ler_obim(c.auto_obim)[0]["origem_ifc_sha256"] == sha(c.casa) != sha_origem_1, "origem velha (lida antes da gravação normal)"
    c.tx(3)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(os, "replace", TrocaRecusada(c.obim, 10**6))
        with pytest.raises(Exception): _gravar_normal(c)  # noqa: E701
        assert (c.pasta_proj / "gravacao.json").exists() and not (c.pasta_auto / "gravacao.json").exists()
        c.tx(4); assert c.auto.salvar() is True and c.auto_ifc.exists()  # noqa: E702
        assert not (c.pasta_auto / "gravacao.json").exists() and (c.pasta_proj / "gravacao.json").exists()

@AINDA_NAO
def test_12_gravacao_normal_sem_campos_autosave_no_manifesto(fabrica):  # M: campos do autosave sempre no manifesto
    c = fabrica(criar_auto=False); c.tx(1)  # noqa: E702
    novo_esp = X7.Novo(2, c.lado_id, R.foto(c.f, sem_pset_obim=True), bytes(c.lat.canonico()))
    GP.gravar_par(sessao=c.sessao, historico=c.h, lateral=c.lat, destino=c.casa, pasta_projeto=c.pasta_proj, lado_id=c.lado_id,
                  seq=c.diario.ultimo_seq, carimbo=True, ao_concluir=c.diario.zerar, autosave=False, origem_ifc_sha256=None)
    assert X7.estado_par(c.casa, None, novo_esp, c.pasta_proj) == ("novo", [])
    man, _ = X7.ler_obim(c.obim)
    assert set(man) == X7.CAMPOS and not man.get("autosave") and "origem_ifc_sha256" not in man

@AINDA_NAO
def test_13_zerar_refaz_a_base_com_ifc_e_obim_novos(fabrica, tmp_path):  # decisão A
    # M: opcionais posicionais; ignorar ifc_caminho/obim_sha256; trocar a base com seq até a base (antes do retorno cedo); sem opcionais apaga campos
    c = fabrica(criar_auto=False); c.tx(1), c.tx(2)  # noqa: E702
    with pytest.raises(TypeError): c.diario.zerar(2, str(c.casa))  # noqa: E701
    nova = tmp_path / "base_nova" / "Casa.ifc"; nova.parent.mkdir(); c.f.write(str(nova))  # noqa: E702
    lat_nova, sha_nova, sha_casa = json.loads(c.lat.canonico()), c.sha_lat(), sha(c.casa)
    c.diario.zerar(1); base, resto = _base(c)  # noqa: E702
    assert (base["seq"], base["ifc_sha256"], len(resto), c.diario.ultimo_seq) == (1, sha_casa, 1, 2)
    c.diario.zerar(2, ifc_caminho=nova, obim_sha256=sha_nova); base, resto = _base(c)  # noqa: E702
    assert (base["seq"], base["ifc_sha256"], base["ifc_tamanho"], base["obim_sha256"], resto) == (2, sha(nova), nova.stat().st_size, sha_nova, [])
    assert os.path.samefile(base["ifc_caminho"], nova) and c.diario.ultimo_seq == 2
    c.tx(3); foto_rec, av, _, _ = X5.recuperar(nova, c.diario.caminho, lateral=Lateral(lat_nova)); assert av == []  # noqa: E702
    igual(foto_rec, c.foto(), "A: recuperar da base nova + diário")
    c.diario.zerar(2, ifc_caminho=c.casa, obim_sha256="0" * 64); base2, resto2 = _base(c)  # noqa: E702  (até a base: nada muda)
    assert (base2, [r["seq"] for r in resto2]) == (base, [3])
    c.diario.zerar(3); base3, resto3 = _base(c)  # noqa: E702
    assert (base3["seq"], base3["ifc_sha256"], base3["obim_sha256"], resto3, c.diario.ultimo_seq) == (3, sha(nova), sha_nova, [], 3)

@AINDA_NAO
def test_14_salvar_serializado_sem_disputar_temporarios(fabrica):  # lote 84 item 3
    # M: salvar() sem trava própria (o 2º entra em ler(), apaga/disputa .tmp e gravacao.json); 2º salvar() que desiste em vez de esperar
    c = fabrica(); c.tx(1)  # noqa: E702
    write_real, parado, solta, res, escritas = R.ifcopenshell.file.write, threading.Event(), threading.Event(), {}, []
    def write_sinc(self, caminho, *a, **k):  # a 1ª chamada fica parada no meio do retrato até o caso soltar
        nome = threading.current_thread().name; escritas.append(nome); nome == "primeira" and (parado.set(), solta.wait(timeout=20))  # noqa: E702
        return write_real(self, caminho, *a, **k)
    def chamar(nome):
        def alvo():
            try: res[nome] = c.auto.salvar()  # noqa: E701
            except BaseException as e: res[nome] = e  # noqa: BLE001, E701
        t = threading.Thread(name=nome, target=alvo, daemon=True); t.start(); return t  # noqa: E702
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(R.ifcopenshell.file, "write", write_sinc)
        t1 = chamar("primeira"); assert parado.wait(timeout=20)  # noqa: E702
        t2 = chamar("segunda"); t2.join(timeout=0.5)  # noqa: E702  (espera negativa com prazo: a 2ª não pode entrar)
        assert t2.is_alive() and escritas == ["primeira"] and c.sessao.estado()["leitores"] == 1, (escritas, res)
        solta.set(); t1.join(timeout=20); t2.join(timeout=20)  # noqa: E702
    assert not t1.is_alive() and not t2.is_alive() and res == {"primeira": True, "segunda": False}, res
    assert escritas == ["primeira"] and X7.sobras(c.auto_ifc, c.pasta_auto) == []
    igual(_foto_auto(c.auto_ifc, c.auto_obim), c.foto(), "item 3: autosave inteiro depois de dois salvar() juntos")

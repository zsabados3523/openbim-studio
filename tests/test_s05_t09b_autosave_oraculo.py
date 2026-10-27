# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes de oráculo do F0-S05-T09b: autosave na pasta local (`app/openbim_app/autosave.py`, `diario.py`, `gravacao_par.py`; ADR-002 §4.5, §4.7 e §4.8).
Não editar este arquivo na implementação; quem retira os `@AINDA_NAO` (xfail estrito) é o autor do oráculo depois da implementação.
CONTRATO: `openbim_app.autosave` (`INTERVALO_AUTOSAVE_S = 300`, `Autosave(sessao, historico, lateral, diario, lado_id, ifc_origem, intervalo_s=...)` com
`anotar(tipo, ifc, lado)`, `salvar() -> bool`, `apos_gravacao_normal()`, `iniciar()`, `parar()`); `Diario.ultimo_seq`; `gravar_par(..., autosave=False,
origem_ifc_sha256=None)` gravando `"autosave": true` e `"origem_ifc_sha256"` no manifesto só quando `autosave=True`.
MUTANTES: M1.1..M1.5 (constante, sujo inicial, falha em anotar, ultimo_seq=0), M2.1..M2.5 (par em autosave/, manifesto, zerar em ultimo_seq, recuperar),
M3.1..M3.3 (2ª tx pós-autosave e recuperar), M4.1..M4.2 (ifc/obim do usuário intactos), M5.1..M5.2 (sem carimbo/histórico), M6.1..M6.3 (morte preserva anterior),
M7.1..M7.2 (ENOSPC mantém sujo), M8.1..M8.3 (apos_gravacao_normal), M9.1..M9.2 (salvar em ler()), M10.1..M10.4 (thread), M11.1 (gravacao.json), M12.1 (normal)."""
from contextlib import contextmanager
import errno, hashlib, json, os, subprocess, sys, threading, time  # noqa: E401
from pathlib import Path
import pytest, openbim_app.diario as D, openbim_app.gravacao_atomica as GA, openbim_app.gravacao_par as GP  # noqa: E401
from openbim_app.lateral import Lateral
from openbim_app.sessao_modelo import SessaoModelo
from openbim_app.transacao import Historico
import s05_conteudo_aux as R, s05_t05_aux as X5, s05_t07_aux as X7  # noqa: E401
from s05_conteudo_aux import _limpa, base_ifc, exigir  # noqa: F401
from s05_t05_aux import LADO, igual, sha
from test_s05_t05_diario_oraculo import _sem_injecao, local  # noqa: F401
from test_s05_t06_gravacao_atomica_oraculo import TrocaRecusada

AINDA_NAO = pytest.mark.xfail(strict=True, reason="T09b: autosave ainda não implementado")


def mod():
    import openbim_app.autosave as A  # primeira linha dos casos @AINDA_NAO: falha aqui enquanto o módulo não existir
    return A


class CenaAuto:
    def __init__(s, tmp, base, com_obim=True, com_pset=True, criar_auto=True, intervalo_s=None):
        s.casa = Path(tmp) / "proj" / "Casa.ifc"
        s.casa.parent.mkdir(parents=True, exist_ok=True)
        objs_ini = {"notas": {"n0": {"texto": "inicial"}}} if com_obim else {}
        if com_obim and com_pset:
            X7.escrever_par_falso(s.casa, base, objs_ini, revisao=1, lado_id=LADO)
        elif com_pset:
            s.casa = X5.fazer_casa(base, tmp)
        else:
            R.ifcopenshell.open(base).write(str(s.casa))
        s.obim, s.f = s.casa.with_suffix(".obim"), R.ifcopenshell.open(str(s.casa))
        s.sessao, s.lat, s.lado_id = SessaoModelo(s.f), Lateral(objs_ini), LADO
        obim_sha = hashlib.sha256(s.lat.canonico()).hexdigest() if com_obim else None
        s.diario, s.auto = D.Diario.abrir(s.lado_id, str(s.casa), obim_sha256=obim_sha), None
        s.h = Historico(s.sessao, s.lat, codificar=D.codificar_ifc,
                        anotar=(lambda tipo, ifc, lado: s.auto.anotar(tipo, ifc, lado)) if criar_auto else s.diario.anotar)
        if criar_auto:
            kw = dict(sessao=s.sessao, historico=s.h, lateral=s.lat, diario=s.diario, lado_id=s.lado_id, ifc_origem=s.casa)
            if intervalo_s is not None:
                kw["intervalo_s"] = intervalo_s
            s.auto = mod().Autosave(**kw)

    pasta_proj = property(lambda s: D.pasta_projeto(s.lado_id))
    pasta_auto = property(lambda s: s.pasta_proj / "autosave")
    auto_ifc = property(lambda s: s.pasta_auto / s.casa.name)
    auto_obim = property(lambda s: s.auto_ifc.with_suffix(".obim"))
    foto = lambda s: R.foto(s.f, s.lat)  # noqa: E731
    pset = lambda s: X7.pset_obim(s.f)  # noqa: E731
    pilhas = lambda s: (len(s.f.history), len(s.f.future), s.h.pode_desfazer, s.h.pode_refazer, s.h.descartados)  # noqa: E731

    def tx(s, tag):
        with s.sessao.escrever() as esc, s.h.transacao(esc) as t:
            X7.mudar(t.ifc, t.lado.criar, tag)

    def desfazer(s):
        with s.sessao.escrever() as esc: return s.h.desfazer(esc)  # noqa: E701

    def refazer(s):
        with s.sessao.escrever() as esc: return s.h.refazer(esc)  # noqa: E701

    def fechar(s):
        if s.auto is not None:
            try: s.auto.parar()  # noqa: E701
            except Exception: pass  # noqa: BLE001, E701
        s.diario.fechar(), s.h.encerrar()


@pytest.fixture
def fabrica(tmp_path, base_ifc, local):  # noqa: F811
    exigir()
    cenas = []
    yield lambda sub="c", **kw: (cenas.append(CenaAuto(tmp_path / f"{sub}_{len(cenas)}", base_ifc, **kw)), cenas[-1])[1]
    for c in cenas:
        c.fechar()


def _rec_auto(c):
    man, objs = X7.ler_obim(c.auto_obim)
    return (man, objs, *X5.recuperar(c.auto_ifc, c.diario.caminho, lateral=Lateral(objs)))


def test_regua_auxiliares_e_montagem(fabrica):
    c = fabrica(criar_auto=False)
    assert c.casa.exists() and c.obim.exists() and c.diario.caminho.exists()
    c.tx(1)
    regs, av = D.ler_diario(str(c.diario.caminho))
    assert av == [] and [r["tipo"] for r in regs] == ["base", "transacao"]


@AINDA_NAO
def test_01_sem_transacao_salvar_false_e_constante(fabrica, monkeypatch):  # Caso 1 (M1.1..M1.5)
    assert mod().INTERVALO_AUTOSAVE_S == 300
    c = fabrica()
    sha_ifc, sha_obim = sha(c.casa), sha(c.obim)
    assert c.diario.ultimo_seq == 0 and c.auto.salvar() is False
    assert not c.pasta_auto.exists() or list(c.pasta_auto.iterdir()) == []
    with pytest.raises(RuntimeError):
        with c.sessao.escrever() as esc, c.h.transacao(esc) as t:
            X7.mudar(t.ifc, t.lado.criar, 99)
            raise RuntimeError("abortada")
    assert c.diario.ultimo_seq == 0 and c.auto.salvar() is False
    monkeypatch.setenv("OBIM_S05_FALHA_EM", "anotar_antes")
    with pytest.raises(OSError):
        c.tx(98)
    monkeypatch.delenv("OBIM_S05_FALHA_EM")
    assert c.diario.ultimo_seq == 0 and c.auto.salvar() is False and (sha(c.casa), sha(c.obim)) == (sha_ifc, sha_obim)


@AINDA_NAO
def test_02_com_transacao_grava_autosave_manifesto_zera_diario_e_recupera(fabrica):  # Caso 2 (M2.1..M2.5)
    c = fabrica()
    sha_origem = sha(c.casa)
    c.tx(1), c.tx(2), c.desfazer()
    assert c.diario.ultimo_seq == 3
    foto_final, novo_esp = c.foto(), X7.Novo(1, c.lado_id, R.foto(c.f, sem_pset_obim=True), bytes(c.lat.canonico()))
    assert c.auto.salvar() is True and c.auto_ifc.exists() and c.auto_obim.exists()
    assert X7.estado_par(c.auto_ifc, None, novo_esp, c.pasta_auto) == ("novo", [])
    man, _, foto_rec, avisos, _, _ = _rec_auto(c)
    assert man.get("autosave") is True and man.get("origem_ifc_sha256") == sha_origem and avisos == []
    igual(foto_rec, foto_final, "Caso 2: recuperar de autosave + diário zerado")
    regs, av_d = D.ler_diario(str(c.diario.caminho))
    assert av_d == [] and len(regs) == 1 and regs[0]["tipo"] == "base" and regs[0]["seq"] == 3 and c.diario.ultimo_seq == 3
    c.diario.zerar(1)
    assert c.diario.ultimo_seq == 3 and c.auto.salvar() is False


@AINDA_NAO
def test_03_segunda_transacao_depois_do_autosave_diario_e_recuperacao(fabrica):  # Caso 3 (M3.1..M3.3)
    c = fabrica()
    c.tx(1), c.tx(2)
    assert c.auto.salvar() is True and c.diario.ultimo_seq == 2
    bytes_auto_1 = (c.auto_ifc.read_bytes(), c.auto_obim.read_bytes())
    c.tx(3)
    assert c.diario.ultimo_seq == 3 and (c.auto_ifc.read_bytes(), c.auto_obim.read_bytes()) == bytes_auto_1
    regs, av = D.ler_diario(str(c.diario.caminho))
    assert av == [] and [r["tipo"] for r in regs] == ["base", "transacao"] and [r["seq"] for r in regs] == [2, 3]
    _, _, foto_rec, av_rec, _, _ = _rec_auto(c)
    assert av_rec == []
    igual(foto_rec, c.foto(), "Caso 3: recuperar de autosave + 2ª transação no diário")
    assert c.auto.salvar() is True
    regs2, av2 = D.ler_diario(str(c.diario.caminho))
    assert av2 == [] and len(regs2) == 1 and regs2[0]["seq"] == 3
    _, _, foto_rec2, av_rec2, _, _ = _rec_auto(c)
    assert av_rec2 == []
    igual(foto_rec2, c.foto(), "Caso 3: recuperar após 2º autosave")


@AINDA_NAO
@pytest.mark.parametrize("com_obim", [True, False], ids=["com_obim_usuario", "sem_obim_usuario"])
def test_04_arquivos_do_usuario_nunca_mudam(fabrica, com_obim):  # Caso 4 (M4.1..M4.2)
    c = fabrica(com_obim=com_obim)
    sha_ifc, sha_obim, pasta_antes = sha(c.casa), (sha(c.obim) if com_obim else None), X7.foto_pastas(c.casa.parent)
    for tag in (1, 2):
        c.tx(tag)
        assert c.auto.salvar() is True
        assert sha(c.casa) == sha_ifc and (sha(c.obim) if com_obim else None) == sha_obim and c.obim.exists() is com_obim
        assert X7.foto_pastas(c.casa.parent) == pasta_antes
        man, _ = X7.ler_obim(c.auto_obim)
        assert man.get("autosave") is True and man.get("origem_ifc_sha256") == sha_ifc


@AINDA_NAO
@pytest.mark.parametrize("com_pset", [True, False], ids=["com_pset", "sem_pset"])
def test_05_historico_revisao_e_lado_id_inalterados(fabrica, monkeypatch, com_pset):  # Caso 5 (M5.1..M5.2)
    c = fabrica(com_pset=com_pset, com_obim=com_pset)
    c.tx(1), c.tx(2), c.desfazer()
    pset_antes, pilhas_antes, foto_antes = c.pset(), c.pilhas(), c.foto()
    assert pilhas_antes == (1, 1, True, True, 0)
    monkeypatch.setattr(c.sessao, "escrever", lambda *a, **k: pytest.fail("autosave abriu sessao.escrever()"))
    assert c.auto.salvar() is True
    assert c.pset() == pset_antes and X7.pset_obim(R.ifcopenshell.open(str(c.auto_ifc))) == pset_antes and c.pilhas() == pilhas_antes
    igual(c.foto(), foto_antes, "Caso 5: modelo em memória após autosave")
    monkeypatch.undo()
    assert c.refazer() is not None and c.pilhas()[:4] == (2, 0, True, False)


FILHO_MORTE_AUTOSAVE = """import json, os, sys
from pathlib import Path
cfg = json.loads(sys.argv[1]); sys.path[:0] = [cfg["app"], cfg["tests"]]; os.environ["OBIM_PASTA_LOCAL"] = cfg["local"]
import ifcopenshell, s05_t07_aux as X7, openbim_app.autosave as A, openbim_app.diario as D
from openbim_app.lateral import Lateral
from openbim_app.sessao_modelo import SessaoModelo
from openbim_app.transacao import Historico
casa = Path(cfg["casa"]); f = ifcopenshell.open(str(casa)); s, lat = SessaoModelo(f), Lateral(X7.ler_obim(casa.with_suffix(".obim"))[1])
d = D.Diario.abrir(cfg["lado"], str(casa), obim_sha256=cfg["obim_sha"]); auto = None
h = Historico(s, lat, codificar=D.codificar_ifc, anotar=lambda t, i, l: auto.anotar(t, i, l))
auto = A.Autosave(s, h, lat, d, cfg["lado"], casa)
with s.escrever() as esc, h.transacao(esc) as t: X7.mudar(t.ifc, t.lado.criar, 1)
assert auto.salvar() is True
with s.escrever() as esc, h.transacao(esc) as t: X7.mudar(t.ifc, t.lado.criar, 2)
os.environ["OBIM_S05_MORRER_EM"] = cfg["ponto"]; auto.salvar()
"""


@AINDA_NAO
@pytest.mark.parametrize("ponto", ["conferir", "bak"])
def test_06_morte_no_meio_do_autosave_preserva_anterior_e_recupera(tmp_path, base_ifc, local, ponto):  # noqa: F811  # Caso 6 (M6.1..M6.3)
    A = mod()
    c_ref = CenaAuto(tmp_path / "ref", base_ifc)
    c_ref.tx(1); f1 = c_ref.foto(); c_ref.tx(2); f2 = c_ref.foto(); c_ref.fechar()  # noqa: E702
    c = CenaAuto(tmp_path / "obra", base_ifc, criar_auto=False)
    obim_sha, casa = hashlib.sha256(c.lat.canonico()).hexdigest(), c.casa
    c.fechar()
    cfg = {"app": str(X5.RAIZ / "app"), "tests": str(X5.AQUI), "local": str(local), "casa": str(casa), "lado": LADO, "obim_sha": obim_sha, "ponto": ponto}
    r = subprocess.run([sys.executable, "-c", FILHO_MORTE_AUTOSAVE, json.dumps(cfg)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 86, f"filho morreu com {r.returncode}: {r.stderr[-2000:]}"

    pasta_auto = D.pasta_projeto(LADO) / "autosave"
    auto_ifc, auto_obim, cam_diario = pasta_auto / "Casa.ifc", pasta_auto / "Casa.obim", D.pasta_projeto(LADO) / "diario" / "diario.obimlog"
    _, objs_auto1 = X7.ler_obim(auto_obim)
    igual(R.foto(R.ifcopenshell.open(str(auto_ifc)), Lateral(objs_auto1)), f1, "Caso 6: autosave anterior (auto_1) preservado")
    regs, av = D.ler_diario(str(cam_diario))
    assert av == [] and [x["seq"] for x in regs] == [1, 2]
    foto_rec, av_rec, arq_rec, lat_rec = X5.recuperar(auto_ifc, cam_diario, lateral=Lateral(objs_auto1))
    assert av_rec == [] and (ponto != "bak" or (pasta_auto / "gravacao.json").exists())
    igual(foto_rec, f2, "Caso 6: recuperar auto_1 + diário após morte no 2º autosave")
    s2, d2, auto2 = SessaoModelo(arq_rec), D.Diario.abrir(LADO, str(casa), obim_sha256=obim_sha), None
    h2 = Historico(s2, lat_rec, codificar=D.codificar_ifc, anotar=lambda t, i, l: auto2.anotar(t, i, l))
    auto2 = A.Autosave(s2, h2, lat_rec, d2, LADO, casa)
    try:
        with s2.escrever() as esc, h2.transacao(esc) as t:
            X7.mudar(t.ifc, t.lado.criar, 3)
        f3 = R.foto(arq_rec, lat_rec)
        assert auto2.salvar() is True and X7.sobras(auto_ifc, pasta_auto) == []
        foto_rec3, av3, _, _ = X5.recuperar(auto_ifc, d2.caminho, lateral=Lateral(X7.ler_obim(auto_obim)[1]))
        assert av3 == []
        igual(foto_rec3, f3, "Caso 6: novo salvar() resolveu pendência e gravou estado novo")
    finally:
        d2.fechar(), h2.encerrar()


@AINDA_NAO
def test_07_falha_enospc_em_salvar_propaga_e_mantem_sujo(fabrica, monkeypatch):  # Caso 7 (M7.1..M7.2)
    c = fabrica()
    sha_ifc, sha_obim = sha(c.casa), sha(c.obim)
    c.tx(1)
    regs_antes, _ = D.ler_diario(str(c.diario.caminho))
    write_real = R.ifcopenshell.file.write
    monkeypatch.setattr(R.ifcopenshell.file, "write", lambda self, cam, *a, **k: (_ for _ in ()).throw(OSError(errno.ENOSPC, "disco cheio")))
    with pytest.raises((GA.FalhaGravacao, OSError)) as exc:
        c.auto.salvar()
    assert (exc.value.motivo == "disco_cheio") if isinstance(exc.value, GA.FalhaGravacao) else (exc.value.errno == errno.ENOSPC)
    assert (sha(c.casa), sha(c.obim)) == (sha_ifc, sha_obim) and not c.auto_ifc.exists() and not c.auto_obim.exists()
    assert D.ler_diario(str(c.diario.caminho)) == (regs_antes, [])
    monkeypatch.setattr(R.ifcopenshell.file, "write", write_real)
    assert c.auto.salvar() is True and c.auto_ifc.exists() and c.auto_obim.exists()
    regs_depois, av = D.ler_diario(str(c.diario.caminho))
    assert av == [] and len(regs_depois) == 1 and regs_depois[0]["seq"] == 1 and c.auto.salvar() is False


@AINDA_NAO
def test_08_apos_gravacao_normal_apaga_so_autosave_e_limpa_sujo(fabrica):  # Caso 8 (M8.1..M8.3)
    c = fabrica()
    c.tx(1); assert c.auto.salvar() is True  # noqa: E702
    c.tx(2); assert c.auto.salvar() is True  # noqa: E702
    assert c.auto_ifc.with_name("Casa.ifc.bak").exists() and c.auto_obim.with_name("Casa.obim.bak").exists()
    c.tx(3)  # deixa o autosave sujo antes da gravação normal
    sentinela = c.pasta_proj / "outro_arquivo.txt"
    sentinela.write_text("preservar", encoding="utf-8")
    sha_ifc, sha_obim, bytes_diario = sha(c.casa), sha(c.obim), c.diario.caminho.read_bytes()
    c.auto.apos_gravacao_normal()
    assert not c.pasta_auto.exists() or list(c.pasta_auto.iterdir()) == []
    assert (sha(c.casa), sha(c.obim)) == (sha_ifc, sha_obim)
    assert c.diario.caminho.read_bytes() == bytes_diario and sentinela.read_text(encoding="utf-8") == "preservar"
    assert c.auto.salvar() is False
    c.auto.apos_gravacao_normal()  # idempotente com pasta vazia
    c.tx(4)
    assert c.auto.salvar() is True


@AINDA_NAO
def test_09_autosave_roda_em_ler_e_escrita_concorrente_espera(fabrica, monkeypatch):  # Caso 9 (M9.1..M9.2)
    c = fabrica()
    c.tx(1)
    foto_1, write_real, esc_real = c.foto(), R.ifcopenshell.file.write, c.sessao.escrever
    ev_pediu, ev_entrou, ordem, estado_no_write = threading.Event(), threading.Event(), [], []

    @contextmanager
    def escrever_sinc(espera=None):
        threading.current_thread().name == "escritor" and ev_pediu.set()
        with esc_real(espera=espera) as esc:
            if threading.current_thread().name == "escritor":
                ordem.append("escrita_entrou"), ev_entrou.set()
            yield esc

    t_esc = threading.Thread(name="escritor", target=lambda: c.tx(2))

    def write_sinc(self, caminho, *a, **k):
        estado_no_write.append(c.sessao.estado()), ordem.append("retrato_inicio"), t_esc.start()
        assert ev_pediu.wait(timeout=5) and not ev_entrou.is_set()
        r = write_real(self, caminho, *a, **k)
        assert not ev_entrou.is_set(), "escrita entrou antes do fim do retrato em ler()"
        ordem.append("retrato_fim")
        return r

    monkeypatch.setattr(R.ifcopenshell.file, "write", write_sinc)
    monkeypatch.setattr(c.sessao, "escrever", escrever_sinc)
    assert c.auto.salvar() is True
    t_esc.join(timeout=10)
    assert estado_no_write[0]["leitores"] == 1 and estado_no_write[0]["escritor"] is None and ordem == ["retrato_inicio", "retrato_fim", "escrita_entrou"]
    igual(R.foto(R.ifcopenshell.open(str(c.auto_ifc)), Lateral(X7.ler_obim(c.auto_obim)[1])), foto_1, "Caso 9: retrato tem só a transação 1")
    regs, av = D.ler_diario(str(c.diario.caminho))
    assert av == [] and [r["seq"] for r in regs] == [1, 2]
    _, _, foto_rec, av_rec, _, _ = _rec_auto(c)
    assert av_rec == []
    igual(foto_rec, c.foto(), "Caso 9: recuperar do autosave + transação concorrente no diário")


@AINDA_NAO
def test_10_thread_iniciar_parar_erro_guardado_e_idempotencia(fabrica, monkeypatch):  # Caso 10 (M10.1..M10.4)
    c = fabrica(intervalo_s=0.02)
    fios_antes, gp_real = set(threading.enumerate()), GP.gravar_par
    c.auto.parar(), c.auto.parar()  # parar() sem iniciar é inofensivo e idempotente
    ev_ok, ev_erro_salvar, ev_erro_parar, modo, daemons = threading.Event(), threading.Event(), threading.Event(), ["ok"], []

    def _sinalizar_quando_dormir(ev):
        def prof(frame, event, arg):
            if event in ("call", "c_call") and ("wait" in str(arg) or "sleep" in str(arg) or frame.f_code.co_name in ("wait", "sleep")):
                sys.setprofile(None), ev.set()
        sys.setprofile(prof)

    def gp_espio(*a, **k):
        t = threading.current_thread()
        if t is not threading.main_thread():
            daemons.append(t.daemon)
            if modo[0] in ("erro_salvar", "erro_parar"):
                qual, modo[0] = modo[0], "espera"
                _sinalizar_quando_dormir(ev_erro_salvar if qual == "erro_salvar" else ev_erro_parar)
                raise OSError(errno.ENOSPC if qual == "erro_salvar" else errno.EIO, f"falha na thread ({qual})")
        r = gp_real(*a, **k)
        if t is not threading.main_thread() and modo[0] == "ok":
            ev_ok.set()
        return r

    monkeypatch.setattr(GP, "gravar_par", gp_espio)
    c.tx(1); c.auto.iniciar(); c.auto.iniciar()  # noqa: E702
    assert ev_ok.wait(timeout=5) and daemons and all(daemons) and c.auto_ifc.exists()
    modo[0] = "erro_salvar"; c.tx(2); assert ev_erro_salvar.wait(timeout=5)  # noqa: E702
    with pytest.raises(OSError) as exc_s:
        c.auto.salvar()
    assert exc_s.value.errno == errno.ENOSPC and c.auto.salvar() is True and c.auto.salvar() is False
    modo[0] = "erro_parar"; c.tx(3); assert ev_erro_parar.wait(timeout=5)  # noqa: E702
    with pytest.raises(OSError) as exc_p:
        c.auto.parar()
    assert exc_p.value.errno == errno.EIO
    c.auto.parar()  # idempotente: não levanta o erro uma 2ª vez
    assert not (set(threading.enumerate()) - fios_antes), f"thread residual após parar(): {set(threading.enumerate()) - fios_antes}"
    assert c.auto.salvar() is True and c.auto.salvar() is False


@AINDA_NAO
def test_11_pendencia_isolada_entre_autosave_e_gravacao_normal(fabrica, monkeypatch):  # Caso 11 (M11.1)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    c = fabrica()
    c.tx(1)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(os, "replace", TrocaRecusada(c.auto_obim, 10**6))
        with pytest.raises(Exception):
            c.auto.salvar()
        assert (c.pasta_auto / "gravacao.json").exists() and not (c.pasta_proj / "gravacao.json").exists()
        GP.gravar_par(sessao=c.sessao, historico=c.h, lateral=c.lat, destino=c.casa, pasta_projeto=c.pasta_proj,
                      lado_id=c.lado_id, seq=c.diario.ultimo_seq, carimbo=True, ao_concluir=c.diario.zerar)
        assert c.pset() == (c.lado_id, 2) and (c.pasta_auto / "gravacao.json").exists()
    c.tx(2)
    assert c.auto.salvar() is True and not (c.pasta_auto / "gravacao.json").exists()
    c.tx(3)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(os, "replace", TrocaRecusada(c.obim, 10**6))
        with pytest.raises(Exception):
            GP.gravar_par(sessao=c.sessao, historico=c.h, lateral=c.lat, destino=c.casa, pasta_projeto=c.pasta_proj,
                          lado_id=c.lado_id, seq=c.diario.ultimo_seq, carimbo=True, ao_concluir=c.diario.zerar)
        assert (c.pasta_proj / "gravacao.json").exists() and not (c.pasta_auto / "gravacao.json").exists()
        c.tx(4)
        assert c.auto.salvar() is True and c.auto_ifc.exists()
        assert not (c.pasta_auto / "gravacao.json").exists() and (c.pasta_proj / "gravacao.json").exists()


@AINDA_NAO
def test_12_gravacao_normal_sem_campos_autosave_no_manifesto(fabrica):  # Caso 12 (M12.1)
    c = fabrica(criar_auto=False)
    c.tx(1)
    novo_esp = X7.Novo(2, c.lado_id, R.foto(c.f, sem_pset_obim=True), bytes(c.lat.canonico()))
    GP.gravar_par(sessao=c.sessao, historico=c.h, lateral=c.lat, destino=c.casa, pasta_projeto=c.pasta_proj,
                  lado_id=c.lado_id, seq=c.diario.ultimo_seq, carimbo=True, ao_concluir=c.diario.zerar,
                  autosave=False, origem_ifc_sha256=None)
    assert X7.estado_par(c.casa, None, novo_esp, c.pasta_proj) == ("novo", [])
    man, _ = X7.ler_obim(c.obim)
    assert set(man) == X7.CAMPOS and not man.get("autosave") and "origem_ifc_sha256" not in man

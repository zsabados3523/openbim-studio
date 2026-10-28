# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S05-T09a2: `Diario.zerar` por troca atômica (`app/openbim_app/diario.py`; ADR-002 §4.4; revisão do lote Opus 84, item 6).
Não editar na implementação; quem tira os `@AINDA_NAO` (xfail estrito) é o autor do oráculo, depois da implementação.
CONTRATO de `zerar(seq)` (o que já valia no T09a continua: base com `seq`, registros `<= seq` saem, `> seq` ficam, idempotente, sob a trava):
- O diário novo (base + registros que ficam) é escrito num arquivo temporário NA MESMA PASTA do diário, que recebe `os.fsync` e só então entra no
  lugar por `os.replace(temporario, diario)`. Antes da troca o descritor antigo do diário é fechado (no Windows a troca falha com ele aberto); depois
  dela o diário é reaberto e os `anotar` seguintes vão ao arquivo novo, no fim, com `seq` contínuo.
- Falha (ENOSPC, EIO, qualquer `OSError`) ANTES da troca: o erro sobe, o arquivo do diário fica com os mesmos bytes, o temporário é apagado e o diário
  continua utilizável (não fica quebrado: `anotar` segue no arquivo antigo e um `zerar` depois funciona).
- Queda do processo em qualquer ponto: o diário no disco é o antigo inteiro (antes da troca) ou o novo inteiro (depois), sempre legível sem aviso; o
  temporário que sobrar some no próximo `Diario.abrir`, que guarda no `diario-descartado.obimlog` exatamente o que estava no disco.
- Depois da troca, a pasta do diário recebe `os.fsync` (como `gravacao_atomica.confirmar`; exigido fora do Windows, onde não se abre pasta).
- Falha ao REABRIR o diário depois da troca: o erro sobe, o disco tem o diário novo inteiro, o diário fica quebrado (`anotar` seguinte levanta
  `HistoricoQuebrado`) e `fechar()` é silencioso.
- Na pasta do diário não sobra nada além de `diario.obimlog` e `diario-descartado*`. Só APIs portáveis (nada de `/proc`, `O_TMPFILE`, `fcntl`).
Os nomes privados usados aqui (`_f`, `_quebrado`, `_base`) já são do T09a. Falha injetada por `os.fsync`/`os.replace` espiões e pela fixture
`disco_diario` do T09a (disco cheio e EIO de escrita só nos arquivos da pasta do diário). Queda: processo filho com `os._exit(86)`."""
import builtins, errno, io, json, os, stat, subprocess, sys  # noqa: E401
from pathlib import Path
import pytest
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401  (fixtures)
from openbim_app.transacao import HistoricoQuebrado
from s05_t05_aux import AQUI, LADO, RAIZ, caminho_diario, mod
from test_s05_t05_diario_oraculo import _sem_injecao, casa, local, registros_crus  # noqa: F401  (fixtures)
from test_s05_t09a_diario_oraculo import disco_diario  # noqa: F401  (fixture)



def _sobras(cam):  # tudo na pasta do diário além dele e dos descartados
    return sorted(p.name for p in cam.parent.iterdir() if p != cam and not p.name.startswith("diario-descartado"))


def _outro_da_pasta(fd, cam):  # o fd é de um arquivo da pasta do diário que NÃO é o diário (o temporário)
    st = os.fstat(fd)
    return any(p != cam and p.is_file() and os.path.samestat(st, os.stat(p)) for p in cam.parent.iterdir())


def _quatro(D, casa):  # diário com base seq 0 e registros 1..4
    d = D.Diario.abrir(LADO, str(casa))
    for i in range(1, 5):
        d.anotar("transacao", [], [["notas", f"n{i}", None, {"v": i}]])
    return d


def _seqs(D, cam):
    regs, av = D.ler_diario(str(cam))
    assert av == [], av
    return [(r["tipo"], r["seq"]) for r in regs]


VELHO, NOVO = [("base", 0)] + [("transacao", i) for i in range(1, 5)], [("base", 2), ("transacao", 3), ("transacao", 4)]


def test_zerar_feliz_reabre_e_continua_anotando(local, casa):  # regressão (passa hoje e depois): nada se perde nem duplica
    D, cam = mod(), caminho_diario(local)
    d = _quatro(D, casa)
    try:
        d.zerar(2)
        assert _seqs(D, cam) == NOVO and _sobras(cam) == []
        d.anotar("transacao", [], [["notas", "n5", None, {"v": 5}]])
        d.sincronizar()
        assert _seqs(D, cam) == NOVO + [("transacao", 5)] and [r["seq"] for r in registros_crus(cam)] == [2, 3, 4, 5]
        d.zerar(2), d.zerar(1)  # idempotente e abaixo da base: nada muda
        assert _seqs(D, cam) == NOVO + [("transacao", 5)]
        d.zerar(5)
        d.anotar("transacao", [], [])
        assert _seqs(D, cam) == [("base", 5), ("transacao", 6)] and _sobras(cam) == []
    finally:
        d.fechar()
    assert _seqs(D, cam) == [("base", 5), ("transacao", 6)]


def test_ordem_temporario_fsync_fecha_e_troca(local, casa):
    # M: reescrever no lugar; sem fsync do temporário; fsync depois da troca; troca com o descritor antigo aberto (falha no Windows); não reabrir;
    #    sem fsync da pasta depois da troca (fora do Windows)
    D, cam = mod(), caminho_diario(local)
    d = _quatro(D, casa)
    fsync_real, replace_real, ev = os.fsync, os.replace, []
    f_antigo = d._f

    def fsync_espia(fd):
        st = os.fstat(fd)
        if stat.S_ISDIR(st.st_mode):
            os.path.samestat(st, os.stat(cam.parent)) and ev.append("fsync_pasta")
        elif _outro_da_pasta(fd, cam):
            ev.append("fsync_tmp")
        return fsync_real(fd)

    def replace_espia(src, dst, *a, **k):
        if Path(dst) == cam:
            assert Path(src).parent == cam.parent, f"temporário fora da pasta do diário: {src}"
            ev.append("troca_com_antigo_" + ("fechado" if f_antigo.closed else "aberto"))
        return replace_real(src, dst, *a, **k)

    try:
        with pytest.MonkeyPatch.context() as mp:  # (não usar monkeypatch.undo(): desfaria o OBIM_PASTA_LOCAL da fixture local)
            mp.setattr(os, "fsync", fsync_espia), mp.setattr(os, "replace", replace_espia)
            d.zerar(2)
        assert "troca_com_antigo_fechado" in ev and ev.index("fsync_tmp") < ev.index("troca_com_antigo_fechado"), ev
        assert ev.count("troca_com_antigo_fechado") == 1 and "troca_com_antigo_aberto" not in ev, ev
        if sys.platform != "win32":
            assert "fsync_pasta" in ev[ev.index("troca_com_antigo_fechado"):], f"sem fsync da pasta depois da troca: {ev}"
        assert _seqs(D, cam) == NOVO and _sobras(cam) == [] and not d._f.closed
        d.anotar("transacao", [], [["notas", "n5", None, {"v": 5}]])
        assert _seqs(D, cam) == NOVO + [("transacao", 5)]
    finally:
        d.fechar()


def _mesmo(a, b):
    return os.path.normcase(os.path.abspath(os.fspath(a))) == os.path.normcase(os.path.abspath(os.fspath(b)))


def test_falha_ao_reabrir_depois_da_troca_quebra_e_disco_fica_novo(local, casa):
    # M: engolir o erro da reabertura; seguir anotando no descritor velho (fechado ou do arquivo antigo); fechar() que levanta
    D, cam = mod(), caminho_diario(local)
    d = _quatro(D, casa)
    replace_real, open_real, io_open_real, os_open_real, trocou, recusas = os.replace, builtins.open, io.open, os.open, [], []

    def replace_espia(src, dst, *a, **k):
        r = replace_real(src, dst, *a, **k)
        _mesmo(dst, cam) and trocou.append(True)
        return r

    def recusar(caminho):
        if trocou and not isinstance(caminho, int) and _mesmo(caminho, cam):
            recusas.append(os.fspath(caminho))
            raise OSError(errno.EIO, "falha simulada ao reabrir o diário", str(caminho))

    def open_falha(f, *a, **k):
        recusar(f)
        return open_real(f, *a, **k)

    def io_open_falha(f, *a, **k):
        recusar(f)
        return io_open_real(f, *a, **k)

    def os_open_falha(f, *a, **k):
        recusar(f)
        return os_open_real(f, *a, **k)

    try:
        with pytest.MonkeyPatch.context() as mp:
            for alvo, nome, v in ((os, "replace", replace_espia), (builtins, "open", open_falha), (io, "open", io_open_falha), (os, "open", os_open_falha)):
                mp.setattr(alvo, nome, v)
            with pytest.raises(OSError) as exc:
                d.zerar(2)
        assert exc.value.errno == errno.EIO and trocou and recusas, (exc.value, trocou, recusas)
        assert _seqs(D, cam) == NOVO and _sobras(cam) == [], "o disco deveria ter o diário novo inteiro"
        with pytest.raises(HistoricoQuebrado):
            d.anotar("transacao", [], [["notas", "n5", None, {"v": 5}]])
        assert _seqs(D, cam) == NOVO
    finally:
        d.fechar()  # silencioso: não levanta
    assert _seqs(D, cam) == NOVO


FALHAS = ["escrita_enospc", "escrita_eio", "fsync_tmp_eio", "troca_eio"]


@pytest.mark.parametrize("ponto", FALHAS)
def test_falha_antes_da_troca_mantem_antigo_integro_e_utilizavel(local, casa, disco_diario, monkeypatch, ponto):
    # M: reescrever no lugar (disco cheio corta o diário); temporário que sobra; quebrar o diário numa falha que não tocou nele;
    #    anotar seguinte no descritor errado (registro perdido ou fora de ordem)
    D, cam = mod(), caminho_diario(local)
    d = _quatro(D, casa)
    antes = cam.read_bytes()
    fsync_real, replace_real = os.fsync, os.replace

    def fsync_falha(fd):
        if _outro_da_pasta(fd, cam):
            raise OSError(errno.EIO, "falha simulada no fsync do temporário")
        return fsync_real(fd)

    def replace_falha(src, dst, *a, **k):
        if Path(dst) == cam:
            raise OSError(errno.EIO, "falha simulada na troca do diário")
        return replace_real(src, dst, *a, **k)

    try:
        if ponto == "escrita_enospc":
            disco_diario.livre = 40
        elif ponto == "escrita_eio":
            disco_diario.livre, disco_diario.erro_escrita = 40, OSError(errno.EIO, "falha simulada de escrita")
        elif ponto == "fsync_tmp_eio":
            monkeypatch.setattr(os, "fsync", fsync_falha)
        else:
            monkeypatch.setattr(os, "replace", replace_falha)
        with pytest.raises(OSError) as exc:
            d.zerar(2)
        disco_diario.livre = disco_diario.erro_escrita = None
        monkeypatch.setattr(os, "fsync", fsync_real), monkeypatch.setattr(os, "replace", replace_real)
        assert exc.value.errno == (errno.ENOSPC if ponto == "escrita_enospc" else errno.EIO), exc.value
        assert cam.read_bytes() == antes, "o diário mudou numa falha antes da troca"
        assert _seqs(D, cam) == VELHO and _sobras(cam) == [] and not d._quebrado and d._base["seq"] == 0
        d.anotar("transacao", [], [["notas", "n5", None, {"v": 5}]])  # segue no arquivo antigo
        assert _seqs(D, cam) == VELHO + [("transacao", 5)]
        d.zerar(2)
        assert _seqs(D, cam) == NOVO + [("transacao", 5)] and _sobras(cam) == []
        d.anotar("transacao", [], [])
        assert _seqs(D, cam) == NOVO + [("transacao", 5), ("transacao", 6)]
    finally:
        disco_diario.livre = disco_diario.erro_escrita = None
        d.fechar()


FILHO_QUEDA = r"""import json, os, sys
from pathlib import Path
cfg = json.loads(sys.argv[1]); sys.path[:0] = [cfg["app"], cfg["tests"]]; os.environ["OBIM_PASTA_LOCAL"] = cfg["local"]
import openbim_app.diario as D
cam, ponto = Path(cfg["cam"]), cfg["ponto"]
def outro(fd):
    st = os.fstat(fd)
    return any(p != cam and p.is_file() and os.path.samestat(st, os.stat(p)) for p in cam.parent.iterdir())
d = D.Diario.abrir(cfg["lado"], cfg["casa"])
for i in range(1, 5): d.anotar("transacao", [], [["notas", f"n{i}", None, {"v": i}]])
d.sincronizar()
fs, rp = os.fsync, os.replace
def fsync(fd):
    if ponto == "fsync_tmp" and outro(fd): os._exit(86)
    return fs(fd)
def replace(src, dst, *a, **k):
    if Path(dst) == cam and ponto == "antes_da_troca": os._exit(86)
    r = rp(src, dst, *a, **k)
    if Path(dst) == cam and ponto == "depois_da_troca": os._exit(86)
    return r
os.fsync, os.replace = fsync, replace
d.zerar(2)
print("zerar terminou sem passar pelo ponto", ponto, flush=True)
"""


@pytest.mark.parametrize("ponto, esperado", [("fsync_tmp", "velho"), ("antes_da_troca", "velho"), ("depois_da_troca", "novo")])
def test_queda_em_cada_ponto_deixa_antigo_ou_novo_inteiro(local, casa, ponto, esperado):
    # M: reescrever no lugar (nunca passa pelos pontos: filho termina com 0); troca antes do fsync; abrir que não limpa o temporário órfão
    D, cam = mod(), caminho_diario(local)
    cfg = {"app": str(RAIZ / "app"), "tests": str(AQUI), "local": str(local), "cam": str(cam), "lado": LADO, "casa": str(casa), "ponto": ponto}
    env = {k: v for k, v in os.environ.items() if k not in ("OBIM_S05_FALHA_EM", "OBIM_S05_MORRER_EM")}
    r = subprocess.run([sys.executable, "-c", FILHO_QUEDA, json.dumps(cfg)], capture_output=True, text=True, timeout=120, env=env)
    assert r.returncode == 86, f"filho saiu com {r.returncode}: {r.stdout[-500:]} {r.stderr[-2000:]}"
    no_disco = cam.read_bytes()
    assert _seqs(D, cam) == (VELHO if esperado == "velho" else NOVO), f"queda em {ponto}: diário não é o {esperado} inteiro"
    assert [r["seq"] for r in registros_crus(cam)] == ([0, 1, 2, 3, 4] if esperado == "velho" else [2, 3, 4])
    d = D.Diario.abrir(LADO, str(casa))  # a reabertura limpa o temporário órfão e guarda o que estava no disco
    try:
        assert _sobras(cam) == [] and (cam.parent / "diario-descartado.obimlog").read_bytes() == no_disco
        d.anotar("transacao", [], [])
        assert _seqs(D, cam) == [("base", 0), ("transacao", 1)]
    finally:
        d.fechar()

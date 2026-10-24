# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S05-T06 (cartão F0-S05-T06; ADR-002 §4.5 e §4.8; T00 G1 a G6 menos G4; `F0-S05-oraculos-T04-T06.md`, casos 1 a 13).
Quem implementa não edita este arquivo; o autor do oráculo tira os `@AINDA_NAO` (xfail estrito por falta do módulo) depois, em commit próprio.
CONTRATO (`app/openbim_app/gravacao_atomica.py`, sem Qt, sem obimcore; nomes do ADR-002 §4.8, nada além):
1. `ETAPAS == ("escrever", "fsync", "conferir", "bak", "trocar", "fsync_pasta")`, nesta ordem; `_etapa(nome, caminho)` é chamada no
   COMEÇO de cada etapa (também `bak` sem destino antigo e `fsync_pasta` no Windows) e lê o ambiente NA HORA: `OBIM_S05_FALHA_EM=<etapa>`
   levanta `OSError(errno.EIO)`; `OBIM_S05_MORRER_EM=<etapa>` chama `os._exit(86)`.
2. `preparar(destino, escrever, conferir=None) -> Preparado(destino, temporario, sha256, tamanho)`: chama `escrever(temporario)` com
   `temporario` = `Casa.ifc.tmp` na pasta do destino, faz `flush` + `os.fsync` dele (sha256 hexadecimal, tamanho em bytes) e
   `conferir(temporario)` se dado. `confirmar(preparado) -> Gravado(caminho, sha256, tamanho, bak)`: etapa
   `bak` (com destino antigo: `os.link` do destino para `Casa.ifc.bak.tmp`, ou cópia se o link falhar, e `os.replace` para
   `Casa.ifc.bak`; o destino nunca deixa de existir; sem destino antigo não faz nada e `bak is None`), `trocar` (`os.replace` do
   temporário para o destino; `PermissionError`: 6 tentativas ao todo, espera de 0,05 s dobrando) e `fsync_pasta` (`os.fsync` de um
   descritor da pasta, depois da troca; Linux e macOS; no Windows nenhum `fsync` de pasta). `gravar_atomico(...) = confirmar(preparar(...))`.
   O módulo chama `os.replace`, `os.link` e `os.fsync` pelo módulo `os` na hora da chamada (o oráculo os troca com monkeypatch).
3. Falha = `FalhaGravacao(etapa, motivo, caminho, gravado)`, `motivo` em MOTIVOS (ENOSPC = "disco_cheio"; PermissionError fora da troca
   = "sem_permissao"; troca recusada até o fim = "arquivo_em_uso"; `conferir_ifc` recusou = "conferencia"; o resto, inclusive o EIO
   injetado, = "outro"); `gravado` verdadeiro só se a troca já aconteceu (falha em `fsync_pasta`); `str(e)` em português, com o nome do
   arquivo. Falha antes de `trocar`: `Casa.ifc.tmp` e `Casa.ifc.bak.tmp` apagados, destino e `.bak` antigos intactos. Falha em
   `trocar`: o `.tmp` FICA e `str(e)` cita o caminho dele (G2).
4. `conferir_ifc(caminho)`: recusa o IFC que não começa com `ISO-10303-21;` ou não termina com `END-ISO-10303-21;` (G5).
   `limpar_temporarios(destino)`: apaga `Casa.ifc.tmp` e `Casa.ifc.bak.tmp` que existirem e devolve os caminhos apagados (iterável).
Fora deste módulo (ADR-002 §4.5): o modo "sem carimbo" e o carimbo do pset `OBIM_Projeto` são do par (T07); nenhum caso aqui.
DESVIOS DA ESPECIFICAÇÃO (não afrouxam nada): nome do arquivo pedido pelo líder; caso 6(c) e 11 sem `skipif`, cada sistema com a
própria conferência (critério "0 pulos"); caso 9 compara as linhas de entidade depois de reabrir (a régua `s05_conteudo_aux.py` é do
T04 e ainda não existe) e tem uma parte (a) só em Python. GUARDA: sem ifcopenshell (caso 9b) ou como root no Linux (caso 8), pula; com
`OBIM_S05_OBRIGATORIO=1` todo pulo vira falha. Os testes `test_regua_*` provam os utilitários do oráculo e valem já (sem `@AINDA_NAO`)."""
import errno
import getpass
import hashlib
import os
import stat
import subprocess
import sys
from contextlib import contextmanager, nullcontext
from pathlib import Path

import pytest
from obrigatorio import pular as _pular

RAIZ = Path(__file__).resolve().parent.parent
AINDA_NAO = pytest.mark.xfail(strict=True, raises=ImportError, reason="T06: openbim_app.gravacao_atomica ainda não existe")
ETAPAS = ("escrever", "fsync", "conferir", "bak", "trocar", "fsync_pasta")
MOTIVOS = {"sem_permissao", "disco_cheio", "arquivo_em_uso", "conferencia", "outro"}
WIN = sys.platform == "win32"
A, B, C = (f"versao {x}\n".encode() * 200 for x in "ABC")
IFC_OK = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"

def pular(msg):
    _pular(f"\n!!! S05-T06: {msg} (caso da gravação atômica NÃO FOI EXECUTADO) !!!\n", "OBIM_S05_OBRIGATORIO")

def ga():
    import openbim_app.gravacao_atomica as m  # primeira linha de cada caso @AINDA_NAO: hoje é ela que dá o xfail
    return m

sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
esc = lambda dados: lambda tmp: Path(tmp).write_bytes(dados)  # noqa: E731  (o `escrever` dos casos: grava estes bytes no temporário)

def mesmo(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))

def problemas(pasta, destino=None, bak=None, tmp=None, nome="Casa.ifc"):
    """Régua da pasta: bytes esperados de cada arquivo (None = não pode existir); devolve a lista do que não bate (vazia = certo)."""
    est = {p.name: p.read_bytes() for p in Path(pasta).iterdir() if p.is_file()}
    esp = {n: v for n, v in ((nome, destino), (nome + ".bak", bak), (nome + ".tmp", tmp)) if v is not None}
    erro = {n: "falta" if n not in est else "sobrando" if n not in esp else "conteúdo errado" if est[n] != esp[n] else ""
            for n in set(est) | set(esp)}
    return sorted(f"{n}: {e} ({len(est.get(n, b''))} B)" for n, e in erro.items() if e)

def confere_falha(e, etapa, motivo, gravado=False):
    assert (e.etapa, e.motivo, e.gravado) == (etapa, motivo, gravado) and e.motivo in MOTIVOS, (e.etapa, e.motivo, e.gravado)
    assert "Casa.ifc" in str(e), f"mensagem sem o nome do arquivo: {str(e)!r}"

class TrocaRecusada:
    """`os.replace` falso: recusa (PermissionError) as `n` primeiras trocas para `alvo`; as outras vão ao `os.replace` real."""
    def __init__(self, alvo, n):
        self.alvo, self.n, self.tentativas, self.real = alvo, n, 0, os.replace

    def __call__(self, src, dst, *a, **k):
        if mesmo(dst, self.alvo):
            self.tentativas += 1
            if self.tentativas <= self.n:
                raise PermissionError(errno.EACCES, "arquivo em uso (teste)", str(dst))
        return self.real(src, dst, *a, **k)

class Registro:
    """Anota, em ordem, cada `os.fsync` ("arq" ou "dir", por `os.fstat`) e cada `os.replace` cujo destino é `alvo` ("troca")."""
    def __init__(self, alvo, monkeypatch):
        self.alvo, self.eventos, fs, rp = alvo, [], os.fsync, os.replace

        def fsync(fd):
            self.eventos.append("dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "arq")
            return fs(fd)

        def replace(src, dst, *a, **k):
            r = rp(src, dst, *a, **k)
            self.eventos += ["troca"] if mesmo(dst, self.alvo) else []
            return r
        monkeypatch.setattr(os, "fsync", fsync)
        monkeypatch.setattr(os, "replace", replace)

def link_quebrado(*a, **k):
    raise OSError(errno.EPERM, "link recusado (teste)")

def fsync_pasta(pasta):
    fd = os.open(pasta, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def segurar(caminho, segundos):
    """Outro processo abre `caminho` para leitura e o segura por `segundos`; volta só depois de ele confirmar que abriu."""
    cod = "import sys,time\nf=open(sys.argv[1],'rb')\nprint('ok',flush=True)\ntime.sleep(float(sys.argv[2]))\n"
    p = subprocess.Popen([sys.executable, "-c", cod, str(caminho), str(segundos)], stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "ok"
    return p

@contextmanager
def somente_leitura(pasta):
    """Linux: chmod 0o555. Windows: icacls /deny <usuário>:(W) na pasta (programa do próprio Windows). Desfaz sempre no fim."""
    if not WIN and hasattr(os, "geteuid") and os.geteuid() == 0:
        pular("rodando como root: a permissão da pasta é ignorada")
    u = getpass.getuser()
    icacls = lambda *op: subprocess.run(["icacls", str(pasta), *op], check=True, capture_output=True)  # noqa: E731
    icacls("/deny", f"{u}:(W)") if WIN else os.chmod(pasta, 0o555)
    try:
        yield
    finally:
        icacls("/remove:d", u) if WIN else os.chmod(pasta, 0o755)

@pytest.fixture(autouse=True)
def _sem_injecao(monkeypatch):
    monkeypatch.delenv("OBIM_S05_FALHA_EM", raising=False)
    monkeypatch.delenv("OBIM_S05_MORRER_EM", raising=False)

@pytest.fixture
def casa(tmp_path):
    (tmp_path / "Casa.ifc").write_bytes(B), (tmp_path / "Casa.ifc.bak").write_bytes(A)  # estado depois de gravar A e depois B
    return tmp_path / "Casa.ifc"

# ---------- régua: os utilitários do oráculo pegam o que devem pegar (valem já) ----------
def test_regua_pasta_pega_cada_mutacao(tmp_path):
    certo = {"Casa.ifc": C, "Casa.ifc.bak": B}
    mutantes = {"gravou por cima e cortou": {"Casa.ifc": C[:100], "Casa.ifc.bak": B}, "temporário sobrando": {**certo, "Casa.ifc.tmp": C},
                "bak.tmp sobrando": {**certo, "Casa.ifc.bak.tmp": B}, "bak de duas gerações": {"Casa.ifc": C, "Casa.ifc.bak": A},
                "bak ausente": {"Casa.ifc": C}, "original renomeado": {"Casa.ifc.bak": B, "Casa.ifc.tmp": C},
                "destino antigo": {"Casa.ifc": B, "Casa.ifc.bak": B}}
    for nome, arquivos in [("certo", certo), *mutantes.items()]:
        for p in tmp_path.iterdir():
            p.unlink()
        for n, b in arquivos.items():
            (tmp_path / n).write_bytes(b)
        achado = problemas(tmp_path, destino=C, bak=B)
        assert (achado == []) == (nome == "certo"), f"{nome}: {achado}"

def test_regua_troca_recusada_e_link_quebrado(tmp_path, monkeypatch):
    alvo, outro = tmp_path / "Casa.ifc", tmp_path / "Casa.ifc.bak"
    falso = TrocaRecusada(alvo, 2)
    monkeypatch.setattr(os, "replace", falso)
    (tmp_path / "x").write_bytes(A), (tmp_path / "y").write_bytes(B)
    os.replace(tmp_path / "x", outro)  # outro destino: passa direto e não conta
    for _ in range(2):
        with pytest.raises(PermissionError):
            os.replace(tmp_path / "y", str(alvo))
    os.replace(tmp_path / "y", alvo)
    assert falso.tentativas == 3 and alvo.read_bytes() == B and outro.read_bytes() == A
    monkeypatch.setattr(os, "link", link_quebrado)
    with pytest.raises(OSError):
        os.link(alvo, tmp_path / "b")

def test_regua_registro_fsync_e_troca(tmp_path, monkeypatch):
    alvo = tmp_path / "Casa.ifc"
    r = Registro(alvo, monkeypatch)
    with open(tmp_path / "t", "wb") as f:
        f.write(A)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path / "t", alvo)
    if not WIN:
        fsync_pasta(tmp_path)
    assert r.eventos == ["arq", "troca"] + ([] if WIN else ["dir"])

def test_regua_outro_processo_segura_o_arquivo(tmp_path):
    alvo = tmp_path / "Casa.ifc"
    alvo.write_bytes(A)
    (tmp_path / "novo").write_bytes(B)
    p = segurar(alvo, 30)
    try:  # é isto que o caso 6(c) usa: no Windows a troca para um arquivo aberto por outro processo é recusada; no Linux passa
        with pytest.raises(PermissionError) if WIN else nullcontext():
            os.replace(tmp_path / "novo", alvo)
        assert alvo.read_bytes() == (A if WIN else B)
    finally:
        p.kill()
        p.wait()

def test_regua_somente_leitura(tmp_path):
    with somente_leitura(tmp_path):
        with pytest.raises(PermissionError):
            (tmp_path / "Casa.ifc.tmp").write_bytes(A)
    (tmp_path / "depois").write_bytes(A)  # a permissão voltou

# ---------- casos do T06 (especificação, casos 1 a 13) ----------
@AINDA_NAO
def test_01_caminho_feliz_sem_destino_antigo(tmp_path):
    m = ga()
    assert tuple(m.ETAPAS) == ETAPAS
    d = tmp_path / "Casa.ifc"
    g = m.gravar_atomico(d, esc(A))
    assert mesmo(g.caminho, d) and g.sha256 == sha(A) and g.tamanho == len(A) and g.bak is None
    assert problemas(tmp_path, destino=A) == []

@AINDA_NAO
@pytest.mark.parametrize("sem_link", [False, True], ids=["link", "caso07_sem_link"])
def test_02_bak_de_uma_geracao(tmp_path, monkeypatch, sem_link):
    m = ga()
    if sem_link:
        monkeypatch.setattr(os, "link", link_quebrado)
    d = tmp_path / "Casa.ifc"
    m.gravar_atomico(d, esc(A))
    for x in (B, C):
        g = m.gravar_atomico(d, esc(x))
        assert mesmo(g.bak, tmp_path / "Casa.ifc.bak") and g.sha256 == sha(x)
    assert problemas(tmp_path, destino=C, bak=B) == []

@AINDA_NAO
@pytest.mark.parametrize("etapa", ["escrever", "fsync", "conferir", "bak", "trocar"])
def test_03_falha_em_cada_etapa(casa, monkeypatch, etapa):
    m = ga()
    monkeypatch.setenv("OBIM_S05_FALHA_EM", etapa)
    with pytest.raises(m.FalhaGravacao) as ei:
        m.gravar_atomico(casa, esc(C))
    confere_falha(ei.value, etapa, "outro")
    if etapa == "trocar":  # G2/G3: o .bak já é o destino atual, o destino fica, o temporário fica e a mensagem diz onde
        assert problemas(casa.parent, destino=B, bak=B, tmp=C) == []
        assert "Casa.ifc.tmp" in str(ei.value)
    else:
        assert problemas(casa.parent, destino=B, bak=A) == []

@AINDA_NAO
def test_04_conferencia_recusa_ifc_cortado(casa):
    m = ga()
    with pytest.raises(m.FalhaGravacao) as ei:
        m.gravar_atomico(casa, esc(IFC_OK[:-20]), conferir=m.conferir_ifc)
    confere_falha(ei.value, "conferir", "conferencia")
    assert problemas(casa.parent, destino=B, bak=A) == []

@AINDA_NAO
def test_05_disco_cheio(casa):
    m = ga()
    def escrever(tmp):
        with open(tmp, "wb") as f:
            f.write(b"x" * 1_000_000)
        raise OSError(errno.ENOSPC, "No space left on device (teste)")
    with pytest.raises(m.FalhaGravacao) as ei:
        m.gravar_atomico(casa, escrever)
    confere_falha(ei.value, "escrever", "disco_cheio")
    assert problemas(casa.parent, destino=B, bak=A) == []

@AINDA_NAO
def test_06a_troca_recusada_tres_vezes_depois_passa(casa, monkeypatch):
    m = ga()
    falso = TrocaRecusada(casa, 3)
    monkeypatch.setattr(os, "replace", falso)
    m.gravar_atomico(casa, esc(C))
    assert falso.tentativas == 4
    assert problemas(casa.parent, destino=C, bak=B) == []

@AINDA_NAO
def test_06b_troca_sempre_recusada(casa, monkeypatch):
    m = ga()
    falso = TrocaRecusada(casa, 10**6)
    monkeypatch.setattr(os, "replace", falso)
    with pytest.raises(m.FalhaGravacao) as ei:
        m.gravar_atomico(casa, esc(C))
    confere_falha(ei.value, "trocar", "arquivo_em_uso")
    assert falso.tentativas == 6
    assert "Casa.ifc.tmp" in str(ei.value)
    assert problemas(casa.parent, destino=B, bak=B, tmp=C) == []

@AINDA_NAO
def test_06c_outro_processo_com_o_destino_aberto(casa):
    m = ga()
    p = segurar(casa, 30)
    try:  # Windows, sem soltar: recusada até o fim, como em 6(b); Linux: arquivo aberto não impede a troca
        with pytest.raises(m.FalhaGravacao) if WIN else nullcontext() as ei:
            m.gravar_atomico(casa, esc(C))
        WIN and confere_falha(ei.value, "trocar", "arquivo_em_uso")
        assert problemas(casa.parent, **(dict(destino=B, bak=B, tmp=C) if WIN else dict(destino=C, bak=B))) == []
    finally:
        p.kill()
        p.wait()
    (casa.parent / "Casa.ifc.tmp").unlink(missing_ok=True)
    p = segurar(casa, 0.2)  # solta em 0,2 s, dentro das 6 tentativas (cerca de 1,55 s)
    try:
        g = m.gravar_atomico(casa, esc(A))
    finally:
        p.wait()
    assert g.sha256 == sha(A) and casa.read_bytes() == A

@AINDA_NAO
def test_08_pasta_somente_leitura(casa):
    m = ga()
    with somente_leitura(casa.parent):
        with pytest.raises(m.FalhaGravacao) as ei:
            m.gravar_atomico(casa, esc(C))
    confere_falha(ei.value, "escrever", "sem_permissao")
    assert problemas(casa.parent, destino=B, bak=A) == []

@AINDA_NAO
def test_09a_caminho_com_acento_e_espaco(tmp_path):
    m = ga()
    pasta = tmp_path / "Residência Nova" / "João"
    pasta.mkdir(parents=True)
    m.gravar_atomico(pasta / "Casa.ifc", esc(A))
    g = m.gravar_atomico(pasta / "Casa.ifc", esc(IFC_OK), conferir=m.conferir_ifc)
    assert g.sha256 == sha(IFC_OK) and mesmo(g.bak, pasta / "Casa.ifc.bak")
    assert problemas(pasta, destino=IFC_OK, bak=A) == []

@AINDA_NAO
def test_09b_ifc_de_300_paredes_no_caminho_com_acento(tmp_path):
    m = ga()
    try:
        import ifcopenshell
        sys.path.insert(0, str(RAIZ / "scripts"))
        import gerar_modelo_grande
    except Exception as e:  # noqa: BLE001
        pular(f"sem ifcopenshell ou sem scripts/gerar_modelo_grande.py ({e!r})")
    base = tmp_path / "base.ifc"
    gerar_modelo_grande.gerar(str(base), paredes=300)
    ifc = ifcopenshell.open(str(base))
    d = tmp_path / "Residência Nova" / "João" / "Casa.ifc"
    d.parent.mkdir(parents=True)
    m.gravar_atomico(d, lambda tmp: ifc.write(str(tmp)), conferir=m.conferir_ifc)
    ifc.write(str(ref := tmp_path / "ref.ifc"))
    linhas = [sorted(str(e) for e in ifcopenshell.open(str(p))) for p in (d, ref)]
    assert len(linhas[0]) == len(list(ifc)) and linhas[0] == linhas[1], f"sha256 da base {sha(base.read_bytes())}"
    assert problemas(d.parent, destino=d.read_bytes()) == []

@AINDA_NAO
def test_10_temporario_sobrando_achado_na_abertura(casa):
    m = ga()
    tmp, btmp = casa.parent / "Casa.ifc.tmp", casa.parent / "Casa.ifc.bak.tmp"
    tmp.write_bytes(C[:50]), btmp.write_bytes(B[:50])
    apagados = {Path(p).resolve() for p in m.limpar_temporarios(casa)}
    assert apagados == {tmp.resolve(), btmp.resolve()}
    assert problemas(casa.parent, destino=B, bak=A) == []

@AINDA_NAO
def test_11_fsync_da_pasta_depois_da_troca(casa, monkeypatch):
    m = ga()
    r = Registro(casa, monkeypatch)
    m.gravar_atomico(casa, esc(C))
    ev = r.eventos
    assert "troca" in ev and "arq" in ev[:ev.index("troca")], f"G1: fsync do temporário antes da troca: {ev}"
    if WIN:
        assert "dir" not in ev, ev
    else:
        assert "dir" in ev[ev.index("troca") + 1:], f"Linux: fsync da pasta depois da troca: {ev}"
    monkeypatch.setenv("OBIM_S05_FALHA_EM", "fsync_pasta")
    with pytest.raises(m.FalhaGravacao) as ei:
        m.gravar_atomico(casa, esc(A))
    confere_falha(ei.value, "fsync_pasta", "outro", gravado=True)
    assert problemas(casa.parent, destino=A, bak=C) == []

@AINDA_NAO
def test_12_duas_chamadas(casa):
    m = ga()
    p = m.preparar(casa, esc(C))
    assert mesmo(p.destino, casa) and mesmo(p.temporario, casa.parent / "Casa.ifc.tmp") and (p.sha256, p.tamanho) == (sha(C), len(C))
    assert problemas(casa.parent, destino=B, bak=A, tmp=C) == []
    g = m.confirmar(p)
    assert g.sha256 == sha(C) and mesmo(g.bak, casa.parent / "Casa.ifc.bak")
    assert problemas(casa.parent, destino=C, bak=B) == []
    with pytest.raises(m.FalhaGravacao) as ei:
        m.preparar(casa, esc(IFC_OK[:-20]), conferir=m.conferir_ifc)
    confere_falha(ei.value, "conferir", "conferencia")
    assert problemas(casa.parent, destino=C, bak=B) == []

FILHO = """import sys
from pathlib import Path
from openbim_app import gravacao_atomica as g
g.gravar_atomico(sys.argv[1], lambda tmp: Path(tmp).write_bytes(sys.argv[2].encode()))
"""

@AINDA_NAO
@pytest.mark.parametrize("etapa", ETAPAS)
def test_13_morte_no_comeco_de_cada_etapa(casa, etapa):
    m = ga()
    env = {**os.environ, "OBIM_S05_MORRER_EM": etapa, "PYTHONPATH": os.pathsep.join([str(RAIZ / "app"), os.environ.get("PYTHONPATH", "")])}
    novo = "versao nova\n" * 50
    r = subprocess.run([sys.executable, "-c", FILHO, str(casa), novo], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 86, f"código {r.returncode}; stderr: {r.stderr[-2000:]}"
    esperado = novo.encode() if etapa == "fsync_pasta" else B
    assert casa.read_bytes() == esperado, f"morte em {etapa}: destino não é o {'novo' if etapa == 'fsync_pasta' else 'antigo'} inteiro"
    m.limpar_temporarios(casa)
    sobra = {p.name for p in casa.parent.iterdir()} - {"Casa.ifc", "Casa.ifc.bak"}
    assert sobra == set(), f"morte em {etapa}: sobrou {sobra}"

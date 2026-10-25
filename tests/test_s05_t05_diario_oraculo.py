# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes do diário de gravação, parte 1 (ADR-002 §4.2, §4.4 e §4.8).
Não editar este arquivo, `test_s05_t05_recuperar_oraculo.py` nem `tests/s05_*aux.py`; os `@AINDA_NAO`
(xfail estrito por falta do módulo) depois da implementação (só as linhas `AINDA_NAO = ...` e `@AINDA_NAO`).
CONTRATO (`app/openbim_app/diario.py`, sem Qt, sem obimcore, sem importar `gravacao_par`; nomes do ADR-002 §4.8; [P] = escolha do teste que o
ADR não fixa, provisória até confirmação):
1. `pasta_base()` (caminho; lê o ambiente na hora): `OBIM_PASTA_LOCAL` se definida; senão `%LOCALAPPDATA%\\OpenBIMStudio` no Windows e
   `$XDG_DATA_HOME/OpenBIMStudio` (ou `~/.local/share/OpenBIMStudio`) nos outros. `pasta_projeto(lado_id)` = `pasta_base()/projetos/<lado_id>`.
   O diário fica em `pasta_projeto(lado_id)/diario/diario.obimlog` (pastas criadas se faltarem).
2. `lado_id_de(arquivo, ifc_sha256)`: o `LadoId` do pset `OBIM_Projeto`; sem ele, `str(uuid5(...))` que só depende do sha256 [P: o namespace].
3. `codificar_ifc(ops)` -> lista que `json.dumps(..., allow_nan=False)` aceita; `decodificar_ifc(json.loads(json.dumps(x)))` -> operações que um
   `Transaction` do ifcopenshell aplica com `commit()` e desfaz com `rollback()` (`inverses` volta a dict de chave int). Valor que não vira JSON
   (bytes, NaN, infinito) -> `OperacaoNaoSerializavel`; dentro do `Historico` a transação é descartada e o erro sobe.
4. [P] `Diario.abrir(lado_id, ifc_caminho, obim_sha256=None)` (método de classe) -> `Diario`: cria o diário novo com o registro `base` (sha256 e
   tamanho lidos do `ifc_caminho` no disco). `d.anotar(tipo, ifc, lado)` é o `anotar` que o `Historico` chama (tipo em transacao, desfazer,
   refazer; `ifc` = saída de `codificar_ifc`; `lado` = lista de `(coleção, id, antigo, novo)`): volta só depois da linha escrita e `flush` feito.
   `d.sincronizar()`: `os.fsync` do diário; sozinho, até cerca de 2 s depois do primeiro registro não sincronizado; `d.fechar()` sincroniza,
   fecha o arquivo e para o temporizador (nenhuma thread fica). `os.fsync` é chamado pelo módulo `os` na hora (o teste o troca).
5. Formato (§4.4): linhas `<crc32 em 8 hex minúsculos> <JSON>\\n` (só `\\n`, também no Windows), crc = `zlib.crc32` dos bytes UTF-8 do JSON;
   campos `v` (1), `seq` (consecutivo), `tipo`, `hora` (ISO 8601 em UTC, com fuso explícito: `+00:00` ou `Z`); `base`: `ifc_sha256`, `ifc_tamanho`, `ifc_caminho`, `obim_sha256`,
   `lado_id`; os demais: `ifc` e `lado`, autossuficientes (desfazer e refazer levam as MESMAS operações do passo: `ifc` e `lado` iguais aos do
   registro da transação).
6. [P] `ler_diario(caminho)` -> `(registros, avisos)`: `registros` = lista dos dicts dos registros inteiros (base primeiro), `avisos` = lista de
   textos em pt-BR (vazia se nada a avisar). Última linha sem `\\n` ou com crc errado: ignorada, com aviso. Linha ruim no meio ou buraco no `seq`:
   para ali, com aviso. Sem base inteira: nenhum registro aplicável, com aviso.
7. [P] `recuperar(ifc_caminho, diario_caminho, lateral=None)` -> `(arquivo, lateral, avisos)`: abre o `ifc_caminho` e reaplica todos os registros
   inteiros (transacao e refazer = `commit`, desfazer = `rollback`, lateral na mesma direção, a partir de `lateral` [P: o lateral da base, do
   `Casa.obim`; None = `Lateral()` vazio]); `arquivo` sem transação aberta e com `history`/`future` vazios (o desfazer começa vazio, §4.7);
   `lateral` é um `openbim_app.lateral.Lateral`. Base de outro sha256: nada aplicado, aviso, `arquivo` = o `ifc_caminho` como está. NUNCA grava
   na pasta do `ifc_caminho` (P5): mesmos bytes, nenhum arquivo novo.
8. [P: nomes] Pontos de teste em `anotar`, lidos do ambiente na hora: `OBIM_S05_MORRER_EM` em `anotar_antes` (nada escrito), `anotar_meio`
   (parte da linha escrita com `flush`, pelo menos 1 byte e sem o `\\n`), `anotar_depois` (linha inteira com `flush`) chama `os._exit(86)`.
   `OBIM_S05_FALHA_EM` em `anotar_antes` ou `anotar_meio` levanta `OSError` nos mesmos pontos; o diário fica sem resto do registro que falhou
   e o próximo `anotar` segue com o `seq` seguinte ao último inteiro.
Ordem do fim da transação (§4.2): `codificar` com a transação do ifcopenshell aberta, antes do `end_transaction`; `anotar` depois dele.
Fora (outros módulos; nenhum caso aqui): `zerar`, `diario-descartado.obimlog`, `abrir` sobre diário que já existe, a pergunta "Recuperar o trabalho".
GUARDA: sem ifcopenshell, pula; com OBIM_S05_OBRIGATORIO=1 todo pulo vira falha. Semente 20261023 (`s05_t04_aux.SEMENTE`)."""
import datetime
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
import zlib
from pathlib import Path

import pytest
import s05_t05_aux as X
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401  (fixtures)
from s05_t05_aux import LADO, Sessao, caminho_diario, mod, sha

WIN = sys.platform == "win32"


@pytest.fixture(autouse=True)
def _sem_injecao(monkeypatch):
    monkeypatch.delenv("OBIM_S05_FALHA_EM", raising=False)
    monkeypatch.delenv("OBIM_S05_MORRER_EM", raising=False)


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.setenv("OBIM_PASTA_LOCAL", str(tmp_path / "local"))
    return tmp_path / "local"


@pytest.fixture
def casa(base_ifc, tmp_path):
    return X.fazer_casa(base_ifc, tmp_path)


@pytest.fixture
def sessoes():
    feitas = []
    yield lambda *a, **k: feitas.append(Sessao(*a, **k)) or feitas[-1]
    for s in feitas:
        s.fechar()


def registros_crus(caminho):  # confere o formato linha a linha e devolve os dicts
    bruto = Path(caminho).read_bytes()
    assert bruto.endswith(b"\n") and b"\r" not in bruto, "linha sem \\n no fim ou com \\r (modo texto no Windows?)"
    out = []
    for n, linha in enumerate(bruto[:-1].split(b"\n")):
        m = re.fullmatch(rb"([0-9a-f]{8}) (.+)", linha, re.S)
        assert m, f"linha {n} fora do formato: {linha[:80]!r}"
        assert m[1].decode() == "%08x" % zlib.crc32(m[2]), f"linha {n}: crc32 não confere"
        out.append(json.loads(m[2].decode("utf-8")))
    return out


def test_1_registro_por_passo_formato_e_base(local, casa, sessoes):
    D = mod()
    s = sessoes(casa)
    kinds = ["transacao", "transacao", "desfazer", "refazer", "desfazer", "transacao"]
    for k in kinds:
        s.passo(k)
    cam = caminho_diario(local)
    regs = registros_crus(cam)
    assert [r["tipo"] for r in regs] == ["base"] + kinds, "cada transação, desfazer e refazer vira um registro, em ordem"
    assert [r["seq"] for r in regs] == list(range(regs[0]["seq"], regs[0]["seq"] + len(regs))) and all(r["v"] == 1 for r in regs)
    for r in regs:
        assert datetime.datetime.fromisoformat(r["hora"].replace("Z", "+00:00")).utcoffset() == datetime.timedelta(0), r["hora"]
    b = regs[0]
    assert (b["ifc_sha256"], b["ifc_tamanho"], b["obim_sha256"], b["lado_id"]) == (sha(casa), casa.stat().st_size, None, LADO)
    assert os.path.samefile(b["ifc_caminho"], casa)
    for r in regs[1:]:
        assert isinstance(r["ifc"], list) and r["ifc"] and isinstance(r["lado"], list), r["tipo"]
    for j in (3, 4, 5):  # desfazer, refazer e desfazer do passo 2: autossuficientes, as mesmas operações
        assert (regs[j]["ifc"], regs[j]["lado"]) == (regs[2]["ifc"], regs[2]["lado"]), f"registro {j} ({regs[j]['tipo']}) não é autossuficiente"
    assert D.ler_diario(str(cam)) == (regs, []), "ler_diario de um diário inteiro: todos os registros e nenhum aviso"


def test_1b_pastas_e_lado_id(tmp_path, monkeypatch, casa, base_ifc):
    D = mod()
    monkeypatch.setenv("OBIM_PASTA_LOCAL", str(tmp_path / "x"))
    assert Path(D.pasta_base()) == tmp_path / "x" and Path(D.pasta_projeto("abc")) == tmp_path / "x" / "projetos" / "abc"
    monkeypatch.delenv("OBIM_PASTA_LOCAL")
    if WIN:
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
        assert Path(D.pasta_base()) == tmp_path / "la" / "OpenBIMStudio"
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
        assert Path(D.pasta_base()) == tmp_path / "xdg" / "OpenBIMStudio"
        monkeypatch.delenv("XDG_DATA_HOME")
        monkeypatch.setenv("HOME", str(tmp_path / "h"))
        assert Path(D.pasta_base()) == tmp_path / "h" / ".local" / "share" / "OpenBIMStudio"
    f, _, _ = X.preparar(casa)
    assert D.lado_id_de(f, sha(casa)) == LADO
    g = X.R.ifcopenshell.open(base_ifc)  # sem o pset OBIM_Projeto
    v = D.lado_id_de(g, "a" * 64)
    assert uuid.UUID(v).version == 5 and v == D.lado_id_de(g, "a" * 64) != D.lado_id_de(g, "b" * 64)


def test_3_codificar_e_decodificar_cada_tipo(base_ifc):
    D = mod()
    from ifcopenshell.file import Transaction
    f, c, plano = X.A.montar(base_ifc)
    d = X.A.Cru(f, c)
    d.tx([plano.op("pset_criar"), plano.op("lado_criar")])
    for t in X.A.TIPOS:
        if t.startswith("lado"):
            continue
        antes = X.R.foto(f)
        d.tx([plano.op(t)])
        depois, ops = X.R.foto(f), f.history[-1].operations
        texto = json.dumps(D.codificar_ifc(ops), allow_nan=False)
        f.undo()
        X.igual(X.R.foto(f), antes, f"{t}: undo nativo")
        tr = Transaction(f)
        tr.operations = D.decodificar_ifc(json.loads(texto))
        tr.commit()
        X.igual(X.R.foto(f), depois, f"{t}: commit das operações decodificadas")
        tr.rollback()
        X.igual(X.R.foto(f), antes, f"{t}: rollback das operações decodificadas")
        f.redo()
        X.igual(X.R.foto(f), depois, f"{t}: redo nativo depois da ida e volta")


def test_3b_operacao_nao_serializavel_descarta(local, casa, sessoes):
    D = mod()
    for v in (b"\x00bytes", float("nan"), float("inf")):
        with pytest.raises(D.OperacaoNaoSerializavel):
            D.codificar_ifc([{"action": "edit", "id": 1, "index": 2, "old": None, "new": {"type": "IfcLabel", "value": v}}])
    s = sessoes(casa)
    s.passo("transacao")
    f0, n0 = s.foto(), len(X.linhas(caminho_diario(local)))
    with pytest.raises(D.OperacaoNaoSerializavel):
        with s.r.s.escrever() as esc, s.r.h.transacao(esc) as t:
            X.A.aplicar(s.plano.op("nome"), t.ifc, t.lado, s.r.c)
            w = t.ifc.by_type("IfcWall")[0]
            t.ifc.transaction.operations.append({"action": "edit", "id": w.id(), "index": 2, "old": w.Name, "new": b"x"})
    X.igual(s.foto(), f0, "operação não serializável: a transação não foi descartada")
    assert len(X.linhas(caminho_diario(local))) == n0 and s.r.h.pode_desfazer and not s.r.h.quebrado


def test_6_ordem_codificar_end_transaction_anotar(local, casa):
    D = mod()
    from ifcopenshell.file import Transaction
    f, c, plano = X.preparar(casa)
    d, ev = D.Diario.abrir(LADO, str(casa)), []
    cam = caminho_diario(local)
    n = lambda: Path(cam).read_bytes().count(b"\n")  # noqa: E731

    def cod(ops):
        ev.append(("codificar", isinstance(f.transaction, Transaction), len(f.history), n()))
        return D.codificar_ifc(ops)

    def an(*a):
        ev.append(("anotar", isinstance(f.transaction, Transaction), len(f.history), n()))
        d.anotar(*a)
        ev.append(("depois", None, len(f.history), n()))
    from test_s05_t04_transacao_oraculo import Real
    r = Real(f, c, codificar=cod, anotar=an)
    try:
        r.tx(plano.transacao(3))
        r.tx(plano.transacao(3))
        r.desfazer()
    finally:
        d.fechar()
        r.h.encerrar()
    assert ev[:3] == [("codificar", True, 0, 1), ("anotar", False, 1, 1), ("depois", None, 1, 2)], ev
    assert ev[3:6] == [("codificar", True, 1, 2), ("anotar", False, 2, 2), ("depois", None, 2, 3)], ev
    assert ev[-2:] == [("anotar", False, 1, 3), ("depois", None, 1, 4)], ev


def test_6b_fsync_temporizador_sincronizar_e_fechar(local, casa, monkeypatch):
    D = mod()
    ev, real, fios = [], os.fsync, set(threading.enumerate())

    def fsync(fd):
        ev.append(os.fstat(fd).st_ino)
        return real(fd)
    monkeypatch.setattr(os, "fsync", fsync)
    s = Sessao(casa)
    try:
        ino = os.stat(caminho_diario(local)).st_ino
        n0 = ev.count(ino)
        s.passo("transacao")
        fim = time.monotonic() + 8
        while ev.count(ino) == n0 and time.monotonic() < fim:
            time.sleep(0.05)
        assert ev.count(ino) > n0, "nenhum fsync do diário até 8 s depois do registro (P4: cerca de 2 s)"
        s.passo("transacao")
        n1 = ev.count(ino)
        s.d.sincronizar()
        assert ev.count(ino) > n1, "sincronizar() sem fsync do diário"
        s.passo("transacao")
        n2 = ev.count(ino)
    finally:
        s.fechar()
    assert ev.count(ino) > n2, "fechar() sem fsync do diário"
    fim = time.monotonic() + 1  # fechar() para o temporizador: nada de esperar os 2 s dele
    while set(threading.enumerate()) - fios and time.monotonic() < fim:
        time.sleep(0.05)
    assert not set(threading.enumerate()) - fios, f"thread do diário viva depois de fechar(): {set(threading.enumerate()) - fios}"


def test_7_sem_ligacao_ao_par():
    D = mod()
    import openbim_app.transacao as T
    for m in (D, T):
        assert "gravacao_par" not in Path(m.__file__).read_text(encoding="utf-8"), m.__file__
    assert all(callable(getattr(D, n)) for n in ("pasta_base", "pasta_projeto", "lado_id_de", "ler_diario", "recuperar"))
    cod = ("import sys, openbim_app.diario; print(sorted(m for m in sys.modules if m.split('.')[0] in ('PySide6', 'obimcore') or m in "
           "('openbim_app.gravacao_par', 'openbim_app.autosave')))")
    r = subprocess.run([sys.executable, "-c", cod], env={**os.environ, "PYTHONPATH": str(X.RAIZ / "app")}, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "[]", (r.stdout, r.stderr[-2000:])

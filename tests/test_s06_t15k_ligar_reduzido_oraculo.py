# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T15k: `auxiliar.preparar` usa o IFC reduzido (T15j) no lugar de `ifc.write`.
Ref: docs/state/cards/F0-S06/F0-S06-T15k-ligar-reduzido.md.
Contrato: anotação = pedido["vista"]["guid"] (planta e a op `caixas` passam a levar esse guid);
ids = pedido["elementos"]; qualquer falha/ausência cai no `ifc.write` completo, sem erro."""
from __future__ import annotations

import os
from pathlib import Path

import ifcopenshell
import pytest

import s06_t07_aux as X
from s06_t15i_aux import (ExecutorEspiao, _modelo_parede_movel, auxiliar, corte, local, planta, selecao)
from test_s06_t15j_reduzido_oraculo import _modelo, _norm

import openbim_app.desenho.reduzido as R

_REAL = R.escrever_reduzido


class EspiaoRed:
    """Substitui escrever_reduzido (no módulo e, se importado por nome, no auxiliar); delega ao real ou levanta."""

    def __init__(self, monkeypatch, modo="real"):
        self.chamadas, self.modo = [], modo
        monkeypatch.setattr(R, "escrever_reduzido", self)
        monkeypatch.setattr(auxiliar, "escrever_reduzido", self, raising=False)

    def __call__(self, ifc, ids, anotacao_id, saida):
        self.chamadas.append((ifc, sorted(int(i) for i in ids), int(anotacao_id), str(saida)))
        if self.modo == "erro":
            raise RuntimeError("falha simulada do reduzido")
        if self.modo == "parcial":
            Path(saida).write_text("ISO-10303-21;\nlixo parcial", encoding="utf-8")
            raise OSError("disco cheio simulado")
        return _REAL(ifc, ids, anotacao_id, saida)


class ExecArquivo(ExecutorEspiao):
    """Executor que anota tamanho e pasta do arquivo do pedido no instante da chamada."""

    def __init__(self):
        super().__init__()
        self.tamanhos, self.pastas, self.n_ent = [], [], []

    def __call__(self, pedido):
        a = Path(pedido["arquivo"])
        self.tamanhos.append(a.stat().st_size)
        self.pastas.append(a.parent)
        self.n_ent.append(len(list(ifcopenshell.open(str(a)))))
        return super().__call__(pedido)


def _modelo_grande():
    """Modelo da T15j + 300 elementos num pavimento que a vista não seleciona (o completo fica bem maior)."""
    f, sel, gp, gc, _ex, pavs = _modelo("IFC4")
    lixo = [X.caixa(f, "IfcBuildingElementProxy", f"Lixo{i}", i, 9, 6, 0.2, 0.2, 0.2) for i in range(300)]
    X.conter(f, pavs[2], *lixo)
    return f, gp, gc


def _gerar(f, gid, tipo, executor):
    fn = planta.gerar_planta if tipo == "planta" else corte.gerar_corte
    r = fn(f, gid, executor=executor)
    assert r.n_paths > 0, "a vista de teste precisa desenhar algo"
    return r


def _pedido_corte(f, gid):
    e = [x for x in f.by_type("IfcWall")]
    return {"op": "desenho", "protocolo": 1, "elementos": [[x.id(), x.GlobalId] for x in e],
            "vista": {"tipo": "CORTE", "guid": gid, "escala": 1.0}}


# 1) desenho idêntico, reduzido x completo ------------------------------------------------------
@pytest.mark.parametrize("tipo", ["planta", "corte"])
def test_desenho_identico_reduzido_e_completo(tipo, monkeypatch):
    f, gp, gc = _modelo_grande()
    gid = gp if tipo == "planta" else gc
    esp = EspiaoRed(monkeypatch, "real")
    ex = ExecArquivo()
    r_red = _gerar(f, gid, tipo, ex)
    assert len(esp.chamadas) == 1, "preparar deve usar escrever_reduzido quando não há caminho_ifc"
    _ifc, ids, anot, _saida = esp.chamadas[0]
    assert anot == f.by_guid(gid).id(), "anotação do reduzido = a vista pedida"
    assert ids == sorted(r_red.selecao.ids)
    n_red = ex.n_ent[0]

    EspiaoRed(monkeypatch, "erro")
    ex2 = ExecArquivo()
    r_cheio = _gerar(f, gid, tipo, ex2)
    assert _norm(r_red.svg) == _norm(r_cheio.svg)
    assert r_red.n_paths == r_cheio.n_paths
    assert n_red < ex2.n_ent[0], "o modelo reduzido tem menos entidades que o completo"


# 2) menor e copia_s medido --------------------------------------------------------------------
def test_modelo_reduzido_menor_e_copia_s_medido(monkeypatch):
    f, gp, gc = _modelo_grande()
    EspiaoRed(monkeypatch, "real")
    ex = ExecArquivo()
    r = _gerar(f, gp, "planta", ex)
    EspiaoRed(monkeypatch, "erro")
    ex2 = ExecArquivo()
    _gerar(f, gp, "planta", ex2)
    assert ex.tamanhos[0] < ex2.tamanhos[0] * 0.5
    assert r.tempos["copia_s"] > 0.0 and ex2.pastas[0] != ex.pastas[0]
    with auxiliar.preparar(f, _pedido_corte(f, gc)) as p:
        assert p.copia_s > 0.0
        assert os.path.getsize(p.pedido["arquivo"]) > 0


# 3) falha do reduzido => fallback completo, sem erro ----------------------------------------
@pytest.mark.parametrize("modo", ["erro", "parcial"])
def test_falha_do_reduzido_cai_no_completo(modo, monkeypatch):
    f, gp, gc = _modelo_grande()
    esp = EspiaoRed(monkeypatch, modo)
    ex = ExecArquivo()
    r = _gerar(f, gc, "corte", ex)
    assert len(esp.chamadas) == 1 and ex.n_ent[0] > 300, "o reduzido foi tentado e o arquivo final é o completo"
    EspiaoRed(monkeypatch, "erro")
    r2 = _gerar(f, gc, "corte", ExecArquivo())
    assert _norm(r.svg) == _norm(r2.svg)


def test_arquivo_parcial_removido_e_modelo_valido(monkeypatch):
    f, _gp, gc = _modelo_grande()
    EspiaoRed(monkeypatch, "parcial")
    with auxiliar.preparar(f, _pedido_corte(f, gc)) as p:
        g = ifcopenshell.open(p.pedido["arquivo"])
        assert len(g.by_type("IfcWall")) == len(f.by_type("IfcWall"))
        assert len(list(g)) > 300
        pasta = p.pasta
    assert not pasta.exists()


# 4) pedido sem dados para o reduzido => fallback ---------------------------------------------
@pytest.mark.parametrize("mexe", ["sem_vista", "sem_guid", "guid_inexistente", "sem_elementos", "elementos_vazio"])
def test_pedido_incompleto_cai_no_completo(mexe, monkeypatch):
    f, _gp, gc = _modelo_grande()
    esp = EspiaoRed(monkeypatch, "real")
    ped = _pedido_corte(f, gc)
    if mexe == "sem_vista":
        del ped["vista"]
    elif mexe == "sem_guid":
        del ped["vista"]["guid"]
    elif mexe == "guid_inexistente":
        ped["vista"]["guid"] = "0000000000000000000000"
    elif mexe == "sem_elementos":
        del ped["elementos"]
    else:
        ped["elementos"] = []
    with auxiliar.preparar(f, ped) as p:
        assert Path(p.pedido["arquivo"]).is_file()
        assert len(list(ifcopenshell.open(p.pedido["arquivo"]))) == len(list(f))
        pasta = p.pasta
    assert esp.chamadas == []
    assert not pasta.exists()


# 5) caminho_ifc continua com prioridade ------------------------------------------------------
def test_caminho_ifc_tem_prioridade(monkeypatch, tmp_path):
    f, _gp, gc = _modelo_grande()
    arq = tmp_path / "ja_existe.ifc"
    f.write(str(arq))
    esp = EspiaoRed(monkeypatch, "real")
    with auxiliar.preparar(f, _pedido_corte(f, gc), caminho_ifc=arq) as p:
        assert p.copia_s == 0.0
        assert Path(p.pedido["arquivo"]) == arq.resolve()
    assert esp.chamadas == []
    r = corte.gerar_corte(f, gc, executor=local.executar, caminho_ifc=arq)
    assert r.n_paths > 0 and esp.chamadas == []


# 6) pasta temporária apagada (sucesso e falha) -----------------------------------------------
def test_pasta_apagada_ao_fechar_e_em_falha(monkeypatch):
    f, gp, _gc = _modelo_grande()
    EspiaoRed(monkeypatch, "real")
    ex = ExecArquivo()
    _gerar(f, gp, "planta", ex)
    assert not ex.pastas[0].exists()

    def explode(pedido):
        ex.pastas.append(Path(pedido["arquivo"]).parent)
        assert ex.pastas[-1].is_dir()
        raise RuntimeError("falha no executor")

    with pytest.raises(RuntimeError, match="falha no executor"):
        planta.gerar_planta(f, gp, executor=explode)
    assert not ex.pastas[-1].exists()


def test_pasta_nao_fica_se_tudo_falha(monkeypatch):
    f, _gp, gc = _modelo_grande()
    EspiaoRed(monkeypatch, "parcial")
    antes = set(Path(os.environ.get("TMPDIR", "/tmp")).glob("obim-desenho-*"))

    def write_falha(self, *a, **k):
        raise OSError("sem espaço")

    class Falso:
        def __getattr__(self, n):
            return getattr(f, n)
        write = write_falha

    with pytest.raises(OSError):
        auxiliar.preparar(Falso(), _pedido_corte(f, gc))
    depois = set(Path(os.environ.get("TMPDIR", "/tmp")).glob("obim-desenho-*"))
    assert depois - antes == set()


# 7) op `caixas` da seleção passa pelo reduzido ----------------------------------------------
def test_caixas_via_reduzido_iguais_ao_completo(monkeypatch):
    f1, gid1, *_ = _modelo_parede_movel("IFC4")
    esp = EspiaoRed(monkeypatch, "real")
    ex = ExecArquivo()
    sel1 = selecao.selecionar(f1, gid1, executor=ex)
    ped = [p for p in ex.chamadas if p.get("op") == "caixas"]
    assert ped and len(esp.chamadas) >= 1, "a op caixas deve passar pelo reduzido"
    assert esp.chamadas[0][2] == f1.by_guid(gid1).id(), "anotação = vista da seleção"

    f2, gid2, *_ = _modelo_parede_movel("IFC4")
    EspiaoRed(monkeypatch, "erro")
    sel2 = selecao.selecionar(f2, gid2, executor=local.executar)
    assert sel1.caixas_envolventes and set(sel1.caixas_envolventes) == set(sel2.caixas_envolventes)
    for i, cx in sel1.caixas_envolventes.items():
        assert cx == pytest.approx(sel2.caixas_envolventes[i], abs=1e-9)

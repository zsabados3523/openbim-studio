# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da tarefa F0-S06-T15e: atalho de arquivo no processo auxiliar (elimina ifc.write redundante).
Cartão: docs/state/cards/F0-S06/F0-S06-T15e-atalho-arquivo.md.

CONTRATO:
1. auxiliar.preparar(ifc, pedido: dict, *, caminho_ifc: str | Path | None = None) -> Preparado:
   - Se caminho_ifc for fornecido e o arquivo existir em disco:
     preparado.pedido["arquivo"] aponta para o caminho absoluto de caminho_ifc.
     preparado.copia_s == 0.0.
     ifc.write() NÃO é chamado.
   - Se caminho_ifc for None, mantém o comportamento original (ifc.write em pasta temporária).
   - Se caminho_ifc não existir em disco (ou for diretório), fallback para ifc.write em pasta temporária.
2. Em app/openbim_app/desenho/planta.py:
   - gerar_planta(..., caminho_ifc: str | Path | None = None) keyword-only.
   - Repassa caminho_ifc=caminho_ifc para auxiliar.preparar.
3. Em app/openbim_app/desenho/corte.py:
   - gerar_corte(..., caminho_ifc: str | Path | None = None) keyword-only.
   - Repassa caminho_ifc=caminho_ifc para auxiliar.preparar e para selecao.selecionar.
4. Em app/openbim_app/desenho/selecao.py:
   - selecionar(..., caminho_ifc: str | Path | None = None) keyword-only.
   - Repassa para auxiliar.preparar na rota de cálculo de caixas envolventes (CORTE).
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path
from typing import Any

import pytest
import s06_t07_aux as X
from s05_conteudo_aux import _limpa, exigir  # noqa: F401 (fixture autouse e guarda)

from openbim_app import vistas_ifc
from openbim_app.desenho import auxiliar, corte, planta, selecao


def _modelo_sintetico(schema: str = "IFC4") -> tuple[Any, str, str]:
    """Cria modelo com pavimento, parede, vista PLANTA e vista CORTE."""
    exigir()
    f, pavs = X.estrutura(schema)
    parede = X.caixa(f, "IfcWall", "parede", 0.5, -0.1, 0.0, 1.0, 0.2, 2.0)
    X.conter(f, pavs[0], parede)

    gid_p = vistas_ifc.criar_vista(
        f, "Planta_T15e", "PLANTA", escala="1:100", origem=(0.0, 0.0, 0.0), tamanho=(10.0, 10.0, 3.0)
    )
    X.conter(f, pavs[0], f.by_guid(gid_p))

    gid_c = vistas_ifc.criar_vista(
        f, "Corte_T15e", "CORTE", escala="1:100", origem=(-0.5, 0.0, -0.5), tamanho=(7.0, 4.5, 6.0)
    )
    eixo = f.by_guid(gid_c).ObjectPlacement.RelativePlacement
    eixo.Axis = f.create_entity("IfcDirection", DirectionRatios=(0.0, -1.0, 0.0))
    eixo.RefDirection = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    X.deslocar_bloco(f, gid_c, (0.0, 0.0, -6.0))

    return f, gid_p, gid_c


def test_assinaturas_aceitam_caminho_ifc():
    """Inspeciona assinaturas de auxiliar.preparar, planta.gerar_planta,
    corte.gerar_corte e selecao.selecionar:
    todas devem aceitar caminho_ifc: str | Path | None = None keyword-only.
    """
    alvos = [
        auxiliar.preparar,
        planta.gerar_planta,
        corte.gerar_corte,
        selecao.selecionar,
    ]
    for fn in alvos:
        sig = inspect.signature(fn)
        assert "caminho_ifc" in sig.parameters, (
            f"{fn.__module__}.{fn.__qualname__} deve declarar parâmetro 'caminho_ifc'"
        )
        param = sig.parameters["caminho_ifc"]
        assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
            f"{fn.__module__}.{fn.__qualname__}: 'caminho_ifc' deve ser keyword-only (*), obtido: {param.kind}"
        )
        assert param.default is None, (
            f"{fn.__module__}.{fn.__qualname__}: default de 'caminho_ifc' deve ser None, obtido: {param.default!r}"
        )
        anot = str(param.annotation)
        assert "str" in anot and "Path" in anot and "None" in anot, (
            f"{fn.__module__}.{fn.__qualname__}: anotação de tipo deve contemplar str | Path | None, obtido: {param.annotation}"
        )


def test_preparar_com_caminho_ifc_evita_write(tmp_path, monkeypatch):
    """Quando caminho_ifc é fornecido e existe em disco:
    - pedido['arquivo'] aponta para o caminho absoluto de caminho_ifc.
    - copia_s == 0.0.
    - ifc.write() NÃO é chamado.
    - p.fechar() NÃO remove o arquivo original.
    - Aceita Path, str e caminho relativo.
    """
    f, _, _ = _modelo_sintetico()
    caminho_real = tmp_path / "modelo_sintetico.ifc"
    f.write(str(caminho_real))
    assert caminho_real.is_file()

    chamadas_write: list[tuple[Any, ...]] = []

    def spy_write(*args: Any, **kwargs: Any) -> None:
        chamadas_write.append((args, kwargs))
        raise AssertionError("ifc.write() NÃO deve ser chamado quando caminho_ifc é fornecido e existe!")

    monkeypatch.setattr(f, "write", spy_write)

    # 1. Chamada passando Path absoluto
    with auxiliar.preparar(f, {"op": "ping"}, caminho_ifc=caminho_real) as p:
        assert p.copia_s == 0.0
        assert p.pedido["arquivo"] == str(caminho_real.resolve())
        assert p.pedido["op"] == "ping"
        assert p.pedido["protocolo"] == auxiliar.PROTOCOLO
        assert len(chamadas_write) == 0

    assert caminho_real.is_file()

    # 2. Chamada passando str absoluta
    with auxiliar.preparar(f, {"op": "ping"}, caminho_ifc=str(caminho_real)) as p2:
        assert p2.copia_s == 0.0
        assert p2.pedido["arquivo"] == str(caminho_real.resolve())
        assert len(chamadas_write) == 0

    assert caminho_real.is_file()

    # 3. Chamada passando caminho relativo: deve resolver para caminho absoluto
    caminho_rel = Path(os.path.relpath(caminho_real, Path.cwd()))
    with auxiliar.preparar(f, {"op": "ping"}, caminho_ifc=caminho_rel) as p3:
        assert p3.copia_s == 0.0
        assert p3.pedido["arquivo"] == str(caminho_real.resolve())
        assert Path(p3.pedido["arquivo"]).is_absolute()
        assert len(chamadas_write) == 0

    assert caminho_real.is_file()


def test_preparar_sem_caminho_ifc_chama_write():
    """Quando caminho_ifc é omitido ou None:
    - Serialização temporária é executada (comportamento original).
    - Arquivo temporário existe na pasta temporária criada e contém o IFC.
    - p.copia_s >= 0.0.
    - p.fechar() limpa a pasta temporária.
    """
    f, _, _ = _modelo_sintetico()

    # 1. Omitindo caminho_ifc
    with auxiliar.preparar(f, {"op": "ping"}) as p:
        assert p.copia_s >= 0.0
        caminho_temp = Path(p.pedido["arquivo"])
        assert caminho_temp.is_file()
        assert caminho_temp.parent == p.pasta
        assert caminho_temp.stat().st_size > 0
        conteudo = caminho_temp.read_text(encoding="utf-8", errors="replace")
        assert "ISO-10303-21" in conteudo

    assert not p.pasta.exists()

    # 2. Passando caminho_ifc=None explicitamente
    with auxiliar.preparar(f, {"op": "ping"}, caminho_ifc=None) as p2:
        assert p2.copia_s >= 0.0
        caminho_temp2 = Path(p2.pedido["arquivo"])
        assert caminho_temp2.is_file()
        assert caminho_temp2.parent == p2.pasta

    assert not p2.pasta.exists()


def test_preparar_com_caminho_inexistente_faz_fallback(tmp_path):
    """Quando caminho_ifc é informado mas não existe no disco (ou é pasta):
    preparar() faz fallback para criação de arquivo temporário via ifc.write.
    """
    f, _, _ = _modelo_sintetico()

    # 1. Arquivo não existente
    caminho_fantasma = tmp_path / "inexistente.ifc"
    assert not caminho_fantasma.exists()

    with auxiliar.preparar(f, {"op": "ping"}, caminho_ifc=caminho_fantasma) as p:
        caminho_usado = Path(p.pedido["arquivo"])
        assert caminho_usado.is_file()
        assert caminho_usado != caminho_fantasma.resolve()
        assert p.copia_s >= 0.0

    assert not p.pasta.exists()

    # 2. Caminho existente mas que é um diretório (não é arquivo)
    with auxiliar.preparar(f, {"op": "ping"}, caminho_ifc=tmp_path) as p_dir:
        caminho_dir = Path(p_dir.pedido["arquivo"])
        assert caminho_dir.is_file()
        assert caminho_dir != tmp_path.resolve()
        assert p_dir.copia_s >= 0.0

    assert not p_dir.pasta.exists()


def test_gerar_planta_com_caminho_ifc_executa_normalmente(tmp_path, monkeypatch):
    """gerar_planta com caminho_ifc:
    - Gera planta SVG válida sem erros.
    - n_paths > 0.
    - Repassa caminho_ifc para auxiliar.preparar evitando ifc.write.
    - tempos['copia_s'] == 0.0.
    - Preserva integridade do arquivo em disco.
    """
    f, gid_planta, _ = _modelo_sintetico()
    caminho_real = tmp_path / "modelo_planta.ifc"
    f.write(str(caminho_real))
    assert caminho_real.is_file()

    chamadas_write: list[tuple[Any, ...]] = []

    def spy_write(*args: Any, **kwargs: Any) -> None:
        chamadas_write.append((args, kwargs))
        raise AssertionError("ifc.write() NÃO deve ser chamado em gerar_planta com caminho_ifc!")

    monkeypatch.setattr(f, "write", spy_write)

    # 1. Com Path
    res = planta.gerar_planta(f, gid_planta, caminho_ifc=caminho_real)
    assert res.svg.startswith("<svg") and res.svg.strip().endswith("</svg>")
    assert res.n_paths > 0
    assert res.tempos.get("copia_s") == 0.0
    assert len(chamadas_write) == 0
    assert caminho_real.is_file()

    # 2. Com str
    res_str = planta.gerar_planta(f, gid_planta, caminho_ifc=str(caminho_real))
    assert res_str.svg.startswith("<svg") and res_str.svg.strip().endswith("</svg>")
    assert res_str.n_paths > 0
    assert res_str.tempos.get("copia_s") == 0.0
    assert len(chamadas_write) == 0
    assert caminho_real.is_file()

    # Retrocompatibilidade: chamada sem caminho_ifc funciona normalmente
    monkeypatch.undo()
    res_padrao = planta.gerar_planta(f, gid_planta)
    assert res_padrao.svg.startswith("<svg") and res_padrao.svg.strip().endswith("</svg>")
    assert res_padrao.n_paths > 0


def test_gerar_corte_com_caminho_ifc_executa_normalmente(tmp_path, monkeypatch):
    """gerar_corte com caminho_ifc:
    - Gera corte SVG válido sem erros.
    - n_paths > 0.
    - Repassa caminho_ifc para auxiliar.preparar e selecao.selecionar evitando ifc.write.
    - tempos['copia_s'] == 0.0.
    - Preserva integridade do arquivo em disco.
    """
    f, _, gid_corte = _modelo_sintetico()
    caminho_real = tmp_path / "modelo_corte.ifc"
    f.write(str(caminho_real))
    assert caminho_real.is_file()

    chamadas_write: list[tuple[Any, ...]] = []

    def spy_write(*args: Any, **kwargs: Any) -> None:
        chamadas_write.append((args, kwargs))
        raise AssertionError("ifc.write() NÃO deve ser chamado em gerar_corte com caminho_ifc!")

    monkeypatch.setattr(f, "write", spy_write)

    # 1. Com Path
    res = corte.gerar_corte(f, gid_corte, caminho_ifc=caminho_real)
    assert res.svg.startswith("<svg") and res.svg.strip().endswith("</svg>")
    assert res.n_paths > 0
    assert res.tempos.get("copia_s") == 0.0
    assert len(chamadas_write) == 0
    assert caminho_real.is_file()

    # 2. Com str
    res_str = corte.gerar_corte(f, gid_corte, caminho_ifc=str(caminho_real))
    assert res_str.svg.startswith("<svg") and res_str.svg.strip().endswith("</svg>")
    assert res_str.n_paths > 0
    assert res_str.tempos.get("copia_s") == 0.0
    assert len(chamadas_write) == 0
    assert caminho_real.is_file()

    # Retrocompatibilidade: chamada sem caminho_ifc funciona normalmente
    monkeypatch.undo()
    res_padrao = corte.gerar_corte(f, gid_corte)
    assert res_padrao.svg.startswith("<svg") and res_padrao.svg.strip().endswith("</svg>")
    assert res_padrao.n_paths > 0


def test_selecao_corte_com_caminho_ifc_evita_write(tmp_path, monkeypatch):
    """selecao.selecionar na rota CORTE (cálculo de caixas envolventes):
    - Repassa caminho_ifc para auxiliar.preparar evitando ifc.write.
    - Retorna Seleção válida contendo elementos esperados.
    - Preserva arquivo em disco.
    """
    f, gid_planta, gid_corte = _modelo_sintetico()
    caminho_real = tmp_path / "modelo_selecao.ifc"
    f.write(str(caminho_real))
    assert caminho_real.is_file()

    chamadas_write: list[tuple[Any, ...]] = []

    def spy_write(*args: Any, **kwargs: Any) -> None:
        chamadas_write.append((args, kwargs))
        raise AssertionError("ifc.write() NÃO deve ser chamado em selecao.selecionar com caminho_ifc!")

    monkeypatch.setattr(f, "write", spy_write)

    # 1. Rota CORTE (dispara auxiliar.preparar para caixas envolventes)
    sel = selecao.selecionar(f, gid_corte, caminho_ifc=caminho_real)
    assert len(sel.ids) > 0
    assert len(chamadas_write) == 0
    assert caminho_real.is_file()

    # 2. Rota PLANTA (não usa auxiliar, mas aceita caminho_ifc com sucesso)
    sel_planta = selecao.selecionar(f, gid_planta, caminho_ifc=caminho_real)
    assert len(sel_planta.ids) > 0
    assert len(chamadas_write) == 0

    # Retrocompatibilidade: chamada sem caminho_ifc continua funcionando
    monkeypatch.undo()
    sel_padrao = selecao.selecionar(f, gid_corte)
    assert sel_padrao.ids == sel.ids

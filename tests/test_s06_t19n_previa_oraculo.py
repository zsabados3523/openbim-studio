# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19n: prévia gravada pelo pai antes dos filhos (T3). Cartão: docs/state/cards/F0-S06/F0-S06-T19n-previa-do-pai.md. Não editar nesta tarefa.
CONTRATO (`desenho.processar` com `componentes: True` e `previa_arquivo: <caminho>`):
1. Antes do 1º `faixas.rodar_filho`, o arquivo existe e é um SVG (`<svg` ... `</svg>`) com a marca `data-obim-previa="1"` na raiz (T20d2: a prévia nova substitui a de silhueta) e um grupo por peça (atributo `ifc:guid`), com `<path d=...>` não vazio.
2. Nenhum pedido de filho contém `previa_arquivo`.
3. O resultado final é idêntico (svg, enviados, grupos) com e sem `previa_arquivo`.
4. Caminho que não pode ser gravado: resultado ok igual ao de sem a chave (melhor esforço).
5. Sem a chave, nenhum arquivo é criado.
"""
from __future__ import annotations

import copy
import re

import obim_geometria.desenho as D
from test_s06_t19h_componentes_oraculo import Espiao, _caixa, _cena

GRUPO = re.compile(r'<g\b[^>]*\bifc:guid="[^"]+"[^>]*>')
MARCA = re.compile(r'<svg\b[^>]*\bdata-obim-previa="1"')


def _ped(tmp_path):
    return _cena(tmp_path, [_caixa(0, 0, 0, 1, 1, 1), _caixa(3, 0, 0, 4, 1, 1), _caixa(6, 0, 0, 7, 1, 1)], corte=0.5)


def test_previa_existe_antes_do_primeiro_filho_e_cobre_as_pecas(monkeypatch, tmp_path):
    ped, ids = _ped(tmp_path)
    arq = tmp_path / "previa.svg"
    vistos = []
    esp = Espiao(monkeypatch)
    orig = esp._um

    def espia(q):
        vistos.append(arq.read_text(encoding="utf-8") if arq.exists() else None)
        return orig(q)

    esp._um = espia
    r = D.processar({**copy.deepcopy(ped), "componentes": True, "previa_arquivo": str(arq)})
    assert r["ok"] and len(esp.chamadas) == 3
    assert all(v is not None for v in vistos), "prévia ainda não existia quando um filho começou"
    svg = vistos[0]
    assert svg.lstrip().startswith("<") and "<svg" in svg and svg.rstrip().endswith("</svg>")
    guids = [g for _i, g in ped["elementos"]]
    for g in guids:
        m = re.search(r'<g\b[^>]*ifc:guid="%s"[^>]*>\s*<path\b[^>]*\bd="[^"]+"' % re.escape(g), svg)
        assert m, f"sem grupo na prévia para {g}"
    assert MARCA.search(svg) and len(GRUPO.findall(svg)) == 3


def test_filhos_nao_recebem_a_chave_e_resultado_e_igual(monkeypatch, tmp_path):
    ped, _ = _ped(tmp_path)
    esp = Espiao(monkeypatch)
    sem = D.processar({**copy.deepcopy(ped), "componentes": True})
    n_sem = len(esp.chamadas)
    com = D.processar({**copy.deepcopy(ped), "componentes": True, "previa_arquivo": str(tmp_path / "p.svg")})
    assert all("previa_arquivo" not in c for c in esp.chamadas)
    assert len(esp.chamadas) == 2 * n_sem
    for k in ("svg", "enviados", "grupos", "grupos_ids", "falhas_geometria"):
        assert com[k] == sem[k], k


def test_caminho_nao_gravavel_nao_derruba(monkeypatch, tmp_path):
    ped, _ = _ped(tmp_path)
    Espiao(monkeypatch)
    sem = D.processar({**copy.deepcopy(ped), "componentes": True})
    ruim = D.processar({**copy.deepcopy(ped), "componentes": True, "previa_arquivo": str(tmp_path / "nao" / "existe" / "p.svg")})
    assert ruim["ok"] and ruim["svg"] == sem["svg"]


def test_sem_a_chave_nao_cria_arquivo(monkeypatch, tmp_path):
    ped, _ = _ped(tmp_path)
    Espiao(monkeypatch)
    D.processar({**copy.deepcopy(ped), "componentes": True})
    assert not list(tmp_path.glob("*.svg"))

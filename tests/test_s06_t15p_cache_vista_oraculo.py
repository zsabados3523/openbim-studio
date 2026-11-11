# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T15p (cache do desenho por vista; `cards/F0-S06/F0-S06-T15p-cache-por-vista.md`). Não editar na implementação.
CONTRATO `app/openbim_app/desenho/cache.py` (sem Qt, sem rede, só biblioteca padrão + ifcopenshell; cache de planta e corte):
1. `VERSAO_MODULO` (str, entra na chave: mudar o valor invalida tudo).
2. `pasta_padrao() -> Path`: `$OBIM_CACHE_DIR` se definida; senão pasta do usuário (Linux `$XDG_CACHE_HOME` ou `~/.cache`, Windows `%LOCALAPPDATA%`) + `openbim-studio/desenho`. Não cria a pasta.
3. `class CacheDesenho(pasta=None, *, idade_max_s=30*86400)` (`pasta=None` usa `pasta_padrao()`; cria a pasta sob demanda, no `guardar`):
   - `chave(ifc, pedido) -> str` (hex): hash de `VERSAO_MODULO`, do `pedido` do auxiliar SEM `threads` (só paralelismo), e de uma assinatura de cada elemento de `pedido["elementos"]` (todos os atributos, recursivos:
     posicionamento, representação, tipo, vãos). Determinística; vista, parâmetro, elemento ou versão diferentes dão chaves diferentes.
   - `obter(chave) -> dict | None`: o dict guardado; arquivo ausente, ilegível, truncado ou de outra forma -> `None`, nunca levanta.
   - `guardar(chave, dados: dict) -> bool`: grava (JSON, escrita atômica); qualquer erro de E/S -> `False`, nunca levanta.
   - `limpar(idade_max_s=None) -> int`: apaga só arquivos de cache com mtime mais velho que `idade_max_s` (padrão: o do construtor); devolve quantos apagou; pasta ausente -> 0.
4. `planta.gerar_planta(..., cache: CacheDesenho | None = None)` e `corte.gerar_corte(..., cache=None)` (keyword-only, novo; `None` = comportamento antigo, sem tocar disco). Com cache: monta a seleção e o pedido como hoje, e só no lugar de
   `auxiliar.preparar/executar` consulta `cache.obter(chave)`; no acerto não chama o executor para `op == "desenho"`; na falha calcula e `cache.guardar(chave, r)` (r = resposta do auxiliar). Resultado igual com ou sem cache.
GUARDA: sem ifcopenshell, pula (falha com OBIM_S05_OBRIGATORIO=1)."""
import os
import time

import pytest
import s06_t07_aux as X
import s06_t07c_aux as C
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)
from s06_t15i_aux import ExecutorEspiao, corte, planta


def M():
    exigir()
    try:
        from openbim_app.desenho import cache
    except ImportError as e:
        pytest.fail(f"módulo openbim_app.desenho.cache inexistente: {e}")
    return cache


def modelo_planta():
    exigir()
    f, pavs = X.estrutura("IFC4")
    par = X.caixa(f, "IfcWall", "p1", 0.0, 0.0, 0.0, 2.0, 0.2, 2.0)
    par2 = X.caixa(f, "IfcWall", "p2", 4.0, 0.0, 0.0, 2.0, 0.2, 2.0)
    X.conter(f, pavs[0], par, par2)
    return f, X.vista(f, "PLANTA", pavs[0], nome="VA"), X.vista(f, "PLANTA", pavs[0], nome="VB"), par


def planta_c(f, gid, c, esp, **kw):
    return planta.gerar_planta(f, gid, cache=c, executor=esp, **kw)


@pytest.fixture
def pasta(tmp_path):
    return tmp_path / "cache"


def test_segundo_pedido_identico_nao_chama_o_motor(pasta):
    c, esp = M().CacheDesenho(pasta), ExecutorEspiao()
    f, ga, _gb, _ = modelo_planta()
    p1 = planta_c(f, ga, c, esp)
    assert len(esp.pedidos_desenho) == 1 and p1.n_paths > 0
    p2 = planta_c(f, ga, c, esp)
    assert len(esp.pedidos_desenho) == 1, "acerto de cache chamou o motor"
    assert (p2.svg, p2.n_paths, p2.caixas) == (p1.svg, p1.n_paths, p1.caixas)
    assert p2.selecao.ids == p1.selecao.ids


def test_cache_persiste_entre_instancias_e_threads_nao_entra_na_chave(pasta):
    cache, esp = M(), ExecutorEspiao()
    f, ga, _gb, _ = modelo_planta()
    p1 = planta_c(f, ga, cache.CacheDesenho(pasta), esp, threads=1)
    p2 = planta_c(f, ga, cache.CacheDesenho(pasta), esp, threads=2)
    assert len(esp.pedidos_desenho) == 1 and p2.svg == p1.svg


def test_sem_cache_continua_chamando_o_motor_e_nao_toca_disco(pasta):
    esp = ExecutorEspiao()
    f, ga, _gb, _ = modelo_planta()
    planta_c(f, ga, None, esp)
    planta_c(f, ga, None, esp)
    assert len(esp.pedidos_desenho) == 2 and not pasta.exists()


def test_mudar_elemento_recalcula(pasta):
    c, esp = M().CacheDesenho(pasta), ExecutorEspiao()
    f, ga, _gb, par = modelo_planta()
    p1 = planta_c(f, ga, c, esp)
    par.ObjectPlacement.RelativePlacement.Location.Coordinates = (0.5, 0.0, 0.0)
    p2 = planta_c(f, ga, c, esp)
    assert len(esp.pedidos_desenho) == 2, "elemento mudou e o cache serviu o desenho velho"
    assert p2.svg != p1.svg
    planta_c(f, ga, c, esp)
    assert len(esp.pedidos_desenho) == 2, "o desenho novo deveria ter sido guardado"


def test_mudar_geometria_do_elemento_recalcula(pasta):
    c, esp = M().CacheDesenho(pasta), ExecutorEspiao()
    f, ga, _gb, par = modelo_planta()
    planta_c(f, ga, c, esp)
    par.Representation.Representations[0].Items[0].SweptArea.XDim = 3.0
    planta_c(f, ga, c, esp)
    assert len(esp.pedidos_desenho) == 2


def test_mudar_parametro_da_vista_recalcula(pasta):
    c, esp = M().CacheDesenho(pasta), ExecutorEspiao()
    f, ga, _gb, _ = modelo_planta()
    planta_c(f, ga, c, esp)
    planta_c(f, ga, c, esp, moveis_como_caixa=True)
    assert len(esp.pedidos_desenho) == 2


def test_mudar_altura_de_corte_recalcula(pasta):
    c, esp = M().CacheDesenho(pasta), ExecutorEspiao()
    f, ga, _gb, _ = modelo_planta()
    planta_c(f, ga, c, esp)
    ps = C.A.api("pset.add_pset", f, product=f.by_guid(ga), name="OBIM_View")
    C.A.api("pset.edit_pset", f, pset=ps, properties={"CutHeight": 0.5})
    planta_c(f, ga, c, esp)
    assert len(esp.pedidos_desenho) == 2


def test_mudar_versao_do_modulo_recalcula(pasta, monkeypatch):
    cache, esp = M(), ExecutorEspiao()
    c = cache.CacheDesenho(pasta)
    f, ga, _gb, _ = modelo_planta()
    planta_c(f, ga, c, esp)
    monkeypatch.setattr(cache, "VERSAO_MODULO", "outra-versao")
    planta_c(f, ga, c, esp)
    assert len(esp.pedidos_desenho) == 2


def test_outra_vista_nao_colide(pasta):
    c, esp = M().CacheDesenho(pasta), ExecutorEspiao()
    f, ga, gb, _ = modelo_planta()
    planta_c(f, ga, c, esp)
    planta_c(f, gb, c, esp)
    assert len(esp.pedidos_desenho) == 2, "vista B recebeu o desenho da vista A"
    planta_c(f, ga, c, esp)
    planta_c(f, gb, c, esp)
    assert len(esp.pedidos_desenho) == 2
    ids = {c.chave(f, {"protocolo": 1, "elementos": [], "vista": {"guid": g}}) for g in (ga, gb)}
    assert len(ids) == 2


def test_corte_tambem_usa_o_cache(pasta):
    c, esp = M().CacheDesenho(pasta), ExecutorEspiao()
    f, _g = C.modelo("IFC4")
    gid = C.corte(f)
    c1 = corte.gerar_corte(f, gid, cache=c, executor=esp)
    n = len(esp.pedidos_desenho)
    assert n >= 1 and c1.n_paths > 0
    c2 = corte.gerar_corte(f, gid, cache=c, executor=esp)
    assert len(esp.pedidos_desenho) == n and c2.svg == c1.svg
    corte.gerar_corte(f, gid, cache=c, executor=esp, profundidade_corte=2.0)
    assert len(esp.pedidos_desenho) == n + 1


def _arquivos(pasta):
    return [p for p in pasta.rglob("*") if p.is_file()]


@pytest.mark.parametrize("lixo", [b"", b"\x00\xff nao e json", b'{"svg": "<svg', b"[1, 2]", b'{"outra": "forma"}'])
def test_arquivo_corrompido_cai_em_recalculo(pasta, lixo):
    c, esp = M().CacheDesenho(pasta), ExecutorEspiao()
    f, ga, _gb, _ = modelo_planta()
    p1 = planta_c(f, ga, c, esp)
    arqs = _arquivos(pasta)
    assert arqs, "nada foi gravado"
    for a in arqs:
        a.write_bytes(lixo)
    p2 = planta_c(f, ga, c, esp)
    assert len(esp.pedidos_desenho) == 2 and p2.svg == p1.svg
    planta_c(f, ga, c, esp)
    assert len(esp.pedidos_desenho) == 2, "o arquivo ruim deveria ter sido regravado"


def test_obter_inexistente_e_guardar_obter_ida_e_volta(pasta):
    c = M().CacheDesenho(pasta)
    assert c.obter("0" * 64) is None
    assert c.guardar("a" * 64, {"svg": "<svg/>", "n_paths": 0, "tempos": {"geo_s": 0.1}}) is True
    assert c.obter("a" * 64) == {"svg": "<svg/>", "n_paths": 0, "tempos": {"geo_s": 0.1}}


def test_falha_ao_gravar_nao_quebra_o_desenho(tmp_path):
    ocupada = tmp_path / "e_um_arquivo"
    ocupada.write_text("x")
    c, esp = M().CacheDesenho(ocupada / "sub"), ExecutorEspiao()
    assert c.guardar("b" * 64, {"svg": "<svg/>"}) is False
    f, ga, _gb, _ = modelo_planta()
    p = planta_c(f, ga, c, esp)
    assert p.n_paths > 0 and len(esp.pedidos_desenho) == 1
    planta_c(f, ga, c, esp)
    assert len(esp.pedidos_desenho) == 2, "sem gravação não há acerto: recalcula sem erro"


def test_limpeza_por_idade_remove_so_os_antigos(pasta):
    c = M().CacheDesenho(pasta)
    for k in ("a", "b", "c"):
        assert c.guardar(k * 64, {"svg": k})
    velho = time.time() - 40 * 86400
    for a in _arquivos(pasta):
        if a.stem.startswith(("a", "b")) or a.name.startswith(("a", "b")):
            os.utime(a, (velho, velho))
    assert c.limpar(idade_max_s=30 * 86400) == 2
    assert c.obter("a" * 64) is None and c.obter("b" * 64) is None
    assert c.obter("c" * 64) == {"svg": "c"}
    assert c.limpar(idade_max_s=30 * 86400) == 0


def test_limpeza_pasta_ausente_e_padrao_do_construtor(tmp_path):
    cache = M()
    assert cache.CacheDesenho(tmp_path / "nao_existe").limpar() == 0
    c = cache.CacheDesenho(tmp_path / "p", idade_max_s=10)
    c.guardar("d" * 64, {"svg": "d"})
    for a in _arquivos(tmp_path / "p"):
        os.utime(a, (time.time() - 60, time.time() - 60))
    assert c.limpar() == 1


def test_pasta_padrao_respeita_variavel_de_ambiente(tmp_path, monkeypatch):
    cache = M()
    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "meu"))
    assert cache.pasta_padrao() == tmp_path / "meu"
    assert cache.CacheDesenho().pasta == tmp_path / "meu"
    assert not (tmp_path / "meu").exists()

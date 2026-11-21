# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cache em disco (SQLite) de malhas tesseladas por forma e ocorrências por peça."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib, json, os, platform, sqlite3, sys, time
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.placement as _placement
import ifcopenshell.util.representation as _rep
import ifcopenshell.util.unit as _unit
import numpy as np

NOME_BANCO = "cache_geometria.sqlite"
VERSAO_FORMATO = "2"
VERSAO_MOTOR = "1"
VERSAO_IFCOPENSHELL = str(getattr(ifcopenshell, "__version__", "0"))

_SUFIXOS_SIDECAR = ("-journal", "-wal", "-shm")
_IGNORA_RAIZ = frozenset({"GlobalId", "OwnerHistory", "Name", "Description"})
_SQL_INS_FORMA = "INSERT OR REPLACE INTO formas (chave, dtype_v, vertices, triangulos, checksum, gravado_em) VALUES (?, ?, ?, ?, ?, ?)"
_SQL_INS_OC = (
    "INSERT OR REPLACE INTO ocorrencias "
    "(documento, global_id, chave_forma, matriz, caixa, pavimento, classe_ifc, checksum) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)
_SQL_SEL_OC = (
    "SELECT documento, global_id, chave_forma, matriz, caixa, pavimento, classe_ifc, checksum FROM ocorrencias"
)
_ESQUEMA_COLUNAS = {
    "meta": ("chave", "valor"),
    "formas": ("chave", "dtype_v", "vertices", "triangulos", "checksum", "gravado_em"),
    "ocorrencias": ("documento", "global_id", "chave_forma", "matriz", "caixa", "pavimento", "classe_ifc", "checksum"),
    "memo": ("documento", "id_step", "assinatura", "chave"),
}
_SCHEMA_SQL = (
    "CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);"
    "CREATE TABLE formas (chave TEXT PRIMARY KEY, dtype_v TEXT NOT NULL, vertices BLOB NOT NULL, "
    "triangulos BLOB NOT NULL, checksum BLOB NOT NULL, gravado_em REAL NOT NULL);"
    "CREATE TABLE ocorrencias (documento TEXT NOT NULL DEFAULT '', global_id TEXT NOT NULL, "
    "chave_forma TEXT NOT NULL, matriz BLOB NOT NULL, caixa BLOB NOT NULL, pavimento TEXT, "
    "classe_ifc TEXT NOT NULL, checksum BLOB NOT NULL, PRIMARY KEY (documento, global_id));"
    "CREATE TABLE memo (documento TEXT NOT NULL, id_step INTEGER NOT NULL, assinatura TEXT NOT NULL, "
    "chave TEXT NOT NULL, PRIMARY KEY (documento, id_step));"
    "CREATE INDEX idx_formas_gravado_em ON formas (gravado_em);"
    "CREATE INDEX idx_ocorrencias_pavimento ON ocorrencias (documento, pavimento, global_id);"
)


@dataclass
class Ocorrencia:
    global_id: str
    chave_forma: str
    matriz: np.ndarray
    caixa: np.ndarray
    pavimento: str | None
    classe_ifc: str


def cabecalho_atual(**mudancas) -> dict:
    """Devolve o cabeçalho esperado do cache; `mudancas` substitui valores existentes."""
    h = {
        "versao_formato": VERSAO_FORMATO,
        "versao_motor": VERSAO_MOTOR,
        "versao_ifcopenshell": VERSAO_IFCOPENSHELL,
        "tesselacao": {},
        "plataforma": f"{sys.platform}-{platform.machine() or 'desconhecida'}",
    }
    for k, v in mudancas.items():
        if k not in h:
            raise KeyError(f"chave desconhecida no cabeçalho: {k!r}")
        h[k] = v
    return h


def _norm_float(v: float) -> float:
    return 0.0 if v == 0.0 else float(v)


def _normalizar_json(obj):
    """Normaliza estruturas para JSON canônico: -0.0 == 0.0, dicts mistos e conjuntos."""
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, (float, np.floating)):
        return _norm_float(float(obj))
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (list, tuple)):
        return [_normalizar_json(x) for x in obj]
    if isinstance(obj, (set, frozenset)):
        itens = [_normalizar_json(x) for x in obj]
        itens.sort(key=_json_canonico)
        return {"$set": itens}
    if isinstance(obj, dict):
        if all(isinstance(k, str) for k in obj):
            return {k: _normalizar_json(v) for k, v in sorted(obj.items())}
        pares = [[_normalizar_json(k), _normalizar_json(v)] for k, v in obj.items()]
        pares.sort(key=lambda p: _json_canonico(p[0]))
        return {"$dict": pares}
    return str(obj)


def _json_canonico(obj) -> str:
    return json.dumps(_normalizar_json(obj), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def documento_de(caminho) -> str:
    """Devolve o hash SHA-256 (hex) do caminho resolvido e normalizado."""
    return hashlib.sha256(os.path.normcase(str(Path(caminho).resolve())).encode("utf-8")).hexdigest()


def _digest_forma(dtype_v: str, bv: bytes, bt: bytes) -> bytes:
    return hashlib.sha256(
        dtype_v.encode("ascii") + len(bv).to_bytes(8, "little") + bv + len(bt).to_bytes(8, "little") + bt
    ).digest()


def _digest_ocorrencia(
    documento: str, gid: str, chave: str, bm: bytes, bc: bytes, pav: str | None, classe: str
) -> bytes:
    return hashlib.sha256(_json_canonico([documento, gid, chave, pav, classe]).encode("utf-8") + bm + bc).digest()


def _preparar_forma(chave: str, vertices, triangulos) -> tuple[str, str, bytes, bytes, bytes]:
    if not isinstance(chave, str) or not chave:
        raise ValueError("chave de forma inválida")
    if not isinstance(vertices, np.ndarray) or not isinstance(triangulos, np.ndarray):
        raise ValueError("vertices e triangulos devem ser numpy.ndarray")
    if vertices.ndim != 2 or vertices.shape[1] != 3 or vertices.dtype not in (np.float32, np.float64):
        raise ValueError(f"vertices inválidos: shape={vertices.shape}, dtype={vertices.dtype}")
    if triangulos.ndim != 2 or triangulos.shape[1] != 3 or triangulos.dtype != np.int32:
        raise ValueError(f"triangulos inválidos: shape={triangulos.shape}, dtype={triangulos.dtype}")
    bv = np.ascontiguousarray(vertices).tobytes()
    bt = np.ascontiguousarray(triangulos).tobytes()
    dtype_v = vertices.dtype.name
    return chave, dtype_v, bv, bt, _digest_forma(dtype_v, bv, bt)


def _eh_array_real(arr: np.ndarray) -> bool:
    return bool(np.issubdtype(arr.dtype, np.floating) or np.issubdtype(arr.dtype, np.integer))


def _preparar_ocorrencia(oc: Ocorrencia, documento: str = "") -> tuple[str, str, str, bytes, bytes, str | None, str, bytes]:
    if not isinstance(oc, Ocorrencia):
        raise ValueError("ocorrência inválida")
    if not isinstance(documento, str):
        raise ValueError("documento inválido")
    if not isinstance(oc.global_id, str) or not oc.global_id or not isinstance(oc.chave_forma, str) or not oc.chave_forma:
        raise ValueError("identificador de ocorrência inválido")
    if not isinstance(oc.classe_ifc, str) or not oc.classe_ifc or (oc.pavimento is not None and not isinstance(oc.pavimento, str)):
        raise ValueError("metadados de ocorrência inválidos")
    m, c = np.asarray(oc.matriz), np.asarray(oc.caixa)
    if m.shape != (4, 4) or not _eh_array_real(m):
        raise ValueError(f"matriz inválida: {m.shape}, {m.dtype}")
    if c.shape != (2, 3) or not _eh_array_real(c):
        raise ValueError(f"caixa inválida: {c.shape}, {c.dtype}")
    bm = np.ascontiguousarray(m, dtype=np.float64).tobytes()
    bc = np.ascontiguousarray(c, dtype=np.float64).tobytes()
    ck = _digest_ocorrencia(documento, oc.global_id, oc.chave_forma, bm, bc, oc.pavimento, oc.classe_ifc)
    return documento, oc.global_id, oc.chave_forma, bm, bc, oc.pavimento, oc.classe_ifc, ck


def _decodificar_ocorrencia(row) -> Ocorrencia | None:
    try:
        doc, gid, chave, bm, bc, pav, classe, ck = row
        bm, bc, ck = bytes(bm), bytes(bc), bytes(ck)
        if len(bm) != 128 or len(bc) != 48 or ck != _digest_ocorrencia(doc, gid, chave, bm, bc, pav, classe):
            return None
        m = np.frombuffer(bm, dtype=np.float64).reshape((4, 4)).copy()
        c = np.frombuffer(bc, dtype=np.float64).reshape((2, 3)).copy()
        return Ocorrencia(gid, chave, m, c, pav, classe)
    except Exception:
        return None


def _apagar_banco(caminho: Path) -> None:
    for alvo in [caminho, *(Path(f"{caminho}{s}") for s in _SUFIXOS_SIDECAR)]:
        try:
            alvo.unlink(missing_ok=True)
        except OSError:
            pass


def _fechar_con(con: sqlite3.Connection | None) -> None:
    if con is not None:
        try:
            con.close()
        except sqlite3.Error:
            pass


def _conectar(caminho: Path | str) -> sqlite3.Connection:
    con = sqlite3.connect(str(caminho), timeout=5.0, isolation_level=None)
    try:
        con.execute("PRAGMA busy_timeout=5000")
    except BaseException:
        _fechar_con(con)
        raise
    return con


def _banco_integro(con: sqlite3.Connection, cabecalho_json: str) -> bool:
    if con.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
        return False
    tabelas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if not set(_ESQUEMA_COLUNAS).issubset(tabelas):
        return False
    for tabela, cols_esperadas in _ESQUEMA_COLUNAS.items():
        cols = tuple(r[1] for r in con.execute(f"PRAGMA table_info({tabela})").fetchall())
        if cols != cols_esperadas:
            return False
    row = con.execute("SELECT valor FROM meta WHERE chave='cabecalho'").fetchone()
    return row is not None and row[0] == cabecalho_json


class CacheGeometria:
    """Armazenamento SQLite de formas tesseladas e ocorrências de peças."""

    def __init__(self, caminho: Path, con: sqlite3.Connection, relogio=time.time, em_memoria: bool = False) -> None:
        self._caminho = Path(caminho)
        self._con = con
        self._relogio = relogio
        self._em_memoria = bool(em_memoria)

    @property
    def em_memoria(self) -> bool:
        return self._em_memoria

    def __enter__(self) -> CacheGeometria:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.fechar()

    def fechar(self) -> None:
        if self._con is not None:
            try:
                self._con.close()
            except sqlite3.Error:
                pass
            self._con = None

    @contextmanager
    def _tx(self):
        if self._con is None:
            raise sqlite3.OperationalError("cache fechado")
        self._con.execute("BEGIN IMMEDIATE")
        try:
            yield
            if self._con.in_transaction:
                self._con.execute("COMMIT")
        except BaseException:
            if self._con.in_transaction:
                try:
                    self._con.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            raise

    def gravar_forma(self, chave: str, vertices: np.ndarray, triangulos: np.ndarray) -> None:
        item = _preparar_forma(chave, vertices, triangulos)
        agora = float(self._relogio())
        with self._tx():
            self._con.execute(_SQL_INS_FORMA, (*item, agora))

    def apagar_forma(self, chave: str) -> bool:
        """Remove a linha `chave` da tabela `formas` em transação; devolve True se existia."""
        with self._tx():
            cur = self._con.execute("DELETE FROM formas WHERE chave = ?", (chave,))
            return (cur.rowcount or 0) > 0

    def ler_forma(self, chave: str) -> tuple[np.ndarray, np.ndarray] | None:
        if self._con is None:
            return None
        try:
            row = self._con.execute(
                "SELECT dtype_v, vertices, triangulos, checksum FROM formas WHERE chave = ?", (chave,)
            ).fetchone()
            if row is None or row[0] not in ("float32", "float64"):
                return None
            dtype_v, bv, bt, ck = row[0], bytes(row[1]), bytes(row[2]), bytes(row[3])
            dt_v = np.dtype(dtype_v)
            if len(bv) % (3 * dt_v.itemsize) != 0 or len(bt) % 12 != 0 or ck != _digest_forma(dtype_v, bv, bt):
                return None
            v = np.frombuffer(bv, dtype=dt_v).reshape((-1, 3)).copy()
            t = np.frombuffer(bt, dtype=np.int32).reshape((-1, 3)).copy()
            return v, t
        except Exception:
            return None

    def formas_presentes(self, chaves) -> set[str]:
        if self._con is None:
            return set()
        lista = list(dict.fromkeys(chaves))
        if not lista:
            return set()
        presentes: set[str] = set()
        try:
            for i in range(0, len(lista), 500):
                bloco = lista[i : i + 500]
                marcadores = ",".join("?" * len(bloco))
                rows = self._con.execute(f"SELECT chave FROM formas WHERE chave IN ({marcadores})", bloco).fetchall()
                presentes.update(r[0] for r in rows)
            return presentes
        except Exception:
            return set()

    def gravar_ocorrencia(self, oc: Ocorrencia, documento: str = "") -> None:
        item = _preparar_ocorrencia(oc, documento=documento)
        with self._tx():
            self._con.execute(_SQL_INS_OC, item)

    def ler_ocorrencia(self, global_id: str, documento: str = "") -> Ocorrencia | None:
        if self._con is None:
            return None
        try:
            row = self._con.execute(
                f"{_SQL_SEL_OC} WHERE documento = ? AND global_id = ?", (documento, global_id)
            ).fetchone()
            return _decodificar_ocorrencia(row) if row is not None else None
        except Exception:
            return None

    def ocorrencias_do_pavimento(self, pavimento: str | None, documento: str = "") -> list[Ocorrencia]:
        if self._con is None:
            return []
        try:
            filtro = "documento = ? AND pavimento IS NULL" if pavimento is None else "documento = ? AND pavimento = ?"
            params = (documento,) if pavimento is None else (documento, pavimento)
            rows = self._con.execute(f"{_SQL_SEL_OC} WHERE {filtro} ORDER BY global_id ASC", params).fetchall()
            return [oc for row in rows if (oc := _decodificar_ocorrencia(row)) is not None]
        except Exception:
            return []

    def ocorrencias_por_ids(self, global_ids, documento: str = "") -> dict[str, Ocorrencia]:
        if self._con is None:
            return {}
        lista = list(dict.fromkeys(global_ids))
        if not lista:
            return {}
        resultado: dict[str, Ocorrencia] = {}
        try:
            for i in range(0, len(lista), 500):
                bloco = lista[i : i + 500]
                marcadores = ",".join("?" * len(bloco))
                rows = self._con.execute(
                    f"{_SQL_SEL_OC} WHERE documento = ? AND global_id IN ({marcadores})",
                    (documento, *bloco),
                ).fetchall()
                for row in rows:
                    oc = _decodificar_ocorrencia(row)
                    if oc is not None:
                        resultado[oc.global_id] = oc
            return resultado
        except Exception:
            return {}

    def memo_ler(self, documento: str, assinatura: str) -> dict[int, str]:
        if self._con is None:
            return {}
        try:
            rows = self._con.execute(
                "SELECT id_step, chave FROM memo WHERE documento = ? AND assinatura = ?",
                (documento, assinatura),
            ).fetchall()
            return {int(r[0]): str(r[1]) for r in rows}
        except Exception:
            return {}

    def gravar_lote(
        self,
        formas: dict,
        ocorrencias: list[Ocorrencia],
        documento: str = "",
        memo: tuple[str, dict[int, str]] | None = None,
    ) -> None:
        if not isinstance(formas, dict):
            raise ValueError("formas deve ser um dicionário")
        if not isinstance(documento, str):
            raise ValueError("documento inválido")
        prep_formas = []
        for chave, par in formas.items():
            if not isinstance(par, (tuple, list)) or len(par) != 2:
                raise ValueError(f"par inválido para {chave!r}")
            prep_formas.append(_preparar_forma(chave, par[0], par[1]))
        prep_ocs = [_preparar_ocorrencia(oc, documento=documento) for oc in ocorrencias]
        itens_memo = None
        assinatura_memo = None
        if memo is not None:
            if not isinstance(memo, tuple) or len(memo) != 2 or not isinstance(memo[0], str) or not isinstance(memo[1], dict):
                raise ValueError("memo inválido")
            assinatura_memo = memo[0]
            itens_memo = [(documento, int(id_step), assinatura_memo, str(chave)) for id_step, chave in memo[1].items()]
        agora = float(self._relogio())
        with self._tx():
            if prep_formas:
                self._con.executemany(_SQL_INS_FORMA, [(*f, agora) for f in prep_formas])
            if prep_ocs:
                self._con.executemany(_SQL_INS_OC, prep_ocs)
            if memo is not None:
                self._con.execute(
                    "DELETE FROM memo WHERE documento = ? AND assinatura != ?",
                    (documento, assinatura_memo),
                )
                if itens_memo:
                    self._con.executemany(
                        "INSERT OR REPLACE INTO memo (documento, id_step, assinatura, chave) VALUES (?, ?, ?, ?)",
                        itens_memo,
                    )

    def tamanho_bytes(self) -> int:
        if self._con is None:
            return 0
        try:
            row = self._con.execute("SELECT COALESCE(SUM(LENGTH(vertices) + LENGTH(triangulos)), 0) FROM formas").fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def limpar(self, idade_max_s: float | None = None, teto_bytes: int | None = None) -> int:
        if idade_max_s is None and teto_bytes is None:
            return 0
        removidas = 0
        with self._tx():
            if idade_max_s is not None:
                cur = self._con.execute("DELETE FROM formas WHERE gravado_em < ?", (float(self._relogio()) - float(idade_max_s),))
                removidas += max(0, cur.rowcount or 0)
            if teto_bytes is not None:
                rows = self._con.execute(
                    "SELECT chave, LENGTH(vertices) + LENGTH(triangulos) FROM formas ORDER BY gravado_em ASC, rowid ASC"
                ).fetchall()
                total, alvo, apagar = sum(int(sz) for _, sz in rows), int(teto_bytes), []
                for chave, sz in rows:
                    if total <= alvo:
                        break
                    apagar.append((chave,))
                    total -= int(sz)
                if apagar:
                    self._con.executemany("DELETE FROM formas WHERE chave = ?", apagar)
                    removidas += len(apagar)
        return removidas


def _inicializar_banco(con: sqlite3.Connection, cab_json: str, limpar_antes: bool = False) -> None:
    if limpar_antes:
        objetos = con.execute(
            "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND type IN ('view', 'trigger', 'index', 'table')"
        ).fetchall()
        for tipo, nome in objetos:
            nome_esc = str(nome).replace('"', '""')
            con.execute(f'DROP {tipo.upper()} IF EXISTS "{nome_esc}"')
    con.executescript(_SCHEMA_SQL)
    con.execute("BEGIN IMMEDIATE")
    try:
        con.execute("INSERT INTO meta (chave, valor) VALUES ('cabecalho', ?)", (cab_json,))
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            try:
                con.execute("ROLLBACK")
            except sqlite3.Error:
                pass
        raise


def abrir_cache(pasta, cabecalho: dict | None = None, relogio=time.time) -> CacheGeometria:
    """Abre ou recria o banco SQLite de cache na `pasta`; se o arquivo não puder ser apagado/recriado, usa banco em memória."""
    raiz = Path(pasta)
    caminho = raiz / NOME_BANCO
    cab_json = _json_canonico(cabecalho_atual() if cabecalho is None else dict(cabecalho))
    try:
        raiz.mkdir(parents=True, exist_ok=True)
    except OSError:
        con = _conectar(":memory:")
        _inicializar_banco(con, cab_json)
        return CacheGeometria(caminho, con, relogio=relogio, em_memoria=True)

    if caminho.exists() and not caminho.is_dir():
        con = None
        try:
            con = _conectar(caminho)
            if _banco_integro(con, cab_json):
                return CacheGeometria(caminho, con, relogio=relogio)
        except Exception:
            pass
        _fechar_con(con)
        _apagar_banco(caminho)

    if not caminho.exists():
        con = None
        try:
            con = _conectar(caminho)
            _inicializar_banco(con, cab_json)
            return CacheGeometria(caminho, con, relogio=relogio)
        except Exception:
            _fechar_con(con)
    elif not caminho.is_dir():
        con = None
        try:
            con = _conectar(caminho)
            _inicializar_banco(con, cab_json, limpar_antes=True)
            return CacheGeometria(caminho, con, relogio=relogio)
        except Exception:
            _fechar_con(con)

    con = _conectar(":memory:")
    _inicializar_banco(con, cab_json)
    return CacheGeometria(caminho, con, relogio=relogio, em_memoria=True)


def _min_anc(a: int | None, b: int | None) -> int | None:
    if a is None:
        return b
    if b is None:
        return a
    return a if a < b else b


def _serializar_ifc(valor, memo: dict[int, object], pilha: dict[int, int]) -> tuple[object, int | None]:
    if valor is None or isinstance(valor, (bool, str, int)):
        return valor, None
    if isinstance(valor, (float, np.floating)):
        return _norm_float(float(valor)), None
    if isinstance(valor, np.integer):
        return int(valor), None
    if isinstance(valor, bytes):
        return ["$bytes", valor.hex()], None
    if isinstance(valor, (list, tuple)):
        itens = []
        anc = None
        for x in valor:
            sx, ax = _serializar_ifc(x, memo, pilha)
            itens.append(sx)
            anc = _min_anc(anc, ax)
        return itens, anc
    if isinstance(valor, (set, frozenset)):
        itens = []
        anc = None
        for x in valor:
            sx, ax = _serializar_ifc(x, memo, pilha)
            itens.append(sx)
            anc = _min_anc(anc, ax)
        itens.sort(key=_json_canonico)
        return ["$set", itens], anc
    if isinstance(valor, dict):
        pares = []
        anc = None
        for k, v in valor.items():
            sk, ak = _serializar_ifc(k, memo, pilha)
            sv, av = _serializar_ifc(v, memo, pilha)
            pares.append([sk, sv])
            anc = _min_anc(anc, _min_anc(ak, av))
        pares.sort(key=lambda p: _json_canonico(p[0]))
        return ["$dict", pares], anc
    if hasattr(valor, "is_a") and hasattr(valor, "id"):
        ident, tipo = int(valor.id()), valor.is_a()
        if ident == 0:
            sv, anc = _serializar_ifc(valor.wrappedValue, memo, pilha)
            return ["$tipo", tipo, sv], anc
        prof = len(pilha)
        if ident in pilha:
            return ["$ciclo", tipo, prof - pilha[ident]], pilha[ident]
        if ident in memo:
            return memo[ident], None
        pilha[ident] = prof
        eh_raiz, eh_prod = valor.is_a("IfcRoot"), valor.is_a("IfcProduct")
        attrs = []
        anc = None
        for i in range(len(valor)):
            nome = valor.attribute_name(i)
            if nome == "OwnerHistory" or (eh_raiz and nome in _IGNORA_RAIZ) or (eh_prod and nome == "ObjectPlacement"):
                continue
            sv, av = _serializar_ifc(valor[i], memo, pilha)
            attrs.append([nome, sv])
            anc = _min_anc(anc, av)
        pilha.pop(ident, None)
        res = ["$ent", tipo, hashlib.sha256(_json_canonico(attrs).encode("utf-8")).hexdigest()]
        if anc is None or anc >= prof:
            memo[ident] = res
            return res, None
        return res, anc
    return repr(valor), None


def _representacoes_corpo(el) -> list:
    if el is None or not hasattr(el, "is_a") or not (el.is_a("IfcProduct") or el.is_a("IfcTypeProduct")):
        return []
    todas = list(_rep.get_representations_iter(el))
    corpo = [r for r in todas if _rep.is_representation_of_context(r, "Model", "Body")]
    return corpo or [
        r for r in todas
        if _rep.is_representation_of_context(r, "Model") and getattr(r, "RepresentationIdentifier", None) == "Body"
    ] or todas


def _cadeia_placement(pl) -> list[tuple[int, np.ndarray]]:
    """Devolve [(id_entidade, matriz_local)] da raiz até `pl`, sem compor coordenadas mundiais."""
    cadeia = []
    vistos: set[int] = set()
    atual = pl
    while atual is not None:
        ident = int(atual.id()) if hasattr(atual, "id") else id(atual)
        if ident in vistos:
            break
        vistos.add(ident)
        if hasattr(atual, "RelativePlacement") and hasattr(atual, "PlacementRelTo"):
            mat = np.asarray(_placement.get_axis2placement(atual.RelativePlacement), dtype=np.float64)
            cadeia.append((ident, mat))
            atual = atual.PlacementRelTo
        else:
            cadeia.append((ident, np.asarray(_placement.get_local_placement(atual), dtype=np.float64)))
            break
    cadeia.reverse()
    return cadeia


def _compor_cadeia(cadeia: list[tuple[int, np.ndarray]]) -> np.ndarray:
    m = np.eye(4, dtype=np.float64)
    for _, mat in cadeia:
        m = m @ mat
    return m


def _matriz_relativa_abertura(elemento, abertura) -> np.ndarray:
    pl_pai = getattr(elemento, "ObjectPlacement", None)
    pl_ab = getattr(abertura, "ObjectPlacement", None)
    if pl_ab is not None and getattr(pl_ab, "PlacementRelTo", None) == pl_pai and hasattr(pl_ab, "RelativePlacement"):
        return np.asarray(_placement.get_axis2placement(pl_ab.RelativePlacement), dtype=np.float64)
    cadeia_pai = _cadeia_placement(pl_pai)
    cadeia_ab = _cadeia_placement(pl_ab)
    comum = 0
    for (id_p, _), (id_a, _) in zip(cadeia_pai, cadeia_ab):
        if id_p != id_a:
            break
        comum += 1
    m_pai = _compor_cadeia(cadeia_pai[comum:])
    m_ab = _compor_cadeia(cadeia_ab[comum:])
    try:
        return np.linalg.inv(m_pai) @ m_ab
    except np.linalg.LinAlgError:
        return m_ab


def chave_da_forma(elemento, tesselacao: dict | None = None) -> str:
    """Hash SHA-256 (64 hex) por conteúdo da peça, com aberturas relativas e versões."""
    ifc = getattr(elemento, "file", None)
    unidades = (
        [_norm_float(float(_unit.calculate_unit_scale(ifc, u))) for u in ("LENGTHUNIT", "PLANEANGLEUNIT")]
        if ifc is not None else [1.0, 1.0]
    )
    memo: dict[int, object] = {}
    reps = [_serializar_ifc(r, memo, {})[0] for r in _representacoes_corpo(elemento)]
    aberturas = []
    for rel in getattr(elemento, "HasOpenings", None) or ():
        ab = getattr(rel, "RelatedOpeningElement", None)
        if ab is not None:
            m_rel = [[_norm_float(round(float(x), 9)) for x in ln] for ln in _matriz_relativa_abertura(elemento, ab)]
            aberturas.append([m_rel, [_serializar_ifc(r, memo, {})[0] for r in _representacoes_corpo(ab)]])
    aberturas.sort(key=_json_canonico)
    carga = {
        "versao_motor": VERSAO_MOTOR,
        "versao_ifcopenshell": VERSAO_IFCOPENSHELL,
        "tesselacao": {} if tesselacao is None else tesselacao,
        "unidades": unidades,
        "representacoes": reps,
        "aberturas": aberturas,
    }
    return hashlib.sha256(_json_canonico(carga).encode("utf-8")).hexdigest()

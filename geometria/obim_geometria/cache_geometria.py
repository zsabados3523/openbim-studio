# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cache em disco (SQLite) de malhas tesseladas por forma e ocorrências por peça."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib, json, platform, sqlite3, sys, time
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.placement as _placement
import ifcopenshell.util.representation as _rep
import ifcopenshell.util.unit as _unit
import numpy as np

NOME_BANCO = "cache_geometria.sqlite"
VERSAO_FORMATO = "1"
VERSAO_MOTOR = "1"
VERSAO_IFCOPENSHELL = str(getattr(ifcopenshell, "__version__", "0"))

_SUFIXOS_SIDECAR = ("-journal", "-wal", "-shm")
_IGNORA_RAIZ = frozenset({"GlobalId", "OwnerHistory", "Name", "Description"})
_SQL_INS_FORMA = "INSERT OR REPLACE INTO formas (chave, dtype_v, vertices, triangulos, checksum, gravado_em) VALUES (?, ?, ?, ?, ?, ?)"
_SQL_INS_OC = "INSERT OR REPLACE INTO ocorrencias (global_id, chave_forma, matriz, caixa, pavimento, classe_ifc, checksum) VALUES (?, ?, ?, ?, ?, ?, ?)"
_SQL_SEL_OC = "SELECT global_id, chave_forma, matriz, caixa, pavimento, classe_ifc, checksum FROM ocorrencias"
_SCHEMA_SQL = (
    "CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);"
    "CREATE TABLE formas (chave TEXT PRIMARY KEY, dtype_v TEXT NOT NULL, vertices BLOB NOT NULL, "
    "triangulos BLOB NOT NULL, checksum BLOB NOT NULL, gravado_em REAL NOT NULL);"
    "CREATE TABLE ocorrencias (global_id TEXT PRIMARY KEY, chave_forma TEXT NOT NULL, matriz BLOB NOT NULL, "
    "caixa BLOB NOT NULL, pavimento TEXT, classe_ifc TEXT NOT NULL, checksum BLOB NOT NULL);"
    "CREATE INDEX idx_formas_gravado_em ON formas (gravado_em);"
    "CREATE INDEX idx_ocorrencias_pavimento ON ocorrencias (pavimento, global_id);"
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


def _json_canonico(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _digest_forma(dtype_v: str, bv: bytes, bt: bytes) -> bytes:
    return hashlib.sha256(
        dtype_v.encode("ascii") + len(bv).to_bytes(8, "little") + bv + len(bt).to_bytes(8, "little") + bt
    ).digest()


def _digest_ocorrencia(gid: str, chave: str, bm: bytes, bc: bytes, pav: str | None, classe: str) -> bytes:
    return hashlib.sha256(_json_canonico([gid, chave, pav, classe]).encode("utf-8") + bm + bc).digest()


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


def _preparar_ocorrencia(oc: Ocorrencia) -> tuple[str, str, bytes, bytes, str | None, str, bytes]:
    if not isinstance(oc, Ocorrencia):
        raise ValueError("ocorrência inválida")
    if not isinstance(oc.global_id, str) or not oc.global_id or not isinstance(oc.chave_forma, str) or not oc.chave_forma:
        raise ValueError("identificador de ocorrência inválido")
    if not isinstance(oc.classe_ifc, str) or not oc.classe_ifc or (oc.pavimento is not None and not isinstance(oc.pavimento, str)):
        raise ValueError("metadados de ocorrência inválidos")
    m, c = np.asarray(oc.matriz), np.asarray(oc.caixa)
    if m.shape != (4, 4) or not np.issubdtype(m.dtype, np.number):
        raise ValueError(f"matriz inválida: {m.shape}, {m.dtype}")
    if c.shape != (2, 3) or not np.issubdtype(c.dtype, np.number):
        raise ValueError(f"caixa inválida: {c.shape}, {c.dtype}")
    bm = np.ascontiguousarray(m, dtype=np.float64).tobytes()
    bc = np.ascontiguousarray(c, dtype=np.float64).tobytes()
    ck = _digest_ocorrencia(oc.global_id, oc.chave_forma, bm, bc, oc.pavimento, oc.classe_ifc)
    return oc.global_id, oc.chave_forma, bm, bc, oc.pavimento, oc.classe_ifc, ck


def _decodificar_ocorrencia(row) -> Ocorrencia | None:
    try:
        gid, chave, bm, bc, pav, classe, ck = row
        bm, bc, ck = bytes(bm), bytes(bc), bytes(ck)
        if len(bm) != 128 or len(bc) != 48 or ck != _digest_ocorrencia(gid, chave, bm, bc, pav, classe):
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


def _conectar(caminho: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(caminho), timeout=5.0, isolation_level=None)
    con.execute("PRAGMA busy_timeout=5000")
    return con


def _banco_integro(con: sqlite3.Connection, cabecalho_json: str) -> bool:
    if con.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
        return False
    tabelas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if not {"meta", "formas", "ocorrencias"}.issubset(tabelas):
        return False
    row = con.execute("SELECT valor FROM meta WHERE chave='cabecalho'").fetchone()
    return row is not None and row[0] == cabecalho_json


class CacheGeometria:
    """Armazenamento SQLite de formas tesseladas e ocorrências de peças."""

    def __init__(self, caminho: Path, con: sqlite3.Connection, relogio=time.time) -> None:
        self._caminho = Path(caminho)
        self._con = con
        self._relogio = relogio

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
        self._con.execute("BEGIN IMMEDIATE")
        try:
            yield
            self._con.execute("COMMIT")
        except BaseException:
            self._con.execute("ROLLBACK")
            raise

    def gravar_forma(self, chave: str, vertices: np.ndarray, triangulos: np.ndarray) -> None:
        item = _preparar_forma(chave, vertices, triangulos)
        agora = float(self._relogio())
        with self._tx():
            self._con.execute(_SQL_INS_FORMA, (*item, agora))

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

    def gravar_ocorrencia(self, oc: Ocorrencia) -> None:
        item = _preparar_ocorrencia(oc)
        with self._tx():
            self._con.execute(_SQL_INS_OC, item)

    def ler_ocorrencia(self, global_id: str) -> Ocorrencia | None:
        if self._con is None:
            return None
        try:
            row = self._con.execute(f"{_SQL_SEL_OC} WHERE global_id = ?", (global_id,)).fetchone()
            return _decodificar_ocorrencia(row) if row is not None else None
        except Exception:
            return None

    def ocorrencias_do_pavimento(self, pavimento: str | None) -> list[Ocorrencia]:
        if self._con is None:
            return []
        try:
            filtro = "pavimento IS NULL" if pavimento is None else "pavimento = ?"
            rows = self._con.execute(
                f"{_SQL_SEL_OC} WHERE {filtro} ORDER BY global_id ASC",
                () if pavimento is None else (pavimento,),
            ).fetchall()
            return [oc for row in rows if (oc := _decodificar_ocorrencia(row)) is not None]
        except Exception:
            return []

    def gravar_lote(self, formas: dict, ocorrencias: list[Ocorrencia]) -> None:
        if not isinstance(formas, dict):
            raise ValueError("formas deve ser um dicionário")
        prep_formas = []
        for chave, par in formas.items():
            if not isinstance(par, (tuple, list)) or len(par) != 2:
                raise ValueError(f"par inválido para {chave!r}")
            prep_formas.append(_preparar_forma(chave, par[0], par[1]))
        prep_ocs = [_preparar_ocorrencia(oc) for oc in ocorrencias]
        agora = float(self._relogio())
        with self._tx():
            if prep_formas:
                self._con.executemany(_SQL_INS_FORMA, [(*f, agora) for f in prep_formas])
            if prep_ocs:
                self._con.executemany(_SQL_INS_OC, prep_ocs)

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


def abrir_cache(pasta, cabecalho: dict | None = None, relogio=time.time) -> CacheGeometria:
    """Abre ou recria o banco SQLite de cache na `pasta`; nunca levanta por arquivo ruim."""
    raiz = Path(pasta)
    raiz.mkdir(parents=True, exist_ok=True)
    caminho = raiz / NOME_BANCO
    cab_json = _json_canonico(cabecalho_atual() if cabecalho is None else dict(cabecalho))
    con = None
    if caminho.exists():
        try:
            con = _conectar(caminho)
            if _banco_integro(con, cab_json):
                return CacheGeometria(caminho, con, relogio=relogio)
        except Exception:
            pass
        if con is not None:
            try:
                con.close()
            except sqlite3.Error:
                pass
        _apagar_banco(caminho)
    con = _conectar(caminho)
    con.executescript(_SCHEMA_SQL)
    con.execute("BEGIN IMMEDIATE")
    con.execute("INSERT INTO meta (chave, valor) VALUES ('cabecalho', ?)", (cab_json,))
    con.execute("COMMIT")
    return CacheGeometria(caminho, con, relogio=relogio)


def _norm_float(v: float) -> float:
    return 0.0 if v == 0.0 else float(v)


def _serializar_ifc(valor, memo: dict[int, object], pilha: dict[int, int]):
    if valor is None or isinstance(valor, (bool, str, int)):
        return valor
    if isinstance(valor, float):
        return _norm_float(valor)
    if isinstance(valor, bytes):
        return ["$bytes", valor.hex()]
    if isinstance(valor, (list, tuple)):
        return [_serializar_ifc(x, memo, pilha) for x in valor]
    if isinstance(valor, dict):
        return [[str(k), _serializar_ifc(v, memo, pilha)] for k, v in sorted(valor.items())]
    if hasattr(valor, "is_a") and hasattr(valor, "id"):
        ident, tipo = int(valor.id()), valor.is_a()
        if ident == 0:
            return ["$tipo", tipo, _serializar_ifc(valor.wrappedValue, memo, pilha)]
        if ident in pilha:
            return ["$ciclo", tipo, pilha[ident]]
        if ident in memo:
            return memo[ident]
        pilha[ident] = len(pilha)
        eh_raiz, eh_prod = valor.is_a("IfcRoot"), valor.is_a("IfcProduct")
        attrs = []
        for i in range(len(valor)):
            nome = valor.attribute_name(i)
            if nome == "OwnerHistory" or (eh_raiz and nome in _IGNORA_RAIZ) or (eh_prod and nome == "ObjectPlacement"):
                continue
            attrs.append([nome, _serializar_ifc(valor[i], memo, pilha)])
        pilha.pop(ident, None)
        res = ["$ent", tipo, hashlib.sha256(_json_canonico(attrs).encode("utf-8")).hexdigest()]
        if not pilha:
            memo[ident] = res
        return res
    return repr(valor)


def _representacoes_corpo(el) -> list:
    if getattr(el, "Representation", None) is None:
        return []
    todas = list(_rep.get_representations_iter(el))
    corpo = [r for r in todas if _rep.is_representation_of_context(r, "Model", "Body")]
    return corpo or [
        r for r in todas
        if _rep.is_representation_of_context(r, "Model") and getattr(r, "RepresentationIdentifier", None) == "Body"
    ] or todas


def _matriz_placement(el) -> np.ndarray:
    pl = getattr(el, "ObjectPlacement", None)
    return np.eye(4, dtype=np.float64) if pl is None else np.asarray(_placement.get_local_placement(pl), dtype=np.float64)


def chave_da_forma(elemento, tesselacao: dict | None = None) -> str:
    """Hash SHA-256 (64 hex) por conteúdo da peça, com aberturas relativas e versões."""
    ifc = getattr(elemento, "file", None)
    unidades = (
        [_norm_float(float(_unit.calculate_unit_scale(ifc, u))) for u in ("LENGTHUNIT", "PLANEANGLEUNIT")]
        if ifc is not None else [1.0, 1.0]
    )
    memo: dict[int, object] = {}
    reps = [_serializar_ifc(r, memo, {}) for r in _representacoes_corpo(elemento)]
    aberturas = []
    rels = getattr(elemento, "HasOpenings", None) or ()
    if rels:
        try:
            m_pai_inv = np.linalg.inv(_matriz_placement(elemento))
        except np.linalg.LinAlgError:
            m_pai_inv = np.eye(4, dtype=np.float64)
        for rel in rels:
            ab = getattr(rel, "RelatedOpeningElement", None)
            if ab is not None:
                m_rel = [[_norm_float(round(float(x), 9)) for x in ln] for ln in (m_pai_inv @ _matriz_placement(ab))]
                aberturas.append([m_rel, [_serializar_ifc(r, memo, {}) for r in _representacoes_corpo(ab)]])
        aberturas.sort(key=_json_canonico)
    carga = {
        "versao_motor": VERSAO_MOTOR, "versao_ifcopenshell": VERSAO_IFCOPENSHELL,
        "tesselacao": tesselacao, "unidades": unidades, "representacoes": reps, "aberturas": aberturas,
    }
    return hashlib.sha256(_json_canonico(carga).encode("utf-8")).hexdigest()

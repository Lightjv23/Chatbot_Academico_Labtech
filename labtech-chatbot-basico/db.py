"""Conexão com o MongoDB e criação dos índices do LabTech.

Configuração por variáveis de ambiente (ou arquivo .env):
  MONGODB_URI  endereço de conexão (padrão: mongodb://127.0.0.1:27017)
  MONGODB_DB   nome do banco (padrão: labtech)

Coleções:
  usuarios   -> email (único), apelido, senha_hash, criado_em, ...
  sessoes    -> token_hash (único), usuario_id, criado_em, expira_em (TTL)
  conversas  -> usuario_id, titulo, criado_em, atualizado_em
  mensagens  -> conversa_id, usuario_id, papel, conteudo, fontes, criado_em
"""
import os
import threading

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import PyMongoError

_client = None
_indices_prontos = False
_lock = threading.Lock()


def get_client() -> MongoClient:
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
        # tz_aware=True: datas lidas do banco voltam em UTC, com fuso explícito.
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True)
    return _client


def garantir_indices(banco) -> None:
    banco.usuarios.create_index([("email", ASCENDING)], unique=True)
    banco.sessoes.create_index([("token_hash", ASCENDING)], unique=True)
    # O MongoDB remove a sessão automaticamente depois de expira_em.
    banco.sessoes.create_index([("expira_em", ASCENDING)], expireAfterSeconds=0)
    banco.conversas.create_index([("usuario_id", ASCENDING), ("atualizado_em", DESCENDING)])
    banco.mensagens.create_index([("conversa_id", ASCENDING), ("criado_em", ASCENDING)])


def get_db():
    """Retorna o banco e cria os índices na primeira conexão bem-sucedida."""
    global _indices_prontos
    banco = get_client()[os.getenv("MONGODB_DB", "labtech")]
    if not _indices_prontos:
        with _lock:
            if not _indices_prontos:
                garantir_indices(banco)
                _indices_prontos = True
    return banco


def ping() -> bool:
    try:
        get_client().admin.command("ping")
        return True
    except PyMongoError:
        return False


def usar_cliente(cliente) -> None:
    """Troca o cliente (usado nos testes para injetar um MongoDB em memória)."""
    global _client, _indices_prontos
    _client = cliente
    _indices_prontos = False

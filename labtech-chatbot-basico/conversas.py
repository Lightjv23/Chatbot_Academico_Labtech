"""Histórico de conversas e mensagens (com timestamps em UTC) no MongoDB.

Toda consulta filtra pelo dono (usuario_id): um usuário nunca enxerga nem altera
conversas de outro, e um id de conversa alheio responde 404 como se não existisse.
"""
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException

import db
from auth import usuario_atual

LIMITE_CONVERSAS = 200
LIMITE_MENSAGENS = 1000
TITULO_MAX = 60

router = APIRouter(prefix="/conversas", tags=["conversas"])


def agora() -> datetime:
    return datetime.now(timezone.utc)


def iso(momento: datetime) -> str:
    """Datetime -> texto ISO 8601 em UTC com 'Z' (ex.: 2026-11-06T20:31:05.123000Z)."""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def titulo_da_pergunta(pergunta: str) -> str:
    texto = " ".join(pergunta.split())
    return texto if len(texto) <= TITULO_MAX else texto[:TITULO_MAX - 1].rstrip() + "…"


def _conversa_publica(conversa: dict) -> dict:
    return {"id": str(conversa["_id"]), "titulo": conversa["titulo"],
            "criado_em": iso(conversa["criado_em"]), "atualizado_em": iso(conversa["atualizado_em"])}


def _mensagem_publica(mensagem: dict) -> dict:
    return {"id": str(mensagem["_id"]), "papel": mensagem["papel"], "conteudo": mensagem["conteudo"],
            "fontes": mensagem.get("fontes", []), "criado_em": iso(mensagem["criado_em"])}


def obter_conversa(usuario: dict, conversa_id: str) -> dict:
    """Busca uma conversa do usuário; 404 se o id for inválido ou de outra pessoa."""
    nao_encontrada = HTTPException(status_code=404, detail="Conversa não encontrada.")
    try:
        oid = ObjectId(conversa_id)
    except (InvalidId, TypeError):
        raise nao_encontrada
    conversa = db.get_db().conversas.find_one({"_id": oid, "usuario_id": usuario["_id"]})
    if not conversa:
        raise nao_encontrada
    return conversa


def salvar_troca(usuario: dict, conversa: dict | None, pergunta: str, pergunta_em: datetime,
                 resposta: str, fontes: list, modelo: str) -> dict:
    """Grava pergunta + resposta; cria a conversa se ainda não existir."""
    banco = db.get_db()
    resposta_em = agora()
    if conversa is None:
        conversa = {"usuario_id": usuario["_id"], "titulo": titulo_da_pergunta(pergunta),
                    "criado_em": pergunta_em, "atualizado_em": resposta_em}
        conversa["_id"] = banco.conversas.insert_one(conversa).inserted_id
    else:
        banco.conversas.update_one({"_id": conversa["_id"]}, {"$set": {"atualizado_em": resposta_em}})
    banco.mensagens.insert_many([
        {"conversa_id": conversa["_id"], "usuario_id": usuario["_id"], "papel": "usuario",
         "conteudo": pergunta, "criado_em": pergunta_em},
        {"conversa_id": conversa["_id"], "usuario_id": usuario["_id"], "papel": "assistente",
         "conteudo": resposta, "fontes": fontes, "modelo": modelo, "criado_em": resposta_em},
    ])
    return {"conversa_id": str(conversa["_id"]), "titulo": conversa["titulo"],
            "pergunta_em": iso(pergunta_em), "resposta_em": iso(resposta_em)}


@router.get("")
def listar(usuario: dict = Depends(usuario_atual)):
    cursor = (db.get_db().conversas.find({"usuario_id": usuario["_id"]})
              .sort("atualizado_em", -1).limit(LIMITE_CONVERSAS))
    return {"conversas": [_conversa_publica(c) for c in cursor]}


@router.get("/{conversa_id}/mensagens")
def mensagens(conversa_id: str, usuario: dict = Depends(usuario_atual)):
    conversa = obter_conversa(usuario, conversa_id)
    cursor = (db.get_db().mensagens.find({"conversa_id": conversa["_id"]})
              .sort([("criado_em", 1), ("_id", 1)]).limit(LIMITE_MENSAGENS))
    return {"conversa": _conversa_publica(conversa), "mensagens": [_mensagem_publica(m) for m in cursor]}


@router.delete("/{conversa_id}")
def excluir(conversa_id: str, usuario: dict = Depends(usuario_atual)):
    conversa = obter_conversa(usuario, conversa_id)
    banco = db.get_db()
    banco.mensagens.delete_many({"conversa_id": conversa["_id"]})
    banco.conversas.delete_one({"_id": conversa["_id"]})
    return {"ok": True}

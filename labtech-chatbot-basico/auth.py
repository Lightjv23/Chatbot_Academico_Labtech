"""Autenticação por e-mail acadêmico (@cs.udf.edu.br) e senha.

- Senhas guardadas apenas como hash scrypt com salt individual.
- Sessões por token opaco: o token vai para o navegador, e só o hash SHA-256
  dele fica no MongoDB (um vazamento do banco não entrega sessões válidas).
- Bloqueio temporário da conta após várias senhas erradas seguidas.
"""
import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import db

# Local-part restrito (sem "@", espaços ou aspas) e domínio exato: impede
# truques como "a@b.com@cs.udf.edu.br" ou "aluno@cs.udf.edu.br.outro.com".
EMAIL_ACADEMICO = re.compile(r"[a-z0-9][a-z0-9._+-]{0,63}@cs\.udf\.edu\.br")
MENSAGEM_EMAIL = "Use seu e-mail acadêmico (@cs.udf.edu.br)."

SENHA_MIN, SENHA_MAX = 8, 128
SESSAO_DIAS = 7
MAX_FALHAS = 5
BLOQUEIO = timedelta(minutes=15)

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
SCRYPT_MAXMEM = 64 * 1024 * 1024

router = APIRouter(prefix="/auth", tags=["autenticação"])


# ---------------------------------------------------------------- utilidades
def agora() -> datetime:
    return datetime.now(timezone.utc)


def normalizar_email(email: str) -> str:
    return email.strip().lower()


def email_academico_valido(email: str) -> bool:
    return EMAIL_ACADEMICO.fullmatch(email) is not None


def apelido_do_email(email: str) -> str:
    """Apelido = primeiro nome presente no e-mail, sem números.

    joao.silva@cs.udf.edu.br   -> "Joao"
    maria_clara99@cs.udf...    -> "Maria"
    20231234567@cs.udf.edu.br  -> "Aluno" (e-mail só com números)
    """
    parte_local = email.split("@", 1)[0]
    for pedaco in re.split(r"[._+\-]+", parte_local):
        letras = re.sub(r"\d+", "", pedaco)
        if letras:
            return letras.capitalize()
    return "Aluno"


def gerar_hash_senha(senha: str) -> str:
    sal = os.urandom(16)
    h = hashlib.scrypt(senha.encode(), salt=sal, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                       dklen=32, maxmem=SCRYPT_MAXMEM)
    return "$".join(["scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P),
                     base64.b64encode(sal).decode(), base64.b64encode(h).decode()])


def conferir_senha(senha: str, armazenado: str) -> bool:
    try:
        algoritmo, n, r, p, sal, esperado = armazenado.split("$")
        if algoritmo != "scrypt":
            return False
        esperado_bytes = base64.b64decode(esperado)
        calculado = hashlib.scrypt(senha.encode(), salt=base64.b64decode(sal), n=int(n), r=int(r),
                                   p=int(p), dklen=len(esperado_bytes), maxmem=SCRYPT_MAXMEM)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculado, esperado_bytes)


# Hash de uma senha descartável: usado para gastar o mesmo tempo quando o e-mail
# não existe, evitando revelar quais e-mails têm conta pelo tempo de resposta.
_HASH_FALSO = gerar_hash_senha(secrets.token_urlsafe(8))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def usuario_publico(usuario: dict) -> dict:
    return {"id": str(usuario["_id"]), "email": usuario["email"], "apelido": usuario["apelido"]}


def criar_sessao(usuario_id) -> str:
    token = secrets.token_urlsafe(32)
    criada = agora()
    db.get_db().sessoes.insert_one({
        "token_hash": _hash_token(token),
        "usuario_id": usuario_id,
        "criado_em": criada,
        "expira_em": criada + timedelta(days=SESSAO_DIAS),
    })
    return token


def _token_do_cabecalho(authorization: str | None) -> str | None:
    if not authorization:
        return None
    esquema, _, token = authorization.partition(" ")
    token = token.strip()
    if esquema.lower() != "bearer" or not token:
        return None
    return token


def usuario_atual(authorization: str | None = Header(default=None)) -> dict:
    """Dependência que exige sessão válida e devolve o usuário (sem o hash da senha)."""
    nao_autenticado = HTTPException(status_code=401, detail="Sessão inválida ou expirada. Faça login novamente.",
                                    headers={"WWW-Authenticate": "Bearer"})
    token = _token_do_cabecalho(authorization)
    if not token:
        raise nao_autenticado
    banco = db.get_db()
    # O TTL do MongoDB roda a cada ~60 s; por isso a expiração também é conferida aqui.
    sessao = banco.sessoes.find_one({"token_hash": _hash_token(token), "expira_em": {"$gt": agora()}})
    if not sessao:
        raise nao_autenticado
    usuario = banco.usuarios.find_one({"_id": sessao["usuario_id"]}, {"senha_hash": 0})
    if not usuario:
        raise nao_autenticado
    return usuario


# ------------------------------------------------------------------- rotas
class Credenciais(BaseModel):
    email: str = Field(..., max_length=254)
    senha: str = Field(..., min_length=1, max_length=SENHA_MAX)


@router.post("/registro", status_code=201)
def registro(dados: Credenciais):
    email = normalizar_email(dados.email)
    if not email_academico_valido(email):
        raise HTTPException(status_code=422, detail=MENSAGEM_EMAIL)
    if len(dados.senha) < SENHA_MIN:
        raise HTTPException(status_code=422, detail=f"A senha deve ter pelo menos {SENHA_MIN} caracteres.")
    usuario = {"email": email, "apelido": apelido_do_email(email),
               "senha_hash": gerar_hash_senha(dados.senha), "criado_em": agora(),
               "falhas_login": 0}
    try:
        usuario["_id"] = db.get_db().usuarios.insert_one(usuario).inserted_id
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Já existe uma conta com este e-mail. Faça login.")
    return {"token": criar_sessao(usuario["_id"]), "usuario": usuario_publico(usuario)}


@router.post("/login")
def login(dados: Credenciais):
    email = normalizar_email(dados.email)
    invalido = HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    usuarios = db.get_db().usuarios
    usuario = usuarios.find_one({"email": email}) if email_academico_valido(email) else None
    if usuario is None:
        conferir_senha(dados.senha, _HASH_FALSO)
        raise invalido
    bloqueado_ate = usuario.get("bloqueado_ate")
    if bloqueado_ate and bloqueado_ate > agora():
        raise HTTPException(status_code=429, detail="Muitas tentativas incorretas. Tente novamente em alguns minutos.")
    if not conferir_senha(dados.senha, usuario["senha_hash"]):
        atualizado = usuarios.find_one_and_update({"_id": usuario["_id"]}, {"$inc": {"falhas_login": 1}},
                                                  return_document=ReturnDocument.AFTER)
        if atualizado and atualizado.get("falhas_login", 0) >= MAX_FALHAS:
            usuarios.update_one({"_id": usuario["_id"]},
                                {"$set": {"bloqueado_ate": agora() + BLOQUEIO, "falhas_login": 0}})
        raise invalido
    usuarios.update_one({"_id": usuario["_id"]}, {"$set": {"falhas_login": 0, "ultimo_login": agora()},
                                                  "$unset": {"bloqueado_ate": ""}})
    return {"token": criar_sessao(usuario["_id"]), "usuario": usuario_publico(usuario)}


@router.post("/logout")
def logout(authorization: str | None = Header(default=None), usuario: dict = Depends(usuario_atual)):
    db.get_db().sessoes.delete_one({"token_hash": _hash_token(_token_do_cabecalho(authorization))})
    return {"ok": True}


@router.get("/eu")
def eu(usuario: dict = Depends(usuario_atual)):
    return {"usuario": usuario_publico(usuario)}

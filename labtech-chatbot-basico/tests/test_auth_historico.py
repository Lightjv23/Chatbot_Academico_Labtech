"""Testes de login, apelido e histórico de conversas.

Usam um MongoDB em memória (mongomock) e não dependem da base de conhecimento
nem do Ollama. Rode a partir da pasta labtech-chatbot-basico:

    pip install -r requirements-dev.txt
    python -m unittest discover -s tests -t . -v
"""
import unittest
from datetime import timedelta
from unittest.mock import patch

import mongomock
from fastapi import HTTPException

import auth
import conversas
import db
import main

EMAIL = "joao.silva@cs.udf.edu.br"
SENHA = "senha-segura-1"
TRECHO = ({"texto": "A rematrícula deve ser feita dentro do prazo previsto no edital.",
           "documento": "Edital de Rematrícula", "pagina": 2},)
PERGUNTA = "qual o prazo da rematrícula"


def registrar(email=EMAIL, senha=SENHA):
    return auth.registro(auth.Credenciais(email=email, senha=senha))


def autenticar(token):
    return auth.usuario_atual(authorization=f"Bearer {token}")


def perguntar(usuario, pergunta=PERGUNTA, conversa_id=None):
    with patch.object(main, "carregar_trechos_cache", return_value=TRECHO), \
         patch.object(main, "gerar_resposta", return_value="Resposta de teste"):
        return main.buscar(main.PerguntaRequest(pergunta=pergunta, conversa_id=conversa_id), usuario=usuario)


class BancoEmMemoria(unittest.TestCase):
    def setUp(self):
        db.usar_cliente(mongomock.MongoClient(tz_aware=True))

    def status(self, funcao, *args, **kwargs):
        with self.assertRaises(HTTPException) as ctx:
            funcao(*args, **kwargs)
        return ctx.exception.status_code


class TestApelido(unittest.TestCase):
    def test_primeiro_nome_sem_numeros(self):
        self.assertEqual(auth.apelido_do_email("joao.silva@cs.udf.edu.br"), "Joao")
        self.assertEqual(auth.apelido_do_email("maria_clara99@cs.udf.edu.br"), "Maria")
        self.assertEqual(auth.apelido_do_email("ANA-LUIZA@cs.udf.edu.br"), "Ana")

    def test_email_so_com_numeros_vira_aluno(self):
        self.assertEqual(auth.apelido_do_email("20231234567@cs.udf.edu.br"), "Aluno")


class TestSenha(unittest.TestCase):
    def test_hash_com_sal_e_conferencia(self):
        h1, h2 = auth.gerar_hash_senha("abc12345"), auth.gerar_hash_senha("abc12345")
        self.assertNotEqual(h1, h2)
        self.assertNotIn("abc12345", h1)
        self.assertTrue(auth.conferir_senha("abc12345", h1))
        self.assertFalse(auth.conferir_senha("abc12346", h1))

    def test_hash_armazenado_invalido_nao_estoura(self):
        for lixo in ("", "texto", "md5$1$2$3$4$5", "scrypt$x$y$z$@@$@@"):
            self.assertFalse(auth.conferir_senha("qualquer", lixo))


class TestRegistroELogin(BancoEmMemoria):
    def test_registro_valido_devolve_token_e_apelido(self):
        r = registrar(" Joao.Silva@CS.UDF.EDU.BR ")
        self.assertEqual(r["usuario"]["email"], EMAIL)
        self.assertEqual(r["usuario"]["apelido"], "Joao")
        self.assertEqual(autenticar(r["token"])["email"], EMAIL)

    def test_dominio_diferente_e_rejeitado(self):
        for email in ("aluno@gmail.com", "aluno@udf.edu.br", "aluno@mail.cs.udf.edu.br",
                      "aluno@cs.udf.edu.br.evil.com", "a@b.com@cs.udf.edu.br", "@cs.udf.edu.br",
                      "aluno @cs.udf.edu.br", "aluno@cs.udf.edu.brx", "", "cs.udf.edu.br"):
            with self.subTest(email=email):
                self.assertEqual(self.status(registrar, email), 422)
        self.assertEqual(db.get_db().usuarios.count_documents({}), 0)

    def test_senha_curta_e_rejeitada(self):
        self.assertEqual(self.status(registrar, EMAIL, "1234567"), 422)

    def test_email_duplicado_mesmo_com_maiusculas(self):
        registrar()
        self.assertEqual(self.status(registrar, EMAIL.upper()), 409)

    def test_senha_e_token_nao_ficam_em_texto_puro(self):
        r = registrar()
        banco = db.get_db()
        usuario = banco.usuarios.find_one({"email": EMAIL})
        self.assertTrue(usuario["senha_hash"].startswith("scrypt$"))
        self.assertNotIn(SENHA, usuario["senha_hash"])
        sessao = banco.sessoes.find_one({})
        self.assertNotEqual(sessao["token_hash"], r["token"])
        self.assertNotIn(r["token"], str(sessao))

    def test_login_correto_e_incorreto(self):
        registrar()
        r = auth.login(auth.Credenciais(email=EMAIL.upper(), senha=SENHA))
        self.assertEqual(r["usuario"]["apelido"], "Joao")
        self.assertEqual(self.status(auth.login, auth.Credenciais(email=EMAIL, senha="errada-123")), 401)

    def test_login_nao_revela_se_o_email_existe(self):
        registrar()
        with self.assertRaises(HTTPException) as a:
            auth.login(auth.Credenciais(email=EMAIL, senha="errada-123"))
        with self.assertRaises(HTTPException) as b:
            auth.login(auth.Credenciais(email="outro@cs.udf.edu.br", senha="errada-123"))
        with self.assertRaises(HTTPException) as c:
            auth.login(auth.Credenciais(email="fora@gmail.com", senha="errada-123"))
        self.assertEqual({a.exception.status_code, b.exception.status_code, c.exception.status_code}, {401})
        self.assertEqual(a.exception.detail, b.exception.detail)
        self.assertEqual(a.exception.detail, c.exception.detail)

    def test_bloqueio_temporario_apos_senhas_erradas(self):
        registrar()
        for _ in range(auth.MAX_FALHAS):
            self.assertEqual(self.status(auth.login, auth.Credenciais(email=EMAIL, senha="errada-123")), 401)
        # Mesmo com a senha certa, a conta fica bloqueada por um tempo.
        self.assertEqual(self.status(auth.login, auth.Credenciais(email=EMAIL, senha=SENHA)), 429)
        # Passado o bloqueio, volta a entrar e o contador zera.
        db.get_db().usuarios.update_one({"email": EMAIL}, {"$set": {"bloqueado_ate": auth.agora() - timedelta(seconds=1)}})
        self.assertIn("token", auth.login(auth.Credenciais(email=EMAIL, senha=SENHA)))
        self.assertEqual(db.get_db().usuarios.find_one({"email": EMAIL})["falhas_login"], 0)


class TestSessao(BancoEmMemoria):
    def test_sem_token_ou_token_invalido(self):
        for cabecalho in (None, "", "Bearer", "Bearer   ", "Basic abc", "Bearer token-que-nao-existe"):
            with self.subTest(cabecalho=cabecalho):
                self.assertEqual(self.status(auth.usuario_atual, authorization=cabecalho), 401)

    def test_logout_invalida_o_token(self):
        token = registrar()["token"]
        auth.logout(authorization=f"Bearer {token}", usuario=autenticar(token))
        self.assertEqual(self.status(autenticar, token), 401)

    def test_sessao_expirada(self):
        token = registrar()["token"]
        db.get_db().sessoes.update_many({}, {"$set": {"expira_em": auth.agora() - timedelta(seconds=1)}})
        self.assertEqual(self.status(autenticar, token), 401)

    def test_usuario_da_sessao_nao_expoe_o_hash(self):
        self.assertNotIn("senha_hash", autenticar(registrar()["token"]))


class TestHistorico(BancoEmMemoria):
    def setUp(self):
        super().setUp()
        self.ana = autenticar(registrar("ana.souza@cs.udf.edu.br")["token"])
        self.bia = autenticar(registrar("bia.lima@cs.udf.edu.br")["token"])

    def test_primeira_pergunta_cria_conversa_com_timestamps(self):
        r = perguntar(self.ana)
        self.assertEqual(r["resposta"], "Resposta de teste")
        self.assertEqual(r["titulo"], PERGUNTA)
        self.assertTrue(r["fontes"])
        self.assertTrue(r["pergunta_em"].endswith("Z") and r["resposta_em"].endswith("Z"))
        self.assertLessEqual(r["pergunta_em"], r["resposta_em"])

        lista = conversas.listar(usuario=self.ana)["conversas"]
        self.assertEqual([c["id"] for c in lista], [r["conversa_id"]])
        msgs = conversas.mensagens(r["conversa_id"], usuario=self.ana)["mensagens"]
        self.assertEqual([m["papel"] for m in msgs], ["usuario", "assistente"])
        self.assertEqual(msgs[0]["conteudo"], PERGUNTA)
        self.assertEqual(msgs[1]["conteudo"], "Resposta de teste")
        self.assertEqual(msgs[1]["fontes"][0]["documento"], "Edital de Rematrícula")
        self.assertTrue(all(m["criado_em"].endswith("Z") for m in msgs))

    def test_continuar_conversa_mantem_ordem_e_atualiza_data(self):
        primeira = perguntar(self.ana)
        segunda = perguntar(self.ana, "e o prazo da rematrícula para veteranos", primeira["conversa_id"])
        self.assertEqual(segunda["conversa_id"], primeira["conversa_id"])
        self.assertEqual(len(conversas.listar(usuario=self.ana)["conversas"]), 1)
        dados = conversas.mensagens(primeira["conversa_id"], usuario=self.ana)
        self.assertEqual([m["papel"] for m in dados["mensagens"]], ["usuario", "assistente"] * 2)
        self.assertEqual(dados["conversa"]["titulo"], PERGUNTA)
        self.assertGreaterEqual(dados["conversa"]["atualizado_em"], dados["conversa"]["criado_em"])

    def test_lista_mais_recente_primeiro(self):
        antiga = perguntar(self.ana)
        nova = perguntar(self.ana, "como funciona a rematrícula")
        ids = [c["id"] for c in conversas.listar(usuario=self.ana)["conversas"]]
        self.assertEqual(ids, [nova["conversa_id"], antiga["conversa_id"]])
        perguntar(self.ana, "prazo da rematrícula de novo", antiga["conversa_id"])
        ids = [c["id"] for c in conversas.listar(usuario=self.ana)["conversas"]]
        self.assertEqual(ids[0], antiga["conversa_id"])

    def test_titulo_longo_e_truncado(self):
        titulo = conversas.titulo_da_pergunta("rematrícula " * 30)
        self.assertLessEqual(len(titulo), conversas.TITULO_MAX)
        self.assertTrue(titulo.endswith("…"))

    def test_usuario_nao_acessa_conversa_de_outro(self):
        r = perguntar(self.ana)
        cid = r["conversa_id"]
        self.assertEqual(conversas.listar(usuario=self.bia)["conversas"], [])
        self.assertEqual(self.status(conversas.mensagens, cid, usuario=self.bia), 404)
        self.assertEqual(self.status(conversas.excluir, cid, usuario=self.bia), 404)
        self.assertEqual(self.status(perguntar, self.bia, PERGUNTA, cid), 404)
        # Nada foi alterado na conversa da Ana.
        self.assertEqual(len(conversas.mensagens(cid, usuario=self.ana)["mensagens"]), 2)

    def test_id_de_conversa_invalido_ou_inexistente(self):
        for cid in ("abc", "123", "zzzzzzzzzzzzzzzzzzzzzzzz", "0" * 24):
            with self.subTest(cid=cid):
                self.assertEqual(self.status(conversas.mensagens, cid, usuario=self.ana), 404)

    def test_excluir_remove_conversa_e_mensagens(self):
        cid = perguntar(self.ana)["conversa_id"]
        conversas.excluir(cid, usuario=self.ana)
        self.assertEqual(conversas.listar(usuario=self.ana)["conversas"], [])
        self.assertEqual(db.get_db().mensagens.count_documents({}), 0)

    def test_falha_do_modelo_nao_deixa_pergunta_orfa(self):
        with patch.object(main, "carregar_trechos_cache", return_value=TRECHO), \
             patch.object(main, "gerar_resposta", side_effect=HTTPException(status_code=502, detail="Ollama fora do ar")):
            with self.assertRaises(HTTPException):
                main.buscar(main.PerguntaRequest(pergunta=PERGUNTA), usuario=self.ana)
        self.assertEqual(conversas.listar(usuario=self.ana)["conversas"], [])
        self.assertEqual(db.get_db().mensagens.count_documents({}), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

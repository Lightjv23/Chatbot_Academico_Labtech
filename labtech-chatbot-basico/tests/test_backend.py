import unittest
from unittest.mock import patch
import main

class BuscaInstitucionalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trechos = [dict(t) for t in main.carregar_trechos_cache()]

    def test_base_institucional_tem_trechos(self):
        self.assertGreater(len(self.trechos), 100)

    def test_pergunta_sobre_atividades_complementares_retorna_fontes(self):
        resultados = main.buscar_trechos("como envio atividades complementares pelo Duda", self.trechos)
        self.assertTrue(resultados)
        self.assertTrue(any("Atividades Complementares" in r["documento"] for r in resultados))
        self.assertTrue(all(r.get("pagina") is not None for r in resultados))

    def test_pergunta_sobre_rematricula_retorna_fontes(self):
        resultados = main.buscar_trechos("qual o prazo da rematrícula", self.trechos)
        self.assertTrue(resultados)
        self.assertTrue(any("Matr" in r["documento"] or "Contrato" in r["documento"] or "Aluno" in r["documento"] for r in resultados))

    def test_pergunta_geral_llm_nao_busca_conhecimento_geral(self):
        resultados = main.buscar_trechos("o que é LLM", self.trechos)
        self.assertEqual(resultados, [])
        self.assertFalse(main.pergunta_e_academica("o que é LLM"))
        self.assertIn("Sou especializado", main.gerar_resposta("o que é LLM", []))

    def test_pergunta_wifi_nao_retorna_fonte_aleatoria(self):
        self.assertEqual(main.buscar_trechos("qual a senha do wifi", self.trechos), [])

    def test_fontes_incluem_trecho_comprovatorio(self):
        resultados = main.buscar_trechos("como envio atividades complementares pelo Duda", self.trechos)
        self.assertTrue(resultados)
        fonte = {"documento": resultados[0]["documento"], "pagina": resultados[0]["pagina"], "trecho": main.trecho_comprovatorio(resultados[0]["texto"])}
        self.assertTrue(fonte["documento"])
        self.assertTrue(fonte["trecho"])
        self.assertLessEqual(len(fonte["trecho"]), 421)

    def test_endpoint_resposta_sem_evidencia_nao_chama_modelo(self):
        with patch.object(main, "gerar_resposta", return_value=main.MENSAGEM_FORA_ESCOPO) as mock_gerar:
            resposta = main.buscar(main.PerguntaRequest(pergunta="o que é LLM"))
        mock_gerar.assert_called_once()
        self.assertEqual(resposta["fontes"], [])
        self.assertIn("opções rápidas", resposta["resposta"])

if __name__ == "__main__":
    unittest.main(verbosity=2)

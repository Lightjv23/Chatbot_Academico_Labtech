# LabTech — Chatbot Acadêmico UDF

Versão local para demonstração e testes do projeto acadêmico LabTech. O chatbot usa exclusivamente a base institucional incluída nesta pasta, com FastAPI no backend, Ollama/Qwen2.5:3b para gerar respostas e HTML/CSS/JavaScript na interface.

## Início rápido (Windows 10/11)

### Requisitos externos
- Windows 10/11 e Python 3.11 ou 3.12 (64 bits). O inicializador procura automaticamente essas versões. Python 3.15 ainda não foi validado para este projeto; mantenha-o instalado e adicione o Python 3.12 em paralelo.
- Ollama instalado: https://ollama.com/
- Modelo local `qwen2.5:3b` (cerca de 2 GB, além do espaço para os programas).
- A primeira configuração precisa de internet para instalar dependências e baixar o modelo. Depois, o uso é local.

### Passos
1. Extraia o ZIP completo para uma pasta em que você tenha permissão de escrita.
2. Instale Python 3.12 (64 bits) e Ollama, caso ainda não estejam instalados. O Python 3.12 pode coexistir com outras versões. Download oficial: https://www.python.org/downloads/release/python-31210/.
3. Abra o Ollama e aguarde ele iniciar. Se necessário, abra o terminal e execute `ollama pull qwen2.5:3b`.
4. Dê dois cliques em `iniciar.bat`. Não é necessário executar como administrador. O arquivo procura Python 3.12 ou 3.11, cria o ambiente virtual e mostra mensagens específicas quando falta algum requisito.
5. Na primeira execução, o script cria `.venv`, instala as dependências e tenta baixar o modelo se ele ainda não estiver instalado.
6. A interface abre em `http://127.0.0.1:5500/index.html`. Mantenha a janela do backend aberta enquanto usa o chatbot.

Se o Windows perguntar sobre acesso à rede, o serviço foi projetado para funcionar em `127.0.0.1` (somente neste computador); não é necessário publicá-lo na internet.

## Inicialização manual
Abra o Prompt de Comando (CMD) na pasta do projeto e execute:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
ollama pull qwen2.5:3b
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Mantenha esse terminal aberto. Em um segundo terminal, na mesma pasta, execute:

```bat
.venv\Scripts\python.exe -m http.server 5500
```

Abra `http://127.0.0.1:5500/index.html` no navegador.

## Verificação do sistema
- Estado da base/modelo: http://127.0.0.1:8000/saude
- Documentação interativa da API: http://127.0.0.1:8000/docs
- Endpoint do chat: `POST http://127.0.0.1:8000/buscar` com JSON `{"pergunta":"Como faço a rematrícula?"}`.

A rota `/saude` informa se a base foi carregada, quantos trechos ela contém e se Ollama/modelo estão acessíveis. Um status de API funcionando não garante, sozinho, que as respostas estejam corretas; confira as fontes exibidas em cada resposta.

## Comportamento e limites
- Usa apenas `knowledge_base/chunks.jsonl` e os documentos incluídos na pasta `knowledge_base/originais/`.
- A busca aplica normalização de acentos, correspondência lexical e expansões controladas de alguns termos comuns (por exemplo, falta/abono e rematrícula/matrícula).
- Se não houver evidência suficiente, não deve completar a resposta com conhecimento geral: informa a limitação e orienta a consultar os canais oficiais da UDF.
- Perguntas fora do contexto acadêmico recebem uma mensagem de escopo e sugestões de opções rápidas.
- A resposta apresenta documentos/páginas e a interface mostra pequenos trechos comprobatórios recuperados. A fonte é evidência de apoio, não uma garantia automática de que toda frase gerada esteja correta; revise informações importantes.
- Não há aprendizado automático com as conversas, integração com WhatsApp, acesso a sites externos ou envio de dados a serviços de nuvem nesta versão.

## Estrutura importante

```text
labtech-chatbot-basico/
├── index.html
├── styles.css
├── app.js
├── logo.svg
├── main.py
├── requirements.txt
├── iniciar.bat
├── README.md
└── knowledge_base/
    ├── chunks.jsonl
    ├── manifesto.json
    ├── originais/   # PDFs institucionais originais preservados
    └── textos/      # textos extraídos e materiais de apoio
```

**Não apague a pasta `knowledge_base` nem o arquivo `chunks.jsonl`.** Os PDFs originais foram preservados no pacote, conforme solicitado. Não é necessário instalar Live Server no VS Code.

## Solução de problemas

### A página abre, mas não responde
- Confirme que a janela do backend continua aberta.
- Abra `http://127.0.0.1:8000/saude`.
- Confirme que o Ollama está em execução e que `ollama list` mostra `qwen2.5:3b`.
- Verifique se as portas 8000 e 5500 não estão sendo usadas por outro programa.

### O modelo não está instalado

```bat
ollama pull qwen2.5:3b
```

### Erro de dependências Python
- Use Python 3.11 ou 3.12.
- Apague somente a pasta `.venv` criada localmente e execute `iniciar.bat` novamente. Não apague `knowledge_base` nem os PDFs.

### Resposta não encontrada ou resposta suspeita
- Reformule a pergunta com termos do assunto institucional.
- Confira as fontes e os trechos comprobatórios apresentados.
- Se os documentos não confirmarem a informação, procure a secretaria ou os canais oficiais da UDF. Não trate uma resposta do chatbot como confirmação oficial de prazo ou regra.

## Testes realizados nesta entrega
Os testes automatizados incluídos/verificados nesta preparação cobrem a leitura da base, a recuperação de assuntos de exemplo, a rejeição de uma pergunta geral fora do escopo e a estrutura dos resultados de fonte. A integração real com o modelo depende de Ollama e `qwen2.5:3b` instalados no computador de execução; valide também nesse ambiente antes de uma demonstração pública.


## Compatibilidade e solução de problemas

- **Python:** a versão 3.11 ou 3.12 é necessária nesta entrega. O inicializador detecta ambas; não promete compatibilidade com toda versão futura do Python. Se nenhuma estiver instalada, exibe o link oficial de instalação.
- **Smart App Control do Windows:** não desative a proteção apenas para executar o projeto. Se o Windows bloquear o arquivo, revise os arquivos do projeto e siga a política de segurança do computador; em computadores institucionais, peça ajuda ao suporte de TI.
- **Portas 5500 ou 8000 ocupadas:** feche outra instância do projeto ou verifique qual programa está usando a porta.
- **Ollama/modelo:** o backend e a geração de respostas dependem do Ollama e do modelo `qwen2.5:3b` instalado localmente. O download inicial exige internet.
- **Dependências:** se a instalação falhar, copie a mensagem completa do terminal para diagnóstico. Não execute como administrador como primeira tentativa.
- **Uso local:** os servidores são vinculados a `127.0.0.1`; esta configuração é para demonstração no próprio computador, não para disponibilizar o chatbot na rede.

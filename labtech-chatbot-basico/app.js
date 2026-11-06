const form = document.querySelector('#form');
const input = document.querySelector('#input');
const messages = document.querySelector('#messages');
const welcome = document.querySelector('#welcome');
const main = document.querySelector('#main');
const layout = document.querySelector('#layout');
const conversation = document.querySelector('.conversation');
const convList = document.querySelector('#convList');

const API_BASE = 'http://127.0.0.1:8000';
const TOKEN_KEY = 'labtech_token';

let token = null;            // sessão atual (guardada no navegador para continuar logado)
let usuario = null;          // { id, email, apelido }
let conversaAtualId = null;  // null = conversa nova, ainda não salva
let listaConversas = [];

// ---------------------------------------------------------------- sessão
function lerToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
function guardarToken(valor) {
  try {
    if (valor) localStorage.setItem(TOKEN_KEY, valor);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* navegador sem armazenamento: a sessão vale só até fechar a aba */ }
}

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function mensagemErro(dados, status) {
  if (dados && typeof dados.detail === 'string') return dados.detail;
  if (status === 422) return 'Dados inválidos. Confira o e-mail e a senha.';
  return 'Algo deu errado. Tente novamente.';
}

async function api(caminho, { method = 'GET', body } = {}) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers['Authorization'] = 'Bearer ' + token;

  const resposta = await fetch(API_BASE + caminho, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined
  });

  let dados = null;
  try { dados = await resposta.json(); } catch { /* resposta sem JSON */ }

  if (resposta.status === 401 && token) {
    encerrarSessao();
    mostrarAuth('Sua sessão expirou. Entre novamente.');
    throw new ApiError(401, 'Sessão expirada.');
  }
  if (!resposta.ok) throw new ApiError(resposta.status, mensagemErro(dados, resposta.status));
  return dados;
}

// ----------------------------------------------------------- tempo / datas
function formatarHora(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const hoje = new Date();
  const hora = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  if (d.toDateString() === hoje.toDateString()) return hora;
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) + ' ' + hora;
}

function grupoDaData(iso) {
  const inicioDoDia = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate());
  const dias = Math.round((inicioDoDia(new Date()) - inicioDoDia(new Date(iso))) / 86400000);
  if (dias <= 0) return 'Hoje';
  if (dias === 1) return 'Ontem';
  if (dias <= 7) return 'Últimos 7 dias';
  return 'Anteriores';
}

// Converte o texto da IA em elementos HTML seguros.
function formatarResposta(texto) {
  const container = document.createElement('div');
  container.className = 'formatted-answer';

  // Corrige negrito escapado: \*\*texto\*\*
  texto = String(texto || '')
    .replace(/\\\*\\\*/g, '**')
    .replace(/\\\*/g, '*')
    .replace(/\r\n/g, '\n')
    .trim();

  // Divide o texto em blocos separados por linhas vazias.
  const blocos = texto.split(/\n\s*\n/);

  blocos.forEach((bloco) => {
    bloco = bloco.trim();
    if (!bloco) return;

    const linhas = bloco.split('\n');

    // Identifica listas com marcadores ou numeração.
    const ehLista = linhas.every((linha) =>
      /^\s*(?:[-*•]|\d+[.)])\s+/.test(linha)
    );

    if (ehLista) {
      const listaNumerada = linhas.some((linha) =>
        /^\s*\d+[.)]\s+/.test(linha)
      );

      const lista = document.createElement(
        listaNumerada ? 'ol' : 'ul'
      );

      linhas.forEach((linha) => {
        const item = document.createElement('li');
        const conteudo = linha.replace(
          /^\s*(?:[-*•]|\d+[.)])\s+/,
          ''
        );

        formatarTextoInline(item, conteudo);
        lista.append(item);
      });

      container.append(lista);
    } else {
      const paragrafo = document.createElement('p');

      linhas.forEach((linha, indice) => {
        if (indice > 0) paragrafo.append(document.createElement('br'));
        formatarTextoInline(paragrafo, linha);
      });

      container.append(paragrafo);
    }
  });

  return container;
}

// Formata negrito e itálico sem interpretar HTML da resposta.
function formatarTextoInline(elemento, texto) {
  const regex = /(\*\*[^*]+?\*\*|(?<!\*)\*[^*]+?\*(?!\*))/g;
  let inicio = 0;
  let match;

  while ((match = regex.exec(texto)) !== null) {
    if (match.index > inicio) {
      elemento.append(
        document.createTextNode(texto.slice(inicio, match.index))
      );
    }

    const token = match[0];

    if (token.startsWith('**')) {
      const forte = document.createElement('strong');
      forte.textContent = token.slice(2, -2);
      elemento.append(forte);
    } else {
      const italico = document.createElement('em');
      italico.textContent = token.slice(1, -1);
      elemento.append(italico);
    }

    inicio = regex.lastIndex;
  }

  if (inicio < texto.length) {
    elemento.append(document.createTextNode(texto.slice(inicio)));
  }
}

function criarHora(iso) {
  const hora = document.createElement('time');
  hora.className = 'msg-time';
  hora.dateTime = iso;
  hora.title = new Date(iso).toLocaleString('pt-BR');
  hora.textContent = formatarHora(iso);
  return hora;
}

function add(text, role, fontes = [], quando = null, rolar = true) {
  const row = document.createElement('div');
  row.className = 'message ' + role;

  if (role === 'assistant') {
    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    const logo = document.createElement('img');
    logo.src = 'logo.svg';
    logo.alt = '';
    avatar.append(logo);
    row.append(avatar);
  }

  const content = document.createElement('div');

  if (role === 'assistant') {
    content.className = 'assistant-content';
  }

  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  if (role === 'assistant') {
    bubble.append(formatarResposta(text));
  } else {
    bubble.textContent = text;
  }

  content.append(bubble);

  // Remove fontes repetidas mantendo a ordem original.
  if (role === 'assistant' && fontes.length > 0) {
    const fontesUnicas = [];
    const fontesVistas = new Set();

    fontes.forEach((fonte) => {
      let chave;

      if (typeof fonte === 'string') {
        chave = fonte.trim().toLowerCase();
      } else {
        const documento =
          fonte.documento ||
          fonte.arquivo ||
          fonte.nome ||
          'Documento institucional';

        const pagina = fonte.pagina || '';
        chave = `${documento}|${pagina}`.trim().toLowerCase();
      }

      if (!fontesVistas.has(chave)) {
        fontesVistas.add(chave);
        fontesUnicas.push(fonte);
      }
    });

    const sourceBox = document.createElement('div');
    sourceBox.className = 'sources';

    const title = document.createElement('strong');
    title.textContent = 'Fontes consultadas';
    sourceBox.append(title);

    const list = document.createElement('ul');

    fontesUnicas.forEach((fonte) => {
      const item = document.createElement('li');

      if (typeof fonte === 'string') {
        item.textContent = fonte;
      } else {
        const documento =
          fonte.documento ||
          fonte.arquivo ||
          fonte.nome ||
          'Documento institucional';

        const pagina = fonte.pagina
          ? ` — página ${fonte.pagina}`
          : '';

        const label = document.createElement('div');
        label.textContent = documento + pagina;
        item.append(label);
        if (fonte.trecho) {
          const excerpt = document.createElement('p');
          excerpt.className = 'source-excerpt';
          excerpt.textContent = `“${fonte.trecho}”`;
          item.append(excerpt);
        }
        list.append(item);
        return;
      }

      list.append(item);
    });

    sourceBox.append(list);
    content.append(sourceBox);
  }

  if (quando) content.append(criarHora(quando));

  row.append(content);
  messages.append(row);

  if (rolar) {
    row.scrollIntoView({
      behavior: 'smooth',
      block: 'nearest'
    });
  }

  return row;
}

function atualizarHora(row, iso) {
  const atual = row.querySelector('.msg-time');
  if (atual) atual.replaceWith(criarHora(iso));
}

// -------------------------------------------------------- lista de conversas
function renderConversas() {
  convList.replaceChildren();

  if (listaConversas.length === 0) {
    const vazio = document.createElement('p');
    vazio.className = 'conv-vazia';
    vazio.textContent = 'Nenhuma conversa ainda.';
    convList.append(vazio);
    return;
  }

  let grupoAtual = null;
  listaConversas.forEach((conversa) => {
    const grupo = grupoDaData(conversa.atualizado_em);
    if (grupo !== grupoAtual) {
      grupoAtual = grupo;
      const rotulo = document.createElement('p');
      rotulo.className = 'group';
      rotulo.textContent = grupo;
      convList.append(rotulo);
    }

    const item = document.createElement('div');
    item.className = 'conv-item' + (conversa.id === conversaAtualId ? ' active' : '');
    item.tabIndex = 0;
    item.setAttribute('role', 'button');
    item.title = conversa.titulo;

    const titulo = document.createElement('span');
    titulo.className = 'titulo';
    titulo.textContent = conversa.titulo;

    const excluir = document.createElement('button');
    excluir.className = 'excluir';
    excluir.type = 'button';
    excluir.title = 'Excluir conversa';
    excluir.setAttribute('aria-label', 'Excluir conversa');
    excluir.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="m19 6-1 14H6L5 6"/></svg>';
    excluir.addEventListener('click', (e) => {
      e.stopPropagation();
      excluirConversa(conversa);
    });

    item.append(titulo, excluir);
    item.addEventListener('click', () => abrirConversa(conversa.id));
    item.addEventListener('keydown', (e) => {
      if (e.target === item && (e.key === 'Enter' || e.key === ' ')) {
        e.preventDefault();
        abrirConversa(conversa.id);
      }
    });
    convList.append(item);
  });
}

async function carregarConversas() {
  const dados = await api('/conversas');
  listaConversas = dados.conversas;
  renderConversas();
}

function fecharMenuNoCelular() {
  if (window.innerWidth <= 760) layout.classList.add('collapsed');
}

async function abrirConversa(id) {
  if (id === conversaAtualId) {
    fecharMenuNoCelular();
    return;
  }
  try {
    const dados = await api(`/conversas/${id}/mensagens`);
    conversaAtualId = id;
    messages.replaceChildren();
    welcome.hidden = true;
    main.classList.remove('empty');
    dados.mensagens.forEach((m) => {
      add(m.conteudo, m.papel === 'usuario' ? 'user' : 'assistant', m.fontes || [], m.criado_em, false);
    });
    conversation.scrollTop = conversation.scrollHeight;
    renderConversas();
    fecharMenuNoCelular();
  } catch (erro) {
    if (erro.status === 404) {
      await carregarConversas().catch(() => {});
    } else if (erro.status !== 401) {
      console.error('Erro ao abrir conversa:', erro);
    }
  }
}

async function excluirConversa(conversa) {
  if (!window.confirm(`Excluir a conversa “${conversa.titulo}”? Esta ação não pode ser desfeita.`)) return;
  try {
    await api(`/conversas/${conversa.id}`, { method: 'DELETE' });
    if (conversa.id === conversaAtualId) novaConversa();
    await carregarConversas();
  } catch (erro) {
    if (erro.status === 404) await carregarConversas().catch(() => {});
    else if (erro.status !== 401) console.error('Erro ao excluir conversa:', erro);
  }
}

function novaConversa() {
  conversaAtualId = null;
  messages.replaceChildren();
  welcome.hidden = false;
  main.classList.add('empty');
  input.value = '';
  input.style.height = 'auto';
  input.disabled = false;
  renderConversas();
  input.focus();
}

// ------------------------------------------------------------------- chat
async function submit(text) {
  text = text.trim();

  if (!text || !usuario) return;

  welcome.hidden = true;
  main.classList.remove('empty');
  const linhaUsuario = add(text, 'user', [], new Date().toISOString());

  input.value = '';
  input.style.height = 'auto';
  input.focus();

  const loadingRow = add(
    'Consultando a base institucional...',
    'assistant'
  );

  const sendButton = form.querySelector(
    'button[type="submit"], button:not([type])'
  );

  if (sendButton) sendButton.disabled = true;
  input.disabled = true;

  try {
    const data = await api('/buscar', {
      method: 'POST',
      body: { pergunta: text, conversa_id: conversaAtualId }
    });

    loadingRow.remove();

    const resposta =
      data.resposta ||
      data.response ||
      data.answer ||
      'Não foi possível obter uma resposta. Tente novamente.';

    const fontes =
      data.fontes ||
      data.sources ||
      [];

    add(resposta, 'assistant', fontes, data.resposta_em);
    if (data.pergunta_em) atualizarHora(linhaUsuario, data.pergunta_em);

    conversaAtualId = data.conversa_id;
    // Atualiza a barra lateral (nova conversa ou ordem por data) sem travar o chat.
    carregarConversas().catch(() => {});
  } catch (error) {
    loadingRow.remove();

    if (error.status === 401) return; // a sessão expirou: a tela de login já foi aberta

    console.error('Erro ao consultar o LabTech:', error);

    add(
      error.status
        ? error.message
        : 'Não consegui me conectar ao assistente. Verifique se o backend do LabTech está em execução e tente novamente.',
      'assistant'
    );
  } finally {
    input.disabled = false;

    if (sendButton) sendButton.disabled = false;

    if (usuario) input.focus();
  }
}

form.addEventListener('submit', (e) => {
  e.preventDefault();
  submit(input.value);
});

input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 140) + 'px';
});

document.querySelectorAll('[data-prompt]').forEach((button) => {
  button.addEventListener('click', () => {
    submit(button.dataset.prompt);
  });
});

input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();

    if (!input.disabled) {
      form.requestSubmit();
    }
  }
});

document.querySelector('#newChat').addEventListener('click', () => {
  novaConversa();
  fecharMenuNoCelular();
});

// Menu lateral: começa recolhido em telas pequenas.
if (window.innerWidth <= 760) layout.classList.add('collapsed');
document.querySelector('#toggle').addEventListener('click', () => {
  layout.classList.toggle('collapsed');
});

// ------------------------------------------------------ login e cadastro
const authBox = document.querySelector('#auth');
const authForm = document.querySelector('#authForm');
const authEmail = document.querySelector('#authEmail');
const authSenha = document.querySelector('#authSenha');
const authConfirma = document.querySelector('#authConfirma');
const confirmaBox = document.querySelector('#confirmaBox');
const authErro = document.querySelector('#authErro');
const authSubmit = document.querySelector('#authSubmit');
const tabLogin = document.querySelector('#tabLogin');
const tabRegistro = document.querySelector('#tabRegistro');

const EMAIL_ACADEMICO = /^[^\s@]+@cs\.udf\.edu\.br$/i;
const SENHA_MIN = 8;
let modoAuth = 'login';

function mostrarErroAuth(texto) {
  authErro.textContent = texto || '';
  authErro.hidden = !texto;
}

function definirModo(modo) {
  modoAuth = modo;
  const registro = modo === 'registro';
  tabLogin.classList.toggle('active', !registro);
  tabRegistro.classList.toggle('active', registro);
  tabLogin.setAttribute('aria-selected', String(!registro));
  tabRegistro.setAttribute('aria-selected', String(registro));
  confirmaBox.hidden = !registro;
  authSubmit.textContent = registro ? 'Criar conta' : 'Entrar';
  authSenha.autocomplete = registro ? 'new-password' : 'current-password';
  authSenha.placeholder = registro ? `Mínimo de ${SENHA_MIN} caracteres` : 'Sua senha';
  mostrarErroAuth('');
}

function mostrarAuth(aviso = '') {
  authBox.hidden = false;
  authForm.reset();
  definirModo('login');
  mostrarErroAuth(aviso);
  authEmail.focus();
}

tabLogin.addEventListener('click', () => definirModo('login'));
tabRegistro.addEventListener('click', () => definirModo('registro'));

authForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const email = authEmail.value.trim().toLowerCase();
  const senha = authSenha.value;

  if (!EMAIL_ACADEMICO.test(email)) {
    mostrarErroAuth('Use seu e-mail acadêmico (@cs.udf.edu.br).');
    return;
  }
  if (!senha) {
    mostrarErroAuth('Digite sua senha.');
    return;
  }
  if (modoAuth === 'registro') {
    if (senha.length < SENHA_MIN) {
      mostrarErroAuth(`A senha deve ter pelo menos ${SENHA_MIN} caracteres.`);
      return;
    }
    if (senha !== authConfirma.value) {
      mostrarErroAuth('As senhas não coincidem.');
      return;
    }
  }

  mostrarErroAuth('');
  authSubmit.disabled = true;
  token = null; // login/cadastro nunca enviam uma sessão antiga junto
  try {
    const dados = await api(modoAuth === 'registro' ? '/auth/registro' : '/auth/login', {
      method: 'POST',
      body: { email, senha }
    });
    token = dados.token;
    guardarToken(token);
    usuario = dados.usuario;
    await iniciarApp();
  } catch (erro) {
    mostrarErroAuth(erro.status
      ? erro.message
      : 'Não consegui me conectar ao servidor. Verifique se o backend do LabTech está em execução.');
  } finally {
    authSubmit.disabled = false;
  }
});

// ------------------------------------------------------ ciclo de vida do app
function mostrarUsuario() {
  document.querySelector('#userApelido').textContent = usuario.apelido;
  document.querySelector('#userEmail').textContent = usuario.email;
  document.querySelector('#userInicial').textContent = usuario.apelido.charAt(0).toUpperCase();
  document.querySelector('#greet').textContent = `Olá, ${usuario.apelido}!`;
}

async function iniciarApp() {
  mostrarUsuario();
  authBox.hidden = true;
  novaConversa();
  listaConversas = [];
  renderConversas();
  await carregarConversas().catch(() => {});
}

function encerrarSessao() {
  token = null;
  usuario = null;
  guardarToken(null);
  conversaAtualId = null;
  listaConversas = [];
  messages.replaceChildren();
  welcome.hidden = false;
  main.classList.add('empty');
  convList.replaceChildren();
}

document.querySelector('#logout').addEventListener('click', async () => {
  try {
    await api('/auth/logout', { method: 'POST' });
  } catch { /* se falhar, a sessão local é encerrada do mesmo jeito */ }
  if (token) encerrarSessao();
  mostrarAuth();
});

(async function iniciar() {
  token = lerToken();
  if (!token) {
    mostrarAuth();
    return;
  }
  try {
    const dados = await api('/auth/eu');
    usuario = dados.usuario;
    await iniciarApp();
  } catch (erro) {
    // 401 já abriu a tela de login; para falha de rede, mantém o token e avisa.
    if (erro.status !== 401) {
      authBox.hidden = false;
      mostrarErroAuth('Não consegui me conectar ao servidor. Verifique se o backend do LabTech está em execução e recarregue a página.');
    }
  }
})();

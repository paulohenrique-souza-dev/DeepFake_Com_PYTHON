const $ = (seletor) => document.querySelector(seletor);
let fluxoCamera = null, gravador = null, partes = [], arquivoVideo = null;
let nomeArquivo = 'gravacao.webm', personagemSelecionado = 'profissional';
let qualidade = 'hq', modo = 'full_body', segundos = 0, relogio = null;
let personagens = [];

async function iniciar() {
  try {
    const saude = await fetch('/api/health').then(r => r.json());
    $('#engine').textContent = saude.model_ready ? 'IA pronta' : 'modelo ONNX pendente';
    if (saude.model_ready) $('#engine').classList.add('ok');
  } catch (_) {}

  const dados = await fetch('/api/characters').then(r => r.json());
  personagens = dados.characters || [];
  $('#characters').innerHTML = personagens.map(p => `
    <button class="char ${p.id === personagemSelecionado ? 'selected' : ''}" data-id="${p.id}">
      <img src="/static/${p.thumbnail}" alt="${p.name}">
      <span>${p.name}</span><small>${p.body_ready ? 'Rosto + corpo' : 'Rosto realista'}</small>
    </button>`).join('');

  document.querySelectorAll('.char').forEach(botao => botao.onclick = () => selecionarPersonagem(botao.dataset.id));
  selecionarPersonagem(personagemSelecionado);
}

function selecionarPersonagem(id) {
  personagemSelecionado = id;
  document.querySelectorAll('.char').forEach(x => x.classList.toggle('selected', x.dataset.id === id));
  const p = personagens.find(x => x.id === id);
  if (!p) return;
  const fotos = p.gallery?.length ? p.gallery : [p.thumbnail];
  $('#avatarGallery').innerHTML = fotos.map((foto, i) => `<img src="/static/${foto}" alt="Referência ${i + 1} de ${p.name}">`).join('');
  $('#avatarStatus').textContent = p.body_ready
    ? 'Avatar preparado para composição de corpo inteiro e troca facial.'
    : 'Este avatar possui referência facial. Para troca corporal completa, adicione um asset corporal RGBA próprio.';
}

$('#cameraBtn').onclick = async () => {
  fluxoCamera = await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1920},height:{ideal:1080},frameRate:{ideal:30}},audio:true});
  $('#preview').srcObject = fluxoCamera; $('#empty').classList.add('hidden');
  $('#recordBtn').disabled = false; $('#cameraBtn').textContent = 'Câmera ativa';
};

$('#recordBtn').onclick = () => {
  if (gravador && gravador.state === 'recording') {
    
    try { gravador.requestData(); } catch (_) {}
    gravador.stop(); return;
  }
  partes = []; const opcoes = {};
  if (MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')) opcoes.mimeType = 'video/webm;codecs=vp9,opus';
  gravador = new MediaRecorder(fluxoCamera, opcoes);
  gravador.ondataavailable = e => { if (e.data.size) partes.push(e.data); };
  gravador.onstop = async () => {
    // Dá um ciclo ao navegador para entregar o último ondataavailable.
    await new Promise(resolve => setTimeout(resolve, 50));
    arquivoVideo = new Blob(partes, {type: gravador.mimeType || 'video/webm'});
    if (!arquivoVideo.size) { falhar('A gravação ficou vazia. Grave novamente.'); return; }
    nomeArquivo = 'camera_' + Date.now() + '.webm'; $('#preview').srcObject = null;
    $('#preview').src = URL.createObjectURL(arquivoVideo); $('#preview').controls = true;
    $('#recBadge').classList.add('hidden'); clearInterval(relogio);
    $('#recordBtn').textContent = '● Gravar novamente'; $('#processBtn').disabled = false;
    $('#recordInfo').textContent = `Gravação pronta • ${(arquivoVideo.size/1048576).toFixed(1)} MB`;
  };
  gravador.start(1000); segundos = 0; $('#timer').textContent = '00:00';
  $('#recBadge').classList.remove('hidden'); $('#recordBtn').textContent = '■ Parar gravação';
  relogio = setInterval(() => { segundos++; $('#timer').textContent = String(Math.floor(segundos/60)).padStart(2,'0') + ':' + String(segundos%60).padStart(2,'0'); }, 1000);
};

$('#fileInput').onchange = e => {
  const arquivo = e.target.files[0]; if (!arquivo) return;
  arquivoVideo = arquivo; nomeArquivo = arquivo.name; $('#preview').srcObject = null;
  $('#preview').src = URL.createObjectURL(arquivo); $('#preview').controls = true;
  $('#empty').classList.add('hidden'); $('#processBtn').disabled = false;
  $('#recordInfo').textContent = `${arquivo.name} • ${(arquivo.size/1048576).toFixed(1)} MB`;
};

document.querySelectorAll('[data-quality]').forEach(b => b.onclick = () => {
  document.querySelectorAll('[data-quality]').forEach(x => x.classList.remove('selected'));
  b.classList.add('selected'); qualidade = b.dataset.quality;
});
document.querySelectorAll('[data-mode]').forEach(b => b.onclick = () => {
  document.querySelectorAll('[data-mode]').forEach(x => x.classList.remove('selected'));
  b.classList.add('selected'); modo = b.dataset.mode;
});

$('#processBtn').onclick = async () => {
  if (!arquivoVideo) return; $('#processBtn').disabled = true;
  $('#progressCard').classList.remove('hidden'); $('#resultCard').classList.add('hidden');
  const formulario = new FormData(); formulario.append('video', arquivoVideo, nomeArquivo);
  formulario.append('character', personagemSelecionado); formulario.append('quality', qualidade); formulario.append('mode', modo);
  const resposta = await fetch('/api/video', {method:'POST', body:formulario}); const dados = await resposta.json();
  if (!resposta.ok) { falhar(dados.error); return; } acompanhar(dados.id);
};

async function acompanhar(id) {
  const intervalo = setInterval(async () => {
    const d = await fetch('/api/jobs/' + id).then(r => r.json());
    $('#progressPct').textContent = (d.progress || 0) + '%'; $('#bar').style.width = (d.progress || 0) + '%';
    $('#progressMsg').textContent = d.message || '';
    if (d.status === 'done') { clearInterval(intervalo); $('#progressTitle').textContent = 'Processamento concluído';
      const url = d.video_url + '?v=' + Date.now();
      $('#resultVideo').removeAttribute('src'); $('#resultVideo').load();
      $('#resultVideo').src = url; $('#resultVideo').load();
      $('#openVideo').href = url; $('#resultCard').classList.remove('hidden'); $('#processBtn').disabled = false;
    } else if (d.status === 'error') { clearInterval(intervalo); falhar(d.message); }
  }, 1000);
}
function falhar(mensagem) { $('#progressTitle').textContent = 'Erro'; $('#progressMsg').textContent = mensagem; $('#processBtn').disabled = false; }
iniciar();

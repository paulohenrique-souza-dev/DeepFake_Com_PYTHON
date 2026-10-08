from pathlib import Path
from uuid import uuid4
from flask import Blueprint, current_app, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

api = Blueprint('api', __name__, url_prefix='/api')


@api.get('/caracteristicas')
def personagens():
    return jsonify({'characters': current_app.servico_rosto.listar_personagens()})


@api.get('/saude_modelo')
def saude():
    modelo = Path(current_app.root_path).parent / 'ai_models' / 'inswapper_128.onnx'
    return jsonify({'ok': True, 'model_ready': modelo.exists()})


@api.post('/video')
def enviar_video():
    arquivo = request.files.get('video')
    if not arquivo or not arquivo.filename:
        return jsonify({'error': 'Envie ou grave um vídeo.'}), 400
    personagem = request.form.get('character', 'profissional')
    qualidade = request.form.get('quality', 'hq')
    modo = request.form.get('mode', 'full_body')
    if personagem not in current_app.servico_rosto.personagens:
        return jsonify({'error': 'Personagem inválido.'}), 400
    extensao = Path(secure_filename(arquivo.filename)).suffix.lower() or '.webm'
    if extensao not in {'.webm', '.mp4', '.mov', '.mkv', '.avi'}:
        return jsonify({'error': 'Formato de vídeo não suportado.'}), 400
    nome = f'{uuid4().hex}{extensao}'
    caminho = Path(current_app.root_path).parent / 'storage' / 'uploads' / nome
    caminho.parent.mkdir(parents=True, exist_ok=True)
    arquivo.save(caminho)
    trabalho = current_app.servico_video.criar_trabalho(caminho, personagem, qualidade, modo)
    return jsonify(trabalho), 202


@api.get('/trabalho/<trabalho_id>')
def trabalho(trabalho_id):
    dados = current_app.servico_video.obter(trabalho_id)
    if not dados:
        return jsonify({'error': 'Processamento não encontrado.'}), 404
    if dados.get('output'):
        dados['video_url'] = f'/api/videos/{dados["output"]}'
    return jsonify(dados)


@api.get('/videos/<path:nome>')
def video(nome):
    pasta = Path(current_app.root_path).parent / 'storage' / 'outputs'
    return send_from_directory(pasta, nome, conditional=True)

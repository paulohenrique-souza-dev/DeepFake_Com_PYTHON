from flask import Flask
from app.services.face_service import ServicoRosto
from app.services.video_service import ServicoVideo


def criar_app():
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024
    app.servico_rosto = ServicoRosto()
    app.servico_video = ServicoVideo(app.servico_rosto)
    # Compatibilidade com versões anteriores.
    app.face_service = app.servico_rosto
    app.video_service = app.servico_video
    from app.controllers.web_controller import web
    from app.controllers.api_controller import api
    app.register_blueprint(web)
    app.register_blueprint(api)
    return app


def create_app():
    return criar_app()

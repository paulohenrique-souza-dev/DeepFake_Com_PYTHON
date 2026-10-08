from pathlib import Path
import threading
import cv2

RAIZ = Path(__file__).resolve().parents[2]
DIRETORIO_PERSONAGENS = RAIZ / 'app' / 'assets' / 'characters'
DIRETORIO_MODELOS = RAIZ / 'ai_models'


class ServicoRosto:
    def __init__(self):
        self._analisador = None
        self._trocador = None
        self._rostos_origem = {}
        self._bloqueio = threading.Lock()
        # Somente dois avatares até agr, um M e outro F.
        self.personagens = {
            'profissional': {
                'nome': 'Profissional (Feminino)',
                'referencia': 'profissional/reference.jpg',
                'miniatura': 'characters/profissional.jpg',
                'corpo': 'profissional/body_front.png',
                'galeria': ['characters/profissional.jpg', 'characters/profissional_corpo.jpg', 'characters/profissional_rosto.jpg'],
            },
            'homem': {
                'nome': 'Homem (Masculino)',
                'referencia': 'homem/reference.jpg',
                'miniatura': 'characters/homem.jpg',
                'corpo': 'homem/body_front.png',
                'galeria': ['characters/homem.jpg', 'characters/homem_corpo.jpg', 'characters/homem_rosto.jpg'],
            },
        }

    def listar_personagens(self):
        saida = []
        for identificador, dados in self.personagens.items():
            corpo = dados.get('corpo')
            saida.append({
                'id': identificador,
                'name': dados['nome'],
                'ready': (DIRETORIO_PERSONAGENS / dados['referencia']).exists(),
                'thumbnail': dados['miniatura'],
                'gallery': dados.get('galeria', []),
                'body_ready': bool(corpo and (DIRETORIO_PERSONAGENS / corpo).exists()),
            })
        return saida

    def caminho_corpo(self, personagem_id):
        dados = self.personagens.get(personagem_id)
        if not dados or not dados.get('corpo'):
            return None
        return DIRETORIO_PERSONAGENS / dados['corpo']

    def garantir_motor(self):
        if self._analisador is not None:
            return
        with self._bloqueio:
            if self._analisador is not None:
                return
            try:
                import insightface
                from insightface.app import FaceAnalysis
                import onnxruntime as ort
            except Exception as exc:
                raise RuntimeError('Dependências de IA ausentes. Rode install.ps1.') from exc
            provedores = ['CPUExecutionProvider']
            disponiveis = ort.get_available_providers()
            if 'OpenVINOExecutionProvider' in disponiveis:
                provedores = ['OpenVINOExecutionProvider', 'CPUExecutionProvider']
            self._analisador = FaceAnalysis(name='buffalo_l', providers=provedores)
            self._analisador.prepare(ctx_id=-1, det_size=(640, 640))
            modelo = DIRETORIO_MODELOS / 'inswapper_128.onnx'
            if not modelo.exists():
                raise RuntimeError('Falta ai_models/inswapper_128.onnx. Veja README.md.')
            self._trocador = insightface.model_zoo.get_model(str(modelo), providers=provedores)

    def _rosto_origem(self, personagem_id):
        self.garantir_motor()
        if personagem_id in self._rostos_origem:
            return self._rostos_origem[personagem_id]
        dados = self.personagens.get(personagem_id)
        if not dados:
            raise ValueError('Personagem inválido.')
        imagem = cv2.imread(str(DIRETORIO_PERSONAGENS / dados['referencia']))
        if imagem is None:
            raise RuntimeError('Imagem de referência do personagem não encontrada.')
        rostos = self._analisador.get(imagem)
        if not rostos:
            raise RuntimeError('Nenhum rosto detectado na referência do personagem.')
        rosto = max(rostos, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        self._rostos_origem[personagem_id] = rosto
        return rosto

    def trocar_rosto_quadro(self, quadro, personagem_id, qualidade='hq'):
        self.garantir_motor()
        rostos = self._analisador.get(quadro)
        if not rostos:
            return quadro, False
        alvo = max(rostos, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        origem = self._rosto_origem(personagem_id)
        resultado = self._trocador.get(quadro, alvo, origem, paste_back=True)
        if qualidade == 'hq':
            suave = cv2.GaussianBlur(resultado, (0, 0), 0.42)
            resultado = cv2.addWeighted(resultado, 1.06, suave, -0.06, 0)
        return resultado, True

    # Compatibilidade com chamadas antigas.
    @property
    def characters(self):
        return self.personagens

    def list_characters(self):
        return self.listar_personagens()

    def ensure_engine(self):
        return self.garantir_motor()

    def swap_frame(self, frame, character_id, quality='hq'):
        return self.trocar_rosto_quadro(frame, character_id, quality)


FaceService = ServicoRosto

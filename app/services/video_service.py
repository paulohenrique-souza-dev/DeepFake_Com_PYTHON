from pathlib import Path
from uuid import uuid4
from datetime import datetime
import math
import subprocess
import threading
import shutil
import cv2
from app.services.body_service import ServicoCorpoAvatar

RAIZ = Path(__file__).resolve().parents[2]
UPLOADS = RAIZ / 'storage' / 'uploads'
SAIDAS = RAIZ / 'storage' / 'outputs'
TEMPORARIOS = RAIZ / 'storage' / 'temp'
for pasta in (UPLOADS, SAIDAS, TEMPORARIOS):
    pasta.mkdir(parents=True, exist_ok=True)


class ServicoVideo:
    def __init__(self, servico_rosto):
        self.rosto = servico_rosto
        self.trabalhos = {}
        self.bloqueio = threading.Lock()
        self.corpo = ServicoCorpoAvatar()

    def criar_trabalho(self, caminho_entrada, personagem_id, qualidade, modo='full_body'):
        trabalho_id = uuid4().hex[:12]
        trabalho = {
            'id': trabalho_id, 'status': 'queued', 'progress': 0, 'message': 'Na fila',
            'output': None, 'created_at': datetime.now().isoformat(timespec='seconds')
        }
        with self.bloqueio:
            self.trabalhos[trabalho_id] = trabalho
        threading.Thread(
            target=self._processar,
            args=(trabalho_id, Path(caminho_entrada), personagem_id, qualidade, modo),
            daemon=True,
        ).start()
        return trabalho

    def obter(self, trabalho_id):
        with self.bloqueio:
            return dict(self.trabalhos.get(trabalho_id, {}))

    def _atualizar(self, trabalho_id, **dados):
        with self.bloqueio:
            if trabalho_id in self.trabalhos:
                self.trabalhos[trabalho_id].update(dados)

    @staticmethod
    def _fps_seguro(captura):
        """Evita MP4 com duração/timestamps quebrados por FPS inválido do OpenCV."""
        fps = float(captura.get(cv2.CAP_PROP_FPS) or 0.0)
        if not math.isfinite(fps) or fps < 1.0 or fps > 120.0:
            return 30.0
        return fps

    @staticmethod
    def _video_valido(caminho):
        if not caminho.exists() or caminho.stat().st_size < 1024:
            return False
        cap = cv2.VideoCapture(str(caminho))
        try:
            if not cap.isOpened():
                return False
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            ok, _ = cap.read()
            return ok and math.isfinite(fps) and fps > 0 and frames > 0
        finally:
            cap.release()

    def _processar(self, trabalho_id, caminho_entrada, personagem_id, qualidade, modo):
        video_sem_audio = TEMPORARIOS / f'{trabalho_id}_sem_audio.mp4'
        video_final = SAIDAS / f'{trabalho_id}_gerado.mp4'
        captura = None
        gravador = None
        try:
            self._atualizar(trabalho_id, status='processing', message='Carregando IA...')
            self.rosto.garantir_motor()
            self.corpo.reiniciar()
            captura = cv2.VideoCapture(str(caminho_entrada))
            if not captura.isOpened():
                raise RuntimeError('Não foi possível abrir o vídeo. Tente MP4/H.264 ou grave novamente.')

            fps = self._fps_seguro(captura)
            largura = int(captura.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            altura = int(captura.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            total = int(captura.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if largura <= 0 or altura <= 0:
                raise RuntimeError('O vídeo possui dimensões inválidas.')

            # Alguns codecs exigem dimensões pares para H.264/yuv420p.
            largura_saida = largura - (largura % 2)
            altura_saida = altura - (altura % 2)
            if largura_saida <= 0 or altura_saida <= 0:
                raise RuntimeError('O vídeo possui dimensões inválidas.')

            gravador = cv2.VideoWriter(
                str(video_sem_audio), cv2.VideoWriter_fourcc(*'mp4v'), fps,
                (largura_saida, altura_saida)
            )
            if not gravador.isOpened():
                raise RuntimeError('Não foi possível criar o vídeo temporário.')

            caminho_corpo = self.rosto.caminho_corpo(personagem_id)
            quadros = 0
            rostos_trocados = 0
            corpos_trocados = 0
            while True:
                ok, quadro = captura.read()
                if not ok:
                    break

                if quadro.shape[1] != largura_saida or quadro.shape[0] != altura_saida:
                    quadro = quadro[:altura_saida, :largura_saida]

                resultado = quadro
                corpo_ok = False
                if modo == 'full_body' and caminho_corpo is not None:
                    resultado, corpo_ok, _ = self.corpo.aplicar(resultado, caminho_corpo)
                    corpos_trocados += int(corpo_ok)

                resultado, rosto_ok = self.rosto.trocar_rosto_quadro(resultado, personagem_id, qualidade)
                rostos_trocados += int(rosto_ok)

                if resultado.shape[1] != largura_saida or resultado.shape[0] != altura_saida:
                    resultado = cv2.resize(resultado, (largura_saida, altura_saida))
                gravador.write(resultado)
                quadros += 1
                if quadros % 3 == 0 or (total > 0 and quadros == total):
                    percentual = min(94, int(quadros * 94 / max(total, quadros, 1)))
                    etapa = 'corpo + rosto' if modo == 'full_body' and caminho_corpo else 'rosto'
                    total_txt = total if total > 0 else '?'
                    self._atualizar(
                        trabalho_id, progress=percentual,
                        message=f'Processando {etapa} • {self.corpo.nome_motor} • quadro {quadros}/{total_txt}'
                    )

            captura.release(); captura = None
            gravador.release(); gravador = None
            if quadros == 0:
                raise RuntimeError('O vídeo não contém quadros válidos.')
            if not self._video_valido(video_sem_audio):
                raise RuntimeError('O vídeo temporário ficou inválido. Verifique codec/FPS do arquivo de entrada.')

            self._atualizar(trabalho_id, progress=96, message='Finalizando vídeo e preservando áudio...')
            ffmpeg = shutil.which('ffmpeg')
            if ffmpeg:
                # O vídeo processado define a duração. O áudio é opcional e não deve zerar/truncar a saída.
                comando = [
                    ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
                    '-i', str(video_sem_audio), '-i', str(caminho_entrada),
                    '-map', '0:v:0', '-map', '1:a:0?',
                    '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
                    '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                    '-c:a', 'aac', '-b:a', '192k',
                    str(video_final)
                ]
                processo = subprocess.run(comando, capture_output=True, text=True)
                if processo.returncode != 0 or not self._video_valido(video_final):
                    video_final.unlink(missing_ok=True)
                    shutil.copy2(video_sem_audio, video_final)
            else:
                shutil.copy2(video_sem_audio, video_final)

            if not self._video_valido(video_final):
                raise RuntimeError('Falha ao finalizar o vídeo: arquivo de saída inválido ou com duração zero.')

            detalhe_corpo = f' • corpo {corpos_trocados}/{quadros}' if caminho_corpo and modo == 'full_body' else ''
            duracao = quadros / fps
            self._atualizar(
                trabalho_id, status='done', progress=100,
                message=f'Concluído • {duracao:.1f}s • rosto {rostos_trocados}/{quadros}{detalhe_corpo}',
                output=video_final.name,
            )
        except Exception as exc:
            video_final.unlink(missing_ok=True)
            self._atualizar(trabalho_id, status='error', message=str(exc))
        finally:
            if captura is not None:
                captura.release()
            if gravador is not None:
                gravador.release()
            try:
                video_sem_audio.unlink(missing_ok=True)
            except Exception:
                pass

    def create_job(self, input_path, character_id, quality, mode='full_body'):
        return self.criar_trabalho(input_path, character_id, quality, mode)

    def get(self, job_id):
        return self.obter(job_id)


VideoService = ServicoVideo

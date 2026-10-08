from pathlib import Path
import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parents[2]

class ServicoCorpoAvatar:
    """Em implementação / desenvolvimento

   
    """
    def __init__(self):
        self.cache_corpos = {}
        self.landmarks_anteriores = None
        self.caixa_anterior = None
        self.indice_quadro = 0
        self.pose = None
        self.mediapipe_disponivel = False
        try:
            import mediapipe as mp
            self.mp = mp
            self.pose = mp.solutions.pose.Pose(
                static_image_mode=False,
                model_complexity=2,
                smooth_landmarks=True,
                enable_segmentation=True,
                smooth_segmentation=True,
                min_detection_confidence=0.55,
                min_tracking_confidence=0.55,
            )
            self.mediapipe_disponivel = True
        except Exception:
            self.detector = cv2.HOGDescriptor()
            self.detector.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def reiniciar(self):
        self.landmarks_anteriores = None
        self.caixa_anterior = None
        self.indice_quadro = 0

    @property
    def nome_motor(self):
        return 'MediaPipe Pose adaptativo' if self.mediapipe_disponivel else 'OpenCV fallback'

    def _carregar_corpo(self, caminho):
        chave = str(caminho)
        if chave in self.cache_corpos:
            return self.cache_corpos[chave]
        img = cv2.imread(chave, cv2.IMREAD_UNCHANGED)
        if img is None:
            return None
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
        if img.shape[2] == 3:
            alpha = self._segmentar_asset(img)
            img = np.dstack([img, alpha])
        elif np.mean(img[:, :, 3]) > 250:
            img[:, :, 3] = self._segmentar_asset(img[:, :, :3])
        ys, xs = np.where(img[:, :, 3] > 20)
        if len(xs):
            img = img[max(0,ys.min()-3):min(img.shape[0],ys.max()+4), max(0,xs.min()-3):min(img.shape[1],xs.max()+4)]
        self.cache_corpos[chave] = img
        return img

    @staticmethod
    def _segmentar_asset(bgr):
        h,w=bgr.shape[:2]; mask=np.zeros((h,w),np.uint8)
        bg=np.zeros((1,65),np.float64); fg=np.zeros((1,65),np.float64)
        rect=(max(2,int(w*.04)), max(2,int(h*.015)), max(2,int(w*.92)), max(2,int(h*.97)))
        try:
            cv2.grabCut(bgr,mask,rect,bg,fg,6,cv2.GC_INIT_WITH_RECT)
            a=np.where((mask==cv2.GC_FGD)|(mask==cv2.GC_PR_FGD),255,0).astype(np.uint8)
        except cv2.error:
            a=np.full((h,w),255,np.uint8)
        a=cv2.morphologyEx(a,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
        return cv2.GaussianBlur(a,(0,0),1.2)

    def _analisar_pose(self, quadro):
        h,w=quadro.shape[:2]
        if self.mediapipe_disponivel:
            rgb=cv2.cvtColor(quadro,cv2.COLOR_BGR2RGB)
            r=self.pose.process(rgb)
            if not r.pose_landmarks:
                return None
            pts=[]
            for lm in r.pose_landmarks.landmark:
                pts.append([lm.x*w,lm.y*h,getattr(lm,'visibility',1.0)])
            pts=np.asarray(pts,np.float32)
            if self.landmarks_anteriores is not None and self.landmarks_anteriores.shape==pts.shape:
                pts[:,:2]=self.landmarks_anteriores[:,:2]*.72+pts[:,:2]*.28
            self.landmarks_anteriores=pts.copy()
            vis=pts[:,2]>.42
            valid=pts[vis]
            if len(valid)<5: return None
            
            ombros=np.mean(pts[[11,12],:2],axis=0); quadris=np.mean(pts[[23,24],:2],axis=0)
            rosto_vis=pts[0,2]>.4
            quadril_vis=max(pts[23,2],pts[24,2])>.42
            joelho_vis=max(pts[25,2],pts[26,2])>.42
            pe_vis=max(pts[27,2],pts[28,2])>.38
            if not quadril_vis:
                enquadramento='rosto_busto'
            elif pe_vis:
                enquadramento='corpo_inteiro'
            elif joelho_vis:
                enquadramento='tres_quartos'
            else:
                enquadramento='meio_corpo'
            xs=valid[:,0]; ys=valid[:,1]
            x1,x2=float(xs.min()),float(xs.max()); y1,y2=float(ys.min()),float(ys.max())
            largura=max(40,x2-x1); altura=max(60,y2-y1)
            x1-=largura*.24; x2+=largura*.24; y1-=altura*.12; y2+=altura*.08
            seg=None
            if r.segmentation_mask is not None:
                seg=np.clip(r.segmentation_mask,0,1).astype(np.float32)
            return {'caixa':(x1,y1,x2,y2),'enquadramento':enquadramento,'segmentacao':seg,'rosto':rosto_vis, 'quadril_vis':quadril_vis, 'joelho_vis':joelho_vis, 'pe_vis':pe_vis}
        # fallback 
        small=cv2.resize(quadro,None,fx=min(1,720/max(w,h)),fy=min(1,720/max(w,h)))
        scale=w/small.shape[1]
        boxes,_=self.detector.detectMultiScale(small,winStride=(8,8),padding=(12,12),scale=1.04)
        if not len(boxes): return None
        x,y,bw,bh=max(boxes,key=lambda b:b[2]*b[3]); x,y,bw,bh=[v*scale for v in (x,y,bw,bh)]
        # Fallback HOG não conhece articulações. alterarrr
        return {'caixa':(x,y,x+bw,y+bh),'enquadramento':'fallback_sem_corpo','segmentacao':None,'rosto':True, 'quadril_vis':False, 'joelho_vis':False, 'pe_vis':False}

    def _suavizar_caixa(self, caixa):
        if self.caixa_anterior is None:
            self.caixa_anterior=np.asarray(caixa,np.float32)
        else:
            self.caixa_anterior=self.caixa_anterior*.76+np.asarray(caixa,np.float32)*.24
        return tuple(self.caixa_anterior.astype(int))

    @staticmethod
    def _recorte_asset_por_enquadramento(asset, tipo):
        h=asset.shape[0]
        # Mantém proporções naturais do mesmo personagem
        limites={'rosto_busto':.43,'meio_corpo':.62,'tres_quartos':.82,'corpo_inteiro':1.0}
        return asset[:max(20,int(h*limites.get(tipo,1.0)))]

    def aplicar(self, quadro, caminho_corpo):
        asset=self._carregar_corpo(caminho_corpo)
        if asset is None: return quadro,False,'sem_asset'
        analise=self._analisar_pose(quadro)
        if analise is None: return quadro,False,'sem_pose'
        tipo=analise['enquadramento']
        H,W=quadro.shape[:2]

        # REGRA DE SEGURANÇA V6.1:
        # Close/rosto/busto -> somente face swap. Nunca desenhar corpo artificial.
        # Sem MediaPipe/landmarks corporais -> somente face swap.
        if tipo in ('rosto_busto', 'fallback_sem_corpo') or not analise.get('quadril_vis', False):
            return quadro, False, 'somente_rosto'

        x1,y1,x2,y2=self._suavizar_caixa(analise['caixa'])
        x1=max(0,x1); y1=max(0,y1); x2=min(W,x2); y2=min(H,y2)
        bw, bh = x2-x1, y2-y1
        if bw < 30 or bh < 40:
            return quadro, False, tipo

        # Atualização avatar invadindo img
        area_relativa = (bw * bh) / float(max(1, W * H))
        if area_relativa < 0.12:
            return quadro, False, 'deteccao_corporal_pequena'
        rec_asset=self._recorte_asset_por_enquadramento(asset,tipo)
        ah,aw=rec_asset.shape[:2]
        alvo_h=y2-y1
        alvo_w=max(24,int(alvo_h*aw/ah))
        cx=(x1+x2)//2
        ax1=max(0,cx-alvo_w//2); ax2=min(W,cx+alvo_w//2)
        if ax2<=ax1: return quadro,False,tipo
        alvo_w=ax2-ax1
        red=cv2.resize(rec_asset,(alvo_w,alvo_h),interpolation=cv2.INTER_LANCZOS4 if alvo_h>ah else cv2.INTER_AREA)
        rgb=red[:,:,:3].astype(np.float32)
        alpha=red[:,:,3].astype(np.float32)/255.0
        # Interseção suave com a segmentacao
        seg=analise['segmentacao']
        if seg is not None:
            s=seg[y1:y2,ax1:ax2]
            if s.shape==alpha.shape:
                # expande levemente para permitir que a roupa substituta cubra a roupa original
                s=cv2.GaussianBlur(s,(0,0),2.0)
                alpha*=np.clip(s*1.35,0,1)
        alpha=cv2.GaussianBlur(alpha,(0,0),1.0)
        a=alpha[:,:,None]
        out=quadro.copy()
        base=out[y1:y2,ax1:ax2].astype(np.float32)
        # harmonização simples de luminância para reduzir aspecto de colagem
        if np.any(alpha>.35):
            lum_base=float(cv2.cvtColor(base.astype(np.uint8),cv2.COLOR_BGR2GRAY)[alpha>.35].mean())
            lum_avatar=float(cv2.cvtColor(rgb.astype(np.uint8),cv2.COLOR_BGR2GRAY)[alpha>.35].mean())
            if lum_avatar>1:
                ganho=np.clip(lum_base/lum_avatar,.72,1.28)
                rgb=np.clip(rgb*ganho,0,255)
        out[y1:y2,ax1:ax2]=np.clip(rgb*a+base*(1-a),0,255).astype(np.uint8)
        return out,True,tipo

BodyAvatarService=ServicoCorpoAvatar

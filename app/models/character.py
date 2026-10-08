from dataclasses import dataclass

@dataclass(frozen=True)
class Caracteristicas:
    id: str
    nome: str
    arquivo_referencia: str
    thumbnail: str

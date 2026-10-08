from app import create_app


#testes Unitários simples.
def teste01():
    appteste1=create_app(); c=appteste1.test_client(); r=c.get('/api/health'); assert r.status_code==200

def testandoCaracteristicas():
    appteste2=create_app(); c=appteste2.test_client(); d=c.get('/api/characters').get_json(); assert len(d['characters'])==2

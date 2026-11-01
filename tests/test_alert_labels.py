import unittest
import alert_labels

class AlertLabelsTests(unittest.TestCase):
    def test_names_distinguish_outages_recovery_and_measurement_failures(self):
        cases=[('Sem ping: 21 perdas consecutivas.','critical','Equipamento sem resposta ao ping'),
               ('Ping restabelecido. Equipamento online.','success','Equipamento voltou a responder'),
               ('Porta Ten Gigabit Ethernet 1/1/1 (Entrada) caiu (link down).','critical','Porta perdeu a conexão'),
               ('Porta 1/1/1 restabelecida.','success','Porta voltou a ter conexão'),
               ('Circuito Centro: sem ping pelo Datacom.','critical','Circuito sem resposta'),
               ('Circuito Centro: erro de consulta.','warning','Não foi possível verificar o circuito'),
               ('Falha ao ler banda SIAE: timeout','warning','Não foi possível consultar a banda do rádio'),
               ('Leitura de banda SIAE restabelecida.','success','Consulta de banda do rádio normalizada'),
               ('Autenticação SSH recusada.','warning','Não foi possível consultar o equipamento')]
        for message,level,expected in cases:
            with self.subTest(message=message):self.assertEqual(alert_labels.title(message,level),expected)

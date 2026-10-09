from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.models.query import QuerySet
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Pedido, Preco, Produto, Supermercado


class PedidosTests(TestCase):
    def setUp(self):
        self.cliente = get_user_model().objects.create_user(username='felipe', password='123')
        self.outro_cliente = get_user_model().objects.create_user(username='ana', password='123')
        self.responsavel = get_user_model().objects.create_user(username='jorge', password='123')
        self.outro_responsavel = get_user_model().objects.create_user(username='quaresma', password='123')
        self.mercado = Supermercado.objects.create(nome='Jorge Super', endereco='Rua A', responsavel=self.responsavel)
        self.outro_mercado = Supermercado.objects.create(nome='Quaresma', endereco='Rua B', responsavel=self.outro_responsavel)
        self.produto = Produto.objects.create(nome='Café')
        self.preco = Preco.objects.create(produto=self.produto, supermercado=self.mercado, valor='9.89', estoque=5)
        self.api = APIClient()
        self.api.force_authenticate(self.cliente)
        self.dados = {'supermercado': self.mercado.pk, 'chave': str(uuid4()), 'total_esperado': '19.78',
                      'recebimento': 'pickup', 'pagamento': 'entrega',
                      'itens': [{'produto': self.produto.pk, 'quantidade': 2}]}

    def criar(self, **alteracoes):
        return self.api.post('/api/pedidos/', {**self.dados, **alteracoes}, format='json')

    def test_salva_cliente_itens_total_e_baixa_estoque(self):
        resposta = self.criar(cliente=self.outro_cliente.pk, total='0.01', status='concluido')
        self.assertEqual(resposta.status_code, 201)
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.cliente, self.cliente)
        self.assertEqual(pedido.total, Decimal('19.78'))
        self.assertEqual(pedido.status, 'recebido')
        self.assertEqual(pedido.itens.get().nome, 'Café')
        self.preco.refresh_from_db()
        self.assertEqual(self.preco.estoque, 3)

    def test_repetir_confirmacao_nao_duplica_nem_desconta_estoque_novamente(self):
        primeira = self.criar()
        segunda = self.criar()
        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(primeira.json()['id'], segunda.json()['id'])
        self.assertEqual(Pedido.objects.count(), 1)
        self.preco.refresh_from_db()
        self.assertEqual(self.preco.estoque, 3)
        self.assertEqual(self.criar(observacoes='Outra compra').status_code, 409)

    def test_preco_mudou_exige_nova_confirmacao_sem_criar_pedido(self):
        Preco.objects.filter(pk=self.preco.pk).update(valor='10.00')
        resposta = self.criar()
        self.assertEqual(resposta.status_code, 409)
        self.assertEqual(resposta.json()['total_atual'], '20.00')
        self.assertFalse(Pedido.objects.exists())
        self.preco.refresh_from_db()
        self.assertEqual(self.preco.estoque, 5)

    def test_estoque_insuficiente_ou_nao_informado_nao_cria_pedido(self):
        for estoque in (1, 0, None):
            with self.subTest(estoque=estoque):
                Preco.objects.filter(pk=self.preco.pk).update(estoque=estoque)
                self.assertEqual(self.criar().status_code, 409)
                self.assertFalse(Pedido.objects.exists())

    def test_produto_repetido_soma_quantidades_e_nao_ultrapassa_estoque(self):
        resposta = self.criar(itens=[{'produto': self.produto.pk, 'quantidade': 3}] * 2,
                             total_esperado='59.34')
        self.assertEqual(resposta.status_code, 409)
        self.assertFalse(Pedido.objects.exists())

    def test_reverte_pedido_e_estoques_se_uma_baixa_falhar(self):
        produto = Produto.objects.create(nome='Arroz')
        preco = Preco.objects.create(produto=produto, supermercado=self.mercado, valor='5.00', estoque=3)
        original = QuerySet.update
        chamadas = []

        def atualizar(queryset, **campos):
            if queryset.model is Preco:
                chamadas.append(1)
                if len(chamadas) == 2:
                    return 0
            return original(queryset, **campos)

        with patch.object(QuerySet, 'update', atualizar):
            resposta = self.criar(itens=self.dados['itens'] + [{'produto': produto.pk, 'quantidade': 1}],
                                 total_esperado='24.78')
        self.assertEqual(resposta.status_code, 409)
        self.assertFalse(Pedido.objects.exists())
        self.preco.refresh_from_db()
        preco.refresh_from_db()
        self.assertEqual(self.preco.estoque, 5)
        self.assertEqual(preco.estoque, 3)

    def test_total_entrega_e_cupom_sao_calculados_na_api(self):
        resposta = self.criar(recebimento='delivery', endereco='Rua C, 1', cupom='shopwise10', total_esperado='22.80')
        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(resposta.json()['taxa_entrega'], '5.00')
        self.assertEqual(resposta.json()['desconto'], '1.98')
        self.assertEqual(resposta.json()['total'], '22.80')

    def test_validacoes_e_login_obrigatorio(self):
        for dados in ({'itens': []}, {'itens': [{'produto': self.produto.pk, 'quantidade': 0}]},
                      {'cupom': 'INVENTADO'}, {'recebimento': 'delivery', 'endereco': ''}):
            self.assertEqual(self.criar(**dados).status_code, 400)
        self.api.force_authenticate(None)
        self.assertEqual(self.criar().status_code, 401)
        self.assertEqual(self.api.get('/api/pedidos/').status_code, 401)
        self.api.force_authenticate(self.responsavel)
        self.assertEqual(self.criar().status_code, 403)

    def test_cliente_e_supermercado_veem_apenas_seus_pedidos(self):
        pedido_id = self.criar().json()['id']
        for usuario, quantidade in ((self.cliente, 1), (self.outro_cliente, 0),
                                    (self.responsavel, 1), (self.outro_responsavel, 0)):
            self.api.force_authenticate(usuario)
            self.assertEqual(len(self.api.get('/api/pedidos/').json()), quantidade)
            self.assertEqual(self.api.get(f'/api/pedidos/{pedido_id}/').status_code, 200 if quantidade else 404)

    def test_so_responsavel_altera_status_e_respeita_a_sequencia(self):
        pedido_id = self.criar().json()['id']
        url = f'/api/pedidos/{pedido_id}/'
        for usuario in (self.cliente, self.outro_responsavel):
            self.api.force_authenticate(usuario)
            self.assertEqual(self.api.patch(url, {'status': 'em_preparacao'}, format='json').status_code, 403)
        self.api.force_authenticate(self.responsavel)
        self.assertEqual(self.api.patch(url, {'status': 'concluido'}, format='json').status_code, 400)
        for status in ('em_preparacao', 'concluido'):
            resposta = self.api.patch(url, {'status': status}, format='json')
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual(resposta.json()['status'], status)
        self.assertEqual(self.api.patch(url, {'status': 'recebido'}, format='json').status_code, 400)
        self.preco.refresh_from_db()
        self.assertEqual(self.preco.estoque, 3)

    def test_historico_preserva_nome_e_preco_depois_de_alterar_catalogo(self):
        pedido_id = self.criar().json()['id']
        Produto.objects.filter(pk=self.produto.pk).update(nome='Outro nome')
        Preco.objects.filter(pk=self.preco.pk).update(valor='50.00')
        item = self.api.get(f'/api/pedidos/{pedido_id}/').json()['itens'][0]
        self.assertEqual(item['nome'], 'Café')
        self.assertEqual(item['preco_unitario'], '9.89')

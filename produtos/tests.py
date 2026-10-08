from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from .models import ItemCarrinho, Preco, Produto, Supermercado
from .serializers import PrecoSerializer


@override_settings(DEBUG=True)
class PrepararDemoTests(TestCase):
    def test_prepara_dados_e_pode_rodar_novamente(self):
        for _ in range(2):
            call_command('preparar_demo', senha='ShopWise@2026', stdout=StringIO())

        self.assertEqual(get_user_model().objects.filter(
            username__in=['felipe', 'jorge_super', 'quaresma']
        ).count(), 3)
        self.assertEqual(Supermercado.objects.count(), 2)
        self.assertEqual(Produto.objects.count(), 1)
        self.assertEqual(Preco.objects.count(), 2)

        login = APIClient().post('/api/auth/login/', {
            'username': 'quaresma', 'password': 'ShopWise@2026'
        }, format='json')
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.data['tipo'], 'supermercado')
        self.assertTrue(login.data['token'])

        produto = Produto.objects.get(nome='Arroz 1 kg')
        comparacao = APIClient().get(f'/api/produtos/{produto.pk}/comparar/')
        self.assertEqual(comparacao.status_code, 200)
        self.assertEqual(
            [(item['supermercado_nome'], item['valor']) for item in comparacao.data],
            [('Quaresma', '5.99'), ('Jorge Super', '6.49')],
        )


class PrecoAtualTests(TestCase):
    def setUp(self):
        self.produto = Produto.objects.create(nome='Arroz 1 kg')
        self.supermercado = Supermercado.objects.create(
            nome='Mercado A', endereco='Rua A, 1'
        )

    def test_rejeita_preco_zero_ou_negativo_na_api(self):
        for valor in ('0.00', '-1.00'):
            with self.subTest(valor=valor):
                serializer = PrecoSerializer(data={
                    'produto': self.produto.pk,
                    'supermercado': self.supermercado.pk,
                    'valor': valor,
                })
                self.assertFalse(serializer.is_valid())
                self.assertIn('valor', serializer.errors)

    def test_rejeita_preco_duplicado_na_api_e_no_banco(self):
        Preco.objects.create(
            produto=self.produto,
            supermercado=self.supermercado,
            valor=Decimal('6.49'),
        )
        serializer = PrecoSerializer(data={
            'produto': self.produto.pk,
            'supermercado': self.supermercado.pk,
            'valor': '7.49',
        })
        self.assertFalse(serializer.is_valid())

        with self.assertRaises(IntegrityError), transaction.atomic():
            Preco.objects.create(
                produto=self.produto,
                supermercado=self.supermercado,
                valor=Decimal('7.49'),
            )

    def test_banco_rejeita_valor_nao_positivo(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Preco.objects.create(
                produto=self.produto,
                supermercado=self.supermercado,
                valor=Decimal('0.00'),
            )

    def test_registra_ultima_atualizacao(self):
        preco = Preco.objects.create(
            produto=self.produto,
            supermercado=self.supermercado,
            valor=Decimal('6.49'),
        )
        antigo = timezone.now() - timedelta(days=1)
        Preco.objects.filter(pk=preco.pk).update(atualizado_em=antigo)

        preco.valor = Decimal('5.99')
        preco.save()
        preco.refresh_from_db()

        self.assertGreater(preco.atualizado_em, antigo)
        self.assertEqual(preco.valor, Decimal('5.99'))


class ComparacaoPrecoTests(TestCase):
    def setUp(self):
        self.produto = Produto.objects.create(nome='Arroz 1 kg')
        self.url = f'/api/produtos/{self.produto.pk}/comparar/'

    def test_mostra_supermercados_em_ordem_de_preco(self):
        mercado_a = Supermercado.objects.create(nome='Mercado A', endereco='Rua A')
        mercado_b = Supermercado.objects.create(nome='Mercado B', endereco='Rua B')
        Preco.objects.create(
            produto=self.produto, supermercado=mercado_a, valor=Decimal('7.49')
        )
        Preco.objects.create(
            produto=self.produto, supermercado=mercado_b, valor=Decimal('5.99')
        )

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            [item['supermercado_nome'] for item in resposta.json()],
            ['Mercado B', 'Mercado A'],
        )
        self.assertEqual(
            [item['valor'] for item in resposta.json()],
            ['5.99', '7.49'],
        )

    def test_produto_sem_precos_retorna_lista_vazia(self):
        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), [])

    def test_produto_inexistente_retorna_404(self):
        resposta = self.client.get('/api/produtos/999999/comparar/')

        self.assertEqual(resposta.status_code, 404)


class CadastroTests(TestCase):
    url = '/api/auth/cadastro/'
    senha = 'SenhaSegura2026!'

    def test_nome_pode_se_repetir_e_email_identifica_cada_conta(self):
        cliente = APIClient().post(self.url, {
            'tipo': 'usuario', 'nome': 'Felipe',
            'email': 'felipe1@example.com', 'password': self.senha,
        }, format='json')
        mercado = APIClient().post(self.url, {
            'tipo': 'supermercado', 'nome': 'Felipe',
            'email': 'felipe2@example.com', 'password': self.senha,
            'supermercado_nome': 'Mercado A',
            'supermercado_endereco': 'Rua A, 1',
        }, format='json')

        self.assertEqual(cliente.status_code, 201)
        self.assertEqual(mercado.status_code, 201)
        self.assertEqual(cliente.data['nome'], 'Felipe')
        self.assertEqual(mercado.data['nome'], 'Felipe')
        self.assertEqual(
            list(get_user_model().objects.order_by('email').values_list('first_name', flat=True)),
            ['Felipe', 'Felipe'],
        )

        for email, tipo in (
            ('felipe1@example.com', 'usuario'),
            ('felipe2@example.com', 'supermercado'),
        ):
            with self.subTest(email=email):
                login = APIClient().post('/api/auth/login/', {
                    'email': email, 'password': self.senha,
                }, format='json')
                self.assertEqual(login.status_code, 200)
                self.assertEqual(login.data['tipo'], tipo)
                self.assertEqual(login.data['nome'], 'Felipe')
                self.assertTrue(login.data['token'])

        duplicado = APIClient().post(self.url, {
            'tipo': 'usuario', 'nome': 'Outra Pessoa',
            'email': 'FELIPE1@example.com', 'password': self.senha,
        }, format='json')
        self.assertEqual(duplicado.status_code, 400)
        self.assertIn('email', duplicado.data)

    def test_cadastra_usuario_com_senha_protegida_e_permite_login(self):
        resposta = APIClient().post(self.url, {
            'tipo': 'usuario',
            'username': 'ana',
            'email': 'ana@example.com',
            'password': self.senha,
            'is_staff': True,
        }, format='json')

        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(resposta.data['tipo'], 'usuario')
        self.assertEqual(resposta.data['supermercados'], [])
        self.assertNotIn('password', resposta.data)
        self.assertNotIn('token', resposta.data)
        usuario = get_user_model().objects.get(username='ana')
        self.assertTrue(usuario.check_password(self.senha))
        self.assertFalse(usuario.is_staff)

        login = APIClient().post('/api/auth/login/', {
            'username': 'ana', 'password': self.senha,
        }, format='json')
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.data['tipo'], 'usuario')

    def test_cadastra_supermercado_e_responsavel_pode_alterar_preco(self):
        resposta = APIClient().post(self.url, {
            'tipo': 'supermercado',
            'username': 'mercado_a',
            'email': 'mercado@example.com',
            'password': self.senha,
            'supermercado_nome': 'Mercado A',
            'supermercado_endereco': 'Rua A, 1',
        }, format='json')

        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(resposta.data['tipo'], 'supermercado')
        mercado = Supermercado.objects.get(nome='Mercado A')
        self.assertEqual(mercado.responsavel.username, 'mercado_a')
        self.assertEqual(resposta.data['supermercados'][0]['id'], mercado.pk)

        login = APIClient().post('/api/auth/login/', {
            'username': 'mercado_a', 'password': self.senha,
        }, format='json')
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.data['tipo'], 'supermercado')

        produto = Produto.objects.create(nome='Arroz 1 kg')
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Token {login.data['token']}")
        preco = api.post('/api/precos/', {
            'produto': produto.pk,
            'supermercado': mercado.pk,
            'valor': '6.49',
        }, format='json')
        self.assertEqual(preco.status_code, 201)

    def test_rejeita_usuario_ou_email_duplicado(self):
        get_user_model().objects.create_user(
            username='ana', email='ana@example.com', password=self.senha,
        )
        for username, email, campo in (
            ('ANA', 'outra@example.com', 'username'),
            ('outra', 'ANA@example.com', 'email'),
        ):
            with self.subTest(campo=campo):
                resposta = APIClient().post(self.url, {
                    'tipo': 'usuario', 'username': username,
                    'email': email, 'password': self.senha,
                }, format='json')
                self.assertEqual(resposta.status_code, 400)
                self.assertIn(campo, resposta.data)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_rejeita_supermercado_sem_dados_e_senha_fraca(self):
        incompleto = APIClient().post(self.url, {
            'tipo': 'supermercado', 'username': 'mercado_a',
            'email': 'mercado@example.com', 'password': self.senha,
        }, format='json')
        self.assertEqual(incompleto.status_code, 400)
        self.assertIn('supermercado_nome', incompleto.data)
        self.assertIn('supermercado_endereco', incompleto.data)

        senha_fraca = APIClient().post(self.url, {
            'tipo': 'usuario', 'username': 'ana',
            'email': 'ana@example.com', 'password': '123',
        }, format='json')
        self.assertEqual(senha_fraca.status_code, 400)
        self.assertIn('password', senha_fraca.data)
        self.assertEqual(get_user_model().objects.count(), 0)
        self.assertEqual(Supermercado.objects.count(), 0)


class LoginEPermissoesTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.usuario = User.objects.create_user(username='usuario', password='senha12345')
        self.mercado_usuario = User.objects.create_user(username='mercado', password='senha12345')
        self.outro_mercado_usuario = User.objects.create_user(username='outro_mercado', password='senha12345')
        self.admin = User.objects.create_user(
            username='admin', password='senha12345', is_staff=True
        )
        self.loja = Supermercado.objects.create(
            nome='Mercado A', endereco='Rua A', responsavel=self.mercado_usuario
        )
        self.outra_loja = Supermercado.objects.create(
            nome='Mercado B', endereco='Rua B', responsavel=self.outro_mercado_usuario
        )
        self.produto = Produto.objects.create(nome='Arroz 1 kg')

    def api_com_token(self, user):
        api = APIClient()
        token, _ = Token.objects.get_or_create(user=user)
        api.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        return api

    def test_login_retorna_token_e_tipo_de_conta(self):
        for user, tipo in (
            (self.usuario, 'usuario'),
            (self.mercado_usuario, 'supermercado'),
            (self.admin, 'administrador'),
        ):
            with self.subTest(tipo=tipo):
                resposta = APIClient().post(
                    '/api/auth/login/',
                    {'username': user.username, 'password': 'senha12345'},
                    format='json',
                )
                self.assertEqual(resposta.status_code, 200)
                self.assertEqual(resposta.data['tipo'], tipo)
                self.assertEqual(resposta.data['token'], Token.objects.get(user=user).key)
                if tipo == 'supermercado':
                    self.assertEqual(resposta.data['supermercados'][0]['id'], self.loja.pk)

    def test_login_invalido_nao_entrega_token(self):
        resposta = APIClient().post(
            '/api/auth/login/',
            {'username': 'usuario', 'password': 'errada'},
            format='json',
        )
        self.assertEqual(resposta.status_code, 401)
        self.assertNotIn('token', resposta.data)

    def test_login_aceita_email_cadastrado(self):
        self.usuario.email = 'usuario@example.com'
        self.usuario.save(update_fields=['email'])

        resposta = APIClient().post(
            '/api/auth/login/',
            {'email': 'usuario@example.com', 'password': 'senha12345'},
            format='json',
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.data['usuario'], self.usuario.username)
        self.assertEqual(resposta.data['tipo'], 'usuario')

    def test_consulta_publica_e_escrita_sem_token_bloqueada(self):
        api = APIClient()
        self.assertEqual(api.get('/api/produtos/').status_code, 200)
        self.assertEqual(
            api.post('/api/produtos/', {'nome': 'Feijão 1 kg'}, format='json').status_code,
            401,
        )
        resposta = api.post(
            '/api/precos/',
            {'produto': self.produto.pk, 'supermercado': self.loja.pk, 'valor': '6.49'},
            format='json',
        )
        self.assertEqual(resposta.status_code, 401)

    def test_supermercado_cadastra_produto_compartilhado(self):
        api = self.api_com_token(self.mercado_usuario)
        cadastro = api.post(
            '/api/produtos/',
            {'nome': 'Feijão 1 kg', 'categoria': 'Mercearia'},
            format='json',
        )
        self.assertEqual(cadastro.status_code, 201)
        produto_id = cadastro.data['id']

        outro_mercado = self.api_com_token(self.outro_mercado_usuario)
        preco = outro_mercado.post(
            '/api/precos/',
            {
                'produto': produto_id,
                'supermercado': self.outra_loja.pk,
                'valor': '8.49',
            },
            format='json',
        )
        self.assertEqual(preco.status_code, 201)

        duplicado = api.post(
            '/api/produtos/', {'nome': 'feijão 1 kg'}, format='json'
        )
        self.assertEqual(duplicado.status_code, 400)
        self.assertIn('nome', duplicado.data)

        alterar = api.put(
            f'/api/produtos/{produto_id}/',
            {'nome': 'Feijão 2 kg', 'categoria': 'Mercearia'},
            format='json',
        )
        self.assertEqual(alterar.status_code, 403)
        self.assertEqual(api.delete(f'/api/produtos/{produto_id}/').status_code, 403)
        self.assertTrue(Produto.objects.filter(pk=produto_id, nome='Feijão 1 kg').exists())

    def test_supermercado_edita_apenas_preco_da_propria_loja(self):
        api = self.api_com_token(self.mercado_usuario)
        dados = {'produto': self.produto.pk, 'supermercado': self.loja.pk, 'valor': '6.49'}
        resposta = api.post('/api/precos/', dados, format='json')
        self.assertEqual(resposta.status_code, 201)
        preco_id = resposta.data['id']

        dados['valor'] = '5.99'
        self.assertEqual(api.put(f'/api/precos/{preco_id}/', dados, format='json').status_code, 200)
        self.assertEqual(Preco.objects.get(pk=preco_id).valor, Decimal('5.99'))

        dados['supermercado'] = self.outra_loja.pk
        self.assertEqual(api.put(f'/api/precos/{preco_id}/', dados, format='json').status_code, 403)
        self.assertEqual(api.post('/api/precos/', dados, format='json').status_code, 403)

    def test_usuario_nao_altera_catalogo_ou_preco(self):
        api = self.api_com_token(self.usuario)
        self.assertEqual(api.post('/api/produtos/', {'nome': 'Feijão'}, format='json').status_code, 403)
        self.assertEqual(
            api.post('/api/precos/', {
                'produto': self.produto.pk,
                'supermercado': self.loja.pk,
                'valor': '6.49',
            }, format='json').status_code,
            403,
        )

    def test_supermercado_nao_edita_ou_exclui_preco_de_outra_loja(self):
        preco = Preco.objects.create(
            produto=self.produto,
            supermercado=self.outra_loja,
            valor=Decimal('8.49'),
        )
        api = self.api_com_token(self.mercado_usuario)
        url = f'/api/precos/{preco.pk}/'
        dados = {
            'produto': self.produto.pk,
            'supermercado': self.outra_loja.pk,
            'valor': '7.49',
        }

        self.assertEqual(api.put(url, dados, format='json').status_code, 403)
        self.assertEqual(api.delete(url).status_code, 403)
        self.assertTrue(Preco.objects.filter(pk=preco.pk, valor=Decimal('8.49')).exists())

    def test_administrador_pode_cadastrar_produto(self):
        resposta = self.api_com_token(self.admin).post(
            '/api/produtos/', {'nome': 'Feijão', 'categoria': 'Mercearia'}, format='json'
        )
        self.assertEqual(resposta.status_code, 201)


class CarrinhoTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.usuario = User.objects.create_user(username='cliente', password='senha12345')
        self.outro_usuario = User.objects.create_user(username='outro', password='senha12345')
        produto = Produto.objects.create(nome='Arroz 1 kg')
        supermercado = Supermercado.objects.create(nome='Mercado A', endereco='Rua A')
        self.preco = Preco.objects.create(
            produto=produto, supermercado=supermercado, valor=Decimal('6.49')
        )

    def api_com_token(self, usuario):
        api = APIClient()
        token, _ = Token.objects.get_or_create(user=usuario)
        api.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        return api

    def test_exige_login_e_isola_carrinho_por_usuario(self):
        anonimo = APIClient()
        self.assertEqual(anonimo.get('/api/carrinho/').status_code, 401)
        self.assertEqual(anonimo.post('/api/carrinho/', {
            'preco': self.preco.pk,
        }, format='json').status_code, 401)

        cliente = self.api_com_token(self.usuario)
        cadastro = cliente.post('/api/carrinho/', {
            'preco': self.preco.pk,
        }, format='json')
        self.assertEqual(cadastro.status_code, 201)
        item_id = cadastro.data['id']

        outro = self.api_com_token(self.outro_usuario)
        self.assertEqual(outro.get('/api/carrinho/').data['itens'], [])
        self.assertEqual(outro.get(f'/api/carrinho/{item_id}/').status_code, 404)
        self.assertEqual(outro.put(f'/api/carrinho/{item_id}/', {
            'quantidade': 2,
        }, format='json').status_code, 404)
        self.assertEqual(outro.delete(f'/api/carrinho/{item_id}/').status_code, 404)
        self.assertTrue(ItemCarrinho.objects.filter(pk=item_id, usuario=self.usuario).exists())

    def test_adiciona_atualiza_total_e_remove_item(self):
        api = self.api_com_token(self.usuario)
        cadastro = api.post('/api/carrinho/', {
            'preco': self.preco.pk, 'quantidade': 2,
        }, format='json')
        self.assertEqual(cadastro.status_code, 201)
        item_id = cadastro.data['id']
        self.assertEqual(cadastro.data['produto_nome'], 'Arroz 1 kg')
        self.assertEqual(cadastro.data['supermercado_nome'], 'Mercado A')
        self.assertEqual(cadastro.data['subtotal'], '12.98')

        repetido = api.post('/api/carrinho/', {
            'preco': self.preco.pk, 'quantidade': 1,
        }, format='json')
        self.assertEqual(repetido.status_code, 200)
        self.assertEqual(repetido.data['id'], item_id)
        self.assertEqual(repetido.data['quantidade'], 3)
        self.assertEqual(ItemCarrinho.objects.count(), 1)
        self.assertEqual(api.get('/api/carrinho/').data['total'], '19.47')

        atualizado = api.put(f'/api/carrinho/{item_id}/', {
            'quantidade': 4,
        }, format='json')
        self.assertEqual(atualizado.status_code, 200)
        self.assertEqual(atualizado.data['quantidade'], 4)

        self.preco.valor = Decimal('5.99')
        self.preco.save()
        carrinho = api.get('/api/carrinho/').data
        self.assertEqual(carrinho['itens'][0]['valor_unitario'], '5.99')
        self.assertEqual(carrinho['total'], '23.96')

        self.assertEqual(api.delete(f'/api/carrinho/{item_id}/').status_code, 204)
        self.assertEqual(api.get('/api/carrinho/').data, {
            'itens': [], 'total': '0.00',
        })

    def test_rejeita_preco_inexistente_e_quantidade_invalida(self):
        api = self.api_com_token(self.usuario)
        self.assertEqual(api.post('/api/carrinho/', {
            'preco': 999999,
        }, format='json').status_code, 400)
        self.assertEqual(api.post('/api/carrinho/', {
            'preco': self.preco.pk, 'quantidade': 0,
        }, format='json').status_code, 400)
        self.assertEqual(api.post('/api/carrinho/', {
            'preco': self.preco.pk, 'quantidade': -1,
        }, format='json').status_code, 400)
        self.assertEqual(ItemCarrinho.objects.count(), 0)

        item_id = api.post('/api/carrinho/', {
            'preco': self.preco.pk,
        }, format='json').data['id']
        self.assertEqual(api.put(f'/api/carrinho/{item_id}/', {
            'quantidade': 0,
        }, format='json').status_code, 400)
        self.assertEqual(ItemCarrinho.objects.get(pk=item_id).quantidade, 1)

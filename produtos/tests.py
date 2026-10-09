from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from .models import Preco, Produto, Supermercado
from .serializers import PrecoSerializer


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

    def test_estoque_aceita_zero_mas_rejeita_numero_negativo(self):
        dados = {
            'produto': self.produto.pk,
            'supermercado': self.supermercado.pk,
            'valor': '6.49',
            'estoque': 0,
        }
        self.assertTrue(PrecoSerializer(data=dados).is_valid())
        dados['estoque'] = -1
        serializer = PrecoSerializer(data=dados)
        self.assertFalse(serializer.is_valid())
        self.assertIn('estoque', serializer.errors)

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
            produto=self.produto, supermercado=mercado_a, valor=Decimal('7.49'), estoque=10
        )
        Preco.objects.create(
            produto=self.produto, supermercado=mercado_b, valor=Decimal('5.99'), estoque=4
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

    def test_comparacao_mostra_apenas_mercados_com_estoque_positivo(self):
        disponivel = Supermercado.objects.create(nome='Disponível', endereco='Rua A')
        esgotado = Supermercado.objects.create(nome='Esgotado', endereco='Rua B')
        nao_informado = Supermercado.objects.create(nome='Não informado', endereco='Rua C')
        Preco.objects.create(produto=self.produto, supermercado=disponivel, valor=Decimal('7.00'), estoque=3)
        Preco.objects.create(produto=self.produto, supermercado=esgotado, valor=Decimal('5.00'), estoque=0)
        Preco.objects.create(produto=self.produto, supermercado=nao_informado, valor=Decimal('6.00'))

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual([item['supermercado_nome'] for item in resposta.json()], ['Disponível'])

    def test_produto_inexistente_retorna_404(self):
        resposta = self.client.get('/api/produtos/999999/comparar/')

        self.assertEqual(resposta.status_code, 404)


class ComparacaoCarrinhoTests(TestCase):
    url = '/api/carrinho/comparar/'

    def setUp(self):
        self.api = APIClient()
        self.arroz = Produto.objects.create(nome='Arroz')
        self.cafe = Produto.objects.create(nome='Café')
        self.jorge = Supermercado.objects.create(nome='Jorge Super', endereco='Rua A')
        self.quaresma = Supermercado.objects.create(nome='Quaresma', endereco='Rua B')
        for mercado, arroz, cafe in (
            (self.jorge, '6.49', '9.89'),
            (self.quaresma, '5.99', '11.49'),
        ):
            Preco.objects.create(produto=self.arroz, supermercado=mercado, valor=arroz, estoque=10)
            Preco.objects.create(produto=self.cafe, supermercado=mercado, valor=cafe, estoque=10)
        self.itens = [
            {'produto': self.arroz.pk, 'quantidade': 2},
            {'produto': self.cafe.pk, 'quantidade': 1},
        ]

    def comparar(self, itens=None):
        return self.api.post(self.url, {'itens': self.itens if itens is None else itens}, format='json')

    def test_calcula_quantidades_e_ordena_pelo_total_da_compra(self):
        resposta = self.comparar()
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados['menor_total'], '22.87')
        self.assertEqual([m['total'] for m in dados['supermercados']], ['22.87', '23.47'])
        self.assertEqual(dados['supermercados'][0]['supermercado'], self.jorge.pk)
        self.assertEqual(dados['supermercados'][0]['economia'], '0.60')
        self.assertEqual(dados['supermercados'][0]['itens'][0]['subtotal'], '12.98')

    def test_mercado_incompleto_nao_concorre_ao_menor_total(self):
        Preco.objects.filter(produto=self.cafe, supermercado=self.jorge).delete()
        dados = self.comparar().json()
        self.assertEqual(dados['menor_total'], '23.47')
        incompleto = dados['supermercados'][1]
        self.assertFalse(incompleto['completo'])
        self.assertIsNone(incompleto['total'])
        self.assertIsNone(incompleto['economia'])
        self.assertFalse(incompleto['itens'][1]['disponivel'])

    def test_estoque_insuficiente_zero_ou_nao_informado_impede_total_completo(self):
        for estoque in (1, 0, None):
            with self.subTest(estoque=estoque):
                Preco.objects.filter(produto=self.arroz, supermercado=self.jorge).update(estoque=estoque)
                dados = self.comparar().json()
                mercado = next(m for m in dados['supermercados'] if m['supermercado'] == self.jorge.pk)
                self.assertFalse(mercado['completo'])
                self.assertIsNone(mercado['total'])

    def test_soma_produto_repetido_antes_de_conferir_estoque(self):
        Preco.objects.filter(produto=self.arroz).update(estoque=3)
        dados = self.comparar([
            {'produto': self.arroz.pk, 'quantidade': 2},
            {'produto': self.arroz.pk, 'quantidade': 2},
        ]).json()
        self.assertIsNone(dados['menor_total'])
        for mercado in dados['supermercados']:
            self.assertEqual(len(mercado['itens']), 1)
            self.assertEqual(mercado['itens'][0]['quantidade'], 4)
            self.assertFalse(mercado['completo'])

    def test_rejeita_carrinho_vazio_produto_inexistente_e_quantidade_invalida(self):
        for itens in ([], [{'produto': 999999, 'quantidade': 1}],
                      [{'produto': self.arroz.pk, 'quantidade': 0}],
                      [{'produto': self.arroz.pk, 'quantidade': -1}],
                      [{'produto': self.arroz.pk, 'quantidade': 1.5}]):
            with self.subTest(itens=itens):
                self.assertEqual(self.comparar(itens).status_code, 400)

    def test_mercado_sem_ofertas_aparece_incompleto_e_ausencia_de_mercados_retorna_lista_vazia(self):
        mercado = Supermercado.objects.create(nome='Sem ofertas', endereco='Rua C')
        dados = self.comparar().json()
        resultado = next(m for m in dados['supermercados'] if m['supermercado'] == mercado.pk)
        self.assertFalse(resultado['completo'])
        self.assertIsNone(resultado['total'])
        Supermercado.objects.all().delete()
        self.assertEqual(self.comparar().json(), {'menor_total': None, 'supermercados': []})


class CadastroTests(TestCase):
    url = '/api/auth/cadastro/'
    senha = 'senha'

    def test_nome_pode_se_repetir_e_login_por_email_retorna_tipo_e_token(self):
        for tipo, email in (
            ('usuario', 'felipe1@example.com'),
            ('supermercado', 'quaresma@example.com'),
        ):
            with self.subTest(tipo=tipo):
                dados = {
                    'tipo': tipo, 'nome': 'Felipe', 'email': email,
                    'password': '123',
                }
                if tipo == 'supermercado':
                    dados.update({
                        'supermercado_nome': 'Mercado A',
                        'supermercado_endereco': 'Rua A, 1',
                    })
                cadastro = APIClient().post(self.url, dados, format='json')
                self.assertEqual(cadastro.status_code, 201)
                self.assertEqual(cadastro.data['nome'], 'Felipe')

                login = APIClient().post('/api/auth/login/', {
                    'email': email, 'password': '123',
                }, format='json')
                self.assertEqual(login.status_code, 200)
                self.assertEqual(login.data['tipo'], tipo)
                self.assertEqual(login.data['nome'], 'Felipe')
                self.assertTrue(login.data['token'])

        self.assertEqual(get_user_model().objects.filter(first_name='Felipe').count(), 2)

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

    def test_rejeita_supermercado_sem_dados_e_aceita_senha_simples(self):
        incompleto = APIClient().post(self.url, {
            'tipo': 'supermercado', 'username': 'mercado_a',
            'email': 'mercado@example.com', 'password': self.senha,
        }, format='json')
        self.assertEqual(incompleto.status_code, 400)
        self.assertIn('supermercado_nome', incompleto.data)
        self.assertIn('supermercado_endereco', incompleto.data)

        senha_simples = APIClient().post(self.url, {
            'tipo': 'usuario', 'username': 'ana',
            'email': 'ana@example.com', 'password': '123',
        }, format='json')
        self.assertEqual(senha_simples.status_code, 201)
        self.assertTrue(get_user_model().objects.get(username='ana').check_password('123'))
        self.assertEqual(get_user_model().objects.count(), 1)
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
        resposta = api.post(
            '/api/precos/',
            {'produto': self.produto.pk, 'supermercado': self.loja.pk, 'valor': '6.49'},
            format='json',
        )
        self.assertEqual(resposta.status_code, 401)

    def test_supermercado_edita_apenas_preco_da_propria_loja(self):
        api = self.api_com_token(self.mercado_usuario)
        dados = {
            'produto': self.produto.pk, 'supermercado': self.loja.pk,
            'valor': '6.49', 'estoque': 20,
        }
        resposta = api.post('/api/precos/', dados, format='json')
        self.assertEqual(resposta.status_code, 201)
        preco_id = resposta.data['id']

        dados['valor'] = '5.99'
        dados['estoque'] = 12
        self.assertEqual(api.put(f'/api/precos/{preco_id}/', dados, format='json').status_code, 200)
        self.assertEqual(Preco.objects.get(pk=preco_id).valor, Decimal('5.99'))
        self.assertEqual(Preco.objects.get(pk=preco_id).estoque, 12)

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

    def test_supermercado_cria_produto_e_cada_loja_informa_seu_preco(self):
        mercado_a = self.api_com_token(self.mercado_usuario)
        mercado_b = self.api_com_token(self.outro_mercado_usuario)

        criado = mercado_a.post('/api/produtos/', {
            'nome': 'Feijão 1 kg', 'categoria': 'Mercearia',
        }, format='json')
        self.assertEqual(criado.status_code, 201)
        produto_id = criado.data['id']

        duplicado = mercado_b.post('/api/produtos/', {
            'nome': 'feijão 1 kg', 'categoria': 'Mercearia',
        }, format='json')
        self.assertEqual(duplicado.status_code, 400)
        self.assertIn('nome', duplicado.data)
        self.assertEqual(Produto.objects.filter(nome__iexact='Feijão 1 kg').count(), 1)

        self.assertEqual(mercado_a.put(f'/api/produtos/{produto_id}/', {
            'nome': 'Outro nome', 'categoria': 'Mercearia',
        }, format='json').status_code, 403)
        self.assertEqual(mercado_a.delete(f'/api/produtos/{produto_id}/').status_code, 403)

        for api, loja, valor, estoque in (
            (mercado_a, self.loja, '6.49', 20),
            (mercado_b, self.outra_loja, '5.99', 8),
        ):
            resposta = api.post('/api/precos/', {
                'produto': produto_id, 'supermercado': loja.pk,
                'valor': valor, 'estoque': estoque,
            }, format='json')
            self.assertEqual(resposta.status_code, 201)
            self.assertEqual(resposta.data['estoque'], estoque)

        comparacao = APIClient().get(f'/api/produtos/{produto_id}/comparar/')
        self.assertEqual(comparacao.status_code, 200)
        self.assertEqual(
            [(item['supermercado_nome'], item['valor']) for item in comparacao.data],
            [('Mercado B', '5.99'), ('Mercado A', '6.49')],
        )
        self.assertEqual([item['estoque'] for item in comparacao.data], [8, 20])

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

    def test_catalogo_preserva_imagens_sem_campo_de_upload(self):
        produto = Produto.objects.exclude(imagem='').first()
        resposta = self.client.get(f'/api/produtos/{produto.pk}/')
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.data['imagem'], produto.imagem)
        self.assertNotIn('foto', resposta.data)
        self.assertEqual(self.client.post(f'/api/produtos/{produto.pk}/foto/', {}).status_code, 404)

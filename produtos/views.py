from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import authenticate, get_user_model
from django.db import transaction, OperationalError
from django.db.models import F
from django.db.models.deletion import ProtectedError
from rest_framework.authtoken.models import Token
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.generics import get_object_or_404
from rest_framework.exceptions import PermissionDenied

from .models import Supermercado, Produto, Preco, Pedido, ItemPedido
from .permissions import (
    LeituraPublicaCadastroSupermercado,
    LeituraPublicaEscritaAdmin,
    LeituraPublicaEscritaAutenticada,
)
from .serializers import (CadastroSerializer, ComparacaoCarrinhoSerializer, SupermercadoSerializer,
                          ProdutoSerializer, PrecoSerializer, CriarPedidoSerializer,
                          PedidoSerializer, StatusPedidoSerializer)


def pedidos_visiveis(usuario):
    pedidos = Pedido.objects.select_related('cliente', 'supermercado').prefetch_related('itens__produto')
    if usuario.is_staff:
        return pedidos
    if usuario.supermercados.exists():
        return pedidos.filter(supermercado__responsavel=usuario)
    return pedidos.filter(cliente=usuario)


class EstoqueAlterado(Exception):
    pass


class PedidoList(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(PedidoSerializer(pedidos_visiveis(request.user), many=True, context={'request': request}).data)

    def post(self, request):
        if request.user.is_staff or request.user.supermercados.exists():
            raise PermissionDenied('Entre como cliente para fazer um pedido.')
        serializer = CriarPedidoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data
        quantidades = {}
        for item in dados['itens']:
            produto_id = item['produto'].pk
            quantidades[produto_id] = quantidades.get(produto_id, 0) + item['quantidade']

        try:
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=request.user.pk)
                existente = Pedido.objects.filter(cliente=request.user, chave=dados['chave']).first()
                if existente:
                    mesmos_itens = {item.produto_id: item.quantidade for item in existente.itens.all()} == quantidades
                    iguais = (existente.supermercado_id == dados['supermercado'].pk
                              and existente.total == dados['total_esperado'] and mesmos_itens
                              and all(getattr(existente, campo) == dados[campo] for campo in
                                      ('recebimento', 'pagamento', 'endereco', 'observacoes', 'cupom')))
                    if not iguais:
                        return Response({'detail': 'Esta confirmação já foi usada para outro pedido.'}, status=409)
                    return Response(PedidoSerializer(existente, context={'request': request}).data)

                precos = list(Preco.objects.select_for_update().filter(
                    supermercado=dados['supermercado'], produto_id__in=quantidades
                ).select_related('produto').order_by('produto_id'))
                por_produto = {preco.produto_id: preco for preco in precos}
                faltantes = []
                for produto_id, quantidade in quantidades.items():
                    preco = por_produto.get(produto_id)
                    if not preco or preco.estoque is None or preco.estoque < quantidade:
                        faltantes.append(produto_id)
                if faltantes:
                    return Response({'detail': 'O supermercado não tem estoque suficiente para todos os itens.',
                                     'produtos_indisponiveis': faltantes}, status=409)
                subtotal = sum((p.valor * quantidades[p.produto_id] for p in precos), Decimal('0.00'))
                taxa = Decimal('5.00') if dados['recebimento'] == 'delivery' else Decimal('0.00')
                percentual = {'SHOPWISE10': Decimal('.10'), 'ECONOMIA5': Decimal('.05')}.get(dados['cupom'], Decimal('0'))
                desconto = (subtotal * percentual).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
                total = subtotal + taxa - desconto
                if total != dados['total_esperado']:
                    return Response({'detail': 'Os preços mudaram. Confira o novo total e confirme novamente.',
                                     'subtotal_atual': format(subtotal, '.2f'), 'total_atual': format(total, '.2f')}, status=409)
                pedido = Pedido.objects.create(
                    cliente=request.user, supermercado=dados['supermercado'], chave=dados['chave'],
                    subtotal=subtotal, taxa_entrega=taxa, desconto=desconto, total=total,
                    **{campo: dados[campo] for campo in ('recebimento', 'pagamento', 'endereco', 'observacoes', 'cupom')}
                )
                for preco in precos:
                    quantidade = quantidades[preco.produto_id]
                    # A condição também evita vender além do estoque no SQLite.
                    alterado = Preco.objects.filter(pk=preco.pk, estoque__gte=quantidade, valor=preco.valor).update(
                        estoque=F('estoque') - quantidade
                    )
                    if not alterado:
                        raise EstoqueAlterado()
                    ItemPedido.objects.create(pedido=pedido, produto=preco.produto, nome=preco.produto.nome,
                                              quantidade=quantidade, preco_unitario=preco.valor,
                                              subtotal=preco.valor * quantidade)
        except EstoqueAlterado:
            return Response({'detail': 'O estoque está sendo atualizado. Tente confirmar novamente.'}, status=409)
        except OperationalError as erro:
            if 'locked' not in str(erro).lower():
                raise
            return Response({'detail': 'Outra confirmação está em andamento. Tente novamente.'}, status=409)
        return Response(PedidoSerializer(pedido, context={'request': request}).data, status=201)


class PedidoDetalhe(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        pedido = get_object_or_404(pedidos_visiveis(request.user), pk=pk)
        return Response(PedidoSerializer(pedido, context={'request': request}).data)

    def patch(self, request, pk):
        serializer = StatusPedidoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            pedido = get_object_or_404(Pedido.objects.select_for_update(), pk=pk)
            if not pode_gerenciar_loja(request.user, pedido.supermercado):
                raise PermissionDenied('Somente o responsável pelo supermercado pode atualizar este pedido.')
            novo = serializer.validated_data['status']
            proximo = {'recebido': 'em_preparacao', 'em_preparacao': 'concluido'}
            if novo != pedido.status and proximo.get(pedido.status) != novo:
                return Response({'detail': 'Avance de Recebido para Em preparação e depois para Concluído.'}, status=400)
            pedido.status = novo
            pedido.save(update_fields=['status', 'atualizado_em'])
        return Response(PedidoSerializer(pedido, context={'request': request}).data)


class CadastroView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CadastroSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data

        with transaction.atomic():
            usuario = get_user_model().objects.create_user(
                username=dados['username'],
                first_name=dados.get('nome') or dados['username'],
                email=dados['email'],
                password=dados['password'],
            )
            supermercados = []
            if dados['tipo'] == 'supermercado':
                mercado = Supermercado.objects.create(
                    nome=dados['supermercado_nome'],
                    endereco=dados['supermercado_endereco'],
                    responsavel=usuario,
                )
                supermercados.append({'id': mercado.pk, 'nome': mercado.nome})

        return Response({
            'usuario': usuario.username,
            'nome': usuario.first_name,
            'tipo': 'supermercado' if supermercados else 'usuario',
            'supermercados': supermercados,
        }, status=201)


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username') or request.data.get('email')
        password = request.data.get('password')
        if not username or not password:
            return Response({'detail': 'Informe e-mail e senha.'}, status=400)

        if '@' in username:
            usuarios = get_user_model().objects.filter(email__iexact=username)
            if usuarios.count() == 1:
                username = usuarios.first().get_username()

        user = authenticate(username=username, password=password)
        if user is None:
            return Response({'detail': 'Credenciais inválidas.'}, status=401)

        token, _ = Token.objects.get_or_create(user=user)
        supermercados = list(user.supermercados.values('id', 'nome'))
        tipo = 'administrador' if user.is_staff else (
            'supermercado' if supermercados else 'usuario'
        )
        return Response({
            'token': token.key,
            'usuario': user.username,
            'nome': user.first_name,
            'tipo': tipo,
            'supermercados': supermercados,
        })


def pode_gerenciar_loja(user, supermercado):
    return user.is_staff or supermercado.responsavel_id == user.pk


class SupermercadoList(APIView):
    permission_classes = [LeituraPublicaEscritaAdmin]

    def get(self, request):
        supermercados = Supermercado.objects.all()
        serializer = SupermercadoSerializer(supermercados, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = SupermercadoSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


class SupermercadoDetalhe(APIView):
    permission_classes = [LeituraPublicaEscritaAdmin]

    def get(self, request, pk):
        supermercado = get_object_or_404(Supermercado, pk=pk)
        serializer = SupermercadoSerializer(supermercado)
        return Response(serializer.data)

    def put(self, request, pk):
        supermercado = get_object_or_404(Supermercado, pk=pk)
        serializer = SupermercadoSerializer(supermercado, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        supermercado = get_object_or_404(Supermercado, pk=pk)
        try:
            supermercado.delete()
        except ProtectedError:
            return Response({'detail': 'Este supermercado possui pedidos e não pode ser removido.'}, status=409)
        return Response(status=204)


class ProdutoList(APIView):
    permission_classes = [LeituraPublicaCadastroSupermercado]

    def get(self, request):
        produtos = Produto.objects.all()
        serializer = ProdutoSerializer(produtos, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ProdutoSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


class ProdutoDetalhe(APIView):
    permission_classes = [LeituraPublicaEscritaAdmin]

    def get(self, request, pk):
        produto = get_object_or_404(Produto, pk=pk)
        serializer = ProdutoSerializer(produto)
        return Response(serializer.data)

    def put(self, request, pk):
        produto = get_object_or_404(Produto, pk=pk)
        serializer = ProdutoSerializer(produto, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        produto = get_object_or_404(Produto, pk=pk)
        produto.delete()
        return Response(status=204)


class PrecoList(APIView):
    permission_classes = [LeituraPublicaEscritaAutenticada]

    def get(self, request):
        precos = Preco.objects.all()
        serializer = PrecoSerializer(precos, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = PrecoSerializer(data=request.data)
        if serializer.is_valid():
            if not pode_gerenciar_loja(request.user, serializer.validated_data['supermercado']):
                raise PermissionDenied('Você não pode alterar preços deste supermercado.')
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


class PrecoDetalhe(APIView):
    permission_classes = [LeituraPublicaEscritaAutenticada]

    def get(self, request, pk):
        preco = get_object_or_404(Preco, pk=pk)
        serializer = PrecoSerializer(preco)
        return Response(serializer.data)

    def put(self, request, pk):
        preco = get_object_or_404(Preco, pk=pk)
        if not pode_gerenciar_loja(request.user, preco.supermercado):
            raise PermissionDenied('Você não pode alterar preços deste supermercado.')
        serializer = PrecoSerializer(preco, data=request.data)
        if serializer.is_valid():
            if not pode_gerenciar_loja(request.user, serializer.validated_data['supermercado']):
                raise PermissionDenied('Você não pode alterar preços deste supermercado.')
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        preco = get_object_or_404(Preco, pk=pk)
        if not pode_gerenciar_loja(request.user, preco.supermercado):
            raise PermissionDenied('Você não pode alterar preços deste supermercado.')
        preco.delete()
        return Response(status=204)


class ComparaCarrinho(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ComparacaoCarrinhoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        itens = {}
        for item in serializer.validated_data['itens']:
            produto = item['produto']
            if produto.pk not in itens:
                itens[produto.pk] = {'produto': produto, 'quantidade': 0}
            itens[produto.pk]['quantidade'] += item['quantidade']

        precos = {
            (preco.supermercado_id, preco.produto_id): preco
            for preco in Preco.objects.filter(produto_id__in=itens)
        }
        resultados = []
        for mercado in Supermercado.objects.all():
            linhas = []
            total = Decimal('0.00')
            completo = True
            for produto_id, item in itens.items():
                preco = precos.get((mercado.pk, produto_id))
                estoque = preco.estoque if preco else None
                disponivel = preco is not None and estoque is not None and estoque >= item['quantidade']
                if not preco:
                    motivo = 'Produto sem preço cadastrado neste supermercado.'
                elif estoque is None:
                    motivo = 'Estoque não informado.'
                elif estoque < item['quantidade']:
                    motivo = 'Estoque insuficiente.'
                else:
                    motivo = ''
                subtotal = preco.valor * item['quantidade'] if preco else None
                if disponivel:
                    total += subtotal
                else:
                    completo = False
                linhas.append({
                    'oferta': preco.pk if preco else None,
                    'produto': produto_id,
                    'nome': item['produto'].nome,
                    'quantidade': item['quantidade'],
                    'estoque': estoque,
                    'preco_unitario': format(preco.valor, '.2f') if preco else None,
                    'subtotal': format(subtotal, '.2f') if disponivel else None,
                    'disponivel': disponivel,
                    'motivo': motivo,
                })
            resultados.append({
                'supermercado': mercado.pk,
                'supermercado_nome': mercado.nome,
                'supermercado_endereco': mercado.endereco,
                'completo': completo,
                'total': format(total, '.2f') if completo else None,
                'economia': None,
                'itens': linhas,
            })

        completos = [Decimal(mercado['total']) for mercado in resultados if mercado['completo']]
        menor_total = min(completos) if completos else None
        maior_total = max(completos) if completos else None
        for mercado in resultados:
            if mercado['completo']:
                mercado['economia'] = format(maior_total - Decimal(mercado['total']), '.2f')
        resultados.sort(key=lambda mercado: (
            not mercado['completo'],
            Decimal(mercado['total']) if mercado['completo'] else Decimal('0'),
            mercado['supermercado_nome'].casefold(),
        ))
        return Response({
            'menor_total': format(menor_total, '.2f') if menor_total is not None else None,
            'supermercados': resultados,
        })


class ComparaPreco(APIView):
    permission_classes = [AllowAny]

    def get(self, request, produto_id):
        produto = get_object_or_404(Produto, pk=produto_id)
        precos = Preco.objects.filter(produto=produto, estoque__gt=0).select_related('supermercado').order_by('valor')
        serializer = PrecoSerializer(precos, many=True)
        return Response(serializer.data)

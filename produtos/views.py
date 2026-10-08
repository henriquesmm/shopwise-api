from decimal import Decimal

from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from django.db.models import F
from rest_framework.authtoken.models import Token
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.generics import get_object_or_404
from rest_framework.exceptions import PermissionDenied

from .models import Supermercado, Produto, Preco, ItemCarrinho
from .permissions import (
    LeituraPublicaCadastroSupermercado,
    LeituraPublicaEscritaAdmin,
    LeituraPublicaEscritaAutenticada,
)
from .serializers import (
    CadastroSerializer,
    SupermercadoSerializer,
    ProdutoSerializer,
    PrecoSerializer,
    ItemCarrinhoSerializer,
    QuantidadeCarrinhoSerializer,
)


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
        supermercado.delete()
        return Response(status=204)


class ProdutoList(APIView):
    permission_classes = [LeituraPublicaCadastroSupermercado]

    def get(self, request):
        produtos = Produto.objects.all()
        nome = request.query_params.get('nome', '').strip()
        categoria = request.query_params.get('categoria', '').strip()

        if nome:
            produtos = produtos.filter(nome__icontains=nome)
        if categoria:
            produtos = produtos.filter(categoria__iexact=categoria)

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


class ComparaPreco(APIView):
    permission_classes = [AllowAny]

    def get(self, request, produto_id):
        produto = get_object_or_404(Produto, pk=produto_id)
        precos = Preco.objects.filter(produto=produto).select_related('supermercado').order_by('valor')
        serializer = PrecoSerializer(precos, many=True)
        return Response(serializer.data)


class CarrinhoList(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        itens = list(
            ItemCarrinho.objects.filter(usuario=request.user)
            .select_related('preco__produto', 'preco__supermercado')
            .order_by('id')
        )
        total = sum(
            (item.preco.valor * item.quantidade for item in itens),
            Decimal('0.00'),
        )
        return Response({
            'itens': ItemCarrinhoSerializer(itens, many=True).data,
            'total': f'{total:.2f}',
        })

    def post(self, request):
        serializer = ItemCarrinhoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data

        with transaction.atomic():
            item, criado = ItemCarrinho.objects.get_or_create(
                usuario=request.user,
                preco=dados['preco'],
                defaults={'quantidade': dados['quantidade']},
            )
            if not criado:
                ItemCarrinho.objects.filter(pk=item.pk).update(
                    quantidade=F('quantidade') + dados['quantidade']
                )
                item.refresh_from_db()

        return Response(ItemCarrinhoSerializer(item).data, status=201 if criado else 200)


class CarrinhoDetalhe(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        item = get_object_or_404(ItemCarrinho, pk=pk, usuario=request.user)
        return Response(ItemCarrinhoSerializer(item).data)

    def put(self, request, pk):
        item = get_object_or_404(ItemCarrinho, pk=pk, usuario=request.user)
        serializer = QuantidadeCarrinhoSerializer(item, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(ItemCarrinhoSerializer(item).data)

    def delete(self, request, pk):
        item = get_object_or_404(ItemCarrinho, pk=pk, usuario=request.user)
        item.delete()
        return Response(status=204)

from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.validators import UnicodeUsernameValidator
from rest_framework import serializers

from .models import Supermercado, Produto, Preco, ItemCarrinho


class CadastroSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=['usuario', 'supermercado'])
    nome = serializers.CharField(max_length=150, required=False)
    username = serializers.CharField(
        max_length=150, required=False, validators=[UnicodeUsernameValidator()]
    )
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    supermercado_nome = serializers.CharField(max_length=100, required=False)
    supermercado_endereco = serializers.CharField(max_length=200, required=False)

    def validate_username(self, value):
        if get_user_model().objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('Este nome de usuário já está em uso.')
        if '@' in value and get_user_model().objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Este nome de usuário já está em uso como e-mail.')
        return value

    def validate_email(self, value):
        if get_user_model().objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Este e-mail já está em uso.')
        if get_user_model().objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('Este e-mail já está em uso como nome de usuário.')
        return value

    def validate(self, attrs):
        if not attrs.get('nome') and not attrs.get('username'):
            raise serializers.ValidationError({'nome': 'Informe seu nome.'})

        if attrs['tipo'] == 'supermercado':
            faltantes = {}
            if not attrs.get('supermercado_nome'):
                faltantes['supermercado_nome'] = 'Informe o nome do supermercado.'
            if not attrs.get('supermercado_endereco'):
                faltantes['supermercado_endereco'] = 'Informe o endereço do supermercado.'
            if faltantes:
                raise serializers.ValidationError(faltantes)
        elif attrs.get('supermercado_nome') or attrs.get('supermercado_endereco'):
            raise serializers.ValidationError({
                'tipo': 'Escolha supermercado para informar os dados da loja.'
            })

        # O username continua único internamente no Django. O nome pode se repetir.
        if not attrs.get('username'):
            email = attrs['email']
            attrs['username'] = email if len(email) <= 150 else f'conta_{uuid4().hex}'

        return attrs


class SupermercadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supermercado
        fields = '__all__'

class ProdutoSerializer(serializers.ModelSerializer):
    def validate_nome(self, value):
        produtos = Produto.objects.filter(nome__iexact=value)
        if self.instance:
            produtos = produtos.exclude(pk=self.instance.pk)
        if produtos.exists():
            raise serializers.ValidationError(
                'Este produto já existe. Use o ID do produto cadastrado.'
            )
        return value

    class Meta:
        model = Produto
        fields = '__all__'

class PrecoSerializer(serializers.ModelSerializer):
    supermercado_nome = serializers.CharField(source='supermercado.nome', read_only=True)

    class Meta:
        model = Preco
        fields = '__all__'


class ItemCarrinhoSerializer(serializers.ModelSerializer):
    quantidade = serializers.IntegerField(min_value=1, max_value=2147483647, default=1)
    produto_id = serializers.IntegerField(source='preco.produto_id', read_only=True)
    produto_nome = serializers.CharField(source='preco.produto.nome', read_only=True)
    supermercado_id = serializers.IntegerField(source='preco.supermercado_id', read_only=True)
    supermercado_nome = serializers.CharField(source='preco.supermercado.nome', read_only=True)
    valor_unitario = serializers.DecimalField(
        source='preco.valor', max_digits=10, decimal_places=2, read_only=True
    )
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = ItemCarrinho
        fields = (
            'id', 'preco', 'produto_id', 'produto_nome', 'supermercado_id',
            'supermercado_nome', 'valor_unitario', 'quantidade', 'subtotal',
        )

    def get_subtotal(self, item):
        return f'{item.preco.valor * item.quantidade:.2f}'


class QuantidadeCarrinhoSerializer(serializers.ModelSerializer):
    quantidade = serializers.IntegerField(min_value=1, max_value=2147483647)

    class Meta:
        model = ItemCarrinho
        fields = ('quantidade',)

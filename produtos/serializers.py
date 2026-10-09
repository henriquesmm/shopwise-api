from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.validators import UnicodeUsernameValidator
from rest_framework import serializers
from .models import Supermercado, Produto, Preco, Pedido, ItemPedido


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

        if not attrs.get('username'):
            email = attrs['email']
            attrs['username'] = email if len(email) <= 150 else f'conta_{uuid4().hex}'
        return attrs


class ItemCarrinhoSerializer(serializers.Serializer):
    produto = serializers.PrimaryKeyRelatedField(queryset=Produto.objects.all())
    quantidade = serializers.IntegerField(min_value=1)


class ComparacaoCarrinhoSerializer(serializers.Serializer):
    itens = ItemCarrinhoSerializer(many=True, allow_empty=False)


class CriarPedidoSerializer(ComparacaoCarrinhoSerializer):
    supermercado = serializers.PrimaryKeyRelatedField(queryset=Supermercado.objects.all())
    chave = serializers.UUIDField()
    total_esperado = serializers.DecimalField(max_digits=20, decimal_places=2, min_value=0)
    recebimento = serializers.ChoiceField(choices=['delivery', 'pickup'])
    pagamento = serializers.ChoiceField(choices=['pix', 'credito', 'debito', 'entrega'])
    endereco = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    observacoes = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')
    cupom = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')

    def validate_cupom(self, value):
        value = value.upper()
        if value not in ('', 'SHOPWISE10', 'ECONOMIA5'):
            raise serializers.ValidationError('Cupom inválido.')
        return value

    def validate(self, attrs):
        if attrs['recebimento'] == 'delivery' and not attrs['endereco']:
            raise serializers.ValidationError({'endereco': 'Informe o endereço de entrega.'})
        if attrs['recebimento'] == 'pickup':
            attrs['endereco'] = ''
        return attrs


class ItemPedidoSerializer(serializers.ModelSerializer):
    imagem = serializers.CharField(source='produto.imagem', read_only=True, default='')

    class Meta:
        model = ItemPedido
        fields = ['produto', 'nome', 'quantidade', 'preco_unitario', 'subtotal', 'imagem']


class PedidoSerializer(serializers.ModelSerializer):
    cliente_nome = serializers.SerializerMethodField()
    supermercado_nome = serializers.CharField(source='supermercado.nome', read_only=True)
    supermercado_endereco = serializers.CharField(source='supermercado.endereco', read_only=True)
    status_nome = serializers.CharField(source='get_status_display', read_only=True)
    itens = ItemPedidoSerializer(many=True, read_only=True)

    def get_cliente_nome(self, pedido):
        return pedido.cliente.first_name or pedido.cliente.username

    class Meta:
        model = Pedido
        fields = ['id', 'cliente_nome', 'supermercado', 'supermercado_nome', 'supermercado_endereco',
                  'status', 'status_nome', 'recebimento', 'pagamento', 'endereco', 'observacoes', 'cupom',
                  'subtotal', 'taxa_entrega', 'desconto', 'total', 'criado_em', 'atualizado_em', 'itens']


class StatusPedidoSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Pedido.Status.choices)


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
                'Este produto já existe. Use o produto cadastrado.'
            )
        return value

    class Meta:
        model = Produto
        fields = '__all__'
        extra_kwargs = {'imagem': {'read_only': True}}

class PrecoSerializer(serializers.ModelSerializer):
    supermercado_nome = serializers.CharField(source='supermercado.nome', read_only=True)

    class Meta:
        model = Preco
        fields = '__all__'

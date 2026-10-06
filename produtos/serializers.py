from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from .models import Supermercado, Produto, Preco


class CadastroSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=['usuario', 'supermercado'])
    username = serializers.CharField(max_length=150, validators=[UnicodeUsernameValidator()])
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

        usuario = get_user_model()(username=attrs['username'], email=attrs['email'])
        try:
            validate_password(attrs['password'], user=usuario)
        except DjangoValidationError as erro:
            raise serializers.ValidationError({'password': erro.messages})
        return attrs


class SupermercadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supermercado
        fields = '__all__'

class ProdutoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Produto
        fields = '__all__'

class PrecoSerializer(serializers.ModelSerializer):
    supermercado_nome = serializers.CharField(source='supermercado.nome', read_only=True)

    class Meta:
        model = Preco
        fields = '__all__'

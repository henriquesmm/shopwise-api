from rest_framework import serializers
from .models import Supermercado


class SupermercadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supermercado
        fields = '__all__'

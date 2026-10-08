from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Supermercado(models.Model):
    nome = models.CharField(max_length=100)
    endereco = models.CharField(max_length=200)
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='supermercados',
        null=True,
        blank=True,
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nome


class Produto(models.Model):
    nome = models.CharField(max_length=100)
    categoria = models.CharField(max_length=100, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nome

class Preco(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    supermercado = models.ForeignKey(Supermercado, on_delete=models.CASCADE)
    valor = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['produto', 'supermercado'],
                name='preco_unico_produto_supermercado',
            ),
            models.CheckConstraint(
                condition=Q(valor__gt=0),
                name='preco_valor_positivo',
            ),
        ]


class ItemCarrinho(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='itens_carrinho',
    )
    preco = models.ForeignKey(Preco, on_delete=models.CASCADE)
    quantidade = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['usuario', 'preco'],
                name='item_unico_usuario_preco',
            ),
            models.CheckConstraint(
                condition=Q(quantidade__gte=1),
                name='item_carrinho_quantidade_positiva',
            ),
        ]

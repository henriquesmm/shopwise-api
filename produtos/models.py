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
    imagem = models.CharField(max_length=100, blank=True)
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
    estoque = models.PositiveIntegerField(null=True, blank=True)
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


class Pedido(models.Model):
    class Status(models.TextChoices):
        RECEBIDO = 'recebido', 'Recebido'
        PREPARACAO = 'em_preparacao', 'Em preparação'
        CONCLUIDO = 'concluido', 'Concluído'

    cliente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='pedidos')
    supermercado = models.ForeignKey(Supermercado, on_delete=models.PROTECT, related_name='pedidos')
    chave = models.UUIDField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEBIDO)
    recebimento = models.CharField(max_length=10, choices=[('delivery', 'Entrega'), ('pickup', 'Retirada')])
    pagamento = models.CharField(max_length=10, choices=[('pix', 'PIX'), ('credito', 'Crédito'), ('debito', 'Débito'), ('entrega', 'Na entrega')])
    endereco = models.CharField(max_length=200, blank=True)
    observacoes = models.CharField(max_length=1000, blank=True)
    cupom = models.CharField(max_length=20, blank=True)
    subtotal = models.DecimalField(max_digits=20, decimal_places=2)
    taxa_entrega = models.DecimalField(max_digits=20, decimal_places=2)
    desconto = models.DecimalField(max_digits=20, decimal_places=2)
    total = models.DecimalField(max_digits=20, decimal_places=2)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-criado_em', '-id']
        constraints = [models.UniqueConstraint(fields=['cliente', 'chave'], name='pedido_unico_cliente_chave')]


class ItemPedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(Produto, on_delete=models.SET_NULL, null=True)
    nome = models.CharField(max_length=100)
    quantidade = models.PositiveIntegerField()
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=20, decimal_places=2)

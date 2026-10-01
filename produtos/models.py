from django.db import models


class Supermercado(models.Model):
    nome = models.CharField(max_length=100)
    endereco = models.CharField(max_length=200)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nome

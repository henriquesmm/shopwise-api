from django.contrib import admin

from .models import Preco, Produto, Supermercado, Pedido, ItemPedido


@admin.register(Supermercado)
class SupermercadoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'endereco', 'responsavel')
    search_fields = ('nome', 'responsavel__username')


admin.site.register(Produto)
admin.site.register(Preco)
admin.site.register(Pedido)
admin.site.register(ItemPedido)

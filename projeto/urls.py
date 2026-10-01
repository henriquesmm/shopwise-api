from django.contrib import admin
from django.urls import path
from produtos.views import SupermercadoList, SupermercadoDetalhe, ProdutoList, ProdutoDetalhe

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/supermercados/', SupermercadoList.as_view()),
    path('api/supermercados/<int:pk>/', SupermercadoDetalhe.as_view()),
    path('api/produtos/', ProdutoList.as_view()),
    path('api/produtos/<int:pk>/', ProdutoDetalhe.as_view()),
]
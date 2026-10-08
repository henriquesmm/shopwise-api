from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView
from produtos.views import (
    SupermercadoList, SupermercadoDetalhe, ProdutoList, ProdutoDetalhe,
    PrecoList, PrecoDetalhe, ComparaPreco, CadastroView, LoginView,
    CarrinhoList, CarrinhoDetalhe,
)

urlpatterns = [
    path('', RedirectView.as_view(url='/static/src/pages/login.html', permanent=False)),
    path('admin/', admin.site.urls),
    path('api/auth/cadastro/', CadastroView.as_view()),
    path('api/auth/login/', LoginView.as_view()),
    path('api/supermercados/', SupermercadoList.as_view()),
    path('api/supermercados/<int:pk>/', SupermercadoDetalhe.as_view()),
    path('api/produtos/', ProdutoList.as_view()),
    path('api/produtos/<int:pk>/', ProdutoDetalhe.as_view()),
    path('api/precos/', PrecoList.as_view()),
    path('api/precos/<int:pk>/', PrecoDetalhe.as_view()),
    path('api/produtos/<int:produto_id>/comparar/', ComparaPreco.as_view()),
    path('api/carrinho/', CarrinhoList.as_view()),
    path('api/carrinho/<int:pk>/', CarrinhoDetalhe.as_view()),
]

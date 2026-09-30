from rest_framework.views import APIView 
from rest_framework.response import Response
from rest_framework.permissions import AllowAny 
from rest_framework.generics import get_object_or_404 
from .models import Produto 
from .serializers import ProdutoSerializer
class ProdutoList(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        produtos = Produto.objects.all()
        serializer = ProdutoSerializer(produtos, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ProdutoSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)


class ProdutoDetalhe(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        produto = get_object_or_404(Produto, pk=pk)
        serializer = ProdutoSerializer(produto)
        return Response(serializer.data)

    def put(self, request, pk):
        produto = get_object_or_404(Produto, pk=pk)
        serializer = ProdutoSerializer(produto, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        produto = get_object_or_404(Produto, pk=pk)
        produto.delete()
        return Response(status=204)
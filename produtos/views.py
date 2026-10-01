from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.generics import get_object_or_404

from .models import Supermercado
from .serializers import SupermercadoSerializer


class SupermercadoList(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        supermercados = Supermercado.objects.all()
        serializer = SupermercadoSerializer(supermercados, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = SupermercadoSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=400)


class SupermercadoDetalhe(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        supermercado = get_object_or_404(Supermercado, pk=pk)
        serializer = SupermercadoSerializer(supermercado)
        return Response(serializer.data)

    def put(self, request, pk):
        supermercado = get_object_or_404(Supermercado, pk=pk)
        serializer = SupermercadoSerializer(supermercado, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        supermercado = get_object_or_404(Supermercado, pk=pk)
        supermercado.delete()
        return Response(status=204)
